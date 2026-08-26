"""Automatic DT role lifecycle for AJAP vacancy assignments.

Rules:
- /rol_dt configures the Discord role that grants market access for this guild.
- Accepting a free-team application grants DT before the club is assigned.
- If Discord cannot grant DT, the application is NOT accepted halfway.
- Unlinking a manager removes DT before freeing the club.
- A role named exactly "DT" is used as a safe fallback until /rol_dt is configured.
"""

from __future__ import annotations

import discord

import free_team_admin_decision_patch as decisions
import free_team_vacancy_patch as vacancies
import team_assignment as teams


APP = None
BOT = None


def _ensure_schema():
    with APP.db() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS dt_role_config (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                role_id INTEGER,
                configured_by INTEGER,
                configured_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )


def _set_role_id(role_id: int, admin_id: int):
    _ensure_schema()
    with APP.db() as conn:
        conn.execute(
            """
            INSERT INTO dt_role_config
                (id, role_id, configured_by, configured_at, updated_at)
            VALUES (1, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            ON CONFLICT(id) DO UPDATE SET
                role_id = excluded.role_id,
                configured_by = excluded.configured_by,
                updated_at = CURRENT_TIMESTAMP
            """,
            (int(role_id), int(admin_id)),
        )


def _get_role_id():
    _ensure_schema()
    with APP.db() as conn:
        row = conn.execute(
            "SELECT role_id FROM dt_role_config WHERE id = 1"
        ).fetchone()
    return int(row["role_id"]) if row and row["role_id"] else None


def _dt_role(guild):
    if guild is None:
        return None

    role_id = _get_role_id()
    if role_id:
        role = guild.get_role(int(role_id))
        if role is not None:
            return role

    # Zero-config fallback. Once /rol_dt is used, the stored role id wins.
    for role in getattr(guild, "roles", []):
        if (role.name or "").strip().casefold() == "dt":
            return role
    return None


def _bot_member(guild):
    if guild is None or BOT is None or BOT.user is None:
        return None
    member = getattr(guild, "me", None)
    if member is not None:
        return member
    return guild.get_member(BOT.user.id)


def _role_manage_error(guild, role):
    if role is None:
        return (
            "⚠️ No está configurado el rol **DT**. Ejecutá `/rol_dt` y elegí el rol "
            "que habilita el canal de mercado antes de aceptar la solicitud."
        )
    if role.is_default():
        return "⚠️ El rol @everyone no puede usarse como rol DT. Configurá otro rol con `/rol_dt`."
    if role.managed:
        return "⚠️ Ese rol está administrado por una integración y el bot no puede asignarlo."

    me = _bot_member(guild)
    if me is None:
        return "⚠️ No pude comprobar la jerarquía de roles del bot en este servidor."
    if not me.guild_permissions.manage_roles:
        return "⚠️ El bot necesita el permiso **Administrar roles** para entregar/quitar el rol DT."
    if me.top_role <= role:
        return (
            f"⚠️ El rol del bot debe estar **por encima de {role.mention}** en la lista de roles de Discord. "
            "Subí el rol del bot y volvé a intentar."
        )
    return None


async def _member(guild, user_id: int):
    if guild is None:
        return None
    member = guild.get_member(int(user_id))
    if member is None:
        try:
            member = await guild.fetch_member(int(user_id))
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            return None
    return member


async def _grant_dt(guild, user_id: int, reason: str):
    role = _dt_role(guild)
    error = _role_manage_error(guild, role)
    if error:
        return False, error, False

    member = await _member(guild, user_id)
    if member is None:
        return False, "⚠️ No pude encontrar al usuario dentro del servidor.", False

    if role in member.roles:
        return True, role, False

    try:
        await member.add_roles(role, reason=reason)
        return True, role, True
    except discord.Forbidden:
        return False, "⚠️ Discord no permitió asignar el rol DT. Revisá permisos y jerarquía de roles.", False
    except discord.HTTPException as exc:
        return False, f"⚠️ Discord no pudo asignar el rol DT: {exc}", False


async def _remove_dt(guild, user_id: int, reason: str, *, require_config=False):
    role = _dt_role(guild)
    if role is None:
        if require_config:
            return False, (
                "⚠️ No encontré el rol DT. Configuralo con `/rol_dt` antes de desvincular para evitar "
                "que el usuario conserve acceso al mercado."
            ), False
        return True, None, False

    error = _role_manage_error(guild, role)
    if error:
        return False, error, False

    member = await _member(guild, user_id)
    if member is None:
        return False, "⚠️ No pude encontrar al usuario dentro del servidor.", False

    if role not in member.roles:
        return True, role, False

    try:
        await member.remove_roles(role, reason=reason)
        return True, role, True
    except discord.Forbidden:
        return False, "⚠️ Discord no permitió quitar el rol DT. Revisá permisos y jerarquía de roles.", False
    except discord.HTTPException as exc:
        return False, f"⚠️ Discord no pudo quitar el rol DT: {exc}", False


