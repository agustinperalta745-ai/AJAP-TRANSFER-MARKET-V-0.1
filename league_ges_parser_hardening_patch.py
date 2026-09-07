"""Hardening for the live GES markup used by AJPA.

The current GES league contains clubs outside the historical hard-coded AJPA
catalog, so GES names must be accepted as authoritative. The scorer page also
contains a second table with general statistics; only the actual
Nombre/Equipo/Total table is allowed to become scorer data.
"""

from __future__ import annotations

import re

import league_ges_manual_sync_patch as ges


_BASE_CANONICAL_TEAM = ges._canonical_team


def _canonical_team_live(label: str) -> str | None:
    clean = ges._clean_ges_team(label)
    if not clean:
        return None
    mapped = _BASE_CANONICAL_TEAM(clean)
    # A club does not need to be present in the historical Python tuple to be
    # valid. The current competition in GES is the source of truth.
    return mapped or clean


def _parse_scorers_live(tables):
    warnings: list[str] = []
    found: dict[tuple[str, str], dict] = {}

    for table in tables:
        if not table:
            continue
        heading = ges._norm(" ".join(cell for row in table[:3] for cell in row))
        # Reject GES' "Estadísticas generales" table (Partidos Disputados,
        # Total Goles, percentages, etc.). The scorer table is explicitly
        # Nombre | Equipo | Total/Goles.
        if not (
            ("nombre" in heading or "jugador" in heading)
            and "equipo" in heading
            and ("total" in heading or "goles" in heading)
        ):
            continue

        for row in table:
            cells = [re.sub(r"\s+", " ", str(cell or "")).strip() for cell in row]
            cells = [cell for cell in cells if cell]
            if len(cells) < 3:
                continue
            norm_cells = [ges._norm(cell) for cell in cells]
            if (
                ("nombre" in norm_cells or "jugador" in norm_cells)
                and "equipo" in norm_cells
            ):
                continue

            goal_index = None
            goals = None
            for index in range(len(cells) - 1, -1, -1):
                value = ges._to_int(cells[index])
                if value is not None:
                    goal_index = index
                    goals = value
                    break
            if goal_index is None or goals is None or goals <= 0 or goals > 200:
                continue

            textual = [
                cell for index, cell in enumerate(cells)
                if index != goal_index and ges._to_int(cell) is None
            ]
            if len(textual) < 2:
                continue
            player = textual[0].strip()
            raw_team = textual[1].strip()
            if not player or not raw_team:
                continue
            team = _canonical_team_live(raw_team) or ges._clean_ges_team(raw_team)
            key = (ges._norm(player), ges._norm(team))
            found[key] = {
                "player": player[:100],
                "team": team[:100],
                "goals": int(goals),
            }

    rows = sorted(found.values(), key=lambda row: (-row["goals"], ges._norm(row["player"])))
    if not rows:
        raise RuntimeError("GES no devolvió una tabla de goleadores reconocible.")
    return rows, warnings


ges._canonical_team = _canonical_team_live
ges._parse_scorers = _parse_scorers_live
print("AJPA GES: parser live endurecido (clubes dinámicos + goleadores aislados)")
