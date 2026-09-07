"""Hardening for the live GES markup used by AJPA.

The current GES league contains clubs outside the historical hard-coded AJPA
catalog, so GES names must be accepted as authoritative. The scorer page also
contains a second table with general statistics; only the actual
Nombre/Equipo/Total table is allowed to become scorer data.

GES' CuadranteResultados page is a matrix: the local club is the row header,
the visitor is the column header and each played cell contains the score. The
legacy parser expected a flat ``Local | score | Visitante`` row, so it silently
missed matches from the configured Resultados URL. The live parser below reads
the matrix first and keeps the old parser only as a compatibility fallback.
"""

from __future__ import annotations

import re

import league_ges_manual_sync_patch as ges


_BASE_CANONICAL_TEAM = ges._canonical_team
_BASE_PARSE_MATCHES = ges._parse_matches


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


def _parse_matches_live(tables):
    """Parse GES CuadranteResultados matrices without treating pending cells as games."""
    warnings: list[str] = []
    found: dict[tuple[str, str], dict] = {}
    score_re = re.compile(r"^\s*(\d{1,2})\s*[-–—]\s*(\d{1,2})\s*$")

    for table in tables:
        if len(table) < 2:
            continue

        normalized = [
            [re.sub(r"\s+", " ", str(cell or "")).strip() for cell in row]
            for row in table
        ]

        # Pick the header row immediately associated with the result matrix.
        # It has no score cells and the following rows contain score cells.
        header_index = None
        best_width = 0
        for index, row in enumerate(normalized[:-1]):
            nonempty = [cell for cell in row if cell]
            if len(nonempty) < 2 or any(score_re.match(cell) for cell in nonempty):
                continue
            following = normalized[index + 1:index + 5]
            score_count = sum(
                1 for candidate in following for cell in candidate if score_re.match(cell)
            )
            if score_count <= 0:
                continue
            if len(row) > best_width:
                header_index = index
                best_width = len(row)

        if header_index is None:
            continue

        header = normalized[header_index]
        for row in normalized[header_index + 1:]:
            score_positions = [
                index for index, cell in enumerate(row) if score_re.match(cell)
            ]
            if not score_positions:
                continue

            # GES places the local team before the first result/pending cell.
            first_score = score_positions[0]
            raw_home = next((cell for cell in row[:first_score] if cell), "")
            if not raw_home:
                continue
            home = _canonical_team_live(raw_home)
            if not home:
                warnings.append(f"Equipo local sin vincular: {raw_home}")
                continue

            # Depending on GES markup, the top-left Local/Visitante cell can be
            # present in the header or represented by a span. Align columns by
            # the width difference so both variants map to the right visitor.
            offset = max(0, len(row) - len(header))
            for score_index in score_positions:
                header_index_for_score = score_index - offset
                if header_index_for_score < 0 or header_index_for_score >= len(header):
                    continue
                raw_away = header[header_index_for_score]
                if not raw_away:
                    continue
                norm_away = ges._norm(raw_away)
                if norm_away in {"visitante", "local", "visitante local", "local visitante"}:
                    continue
                away = _canonical_team_live(raw_away)
                if not away or ges._norm(home) == ges._norm(away):
                    continue

                score = score_re.match(row[score_index])
                if score is None:
                    continue
                found[(ges._norm(home), ges._norm(away))] = {
                    "home_team": home,
                    "away_team": away,
                    "home_goals": int(score.group(1)),
                    "away_goals": int(score.group(2)),
                }

    if found:
        return list(found.values()), list(dict.fromkeys(warnings))

    # Compatibility with any GES page/layout that still exposes flat match rows.
    return _BASE_PARSE_MATCHES(tables)


ges._canonical_team = _canonical_team_live
ges._parse_matches = _parse_matches_live
ges._parse_scorers = _parse_scorers_live
print("AJPA GES: parser live endurecido (clubes dinámicos + cuadrante de resultados + goleadores aislados)")
