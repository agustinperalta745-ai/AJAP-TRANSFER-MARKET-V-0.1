"""Radio Pasillo rumors for every new player market publication.

Discord and AJPA Mobile both end in the same persisted outbox. The publication
id is UNIQUE in that outbox, so a listing can generate at most one queued Radio
Pasillo event even when several compatibility layers observe the same creation.
"""

from __future__ import annotations

import sqlite3
from contextlib import closing

import discord
from discord.ext import tasks

import guild_isolation_patch as guild_isolation
import mobile_write_api as mobile_write
import publication_announce_patch as publication_announcements
import team_badge_selector_patch as team_badges


APP = None
BOT = None
RETRY_SECONDS = 60


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    return bool(
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
            (str(table),),
        ).fetchone()
    )


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    if not _table_exists(conn, table):
        return set()
    return {str(row["name"]) for row in conn.execute(f'PRAGMA table_info("{table}")')}


def _ensure_outbox(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS radio_player_publication_outbox (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            publication_id INTEGER NOT NULL UNIQUE,
            source TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'PENDING',
            attempts INTEGER NOT NULL DEFAULT 0,
            next_attempt_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            last_error TEXT,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            processed_at DATETIME
        )
        """
    )
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_radio_player_publication_pending
        ON radio_player_publication_outbox(status, next_attempt_at, id)
        """
    )


def queue_player_publication(
    conn: sqlite3.Connection,
    publication_id: int,
    *,
    source: str,
) -> bool:
    """Persist one Radio Pasillo event for a newly-created publication."""
    _ensure_outbox(conn)
    cur = conn.execute(
        """
        INSERT OR IGNORE INTO radio_player_publication_outbox
            (publication_id, source)
        VALUES (?, ?)
        """,
        (
            int(publication_id),
            (str(source or "UNKNOWN").strip().upper() or "UNKNOWN")[:80],
        ),
    )
    return int(cur.rowcount or 0) > 0


def _conn_for_guild(guild_id: int):
    if APP is None:
        raise RuntimeError("AJPA runtime todavía no inicializado")
    if hasattr(APP, "db_for_guild"):
        return APP.db_for_guild(int(guild_id))
    if hasattr(APP, "guild_context"):
        with APP.guild_context(int(guild_id)):
            return APP.db()
    return APP.db()


def _pending(conn: sqlite3.Connection, limit: int = 30) -> list[dict]:
    conn.row_factory = sqlite3.Row
    _ensure_outbox(conn)
    conn.commit()
    rows = conn.execute(
        """
        SELECT id, publication_id, source, attempts
        FROM radio_player_publication_outbox
        WHERE status='PENDING'
          AND datetime(next_attempt_at) <= datetime('now')
        ORDER BY id ASC
        LIMIT ?
        """,
        (max(1, min(int(limit), 100)),),
    ).fetchall()
    return [dict(row) for row in rows]


def _mark_sent(conn: sqlite3.Connection, event_id: int) -> None:
    conn.execute(
        """
        UPDATE radio_player_publication_outbox
        SET status='PUBLISHED', processed_at=CURRENT_TIMESTAMP, last_error=NULL
        WHERE id=? AND status='PENDING'
        """,
        (int(event_id),),
    )
    conn.commit()


def _mark_skipped(conn: sqlite3.Connection, event_id: int, reason: str) -> None:
    conn.execute(
        """
        UPDATE radio_player_publication_outbox
        SET status='SKIPPED', processed_at=CURRENT_TIMESTAMP, last_error=?
        WHERE id=? AND status='PENDING'
        """,
        (str(reason)[:500], int(event_id)),
    )
    conn.commit()


def _retry(conn: sqlite3.Connection, event_id: int, error: str) -> None:
    conn.execute(
        """
        UPDATE radio_player_publication_outbox
        SET attempts=attempts+1,
            last_error=?,
            next_attempt_at=datetime('now', ?)
        WHERE id=? AND status='PENDING'
        """,
        (str(error)[:500], f"+{RETRY_SECONDS} seconds", int(event_id)),
    )
    conn.commit()


def _publication_snapshot(conn: sqlite3.Connection, publication_id: int) -> dict | None:
    conn.row_factory = sqlite3.Row
    if not _table_exists(conn, "publications"):
        return None
    publication = conn.execute(
        "SELECT * FROM publications WHERE id=? LIMIT 1",
        (int(publication_id),),
    ).fetchone()
    if publication is None:
        return None

    rating = None
    if _table_exists(conn, "roster_players"):
        cols = _columns(conn, "roster_players")
        if "rating" in cols:
            player = conn.execute(
                "SELECT rating FROM roster_players WHERE name=? COLLATE NOCASE LIMIT 1",
                (str(publication["player"]),),
            ).fetchone()
            if player is not None:
                rating = player["rating"]

    keys = set(publication.keys())
    return {
        "id": int(publication["id"]),
        "player": str(publication["player"] or "Jugador"),
        "club": str(publication["club"] or "Club"),
        "position": str(publication["position"] or "Sin definir") if "position" in keys else "Sin definir",
        "price": str(publication["price"] or "Sin definir") if "price" in keys else "Sin definir",
        "rating": rating,
    }


