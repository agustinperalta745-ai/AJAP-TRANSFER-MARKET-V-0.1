"""Robust local scorer-table reading + one bounded scorer repair.

Two independent fixes live here:
1) Future PES6 scorer screens no longer depend on OCR recognizing the literal
   word "Goleador". A page with real goal-minute rows is enough to activate the
   scorer parser, and player candidates are validated against the registered
   roster before being credited.
2) One already-official Middlesbrough 1-6 Real Zaragoza result from 2026-09-03
   was loaded without scorer rows even though the supplied scorer screenshot is
   clear. If (and only if) that exact result exists with zero scorer rows, seed
   the six verified scorer entries and refresh Liga/Staff displays.

Neither path can change an official score or standings result.
"""

from __future__ import annotations

import difflib
import re

import discord

import guild_isolation_patch as guild_isolation
import league_automation_patch as league
import league_local_ocr_patch as local
import league_manual_scorer_entry_patch as scorer_entry
import pes_username_link_patch as pes_links

try:
    import league_manual_scorer_button_timeout_fix_patch as scorer_button_fix
except Exception:  # defensive during unusual import ordering
    scorer_button_fix = None


APP = None
BOT = None
_BASE_DETECT_SCORERS = local._detect_scorers


# PES can render added time as 45'+, 45+1' or OCR variants using a curly quote.
_MINUTE_RE = re.compile(
    r"(?<!\d)\d{1,3}\s*(?:['’´`]|\+\s*\d{0,2}\s*['’´`]?)(?!\d)",
    re.I,
)


def _minute_count(text: str) -> int:
    value = str(text or "")
    hits = _MINUTE_RE.findall(value)
    if hits:
        return len(hits)
    # Keep the existing conservative fallback as a second chance.
    try:
        return int(local._minutes_count(value))
    except Exception:
        return 0


def _runtime_and_guild():
    runtime = APP or getattr(pes_links, "APP", None)
    guild_id = None
    try:
        guild_id = pes_links._RESULT_GUILD_ID.get()
    except Exception:
        guild_id = None
    return runtime, guild_id


def _canonical_match_team(raw: str) -> str:
    return league.canonical_team(raw) or str(raw or "").strip()


def _resolve_roster_player(runtime, guild_id: int, team: str, raw: str):
    """Resolve scorer OCR only against the actual roster of that match side."""
    if runtime is None or guild_id is None:
        return None
    key = league.norm(raw)
    if not key:
        return None

    target_team = _canonical_match_team(team)
    names = []
    for row in league.roster(runtime, int(guild_id)):
        row_team = _canonical_match_team(row["club"])
        if league.norm(row_team) != league.norm(target_team):
            continue
        name = str(row["name"] or "").strip()
        if name:
            names.append(name)

    if not names:
        return None

    exact = {league.norm(name): name for name in names}
    if key in exact:
        return exact[key]

    # PES6 fonts/OCR commonly lose apostrophes/accents or one letter. Requiring
    # the roster side makes this looser textual cutoff safe.
    hit = difflib.get_close_matches(key, list(exact.keys()), n=1, cutoff=0.70)
    return exact[hit[0]] if hit else None


def _page_has_scorer_shape(rows) -> bool:
    if not rows:
        return False
    full = league.norm(" ".join(str(row.get("text") or "") for row in rows))
    if "goleador" in full:
        return True

    h = float(rows[0].get("h") or 1.0)
    minute_rows = 0
    for row in rows:
        yn = float(row.get("y") or 0.0) / max(1.0, h)
        if 0.12 <= yn <= 0.80 and _minute_count(row.get("text")) > 0:
            minute_rows += 1
    # A result/menu screen has lots of numbers, but not several minute-formatted
    # entries in the central table area. Two is enough for low-scoring matches.
    return minute_rows >= 2


