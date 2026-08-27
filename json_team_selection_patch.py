"""Show only JSON-backed clubs in the first team-selection menu.

This is intentionally a UI filter only. Legacy seeded/admin-created clubs stay in
SQLite so old assignments, transfers and history are not destroyed, but a user
without a club can only choose teams whose source JSON exists in data/ and whose
canonical club is active in the current guild DB.
"""

from __future__ import annotations

import json
from pathlib import Path

import discord

import guild_isolation_patch as guild_isolation
import team_assignment as teams


APP = None
DATA_DIR = Path(__file__).resolve().parent / "data"


def _source_team_names():
    names = []
    for path in sorted(DATA_DIR.glob("*.json"), key=lambda item: item.name.casefold()):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            print(f"WARNING AJAP selector JSON: no se pudo leer {path.name}: {exc}")
            continue
        raw = str(payload.get("equipo", "") or "").strip()
        players = payload.get("jugadores")
        if raw and isinstance(players, list) and players:
            names.append(raw)
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


def _json_team_rows():
    if APP is None:
        return []

    sources = _source_team_names()
    if not sources:
        return []

    rows = []
    used = set()
    with APP.db() as conn:
        for source_name in sources:
            row = None
            for candidate in _candidate_names(source_name):
                row = conn.execute(
                    """
                    SELECT name, country
                    FROM league_teams
                    WHERE active = 1 AND name = ? COLLATE NOCASE
                    LIMIT 1
                    """,
                    (candidate,),
                ).fetchone()
                if row:
                    break
            if not row:
                continue

            club = str(row["name"] or "").strip()
            key = club.casefold()
            if not club or key in used:
                continue
            used.add(key)
            rows.append({"name": club, "country": str(row["country"] or "Sin definir")})

    rows.sort(key=lambda row: row["name"].casefold())
    return rows


def _country_emoji(country: str) -> str:
    raw = str(country or "").strip().casefold()
    if "argentin" in raw:
        return "🇦🇷"
    if "fran" in raw:
        return "🇫🇷"
    if "espa" in raw:
        return "🇪🇸"
    if "ital" in raw:
        return "🇮🇹"
    if "inglat" in raw or "england" in raw:
        # England subdivision flag: U+1F3F4 + tag "gbeng" + cancel tag.
        # Written explicitly so it cannot be reduced to the plain black flag.
        return "\U0001F3F4\U000E0067\U000E0062\U000E0065\U000E006E\U000E0067\U000E007F"
    if "portugal" in raw:
        return "🇵🇹"
    if "países bajos" in raw or "paises bajos" in raw or "holanda" in raw:
        return "🇳🇱"
    return "⚽"


def _json_welcome_embed():
    rows = _json_team_rows()
    occupied = {str(row["name"]).casefold() for row in teams.assignments()}
    embed = discord.Embed(
        title="⚽ Elegí tu equipo",
        description=(
            "Seleccioná el club que vas a manejar en **AJAP Transfer Market**.\n\n"
            "Solo aparecen equipos con plantilla cargada desde JSON."
        ),
    )

    if not rows:
        embed.description = "Todavía no hay equipos con JSON cargado disponibles."
        return embed

    for row in rows[:25]:
        club = row["name"]
        status = "🔒 Ya asignado" if club.casefold() in occupied else "✅ Disponible"
        embed.add_field(
            name=f"{_country_emoji(row['country'])} {club}",
            value=f"{row['country']} • {status}",
            inline=False,
        )

    embed.set_footer(text=f"{len(rows)} equipo(s) con JSON • 1 equipo por cuenta")
    return embed


def _install_json_only_selector():
    BaseTeamSelect = teams.TeamSelect

    class JsonOnlyTeamSelect(BaseTeamSelect):
        def __init__(self):
            rows = _json_team_rows()[:25]
            occupied = {str(row["name"]).casefold() for row in teams.assignments()}
            options = [
                discord.SelectOption(
                    label=row["name"][:100],
                    description=(
                        f"{row['country']} • "
                        f"{'🔒 Ya asignado' if row['name'].casefold() in occupied else '✅ Disponible'}"
                    )[:100],
                    value=row["name"],
                    emoji=_country_emoji(row["country"]),
                )
                for row in rows
            ]
            discord.ui.Select.__init__(
                self,
                placeholder="Elegí tu equipo",
                min_values=1,
                max_values=1,
                options=options,
            )

    class JsonOnlyTeamChoiceView(discord.ui.View):
        def __init__(self):
            super().__init__(timeout=300)
            if _json_team_rows():
                self.add_item(JsonOnlyTeamSelect())

    teams.TeamSelect = JsonOnlyTeamSelect
    teams.TeamChoiceView = JsonOnlyTeamChoiceView
    teams.welcome_embed = _json_welcome_embed


def apply_json_team_selection_patch(runtime, bot):
    global APP
    APP = runtime
    if getattr(runtime, "_ajap_json_team_selection_patch", False):
        return

    _install_json_only_selector()
    runtime._ajap_json_team_selection_patch = True
    print(
        "AJAP selector inicial filtrado por JSON activo: "
        + ", ".join(row["name"] for row in _json_team_rows())
    )


_original_apply_guild_isolation_patch = guild_isolation.apply_guild_isolation_patch


def _apply_guild_isolation_then_json_selector(runtime, bot):
    _original_apply_guild_isolation_patch(runtime, bot)
    apply_json_team_selection_patch(runtime, bot)


if not getattr(
    guild_isolation.apply_guild_isolation_patch,
    "_ajap_json_team_selection_wrapped",
    False,
):
    _apply_guild_isolation_then_json_selector._ajap_json_team_selection_wrapped = True
    guild_isolation.apply_guild_isolation_patch = _apply_guild_isolation_then_json_selector