def _radio_message(publication: dict, club_emoji) -> str:
    rating = publication.get("rating")
    rating_text = str(rating) if rating is not None else "Sin definir"
    club_label = f"{club_emoji} **{publication['club']}**"
    return (
        "📻 **RADIO PASILLO**\n\n"
        "👀 **Se mueve el mercado...**\n\n"
        "Un nuevo nombre empezó a circular fuerte por los pasillos: "
        f"**{publication['player']}**.\n\n"
        f"Desde {club_label} habrían decidido escuchar propuestas y el futbolista "
        "**ya está disponible en el mercado**. 📞💰\n\n"
        f"⭐ **Media:** {rating_text}\n"
        f"⚽ **Posición:** {publication['position']}\n"
        f"💵 **Valor:** {publication['price']}\n\n"
        "Ahora la pelota queda del lado de los DTs...\n\n"
        "¿Quién será el primero en levantar el teléfono? 👀🔥"
    )


def _resolve_dt_role(guild):
    """Use the same DT-role preference as AJPA: configured role first, exact DT fallback."""
    if guild is None:
        return None

    role_id = None
    try:
        with closing(_conn_for_guild(guild.id)) as conn:
            conn.row_factory = sqlite3.Row
            if _table_exists(conn, "dt_role_config"):
                row = conn.execute(
                    "SELECT role_id FROM dt_role_config WHERE id=1 LIMIT 1"
                ).fetchone()
                if row and row["role_id"]:
                    role_id = int(row["role_id"])
    except Exception as exc:
        print(
            "WARNING AJPA Radio Pasillo rol DT configurado | "
            f"guild={getattr(guild, 'id', None)} {type(exc).__name__}: {exc}"
        )

    if role_id:
        configured = guild.get_role(role_id)
        if configured is not None:
            return configured

    for role in getattr(guild, "roles", []):
        if (getattr(role, "name", "") or "").strip().casefold() == "dt":
            return role
    return None


def _resolve_club_emoji(guild, club: str):
    """Reuse AJPA's canonical Staff-uploaded club emoji mapping for this guild."""
    try:
        emoji = team_badges._find_badge_emoji(guild, str(club))
    except Exception as exc:
        print(
            "WARNING AJPA Radio Pasillo emoji club | "
            f"guild={getattr(guild, 'id', None)} club={club!r} {type(exc).__name__}: {exc}"
        )
        return None
    if emoji is None or not getattr(emoji, "available", True):
        return None
    return emoji


async def _process_guild(guild) -> int:
    if guild is None:
        return 0

    with closing(_conn_for_guild(guild.id)) as conn:
        events = _pending(conn)
    if not events:
        return 0

    # Reuse the canonical Radio Pasillo channel resolver already used by the
    # rest of AJPA instead of creating a second destination setting.
    import radio_pasillo_feature_ads_patch as radio

    channel = await radio._resolve_radio_channel(guild)
    if channel is None:
        with closing(_conn_for_guild(guild.id)) as conn:
            for event in events:
                _retry(conn, int(event["id"]), "Canal Radio Pasillo no encontrado")
        return 0

    dt_role = _resolve_dt_role(guild)
    if dt_role is None:
        with closing(_conn_for_guild(guild.id)) as conn:
            for event in events:
                _retry(conn, int(event["id"]), "Rol DT no encontrado/configurado")
        print(
            "WARNING AJPA Radio Pasillo publicación: rol DT no encontrado | "
            f"guild={guild.id}"
        )
        return 0

    published = 0
    for event in events:
        event_id = int(event["id"])
        publication_id = int(event["publication_id"])
        with closing(_conn_for_guild(guild.id)) as conn:
            snapshot = _publication_snapshot(conn, publication_id)

        if snapshot is None:
            with closing(_conn_for_guild(guild.id)) as conn:
                _mark_skipped(conn, event_id, "Publicación inexistente")
            continue

        club_emoji = _resolve_club_emoji(guild, snapshot["club"])
        if club_emoji is None:
            with closing(_conn_for_guild(guild.id)) as conn:
                _retry(
                    conn,
                    event_id,
                    f"Emoji del club no encontrado: {snapshot['club']}",
                )
            print(
                "WARNING AJPA Radio Pasillo publicación: emoji de club no encontrado | "
                f"guild={guild.id} publication={publication_id} club={snapshot['club']}"
            )
            continue

        try:
            await channel.send(
                content=f"{dt_role.mention}\n\n{_radio_message(snapshot, club_emoji)}",
                allowed_mentions=discord.AllowedMentions(
                    everyone=False,
                    users=False,
                    roles=[dt_role],
                    replied_user=False,
                ),
            )
        except (discord.Forbidden, discord.HTTPException) as exc:
            with closing(_conn_for_guild(guild.id)) as conn:
                _retry(conn, event_id, f"{type(exc).__name__}: {exc}")
            continue

        with closing(_conn_for_guild(guild.id)) as conn:
            _mark_sent(conn, event_id)
        published += 1
        print(
            "AJPA Radio Pasillo jugador publicado | "
            f"guild={guild.id} publication={publication_id} role={dt_role.id} "
            f"club_emoji={getattr(club_emoji, 'name', '?')} source={event.get('source')}"
        )

    return published


