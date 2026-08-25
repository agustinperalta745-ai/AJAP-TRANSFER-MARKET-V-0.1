"""Temporary single-team assignment test for AJAP Transfer Market.

For this test build, only Olympique de Lyon is exposed to players. The rest of
AJAP's fixed-team system can be restored later without changing the persistent
club/roster model.
"""

import discord


OFFICIAL_TEAMS = [
    ("Olympique de Lyon", "Francia"),
]
OFFICIAL = {name.casefold(): name for name, _ in OFFICIAL_TEAMS}
APP = None


def official_name(name):
    return OFFICIAL.get(str(name).strip().casefold()) if name else None


def db():
    return APP.db()


def ensure_schema():
    with db() as conn:
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

        # Test mode: keep previous teams in the database but hide/deactivate them.
        conn.execute("UPDATE league_teams SET active = 0")
        for name, country in OFFICIAL_TEAMS:
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


def club_de(user_id):
    with db() as conn:
        row = conn.execute(
            "SELECT name FROM clubs WHERE user_id = ?", (int(user_id),)
        ).fetchone()
    return official_name(row["name"]) if row else None


def assignments():
    with db() as conn:
        rows = conn.execute(
            "SELECT user_id, name FROM clubs ORDER BY name COLLATE NOCASE"
        ).fetchall()
    return [row for row in rows if official_name(row["name"])]


def assign_team(user_id, team_name):
    team = official_name(team_name)
    if not team:
        return False, "Ese equipo no está habilitado en esta prueba."

    conn = db()
    try:
        conn.execute("BEGIN IMMEDIATE")
        current = conn.execute(
            "SELECT name FROM clubs WHERE user_id = ?", (int(user_id),)
        ).fetchone()
        current_team = official_name(current["name"]) if current else None
        if current_team:
            conn.rollback()
            return False, f"Ya tenés asignado **{current_team}**."

        occupied = conn.execute(
            """
            SELECT user_id FROM clubs
            WHERE name = ? COLLATE NOCASE AND user_id != ? LIMIT 1
            """,
            (team, int(user_id)),
        ).fetchone()
        if occupied:
            conn.rollback()
            return False, f"**{team}** ya está asignado a otro jugador."

        # If this account had an old test club, replace it with Lyon.
        conn.execute(
            """
            INSERT INTO clubs (user_id, name) VALUES (?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                name = excluded.name,
                created_at = CURRENT_TIMESTAMP
            """,
            (int(user_id), team),
        )
        conn.execute(
            """
            INSERT INTO club_assignment_history (user_id, club, action, actor_id)
            VALUES (?, ?, 'ASIGNADO', ?)
            """,
            (int(user_id), team, int(user_id)),
        )
        conn.commit()
        return True, team
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def unlink_team(user_id, admin_id):
    # Only the Discord <-> club assignment is removed. The Lyon roster stays.
    with db() as conn:
        row = conn.execute(
            "SELECT name FROM clubs WHERE user_id = ?", (int(user_id),)
        ).fetchone()
        if not row:
            return None
        team = row["name"]
        conn.execute("DELETE FROM clubs WHERE user_id = ?", (int(user_id),))
        conn.execute(
            """
            INSERT INTO club_assignment_history (user_id, club, action, actor_id)
            VALUES (?, ?, 'DESVINCULADO_ADMIN', ?)
            """,
            (int(user_id), team, int(admin_id)),
        )
        return team


def welcome_embed():
    embed = discord.Embed(
        title="🧪 Prueba de asignación • Olympique de Lyon",
        description=(
            "Por ahora está habilitado **un solo club para probar el sistema**.\n\n"
            "Elegí **Olympique de Lyon** para vincularlo a tu cuenta y acceder a su plantilla."
        ),
    )
    embed.add_field(name="Club habilitado", value="Olympique de Lyon", inline=False)
    embed.add_field(name="País", value="🇫🇷 Francia", inline=True)
    embed.add_field(name="Por cuenta", value="1 equipo", inline=True)
    embed.set_footer(text="La plantilla queda guardada aunque un admin desvincule al dueño")
    return embed


def assignments_embed():
    rows = assignments()
    embed = discord.Embed(title="👥 Asignaciones de equipos • prueba Lyon")
    if not rows:
        embed.description = "Olympique de Lyon todavía no está asignado."
        return embed
    for row in rows:
        embed.add_field(
            name=official_name(row["name"]),
            value=f"<@{row['user_id']}>",
            inline=True,
        )
    embed.set_footer(text=f"{len(rows)}/1 asignado • Revertir no modifica la plantilla")
    return embed


