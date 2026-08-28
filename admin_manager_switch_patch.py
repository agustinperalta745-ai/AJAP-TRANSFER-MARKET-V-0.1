"""Cambio administrativo y atómico de DT entre clubes AJAP.

Objetivo:
- acceso a /mercado y pertenencia a un club son estados separados;
- un DT puede quedar SIN CLUB sin perder el acceso general al bot;
- Staff puede mover un DT de un club a otro libre sin pasar por renuncia + nueva
  asignación manual;
- el cambio conserva planteles, presupuestos y estado deportivo de ambos clubes;
- SQLite es la fuente de verdad y luego se sincronizan rol de club + apodo;
- el club anterior queda libre y se publica como vacante.
"""

from __future__ import annotations

import discord

import free_team_vacancy_patch as vacancies
import guild_isolation_patch as guild_isolation
import json_team_selection_patch as json_selector
import staff_admin_organized_patch as admin_ui
import team_badge_selector_patch as badge_selector
import team_role_identity_patch as club_identity


APP = None
BOT = None
ORIGINAL_MANAGEMENT_VIEW = None


def _json_clubs():
    """Clubes realmente habilitados por JSON, sin arrastrar equipos legacy."""
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


def _assignments():
    with APP.db() as conn:
        return conn.execute(
            "SELECT user_id, name FROM clubs ORDER BY name COLLATE NOCASE"
        ).fetchall()


def _current_club(user_id: int):
    with APP.db() as conn:
        row = conn.execute(
            "SELECT name FROM clubs WHERE user_id = ? LIMIT 1",
            (int(user_id),),
        ).fetchone()
    return str(row["name"]) if row else None


def _free_clubs(*, excluding_current: str | None = None):
    with APP.db() as conn:
        rows = conn.execute("SELECT name FROM clubs").fetchall()
    occupied = {str(row["name"] or "").casefold() for row in rows}
    current_key = str(excluding_current or "").casefold()
    return [
        club
        for club in _json_clubs()
        if club.casefold() not in occupied and club.casefold() != current_key
    ]


def _table_exists(conn, table_name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
        (table_name,),
    ).fetchone()
    return bool(row)


def _switch_assignment(user_id: int, expected_old: str, new_club: str, admin_id: int):
    """Cambia solo la asignación Discord↔club. Planteles/economía no se tocan."""
    valid = {name.casefold(): name for name in _json_clubs()}
    canonical_new = valid.get(str(new_club).casefold())
    if not canonical_new:
        return False, "El club destino ya no está habilitado por JSON."

    conn = APP.db()
    try:
        conn.execute("BEGIN IMMEDIATE")
        current = conn.execute(
            "SELECT name FROM clubs WHERE user_id = ? LIMIT 1",
            (int(user_id),),
        ).fetchone()
        if not current:
            conn.rollback()
            return False, "El usuario ya no tiene club asignado."

        old_club = str(current["name"])
        if old_club.casefold() != str(expected_old).casefold():
            conn.rollback()
            return False, f"La asignación cambió: ahora figura en {old_club}."

        occupied = conn.execute(
            """
            SELECT user_id FROM clubs
            WHERE name = ? COLLATE NOCASE AND user_id != ?
            LIMIT 1
            """,
            (canonical_new, int(user_id)),
        ).fetchone()
        if occupied:
            conn.rollback()
            return False, f"{canonical_new} ya está asignado a otro DT."

        conn.execute(
            "UPDATE clubs SET name = ? WHERE user_id = ?",
            (canonical_new, int(user_id)),
        )
        conn.execute(
            """
            INSERT INTO club_assignment_history (user_id, club, action, actor_id)
            VALUES (?, ?, 'CAMBIO_CLUB_ADMIN', ?)
            """,
            (int(user_id), canonical_new, int(admin_id)),
        )

        # Si el destino estaba publicado como vacante, cualquier solicitud activa
        # deja de ser válida. También cerramos solicitudes del propio DT: ya quedó
        # asignado nuevamente y no debe conservar pedidos simultáneos.
        if _table_exists(conn, "free_team_requests"):
            conn.execute(
                """
                UPDATE free_team_requests
                SET status = 'CERRADA_AUTOMATICA',
                    resolved_by = ?,
                    resolved_at = CURRENT_TIMESTAMP
                WHERE status IN ('PENDIENTE', 'EN_ESPERA')
                  AND (club = ? COLLATE NOCASE OR user_id = ?)
                """,
                (int(admin_id), canonical_new, int(user_id)),
            )

        conn.commit()
        return True, (old_club, canonical_new)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _member_label(guild: discord.Guild | None, user_id: int):
    if guild is not None:
        member = guild.get_member(int(user_id))
        if member is not None:
            return str(member.display_name or member.name)[:100]
    return f"Usuario {int(user_id)}"


