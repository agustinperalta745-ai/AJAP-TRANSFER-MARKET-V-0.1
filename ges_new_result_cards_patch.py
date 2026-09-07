"""Publish only newly discovered GES results using AJPA's existing result card.

The authoritative GES snapshot owns standings/results. This layer does not keep
competitive data or recalculate anything: it only remembers which visual result
cards were already published so a repeated "GES actualizada" never spams the
results channel.

On first activation, every result that is already present in the current live
snapshot is marked as baseline (already seen). From then on, fixtures that appear
for the first time after a GES sync are queued and published with the same
RESULTADO FINAL image that AJPA already uses.
"""

from __future__ import annotations

import discord

import competition_cycle as cycle
import league_ges_manual_sync_patch as ges
import league_ges_result_queue_patch as cards


def _table(conn, name: str) -> bool:
    return bool(
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
            (name,),
        ).fetchone()
    )


def _cols(conn, table: str) -> set[str]:
    if not _table(conn, table):
        return set()
    return {
        str(row["name"])
        for row in conn.execute(f'PRAGMA table_info("{table}")').fetchall()
    }


def _competition_key(competition_id: int | None) -> int:
    return int(competition_id) if competition_id is not None else 0


def _fixture_key(home: str, away: str) -> str:
    return f"{ges._norm(home)}|{ges._norm(away)}"


def _ensure_schema(conn) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS league_ges_result_publications (
            guild_id INTEGER NOT NULL,
            league_id TEXT NOT NULL,
            competition_id INTEGER NOT NULL DEFAULT 0,
            fixture_key TEXT NOT NULL,
            home_team TEXT NOT NULL,
            away_team TEXT NOT NULL,
            home_goals INTEGER NOT NULL,
            away_goals INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            discord_channel_id INTEGER,
            discord_message_id INTEGER,
            first_seen_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            published_at DATETIME,
            last_error TEXT,
            PRIMARY KEY (guild_id, league_id, competition_id, fixture_key)
        );
        CREATE INDEX IF NOT EXISTS idx_ges_result_publications_pending
        ON league_ges_result_publications(guild_id, league_id, competition_id, status);
        """
    )


def _active_competition(conn) -> int | None:
    try:
        cycle.ensure_schema(conn)
        conn.commit()
        return cycle.active_competition_id(conn)
    except Exception:
        return None


def _current_rows(conn, competition_id: int | None):
    if not _table(conn, "league_matches"):
        return []
    cols = _cols(conn, "league_matches")
    if competition_id is not None and "competition_id" in cols:
        return conn.execute(
            """SELECT home_team,away_team,home_goals,away_goals
               FROM league_matches WHERE competition_id=?""",
            (int(competition_id),),
        ).fetchall()
    return conn.execute(
        "SELECT home_team,away_team,home_goals,away_goals FROM league_matches"
    ).fetchall()


def _seed_existing_as_baseline(runtime, guild_id: int) -> int | None:
    """Prevent the feature's first deploy from reposting every old result."""
    conn = ges.league.db(runtime, int(guild_id))
    try:
        _ensure_schema(conn)
        competition_id = _active_competition(conn)
        cid = _competition_key(competition_id)
        exists = conn.execute(
            """SELECT 1 FROM league_ges_result_publications
               WHERE guild_id=? AND league_id=? AND competition_id=? LIMIT 1""",
            (int(guild_id), ges.GES_LEAGUE_ID, cid),
        ).fetchone()
        if exists:
            return competition_id

        for row in _current_rows(conn, competition_id):
            conn.execute(
                """INSERT OR IGNORE INTO league_ges_result_publications
                   (guild_id,league_id,competition_id,fixture_key,home_team,
                    away_team,home_goals,away_goals,status)
                   VALUES(?,?,?,?,?,?,?,?, 'baseline')""",
                (
                    int(guild_id), ges.GES_LEAGUE_ID, cid,
                    _fixture_key(row["home_team"], row["away_team"]),
                    str(row["home_team"]), str(row["away_team"]),
                    int(row["home_goals"]), int(row["away_goals"]),
                ),
            )
        conn.commit()
        return competition_id
    finally:
        conn.close()