class TeamSelect(discord.ui.Select):
    def __init__(self):
        occupied = {row["name"].casefold() for row in assignments()}
        options = [
            discord.SelectOption(
                label=name,
                description=(
                    f"{country} • "
                    f"{'🔒 Ya asignado' if name.casefold() in occupied else '✅ Disponible para probar'}"
                )[:100],
                value=name,
                emoji="🇫🇷",
            )
            for name, country in OFFICIAL_TEAMS
        ]
        super().__init__(
            placeholder="Elegí Olympique de Lyon",
            min_values=1,
            max_values=1,
            options=options,
        )

    async def callback(self, interaction: discord.Interaction):
        current = club_de(interaction.user.id)
        if current:
            await interaction.response.send_message(
                f"⚠️ Ya tenés asignado **{current}**. Solo un admin puede revertirlo.",
                ephemeral=True,
            )
            return

        ok, result = assign_team(interaction.user.id, self.values[0])
        if not ok:
            await interaction.response.send_message(f"⚠️ {result}", ephemeral=True)
            return

        jugadores = APP.jugadores_de_club(result, 50)
        await interaction.response.edit_message(
            embed=discord.Embed(
                title="✅ Olympique de Lyon asignado",
                description=(
                    f"Desde ahora manejás **{result}**.\n\n"
                    f"Plantilla cargada: **{len(jugadores)} jugadores**.\n"
                    "Ya podés entrar a **Mi club** o **Publicar jugador** para probar el flujo."
                ),
            ),
            view=APP.MercadoView(),
        )


class TeamChoiceView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=300)
        self.add_item(TeamSelect())


