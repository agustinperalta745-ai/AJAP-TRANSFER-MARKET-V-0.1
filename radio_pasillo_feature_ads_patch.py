"""Radio Pasillo: recordatorios rotativos de funciones para los DT.

Publica un mensaje corto cada dos horas como máximo por servidor. El estado se
guarda en la DB aislada de cada guild para que reinicios/reconexiones de Railway
no provoquen publicaciones duplicadas.

La publicidad de AJPA Mobile se habilita cuando AJPA_APP_DOWNLOAD_URL tiene un
link real; hasta entonces se omite de la rotación.
"""

from __future__ import annotations

import os
import time
import unicodedata
from contextlib import closing

import discord
from discord.ext import tasks

import guild_isolation_patch as guild_isolation


APP = None
BOT = None

INTERVAL_SECONDS = 2 * 60 * 60
CHECK_EVERY_MINUTES = 5
APP_DOWNLOAD_URL = (os.getenv("AJPA_APP_DOWNLOAD_URL") or "").strip()

_ADS = (
    (
        "classic",
        "🔥 **¿Ya definiste tu clásico rival?**\n"
        "Entrá a `/mercado` → **MI CLUB** → **CLÁSICO RIVAL**, elegí al rival y enviá la propuesta. "
        "El otro DT tiene que aceptarla y el historial queda registrado.",
    ),
    (
        "publish",
        "📤 **¿Tenés un jugador para negociar?**\n"
        "Desde `/mercado` → **MERCADO** → **PUBLICAR** podés ponerlo en venta, préstamo o intercambio "
        "y dejar claras las condiciones.",
    ),
    (
        "search",
        "🔎 **No hace falta esperar una publicación.**\n"
        "Usá `/mercado` → **BUSCAR** para encontrar jugadores de cualquier plantel y, cuando corresponda, "
        "hacer una oferta directamente.",
    ),
    (
        "offers",
        "📩 **Revisá tus ofertas.**\n"
        "En `/mercado` → **OFERTAS** podés ver negociaciones pendientes y responderlas sin perder el hilo "
        "de la operación.",
    ),
    (
        "my_club",
        "🏟️ **Tu club tiene su propio panel.**\n"
        "En `/mercado` → **MI CLUB** tenés plantilla, presupuesto, valor del equipo e información general "
        "en un solo lugar.",
    ),
    (
        "league",
        "🏆 **La Liga también está dentro del bot.**\n"
        "Entrá a `/mercado` → **LIGA** para consultar la tabla y los goleadores actualizados.",
    ),
    (
        "history",
        "📜 **¿Querés repasar los movimientos?**\n"
        "Usá `/mercado` → **HISTORIAL** para consultar las transferencias que ya quedaron registradas.",
    ),
    (
        "clausulazo",
        "💥 **El clausulazo también se gestiona desde AJPA.**\n"
        "Cuando el mercado esté abierto, entrá a `/mercado` → **MERCADO** → **CLAUSULAZO** para iniciar "
        "la operación con las protecciones de la liga.",
    ),
    (
        "match_search",
        "⚽ **¿Querés jugar y no encontrás rival?**\n"
        "Desde **AJPA Mobile** podés publicar que estás buscando partido; la búsqueda aparece en Discord "
        "y otro DT puede tomarla desde **IR A LA CANCHA**.",
    ),
)

_APP_AD = (
    "app",
    "📲 **DESCARGÁ AJPA MOBILE**\n"
    "Llevá la liga en el celu: buscá partido, seguí tu club y usá las funciones conectadas con Discord.\n"
    "🔗 {url}",
)


def _norm(value: str) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return "".join(ch for ch in text.casefold() if ch.isalnum())


def _conn_for_guild(guild_id: int):
    if APP is None:
        raise RuntimeError("AJPA runtime todavía no inicializado")
    if hasattr(APP, "db_for_guild"):
        return APP.db_for_guild(int(guild_id))
    if hasattr(APP, "guild_context"):
        with APP.guild_context(int(guild_id)):
            return APP.db()
    return APP.db()