def _club_emoji(guild: discord.Guild | None, club: str):
    if guild is None:
        return None
    try:
        return badge_selector._manual_badge_emoji(guild, club)
    except Exception:
        return None


class ManagerSelect(discord.ui.Select):
    def __init__(self, rows, guild):
        options = []
        for row in rows[:25]:
            user_id = int(row["user_id"])
            club = str(row["name"])
            options.append(
                discord.SelectOption(
                    label=_member_label(guild, user_id),
                    description=f"Actual: {club}"[:100],
                    value=str(user_id),
                    emoji=_club_emoji(guild, club),
                )
            )
        super().__init__(
            placeholder="Elegí el DT que va a cambiar de club",
            min_values=1,
            max_values=1,
            options=options,
        )

    async def callback(self, interaction: discord.Interaction):
        if not APP.es_admin(interaction):
            await interaction.response.send_message("⛔ Solo administradores.", ephemeral=True)
            return

        user_id = int(self.values[0])
        current = _current_club(user_id)
        if not current:
            await interaction.response.send_message(
                "⚠️ Ese usuario ya quedó sin club. Volvé a abrir la herramienta.",
                ephemeral=True,
            )
            return

        available = _free_clubs(excluding_current=current)
        if not available:
            await interaction.response.send_message(
                "⚠️ No hay otro club JSON libre para asignar.",
                ephemeral=True,
            )
            return

        embed = discord.Embed(
            title="🔄 CAMBIAR CLUB",
            description=(
                f"DT: <@{user_id}>\n"
                f"Club actual: **{current}**\n\n"
                "Elegí el nuevo club. Solo aparecen equipos libres."
            ),
            color=discord.Color.blurple(),
        )
        await interaction.response.edit_message(
            embed=embed,
            view=TargetClubView(user_id, current, available, interaction.guild),
        )


class ManagerSelectView(discord.ui.View):
    def __init__(self, rows, guild):
        super().__init__(timeout=180)
        self.add_item(ManagerSelect(rows, guild))
        self.add_item(admin_ui.BackAdminButton(row=1))


class TargetClubSelect(discord.ui.Select):
    def __init__(self, user_id: int, old_club: str, clubs, guild):
        self.user_id = int(user_id)
        self.old_club = str(old_club)
        options = [
            discord.SelectOption(
                label=club[:100],
                value=club,
                description="✅ Libre"[:100],
                emoji=_club_emoji(guild, club),
            )
            for club in clubs[:25]
        ]
        super().__init__(
            placeholder="Elegí el nuevo club",
            min_values=1,
            max_values=1,
            options=options,
        )

    async def callback(self, interaction: discord.Interaction):
        if not APP.es_admin(interaction):
            await interaction.response.send_message("⛔ Solo administradores.", ephemeral=True)
            return
        new_club = self.values[0]
        embed = discord.Embed(
            title="⚠️ CONFIRMAR CAMBIO DE CLUB",
            description=(
                f"<@{self.user_id}>\n\n"
                f"⬅️ **{self.old_club}**\n"
                f"➡️ **{new_club}**\n\n"
                "El bot conservará intactos los planteles y presupuestos. "
                f"**{self.old_club}** quedará libre."
            ),
            color=discord.Color.orange(),
        )
        await interaction.response.edit_message(
            embed=embed,
            view=ConfirmSwitchView(self.user_id, self.old_club, new_club),
        )


class TargetClubView(discord.ui.View):
    def __init__(self, user_id: int, old_club: str, clubs, guild):
        super().__init__(timeout=180)
        self.add_item(TargetClubSelect(user_id, old_club, clubs, guild))
        self.add_item(ChangeClubButton(label="VOLVER A ELEGIR DT", emoji="⬅️", row=1))


