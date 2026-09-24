"""One-shot Radio Pasillo announcement for AJPA Season 1 Best XI.

Publishes the approved 4-3-3 once per guild, using AJPA club badge emojis,
the manager recorded at the official Season 1 close, and the @DT role.
The delivery marker is persisted in SQLite so Railway restarts cannot duplicate it.
"""

from __future__ import annotations

import asyncio
import os

import discord

import competition_cycle as cycle
import league_automation_patch as league
import league_top5_overtake_radio_patch as radio


_JOB_KEY = "radio_season1_xi_ideal_20260924_v1"
_JOB_TABLE = "ajap_one_time_jobs"

_XI = (
    ("ARQ", "Coupet", "Olympique de Lyon"),
    ("LD", "Beye", "Olympique de Marsella"),
    ("DFC", "G. Milito", "Real Zaragoza"),
    ("DFC", "Cufre", "AS Monaco"),
    ("LI", "Givet", "AS Monaco"),
    ("MC", "Maduro", "Ajax"),
    ("MC", "Ribery", "Olympique de Marsella"),
    ("MCO", "Juan Román Riquelme", "Villarreal"),
    ("ED", "Ángel", "Aston Villa"),
    ("DC", "Djibril Cisse", "Olympique de Marsella"),
    ("EI", "Boa Morte", "Fulham"),
)

_TEAM_ALIASES = {
    "Olympique de Lyon": ("Olympique de Lyon", "Lyon"),
    "Olympique de Marsella": (
        "Olympique de Marsella",
        "Olympique Marseille",
        "Olympique de Marseille",
        "Marsella",
    ),
    "Real Zaragoza": ("Real Zaragoza", "Zaragoza"),
    "AS Monaco": ("AS Monaco", "Monaco"),
    "Ajax": ("Ajax",),
    "Villarreal": ("Villarreal", "Villareal"),
    "Aston Villa": ("Aston Villa",),
    "Fulham": ("Fulham",),
}


