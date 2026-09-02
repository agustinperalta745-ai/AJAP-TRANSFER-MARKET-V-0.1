"""Anuncia en Radio Pasillo los resultados oficiales de clásicos cargados por captura.

Se monta sobre la capa final de feedback de Liga para ejecutar solamente después
de que el resultado quedó persistido. Usa la misma tabla classic_rivals que
Discord/AJPA Mobile y una outbox persistente para no duplicar anuncios y poder
reintentar tras un reinicio si el canal no estaba disponible.
"""

from __future__ import annotations

import discord

import league_automation_patch as league
import league_result_feedback_patch as feedback


_BASE_FEEDBACK_HANDLE = feedback._feedback_handle
_BASE_FEEDBACK_APPLY = feedback.apply_league_result_feedback_patch


def _table_exists(conn, table: str) -> bool:
    return bool(
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
            (str(table),),
        ).fetchone()
    )


def _ensure_schema(conn) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS classic_result_radio_outbox (
            source_message_id INTEGER PRIMARY KEY,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS classic_result_radio_announcements (
            source_message_id INTEGER PRIMARY KEY,
            match_id INTEGER NOT NULL,
            classic_id INTEGER NOT NULL,
            channel_id INTEGER NOT NULL,
            message_id INTEGER NOT NULL,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """
    )
    conn.commit()


def _same_team(left: str, right: str) -> bool:
    if league.norm(left) == league.norm(right):
        return True
    try:
        a = league.canonical_team(left)
        b = league.canonical_team(right)
        return bool(a and b and league.norm(a) == league.norm(b))
    except Exception:
        return False


def _classic_for_match(conn, home: str, away: str):
    if not _table_exists(conn, "classic_rivals"):
        return None
    for row in conn.execute(
        "SELECT id, club_a, club_b FROM classic_rivals WHERE active=1 ORDER BY id DESC"
    ).fetchall():
        club_a = str(row["club_a"])
        club_b = str(row["club_b"])
        direct = _same_team(home, club_a) and _same_team(away, club_b)
        reverse = _same_team(home, club_b) and _same_team(away, club_a)
        if direct or reverse:
            return row
    return None


def _match_and_classic(runtime, guild_id: int, source_message_id: int):
    conn = league.db(runtime, int(guild_id))
    try:
        _ensure_schema(conn)
        match = conn.execute(
            """
            SELECT id, source_message_id, home_team, away_team, home_goals, away_goals
            FROM league_matches
            WHERE source_message_id=?
            LIMIT 1
            """,
            (int(source_message_id),),
        ).fetchone()
        if not match:
            return None, None, False

        classic = _classic_for_match(
            conn,
            str(match["home_team"]),
            str(match["away_team"]),
        )
        if not classic:
            return match, None, False

        announced = conn.execute(
            "SELECT 1 FROM classic_result_radio_announcements WHERE source_message_id=? LIMIT 1",
            (int(source_message_id),),
        ).fetchone()
        if announced:
            conn.execute(
                "DELETE FROM classic_result_radio_outbox WHERE source_message_id=?",
                (int(source_message_id),),
            )
            conn.commit()
            return match, classic, True

        conn.execute(
            "INSERT OR IGNORE INTO classic_result_radio_outbox (source_message_id) VALUES (?)",
            (int(source_message_id),),
        )
        conn.commit()
        return match, classic, False
    finally:
        conn.close()


def _normalized_channel_name(name: str) -> str:
    return "".join(ch for ch in str(name or "").casefold() if ch.isalnum())


async def _resolve_radio_channel(runtime, bot, guild):
    if guild is None:
        return None, "NO_GUILD"

    conn = league.db(runtime, int(guild.id))
    try:
        configured_id = None
        if _table_exists(conn, "public_market_channels"):
            row = conn.execute(
                "SELECT channel_id FROM public_market_channels WHERE guild_id=? LIMIT 1",
                (int(guild.id),),
            ).fetchone()
            configured_id = int(row["channel_id"]) if row and row["channel_id"] else None
    finally:
        conn.close()

    if configured_id:
        channel = guild.get_channel(configured_id)
        if channel is None:
            try:
                channel = await bot.fetch_channel(configured_id)
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                channel = None
        if channel is not None and hasattr(channel, "send"):
            return channel, "CONFIGURED_PUBLIC_FEED"

    # Radio Pasillo puede tener emojis, espacios, puntos o guiones en el nombre.
    # Al normalizar, todos terminan conteniendo "radiopasillo".
    me = getattr(guild, "me", None)
    for channel in getattr(guild, "text_channels", []):
        if "radiopasillo" not in _normalized_channel_name(getattr(channel, "name", "")):
            continue
        if me is not None:
            try:
                perms = channel.permissions_for(me)
                if not perms.view_channel or not perms.send_messages:
                    continue
            except Exception:
                pass
        return channel, "RADIO_PASILLO_NAME"

    return None, "NOT_FOUND"


def _chicana(match) -> tuple[str, str]:
    home = str(match["home_team"])
    away = str(match["away_team"])
    hg = int(match["home_goals"])
    ag = int(match["away_goals"])
    seed = int(match["id"])

    if hg == ag:
        lines = [
            "Nadie puede sacar pecho todavía: las cargadas quedaron guardadas para la revancha.",
            "Clásico sin dueño. Mucho ruido en la previa y la cargada tendrá que esperar.",
            "Empate y a casa: hoy ninguno tiene permiso para hacerse el guapo en el grupo.",
            "Se repartieron los puntos. La próxima define quién habla y quién silencia el grupo.",
        ]
        return "🤝 **Clásico sin dueño.**", lines[seed % len(lines)]

    winner = home if hg > ag else away
    loser = away if hg > ag else home
    winner_md = discord.utils.escape_markdown(winner)
    loser_md = discord.utils.escape_markdown(loser)
    lines = [
        f"En **{loser_md}** ya preguntaron cuándo es la revancha. **{winner_md}** todavía está festejando.",
        f"**{winner_md}** se quedó con el clásico y a **{loser_md}** le toca bancarse Radio Pasillo hasta la revancha.",
        f"Dicen que en **{loser_md}** silenciaron el grupo. **{winner_md}** tiene la cargada habilitada.",
        f"El clásico tiene dueño: **{winner_md}**. Para **{loser_md}**, hoy conviene no abrir el grupo.",
        f"Ganó **{winner_md}**. En **{loser_md}** ya arrancó el operativo ‘la próxima es nuestra’.",
        f"**{winner_md}** ganó el que había que ganar. **{loser_md}** tendrá que esperar la revancha para responder.",
    ]
    return f"🏆 **{winner_md} se quedó con el clásico.**", lines[seed % len(lines)]


def _embed_for(match) -> discord.Embed:
    home = discord.utils.escape_markdown(str(match["home_team"]))
    away = discord.utils.escape_markdown(str(match["away_team"]))
    hg = int(match["home_goals"])
    ag = int(match["away_goals"])
    outcome, chicana = _chicana(match)

    embed = discord.Embed(
        title="🔥 FINAL DEL CLÁSICO",
        description=(
            f"⚔️ **{home} {hg}–{ag} {away}**\n\n"
            f"{outcome}\n\n"
            f"🎙️ **La chicana de Radio Pasillo:**\n{chicana}"
        ),
        color=discord.Color.red(),
    )
    embed.set_footer(text="📻 Radio Pasillo • AJPA")
    return embed


def _text_for(match) -> str:
    home = discord.utils.escape_markdown(str(match["home_team"]))
    away = discord.utils.escape_markdown(str(match["away_team"]))
    hg = int(match["home_goals"])
    ag = int(match["away_goals"])
    outcome, chicana = _chicana(match)
    return (
        "🔥 **FINAL DEL CLÁSICO**\n\n"
        f"⚔️ **{home} {hg}–{ag} {away}**\n\n"
        f"{outcome}\n\n"
        f"🎙️ **La chicana de Radio Pasillo:**\n{chicana}"
    )


async def publish_for_source(runtime, bot, guild, source_message_id: int) -> bool:
    match, classic, already = _match_and_classic(
        runtime, guild.id, int(source_message_id)
    )
    if not match or not classic:
        return False
    if already:
        return True

    channel, source = await _resolve_radio_channel(runtime, bot, guild)
    if channel is None:
        print(
            f"AJAP clásico resultado pendiente mensaje={source_message_id}: Radio Pasillo no encontrado"
        )
        return False

    try:
        sent = await channel.send(
            embed=_embed_for(match),
            allowed_mentions=discord.AllowedMentions.none(),
        )
        mode = "EMBED"
    except (discord.Forbidden, discord.HTTPException):
        try:
            sent = await channel.send(
                content=_text_for(match),
                allowed_mentions=discord.AllowedMentions.none(),
            )
            mode = "TEXT"
        except (discord.Forbidden, discord.HTTPException) as exc:
            print(
                f"AJAP clásico resultado envío falló mensaje={source_message_id} canal={getattr(channel, 'id', None)}: {exc}"
            )
            return False

    conn = league.db(runtime, int(guild.id))
    try:
        _ensure_schema(conn)
        conn.execute(
            """
            INSERT OR IGNORE INTO classic_result_radio_announcements
                (source_message_id, match_id, classic_id, channel_id, message_id)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                int(source_message_id),
                int(match["id"]),
                int(classic["id"]),
                int(channel.id),
                int(sent.id),
            ),
        )
        conn.execute(
            "DELETE FROM classic_result_radio_outbox WHERE source_message_id=?",
            (int(source_message_id),),
        )
        conn.commit()
    finally:
        conn.close()

    print(
        f"AJAP FINAL DEL CLÁSICO publicado mensaje={source_message_id} "
        f"canal={channel.id} source={source} mode={mode}"
    )
    return True


