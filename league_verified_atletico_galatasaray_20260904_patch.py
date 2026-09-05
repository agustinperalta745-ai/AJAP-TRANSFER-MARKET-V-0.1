"""Verified AJPA recovery for Atlético de Madrid vs Galatasaray on 2026-09-04.

Also keeps the original scorer screenshot visible on Staff pending-scorer cards.
The data repair is deliberately bounded to the live guild evidence from the
reported OCR.Space review and is idempotent.
"""
from __future__ import annotations

import sqlite3

import discord

import guild_isolation_patch as guild_isolation
import league_automation_patch as league
import league_scorer_pending_patch as pending


REPORTER_ID = 1526669873487548528
FIX_KEY = "verified_atletico_galatasaray_two_6_1_20260904_v1"
MATCH_DATE = "2026-09-04"
SYNTHETIC_A = -20260904006101
SYNTHETIC_B = -20260904006102

_ORIGINAL_PENDING_ENSURE = pending._ensure_card
_ORIGINAL_PENDING_REFRESH = pending._refresh_card


def _preferred_scorer_image(message):
    images = []
    for attachment in list(getattr(message, "attachments", None) or []):
        mime = str(getattr(attachment, "content_type", "") or "").casefold()
        filename = str(getattr(attachment, "filename", "") or "").casefold()
        if mime.startswith("image/") or filename.endswith(
            (".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp")
        ):
            images.append(attachment)
    if len(images) >= 2:
        return images[1]
    return images[0] if images else None


async def _pending_card_with_image(runtime, bot, message):
    await _ORIGINAL_PENDING_ENSURE(runtime, bot, message)

    attachment = _preferred_scorer_image(message)
    if attachment is None or not getattr(message, "guild", None):
        return

    conn = league.db(runtime, int(message.guild.id))
    try:
        try:
            review = conn.execute(
                """
                SELECT staff_channel_id, staff_message_id
                FROM league_manual_reviews
                WHERE source_message_id=?
                LIMIT 1
                """,
                (int(message.id),),
            ).fetchone()
        except sqlite3.OperationalError:
            review = None
    finally:
        conn.close()

    if not review or not review["staff_channel_id"] or not review["staff_message_id"]:
        return

    try:
        channel = (
            message.guild.get_channel(int(review["staff_channel_id"]))
            or await message.guild.fetch_channel(int(review["staff_channel_id"]))
        )
        staff_message = await channel.fetch_message(int(review["staff_message_id"]))
        if not staff_message.embeds:
            return
        embed = staff_message.embeds[0]
        embed.set_image(url=attachment.url)
        await staff_message.edit(embed=embed)
    except Exception as exc:
        print(
            "AJAP scorer evidence: no se pudo adjuntar foto a Staff "
            f"message={getattr(message, 'id', '?')}: {type(exc).__name__}: {exc}"
        )


async def _pending_refresh_keep_image(interaction, review):
    image_url = None
    try:
        if interaction.message and interaction.message.embeds:
            image_url = interaction.message.embeds[0].image.url
    except Exception:
        image_url = None

    await _ORIGINAL_PENDING_REFRESH(interaction, review)

    if not image_url or interaction.message is None:
        return
    try:
        channel = interaction.channel
        current = await channel.fetch_message(int(interaction.message.id))
        if not current.embeds:
            return
        embed = current.embeds[0]
        embed.set_image(url=image_url)
        await current.edit(embed=embed)
    except Exception as exc:
        print(
            "AJAP scorer evidence: no se pudo conservar foto tras editar goleadores: "
            f"{type(exc).__name__}: {exc}"
        )


def _install_pending_image_fix():
    if getattr(pending._ensure_card, "_ajap_scorer_image_fix", False):
        return
    _pending_card_with_image._ajap_scorer_image_fix = True
    _pending_refresh_keep_image._ajap_scorer_image_fix = True
    pending._ensure_card = _pending_card_with_image
    pending._refresh_card = _pending_refresh_keep_image
    print("AJAP Liga: tarjeta de goleadores pendientes conserva la foto de goleadores")


def _canonical(value):
    return league.canonical_team(value) or str(value or "").strip()


