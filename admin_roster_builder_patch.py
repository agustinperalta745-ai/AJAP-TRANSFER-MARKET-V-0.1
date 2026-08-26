"""Admin roster/team builder for AJAP Transfer Market.

Adds a Staff flow to:
- create teams from Discord,
- load players by selecting club and primary position,
- request exactly three role-specific stats,
- calculate OVR as the rounded arithmetic mean,
- persist the calculation inputs for auditing,
- feed the existing AJAP market-value/clause economy from the calculated OVR.

It also makes the team selector read active teams from league_teams so teams created
from Discord remain selectable after restarts and are isolated per guild database.
"""

from __future__ import annotations

import discord

import guild_isolation_patch as guild_isolation
import staff_admin_organized_patch as staff
import team_assignment as teams


APP = None
BOT = None
INITIAL_TEAM_BUDGET = 10_000_000

POSITION_STATS = {
    "GK": ("Reflejos", "Atajadas", "Colocación"),
    "CB": ("Defensa", "Fuerza", "Juego aéreo"),
    "LB": ("Defensa", "Velocidad", "Resistencia"),
    "RB": ("Defensa", "Velocidad", "Resistencia"),
    "DMF": ("Defensa", "Pase", "Resistencia"),
    "CMF": ("Pase", "Técnica", "Resistencia"),
    "AMF": ("Pase", "Regate", "Tiro"),
    "LMF": ("Velocidad", "Regate", "Pase"),
    "RMF": ("Velocidad", "Regate", "Pase"),
    "WF": ("Velocidad", "Regate", "Tiro"),
    "SS": ("Regate", "Pase", "Tiro"),
    "CF": ("Tiro", "Ataque", "Juego aéreo"),
}