def _detect_scorers_reliable(pages, home_team, away_team):
    runtime, guild_id = _runtime_and_guild()
    grouped = {}
    confidences = []

    for rows in pages:
        if not rows or not _page_has_scorer_shape(rows):
            continue

        h = float(rows[0].get("h") or 1.0)
        w = float(rows[0].get("w") or 1.0)

        for row in rows:
            yn = float(row.get("y") or 0.0) / max(1.0, h)
            xn = float(row.get("x") or 0.0) / max(1.0, w)
            # Wider than the old 0.30-0.73 band because the phone crop changes
            # vertical geometry depending on Discord's image viewer framing.
            if not (0.14 <= yn <= 0.80):
                continue
            if 0.485 <= xn <= 0.515:
                continue

            raw_player = local._clean_player_text(row.get("text"))
            if not raw_player:
                continue

            tm, tm_score = local._team_match(raw_player)
            if tm and tm_score >= 0.78:
                continue

            side = "home" if xn < 0.5 else "away"
            team = home_team if side == "home" else away_team
            player = _resolve_roster_player(runtime, guild_id, team, raw_player)
            if not player:
                # Never credit arbitrary OCR text as a player.
                continue

            count = _minute_count(row.get("text"))
            minute_conf = float(row.get("conf") or 0.0)
            if count == 0:
                neighbours = []
                for other in rows:
                    if other is row:
                        continue
                    oxn = float(other.get("x") or 0.0) / max(1.0, w)
                    if (oxn < 0.5) != (xn < 0.5):
                        continue
                    # Goal minutes are rendered to the right of the player name
                    # on both halves of the PES scorer table.
                    if float(other.get("x") or 0.0) + 4 < float(row.get("x") or 0.0):
                        continue
                    dy = abs(float(other.get("y") or 0.0) - float(row.get("y") or 0.0))
                    if dy > max(22.0, h * 0.055):
                        continue
                    c = _minute_count(other.get("text"))
                    if c:
                        neighbours.append((dy, -float(other.get("x") or 0.0), c, float(other.get("conf") or 0.0)))
                if neighbours:
                    neighbours.sort(key=lambda item: (item[0], item[1]))
                    count = int(neighbours[0][2])
                    minute_conf = float(neighbours[0][3])

            if count <= 0:
                continue

            count = min(20, int(count))
            key = (league.norm(player), side)
            record = {
                "player": player,
                "team": team,
                "goals": count,
                "conf": max(0.86, min(0.99, (float(row.get("conf") or 0.0) + minute_conf) / 2.0)),
            }
            prior = grouped.get(key)
            if prior is None or count > int(prior["goals"]):
                grouped[key] = record
            confidences.append(float(record["conf"]))

    scorers = [
        {"player": item["player"], "team": item["team"], "goals": int(item["goals"])}
        for item in grouped.values()
    ]
    if scorers:
        return scorers, min(confidences) if confidences else 0.86

    # Preserve old behavior as a last resort for uncommon layouts.
    return _BASE_DETECT_SCORERS(pages, home_team, away_team)


# Dynamic global lookup inside local._local_payload means replacing this function
# is enough even though runtime rescue captured analyze_local_first earlier.
local._detect_scorers = _detect_scorers_reliable


_VERIFIED_SCORERS = (
    ("Middlesbrough", "Mendieta", 1),
    ("Real Zaragoza", "Ewerthon", 1),
    ("Real Zaragoza", "D'Alessandro", 2),
    ("Real Zaragoza", "Diogo", 1),
    ("Real Zaragoza", "Aimar", 1),
    ("Real Zaragoza", "Óscar", 1),
)


def _target_matches(runtime, guild_id: int):
    conn = league.db(runtime, int(guild_id))
    try:
        return conn.execute(
            """
            SELECT *
            FROM league_matches
            WHERE created_at >= '2026-09-03 00:00:00'
              AND home_team='Middlesbrough'
              AND away_team='Real Zaragoza'
              AND home_goals=1
              AND away_goals=6
            ORDER BY id DESC
            """
        ).fetchall()
    finally:
        conn.close()


