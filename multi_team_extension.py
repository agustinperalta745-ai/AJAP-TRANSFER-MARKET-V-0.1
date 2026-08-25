"""Permanent AJAP expansion for additional fixed teams.

This module extends the original Lyon assignment layer without resetting any
existing club assignment or roster. Each roster is seeded once on the persistent
SQLite database so future transfers/restarts do not restore moved players.
"""

import discord
import team_assignment as teams

VILLARREAL = "Villarreal"
VILLARREAL_ROSTER = [
    ("Juan Román Riquelme", "AMF", 90),
    ("Diego Forlán", "CF/SS", 86),
    ("Marcos Senna", "DMF/CMF", 85),
    ("Robert Pirès", "LMF/AMF", 84),
    ("Nihat Kahveci", "CF/SS", 84),
    ("Gonzalo Rodríguez", "CB", 83),
    ("Cani", "RMF/AMF", 82),
    ("Alessio Tacchinardi", "DMF/CMF", 81),
    ("Sebastián Viera", "GK", 80),
    ("Rodolfo Arruabarrena", "LB/CB", 80),
    ("Fabricio Fuentes", "CB", 80),
    ("Guillermo Franco", "CF", 79),
    ("Leandro Somoza", "DMF/CMF", 79),
    ("Javi Venta", "RB", 78),
    ("Juan Manuel Peña", "CB", 78),
    ("Josico", "DMF/CMF", 78),
    ("Pascal Cygan", "CB", 77),
    ("José Enrique", "LB", 77),
    ("José Mari", "CF/SS", 77),
    ("Josemi", "RB/CB", 76),
    ("Quique Álvarez", "CB", 76),
    ("Mariano Barbosa", "GK", 75),
    ("Óscar López", "LB/CB", 72),
    ("Marquitos", "RMF/SMF", 72),
    ("Jonathan Pereira", "CF/SS", 69),
    ("Juan Carlos", "GK", 64),
]


def _flag(country: str) -> str:
    return {"Francia": "🇫🇷", "España": "🇪🇸"}.get(country, "⚽")


