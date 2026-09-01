"""Staff assignment flow for managers who have not selected a club yet.

Adds an `ASIGNAR EQUIPO` button inside the existing Staff -> Asignaciones screen.
The flow is intentionally limited to users without a live club assignment and to
currently free JSON-backed clubs. SQLite is updated atomically, assignment history
and the integrity guard advance together, and Discord club identity is synchronized
after the commit.
"""

from __future__ import annotations

import discord

import club_assignment_consistency_patch as consistency
import guild_isolation_patch as guild_isolation
import json_team_selection_patch as json_selector
import team_assignment as teams
import team_role_identity_patch as club_identity


APP = None
BOT = None
BASE_ASSIGNMENTS_VIEW = None


def _table_exists(conn, table_name: str) -> bool:
    return bool(
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
            (str(table_name),),
        ).fetchone()
    )


def _json_clubs():
    names = []
    seen = set()
    try:
        rows = json_selector._json_team_rows()
    except Exception:
        rows = []
    for row in rows:
        try:
            name = str(row.get("name") or "").strip()
        except AttributeError:
            try:
                name = str(row["name"] or "").strip()
            except Exception:
                name = ""
        key = name.casefold()
        if name and key not in seen:
            seen.add(key)
            names.append(name)
    return names


def _current_club(user_id: int):
    try:
        return APP.club_de(int(user_id))
    except Exception:
        with APP.db() as conn:
            row = conn.execute(
                "SELECT name FROM clubs WHERE user_id=? LIMIT 1",
                (int(user_id),),
            ).fetchone()
        return str(row["name"]) if row else None


def _free_clubs():
    with APP.db() as conn:
        rows = conn.execute("SELECT name FROM clubs").fetchall()
    occupied = {str(row["name"] or "").strip().casefold() for row in rows}
    return [club for club in _json_clubs() if club.casefold() not in occupied]


def _assign_unassigned(user_id: int, club: str, admin_id: int):
    valid = {name.casefold(): name for name in _json_clubs()}
    canonical = valid.get(str(club or "").strip().casefold())
    if not canonical:
        return False, "Ese club ya no está habilitado por JSON."

    conn = APP.db()
    try:
        conn.execute("BEGIN IMMEDIATE")
        current = conn.execute(
            "SELECT name FROM clubs WHERE user_id=? LIMIT 1",
            (int(user_id),),
        ).fetchone()
        if current:
            conn.rollback()
            return False, f"Ese usuario ya tiene asignado **{current['name']}**."

        occupied = conn.execute(
            "SELECT user_id FROM clubs WHERE name=? COLLATE NOCASE LIMIT 1",
            (canonical,),
        ).fetchone()
        if occupied:
            conn.rollback()
            return False, f"**{canonical}** ya está asignado a otro jugador."

        conn.execute(
            "INSERT INTO clubs (user_id, name) VALUES (?, ?)",
            (int(user_id), canonical),
        )
        conn.execute(
            """
            INSERT INTO club_assignment_history (user_id, club, action, actor_id)
            VALUES (?, ?, 'ASIGNADO', ?)
            """,
            (int(user_id), canonical, int(admin_id)),
        )

        # Advance the same integrity guard used by normal self-assignment so a
        # previous unlink/resignation can never resurrect over this Staff action.
        consistency._set_guard(
            conn,
            int(user_id),
            canonical,
            True,
            "STAFF_ASSIGN_TEAM",
            int(admin_id),
        )
        consistency._event(
            conn,
            int(user_id),
            canonical,
            canonical,
            "LEGITIMATE_STAFF_ASSIGNMENT",
        )

        # Any outstanding free-team request for this user/club is no longer valid.
        if _table_exists(conn, "free_team_requests"):
            conn.execute(
                """
                UPDATE free_team_requests
                SET status='CERRADA_AUTOMATICA',
                    resolved_by=?,
                    resolved_at=CURRENT_TIMESTAMP
                WHERE status IN ('PENDIENTE','EN_ESPERA')
                  AND (club=? COLLATE NOCASE OR user_id=?)
                """,
                (int(admin_id), canonical, int(user_id)),
            )

        conn.commit()
        return True, canonical
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _member_name(guild: discord.Guild | None, user_id: int) -> str:
    if guild is not None:
        member = guild.get_member(int(user_id))
        if member is not None:
            return str(member.display_name or member.name)
    return f"Usuario {int(user_id)}"


async def _show_assignments(interaction: discord.Interaction):
    rows = teams.assignments()
    await interaction.response.edit_message(
        embed=teams.assignments_embed(),
        view=teams.AssignmentsView(rows),
    )


