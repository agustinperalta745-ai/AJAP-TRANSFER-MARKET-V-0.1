"""Radio Pasillo announces every official AJPA season start once.

When the competition cycle enters a new `season` phase, persist a pending event.
The next league refresh publishes a normal Discord message in Radio Pasillo,
mentioning the DT role and using the correct season number (1, 2, 3, ...).
Pending events are retried on bot ready and are never duplicated after restart.
"""

from __future__ import annotations

import sqlite3

import discord

import competition_cycle as cycle
import league_automation_patch as league
import league_top5_overtake_radio_patch as radio


_BASE_RUNTIME_ADVANCE = cycle.runtime_advance
_BASE_REFRESH = league.refresh
_EVENT_TABLE = "radio_pasillo_season_start_events"


def _ensure_schema(conn) -> None:
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {_EVENT_TABLE} (
            guild_id INTEGER NOT NULL,
            season_number INTEGER NOT NULL,
            competition_id INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            channel_id INTEGER,
            discord_message_id INTEGER,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            posted_at DATETIME,
            PRIMARY KEY (guild_id, season_number, competition_id)
        )
        """
    )
    conn.commit()


def _dt_role(guild):
    for role in list(getattr(guild, "roles", []) or []):
        if str(getattr(role, "name", "")).strip().casefold() == "dt":
            return role
    return None


def _announcement_text(guild, season_number: int) -> str:
    role = _dt_role(guild)
    mention = role.mention if role is not None else "@DT"
    n = int(season_number)
    return "\n".join(
        [
            mention,
            "",
            "📻 **R A D I O - P A S I L L O**",
            f"🚨 **ARRANCA LA TEMPORADA {n}**",
            "",
            "Se terminaron las pruebas. Desde ahora, **cada punto vale de verdad**. ⚽🔥",
            "",
            f"🏆 Queda oficialmente inaugurada la **TEMPORADA {n} DE AJPA**.",
            "Los planteles están listos, los DT ya eligieron su camino y la tabla arranca desde cero.",
            "",
            "👀 Que empiecen las cuentas, las promesas, las pecheadas y las sorpresas...",
            "porque desde hoy **se juega por los puntos**.",
            "",
            "🎙️ *Radio Pasillo abre la transmisión. Que ruede la pelota.*",
        ]
    )


def _queue_if_season_started(runtime, user_id: int, expected_phase=None):
    before = None
    try:
        before = cycle.runtime_state(runtime)
    except Exception:
        pass

    payload = _BASE_RUNTIME_ADVANCE(runtime, int(user_id), expected_phase)

    try:
        old_phase = str((before or {}).get("phase") or "")
        new_phase = str(payload.get("phase") or "")
        if new_phase != cycle.SEASON or old_phase == cycle.SEASON:
            return payload

        season_number = int(payload.get("season_number") or 1)
        competition_id = payload.get("competition_id")
        if competition_id is None:
            return payload

        with runtime.db() as conn:
            _ensure_schema(conn)
            # Guild databases are isolated by runtime; guild_id is filled during refresh.
            conn.execute(
                f"""
                INSERT OR IGNORE INTO {_EVENT_TABLE}
                    (guild_id,season_number,competition_id,status)
                VALUES (0,?,?, 'pending')
                """,
                (season_number, int(competition_id)),
            )
            conn.commit()
    except Exception as exc:
        print(
            "WARNING AJAP Radio Pasillo inicio temporada: no se pudo encolar "
            f"{type(exc).__name__}: {exc}"
        )
    return payload


cycle.runtime_advance = _queue_if_season_started


def _pending_rows(runtime, guild_id: int):
    conn = league.db(runtime, int(guild_id))
    try:
        _ensure_schema(conn)
        # Events queued through runtime.db() belong to this isolated guild DB.
        conn.execute(
            f"UPDATE {_EVENT_TABLE} SET guild_id=? WHERE guild_id=0",
            (int(guild_id),),
        )
        conn.commit()
        return conn.execute(
            f"""
            SELECT guild_id,season_number,competition_id
            FROM {_EVENT_TABLE}
            WHERE guild_id=? AND status='pending'
            ORDER BY season_number,competition_id
            """,
            (int(guild_id),),
        ).fetchall()
    finally:
        conn.close()


def _mark_posted(runtime, guild_id: int, season_number: int, competition_id: int, channel_id: int, message_id: int) -> None:
    conn = league.db(runtime, int(guild_id))
    try:
        _ensure_schema(conn)
        conn.execute(
            f"""
            UPDATE {_EVENT_TABLE}
            SET status='posted',channel_id=?,discord_message_id=?,posted_at=CURRENT_TIMESTAMP
            WHERE guild_id=? AND season_number=? AND competition_id=?
            """,
            (
                int(channel_id),
                int(message_id),
                int(guild_id),
                int(season_number),
                int(competition_id),
            ),
        )
        conn.commit()
    finally:
        conn.close()


async def _publish_pending(runtime, bot, guild) -> None:
    rows = _pending_rows(runtime, guild.id)
    if not rows:
        return

    channel = await radio._resolve_radio_channel(runtime, bot, guild)
    if channel is None:
        print(f"AJAP inicio temporada pendiente guild={guild.id}: Radio Pasillo no encontrado")
        return

    for row in rows:
        season_number = int(row["season_number"])
        competition_id = int(row["competition_id"])
        try:
            sent = await channel.send(
                content=_announcement_text(guild, season_number),
                allowed_mentions=discord.AllowedMentions(
                    everyone=False,
                    users=False,
                    roles=True,
                    replied_user=False,
                ),
            )
        except (discord.Forbidden, discord.HTTPException) as exc:
            print(
                f"AJAP inicio temporada envío falló guild={guild.id} "
                f"temporada={season_number}: {exc}"
            )
            continue

        _mark_posted(
            runtime,
            guild.id,
            season_number,
            competition_id,
            channel.id,
            sent.id,
        )
        print(
            f"AJAP Radio Pasillo: Temporada {season_number} anunciada "
            f"guild={guild.id} channel={channel.id} message={sent.id}"
        )


async def _refresh_with_season_start(runtime, bot, guild_id: int):
    result = await _BASE_REFRESH(runtime, bot, int(guild_id))
    guild = bot.get_guild(int(guild_id)) if bot is not None else None
    if guild is not None:
        try:
            await _publish_pending(runtime, bot, guild)
        except Exception as exc:
            print(
                f"AJAP inicio temporada post-refresh falló guild={guild_id}: "
                f"{type(exc).__name__}: {exc}"
            )
    return result


league.refresh = _refresh_with_season_start


_BASE_APPLY = league.apply_league_automation_patch


def _apply_with_season_start(runtime, bot):
    _BASE_APPLY(runtime, bot)
    if getattr(runtime, "_ajap_radio_season_start_ready", False):
        return

    async def ready_listener():
        for guild in list(getattr(bot, "guilds", [])):
            try:
                await _publish_pending(runtime, bot, guild)
            except Exception as exc:
                print(
                    f"AJAP inicio temporada on_ready guild={guild.id}: "
                    f"{type(exc).__name__}: {exc}"
                )

    bot.add_listener(ready_listener, "on_ready")
    runtime._ajap_radio_season_start_ready = True
    print("AJAP Radio Pasillo: anuncios automáticos de inicio de Temporada activos")


league.apply_league_automation_patch = _apply_with_season_start