class ConfirmUnlinkView(discord.ui.View):
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
        if not APP.es_admin(interaction):
            await interaction.response.send_message("⛔ Solo admins.", ephemeral=True)
            return
        current = club_de(self.user_id)
        if not current or current.casefold() != self.team.casefold():
            await interaction.response.send_message("⚠️ Esa asignación ya cambió.", ephemeral=True)
            return
        removed = unlink_team(self.user_id, interaction.user.id)
        await interaction.response.edit_message(
            embed=discord.Embed(
                title="↩️ Asignación revertida",
                description=(
                    f"<@{self.user_id}> ya no tiene **{removed}**.\n\n"
                    "✅ La plantilla de Lyon quedó intacta. Al abrir `/mercado`, podrá elegir Lyon de nuevo."
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
        if not APP.es_admin(interaction):
            await interaction.response.send_message("⛔ Solo admins.", ephemeral=True)
            return
        await interaction.response.edit_message(content="Cancelado.", embed=None, view=None)


class AssignmentSelect(discord.ui.Select):
    def __init__(self, rows):
        options = [
            discord.SelectOption(
                label=official_name(row["name"]),
                description=f"Discord ID: {row['user_id']}",
                value=str(row["user_id"]),
            )
            for row in rows[:25]
        ]
        super().__init__(
            placeholder="Elegí la asignación para revertir",
            min_values=1,
            max_values=1,
            options=options,
        )

    async def callback(self, interaction: discord.Interaction):
        if not APP.es_admin(interaction):
            await interaction.response.send_message("⛔ Solo administradores.", ephemeral=True)
            return
        user_id = int(self.values[0])
        team = club_de(user_id)
        if not team:
            await interaction.response.send_message("⚠️ Esa asignación ya no existe.", ephemeral=True)
            return
        await interaction.response.send_message(
            embed=discord.Embed(
                title="⚠️ Confirmar desvinculación",
                description=(
                    f"¿Querés quitar **{team}** de <@{user_id}>?\n\n"
                    "Esto solo borra la asignación Discord ↔ club; **no toca la plantilla**."
                ),
            ),
            view=ConfirmUnlinkView(user_id, team),
            ephemeral=True,
        )


class AssignmentsView(discord.ui.View):
    def __init__(self, rows):
        super().__init__(timeout=180)
        if rows:
            self.add_item(AssignmentSelect(rows))


def build_market_view():
    OldView = APP.MercadoView

    class PatchedMercadoView(OldView):
        def __init__(self):
            super().__init__()
            for item in self.children:
                if getattr(item, "custom_id", None) == "mercado_mi_club":
                    item.callback = self._fixed_mi_club
                elif getattr(item, "custom_id", None) == "mercado_publicar":
                    item.callback = self._fixed_publicar

            admin_button = discord.ui.Button(
                label="Asignaciones",
                emoji="👥",
                style=discord.ButtonStyle.primary,
                custom_id="mercado_asignaciones",
                row=1,
            )
            admin_button.callback = self._assignments
            self.add_item(admin_button)

        async def _fixed_mi_club(self, interaction):
            team = club_de(interaction.user.id)
            if not team:
                await interaction.response.send_message(
                    embed=welcome_embed(),
                    view=TeamChoiceView(),
                    ephemeral=True,
                )
                return
            await interaction.response.send_message(
                embed=APP.plantel_embed(team),
                ephemeral=True,
            )

        async def _fixed_publicar(self, interaction):
            team = club_de(interaction.user.id)
            if not team:
                await interaction.response.send_message(
                    embed=welcome_embed(),
                    view=TeamChoiceView(),
                    ephemeral=True,
                )
                return

            jugadores = [
                j
                for j in APP.jugadores_de_club(team, 50)
                if not APP.publicacion_activa_del_jugador(j["name"])
                and not APP.operacion_abierta_del_jugador(j["name"])
            ]
            if not jugadores:
                await interaction.response.send_message(
                    "⚠️ No tenés jugadores disponibles para publicar.",
                    ephemeral=True,
                )
                return
            await interaction.response.send_message(
                "📤 Elegí el jugador que querés publicar:",
                view=APP.PublicarView(jugadores[:25]),
                ephemeral=True,
            )

        async def _assignments(self, interaction):
            if not APP.es_admin(interaction):
                await interaction.response.send_message(
                    "⛔ Solo administradores.",
                    ephemeral=True,
                )
                return
            rows = assignments()
            await interaction.response.send_message(
                embed=assignments_embed(),
                view=AssignmentsView(rows),
                ephemeral=True,
            )

    PatchedMercadoView.__name__ = "MercadoView"
    return PatchedMercadoView


async def mercado_command(interaction: discord.Interaction):
    if not club_de(interaction.user.id):
        await interaction.response.send_message(
            embed=welcome_embed(),
            view=TeamChoiceView(),
            ephemeral=True,
        )
        return
    await interaction.response.send_message(
        embed=APP.panel_embed(interaction.user.id),
        view=APP.MercadoView(),
    )


async def assignments_command(interaction: discord.Interaction):
    if not APP.es_admin(interaction):
        await interaction.response.send_message("⛔ Solo administradores.", ephemeral=True)
        return
    rows = assignments()
    await interaction.response.send_message(
        embed=assignments_embed(),
        view=AssignmentsView(rows),
        ephemeral=True,
    )


async def unlink_command(interaction: discord.Interaction, usuario: discord.Member):
    if not APP.es_admin(interaction):
        await interaction.response.send_message("⛔ Solo administradores.", ephemeral=True)
        return
    team = club_de(usuario.id)
    if not team:
        await interaction.response.send_message(
            f"⚠️ {usuario.mention} no tiene un equipo asignado.",
            ephemeral=True,
        )
        return
    await interaction.response.send_message(
        embed=discord.Embed(
            title="⚠️ Confirmar desvinculación",
            description=(
                f"Vas a quitar **{team}** de {usuario.mention}.\n\n"
                "La plantilla queda intacta y el jugador podrá elegir nuevamente."
            ),
        ),
        view=ConfirmUnlinkView(usuario.id, team),
        ephemeral=True,
    )


def apply_team_assignment_patch(main_module, bot):
    global APP
    if getattr(bot, "_ajap_fixed_team_patch", False):
        return

    APP = main_module
    ensure_schema()

    main_module.club_de = club_de
    main_module.MercadoView = build_market_view()

    bot.tree.remove_command("mercado")
    bot.tree.command(
        name="mercado",
        description="Abre AJAP Transfer Market",
    )(mercado_command)

    if bot.tree.get_command("asignaciones") is None:
        bot.tree.command(
            name="asignaciones",
            description="Gestiona equipos asignados (solo admin)",
        )(assignments_command)

    if bot.tree.get_command("desvincular_equipo") is None:
        bot.tree.command(
            name="desvincular_equipo",
            description="Revierte un equipo mal elegido (solo admin)",
        )(unlink_command)

    bot._ajap_fixed_team_patch = True
    print("Modo prueba AJAP activo: solo Olympique de Lyon")