class BackAssignmentsButton(discord.ui.Button):
    def __init__(self, row=1):
        super().__init__(
            label="VOLVER A ASIGNACIONES",
            emoji="⬅️",
            style=discord.ButtonStyle.secondary,
            row=row,
            custom_id=f"ajap_staff_assign_back_{row}",
        )

    async def callback(self, interaction: discord.Interaction):
        if not APP.es_admin(interaction):
            await interaction.response.send_message("⛔ Solo administradores.", ephemeral=True)
            return
        await _show_assignments(interaction)


class UnassignedUserSelect(discord.ui.UserSelect):
    def __init__(self):
        super().__init__(
            placeholder="Buscá al jugador que todavía no tiene equipo",
            min_values=1,
            max_values=1,
            row=0,
        )

    async def callback(self, interaction: discord.Interaction):
        if not APP.es_admin(interaction):
            await interaction.response.send_message("⛔ Solo administradores.", ephemeral=True)
            return
        if not interaction.guild:
            await interaction.response.send_message("⚠️ Esta herramienta solo funciona dentro del servidor.", ephemeral=True)
            return

        member = self.values[0]
        if getattr(member, "bot", False):
            await interaction.response.send_message("⚠️ No se puede asignar un club a un bot.", ephemeral=True)
            return

        current = _current_club(member.id)
        if current:
            await interaction.response.send_message(
                f"⚠️ {member.mention} ya tiene **{current}**. Para moverlo usá la herramienta de cambio de club.",
                ephemeral=True,
            )
            return

        available = _free_clubs()
        if not available:
            await interaction.response.send_message("⚠️ No hay equipos JSON libres para asignar.", ephemeral=True)
            return

        embed = discord.Embed(
            title="👤 ASIGNAR EQUIPO",
            description=(
                f"Jugador: {member.mention}\n"
                "Estado: **sin equipo** ✅\n\n"
                "Elegí uno de los clubes disponibles."
            ),
            color=discord.Color.blurple(),
        )
        await interaction.response.edit_message(
            embed=embed,
            view=FreeClubView(member.id, available, interaction.guild),
        )


class PickUnassignedUserView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=180)
        self.add_item(UnassignedUserSelect())
        self.add_item(BackAssignmentsButton(row=1))


class FreeClubSelect(discord.ui.Select):
    def __init__(self, user_id: int, clubs, guild: discord.Guild | None):
        self.user_id = int(user_id)
        options = []
        for club in clubs[:25]:
            emoji = None
            try:
                import team_badge_selector_patch as badges
                emoji = badges._manual_badge_emoji(guild, club) if guild else None
            except Exception:
                emoji = None
            options.append(
                discord.SelectOption(
                    label=club[:100],
                    value=club,
                    description="✅ Disponible",
                    emoji=emoji,
                )
            )
        super().__init__(
            placeholder="Elegí el equipo a asignar",
            min_values=1,
            max_values=1,
            options=options,
            row=0,
        )

    async def callback(self, interaction: discord.Interaction):
        if not APP.es_admin(interaction):
            await interaction.response.send_message("⛔ Solo administradores.", ephemeral=True)
            return

        current = _current_club(self.user_id)
        if current:
            await interaction.response.send_message(
                f"⚠️ La asignación cambió: <@{self.user_id}> ahora tiene **{current}**.",
                ephemeral=True,
            )
            return

        club = self.values[0]
        if club.casefold() not in {name.casefold() for name in _free_clubs()}:
            await interaction.response.send_message(
                f"⚠️ **{club}** dejó de estar disponible. Volvé a abrir Asignaciones.",
                ephemeral=True,
            )
            return

        embed = discord.Embed(
            title="⚠️ CONFIRMAR ASIGNACIÓN",
            description=(
                f"Jugador: <@{self.user_id}>\n"
                f"Equipo: **{club}**\n\n"
                "Se guardará como asignación oficial y se sincronizarán el rol del club y el apodo."
            ),
            color=discord.Color.orange(),
        )
        await interaction.response.edit_message(
            embed=embed,
            view=ConfirmStaffAssignmentView(self.user_id, club),
        )


class FreeClubView(discord.ui.View):
    def __init__(self, user_id: int, clubs, guild: discord.Guild | None):
        super().__init__(timeout=180)
        self.add_item(FreeClubSelect(user_id, clubs, guild))
        self.add_item(BackAssignmentsButton(row=1))