def _install_preserving_team_schema():
    """Keep admin-created teams active when the base team-assignment patch starts."""
    if getattr(teams.ensure_schema, "_ajap_preserve_custom_teams", False):
        return

    def ensure_schema():
        with teams.db() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS league_teams (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL COLLATE NOCASE UNIQUE,
                    country TEXT NOT NULL,
                    active INTEGER NOT NULL DEFAULT 1,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS club_assignment_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    club TEXT NOT NULL,
                    action TEXT NOT NULL,
                    actor_id INTEGER,
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
            # Reactivate/update the built-in catalog, but never deactivate teams
            # created by Staff from Discord.
            for name, country in teams.OFFICIAL_TEAMS:
                conn.execute(
                    """
                    INSERT INTO league_teams (name, country, active)
                    VALUES (?, ?, 1)
                    ON CONFLICT(name) DO UPDATE SET
                        country = excluded.country,
                        active = 1
                    """,
                    (name, country),
                )

    ensure_schema._ajap_preserve_custom_teams = True
    teams.ensure_schema = ensure_schema


_install_preserving_team_schema()


def _fmt_money(value: int) -> str:
    return f"${int(value):,}".replace(",", ".")


def _calculate_ovr(values) -> int:
    return int(round(sum(int(value) for value in values) / 3))


def _ensure_schema():
    with APP.db() as conn:
        APP.add_column_if_missing(conn, "roster_players", "rating", "INTEGER")
        APP.add_column_if_missing(conn, "roster_players", "min_sale_value", "INTEGER")
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS league_teams (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL COLLATE NOCASE UNIQUE,
                country TEXT NOT NULL,
                active INTEGER NOT NULL DEFAULT 1,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS club_finances (
                club TEXT PRIMARY KEY COLLATE NOCASE,
                balance INTEGER NOT NULL DEFAULT 0,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS player_rating_inputs (
                player_id INTEGER PRIMARY KEY,
                position_key TEXT NOT NULL,
                stat_1_name TEXT NOT NULL,
                stat_1_value INTEGER NOT NULL,
                stat_2_name TEXT NOT NULL,
                stat_2_value INTEGER NOT NULL,
                stat_3_name TEXT NOT NULL,
                stat_3_value INTEGER NOT NULL,
                calculated_ovr INTEGER NOT NULL,
                formula TEXT NOT NULL DEFAULT 'PROMEDIO_SIMPLE_3',
                created_by INTEGER,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );
            """
        )


def _active_teams():
    _ensure_schema()
    with APP.db() as conn:
        return conn.execute(
            """
            SELECT name, country
            FROM league_teams
            WHERE active = 1
            ORDER BY name COLLATE NOCASE
            """
        ).fetchall()


def _official_name(name):
    if not name:
        return None
    _ensure_schema()
    with APP.db() as conn:
        row = conn.execute(
            """
            SELECT name
            FROM league_teams
            WHERE active = 1 AND name = ? COLLATE NOCASE
            LIMIT 1
            """,
            (str(name).strip(),),
        ).fetchone()
    return row["name"] if row else None


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
        return "🏴"
    if "portugal" in raw:
        return "🇵🇹"
    if "países bajos" in raw or "paises bajos" in raw or "holanda" in raw:
        return "🇳🇱"
    return "⚽"


def _dynamic_welcome_embed():
    rows = _active_teams()
    occupied = {row["name"].casefold() for row in teams.assignments()}
    embed = discord.Embed(
        title="⚽ Elegí tu equipo",
        description=(
            "Seleccioná el club que vas a manejar en **AJAP Transfer Market**.\n\n"
            "La elección queda guardada en tu cuenta. Solo un administrador puede desvincularla."
        ),
    )
    if not rows:
        embed.description = "Todavía no hay equipos activos. Un administrador debe crear uno."
        return embed
    for row in rows[:25]:
        status = "🔒 Ya asignado" if row["name"].casefold() in occupied else "✅ Disponible"
        embed.add_field(
            name=f"{_country_emoji(row['country'])} {row['name']}",
            value=f"{row['country']} • {status}",
            inline=False,
        )
    if len(rows) > 25:
        embed.set_footer(text=f"Mostrando 25 de {len(rows)} equipos activos")
    else:
        embed.set_footer(text=f"{len(rows)} equipo(s) activo(s) • 1 equipo por cuenta")
    return embed


def _dynamic_assignments_embed():
    rows = teams.assignments()
    total = len(_active_teams())
    embed = discord.Embed(title="👥 Asignaciones de equipos")
    if not rows:
        embed.description = "Todavía no hay equipos asignados."
        embed.set_footer(text=f"0/{total} equipo(s) asignado(s)")
        return embed
    for row in rows[:25]:
        club = _official_name(row["name"]) or row["name"]
        embed.add_field(name=club, value=f"<@{row['user_id']}>", inline=True)
    embed.set_footer(text=f"{len(rows)}/{total} equipo(s) asignado(s)")
    return embed


def _install_dynamic_team_catalog():
    # Keep the already-patched callback chain (nickname + manager menu + DT role)
    # by subclassing the final selector class and overriding only option creation.
    BaseTeamSelect = teams.TeamSelect

    class DynamicTeamSelect(BaseTeamSelect):
        def __init__(self):
            rows = _active_teams()[:25]
            occupied = {row["name"].casefold() for row in teams.assignments()}
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

    class DynamicTeamChoiceView(discord.ui.View):
        def __init__(self):
            super().__init__(timeout=300)
            rows = _active_teams()
            if rows:
                self.add_item(DynamicTeamSelect())

    teams.official_name = _official_name
    teams.TeamSelect = DynamicTeamSelect
    teams.TeamChoiceView = DynamicTeamChoiceView
    teams.welcome_embed = _dynamic_welcome_embed
    teams.assignments_embed = _dynamic_assignments_embed


def _market_value_for_rating(rating: int) -> int:
    fn = getattr(APP, "market_value_for_rating", None)
    if callable(fn):
        return int(fn(rating))
    from lyon_test_seed import minimum_for_rating

    return int(minimum_for_rating(rating))


def _clause_value_for_player(player_row) -> int | None:
    fn = getattr(APP, "player_clause_value", None)
    if callable(fn):
        return int(fn(player_row))
    return None


def _parse_stat(raw: str, label: str) -> int:
    text = str(raw or "").strip()
    if not text.isdigit():
        raise ValueError(f"{label} debe ser un número entre 1 y 99.")
    value = int(text)
    if not 1 <= value <= 99:
        raise ValueError(f"{label} debe estar entre 1 y 99.")
    return value


class CreateTeamModal(discord.ui.Modal, title="Crear equipo"):
    name = discord.ui.TextInput(
        label="Nombre del equipo",
        placeholder="Ej: Newcastle United",
        max_length=60,
    )
    country = discord.ui.TextInput(
        label="País",
        placeholder="Ej: Inglaterra",
        max_length=40,
    )

    async def on_submit(self, interaction: discord.Interaction):
        if not APP.es_admin(interaction):
            await interaction.response.send_message("⛔ Solo administradores.", ephemeral=True)
            return

        name = self.name.value.strip()
        country = self.country.value.strip()
        if not name or not country:
            await interaction.response.send_message("⚠️ Nombre y país son obligatorios.", ephemeral=True)
            return

        _ensure_schema()
        with APP.db() as conn:
            existing = conn.execute(
                "SELECT id, active FROM league_teams WHERE name = ? COLLATE NOCASE LIMIT 1",
                (name,),
            ).fetchone()
            conn.execute(
                """
                INSERT INTO league_teams (name, country, active)
                VALUES (?, ?, 1)
                ON CONFLICT(name) DO UPDATE SET
                    country = excluded.country,
                    active = 1
                """,
                (name, country),
            )
            conn.execute(
                """
                INSERT OR IGNORE INTO club_finances (club, balance, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP)
                """,
                (name, INITIAL_TEAM_BUDGET),
            )

        embed = discord.Embed(
            title="✅ Equipo creado" if not existing else "✅ Equipo actualizado",
            description=f"**{name}** ya está habilitado en el selector de equipos.",
            color=discord.Color.green(),
        )
        embed.add_field(name="🌍 País", value=country, inline=True)
        embed.add_field(
            name="💰 Presupuesto inicial",
            value=_fmt_money(INITIAL_TEAM_BUDGET),
            inline=True,
        )
        embed.set_footer(text="Ahora podés cargar jugadores directamente desde PLANTELES.")
        await interaction.response.send_message(embed=embed, ephemeral=True)


class PlayerTeamSelect(discord.ui.Select):
    def __init__(self, rows):
        options = [
            discord.SelectOption(
                label=row["name"][:100],
                description=f"{row['country']} • elegir plantilla"[:100],
                value=row["name"],
                emoji=_country_emoji(row["country"]),
            )
            for row in rows[:25]
        ]
        super().__init__(
            placeholder="1/2 • Elegí el equipo",
            min_values=1,
            max_values=1,
            options=options,
        )

    async def callback(self, interaction: discord.Interaction):
        if not APP.es_admin(interaction):
            await interaction.response.send_message("⛔ Solo administradores.", ephemeral=True)
            return
        club = _official_name(self.values[0])
        if not club:
            await interaction.response.send_message("⚠️ Ese equipo ya no está activo.", ephemeral=True)
            return
        embed = discord.Embed(
            title=f"➕ Cargar jugador • {club}",
            description="2/2 • Elegí la **posición principal**. Después el bot pedirá las 3 estadísticas definidas para esa posición.",
        )
        await interaction.response.edit_message(embed=embed, view=PlayerPositionView(club))


class PlayerTeamView(discord.ui.View):
    def __init__(self, rows):
        super().__init__(timeout=300)
        self.add_item(PlayerTeamSelect(rows))


class PlayerPositionSelect(discord.ui.Select):
    def __init__(self, club: str):
        self.club = club
        options = [
            discord.SelectOption(
                label=position,
                description=" • ".join(stats)[:100],
                value=position,
            )
            for position, stats in POSITION_STATS.items()
        ]
        super().__init__(
            placeholder="2/2 • Elegí la posición",
            min_values=1,
            max_values=1,
            options=options,
        )

    async def callback(self, interaction: discord.Interaction):
        if not APP.es_admin(interaction):
            await interaction.response.send_message("⛔ Solo administradores.", ephemeral=True)
            return
        position = self.values[0]
        await interaction.response.send_modal(PlayerStatsModal(self.club, position))


class PlayerPositionView(discord.ui.View):
    def __init__(self, club: str):
        super().__init__(timeout=300)
        self.add_item(PlayerPositionSelect(club))


class PlayerStatsModal(discord.ui.Modal):
    def __init__(self, club: str, position: str):
        super().__init__(title=f"Cargar jugador • {position}")
        self.club = club
        self.position = position
        stat_names = POSITION_STATS[position]

        self.player_name = discord.ui.TextInput(
            label="Nombre del jugador",
            placeholder="Ej: Ronaldinho",
            max_length=60,
        )
        self.stat_1 = discord.ui.TextInput(
            label=f"{stat_names[0]} (1-99)",
            placeholder="Ej: 88",
            max_length=2,
        )
        self.stat_2 = discord.ui.TextInput(
            label=f"{stat_names[1]} (1-99)",
            placeholder="Ej: 84",
            max_length=2,
        )
        self.stat_3 = discord.ui.TextInput(
            label=f"{stat_names[2]} (1-99)",
            placeholder="Ej: 82",
            max_length=2,
        )
        self.add_item(self.player_name)
        self.add_item(self.stat_1)
        self.add_item(self.stat_2)
        self.add_item(self.stat_3)

    async def on_submit(self, interaction: discord.Interaction):
        if not APP.es_admin(interaction):
            await interaction.response.send_message("⛔ Solo administradores.", ephemeral=True)
            return

        club = _official_name(self.club)
        if not club:
            await interaction.response.send_message("⚠️ El equipo ya no está activo.", ephemeral=True)
            return

        name = self.player_name.value.strip()
        if not name:
            await interaction.response.send_message("⚠️ El nombre del jugador es obligatorio.", ephemeral=True)
            return

        existing = APP.jugador_por_nombre(name)
        if existing:
            await interaction.response.send_message(
                f"⚠️ Ya existe como `{APP.player_code(existing['id'])}` y pertenece a **{existing['club']}**.",
                ephemeral=True,
            )
            return

        stat_names = POSITION_STATS[self.position]
        try:
            values = [
                _parse_stat(self.stat_1.value, stat_names[0]),
                _parse_stat(self.stat_2.value, stat_names[1]),
                _parse_stat(self.stat_3.value, stat_names[2]),
            ]
        except ValueError as exc:
            await interaction.response.send_message(f"⚠️ {exc}", ephemeral=True)
            return

        ovr = _calculate_ovr(values)
        market_value = _market_value_for_rating(ovr)
        season = APP.temporada_activa()

        _ensure_schema()
        with APP.db() as conn:
            cur = conn.execute(
                """
                INSERT INTO roster_players
                    (name, position, club, added_by, rating, min_sale_value, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                """,
                (name, self.position, club, interaction.user.id, ovr, market_value),
            )
            player_id = int(cur.lastrowid)
            conn.execute(
                """
                INSERT OR REPLACE INTO player_rating_inputs
                    (player_id, position_key,
                     stat_1_name, stat_1_value,
                     stat_2_name, stat_2_value,
                     stat_3_name, stat_3_value,
                     calculated_ovr, formula, created_by, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'PROMEDIO_SIMPLE_3', ?, CURRENT_TIMESTAMP)
                """,
                (
                    player_id,
                    self.position,
                    stat_names[0],
                    values[0],
                    stat_names[1],
                    values[1],
                    stat_names[2],
                    values[2],
                    ovr,
                    interaction.user.id,
                ),
            )
            if conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='player_history'"
            ).fetchone():
                conn.execute(
                    """
                    INSERT INTO player_history
                        (player_id, player, from_club, to_club, transfer_id, season_id, event_type)
                    VALUES (?, ?, NULL, ?, NULL, ?, 'ALTA ADMIN')
                    """,
                    (player_id, name, club, season["id"] if season else None),
                )

        player = APP.jugador_por_id(player_id)
        clause = _clause_value_for_player(player)

        embed = discord.Embed(
            title="✅ Jugador cargado",
            description=f"`{APP.player_code(player_id)}` • **{name}** agregado a **{club}**.",
            color=discord.Color.green(),
        )
        embed.add_field(name="📍 Posición", value=self.position, inline=True)
        embed.add_field(name="⭐ OVR calculado", value=str(ovr), inline=True)
        embed.add_field(name="🧮 Fórmula", value=f"({values[0]} + {values[1]} + {values[2]}) / 3", inline=False)
        embed.add_field(name=stat_names[0], value=str(values[0]), inline=True)
        embed.add_field(name=stat_names[1], value=str(values[1]), inline=True)
        embed.add_field(name=stat_names[2], value=str(values[2]), inline=True)
        embed.add_field(name="💰 Valor de mercado", value=_fmt_money(market_value), inline=True)
        if clause is not None:
            embed.add_field(name="💥 Cláusula", value=_fmt_money(clause), inline=True)
        embed.set_footer(text="Las 3 estadísticas y el OVR quedan guardados para auditoría.")
        await interaction.response.send_message(embed=embed, ephemeral=True)


class CreateTeamButton(discord.ui.Button):
    def __init__(self, row=1):
        super().__init__(
            label="CREAR EQUIPO",
            emoji="🆕",
            style=discord.ButtonStyle.success,
            row=row,
            custom_id="ajap_admin_create_team",
        )

    async def callback(self, interaction: discord.Interaction):
        if not APP.es_admin(interaction):
            await interaction.response.send_message("⛔ Solo administradores.", ephemeral=True)
            return
        await interaction.response.send_modal(CreateTeamModal())


class LoadPlayerButton(discord.ui.Button):
    def __init__(self, row=0):
        super().__init__(
            label="CARGAR JUGADOR",
            emoji="➕",
            style=discord.ButtonStyle.primary,
            row=row,
            custom_id="ajap_admin_load_player_ovr",
        )

    async def callback(self, interaction: discord.Interaction):
        if not APP.es_admin(interaction):
            await interaction.response.send_message("⛔ Solo administradores.", ephemeral=True)
            return
        rows = _active_teams()
        if not rows:
            await interaction.response.send_message(
                "⚠️ No hay equipos activos. Creá uno primero desde **CREAR EQUIPO**.",
                ephemeral=True,
            )
            return
        embed = discord.Embed(
            title="➕ CARGAR JUGADOR",
            description="1/2 • Elegí el equipo al que pertenece el jugador.",
        )
        if len(rows) > 25:
            embed.set_footer(text=f"Mostrando los primeros 25 de {len(rows)} equipos activos.")
        await interaction.response.send_message(
            embed=embed,
            view=PlayerTeamView(rows),
            ephemeral=True,
        )


def _install_admin_roster_view():
    BaseRostersView = staff.RostersView

    class RosterBuilderView(BaseRostersView):
        def __init__(self):
            super().__init__()

            # Replace the legacy free-text "Agregar jugador" action.
            for item in list(self.children):
                label = str(getattr(item, "label", "") or "").strip().casefold()
                custom_id = getattr(item, "custom_id", None)
                if "agregar jugador" in label or custom_id == "ajap_admin_roster_add":
                    self.remove_item(item)

            self.add_item(LoadPlayerButton(row=0))
            self.add_item(CreateTeamButton(row=1))

    RosterBuilderView.__name__ = "RostersView"
    staff.RostersView = RosterBuilderView

    original_section_embed = staff.section_embed
    if not getattr(original_section_embed, "_ajap_roster_builder_wrapped", False):
        def section_embed(title, description, tools):
            if str(title).startswith("👥"):
                tools = [
                    "🆕 Crear equipo",
                    "➕ Cargar jugador + OVR automático",
                    "🔁 Mover jugador",
                    "🗑️ Quitar jugador",
                    "📋 Ver plantel",
                ]
                description = "Altas y correcciones sobre equipos y planteles oficiales."
            return original_section_embed(title, description, tools)

        section_embed._ajap_roster_builder_wrapped = True
        staff.section_embed = section_embed


def apply_admin_roster_builder_patch(runtime, bot):
    global APP, BOT
    APP = runtime
    BOT = bot
    if getattr(runtime, "_ajap_admin_roster_builder_patch", False):
        return

    _ensure_schema()
    _install_dynamic_team_catalog()
    _install_admin_roster_view()

    runtime.admin_position_stats = POSITION_STATS
    runtime.calculate_admin_ovr = _calculate_ovr
    runtime._ajap_admin_roster_builder_patch = True
    print("AJAP Staff: crear equipo + cargar jugador con 3 stats y OVR automático activos")


_original_apply_guild_isolation_patch = guild_isolation.apply_guild_isolation_patch


def _apply_guild_isolation_then_admin_roster_builder(runtime, bot):
    _original_apply_guild_isolation_patch(runtime, bot)
    apply_admin_roster_builder_patch(runtime, bot)


if not getattr(
    guild_isolation.apply_guild_isolation_patch,
    "_ajap_admin_roster_builder_wrapped",
    False,
):
    _apply_guild_isolation_then_admin_roster_builder._ajap_admin_roster_builder_wrapped = True
    guild_isolation.apply_guild_isolation_patch = _apply_guild_isolation_then_admin_roster_builder