def _ensure_fix_table(conn):
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS ajap_runtime_fixes (
            fix_key TEXT PRIMARY KEY,
            applied_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """
    )


def _candidate_review(conn, atl, gala):
    try:
        rows = conn.execute(
            """
            SELECT *
            FROM league_manual_reviews
            WHERE source_author_id=?
              AND reason LIKE '%OCR.Space%'
            ORDER BY datetime(created_at) DESC, source_message_id DESC
            LIMIT 20
            """,
            (REPORTER_ID,),
        ).fetchall()
    except sqlite3.OperationalError:
        return None

    for row in rows:
        home = _canonical(row["home_team"]) if row["home_team"] else None
        away = _canonical(row["away_team"]) if row["away_team"] else None
        if home and away and {home, away} != {atl, gala}:
            continue
        return row
    return None


def _live_marker(conn, atl):
    """Fallback target guard: this is the live guild that already has today's ATL 2-4 Fulham."""
    try:
        row = conn.execute(
            """
            SELECT 1
            FROM league_matches
            WHERE home_team=? COLLATE NOCASE
              AND away_team='Fulham' COLLATE NOCASE
              AND home_goals=2 AND away_goals=4
              AND substr(COALESCE(created_at,''),1,10)=?
            LIMIT 1
            """,
            (atl, MATCH_DATE),
        ).fetchone()
        return bool(row)
    except sqlite3.OperationalError:
        return False


def _exact_match(conn, home, away, hg, ag):
    return conn.execute(
        """
        SELECT *
        FROM league_matches
        WHERE home_team=? COLLATE NOCASE
          AND away_team=? COLLATE NOCASE
          AND home_goals=? AND away_goals=?
          AND substr(COALESCE(created_at,''),1,10)=?
        ORDER BY id DESC
        LIMIT 1
        """,
        (home, away, int(hg), int(ag), MATCH_DATE),
    ).fetchone()


def _source_in_use(conn, source_id):
    return bool(
        conn.execute(
            "SELECT 1 FROM league_matches WHERE source_message_id=? LIMIT 1",
            (int(source_id),),
        ).fetchone()
    )


def _insert_match(conn, source_id, source_channel_id, author_id, home, away, hg, ag):
    conn.execute(
        """
        INSERT INTO league_matches
            (source_message_id, source_channel_id, author_id,
             home_team, away_team, home_goals, away_goals, confidence)
        VALUES (?, ?, ?, ?, ?, ?, ?, 1.0)
        """,
        (
            int(source_id),
            int(source_channel_id or 0),
            int(author_id or REPORTER_ID),
            home,
            away,
            int(hg),
            int(ag),
        ),
    )
    return conn.execute(
        "SELECT * FROM league_matches WHERE source_message_id=? LIMIT 1",
        (int(source_id),),
    ).fetchone()


def _scorer_totals(conn, source_id):
    rows = conn.execute(
        """
        SELECT team, SUM(goals) AS goals
        FROM league_goal_events
        WHERE source_message_id=?
        GROUP BY team COLLATE NOCASE
        """,
        (int(source_id),),
    ).fetchall()
    return {str(row["team"]): int(row["goals"] or 0) for row in rows}


def _write_verified_scorers(conn, match, scorers):
    source_id = int(match["source_message_id"])
    home = str(match["home_team"])
    away = str(match["away_team"])
    totals = _scorer_totals(conn, source_id)

    # Never downgrade a scorer attribution that is already complete.
    if (
        int(totals.get(home, 0)) == int(match["home_goals"])
        and int(totals.get(away, 0)) == int(match["away_goals"])
    ):
        return False

    conn.execute(
        "DELETE FROM league_goal_events WHERE source_message_id=?",
        (source_id,),
    )
    for player, team, goals in scorers:
        conn.execute(
            """
            INSERT INTO league_goal_events
                (source_message_id, player, team, goals, confidence)
            VALUES (?, ?, ?, ?, 1.0)
            """,
            (source_id, player, team, int(goals)),
        )
    return True


def _resolve_review(conn, review, match):
    if review is None or int(review["source_message_id"]) != int(match["source_message_id"]):
        return
    conn.execute(
        """
        UPDATE league_manual_reviews
        SET status='RESUELTO',
            resolved_at=COALESCE(resolved_at, CURRENT_TIMESTAMP),
            home_team=?, away_team=?, home_goals=?, away_goals=?
        WHERE source_message_id=?
        """,
        (
            str(match["home_team"]),
            str(match["away_team"]),
            int(match["home_goals"]),
            int(match["away_goals"]),
            int(match["source_message_id"]),
        ),
    )


def _load_two_matches(runtime, guild_id):
    atl = _canonical("Atletico de Madrid")
    gala = _canonical("Galatasaray")

    conn = league.db(runtime, int(guild_id))
    review = None
    result = None
    try:
        _ensure_fix_table(conn)
        conn.commit()

        if conn.execute(
            "SELECT 1 FROM ajap_runtime_fixes WHERE fix_key=? LIMIT 1",
            (FIX_KEY,),
        ).fetchone():
            return None

        review = _candidate_review(conn, atl, gala)
        if review is None and not _live_marker(conn, atl):
            return None

        conn.execute("BEGIN IMMEDIATE")

        source_channel = int(review["source_channel_id"]) if review else 0
        author_id = int(review["source_author_id"] or REPORTER_ID) if review else REPORTER_ID

        # Match A: Atlético 6-1 Galatasaray. The Staff card shown by the user is
        # this orientation, so reuse its real Discord source when still available.
        match_a = _exact_match(conn, atl, gala, 6, 1)
        if match_a is None:
            source_a = (
                int(review["source_message_id"])
                if review is not None and not _source_in_use(conn, int(review["source_message_id"]))
                else SYNTHETIC_A
            )
            channel_a = source_channel if source_a > 0 else 0
            match_a = _insert_match(
                conn, source_a, channel_a, author_id, atl, gala, 6, 1
            )

        _write_verified_scorers(
            conn,
            match_a,
            [
                ("Fernando Torres", atl, 3),
                ("Kezman", atl, 2),
                ("Galleti", atl, 1),
                ("Necati Ates", gala, 1),
            ],
        )
        _resolve_review(conn, review, match_a)

        # Match B: Galatasaray 1-6 Atlético. The provided scorer screen proves
        # only 5 of Atlético's 6 goals, so the sixth intentionally stays pending.
        match_b = _exact_match(conn, gala, atl, 1, 6)
        if match_b is None:
            match_b = _insert_match(
                conn, SYNTHETIC_B, 0, author_id, gala, atl, 1, 6
            )

        _write_verified_scorers(
            conn,
            match_b,
            [
                ("Necati Ates", gala, 1),
                ("Fernando Torres", atl, 4),
                ("Galleti", atl, 1),
            ],
        )

        league.standings(conn)
        conn.execute(
            "INSERT OR REPLACE INTO ajap_runtime_fixes (fix_key, applied_at) VALUES (?, CURRENT_TIMESTAMP)",
            (FIX_KEY,),
        )
        conn.commit()
        result = (review, match_a, match_b)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    return result


async def _refresh_resolved_review(guild, review, match_a):
    if review is None:
        return
    staff_channel_id = review["staff_channel_id"]
    staff_message_id = review["staff_message_id"]

    source_message = None
    try:
        source_channel = (
            guild.get_channel(int(review["source_channel_id"]))
            or await guild.fetch_channel(int(review["source_channel_id"]))
        )
        source_message = await source_channel.fetch_message(int(review["source_message_id"]))
    except Exception:
        source_message = None

    if staff_channel_id and staff_message_id:
        try:
            channel = (
                guild.get_channel(int(staff_channel_id))
                or await guild.fetch_channel(int(staff_channel_id))
            )
            staff_message = await channel.fetch_message(int(staff_message_id))
            embed = discord.Embed(
                title="✅ RESULTADO CARGADO MANUALMENTE",
                description="**Atlético de Madrid 6–1 Galatasaray**",
                color=discord.Color.green(),
            )
            embed.add_field(
                name="Goleadores",
                value=(
                    "⚽ Fernando Torres x3\n"
                    "⚽ Kezman x2\n"
                    "⚽ Galleti x1\n"
                    "⚽ Necati Ates x1"
                ),
                inline=False,
            )
            if source_message is not None:
                scorer_image = _preferred_scorer_image(source_message)
                if scorer_image is not None:
                    embed.set_image(url=scorer_image.url)
            await staff_message.edit(embed=embed, view=None)
        except Exception as exc:
            print(
                "AJAP Atlético/Galatasaray: no se pudo actualizar tarjeta Staff: "
                f"{type(exc).__name__}: {exc}"
            )

    if source_message is not None:
        try:
            await source_message.add_reaction("✅")
            await source_message.reply(
                "✅ Cargado manualmente: **Atlético de Madrid 6–1 Galatasaray**.\n"
                "⚽ Fernando Torres x3 • Kezman x2 • Galleti x1 • Necati Ates x1",
                mention_author=False,
            )
        except Exception:
            pass


async def _apply_verified_matches(runtime, bot, guild):
    result = _load_two_matches(runtime, int(guild.id))
    if result is None:
        return False

    review, match_a, match_b = result
    try:
        await league.refresh(runtime, bot, int(guild.id))
    except Exception as exc:
        print(
            "AJAP Atlético/Galatasaray: refresh falló: "
            f"{type(exc).__name__}: {exc}"
        )

    await _refresh_resolved_review(guild, review, match_a)
    print(
        "AJAP Liga: carga verificada Atlético/Galatasaray aplicada | "
        f"guild={guild.id} | Atlético 6-1 Galatasaray + Galatasaray 1-6 Atlético | "
        "segundo partido conserva 1 gol de Atlético pendiente"
    )
    return True


_install_pending_image_fix()

_PREVIOUS_APPLY = guild_isolation.apply_guild_isolation_patch


def _apply(runtime, bot):
    _PREVIOUS_APPLY(runtime, bot)
    if getattr(bot, "_ajap_atletico_galatasaray_verified_listener", False):
        return

    async def on_ready():
        for guild in list(bot.guilds):
            try:
                await _apply_verified_matches(runtime, bot, guild)
            except Exception as exc:
                print(
                    "AJAP Atlético/Galatasaray recovery falló "
                    f"guild={getattr(guild, 'id', '?')}: {type(exc).__name__}: {exc}"
                )

    bot.add_listener(on_ready, "on_ready")
    bot._ajap_atletico_galatasaray_verified_listener = True


if not getattr(
    guild_isolation.apply_guild_isolation_patch,
    "_ajap_atletico_galatasaray_verified_wrapper",
    False,
):
    _apply._ajap_atletico_galatasaray_verified_wrapper = True
    guild_isolation.apply_guild_isolation_patch = _apply
