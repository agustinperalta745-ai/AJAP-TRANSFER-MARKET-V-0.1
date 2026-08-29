"""Keep AJAP's active team catalog limited to real JSON-backed clubs.

Current league rule: only clubs with a valid source JSON in data/ are part of the
selectable/active catalog. Legacy seeded/admin-created rows may remain in SQLite
for history and referential safety, but they are kept inactive and must not count
as available clubs.

A source may be either a normal ``*.json`` file or a multipart upload split as
``*.json.part01``, ``*.json.part02``, etc. Multipart files are concatenated and
validated as one JSON document before their club is admitted to the catalog.

Staff-deleted teams remain hidden. Adding a new valid JSON source automatically
makes that club eligible on the next catalog sync, provided its canonical row can
be resolved (or it is created safely from the JSON name).
"""

from __future__ import annotations

import json
from pathlib import Path

import admin_roster_builder_patch as builder
import guild_isolation_patch as guild_isolation
import team_assignment as teams


_ORIGINAL_ACTIVE_TEAMS = None
_ORIGINAL_OFFICIAL_NAME = None
DATA_DIR = Path(__file__).resolve().parent / "data"


def _table_exists(conn, table: str) -> bool:
    return bool(
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
            (table,),
        ).fetchone()
    )


def _country_for(club: str) -> str:
    wanted = str(club or "").strip().casefold()
    for name, country in getattr(teams, "OFFICIAL_TEAMS", []):
        if str(name).strip().casefold() == wanted:
            return str(country or "Sin definir")
    if wanted == "real betis":
        return "España"
    return "Sin definir"


def _is_deleted(conn, club: str) -> bool:
    if not _table_exists(conn, "deleted_teams"):
        return False
    return bool(
        conn.execute(
            "SELECT 1 FROM deleted_teams WHERE name = ? COLLATE NOCASE LIMIT 1",
            (club,),
        ).fetchone()
    )


def _json_payload_sources():
    """Yield (source label, parsed payload) for regular and multipart JSON files."""
    for path in sorted(DATA_DIR.glob("*.json"), key=lambda item: item.name.casefold()):
        try:
            yield path.name, json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            print(f"WARNING AJAP catálogo JSON: no se pudo leer {path.name}: {exc}")

    multipart = {}
    for part in DATA_DIR.glob("*.json.part*"):
        prefix, separator, suffix = part.name.rpartition(".part")
        if not separator or not prefix.casefold().endswith(".json") or not suffix.isdigit():
            continue
        multipart.setdefault(prefix, []).append((int(suffix), part))

    for prefix in sorted(multipart, key=str.casefold):
        parts = sorted(multipart[prefix], key=lambda item: item[0])
        try:
            text = "".join(path.read_text(encoding="utf-8") for _index, path in parts)
            yield f"{prefix}.part*", json.loads(text)
        except Exception as exc:
            print(
                f"WARNING AJAP catálogo JSON multipart: no se pudo reconstruir {prefix}: {exc}"
            )


def _json_source_team_names():
    """Return clubs backed by a readable JSON source with a non-empty roster."""
    names = []
    seen = set()
    for source_label, payload in _json_payload_sources():
        raw = str(payload.get("equipo", "") or "").strip()
        players = payload.get("jugadores")
        key = raw.casefold()
        if not raw or not isinstance(players, list) or not players or key in seen:
            continue
        seen.add(key)
        names.append(raw)
        if ".part*" in source_label:
            print(f"AJAP catálogo JSON multipart válido: {source_label} -> {raw}")
    return names


def _candidate_names(source_name: str):
    raw = str(source_name or "").strip()
    candidates = [raw]
    lower = raw.casefold()

    aliases = {
        "villarreal cf": "Villarreal",
        "villareal cf": "Villarreal",
        "villareal": "Villarreal",
        "sevilla fc": "Sevilla",
    }
    alias = aliases.get(lower)
    if alias:
        candidates.append(alias)

    for suffix in (" FC", " CF"):
        if raw.upper().endswith(suffix):
            candidates.append(raw[: -len(suffix)].strip())

    unique = []
    seen = set()
    for candidate in candidates:
        key = candidate.casefold()
        if candidate and key not in seen:
            seen.add(key)
            unique.append(candidate)
    return unique