def _queue_unseen_current(runtime, guild_id: int) -> tuple[int | None, int]:
    """Queue every current GES fixture that has never been seen in this edition."""
    conn = ges.league.db(runtime, int(guild_id))
    queued = 0
    try:
        _ensure_schema(conn)
        competition_id = _active_competition(conn)
        cid = _competition_key(competition_id)
        for row in _current_rows(conn, competition_id):
            key = _fixture_key(row["home_team"], row["away_team"])
            previous = conn.execute(
                """SELECT status FROM league_ges_result_publications
                   WHERE guild_id=? AND league_id=? AND competition_id=? AND fixture_key=?""",
                (int(guild_id), ges.GES_LEAGUE_ID, cid, key),
            ).fetchone()
            if previous is None:
                conn.execute(
                    """INSERT INTO league_ges_result_publications
                       (guild_id,league_id,competition_id,fixture_key,home_team,
                        away_team,home_goals,away_goals,status)
                       VALUES(?,?,?,?,?,?,?,?, 'pending')""",
                    (
                        int(guild_id), ges.GES_LEAGUE_ID, cid, key,
                        str(row["home_team"]), str(row["away_team"]),
                        int(row["home_goals"]), int(row["away_goals"]),
                    ),
                )
                queued += 1
            else:
                # Corrections in GES update the stored score but do not create a
                # second "new result" publication for the same fixture.
                conn.execute(
                    """UPDATE league_ges_result_publications
                       SET home_team=?,away_team=?,home_goals=?,away_goals=?
                       WHERE guild_id=? AND league_id=? AND competition_id=? AND fixture_key=?""",
                    (
                        str(row["home_team"]), str(row["away_team"]),
                        int(row["home_goals"]), int(row["away_goals"]),
                        int(guild_id), ges.GES_LEAGUE_ID, cid, key,
                    ),
                )
        conn.commit()
        return competition_id, queued
    finally:
        conn.close()


def _pending_rows(runtime, guild_id: int, competition_id: int | None):
    conn = ges.league.db(runtime, int(guild_id))
    try:
        _ensure_schema(conn)
        cid = _competition_key(competition_id)
        current_keys = {
            _fixture_key(row["home_team"], row["away_team"])
            for row in _current_rows(conn, competition_id)
        }
        rows = conn.execute(
            """SELECT fixture_key,home_team,away_team,home_goals,away_goals
               FROM league_ges_result_publications
               WHERE guild_id=? AND league_id=? AND competition_id=? AND status='pending'
               ORDER BY first_seen_at ASC, fixture_key ASC""",
            (int(guild_id), ges.GES_LEAGUE_ID, cid),
        ).fetchall()
        # If GES removed/corrected a fixture before we managed to publish it,
        # never send a result that is no longer part of the authoritative snapshot.
        return [row for row in rows if str(row["fixture_key"]) in current_keys]
    finally:
        conn.close()