def _install_accept_role_hook():
    BaseView = decisions.VacancyAdminDecisionView
    if getattr(BaseView, "_ajap_dt_role_accept", False):
        return

    class DTRoleVacancyAdminDecisionView(BaseView):
        async def _accept(self, interaction: discord.Interaction):
            # Resolve only to know the candidate before the base flow mutates anything.
            request = await self._resolve(interaction)
            if not request:
                return

            # Let the existing workflow own automatic rejections caused by stale club/user state.
            if not vacancies._club_is_free(request["club"]) or APP.club_de(int(request["user_id"])):
                await super()._accept(interaction)
                return

            ok, result, added_now = await _grant_dt(
                interaction.guild,
                int(request["user_id"]),
                reason=f"AJAP: vacante {request['club']} aceptada por admin {interaction.user.id}",
            )
            if not ok:
                await interaction.response.send_message(result, ephemeral=True)
                return

            try:
                await super()._accept(interaction)
            except Exception:
                if added_now:
                    try:
                        await _remove_dt(
                            interaction.guild,
                            int(request["user_id"]),
                            reason="AJAP: rollback por error al aceptar vacante",
                        )
                    except Exception:
                        pass
                raise

            # If a concurrent change made the base workflow reject instead of accept,
            # remove the role we had provisionally granted.
            fresh = decisions._request_by_id(int(request["id"]))
            if added_now and (not fresh or (fresh["status"] or "").upper() != "ACEPTADA"):
                await _remove_dt(
                    interaction.guild,
                    int(request["user_id"]),
                    reason="AJAP: vacante no aceptada finalmente",
                )

    DTRoleVacancyAdminDecisionView.__name__ = "VacancyAdminDecisionView"
    DTRoleVacancyAdminDecisionView._ajap_dt_role_accept = True
    decisions.VacancyAdminDecisionView = DTRoleVacancyAdminDecisionView
    APP.VacancyAdminDecisionView = DTRoleVacancyAdminDecisionView

    # Replace the global persistent handler for the same custom_ids.
    try:
        BOT.add_view(DTRoleVacancyAdminDecisionView())
    except ValueError:
        pass


def _install_unlink_role_hook():
    BaseView = teams.ConfirmUnlinkView
    if getattr(BaseView, "_ajap_dt_role_unlink", False):
        return

    class DTRoleConfirmUnlinkView(BaseView):
        def __init__(self, user_id, team):
            super().__init__(user_id, team)
            self.user_id = int(user_id)
            self.team = team

            for item in self.children:
                if not isinstance(item, discord.ui.Button) or item.label != "Desvincular equipo":
                    continue
                original_callback = item.callback

                async def unlink_with_role(interaction, _original=original_callback):
                    if not APP.es_admin(interaction):
                        await interaction.response.send_message("⛔ Solo admins.", ephemeral=True)
                        return

                    current = teams.club_de(self.user_id)
                    if not current or current.casefold() != self.team.casefold():
                        await interaction.response.send_message("⚠️ Esa asignación ya cambió.", ephemeral=True)
                        return

                    ok, result, removed_now = await _remove_dt(
                        interaction.guild,
                        self.user_id,
                        reason=f"AJAP: {self.team} desvinculado por admin {interaction.user.id}",
                        require_config=True,
                    )
                    if not ok:
                        await interaction.response.send_message(result, ephemeral=True)
                        return

                    try:
                        await _original(interaction)
                    except Exception:
                        if removed_now:
                            try:
                                await _grant_dt(
                                    interaction.guild,
                                    self.user_id,
                                    reason="AJAP: rollback por error al desvincular club",
                                )
                            except Exception:
                                pass
                        raise

                item.callback = unlink_with_role
                break

    DTRoleConfirmUnlinkView.__name__ = "ConfirmUnlinkView"
    DTRoleConfirmUnlinkView._ajap_dt_role_unlink = True
    teams.ConfirmUnlinkView = DTRoleConfirmUnlinkView


def _register_command():
    if BOT.tree.get_command("rol_dt") is not None:
        return

    @BOT.tree.command(
        name="rol_dt",
        description="Configura el rol DT que habilita el acceso al mercado",
    )
    async def rol_dt(interaction: discord.Interaction, rol: discord.Role):
        if not APP.es_admin(interaction):
            await interaction.response.send_message("⛔ Solo administradores.", ephemeral=True)
            return

        error = _role_manage_error(interaction.guild, rol)
        if error:
            await interaction.response.send_message(error, ephemeral=True)
            return

        _set_role_id(rol.id, interaction.user.id)
        await interaction.response.send_message(
            (
                f"✅ {rol.mention} quedó configurado como **rol DT**.\n\n"
                "• Aceptar una vacante: asigna club + entrega DT.\n"
                "• Desvincular un usuario: quita DT + libera el club."
            ),
            ephemeral=True,
        )


def apply_dt_role_patch(runtime, bot):
    global APP, BOT
    APP = runtime
    BOT = bot

    if getattr(runtime, "_ajap_dt_role_patch", False):
        return

    _ensure_schema()
    _install_accept_role_hook()
    _install_unlink_role_hook()
    _register_command()

    runtime.dt_role = _dt_role
    runtime._ajap_dt_role_patch = True
    print("AJAP rol DT activo: vacante aceptada => rol DT | desvinculación => quitar DT")
