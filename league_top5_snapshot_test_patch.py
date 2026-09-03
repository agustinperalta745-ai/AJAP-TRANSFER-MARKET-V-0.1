"""Publica una sola foto de prueba del Top 5 actual en Radio Pasillo.

No cambia resultados, puntos, posiciones ni eventos de adelantamiento. Solo reutiliza
el renderizador y el resolvedor de canal del sistema Top 5 para comprobar de punta
a punta que Railway puede generar la imagen y enviarla al canal correcto.
"""

from __future__ import annotations

import discord

import league_automation_patch as league
import league_result_feedback_patch as feedback
import league_top5_overtake_radio_patch as top5


_BASE_APPLY = feedback.apply_league_result_feedback_patch
_TEST_KEY = "radio_top5_snapshot_2026_09_03_v1"


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
                (int(guild_id), _TEST_KEY),
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
            (int(guild_id), _TEST_KEY, int(message_id)),
        )
        conn.commit()
    finally:
        conn.close()


def _snapshot_text(guild, rows) -> str:
    lines = [
        "🧪 **PRUEBA RADIO PASILLO • TOP 5 ACTUAL**",
        "",
        "Esta publicación es solo para comprobar la foto y el envío automático.",
        "",
    ]
    for pos, row in enumerate(list(rows)[:5], start=1):
        team = str(row["team"])
        emoji = top5._club_emoji(guild, team)
        lines.append(f"**{pos}.** {emoji} **{discord.utils.escape_markdown(team)}** • {int(row['pts'])} pts")
    return "\n".join(lines)


async def _publish_snapshot(runtime, bot, guild) -> bool:
    if guild is None or _already_sent(runtime, guild.id):
        return True

    try:
        rows = top5._top5(runtime, guild.id)
    except Exception as exc:
        print(f"AJAP Top5 prueba: no se pudo leer tabla guild={guild.id}: {exc}")
        return False

    if not rows:
        print(f"AJAP Top5 prueba pendiente guild={guild.id}: tabla vacía")
        return False

    channel = await top5._resolve_radio_channel(runtime, bot, guild)
    if channel is None:
        print(f"AJAP Top5 prueba pendiente guild={guild.id}: Radio Pasillo no encontrado")
        return False

    try:
        image = top5._render_top5(rows)
        file = discord.File(image, filename="ajpa-top5-prueba-actual.png")
        sent = await channel.send(
            content=_snapshot_text(guild, rows),
            file=file,
            allowed_mentions=discord.AllowedMentions.none(),
        )
    except (discord.Forbidden, discord.HTTPException) as exc:
        print(
            f"AJAP Top5 prueba envío falló guild={guild.id} "
            f"canal={getattr(channel, 'id', None)}: {exc}"
        )
        return False

    _mark_sent(runtime, guild.id, sent.id)
    print(
        f"AJAP Top5 prueba publicada guild={guild.id} canal={channel.id} mensaje={sent.id}"
    )
    return True


def _apply_feedback_with_snapshot_test(runtime, bot):
    _BASE_APPLY(runtime, bot)

    if getattr(runtime, "_ajap_top5_snapshot_test_ready", False):
        return

    async def ready_listener():
        for guild in list(getattr(bot, "guilds", [])):
            try:
                await _publish_snapshot(runtime, bot, guild)
            except Exception as exc:
                print(f"AJAP Top5 prueba on_ready guild={guild.id}: {exc}")

    bot.add_listener(ready_listener, "on_ready")
    runtime._ajap_top5_snapshot_test_ready = True
    print("AJAP Top5 prueba única armada: publicará la tabla actual en Radio Pasillo")


feedback.apply_league_result_feedback_patch = _apply_feedback_with_snapshot_test
