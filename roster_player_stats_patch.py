"""Player detail selector inside MI CLUB -> PLANTILLA.

After choosing an OVR range, managers can select any player in that range and
open a full PES 6 card. The card reads the persisted pes6_player_attributes data
(imported from the team's JSON/source dataset) instead of inventing values from
AJPA OVR.
"""

from __future__ import annotations

import discord

import lyon_test_seed as roster


STAT_GROUPS = (
    (
        "⚽ Ataque y definición",
        (
            ("attack", "Ataque"),
            ("aggression", "Agresividad"),
            ("shot_accuracy", "Precisión de tiro"),
            ("shot_power", "Potencia de tiro"),
            ("shot_technique", "Técnica de tiro"),
            ("free_kick_accuracy", "Tiros libres"),
            ("curling", "Efecto"),
            ("header", "Cabeceo"),
            ("technique", "Técnica"),
        ),
    ),
    (
        "🎯 Pase y regate",
        (
            ("dribble_accuracy", "Precisión de regate"),
            ("dribble_speed", "Velocidad de regate"),
            ("short_pass_accuracy", "Precisión pase corto"),
            ("short_pass_speed", "Velocidad pase corto"),
            ("long_pass_accuracy", "Precisión pase largo"),
            ("long_pass_speed", "Velocidad pase largo"),
        ),
    ),
    (
        "⚡ Físico y movilidad",
        (
            ("body_balance", "Equilibrio"),
            ("stamina", "Resistencia"),
            ("top_speed", "Velocidad máxima"),
            ("acceleration", "Aceleración"),
            ("response", "Respuesta"),
            ("agility", "Agilidad"),
            ("jump", "Salto"),
        ),
    ),
    (
        "🛡️ Defensa y mentalidad",
        (
            ("defence", "Defensa"),
            ("mentality", "Mentalidad"),
            ("teamwork", "Trabajo en equipo"),
            ("gk_skills", "Cualidad de arquero"),
        ),
    ),
    (
        "🦶 Otros datos PES 6",
        (
            ("injury_resistance", "Resistencia a lesiones"),
            ("weak_foot_usage", "Uso de pierna mala"),
            ("weak_foot_accuracy", "Precisión pierna mala"),
        ),
    ),
)


def _fmt_money(value):
    if value is None:
        return "Sin definir"
    try:
        return f"${int(value):,}".replace(",", ".")
    except (TypeError, ValueError):
        return str(value)


def _table_exists(conn, table: str) -> bool:
    return bool(
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
            (table,),
        ).fetchone()
    )


def _attributes(player_id: int):
    app = roster.APP
    if app is None:
        return None, []

    with app.db() as conn:
        if not _table_exists(conn, "pes6_player_attributes"):
            return None, []
        attrs = conn.execute(
            "SELECT * FROM pes6_player_attributes WHERE player_id = ? LIMIT 1",
            (int(player_id),),
        ).fetchone()

        abilities = []
        if _table_exists(conn, "pes6_player_special_abilities"):
            abilities = [
                str(row["ability"])
                for row in conn.execute(
                    """
                    SELECT ability
                    FROM pes6_player_special_abilities
                    WHERE player_id = ?
                    ORDER BY ability COLLATE NOCASE
                    """,
                    (int(player_id),),
                ).fetchall()
            ]
    return attrs, abilities


def _group_text(attrs, definitions):
    if not attrs:
        return None
    available = []
    keys = set(attrs.keys())
    for column, label in definitions:
        if column not in keys or attrs[column] is None:
            continue
        value = attrs[column]
        available.append(f"**{label}:** {value}")
    return "\n".join(available) if available else None


def player_stats_embed(player):
    app = roster.APP
    attrs, abilities = _attributes(int(player["id"]))
    rating = player["rating"] if "rating" in player.keys() else None
    minimum = player["min_sale_value"] if "min_sale_value" in player.keys() else None

    embed = discord.Embed(
        title=f"📊 {player['name']} • PES 6",
        description="Estadísticas originales guardadas desde el JSON/dataset del equipo.",
    )
    embed.add_field(name="🆔 ID", value=f"`{app.player_code(player['id'])}`", inline=True)
    embed.add_field(name="📍 Posición", value=player["position"], inline=True)
    embed.add_field(
        name="⭐ OVR AJPA",
        value=str(rating) if rating is not None else "Sin cargar",
        inline=True,
    )
    embed.add_field(name="🏟️ Club", value=player["club"], inline=True)
    embed.add_field(name="💰 Valor mínimo", value=_fmt_money(minimum), inline=True)

    if not attrs:
        embed.add_field(
            name="📂 Estadísticas PES 6",
            value="Este jugador todavía no tiene estadísticas de JSON/PES 6 guardadas.",
            inline=False,
        )
        embed.set_footer(text="No se calculan ni inventan atributos desde el OVR")
        return embed

    for title, definitions in STAT_GROUPS:
        text = _group_text(attrs, definitions)
        if text:
            embed.add_field(name=title, value=text, inline=False)

    if abilities:
        ability_text = " • ".join(abilities)
        if len(ability_text) > 1000:
            ability_text = ability_text[:997] + "..."
        embed.add_field(
            name="✨ Habilidades especiales",
            value=ability_text,
            inline=False,
        )

    source = attrs["source"] if "source" in attrs.keys() and attrs["source"] else "PES 6 / JSON"
    embed.set_footer(text=f"Fuente: {source}")
    return embed


