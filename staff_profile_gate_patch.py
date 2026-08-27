"""Selector inicial de perfiles para administradores AJAP.

Regla final:
- /mercado ejecutado por un admin SIEMPRE abre primero el dashboard Staff con
  dos únicas opciones: PERFIL USUARIO y PERFIL ADMINISTRADOR.
- PERFIL USUARIO reproduce el flujo normal de un jugador, pero agrega VOLVER A
  STAFF para salir del modo prueba. Si el admin todavía no tiene club, ve el
  mismo selector de equipo que vería un usuario normal.
- PERFIL ADMINISTRADOR abre el panel ordenado de herramientas Staff.

Este parche se aplica después del dashboard y del panel admin organizado para
que ninguna capa visual posterior vuelva a mostrar directamente el menú manager.
"""

from __future__ import annotations

import discord

import guild_isolation_patch as guild_isolation
import manager_menu_patch as manager
import staff_dashboard_patch as staff_dashboard
import staff_admin_organized_patch as admin_tools


APP = None
BOT = None
_PRIOR_MANAGER_PANEL = None
_PRIOR_MARKET_VIEW_FOR = None
_MODES = {}  # (guild_id, user_id) -> "staff" | "user" | "admin"


def _guild_id(interaction=None):
    if interaction is not None and getattr(interaction, "guild_id", None):
        return int(interaction.guild_id)
    getter = getattr(APP, "current_guild_id", None)
    if getter:
        try:
            return int(getter())
        except Exception:
            pass
    return int(getattr(guild_isolation, "LEGACY_GUILD_ID", 0) or 0)


def _key(user_id, interaction=None):
    return (_guild_id(interaction), int(user_id))


def _set_mode(interaction, mode):
    _MODES[_key(interaction.user.id, interaction)] = mode


def _mode(user_id):
    return _MODES.get(_key(user_id))


def _normal_user_embed(user_id):
    # Cuando ya tiene club, el panel manager original es exactamente la ficha
    # que ve cualquier DT normal. El wrapper Staff solo debe usarse afuera del
    # modo usuario.
    original = getattr(staff_dashboard, "_ORIGINAL_MANAGER_PANEL_EMBED", None)
    if callable(original):
        return original(user_id)
    return _PRIOR_MANAGER_PANEL(user_id)


def _strip_admin_controls(view):
    for item in list(view.children):
        cid = str(getattr(item, "custom_id", "") or "")
        label = str(getattr(item, "label", "") or "").strip().casefold()
        if cid in {
            "ajap_manager_admin",
            "mercado_admin",
            "mercado_asignaciones",
        }:
            view.remove_item(item)
            continue
        if "administración" in label or label == "asignaciones":
            view.remove_item(item)
    return view


async def _defer_component(interaction: discord.Interaction):
    """Acknowledge component clicks before any DB/embed work can hit Discord's deadline."""
    if not interaction.response.is_done():
        await interaction.response.defer()


async def _followup_screen(
    interaction: discord.Interaction,
    *,
    embed=None,
    embeds=None,
    view=None,
):
    """Open the next profile screen as a fresh ephemeral followup.

    Editing an ephemeral component response has proven unreliable in the live
    Railway/discord.py stack. A deferred click + ephemeral followup uses the
    webhook token directly and avoids that failing edit path.
    """
    kwargs = {"ephemeral": True, "view": view}
    if embeds is not None:
        kwargs["embeds"] = embeds
    elif embed is not None:
        kwargs["embed"] = embed
    await interaction.followup.send(**kwargs)


class BackToStaffButton(discord.ui.Button):
    def __init__(self, row=4):
        super().__init__(
            label="VOLVER A STAFF",
            emoji="⬅️",
            style=discord.ButtonStyle.secondary,
            row=row,
            custom_id=f"ajap_profile_back_staff_{row}",
        )

    async def callback(self, interaction: discord.Interaction):
        if not APP.es_admin(interaction):
            await interaction.response.send_message("⛔ Solo administradores.", ephemeral=True)
            return
        await _defer_component(interaction)
        _set_mode(interaction, "staff")
        await _followup_screen(
            interaction,
            embed=staff_dashboard.staff_dashboard_embed(),
            view=StaffProfileChoiceView(),
        )


def _user_market_view(interaction):
    view = _PRIOR_MARKET_VIEW_FOR(interaction)
    _strip_admin_controls(view)
    if not any(getattr(item, "custom_id", "").startswith("ajap_profile_back_staff") for item in view.children):
        view.add_item(BackToStaffButton(row=4))
    return view


def _team_choice_view():
    import team_assignment as teams

    view = teams.TeamChoiceView()
    view.add_item(BackToStaffButton(row=1))
    return view


def _patch_admin_home_back_button():
    BaseAdminHome = admin_tools.OrganizedAdminHomeView
    if getattr(BaseAdminHome, "_ajap_profile_gate", False):
        return

    class ProfileAwareAdminHomeView(BaseAdminHome):
        def __init__(self):
            super().__init__()
            for item in list(self.children):
                label = str(getattr(item, "label", "") or "").strip().casefold()
                cid = str(getattr(item, "custom_id", "") or "")
                if label.startswith("volver") or cid.startswith("ajap_manager_back"):
                    self.remove_item(item)
            self.add_item(BackToStaffButton(row=2))

    ProfileAwareAdminHomeView.__name__ = "OrganizedAdminHomeView"
    ProfileAwareAdminHomeView._ajap_profile_gate = True
    admin_tools.OrganizedAdminHomeView = ProfileAwareAdminHomeView
    APP.AdminView = ProfileAwareAdminHomeView


