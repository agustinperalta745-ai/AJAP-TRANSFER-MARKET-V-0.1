"""Full team deletion/reset flow for AJAP Transfer Market Staff.

Adds PLANTELES -> ELIMINAR EQUIPO with a guarded select + confirmation flow.
Deleting a team:
- removes it from the active team catalog,
- deletes its current roster and player-rating inputs,
- clears its budget,
- removes current Discord<->club assignments,
- clears market records tied to that club/current roster so it can be reloaded cleanly,
- records a tombstone so built-in seed/catalog code cannot silently reactivate it,
- restores manager nicknames / removes DT role when Discord permissions allow it.

Creating the same team again clears the tombstone and starts it fresh.
"""

from __future__ import annotations

import discord

import admin_roster_builder_patch as builder
import guild_isolation_patch as guild_isolation
import staff_admin_organized_patch as staff
import team_assignment as teams


APP = None
BOT = None


def _table_exists(conn, table: str) -> bool:
    return bool(
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
            (table,),
        ).fetchone()
    )


def _columns(conn, table: str) -> set[str]:
    if not _table_exists(conn, table):
        return set()
    safe = table.replace('"', '""')
    return {row["name"] for row in conn.execute(f'PRAGMA table_info("{safe}")').fetchall()}


def _ensure_delete_schema():
    with APP.db() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS deleted_teams (
                name TEXT PRIMARY KEY COLLATE NOCASE,
                deleted_by INTEGER,
                deleted_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )


def _is_deleted(name: str) -> bool:
    if not name:
        return False
    _ensure_delete_schema()
    with APP.db() as conn:
        return bool(
            conn.execute(
                "SELECT 1 FROM deleted_teams WHERE name = ? COLLATE NOCASE LIMIT 1",
                (str(name).strip(),),
            ).fetchone()
        )


def _active_teams():
    _ensure_delete_schema()
    with APP.db() as conn:
        return conn.execute(
            """
            SELECT lt.name, lt.country
            FROM league_teams lt
            LEFT JOIN deleted_teams d ON d.name = lt.name COLLATE NOCASE
            WHERE lt.active = 1 AND d.name IS NULL
            ORDER BY lt.name COLLATE NOCASE
            """
        ).fetchall()


def _official_name(name):
    if not name:
        return None
    _ensure_delete_schema()
    with APP.db() as conn:
        row = conn.execute(
            """
            SELECT lt.name
            FROM league_teams lt
            LEFT JOIN deleted_teams d ON d.name = lt.name COLLATE NOCASE
            WHERE lt.active = 1
              AND d.name IS NULL
              AND lt.name = ? COLLATE NOCASE
            LIMIT 1
            """,
            (str(name).strip(),),
        ).fetchone()
    return row["name"] if row else None


def _install_deleted_catalog_guard():
    """Prevent built-in startup code from reactivating a Staff-deleted team."""
    original_ensure = teams.ensure_schema
    if not getattr(original_ensure, "_ajap_deleted_team_guard", False):
        def ensure_schema():
            original_ensure()
            _ensure_delete_schema()
            with APP.db() as conn:
                conn.execute(
                    """
                    UPDATE league_teams
                    SET active = 0
                    WHERE name IN (SELECT name FROM deleted_teams)
                    """
                )

        ensure_schema._ajap_deleted_team_guard = True
        teams.ensure_schema = ensure_schema

    # Every assignment / selector lookup must use the tombstone-aware catalog.
    builder._active_teams = _active_teams
    builder._official_name = _official_name
    teams.official_name = _official_name


def _install_recreate_hook():
    BaseModal = builder.CreateTeamModal
    if getattr(BaseModal, "_ajap_recreate_deleted_team", False):
        return

    class RecreateAwareCreateTeamModal(BaseModal):
        async def on_submit(self, interaction: discord.Interaction):
            name = self.name.value.strip()
            if name:
                _ensure_delete_schema()
                with APP.db() as conn:
                    conn.execute(
                        "DELETE FROM deleted_teams WHERE name = ? COLLATE NOCASE",
                        (name,),
                    )
            await super().on_submit(interaction)

    RecreateAwareCreateTeamModal.__name__ = "CreateTeamModal"
    RecreateAwareCreateTeamModal._ajap_recreate_deleted_team = True
    builder.CreateTeamModal = RecreateAwareCreateTeamModal