def _table_exists(conn, table: str) -> bool:
    return bool(
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
            (str(table),),
        ).fetchone()
    )


def _ensure_schema(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS radio_pasillo_feature_ads_state (
            guild_id INTEGER PRIMARY KEY,
            last_sent_at INTEGER NOT NULL DEFAULT 0,
            last_ad_key TEXT,
            channel_id INTEGER,
            discord_message_id INTEGER,
            updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.commit()


def _state(conn, guild_id: int):
    _ensure_schema(conn)
    return conn.execute(
        """
        SELECT guild_id, last_sent_at, last_ad_key, channel_id, discord_message_id
        FROM radio_pasillo_feature_ads_state
        WHERE guild_id=?
        LIMIT 1
        """,
        (int(guild_id),),
    ).fetchone()


def _mark_sent(
    conn,
    guild_id: int,
    *,
    now: int,
    ad_key: str,
    channel_id: int,
    message_id: int,
) -> None:
    _ensure_schema(conn)
    conn.execute(
        """
        INSERT INTO radio_pasillo_feature_ads_state
            (guild_id, last_sent_at, last_ad_key, channel_id, discord_message_id, updated_at)
        VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(guild_id) DO UPDATE SET
            last_sent_at=excluded.last_sent_at,
            last_ad_key=excluded.last_ad_key,
            channel_id=excluded.channel_id,
            discord_message_id=excluded.discord_message_id,
            updated_at=CURRENT_TIMESTAMP
        """,
        (
            int(guild_id),
            int(now),
            str(ad_key),
            int(channel_id),
            int(message_id),
        ),
    )
    conn.commit()


def _eligible_ads():
    ads = list(_ADS)
    if APP_DOWNLOAD_URL:
        ads.append((_APP_AD[0], _APP_AD[1].format(url=APP_DOWNLOAD_URL)))
    return ads


def _next_ad(last_key: str | None):
    ads = _eligible_ads()
    if not ads:
        return None

    if last_key:
        for index, (key, _body) in enumerate(ads):
            if key == last_key:
                return ads[(index + 1) % len(ads)]

    index = (int(time.time()) // INTERVAL_SECONDS) % len(ads)
    return ads[index]


async def _resolve_radio_channel(guild):
    if guild is None:
        return None

    me = getattr(guild, "me", None)
    for channel in getattr(guild, "text_channels", []):
        if "radiopasillo" not in _norm(getattr(channel, "name", "")):
            continue
        if me is not None:
            try:
                perms = channel.permissions_for(me)
                if not perms.view_channel or not perms.send_messages:
                    continue
            except Exception:
                pass
        return channel

    configured_id = None
    try:
        with closing(_conn_for_guild(guild.id)) as conn:
            if _table_exists(conn, "public_market_channels"):
                row = conn.execute(
                    "SELECT channel_id FROM public_market_channels WHERE guild_id=? LIMIT 1",
                    (int(guild.id),),
                ).fetchone()
                configured_id = (
                    int(row["channel_id"]) if row and row["channel_id"] else None
                )
    except Exception:
        configured_id = None

    if configured_id:
        channel = guild.get_channel(configured_id)
        if channel is None and BOT is not None:
            try:
                channel = await BOT.fetch_channel(configured_id)
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                channel = None
        if channel is not None and hasattr(channel, "send"):
            return channel

    return None


def _dt_role(guild):
    if guild is None:
        return None

    configured_id = None
    try:
        with closing(_conn_for_guild(guild.id)) as conn:
            if _table_exists(conn, "dt_role_config"):
                row = conn.execute(
                    "SELECT role_id FROM dt_role_config WHERE id=1 LIMIT 1"
                ).fetchone()
                configured_id = int(row["role_id"]) if row and row["role_id"] else None
    except Exception:
        configured_id = None

    if configured_id:
        role = guild.get_role(configured_id)
        if role is not None:
            return role

    for role in getattr(guild, "roles", []):
        if (role.name or "").strip().casefold() == "dt":
            return role
    return None


async def _send_due(guild) -> bool:
    if guild is None:
        return False

    now = int(time.time())
    with closing(_conn_for_guild(guild.id)) as conn:
        row = _state(conn, guild.id)
        last_sent_at = int(row["last_sent_at"]) if row else 0
        last_key = str(row["last_ad_key"]) if row and row["last_ad_key"] else None

    if last_sent_at and now - last_sent_at < INTERVAL_SECONDS:
        return False

    channel = await _resolve_radio_channel(guild)
    if channel is None:
        print(f"AJAP publicidad Radio Pasillo: canal no encontrado guild={guild.id}")
        return False

    role = _dt_role(guild)
    if role is None:
        print(f"AJAP publicidad Radio Pasillo: rol DT no encontrado guild={guild.id}")
        return False

    selected = _next_ad(last_key)
    if selected is None:
        return False
    ad_key, body = selected

    content = (
        f"{role.mention}\n"
        "📻 **RADIO PASILLO • RECORDATORIO AJPA**\n"
        f"{body}"
    )
    try:
        sent = await channel.send(
            content=content,
            allowed_mentions=discord.AllowedMentions(
                everyone=False,
                users=False,
                roles=True,
                replied_user=False,
            ),
        )
    except (discord.Forbidden, discord.HTTPException) as exc:
        print(
            "AJAP publicidad Radio Pasillo: envío falló "
            f"guild={guild.id} channel={getattr(channel, 'id', None)} "
            f"error={type(exc).__name__}: {exc}"
        )
        return False

    with closing(_conn_for_guild(guild.id)) as conn:
        _mark_sent(
            conn,
            guild.id,
            now=now,
            ad_key=ad_key,
            channel_id=channel.id,
            message_id=sent.id,
        )

    print(
        "AJAP publicidad Radio Pasillo enviada "
        f"guild={guild.id} channel={channel.id} ad={ad_key}"
    )
    return True


@tasks.loop(minutes=CHECK_EVERY_MINUTES)
async def _ad_loop():
    if BOT is None or not BOT.is_ready():
        return
    for guild in list(getattr(BOT, "guilds", [])):
        try:
            await _send_due(guild)
        except Exception as exc:
            print(
                "AJAP publicidad Radio Pasillo: ciclo falló "
                f"guild={getattr(guild, 'id', None)} "
                f"error={type(exc).__name__}: {exc}"
            )


@_ad_loop.before_loop
async def _before_ad_loop():
    if BOT is not None:
        await BOT.wait_until_ready()


async def _on_ready_radio_ads():
    if not _ad_loop.is_running():
        _ad_loop.start()


def apply_radio_pasillo_feature_ads_patch(runtime, bot):
    global APP, BOT
    APP = runtime
    BOT = bot

    if getattr(runtime, "_ajap_radio_pasillo_feature_ads_patch", False):
        return

    bot.add_listener(_on_ready_radio_ads, "on_ready")
    runtime.radio_pasillo_send_feature_ad_if_due = _send_due
    runtime._ajap_radio_pasillo_feature_ads_patch = True
    print(
        "AJAP Radio Pasillo: publicidad rotativa activa "
        f"cada {INTERVAL_SECONDS // 3600}h"
        + (" + AJPA Mobile" if APP_DOWNLOAD_URL else " (link AJPA Mobile pendiente)")
    )


_original_apply_guild_isolation_patch = guild_isolation.apply_guild_isolation_patch


def _apply_guild_isolation_then_radio_ads(runtime, bot):
    _original_apply_guild_isolation_patch(runtime, bot)
    apply_radio_pasillo_feature_ads_patch(runtime, bot)


if not getattr(
    guild_isolation.apply_guild_isolation_patch,
    "_ajap_radio_pasillo_feature_ads_wrapped",
    False,
):
    _apply_guild_isolation_then_radio_ads._ajap_radio_pasillo_feature_ads_wrapped = True
    guild_isolation.apply_guild_isolation_patch = _apply_guild_isolation_then_radio_ads