def _ensure_schema(conn) -> None:
    cycle.ensure_schema(conn)
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {_JOB_TABLE} (
            guild_id INTEGER NOT NULL,
            job_key TEXT NOT NULL,
            completed_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            discord_message_id INTEGER,
            PRIMARY KEY (guild_id, job_key)
        )
        """
    )
    conn.commit()


def _job_row(runtime, guild_id: int):
    conn = league.db(runtime, int(guild_id))
    try:
        _ensure_schema(conn)
        return conn.execute(
            f"""SELECT completed_at,discord_message_id
                FROM {_JOB_TABLE}
                WHERE guild_id=? AND job_key=? LIMIT 1""",
            (int(guild_id), _JOB_KEY),
        ).fetchone()
    finally:
        conn.close()


def _mark_done(runtime, guild_id: int, message_id: int) -> None:
    conn = league.db(runtime, int(guild_id))
    try:
        _ensure_schema(conn)
        conn.execute(
            f"""
            INSERT OR REPLACE INTO {_JOB_TABLE}
                (guild_id,job_key,completed_at,discord_message_id)
            VALUES (?,?,CURRENT_TIMESTAMP,?)
            """,
            (int(guild_id), _JOB_KEY, int(message_id)),
        )
        conn.commit()
    finally:
        conn.close()


def _season_one_closed_at(conn) -> str | None:
    cycle.ensure_schema(conn)
    row = conn.execute(
        """
        SELECT ended_at
        FROM competition_editions
        WHERE kind='season' AND season_number=1
          AND status='finished' AND ended_at IS NOT NULL
        ORDER BY ended_at DESC, id DESC
        LIMIT 1
        """
    ).fetchone()
    if not row:
        return None
    value = str(row["ended_at"] or "").strip()
    return value or None


def _manager_snapshot(conn, team: str, closed_at: str | None) -> tuple[int | None, str]:
    """Resolve the historical Discord user id locally; mentions do not need a REST name lookup."""
    if not closed_at:
        return None, "DT no registrado"

    table = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='club_assignment_history' LIMIT 1"
    ).fetchone()
    if not table:
        return None, "DT no registrado"

    active_actions = {"ASIGNADO", "ASIGNADO_VACANTE_ADMIN"}
    aliases = _TEAM_ALIASES.get(team, (team,))
    for alias in aliases:
        row = conn.execute(
            """
            SELECT user_id, action
            FROM club_assignment_history
            WHERE club=? COLLATE NOCASE AND created_at<=?
            ORDER BY created_at DESC, id DESC
            LIMIT 1
            """,
            (str(alias).strip(), str(closed_at)),
        ).fetchone()
        if row and str(row["action"] or "").strip().upper() in active_actions:
            raw_user_id = row["user_id"]
            if str(raw_user_id or "").isdigit():
                return int(raw_user_id), "DT histórico"

    return None, "DT no registrado"


def _dt_role_mention(guild) -> str:
    for role in list(getattr(guild, "roles", []) or []):
        if str(getattr(role, "name", "")).strip().casefold() == "dt":
            return str(getattr(role, "mention", "@DT"))
    return "@DT"


def _manager_label(user_id: int | None, manager_name: str) -> str:
    if user_id is not None:
        return f"<@{int(user_id)}>"
    safe = discord.utils.escape_markdown(
        str(manager_name or "DT no registrado").strip() or "DT no registrado"
    )
    return safe


def _safe_player(name: str) -> str:
    return discord.utils.escape_markdown(str(name or "").strip())


def _safe_team(name: str) -> str:
    return discord.utils.escape_markdown(str(name or "").strip())


def _line(guild, position: str, player: str, team: str, manager) -> str:
    user_id, manager_name = manager
    badge = radio._club_emoji(guild, team)
    return (
        f"{badge} **{position} • {_safe_player(player)}** — "
        f"{_safe_team(team)} — DT: {_manager_label(user_id, manager_name)}"
    )


def _message(guild, managers: dict[str, tuple[int | None, str]]) -> str:
    by_position = {position: [] for position in ("ARQ", "DEF", "MED", "ATA")}
    for position, player, team in _XI:
        if position == "ARQ":
            group = "ARQ"
        elif position in {"LD", "DFC", "LI"}:
            group = "DEF"
        elif position in {"MC", "MCO"}:
            group = "MED"
        else:
            group = "ATA"
        by_position[group].append(
            _line(guild, position, player, team, managers.get(team, (None, "DT no registrado")))
        )

    lines = [
        _dt_role_mention(guild),
        "",
        "📻 **R A D I O - P A S I L L O**",
        "🌟 **XI IDEAL DE LA TEMPORADA 1**",
        "",
        "La Temporada 1 dejó su equipo ideal. Estos son los once elegidos:",
        "",
        "🧤 **ARQUERO**",
        *by_position["ARQ"],
        "",
        "🛡️ **DEFENSA**",
        *by_position["DEF"],
        "",
        "🎩 **MEDIOCAMPO**",
        *by_position["MED"],
        "",
        "⚡ **ATAQUE**",
        *by_position["ATA"],
        "",
        "🏅 **Felicitaciones a los jugadores y a los DTs que los llevaron al XI Ideal de AJPA.**",
    ]
    return "\n".join(lines)


async def _publish(runtime, bot, guild) -> bool:
    existing = _job_row(runtime, guild.id)
    if existing:
        print(
            f"AJPA XI Ideal T1 ya publicado guild={guild.id} "
            f"mensaje={existing['discord_message_id']} completed_at={existing['completed_at']}"
        )
        return True

    print(f"AJPA XI Ideal T1 procesando guild={guild.id}")
    channel = await radio._resolve_radio_channel(runtime, bot, guild)
    if channel is None:
        print(
            f"AJPA XI Ideal T1 pendiente guild={guild.id}: Radio Pasillo no encontrado"
        )
        return False

    conn = league.db(runtime, int(guild.id))
    try:
        _ensure_schema(conn)
        closed_at = _season_one_closed_at(conn)
        if not closed_at:
            print(
                f"AJPA XI Ideal T1 pendiente guild={guild.id}: "
                "Temporada 1 todavía no figura cerrada"
            )
            return False

        managers = {}
        for _, _, team in _XI:
            if team not in managers:
                managers[team] = _manager_snapshot(conn, team, closed_at)
    finally:
        conn.close()

    try:
        sent = await channel.send(
            content=_message(guild, managers),
            allowed_mentions=discord.AllowedMentions(
                everyone=False,
                users=True,
                roles=True,
            ),
        )
    except (discord.Forbidden, discord.HTTPException) as exc:
        print(
            f"AJPA XI Ideal T1 envío falló guild={guild.id} "
            f"canal={getattr(channel, 'id', None)}: {exc}"
        )
        return False

    _mark_done(runtime, guild.id, sent.id)
    print(
        f"AJPA XI Ideal T1 publicado guild={guild.id} "
        f"canal={channel.id} mensaje={sent.id}"
    )
    return True


def apply_radio_pasillo_season1_xi_patch(runtime, bot) -> None:
    if getattr(bot, "_ajpa_radio_season1_xi_patch", False):
        return

    async def on_ready():
        # This announcement belongs only to the production AJPA guild. The old
        # test guild intentionally has no Radio Pasillo and must never consume work.
        await asyncio.sleep(1.0)
        configured = str(os.getenv("AJPA_MOBILE_GUILD_ID") or "").strip()
        guilds = list(getattr(bot, "guilds", []) or [])
        if configured.isdigit():
            target = bot.get_guild(int(configured))
            guilds = [target] if target is not None else []

        if not guilds:
            print(
                f"AJPA XI Ideal T1 pendiente: guild producción {configured or '?'} no disponible"
            )
            return

        # A busy Discord startup may temporarily rate-limit unrelated routes.
        # Retry only until the persisted one-shot marker proves delivery.
        for attempt in range(1, 7):
            all_done = True
            for guild in guilds:
                try:
                    ok = await _publish(runtime, bot, guild)
                    all_done = all_done and bool(ok)
                except Exception as exc:
                    all_done = False
                    print(
                        f"AJPA XI Ideal T1 falló guild={getattr(guild, 'id', '?')} "
                        f"intento={attempt}: {type(exc).__name__}: {exc}"
                    )
            if all_done:
                return
            await asyncio.sleep(10.0)

    bot.add_listener(on_ready, "on_ready")
    bot._ajpa_radio_season1_xi_patch = True
    print("AJPA Radio Pasillo: XI Ideal de Temporada 1 listo para publicación única")