class StaffProfileChoiceView(discord.ui.View):
    def __init__(self):
        # Persistent fallback lets custom_ids survive Railway redeploys.
        super().__init__(timeout=None)

    async def on_error(
        self,
        interaction: discord.Interaction,
        error: Exception,
        item: discord.ui.Item,
    ):
        detail = f"{type(error).__name__}: {error}"[:900]
        print(
            "ERROR AJAP perfil /mercado: "
            f"item={getattr(item, 'custom_id', None)} {detail}"
        )
        try:
            message = (
                "⚠️ No pude abrir ese perfil.\n"
                f"`{detail}`\n"
                "Ejecutá /mercado de nuevo si necesitás reintentar."
            )
            if not interaction.response.is_done():
                await interaction.response.send_message(message, ephemeral=True)
            else:
                await interaction.followup.send(message, ephemeral=True)
        except Exception:
            pass

    @discord.ui.button(
        label="PERFIL USUARIO",
        emoji="👤",
        style=discord.ButtonStyle.primary,
        row=0,
        custom_id="ajap_staff_profile_user",
    )
    async def user_profile(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not APP.es_admin(interaction):
            await interaction.response.send_message("⛔ Solo administradores.", ephemeral=True)
            return

        await _defer_component(interaction)
        _set_mode(interaction, "user")
        club = APP.club_de(interaction.user.id)
        if not club:
            import team_assignment as teams
            await _followup_screen(
                interaction,
                embed=teams.welcome_embed(),
                view=_team_choice_view(),
            )
            return

        await _followup_screen(
            interaction,
            embed=_normal_user_embed(interaction.user.id),
            view=_user_market_view(interaction),
        )

    @discord.ui.button(
        label="PERFIL ADMINISTRADOR",
        emoji="⚙️",
        style=discord.ButtonStyle.secondary,
        row=0,
        custom_id="ajap_staff_profile_admin",
    )
    async def admin_profile(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not APP.es_admin(interaction):
            await interaction.response.send_message("⛔ Solo administradores.", ephemeral=True)
            return

        await _defer_component(interaction)
        _set_mode(interaction, "admin")
        await _followup_screen(
            interaction,
            embed=admin_tools.admin_home_embed(),
            view=admin_tools.OrganizedAdminHomeView(),
        )


def apply_staff_profile_gate_patch(runtime, bot):
    global APP, BOT, _PRIOR_MANAGER_PANEL, _PRIOR_MARKET_VIEW_FOR
    APP = runtime
    BOT = bot

    if getattr(runtime, "_ajap_staff_profile_gate_patch", False):
        return

    _PRIOR_MANAGER_PANEL = manager.manager_panel_embed
    _PRIOR_MARKET_VIEW_FOR = manager.market_view_for
    _patch_admin_home_back_button()

    def mode_aware_panel(user_id):
        if _mode(user_id) == "user" and APP.club_de(user_id):
            return _normal_user_embed(user_id)
        return _PRIOR_MANAGER_PANEL(user_id)

    def mode_aware_market_view(interaction):
        if APP.es_admin(interaction) and _mode(interaction.user.id) == "user":
            return _user_market_view(interaction)
        return _PRIOR_MARKET_VIEW_FOR(interaction)

    async def mercado_command(interaction: discord.Interaction):
        if APP.es_admin(interaction):
            _set_mode(interaction, "staff")
            await interaction.response.send_message(
                embed=staff_dashboard.staff_dashboard_embed(),
                view=StaffProfileChoiceView(),
                ephemeral=True,
            )
            return

        # Para usuarios normales se conserva exactamente el flujo manager previo.
        if not APP.club_de(interaction.user.id):
            import team_assignment as teams
            await interaction.response.send_message(
                embed=teams.welcome_embed(),
                view=teams.TeamChoiceView(),
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            embed=_PRIOR_MANAGER_PANEL(interaction.user.id),
            view=_PRIOR_MARKET_VIEW_FOR(interaction),
            ephemeral=True,
        )

    manager.manager_panel_embed = mode_aware_panel
    manager.market_view_for = mode_aware_market_view
    runtime.panel_embed = mode_aware_panel
    runtime.manager_market_view_for = mode_aware_market_view
    runtime.market_view_for = mode_aware_market_view
    runtime.StaffProfileChoiceView = StaffProfileChoiceView

    try:
        bot.add_view(StaffProfileChoiceView())
    except Exception as exc:
        print(f"WARNING AJAP perfil persistente: {type(exc).__name__}: {exc}")

    bot.tree.remove_command("mercado")
    bot.tree.command(
        name="mercado",
        description="Abre el panel principal de AJAP Transfer Market",
    )(mercado_command)

    runtime._ajap_staff_profile_gate_patch = True
    print("AJAP Staff perfiles activo: /mercado -> Perfil Usuario / Perfil Administrador")


_original_apply_guild_isolation_patch = guild_isolation.apply_guild_isolation_patch


def _apply_guild_isolation_then_staff_profiles(runtime, bot):
    _original_apply_guild_isolation_patch(runtime, bot)
    apply_staff_profile_gate_patch(runtime, bot)


if not getattr(guild_isolation.apply_guild_isolation_patch, "_ajap_staff_profile_gate_wrapped", False):
    _apply_guild_isolation_then_staff_profiles._ajap_staff_profile_gate_wrapped = True
    guild_isolation.apply_guild_isolation_patch = _apply_guild_isolation_then_staff_profiles
