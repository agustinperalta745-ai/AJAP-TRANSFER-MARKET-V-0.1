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

    # PES 6 can show licensed/DB club names or its default fake names depending
    # on the database installed by each player. Result recognition must resolve
    # both forms to the same official AJPA club before validating the screenshot.
    league.ALIASES.update(
        {
            "monaco": "AS Monaco",
            "as monaco": "AS Monaco",
            "feyenoord": "Feyenoord",

            # PES default / unlicensed names used by AJPA players.
            "middlebrook": "Bolton Wanderers",
            "teesside": "Middlesbrough",
            "west lindo white": "Fulham",
            "west london white": "Fulham",
            "west midlands village": "Aston Villa",
            "merseyside blue": "Everton",
            "man blue": "Manchester City",
            "north east london": "Tottenham Hotspur",
        }
    )
    print(
        "AJAP Liga: catálogo actualizado • nombres oficiales + aliases PES por defecto "
        "• AS Monaco/Feyenoord activos • Celta/AS Roma retirados"
    )


# This module is imported by the final result-reader bootstrap. Apply immediately
# so every reader built afterwards sees the same active club catalog.
apply_league_team_catalog_patch()