async def publish_pending(runtime, bot, guild) -> None:
    conn = league.db(runtime, int(guild.id))
    try:
        _ensure_schema(conn)
        rows = conn.execute(
            "SELECT source_message_id FROM classic_result_radio_outbox ORDER BY created_at LIMIT 50"
        ).fetchall()
        source_ids = [int(row["source_message_id"]) for row in rows]
    finally:
        conn.close()

    for source_id in source_ids:
        try:
            await publish_for_source(runtime, bot, guild, source_id)
        except Exception as exc:
            print(
                f"AJAP clásico resultado retry falló guild={guild.id} mensaje={source_id}: {exc}"
            )


async def _feedback_handle_with_classic_radio(runtime, bot, message):
    result = await _BASE_FEEDBACK_HANDLE(runtime, bot, message)

    # Solo las capturas del flujo Liga pueden disparar este anuncio. El handler
    # anterior ya verificó canal, evidencia, persistencia y confirmación oficial.
    if not message.guild or message.author.bot or not message.attachments:
        return result

    try:
        state = feedback._source_state(runtime, message.guild.id, message.id)
        if state["match"]:
            await publish_for_source(runtime, bot, message.guild, message.id)
    except Exception as exc:
        # Radio Pasillo nunca debe romper la carga oficial del resultado.
        print(
            f"AJAP clásico resultado post-carga falló guild={message.guild.id} mensaje={message.id}: {exc}"
        )
    return result


# El diagnóstico existente espera este nombre para considerar sano al handler.
_feedback_handle_with_classic_radio.__name__ = "_feedback_handle"
feedback._feedback_handle = _feedback_handle_with_classic_radio


def _apply_feedback_with_classic_radio(runtime, bot):
    _BASE_FEEDBACK_APPLY(runtime, bot)

    if getattr(runtime, "_ajap_classic_result_radio_ready", False):
        # Reafirmar el wrapper por si otra capa repuso el handler de feedback.
        feedback._feedback_handle = _feedback_handle_with_classic_radio
        league.handle = _feedback_handle_with_classic_radio
        return

    async def ready_listener():
        for guild in list(getattr(bot, "guilds", [])):
            try:
                await publish_pending(runtime, bot, guild)
            except Exception as exc:
                print(f"AJAP clásico resultado outbox guild={guild.id}: {exc}")

    bot.add_listener(ready_listener, "on_ready")
    runtime._ajap_classic_result_radio_ready = True
    feedback._feedback_handle = _feedback_handle_with_classic_radio
    league.handle = _feedback_handle_with_classic_radio
    print("AJAP Radio Pasillo: finales de clásicos por captura activos")


feedback.apply_league_result_feedback_patch = _apply_feedback_with_classic_radio
