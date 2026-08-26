"""Apply AJAP's current 3-stat OVR formula to the uploaded Betis.json roster.

The base Betis replacement remains responsible for canonical names, full PES6
attributes, special abilities and per-guild migration safety. This overlay updates
the static OVRs from the same JSON source, bumps the migration marker and guarantees
that Real Betis is registered as an active selectable team in every guild database.
"""

from __future__ import annotations

import betis_replacement_patch as base


MIGRATION_MARKER = "real_betis_json_v3_ovr3_20260826"


def _aerial(stats):
    return int(round((int(stats["cabezazo"]) + int(stats["salto"])) / 2))


def _role_values(position: str, stats):
    primary = str(position or "").upper().replace(" ", "").split("/", 1)[0]
    aerial = _aerial(stats)
    values = {
        "GK": (("Reflejos", stats["respuesta"]), ("Atajadas", stats["cualidad_portero"]), ("Colocación", stats["defensa"])),
        "CB": (("Defensa", stats["defensa"]), ("Fuerza", stats["equilibrio"]), ("Juego aéreo", aerial)),
        "LB": (("Defensa", stats["defensa"]), ("Velocidad", stats["velocidad_maxima"]), ("Resistencia", stats["resistencia"])),
        "RB": (("Defensa", stats["defensa"]), ("Velocidad", stats["velocidad_maxima"]), ("Resistencia", stats["resistencia"])),
        "DMF": (("Defensa", stats["defensa"]), ("Pase", stats["precision_pase_corto"]), ("Resistencia", stats["resistencia"])),
        "CMF": (("Pase", stats["precision_pase_corto"]), ("Técnica", stats["tecnica"]), ("Resistencia", stats["resistencia"])),
        "AMF": (("Pase", stats["precision_pase_corto"]), ("Regate", stats["precision_regate"]), ("Tiro", stats["precision_tiro"])),
        "LMF": (("Velocidad", stats["velocidad_maxima"]), ("Regate", stats["precision_regate"]), ("Pase", stats["precision_pase_corto"])),
        "RMF": (("Velocidad", stats["velocidad_maxima"]), ("Regate", stats["precision_regate"]), ("Pase", stats["precision_pase_corto"])),
        "WF": (("Velocidad", stats["velocidad_maxima"]), ("Regate", stats["precision_regate"]), ("Tiro", stats["precision_tiro"])),
        "SS": (("Regate", stats["precision_regate"]), ("Pase", stats["precision_pase_corto"]), ("Tiro", stats["precision_tiro"])),
        "CF": (("Tiro", stats["precision_tiro"]), ("Ataque", stats["ataque"]), ("Juego aéreo", aerial)),
    }.get(primary)
    if values is None:
        raise RuntimeError(f"Posición Betis sin fórmula OVR: {position}")
    return tuple((name, int(value)) for name, value in values)


def _rating(position: str, stats) -> int:
    values = _role_values(position, stats)
    return int(round(sum(value for _, value in values) / 3))


def _rebuild_roster():
    roster = []
    for name, position, _old_rating in base.BETIS_ROSTER:
        payload = base.BETIS_DATA.get(name)
        if not payload:
            raise RuntimeError(f"Falta {name} en Betis.json")
        roster.append((name, position, _rating(position, payload["stats"])))
    return roster


def _ensure_betis_team(runtime, conn):
    """Register Betis in league_teams even when an older seed marker already exists."""
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS league_teams (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL COLLATE NOCASE UNIQUE,
            country TEXT NOT NULL,
            active INTEGER NOT NULL DEFAULT 1,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute(
        """
        INSERT INTO league_teams (name, country, active)
        VALUES (?, 'España', 1)
        ON CONFLICT(name) DO UPDATE SET
            country = excluded.country,
            active = 1
        """,
        (base.BETIS,),
    )


base.BETIS_ROSTER = _rebuild_roster()
base.ROSTER_META = {name: (position, rating) for name, position, rating in base.BETIS_ROSTER}
base.MARKER = MIGRATION_MARKER
base.SOURCE = "Betis.json • OVR AJAP promedio de 3 stats • 2026-08-26"
base.multi.REAL_BETIS_ROSTER = list(base.BETIS_ROSTER)

# The original migration can legitimately return early when the guild already has
# the Betis seed marker. That used to skip league_teams if the table was created
# later by the dynamic admin/team patch, leaving a loaded roster but no selectable
# club. Keep the roster migration intact and always repair the catalog entry.
_original_sync_connection = base._sync_connection


def _sync_connection_with_team_catalog(runtime, conn):
    changed = _original_sync_connection(runtime, conn)
    _ensure_betis_team(runtime, conn)
    return changed


base._sync_connection = _sync_connection_with_team_catalog

BETIS_ROSTER = base.BETIS_ROSTER
OVR_BY_PLAYER = {name: rating for name, _position, rating in BETIS_ROSTER}

print(
    "AJAP Betis OVR actualizado: promedio simple de 3 stats por posición • "
    f"{len(BETIS_ROSTER)} jugadores • selector asegurado"
)
