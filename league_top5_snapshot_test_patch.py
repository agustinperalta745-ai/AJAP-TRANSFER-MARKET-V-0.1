"""Capa final de Radio Pasillo: menciona @DT y publica un Top 5 real una vez.

La publicación única usa la tabla oficial persistida; no modifica resultados,
puntos ni posiciones. Además envuelve el canal de Radio Pasillo para que los
anuncios automáticos de adelantamientos permitan mencionar únicamente roles y
antepone el rol DT al texto real de cada movimiento.
"""

from __future__ import annotations

import discord

import league_automation_patch as league
import league_result_feedback_patch as feedback
import league_top5_overtake_radio_patch as top5


_BASE_APPLY = feedback.apply_league_result_feedback_patch
_BASE_ANNOUNCEMENT_TEXT = top5._announcement_text
_BASE_RESOLVE_RADIO_CHANNEL = top5._resolve_radio_channel
_LIVE_KEY = "radio_top5_live_2026_09_04_dt_v1"


def _ensure_schema(conn) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS ajap_one_time_jobs (
            guild_id INTEGER NOT NULL,
            job_key TEXT NOT NULL,
            completed_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            discord_message_id INTEGER,
            PRIMARY KEY (guild_id, job_key)
        )
        """
    )
    conn.commit()


def _already_sent(runtime, guild_id: int) -> bool:
    conn = league.db(runtime, int(guild_id))
    try:
        _ensure_schema(conn)
        return bool(
            conn.execute(
                "SELECT 1 FROM ajap_one_time_jobs WHERE guild_id=? AND job_key=? LIMIT 1",
                (int(guild_id), _LIVE_KEY),
            ).fetchone()
        )
    finally:
        conn.close()


def _mark_sent(runtime, guild_id: int, message_id: int) -> None:
    conn = league.db(runtime, int(guild_id))
    try:
        _ensure_schema(conn)
        conn.execute(
            """
            INSERT OR IGNORE INTO ajap_one_time_jobs
                (guild_id, job_key, discord_message_id)
            VALUES (?, ?, ?)
            """,
            (int(guild_id), _LIVE_KEY, int(message_id)),
        )
        conn.commit()
    finally:
        conn.close()


def _dt_role(guild):
    if guild is None:
        return None
    roles = list(getattr(guild, "roles", []) or [])
    for role in roles:
        if str(getattr(role, "name", "")).strip().casefold() == "dt":
            return role
    return None


def _dt_mention(guild) -> str:
    role = _dt_role(guild)
    return str(getattr(role, "mention", "@DT")) if role is not None else "@DT"


def _announcement_text_with_dt(guild, moves) -> str:
    body = _BASE_ANNOUNCEMENT_TEXT(guild, moves)
    return f"{_dt_mention(guild)}\n\n{body}"


class _RoleMentionChannelProxy:
    """Conserva el canal real pero habilita solo menciones de roles."""

    def __init__(self, channel):
        self._channel = channel

    def __getattr__(self, name):
        return getattr(self._channel, name)

    async def send(self, *args, **kwargs):
        kwargs["allowed_mentions"] = discord.AllowedMentions(
            everyone=False,
            users=False,
            roles=True,
        )
        return await self._channel.send(*args, **kwargs)


async def _resolve_radio_channel_with_role_mentions(runtime, bot, guild):
    channel = await _BASE_RESOLVE_RADIO_CHANNEL(runtime, bot, guild)
    if channel is None:
        return None
    if isinstance(channel, _RoleMentionChannelProxy):
        return channel
    return _RoleMentionChannelProxy(channel)


# La función base de publicación resuelve estos nombres globales al ejecutarse,
# por lo que también cubre el wrapper con lock instalado por persistence_bridge.
top5._announcement_text = _announcement_text_with_dt
top5._resolve_radio_channel = _resolve_radio_channel_with_role_mentions


def _live_snapshot_text(guild, rows) -> str:
    lines = [
        _dt_mention(guild),
        "",
        "📻 **R A D I O - P A S I L L O**",
        "🚨 **TOP 5 ACTUALIZADO**",
        "",
    ]
    for pos, row in enumerate(list(rows)[:5], start=1):
        team = str(row["team"])
        emoji = top5._club_emoji(guild, team)
        lines.append(
            f"**{pos}.** {emoji} **{discord.utils.escape_markdown(team)}** • {int(row['pts'])} pts"
        )
    return "\n".join(lines)


async def _publish_live_snapshot(runtime, bot, guild) -> bool:
    if guild is None or _already_sent(runtime, guild.id):
        return True

    try:
        rows = top5._top5(runtime, guild.id)
    except Exception as exc:
        print(f"AJAP Top5 real: no se pudo leer tabla guild={guild.id}: {exc}")
        return False

    if not rows:
        print(f"AJAP Top5 real pendiente guild={guild.id}: tabla vacía")
        return False

    channel = await top5._resolve_radio_channel(runtime, bot, guild)
    if channel is None:
        print(f"AJAP Top5 real pendiente guild={guild.id}: Radio Pasillo no encontrado")
        return False

    try:
        render_for_guild = getattr(top5, "_render_top5_for_guild", None)
        if callable(render_for_guild):
            image = await render_for_guild(guild, rows)
        else:
            image = top5._render_top5(rows)
        file = discord.File(image, filename="ajpa-top5-radio-pasillo.png")
        sent = await channel.send(
            content=_live_snapshot_text(guild, rows),
            file=file,
            allowed_mentions=discord.AllowedMentions(
                everyone=False,
                users=False,
                roles=True,
            ),
        )
    except (discord.Forbidden, discord.HTTPException) as exc:
        print(
            f"AJAP Top5 real envío falló guild={guild.id} "
            f"canal={getattr(channel, 'id', None)}: {exc}"
        )
        return False

    _mark_sent(runtime, guild.id, sent.id)
    print(
        f"AJAP Top5 real publicado guild={guild.id} canal={channel.id} mensaje={sent.id}"
    )
    return True


def _apply_feedback_with_live_top5(runtime, bot):
    _BASE_APPLY(runtime, bot)

    if getattr(runtime, "_ajap_top5_live_dt_ready", False):
        return

    async def ready_listener():
        for guild in list(getattr(bot, "guilds", [])):
            try:
                await _publish_live_snapshot(runtime, bot, guild)
            except Exception as exc:
                print(f"AJAP Top5 real on_ready guild={guild.id}: {exc}")

    bot.add_listener(ready_listener, "on_ready")
    runtime._ajap_top5_live_dt_ready = True
    print("AJAP Top5 real armado: @DT activo y publicación única pendiente de on_ready")


feedback.apply_league_result_feedback_patch = _apply_feedback_with_live_top5

# Temporary operational freeze requested by the league admin: import this last so
# every earlier image/text result wrapper remains bypassed until the reader is fixed.
import league_result_intake_pause_patch  # noqa: F401,E402
