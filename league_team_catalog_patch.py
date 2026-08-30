"""Keep the result bot team catalog aligned with the active AJPA club set."""

from __future__ import annotations


def apply_league_team_catalog_patch() -> None:
    import league_automation_patch as league

    retired = {"celta de vigo", "as roma"}
    league.TEAMS[:] = [
        name for name in league.TEAMS
        if str(name).strip().casefold() not in retired
    ]
    for club in ("AS Monaco", "Feyenoord"):
        if not any(str(name).casefold() == club.casefold() for name in league.TEAMS):
            league.TEAMS.append(club)

    league.ALIASES.update(
        {
            "monaco": "AS Monaco",
            "as monaco": "AS Monaco",
            "feyenoord": "Feyenoord",
        }
    )
    print("AJAP Liga: catálogo de resultados actualizado • AS Monaco + Feyenoord activos • Celta/AS Roma retirados")