def _team_snapshot(club: str):
    _ensure_delete_schema()
    with APP.db() as conn:
        team = conn.execute(
            "SELECT name, country FROM league_teams WHERE name = ? COLLATE NOCASE LIMIT 1",
            (club,),
        ).fetchone()
        player_count = 0
        if _table_exists(conn, "roster_players"):
            player_count = int(
                conn.execute(
                    "SELECT COUNT(*) AS n FROM roster_players WHERE club = ? COLLATE NOCASE",
                    (club,),
                ).fetchone()["n"]
            )
        assigned = []
        if _table_exists(conn, "clubs"):
            assigned = [
                int(row["user_id"])
                for row in conn.execute(
                    "SELECT user_id FROM clubs WHERE name = ? COLLATE NOCASE",
                    (club,),
                ).fetchall()
            ]
        balance = None
        if _table_exists(conn, "club_finances"):
            row = conn.execute(
                "SELECT balance FROM club_finances WHERE club = ? COLLATE NOCASE LIMIT 1",
                (club,),
            ).fetchone()
            if row:
                balance = int(row["balance"])
    return team, player_count, assigned, balance


def _delete_by_player_ids(conn, table: str, player_ids: list[int]):
    if not player_ids or not _table_exists(conn, table):
        return
    cols = _columns(conn, table)
    if "player_id" not in cols:
        return
    marks = ",".join("?" for _ in player_ids)
    safe = table.replace('"', '""')
    conn.execute(f'DELETE FROM "{safe}" WHERE player_id IN ({marks})', tuple(player_ids))


def _delete_team_data(club: str, admin_id: int):
    """Hard reset the selected team's current AJAP data inside one transaction."""
    conn = APP.db()
    try:
        conn.execute("BEGIN IMMEDIATE")
        team = conn.execute(
            "SELECT name, country FROM league_teams WHERE name = ? COLLATE NOCASE LIMIT 1",
            (club,),
        ).fetchone()
        if not team:
            conn.rollback()
            return False, "Ese equipo ya no existe.", []

        canonical = team["name"]
        player_rows = []
        if _table_exists(conn, "roster_players"):
            player_rows = conn.execute(
                "SELECT id, name FROM roster_players WHERE club = ? COLLATE NOCASE",
                (canonical,),
            ).fetchall()
        player_ids = [int(row["id"]) for row in player_rows]
        player_names = [row["name"] for row in player_rows]

        assigned_users = []
        if _table_exists(conn, "clubs"):
            assigned_users = [
                int(row["user_id"])
                for row in conn.execute(
                    "SELECT user_id FROM clubs WHERE name = ? COLLATE NOCASE",
                    (canonical,),
                ).fetchall()
            ]
            conn.execute("DELETE FROM clubs WHERE name = ? COLLATE NOCASE", (canonical,))

        # Remove active/past market footprint for this team so reloading truly starts clean.
        if _table_exists(conn, "publications"):
            conn.execute("DELETE FROM publications WHERE club = ? COLLATE NOCASE", (canonical,))
        if _table_exists(conn, "offers"):
            cols = _columns(conn, "offers")
            clauses = []
            params = []
            if "from_club" in cols:
                clauses.append("from_club = ? COLLATE NOCASE")
                params.append(canonical)
            if "to_club" in cols:
                clauses.append("to_club = ? COLLATE NOCASE")
                params.append(canonical)
            if clauses:
                conn.execute("DELETE FROM offers WHERE " + " OR ".join(clauses), tuple(params))
        if _table_exists(conn, "transfers"):
            cols = _columns(conn, "transfers")
            clauses = []
            params = []
            if "seller" in cols:
                clauses.append("seller = ? COLLATE NOCASE")
                params.append(canonical)
            if "buyer" in cols:
                clauses.append("buyer = ? COLLATE NOCASE")
                params.append(canonical)
            if clauses:
                conn.execute("DELETE FROM transfers WHERE " + " OR ".join(clauses), tuple(params))
        if _table_exists(conn, "player_history"):
            cols = _columns(conn, "player_history")
            clauses = []
            params = []
            if "from_club" in cols:
                clauses.append("from_club = ? COLLATE NOCASE")
                params.append(canonical)
            if "to_club" in cols:
                clauses.append("to_club = ? COLLATE NOCASE")
                params.append(canonical)
            if clauses:
                conn.execute("DELETE FROM player_history WHERE " + " OR ".join(clauses), tuple(params))

        # Player-id keyed extension tables (stats, loans, clause requests, etc.).
        for table in (
            "player_rating_inputs",
            "pes6_player_attributes",
            "pes6_attributes",
            "player_attributes",
            "loans",
            "clause_requests",
        ):
            _delete_by_player_ids(conn, table, player_ids)

        # Extra rows in common club-keyed extension tables are removed only when
        # the expected club columns exist. This keeps the reset compatible with
        # older/newer guild DB schemas.
        for table in (
            "loans",
            "clause_requests",
            "free_team_requests",
            "vacancy_requests",
        ):
            if not _table_exists(conn, table):
                continue
            cols = _columns(conn, table)
            club_cols = [
                col for col in (
                    "club", "seller", "buyer", "from_club", "to_club",
                    "lender_club", "borrower_club", "owner_club", "source_club",
                    "destination_club", "team",
                )
                if col in cols
            ]
            if club_cols:
                where = " OR ".join(f'{col} = ? COLLATE NOCASE' for col in club_cols)
                conn.execute(
                    f'DELETE FROM "{table}" WHERE {where}',
                    tuple(canonical for _ in club_cols),
                )

        if _table_exists(conn, "club_finances"):
            conn.execute("DELETE FROM club_finances WHERE club = ? COLLATE NOCASE", (canonical,))

        if _table_exists(conn, "roster_players"):
            conn.execute("DELETE FROM roster_players WHERE club = ? COLLATE NOCASE", (canonical,))

        # Keep a tombstone. Built-in static team code may try to recreate its
        # league_teams row on restart, but the guard immediately leaves it inactive.
        conn.execute(
            """
            INSERT INTO deleted_teams (name, deleted_by, deleted_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(name) DO UPDATE SET
                deleted_by = excluded.deleted_by,
                deleted_at = CURRENT_TIMESTAMP
            """,
            (canonical, int(admin_id)),
        )
        conn.execute("DELETE FROM league_teams WHERE name = ? COLLATE NOCASE", (canonical,))

        if _table_exists(conn, "club_assignment_history"):
            for user_id in assigned_users:
                conn.execute(
                    """
                    INSERT INTO club_assignment_history (user_id, club, action, actor_id)
                    VALUES (?, ?, 'EQUIPO_ELIMINADO_ADMIN', ?)
                    """,
                    (user_id, canonical, int(admin_id)),
                )

        conn.commit()
        return True, {
            "club": canonical,
            "players": len(player_rows),
            "assigned_users": assigned_users,
            "player_names": player_names,
        }, assigned_users
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