def _mark_published(
    runtime,
    guild_id: int,
    competition_id: int | None,
    fixture_key: str,
    channel_id: int,
    message_id: int,
) -> None:
    conn = ges.league.db(runtime, int(guild_id))
    try:
        _ensure_schema(conn)
        conn.execute(
            """UPDATE league_ges_result_publications
               SET status='published',discord_channel_id=?,discord_message_id=?,
                   published_at=CURRENT_TIMESTAMP,last_error=NULL
               WHERE guild_id=? AND league_id=? AND competition_id=? AND fixture_key=?""",
            (
                int(channel_id), int(message_id), int(guild_id), ges.GES_LEAGUE_ID,
                _competition_key(competition_id), str(fixture_key),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def _mark_error(
    runtime,
    guild_id: int,
    competition_id: int | None,
    fixture_key: str,
    error: Exception,
) -> None:
    conn = ges.league.db(runtime, int(guild_id))
    try:
        _ensure_schema(conn)
        conn.execute(
            """UPDATE league_ges_result_publications
               SET last_error=?
               WHERE guild_id=? AND league_id=? AND competition_id=? AND fixture_key=?""",
            (
                f"{type(error).__name__}: {error}"[:500], int(guild_id),
                ges.GES_LEAGUE_ID, _competition_key(competition_id), str(fixture_key),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def _official_embed(guild, row) -> discord.Embed:
    home = str(row["home_team"])
    away = str(row["away_team"])
    home_icon = cards._badge(guild, home)
    away_icon = cards._badge(guild, away)
    embed = discord.Embed(
        title="📋 RESULTADO OFICIAL • GES LIGA",
        description=(
            f"{home_icon or '🛡️'} **{home}**\n"
            f"## **{int(row['home_goals'])}  —  {int(row['away_goals'])}**\n"
            f"{away_icon or '🛡️'} **{away}**"
        ),
        color=discord.Color.green(),
    )
    embed.add_field(name="Estado GES", value="🟢 Cargado en GES", inline=True)
    embed.add_field(
        name="Sincronización",
        value="Nuevo resultado detectado al actualizar GES.",
        inline=False,
    )
    embed.set_footer(text="AJPA • Fuente oficial: GES")
    return embed


async def _publish_pending(runtime, bot, guild_id: int, competition_id: int | None) -> tuple[int, list[str]]:
    pending = _pending_rows(runtime, int(guild_id), competition_id)
    if not pending:
        return 0, []

    channel_id = cards._get_channel_id(runtime, int(guild_id))
    if not channel_id:
        return 0, [
            "Hay resultados nuevos de GES pendientes de publicar, pero no hay canal de resultados GES configurado."
        ]

    guild = bot.get_guild(int(guild_id))
    if guild is None:
        return 0, ["No se encontró el servidor para publicar los nuevos resultados GES."]
    channel = guild.get_channel(int(channel_id))
    if not isinstance(channel, discord.TextChannel):
        return 0, ["El canal configurado para resultados GES ya no está disponible."]

    sent_count = 0
    warnings: list[str] = []
    for row in pending:
        try:
            image = await cards._card(
                guild,
                str(row["home_team"]),
                str(row["away_team"]),
                int(row["home_goals"]),
                int(row["away_goals"]),
            )
            embed = _official_embed(guild, row)
            embed.set_image(url="attachment://ges_resultado.png")
            sent = await channel.send(
                embed=embed,
                file=discord.File(image, filename="ges_resultado.png"),
                allowed_mentions=discord.AllowedMentions.none(),
            )
            _mark_published(
                runtime, int(guild_id), competition_id,
                str(row["fixture_key"]), channel.id, sent.id,
            )
            sent_count += 1
        except Exception as exc:
            _mark_error(
                runtime, int(guild_id), competition_id,
                str(row["fixture_key"]), exc,
            )
            warnings.append(
                f"No se pudo publicar {row['home_team']} {row['home_goals']}-{row['away_goals']} {row['away_team']}: {exc}"
            )

    return sent_count, warnings


def apply_ges_new_result_cards(runtime, bot) -> None:
    if getattr(runtime, "_ajpa_ges_new_result_cards", False):
        return

    base_sync = ges.sync_from_ges
    if getattr(base_sync, "_ajpa_new_result_cards", False):
        runtime._ajpa_ges_new_result_cards = True
        return

    async def sync_with_new_result_cards(
        runtime_arg,
        bot_arg,
        guild_id: int,
        staff_user_id: int | None = None,
    ) -> dict:
        # Capture everything that already exists before the authoritative sync.
        # This makes deployment safe: historical/current cards are not reposted.
        _seed_existing_as_baseline(runtime_arg, int(guild_id))

        result = await base_sync(
            runtime_arg, bot_arg, int(guild_id), staff_user_id
        )

        competition_id, newly_queued = _queue_unseen_current(
            runtime_arg, int(guild_id)
        )
        sent_count, publish_warnings = await _publish_pending(
            runtime_arg, bot_arg, int(guild_id), competition_id
        )

        merged = dict(result)
        merged["new_result_cards_detected"] = int(newly_queued)
        merged["new_result_cards_sent"] = int(sent_count)
        if publish_warnings:
            warnings = list(merged.get("warnings") or [])
            warnings.extend(publish_warnings)
            merged["warnings"] = list(dict.fromkeys(warnings))[:40]
        return merged

    sync_with_new_result_cards._ajpa_new_result_cards = True
    sync_with_new_result_cards._ajpa_new_result_cards_base = base_sync
    ges.sync_from_ges = sync_with_new_result_cards

    runtime._ajpa_ges_new_result_cards = True
    print(
        "AJPA GES nuevos resultados activo: solo fixtures nuevos -> tarjeta RESULTADO FINAL"
    )