class RosterPlayerSelect(discord.ui.Select):
    def __init__(
        self,
        club: str,
        players,
        range_label: str,
        min_ovr: int,
        max_ovr: int,
        group_index: int = 0,
    ):
        self.club = club
        self.range_label = range_label
        self.min_ovr = int(min_ovr)
        self.max_ovr = int(max_ovr)

        options = []
        for player in players:
            rating = roster.player_rating(player)
            details = [str(player["position"])]
            if rating >= 0:
                details.append(f"OVR {rating}")
            options.append(
                discord.SelectOption(
                    label=str(player["name"])[:100],
                    description=" • ".join(details)[:100],
                    value=str(player["id"]),
                )
            )

        super().__init__(
            placeholder=(
                "Elegí un jugador para ver sus estadísticas"
                if group_index == 0
                else f"Más jugadores • grupo {group_index + 1}"
            ),
            min_values=1,
            max_values=1,
            options=options,
            row=group_index,
        )

    async def callback(self, interaction: discord.Interaction):
        app = roster.APP
        current_team = app.club_de(interaction.user.id)
        if not current_team or current_team.casefold() != self.club.casefold():
            await interaction.response.send_message(
                "⛔ Este plantel ya no está vinculado a tu cuenta.",
                ephemeral=True,
            )
            return

        player = app.jugador_por_id(int(self.values[0]))
        if not player or str(player["club"]).casefold() != self.club.casefold():
            await interaction.response.send_message(
                "⚠️ Ese jugador ya no pertenece a este plantel.",
                ephemeral=True,
            )
            return

        await interaction.response.edit_message(
            embed=player_stats_embed(player),
            view=PlayerStatsBackView(
                self.club,
                self.range_label,
                self.min_ovr,
                self.max_ovr,
            ),
        )


class BackToRosterRange(discord.ui.Button):
    def __init__(self, club: str, range_label: str, min_ovr: int, max_ovr: int):
        super().__init__(
            label="Volver al rango",
            emoji="⬅️",
            style=discord.ButtonStyle.secondary,
            row=0,
            custom_id="ajpa_roster_stats_back_range",
        )
        self.club = club
        self.range_label = range_label
        self.min_ovr = int(min_ovr)
        self.max_ovr = int(max_ovr)

    async def callback(self, interaction: discord.Interaction):
        app = roster.APP
        current_team = app.club_de(interaction.user.id)
        if not current_team or current_team.casefold() != self.club.casefold():
            await interaction.response.send_message(
                "⛔ Este plantel ya no está vinculado a tu cuenta.",
                ephemeral=True,
            )
            return
        players = roster.players_in_range(self.club, self.min_ovr, self.max_ovr)
        await interaction.response.edit_message(
            embed=roster.rated_plantel_embed(
                self.club,
                self.min_ovr,
                self.max_ovr,
                self.range_label,
            ),
            view=RosterRangePlayersView(
                self.club,
                self.range_label,
                self.min_ovr,
                self.max_ovr,
                players,
            ),
        )


class PlayerStatsBackView(discord.ui.View):
    def __init__(self, club: str, range_label: str, min_ovr: int, max_ovr: int):
        super().__init__(timeout=300)
        self.add_item(BackToRosterRange(club, range_label, min_ovr, max_ovr))


class BackToRosterRanges(discord.ui.Button):
    def __init__(self, club: str, row: int):
        super().__init__(
            label="Volver a rangos",
            emoji="📊",
            style=discord.ButtonStyle.secondary,
            row=row,
            custom_id="ajpa_roster_stats_back_ranges",
        )
        self.club = club

    async def callback(self, interaction: discord.Interaction):
        app = roster.APP
        current_team = app.club_de(interaction.user.id)
        if not current_team or current_team.casefold() != self.club.casefold():
            await interaction.response.send_message(
                "⛔ Este plantel ya no está vinculado a tu cuenta.",
                ephemeral=True,
            )
            return
        await interaction.response.edit_message(
            embed=roster.plantel_ranges_embed(self.club),
            view=roster.PlantelOVRView(self.club),
        )


class RosterRangePlayersView(discord.ui.View):
    def __init__(self, club: str, range_label: str, min_ovr: int, max_ovr: int, players):
        super().__init__(timeout=300)
        groups = [players[index:index + 25] for index in range(0, len(players), 25)]
        for group_index, group in enumerate(groups[:4]):
            if group:
                self.add_item(
                    RosterPlayerSelect(
                        club,
                        group,
                        range_label,
                        min_ovr,
                        max_ovr,
                        group_index,
                    )
                )
        self.add_item(BackToRosterRanges(club, row=min(len(groups), 4)))


async def _range_callback(self, interaction: discord.Interaction):
    app = roster.APP
    current_team = app.club_de(interaction.user.id)
    if not current_team or current_team.casefold() != self.club.casefold():
        await interaction.response.send_message(
            "⛔ Este plantel ya no está vinculado a tu cuenta.",
            ephemeral=True,
        )
        return

    players = roster.players_in_range(self.club, self.min_ovr, self.max_ovr)
    await interaction.response.edit_message(
        embed=roster.rated_plantel_embed(
            self.club,
            self.min_ovr,
            self.max_ovr,
            self.range_label,
        ),
        view=RosterRangePlayersView(
            self.club,
            self.range_label,
            self.min_ovr,
            self.max_ovr,
            players,
        ),
    )


# PlantelOVRView already creates OVRRangeButton instances. Replacing the callback
# method here upgrades every existing/future range button without rebuilding the
# market view or changing the publish-player flow.
roster.OVRRangeButton.callback = _range_callback
roster.RosterRangePlayersView = RosterRangePlayersView
roster.player_stats_embed = player_stats_embed

print("AJPA plantilla: selector de jugador + estadísticas completas PES6/JSON activo")