async def _cleanup_discord_members(guild, user_ids: list[int], club: str):
    if guild is None:
        return
    for user_id in user_ids:
        try:
            import dt_role_patch as dt_roles
            await dt_roles._remove_dt(
                guild,
                int(user_id),
                reason=f"AJAP: equipo {club} eliminado por Staff",
                require_config=False,
            )
        except Exception as exc:
            print(f"WARNING AJAP: no se pudo quitar DT al eliminar {club}: {exc}")
        try:
            import member_nickname_patch as nicknames
            await nicknames._restore_member_nickname(guild, int(user_id))
        except Exception as exc:
            print(f"WARNING AJAP: no se pudo restaurar apodo al eliminar {club}: {exc}")


class DeleteTeamSelect(discord.ui.Select):
    def __init__(self, rows):
        options = [
            discord.SelectOption(
                label=row["name"][:100],
                description=f"{row['country']} • eliminar equipo completo"[:100],
                value=row["name"],
                emoji="🗑️",
            )
            for row in rows[:25]
        ]
        super().__init__(
            placeholder="Elegí el equipo que querés eliminar",
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
        team, player_count, assigned, balance = _team_snapshot(club)
        if not team:
            await interaction.response.send_message("⚠️ Ese equipo ya no existe.", ephemeral=True)
            return

        embed = discord.Embed(
            title="⚠️ ELIMINAR EQUIPO COMPLETO",
            description=(
                f"Vas a eliminar **{team['name']}** y dejarlo listo para cargar nuevamente desde cero.\n\n"
                "Esta acción elimina su plantilla, presupuesto, asignaciones y registros de mercado ligados al equipo."
            ),
            color=discord.Color.red(),
        )
        embed.add_field(name="🌍 País", value=team["country"], inline=True)
        embed.add_field(name="👥 Jugadores", value=str(player_count), inline=True)
        embed.add_field(
            name="💰 Presupuesto",
            value=builder._fmt_money(balance) if balance is not None else "Sin saldo",
            inline=True,
        )
        embed.add_field(
            name="👤 DT asignado",
            value=f"{len(assigned)} usuario(s)" if assigned else "Ninguno",
            inline=False,
        )
        embed.set_footer(text="Para volver a usarlo, crealo otra vez desde CREAR EQUIPO y cargá su plantilla.")
        await interaction.response.edit_message(
            embed=embed,
            view=DeleteTeamConfirmView(team["name"]),
        )


class DeleteTeamListView(discord.ui.View):
    def __init__(self, rows):
        super().__init__(timeout=300)
        if rows:
            self.add_item(DeleteTeamSelect(rows))


class DeleteTeamConfirmView(discord.ui.View):
    def __init__(self, club: str):
        super().__init__(timeout=180)
        self.club = club

    @discord.ui.button(
        label="CONFIRMAR ELIMINACIÓN",
        emoji="🗑️",
        style=discord.ButtonStyle.danger,
        row=0,
    )
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not APP.es_admin(interaction):
            await interaction.response.send_message("⛔ Solo administradores.", ephemeral=True)
            return

        ok, result, assigned_users = _delete_team_data(self.club, interaction.user.id)
        if not ok:
            await interaction.response.send_message(f"⚠️ {result}", ephemeral=True)
            return

        await _cleanup_discord_members(interaction.guild, assigned_users, result["club"])
        embed = discord.Embed(
            title="✅ Equipo eliminado",
            description=f"**{result['club']}** fue eliminado completamente del servidor.",
            color=discord.Color.green(),
        )
        embed.add_field(name="👥 Jugadores eliminados", value=str(result["players"]), inline=True)
        embed.add_field(name="👤 Asignaciones liberadas", value=str(len(assigned_users)), inline=True)
        embed.add_field(
            name="🔄 Próximo paso",
            value="Usá **CREAR EQUIPO** para volver a crearlo y después **CARGAR JUGADOR** para reconstruir la plantilla.",
            inline=False,
        )
        await interaction.response.edit_message(embed=embed, view=None)

    @discord.ui.button(
        label="CANCELAR",
        emoji="✖️",
        style=discord.ButtonStyle.secondary,
        row=0,
    )
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(
            embed=discord.Embed(
                title="🗑️ ELIMINAR EQUIPO",
                description="Elegí el equipo que querés eliminar completamente.",
            ),
            view=DeleteTeamListView(_active_teams()),
        )


class DeleteTeamButton(discord.ui.Button):
    def __init__(self, row=1):
        super().__init__(
            label="ELIMINAR EQUIPO",
            emoji="🗑️",
            style=discord.ButtonStyle.danger,
            row=row,
            custom_id="ajap_admin_delete_team_full",
        )

    async def callback(self, interaction: discord.Interaction):
        if not APP.es_admin(interaction):
            await interaction.response.send_message("⛔ Solo administradores.", ephemeral=True)
            return
        rows = _active_teams()
        embed = discord.Embed(
            title="🗑️ ELIMINAR EQUIPO",
            description="Elegí el equipo que querés eliminar completamente y volver a cargar desde cero.",
            color=discord.Color.red(),
        )
        if not rows:
            embed.description = "No hay equipos activos para eliminar."
        await interaction.response.send_message(
            embed=embed,
            view=DeleteTeamListView(rows),
            ephemeral=True,
        )


def _install_delete_button():
    BaseRostersView = staff.RostersView
    if getattr(BaseRostersView, "_ajap_delete_team_button", False):
        return

    class TeamDeleteRostersView(BaseRostersView):
        def __init__(self):
            super().__init__()
            if not any(
                getattr(item, "custom_id", None) == "ajap_admin_delete_team_full"
                for item in self.children
            ):
                self.add_item(DeleteTeamButton(row=1))

    TeamDeleteRostersView.__name__ = "RostersView"
    TeamDeleteRostersView._ajap_delete_team_button = True
    staff.RostersView = TeamDeleteRostersView

    original_section_embed = staff.section_embed
    if not getattr(original_section_embed, "_ajap_delete_team_tools", False):
        def section_embed(title, description, tools):
            if str(title).startswith("👥"):
                tools = list(tools)
                if not any("Eliminar equipo" in str(item) for item in tools):
                    tools.insert(1, "🗑️ Eliminar equipo completo")
            return original_section_embed(title, description, tools)

        section_embed._ajap_delete_team_tools = True
        staff.section_embed = section_embed


def apply_admin_team_delete_patch(runtime, bot):
    global APP, BOT
    APP = runtime
    BOT = bot
    if getattr(runtime, "_ajap_admin_team_delete_patch", False):
        return

    _ensure_delete_schema()
    _install_deleted_catalog_guard()
    _install_recreate_hook()
    _install_delete_button()

    runtime._ajap_admin_team_delete_patch = True
    print("AJAP Staff: eliminar equipo completo + recarga limpia activos")


_original_apply_guild_isolation_patch = guild_isolation.apply_guild_isolation_patch


def _apply_guild_isolation_then_team_delete(runtime, bot):
    _original_apply_guild_isolation_patch(runtime, bot)
    apply_admin_team_delete_patch(runtime, bot)


if not getattr(
    guild_isolation.apply_guild_isolation_patch,
    "_ajap_admin_team_delete_wrapped",
    False,
):
    _apply_guild_isolation_then_team_delete._ajap_admin_team_delete_wrapped = True
    guild_isolation.apply_guild_isolation_patch = _apply_guild_isolation_then_team_delete
