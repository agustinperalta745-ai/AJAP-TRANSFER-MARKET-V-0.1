"""Expose the currently assigned Discord manager under each AJPA league team."""

from __future__ import annotations

import os

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


def _clean_name(member, club: str) -> str:
    for raw in (
        getattr(member, "global_name", None),
        getattr(member, "name", None),
        getattr(member, "display_name", None),
    ):
        value = str(raw or "").strip()
        if not value:
            continue
        suffix = f" | {club}".casefold()
        if value.casefold().endswith(suffix):
            value = value[: -len(suffix)].strip()
        if value:
            return value
    return ""


async def _refresh_manager_names(bot) -> None:
    guild = _target_guild(bot)
    if guild is None:
        return

    with mobile_write_api.write_db() as conn:
        _ensure_table(conn)
        if "clubs" not in parity._tables(conn):
            conn.commit()
            return

        club_columns = set(mobile_write_api._columns(conn, "clubs")) if hasattr(mobile_write_api, "_columns") else set()
        if club_columns and not {"name", "user_id"}.issubset(club_columns):
            conn.commit()
            return

        rows = conn.execute(
            """SELECT name,user_id FROM clubs
               WHERE user_id IS NOT NULL AND TRIM(COALESCE(name,''))<>''
               ORDER BY name COLLATE NOCASE"""
        ).fetchall()
        assigned_clubs = {str(row["name"] or "").strip().casefold() for row in rows}

        cached_rows = conn.execute(
            "SELECT club,user_id,manager_name FROM mobile_manager_names"
        ).fetchall()
        cached = {
            str(row["club"] or "").strip().casefold(): {
                "user_id": int(row["user_id"]) if row["user_id"] is not None else None,
                "manager_name": str(row["manager_name"] or "").strip(),
            }
            for row in cached_rows
        }

        for row in rows:
            club = str(row["name"] or "").strip()
            user_id = int(row["user_id"])
            member = guild.get_member(user_id)
            if member is None:
                try:
                    member = await guild.fetch_member(user_id)
                except Exception:
                    member = None

            manager_name = _clean_name(member, club) if member is not None else ""
            previous = cached.get(club.casefold())
            if not manager_name and previous and previous.get("user_id") == user_id:
                manager_name = str(previous.get("manager_name") or "").strip()
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

        for row in cached_rows:
            key = str(row["club"] or "").strip().casefold()
            if key not in assigned_clubs:
                conn.execute("DELETE FROM mobile_manager_names WHERE club=? COLLATE NOCASE", (str(row["club"]),))

        conn.commit()


def _manager_map(conn) -> dict[str, dict]:
    if "mobile_manager_names" not in parity._tables(conn):
        return {}
    rows = conn.execute(
        "SELECT club,user_id,manager_name FROM mobile_manager_names"
    ).fetchall()
    return {
        str(row["club"] or "").strip().casefold(): {
            "manager_name": str(row["manager_name"] or "").strip() or None,
            "manager_user_id": str(row["user_id"]) if row["user_id"] is not None else None,
        }
        for row in rows
        if str(row["club"] or "").strip()
    }


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
                info = managers.get(str(row.get("team") or "").strip().casefold())
                row["manager_name"] = info.get("manager_name") if info else None
                row["manager_user_id"] = info.get("manager_user_id") if info else None
                standings.append(row)
            payload["standings"] = standings
            return payload

        league_payload._ajpa_manager_names = True
        parity.league_payload = league_payload

    async def refresh_manager_names_on_ready():
        try:
            await _refresh_manager_names(bot)
            print("AJPA Mobile: nombres de DT sincronizados con las asignaciones de Discord")
        except Exception as exc:
            print(f"AJPA Mobile manager names error: {type(exc).__name__}: {exc}")

    bot.add_listener(refresh_manager_names_on_ready, "on_ready")
    bot._ajpa_mobile_manager_names_patch = True
