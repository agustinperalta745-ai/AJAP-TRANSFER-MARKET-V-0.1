"""Expose the currently assigned Discord manager under each AJPA league team.

The standings payload lives in the Mobile/GES database, while Discord club
assignments are guild-isolated. Do not assume both reads point at the same
SQLite connection: resolve the real assignment DB through ``runtime.db_for_guild``
and copy only the public manager label into the Mobile cache used by standings.
"""

from __future__ import annotations

import os
import re
import unicodedata

import mobile_parity_api_patch as parity
import mobile_write_api


_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS mobile_manager_names (
    club TEXT PRIMARY KEY COLLATE NOCASE,
    user_id INTEGER,
    manager_name TEXT NOT NULL,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
)
"""


def _ensure_table(conn) -> None:
    conn.execute(_TABLE_SQL)


def _target_guild(bot):
    raw = (os.getenv("AJPA_MOBILE_GUILD_ID") or os.getenv("DISCORD_GUILD_ID") or "").strip()
    if raw:
        try:
            guild = bot.get_guild(int(raw))
            if guild is not None:
                return guild
        except (TypeError, ValueError):
            pass
    guilds = list(getattr(bot, "guilds", []) or [])
    return guilds[0] if guilds else None


def _plain_club(value: str) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(char for char in text if not unicodedata.combining(char))
    text = re.sub(r"[^a-z0-9]+", " ", text.casefold()).strip()
    return re.sub(r"\s+", " ", text)


# GES, roster JSONs and historical Discord assignments do not always use the
# exact same club spelling. Normalize only known AJPA aliases; unknown clubs
# still match naturally through the accent/punctuation-insensitive key above.
_CLUB_ALIASES = {
    "monaco": "as monaco",
    "as monaco": "as monaco",
    "atletico madrid": "atletico de madrid",
    "atletico de madrid": "atletico de madrid",
    "lyon": "olympique de lyon",
    "olympique lyon": "olympique de lyon",
    "olympique de lyon": "olympique de lyon",
    "marsella": "olympique de marsella",
    "marseille": "olympique de marsella",
    "olympique marsella": "olympique de marsella",
    "olympique de marsella": "olympique de marsella",
    "olympique marseille": "olympique de marsella",
    "olympique de marseille": "olympique de marsella",
    "psg": "paris saint germain",
    "paris sg": "paris saint germain",
    "paris saint germain": "paris saint germain",
    "betis": "real betis",
    "real betis": "real betis",
    "sevilla": "sevilla fc",
    "sevilla fc": "sevilla fc",
    "villarreal": "villarreal cf",
    "villarreal cf": "villarreal cf",
    "villareal": "villarreal cf",
    "villareal cf": "villarreal cf",
    "zaragoza": "real zaragoza",
    "real zaragoza": "real zaragoza",
    "middle": "middlesbrough",
    "middlesbrough": "middlesbrough",
}


def _club_key(value: str) -> str:
    plain = _plain_club(value)
    return _CLUB_ALIASES.get(plain, plain)


def _strip_club_suffix(value: str, club: str) -> str:
    cleaned = str(value or "").strip()
    if not cleaned:
        return ""
    suffix = f" | {club}"
    if cleaned.casefold().endswith(suffix.casefold()):
        cleaned = cleaned[: -len(suffix)].strip()
    return cleaned


def _clean_name(member, club: str) -> str:
    # Prefer the server display name because that is the identity Staff manages
    # in AJPA. Fall back to global/user name if no nickname is available.
    for raw in (
        getattr(member, "display_name", None),
        getattr(member, "global_name", None),
        getattr(member, "name", None),
    ):
        value = _strip_club_suffix(raw, club)
        if value:
            return value
    return ""


def _usable_cached_name(value: str, user_id: int) -> str:
    name = str(value or "").strip()
    if not name:
        return ""
    if name.casefold() == f"usuario {int(user_id)}".casefold():
        return ""
    return name


def _open_assignment_db(runtime, guild_id: int):
    if hasattr(runtime, "db_for_guild"):
        return runtime.db_for_guild(int(guild_id))
    return mobile_write_api.write_db()


def _assignment_rows(runtime, guild_id: int):
    """Read club ownership from Discord's authoritative guild-isolated DB."""
    conn = _open_assignment_db(runtime, guild_id)
    try:
        if "clubs" not in parity._tables(conn):
            return []
        columns = (
            set(mobile_write_api._columns(conn, "clubs"))
            if hasattr(mobile_write_api, "_columns")
            else set()
        )
        if columns and not {"name", "user_id"}.issubset(columns):
            return []
        rows = conn.execute(
            """SELECT name,user_id FROM clubs
               WHERE user_id IS NOT NULL AND TRIM(COALESCE(name,''))<>''
               ORDER BY name COLLATE NOCASE"""
        ).fetchall()
        return [(str(row["name"] or "").strip(), int(row["user_id"])) for row in rows]
    finally:
        conn.close()


def _stored_original_name(runtime, guild_id: int, user_id: int, club: str) -> str:
    """Fallback to the pre-AJPA nickname remembered when the club was assigned."""
    conn = _open_assignment_db(runtime, guild_id)
    try:
        tables = parity._tables(conn)
        if "discord_nickname_state" not in tables:
            return ""
        columns = (
            set(mobile_write_api._columns(conn, "discord_nickname_state"))
            if hasattr(mobile_write_api, "_columns")
            else set()
        )
        if columns and not {"guild_id", "user_id", "original_nick"}.issubset(columns):
            return ""
        row = conn.execute(
            """SELECT original_nick
               FROM discord_nickname_state
               WHERE guild_id=? AND user_id=?
               LIMIT 1""",
            (int(guild_id), int(user_id)),
        ).fetchone()
        if not row:
            return ""
        return _strip_club_suffix(row["original_nick"], club)
    finally:
        conn.close()