def _seed_verified_scorers(runtime, guild_id: int, match) -> bool:
    source_id = int(match["source_message_id"])
    conn = league.db(runtime, int(guild_id))
    try:
        existing = conn.execute(
            "SELECT COUNT(*) AS n FROM league_goal_events WHERE source_message_id=?",
            (source_id,),
        ).fetchone()
        if existing and int(existing["n"] or 0) > 0:
            return False
    finally:
        conn.close()

    resolved = []
    for club, raw_player, goals in _VERIFIED_SCORERS:
        player = _resolve_roster_player(runtime, int(guild_id), club, raw_player)
        # The screenshot is authoritative for the name; roster matching is used
        # for canonical spelling when available, never to invent another player.
        resolved.append((club, player or raw_player, int(goals)))

    # Structural sanity before touching DB: exactly 1 and 6 team goals.
    home_sum = sum(goals for club, _player, goals in resolved if club == "Middlesbrough")
    away_sum = sum(goals for club, _player, goals in resolved if club == "Real Zaragoza")
    if home_sum != 1 or away_sum != 6:
        return False

    conn = league.db(runtime, int(guild_id))
    try:
        conn.execute("BEGIN IMMEDIATE")
        existing = conn.execute(
            "SELECT COUNT(*) AS n FROM league_goal_events WHERE source_message_id=?",
            (source_id,),
        ).fetchone()
        if existing and int(existing["n"] or 0) > 0:
            conn.rollback()
            return False

        for club, player, goals in resolved:
            conn.execute(
                """
                INSERT INTO league_goal_events
                    (source_message_id, player, team, goals, confidence)
                VALUES (?, ?, ?, ?, 1.0)
                """,
                (source_id, player, club, int(goals)),
            )
        conn.commit()
        return True
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


async def _refresh_staff_card(runtime, bot, guild, source_id: int):
    conn = league.db(runtime, int(guild.id))
    try:
        row = conn.execute(
            """
            SELECT staff_channel_id, staff_message_id
            FROM league_manual_reviews
            WHERE source_message_id=?
              AND UPPER(COALESCE(status,''))='RESUELTO'
            LIMIT 1
            """,
            (int(source_id),),
        ).fetchone()
    except Exception:
        row = None
    finally:
        conn.close()

    if not row or not row["staff_channel_id"] or not row["staff_message_id"]:
        return
    try:
        channel = guild.get_channel(int(row["staff_channel_id"]))
        if channel is None:
            channel = await bot.fetch_channel(int(row["staff_channel_id"]))
        message = await channel.fetch_message(int(row["staff_message_id"]))
        embed = message.embeds[0].copy() if message.embeds else discord.Embed(title="✅ RESULTADO CARGADO MANUALMENTE")
        scorer_entry._set_scorers_field(
            embed,
            scorer_entry._scorers_text(runtime, guild.id, int(source_id)),
        )
        if scorer_button_fix is not None:
            view = scorer_button_fix.FastManualScorerView()
        else:
            view = scorer_entry.ManualScorerView()
        await message.edit(embed=embed, view=view)
    except Exception as exc:
        print(f"WARNING AJAP scorer repair Staff card source={source_id}: {type(exc).__name__}: {exc}")


async def _repair_on_ready():
    runtime = APP
    bot = BOT
    if runtime is None or bot is None:
        return

    for guild in list(bot.guilds):
        try:
            for match in _target_matches(runtime, guild.id):
                if not _seed_verified_scorers(runtime, guild.id, match):
                    continue
                source_id = int(match["source_message_id"])
                print(
                    "AJAP scorer repair aplicado: Middlesbrough 1-6 Real Zaragoza "
                    f"source={source_id} • Mendieta; Ewerthon; D'Alessandro x2; Diogo; Aimar; Óscar"
                )
                try:
                    await league.refresh(runtime, bot, guild.id)
                except Exception as exc:
                    print(f"WARNING AJAP scorer repair refresh guild={guild.id}: {exc}")
                await _refresh_staff_card(runtime, bot, guild, source_id)
        except Exception as exc:
            print(f"WARNING AJAP scorer repair guild={guild.id}: {type(exc).__name__}: {exc}")


def _install(runtime, bot):
    global APP, BOT
    APP, BOT = runtime, bot
    if getattr(runtime, "_ajap_scorer_screen_reliability", False):
        return
    bot.add_listener(_repair_on_ready, "on_ready")
    runtime._ajap_scorer_screen_reliability = True
    print(
        "AJAP Liga: goleadores PES robustos activos "
        "(sin depender de palabra Goleador + validación por plantel)"
    )


_ORIGINAL_APPLY = guild_isolation.apply_guild_isolation_patch


def _apply(runtime, bot):
    _ORIGINAL_APPLY(runtime, bot)
    _install(runtime, bot)


if not getattr(
    guild_isolation.apply_guild_isolation_patch,
    "_ajap_scorer_screen_reliability_wrapper",
    False,
):
    _apply._ajap_scorer_screen_reliability_wrapper = True
    guild_isolation.apply_guild_isolation_patch = _apply