class ConfirmSwitchView(discord.ui.View):
    def __init__(self, user_id: int, old_club: str, new_club: str):
        super().__init__(timeout=120)
        self.user_id = int(user_id)
        self.old_club = str(old_club)
        self.new_club = str(new_club)

    @discord.ui.button(
        label="CONFIRMAR CAMBIO",
        emoji="🔄",
        style=discord.ButtonStyle.success,
    )
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not APP.es_admin(interaction):
            await interaction.response.send_message("⛔ Solo administradores.", ephemeral=True)
            return

        await interaction.response.defer()
        try:
            ok, result = _switch_assignment(
                self.user_id,
                self.old_club,
                self.new_club,
                interaction.user.id,
            )
        except Exception as exc:
            print(
                "ERROR AJAP cambio club: "
                f"user={self.user_id} old={self.old_club} new={self.new_club} "
                f"error={type(exc).__name__}: {exc}"
            )
            await interaction.edit_original_response(
                embed=discord.Embed(
                    title="❌ Cambio no realizado",
                    description="Ocurrió un error interno. No se confirmó el cambio de club.",
                    color=discord.Color.red(),
                ),
                view=admin_ui.ManagementView(),
            )
            return

        if not ok:
            await interaction.edit_original_response(
                embed=discord.Embed(
                    title="⚠️ Cambio no realizado",
                    description=str(result),
                    color=discord.Color.orange(),
                ),
                view=admin_ui.ManagementView(),
            )
            return

        old_club, new_club = result
        identity_ok = False
        vacancy_ok = False

        try:
            identity_ok = await club_identity.sync_member_identity(
                interaction.guild,
                self.user_id,
            )
        except Exception as exc:
            print(f"WARNING AJAP cambio club: identidad Discord pendiente: {exc}")

        try:
            vacancy_ok = await vacancies._publish_vacancy(interaction.guild, old_club)
        except Exception as exc:
            print(f"WARNING AJAP cambio club: vacante anterior no publicada: {exc}")

        embed = discord.Embed(
            title="✅ CLUB CAMBIADO",
            description=(
                f"<@{self.user_id}> fue reasignado correctamente.\n\n"
                f"⬅️ Club anterior: **{old_club}**\n"
                f"➡️ Nuevo club: **{new_club}**"
            ),
            color=discord.Color.green(),
        )
        embed.add_field(
            name="🏟️ Club anterior",
            value="Quedó libre" + (" y fue publicado como vacante." if vacancy_ok else "."),
            inline=False,
        )
        embed.add_field(
            name="🪪 Identidad Discord",
            value=(
                "Rol de club y apodo sincronizados."
                if identity_ok
                else "La DB quedó correcta; la identidad se reconciliará automáticamente al reconectar."
            ),
            inline=False,
        )
        embed.set_footer(text="El rol DT se conserva: cambiar de club no equivale a renunciar")
        await interaction.edit_original_response(embed=embed, view=admin_ui.ManagementView())

    @discord.ui.button(
        label="CANCELAR",
        emoji="✖️",
        style=discord.ButtonStyle.secondary,
    )
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(
            embed=discord.Embed(
                title="⚙️ GESTIÓN",
                description="Cambio de club cancelado.",
            ),
            view=admin_ui.ManagementView(),
        )


class ChangeClubButton(discord.ui.Button):
    def __init__(self, *, label="CAMBIAR CLUB", emoji="🔄", row=1):
        super().__init__(
            label=label,
            emoji=emoji,
            style=discord.ButtonStyle.primary,
            row=row,
            custom_id="ajap_admin_change_manager_club",
        )

    async def callback(self, interaction: discord.Interaction):
        if not APP.es_admin(interaction):
            await interaction.response.send_message("⛔ Solo administradores.", ephemeral=True)
            return

        rows = _assignments()
        if not rows:
            await interaction.response.send_message(
                "⚠️ No hay DTs con club asignado.",
                ephemeral=True,
            )
            return

        embed = discord.Embed(
            title="🔄 CAMBIAR CLUB DE UN DT",
            description=(
                "Elegí el DT que querés mover. Después vas a elegir únicamente entre "
                "los clubes JSON que estén libres."
            ),
            color=discord.Color.blurple(),
        )
        embed.set_footer(text="El cambio es directo: no hace falta renunciar primero")
        await interaction.response.edit_message(
            embed=embed,
            view=ManagerSelectView(rows, interaction.guild),
        )


def apply_admin_manager_switch_patch(runtime, bot):
    global APP, BOT, ORIGINAL_MANAGEMENT_VIEW
    APP = runtime
    BOT = bot
    if getattr(runtime, "_ajap_admin_manager_switch_patch", False):
        return

    ORIGINAL_MANAGEMENT_VIEW = admin_ui.ManagementView

    class ManagementWithClubSwitch(ORIGINAL_MANAGEMENT_VIEW):
        def __init__(self):
            super().__init__()
            # Gestión tiene espacio en la fila 1 junto a Exportar mercado.
            self.add_item(ChangeClubButton(row=1))

    ManagementWithClubSwitch.__name__ = "ManagementView"
    admin_ui.ManagementView = ManagementWithClubSwitch
    runtime.admin_switch_manager_club = _switch_assignment
    runtime._ajap_admin_manager_switch_patch = True
    print(
        "AJAP cambio de DT activo: Gestión > Cambiar club | "
        "DB atómica + rol/apodo sincronizado + club anterior libre"
    )


_original_apply_guild_isolation_patch = guild_isolation.apply_guild_isolation_patch


def _apply_guild_isolation_then_manager_switch(runtime, bot):
    _original_apply_guild_isolation_patch(runtime, bot)
    apply_admin_manager_switch_patch(runtime, bot)


if not getattr(
    guild_isolation.apply_guild_isolation_patch,
    "_ajap_admin_manager_switch_wrapped",
    False,
):
    _apply_guild_isolation_then_manager_switch._ajap_admin_manager_switch_wrapped = True
    guild_isolation.apply_guild_isolation_patch = _apply_guild_isolation_then_manager_switch