class ConfirmStaffAssignmentView(discord.ui.View):
    def __init__(self, user_id: int, club: str):
        super().__init__(timeout=120)
        self.user_id = int(user_id)
        self.club = str(club)

    @discord.ui.button(
        label="CONFIRMAR ASIGNACIÓN",
        emoji="✅",
        style=discord.ButtonStyle.success,
        row=0,
    )
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not APP.es_admin(interaction):
            await interaction.response.send_message("⛔ Solo administradores.", ephemeral=True)
            return

        await interaction.response.defer()
        try:
            ok, result = _assign_unassigned(
                self.user_id,
                self.club,
                interaction.user.id,
            )
        except Exception as exc:
            print(
                "ERROR AJAP Staff asignar equipo: "
                f"user={self.user_id} club={self.club} error={type(exc).__name__}: {exc}"
            )
            await interaction.edit_original_response(
                embed=discord.Embed(
                    title="❌ ASIGNACIÓN NO REALIZADA",
                    description="Ocurrió un error interno y no se guardó ningún cambio.",
                    color=discord.Color.red(),
                ),
                view=teams.AssignmentsView(teams.assignments()),
            )
            return

        if not ok:
            await interaction.edit_original_response(
                embed=discord.Embed(
                    title="⚠️ ASIGNACIÓN NO REALIZADA",
                    description=str(result),
                    color=discord.Color.orange(),
                ),
                view=teams.AssignmentsView(teams.assignments()),
            )
            return

        identity_ok = False
        try:
            identity_ok = await club_identity.sync_member_identity(
                interaction.guild,
                self.user_id,
            )
        except Exception as exc:
            print(f"WARNING AJAP Staff asignar equipo: identidad Discord pendiente: {exc}")

        embed = discord.Embed(
            title="✅ EQUIPO ASIGNADO",
            description=(
                f"<@{self.user_id}> ahora dirige **{result}**.\n\n"
                "La asignación quedó guardada oficialmente."
            ),
            color=discord.Color.green(),
        )
        embed.add_field(
            name="🪪 Discord",
            value=(
                "Rol del club y apodo sincronizados."
                if identity_ok
                else "La DB quedó correcta; el rol/apodo se reconciliarán automáticamente."
            ),
            inline=False,
        )
        await interaction.edit_original_response(
            embed=embed,
            view=teams.AssignmentsView(teams.assignments()),
        )

    @discord.ui.button(
        label="CANCELAR",
        emoji="✖️",
        style=discord.ButtonStyle.secondary,
        row=0,
    )
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await _show_assignments(interaction)


class StaffAssignTeamButton(discord.ui.Button):
    def __init__(self, row=1):
        super().__init__(
            label="ASIGNAR EQUIPO",
            emoji="➕",
            style=discord.ButtonStyle.success,
            row=row,
            custom_id="ajap_staff_assign_team",
        )

    async def callback(self, interaction: discord.Interaction):
        if not APP.es_admin(interaction):
            await interaction.response.send_message("⛔ Solo administradores.", ephemeral=True)
            return

        available = _free_clubs()
        if not available:
            await interaction.response.send_message(
                "⚠️ No hay equipos JSON libres para asignar en este momento.",
                ephemeral=True,
            )
            return

        embed = discord.Embed(
            title="➕ ASIGNAR EQUIPO A UN JUGADOR",
            description=(
                "Buscá al usuario de Discord que todavía **no eligió equipo**.\n\n"
                "Si ya tiene club, el bot no permitirá pisar la asignación existente."
            ),
            color=discord.Color.blurple(),
        )
        await interaction.response.edit_message(embed=embed, view=PickUnassignedUserView())


def apply_staff_assign_team_patch(runtime, bot):
    global APP, BOT, BASE_ASSIGNMENTS_VIEW
    APP = runtime
    BOT = bot
    if getattr(runtime, "_ajap_staff_assign_team_patch", False):
        return

    BASE_ASSIGNMENTS_VIEW = teams.AssignmentsView

    class StaffAssignmentsView(BASE_ASSIGNMENTS_VIEW):
        def __init__(self, rows):
            super().__init__(rows)
            self.add_item(StaffAssignTeamButton(row=1))

    StaffAssignmentsView.__name__ = "AssignmentsView"
    teams.AssignmentsView = StaffAssignmentsView
    runtime.AssignmentsView = StaffAssignmentsView

    runtime.staff_assign_unassigned_team = _assign_unassigned
    runtime._ajap_staff_assign_team_patch = True
    print("AJAP Staff: Asignaciones > Asignar equipo activo para usuarios sin club")


_original_apply_guild_isolation_patch = guild_isolation.apply_guild_isolation_patch


def _apply_guild_isolation_then_staff_assign(runtime, bot):
    _original_apply_guild_isolation_patch(runtime, bot)
    apply_staff_assign_team_patch(runtime, bot)


if not getattr(
    guild_isolation.apply_guild_isolation_patch,
    "_ajap_staff_assign_team_wrapped",
    False,
):
    _apply_guild_isolation_then_staff_assign._ajap_staff_assign_team_wrapped = True
    guild_isolation.apply_guild_isolation_patch = _apply_guild_isolation_then_staff_assign