@tasks.loop(seconds=5)
async def _publication_radio_loop():
    if BOT is None or not BOT.is_ready():
        return
    for guild in list(getattr(BOT, "guilds", [])):
        try:
            await _process_guild(guild)
        except Exception as exc:
            print(
                "WARNING AJPA Radio Pasillo publicación | "
                f"guild={getattr(guild, 'id', None)} {type(exc).__name__}: {exc}"
            )


@_publication_radio_loop.before_loop
async def _before_publication_radio_loop():
    if BOT is not None:
        await BOT.wait_until_ready()


async def _on_ready_publication_radio():
    if BOT is None:
        return
    for guild in list(getattr(BOT, "guilds", [])):
        try:
            await _process_guild(guild)
        except Exception as exc:
            print(
                "WARNING AJPA Radio Pasillo publicación startup | "
                f"guild={getattr(guild, 'id', None)} {type(exc).__name__}: {exc}"
            )
    if not _publication_radio_loop.is_running():
        _publication_radio_loop.start()


def _install_mobile_hook() -> None:
    current = mobile_write.create_publication
    if getattr(current, "_ajpa_radio_player_publication_wrapped", False):
        return

    def create_publication_with_radio(conn, session: dict, payload: dict) -> dict:
        result = current(conn, session, payload)
        publication_id = result.get("publication_id")
        if publication_id is not None:
            queue_player_publication(
                conn,
                int(publication_id),
                source="MOBILE_APP",
            )
        return result

    create_publication_with_radio._ajpa_radio_player_publication_wrapped = True
    mobile_write.create_publication = create_publication_with_radio


def _install_discord_hook() -> None:
    current = publication_announcements._send_public_announcement
    if getattr(current, "_ajpa_radio_player_publication_wrapped", False):
        return

    async def public_announcement_with_radio(interaction, publication):
        guild = getattr(interaction, "guild", None)
        if guild is not None:
            try:
                with closing(_conn_for_guild(guild.id)) as conn:
                    queued = queue_player_publication(
                        conn,
                        int(publication["id"]),
                        source="DISCORD_BOT",
                    )
                    conn.commit()
                if queued:
                    print(
                        "AJPA Radio Pasillo publicación en cola | "
                        f"guild={guild.id} publication={publication['id']} source=DISCORD_BOT"
                    )
            except Exception as exc:
                # The market listing already exists; never invalidate it because
                # Discord's Radio queue had a transient storage problem.
                print(
                    "WARNING AJPA Radio Pasillo queue publicación Discord | "
                    f"publication={publication.get('id') if hasattr(publication, 'get') else '?'} "
                    f"{type(exc).__name__}: {exc}"
                )
        return await current(interaction, publication)

    public_announcement_with_radio._ajpa_radio_player_publication_wrapped = True
    publication_announcements._send_public_announcement = public_announcement_with_radio


def apply_radio_player_publication_patch(runtime, bot) -> None:
    global APP, BOT
    APP = runtime
    BOT = bot
    if getattr(runtime, "_ajpa_radio_player_publication_patch", False):
        return

    _install_mobile_hook()
    _install_discord_hook()
    bot.add_listener(_on_ready_publication_radio, "on_ready")
    runtime._ajpa_radio_player_publication_patch = True
    print(
        "AJPA Radio Pasillo: publicaciones conectadas App + Discord con dedupe + ping DT + emoji de club"
    )


_base_apply_guild_isolation_patch = guild_isolation.apply_guild_isolation_patch


def _apply_guild_isolation_then_player_publication_radio(runtime, bot):
    _base_apply_guild_isolation_patch(runtime, bot)
    apply_radio_player_publication_patch(runtime, bot)


if not getattr(
    guild_isolation.apply_guild_isolation_patch,
    "_ajpa_radio_player_publication_wrapped",
    False,
):
    _apply_guild_isolation_then_player_publication_radio._ajpa_radio_player_publication_wrapped = True
    guild_isolation.apply_guild_isolation_patch = _apply_guild_isolation_then_player_publication_radio
