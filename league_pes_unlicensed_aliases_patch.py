"""Official AJAP mappings for PES 6 unlicensed club names.

Players may use AJAP's kitserver (real club names/badges) or stock PES 6 names.
Both forms must resolve to the same official league club.  The canonical AJAP
names already live in league.TEAMS; this module only adds the stock-PES aliases.
"""

import league_automation_patch as league

PES6_UNLICENSED_ALIASES = {
    "middlebrook": "Bolton Wanderers",
    "teesside": "Middlesbrough",
    "west london white": "Fulham",
    # Defensive OCR spelling variant seen/typed during setup.
    "west lindo white": "Fulham",
    "west midlands village": "Aston Villa",
    "merseyside blue": "Everton",
    "man blue": "Manchester City",
    "north east london": "Tottenham Hotspur",
    "east london": "West Ham United",
}

league.ALIASES.update(PES6_UNLICENSED_ALIASES)

print(
    "AJAP Liga: aliases PES6 sin licencia activos: "
    + ", ".join(f"{alias}->{club}" for alias, club in PES6_UNLICENSED_ALIASES.items())
)