async def _resolve_manager_name(runtime, bot, guild, user_id: int, club: str) -> str:
    """Resolve a manager label without ever preferring a raw Discord numeric ID."""
    member = guild.get_member(user_id)
    if member is None:
        try:
            member = await guild.fetch_member(user_id)
        except Exception:
            member = None
    if member is not None:
        name = _clean_name(member, club)
        if name:
            return name

    # Some assigned users are not returned by the guild member cache/fetch path.
    # Discord can still resolve their global account by user id, which is enough
    # to show a human-readable DT name instead of "Usuario 123...".
    user = None
    get_user = getattr(bot, "get_user", None)
    if callable(get_user):
        try:
            user = get_user(int(user_id))
        except Exception:
            user = None
    if user is None:
        fetch_user = getattr(bot, "fetch_user", None)
        if callable(fetch_user):
            try:
                user = await fetch_user(int(user_id))
            except Exception:
                user = None
    if user is not None:
        name = _clean_name(user, club)
        if name:
            return name

    return _stored_original_name(runtime, int(guild.id), user_id, club)


async def _refresh_manager_names(runtime, bot) -> None:
    guild = _target_guild(bot)
    if guild is None:
        return

    # Read assignments from the same guild DB used by Discord interactions.
    assignments = _assignment_rows(runtime, int(guild.id))

    # Write the lightweight public manager cache into the Mobile/GES DB consumed
    # by /api/v1/league. These paths can legitimately differ.
    with mobile_write_api.write_db() as conn:
        _ensure_table(conn)
        cached_rows = conn.execute(
            "SELECT club,user_id,manager_name FROM mobile_manager_names"
        ).fetchall()
        cached_by_key = {}
        for row in cached_rows:
            key = _club_key(str(row["club"] or ""))
            if key:
                cached_by_key[key] = {
                    "user_id": int(row["user_id"]) if row["user_id"] is not None else None,
                    "manager_name": str(row["manager_name"] or "").strip(),
                }

        active_raw_clubs: set[str] = set()
        for club, user_id in assignments:
            if not club:
                continue
            active_raw_clubs.add(club.casefold())

            manager_name = await _resolve_manager_name(runtime, bot, guild, user_id, club)
            previous = cached_by_key.get(_club_key(club))
            if not manager_name and previous and previous.get("user_id") == user_id:
                manager_name = _usable_cached_name(previous.get("manager_name"), user_id)
            if not manager_name:
                manager_name = f"Usuario {user_id}"

            conn.execute(
                """INSERT INTO mobile_manager_names(club,user_id,manager_name,updated_at)
                   VALUES(?,?,?,CURRENT_TIMESTAMP)
                   ON CONFLICT(club) DO UPDATE SET
                     user_id=excluded.user_id,
                     manager_name=excluded.manager_name,
                     updated_at=CURRENT_TIMESTAMP""",
                (club, user_id, manager_name),
            )

        # Remove only genuinely unassigned raw club rows. Alias matching happens
        # at read time, so we never need duplicate cache rows for PSG/Marsella/etc.
        for row in cached_rows:
            raw = str(row["club"] or "").strip()
            if raw and raw.casefold() not in active_raw_clubs:
                conn.execute(
                    "DELETE FROM mobile_manager_names WHERE club=? COLLATE NOCASE",
                    (raw,),
                )

        conn.commit()


def _manager_map(conn) -> dict[str, dict]:
    if "mobile_manager_names" not in parity._tables(conn):
        return {}
    rows = conn.execute(
        "SELECT club,user_id,manager_name FROM mobile_manager_names"
    ).fetchall()
    result: dict[str, dict] = {}
    for row in rows:
        key = _club_key(str(row["club"] or ""))
        if not key:
            continue
        result[key] = {
            "manager_name": str(row["manager_name"] or "").strip() or None,
            "manager_user_id": str(row["user_id"]) if row["user_id"] is not None else None,
        }
    return result


def apply_mobile_manager_names_patch(runtime, bot) -> None:
    if getattr(bot, "_ajpa_mobile_manager_names_patch", False):
        return

    with mobile_write_api.write_db() as conn:
        _ensure_table(conn)
        conn.commit()

    current_league_payload = parity.league_payload
    if not getattr(current_league_payload, "_ajpa_manager_names", False):
        def league_payload(conn):
            payload = dict(current_league_payload(conn))
            managers = _manager_map(conn)
            standings = []
            for item in payload.get("standings") or []:
                row = dict(item)
                info = managers.get(_club_key(str(row.get("team") or "")))
                row["manager_name"] = info.get("manager_name") if info else None
                row["manager_user_id"] = info.get("manager_user_id") if info else None
                standings.append(row)
            payload["standings"] = standings
            return payload

        league_payload._ajpa_manager_names = True
        parity.league_payload = league_payload

    async def refresh_manager_names_on_ready():
        try:
            await _refresh_manager_names(runtime, bot)
            print(
                "AJPA Mobile: nombres de DT sincronizados desde la DB real del servidor, "
                "con fallback global de Discord y aliases de GES"
            )
        except Exception as exc:
            print(f"AJPA Mobile manager names error: {type(exc).__name__}: {exc}")

    bot.add_listener(refresh_manager_names_on_ready, "on_ready")
    bot._ajpa_mobile_manager_names_patch = True