def _resolve_catalog_name(conn, source_name: str) -> str:
    """Prefer the canonical row already used by the DB, otherwise use JSON name."""
    for candidate in _candidate_names(source_name):
        row = conn.execute(
            "SELECT name FROM league_teams WHERE name = ? COLLATE NOCASE LIMIT 1",
            (candidate,),
        ).fetchone()
        if row:
            return str(row["name"] or "").strip()
    return str(source_name or "").strip()


def _upsert_catalog(conn, club: str, country: str):
    existing = conn.execute(
        "SELECT country FROM league_teams WHERE name = ? COLLATE NOCASE LIMIT 1",
        (club,),
    ).fetchone()
    final_country = (
        str(existing["country"] or "").strip()
        if existing and str(existing["country"] or "").strip()
        else str(country or "Sin definir").strip() or "Sin definir"
    )

    conn.execute(
        """
        INSERT INTO league_teams (name, country, active)
        VALUES (?, ?, 1)
        ON CONFLICT(name) DO UPDATE SET
            country = CASE
                WHEN TRIM(COALESCE(league_teams.country, '')) = '' THEN excluded.country
                ELSE league_teams.country
            END,
            active = 1
        """,
        (club, final_country),
    )
    conn.execute(
        """
        INSERT OR IGNORE INTO club_finances (club, balance, updated_at)
        VALUES (?, ?, CURRENT_TIMESTAMP)
        """,
        (club, builder.INITIAL_TEAM_BUDGET),
    )


def _sync_loaded_teams_into_catalog():
    app = builder.APP
    if app is None:
        return

    builder._ensure_schema()
    with app.db() as conn:
        # The database can keep legacy rows for history, but only clubs backed by
        # a valid JSON source are active. Every panel/admin selector therefore
        # uses the same live source of truth as the initial user selector.
        conn.execute("UPDATE league_teams SET active = 0")

        active_json_clubs = []
        for source_name in _json_source_team_names():
            club = _resolve_catalog_name(conn, source_name)
            if not club or _is_deleted(conn, club):
                continue
            _upsert_catalog(conn, club, _country_for(club))
            active_json_clubs.append(club)

        if active_json_clubs:
            print(
                "AJAP catálogo activo JSON-only: "
                f"{len(active_json_clubs)} club(es)"
            )


def _active_teams():
    _sync_loaded_teams_into_catalog()
    return _ORIGINAL_ACTIVE_TEAMS()


def _official_name(name):
    _sync_loaded_teams_into_catalog()
    return _ORIGINAL_OFFICIAL_NAME(name)


def apply_roster_catalog_autosync_patch(runtime, bot):
    """Install after the deletion/catalog guards have finished applying."""
    global _ORIGINAL_ACTIVE_TEAMS, _ORIGINAL_OFFICIAL_NAME

    if getattr(runtime, "_ajpa_roster_catalog_autosync_patch", False):
        return

    # Capture the FINAL tombstone-aware functions now, not at module import time.
    _ORIGINAL_ACTIVE_TEAMS = builder._active_teams
    _ORIGINAL_OFFICIAL_NAME = builder._official_name

    builder._active_teams = _active_teams
    builder._official_name = _official_name
    teams.official_name = _official_name

    # Force one sync immediately for the startup DB. Future guilds are synced
    # lazily whenever their selector/official-name lookup runs.
    _sync_loaded_teams_into_catalog()

    runtime._ajpa_roster_catalog_autosync_patch = True
    print("AJAP catálogo limitado a equipos con JSON real en data/ (incluye multipart)")


_original_apply_guild_isolation_patch = guild_isolation.apply_guild_isolation_patch


def _apply_guild_isolation_then_catalog_autosync(runtime, bot):
    _original_apply_guild_isolation_patch(runtime, bot)
    apply_roster_catalog_autosync_patch(runtime, bot)


if not getattr(
    guild_isolation.apply_guild_isolation_patch,
    "_ajpa_roster_catalog_autosync_wrapped",
    False,
):
    _apply_guild_isolation_then_catalog_autosync._ajpa_roster_catalog_autosync_wrapped = True
    guild_isolation.apply_guild_isolation_patch = _apply_guild_isolation_then_catalog_autosync