def enable_additional_teams():
    """Make Villarreal selectable before the assignment patch is installed."""
    if not any(name.casefold() == VILLARREAL.casefold() for name, _ in teams.OFFICIAL_TEAMS):
        teams.OFFICIAL_TEAMS.append((VILLARREAL, "España"))
    teams.OFFICIAL[VILLARREAL.casefold()] = VILLARREAL

    def welcome_embed():
        occupied = {row["name"].casefold() for row in teams.assignments()}
        embed = discord.Embed(
            title="⚽ Elegí tu equipo",
            description=(
                "Seleccioná el club que vas a manejar en **AJAP Transfer Market**.\n\n"
                "La elección queda guardada en tu cuenta. Solo un administrador puede desvincularla."
            ),
        )
        for name, country in teams.OFFICIAL_TEAMS:
            status = "🔒 Ya asignado" if name.casefold() in occupied else "✅ Disponible"
            embed.add_field(
                name=f"{_flag(country)} {name}",
                value=f"{country} • {status}",
                inline=False,
            )
        embed.set_footer(text="1 equipo por cuenta • Las plantillas quedan guardadas permanentemente")
        return embed

    def assignments_embed():
        rows = teams.assignments()
        embed = discord.Embed(title="👥 Asignaciones de equipos")
        if not rows:
            embed.description = "Todavía no hay equipos asignados."
            return embed
        for row in rows:
            club = teams.official_name(row["name"])
            embed.add_field(name=club, value=f"<@{row['user_id']}>", inline=True)
        embed.set_footer(text=f"{len(rows)}/{len(teams.OFFICIAL_TEAMS)} equipo(s) asignado(s)")
        return embed

    class MultiTeamSelect(discord.ui.Select):
        def __init__(self):
            occupied = {row["name"].casefold() for row in teams.assignments()}
            options = []
            for name, country in teams.OFFICIAL_TEAMS:
                status = "🔒 Ya asignado" if name.casefold() in occupied else "✅ Disponible"
                options.append(
                    discord.SelectOption(
                        label=name,
                        description=f"{country} • {status}"[:100],
                        value=name,
                        emoji=_flag(country),
                    )
                )
            super().__init__(
                placeholder="Elegí tu equipo",
                min_values=1,
                max_values=1,
                options=options,
            )

        async def callback(self, interaction: discord.Interaction):
            current = teams.club_de(interaction.user.id)
            if current:
                await interaction.response.send_message(
                    f"⚠️ Ya tenés asignado **{current}**. Solo un admin puede revertirlo.",
                    ephemeral=True,
                )
                return

            ok, result = teams.assign_team(interaction.user.id, self.values[0])
            if not ok:
                await interaction.response.send_message(f"⚠️ {result}", ephemeral=True)
                return

            jugadores = teams.APP.jugadores_de_club(result, 50)
            await interaction.response.edit_message(
                embed=discord.Embed(
                    title=f"✅ {result} asignado",
                    description=(
                        f"Desde ahora manejás **{result}**.\n\n"
                        f"Plantilla cargada: **{len(jugadores)} jugadores**.\n"
                        "Ya podés entrar a **Mi club** o **Publicar jugador**."
                    ),
                ),
                view=teams.APP.MercadoView(),
            )

    class GenericConfirmUnlinkView(discord.ui.View):
        def __init__(self, user_id, team):
            super().__init__(timeout=120)
            self.user_id = int(user_id)
            self.team = team

        @discord.ui.button(
            label="Desvincular equipo",
            emoji="↩️",
            style=discord.ButtonStyle.danger,
        )
        async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
            if not teams.APP.es_admin(interaction):
                await interaction.response.send_message("⛔ Solo admins.", ephemeral=True)
                return
            current = teams.club_de(self.user_id)
            if not current or current.casefold() != self.team.casefold():
                await interaction.response.send_message("⚠️ Esa asignación ya cambió.", ephemeral=True)
                return
            removed = teams.unlink_team(self.user_id, interaction.user.id)
            await interaction.response.edit_message(
                embed=discord.Embed(
                    title="↩️ Asignación revertida",
                    description=(
                        f"<@{self.user_id}> ya no tiene **{removed}**.\n\n"
                        f"✅ La plantilla de **{removed}** quedó intacta. "
                        "Al abrir `/mercado`, podrá elegir un equipo disponible nuevamente."
                    ),
                ),
                view=None,
            )

        @discord.ui.button(
            label="Cancelar",
            emoji="✖️",
            style=discord.ButtonStyle.secondary,
        )
        async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
            if not teams.APP.es_admin(interaction):
                await interaction.response.send_message("⛔ Solo admins.", ephemeral=True)
                return
            await interaction.response.edit_message(content="Cancelado.", embed=None, view=None)

    teams.welcome_embed = welcome_embed
    teams.assignments_embed = assignments_embed
    teams.TeamSelect = MultiTeamSelect
    teams.ConfirmUnlinkView = GenericConfirmUnlinkView


def seed_additional_rosters(app):
    """Seed Villarreal once, using the exact same OVR -> minimum-price curve as Lyon."""
    from lyon_test_seed import minimum_for_rating

    marker = "villarreal_pes6_v1"
    with app.db() as conn:
        app.add_column_if_missing(conn, "roster_players", "rating", "INTEGER")
        app.add_column_if_missing(conn, "roster_players", "min_sale_value", "INTEGER")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS seed_state (
                key TEXT PRIMARY KEY,
                applied_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        seeded = conn.execute("SELECT 1 FROM seed_state WHERE key = ?", (marker,)).fetchone()
        if seeded:
            return 0

        for name, position, rating in VILLARREAL_ROSTER:
            conn.execute(
                """
                INSERT INTO roster_players
                    (name, position, club, added_by, rating, min_sale_value, updated_at)
                VALUES (?, ?, ?, NULL, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(name) DO UPDATE SET
                    position = excluded.position,
                    club = excluded.club,
                    rating = excluded.rating,
                    min_sale_value = excluded.min_sale_value,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (name, position, VILLARREAL, rating, minimum_for_rating(rating)),
            )

        conn.execute("INSERT INTO seed_state (key) VALUES (?)", (marker,))
    return len(VILLARREAL_ROSTER)
