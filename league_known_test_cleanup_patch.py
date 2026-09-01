"""Limpieza acotada de los 3 puntos de prueba conocidos de Real Betis.

Solo actúa automáticamente cuando la base no deja lugar a ambigüedad:
- existe exactamente UN partido de Betis,
- ese partido le da 3 puntos (victoria), y
- fue creado antes de este arreglo (2026-09-02 UTC).

Si hay más de un partido de Betis, no borra nada y Staff puede usar
`/eliminar_resultado_liga equipo:Betis` para elegir el correcto.
"""

from __future__ import annotations

import guild_isolation_patch as guild_isolation
import league_automation_patch as league
import league_result_admin_cleanup_patch as cleanup


APP = None
BOT = None
_CUTOFF = "2026-09-02 00:00:00"


def _betis_points(row):
    home = str(row["home_team"])
    away = str(row["away_team"])
    hg = int(row["home_goals"])
    ag = int(row["away_goals"])
    if home == "Real Betis":
        return 3 if hg > ag else (1 if hg == ag else 0)
    if away == "Real Betis":
        return 3 if ag > hg else (1 if hg == ag else 0)
    return 0


def _single_unambiguous_test(runtime, guild_id: int):
    conn = league.db(runtime, int(guild_id))
    try:
        rows = conn.execute(
            """
            SELECT * FROM league_matches
            WHERE home_team='Real Betis' OR away_team='Real Betis'
            ORDER BY created_at ASC, id ASC
            """
        ).fetchall()
    finally:
        conn.close()

    if len(rows) != 1:
        return None
    row = rows[0]
    if _betis_points(row) != 3:
        return None
    created = str(row["created_at"] or "")
    if not created or created >= _CUTOFF:
        return None
    return row


async def _cleanup_known_test_on_ready():
    if APP is None or BOT is None:
        return
    for guild in list(BOT.guilds):
        try:
            candidate = _single_unambiguous_test(APP, guild.id)
            if not candidate:
                continue
            removed = cleanup._delete_match(
                APP,
                guild.id,
                int(candidate["source_message_id"]),
            )
            if not removed:
                continue
            await league.refresh(APP, BOT, guild.id)
            await cleanup._remove_success_reaction(guild, removed)
            print(
                "AJAP Liga limpieza prueba Betis guild="
                f"{guild.id}: {_score_for_log(removed)} eliminado"
            )
        except Exception as exc:
            print(f"AJAP Liga limpieza prueba Betis guild={guild.id} error: {exc}")


def _score_for_log(row):
    return (
        f"{row['home_team']} {int(row['home_goals'])}-"
        f"{int(row['away_goals'])} {row['away_team']}"
    )


def _install(runtime, bot):
    global APP, BOT
    APP, BOT = runtime, bot
    if getattr(runtime, "_ajap_known_betis_test_cleanup", False):
        return

    if not getattr(bot, "_ajap_known_betis_test_listener", False):
        bot.add_listener(_cleanup_known_test_on_ready, "on_ready")
        bot._ajap_known_betis_test_listener = True

    runtime._ajap_known_betis_test_cleanup = True
    print("AJAP Liga: limpieza acotada de puntos de prueba Betis activa")


_original_apply_guild_isolation_patch = guild_isolation.apply_guild_isolation_patch


def _apply_guild_isolation_then_known_cleanup(runtime, bot):
    _original_apply_guild_isolation_patch(runtime, bot)
    _install(runtime, bot)


if not getattr(guild_isolation.apply_guild_isolation_patch, "_ajap_known_betis_test_wrapped", False):
    _apply_guild_isolation_then_known_cleanup._ajap_known_betis_test_wrapped = True
    guild_isolation.apply_guild_isolation_patch = _apply_guild_isolation_then_known_cleanup
