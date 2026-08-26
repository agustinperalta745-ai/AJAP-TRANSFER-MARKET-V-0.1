"""Panel principal estilo manager para AJAP Transfer Market.

Reordena la pantalla principal sin reemplazar la lógica existente: cada botón
nuevo delega en los callbacks finales ya parcheados (plantel OVR, publicaciones,
ofertas, búsqueda, clausulazo, administración, asignaciones y renuncia).
También integra la Liga AJAP en el mismo panel, manteniéndola separada del mercado.
"""

from __future__ import annotations

import discord

import guild_isolation_patch as guild_isolation
import league_automation_patch as league

APP = None
BOT = None


def _fmt_money(value):
    if value is None:
        return "Sin definir"
    try:
        return f"${int(value):,}".replace(",", ".")
    except (TypeError, ValueError):
        return str(value)


def _club_balance(club):
    if not club:
        return None
    getter = getattr(APP, "club_balance", None)
    if getter:
        try:
            return getter(club)
        except Exception:
            pass
    try:
        with APP.db() as conn:
            row = conn.execute(
                "SELECT balance FROM club_finances WHERE club = ? COLLATE NOCASE",
                (club,),
            ).fetchone()
        return int(row["balance"]) if row else None
    except Exception:
        return None


def _squad_value(players):
    value_fn = getattr(APP, "player_market_value", None)
    total = 0
    for player in players:
        try:
            if value_fn:
                total += int(value_fn(player) or 0)
            elif "min_sale_value" in player.keys() and player["min_sale_value"] is not None:
                total += int(player["min_sale_value"])
        except (TypeError, ValueError):
            continue
    return total


def manager_panel_embed(user_id: int):
    club = APP.club_de(user_id)
    open_market = APP.mercado_abierto()

    if club:
        players = list(APP.jugadores_de_club(club, 100))
        balance = _club_balance(club)
        squad_value = _squad_value(players)
        title = f"🏟️ {club.upper()}"
    else:
        players = []
        balance = None
        squad_value = 0
        title = "⚙️ AJAP TRANSFER MARKET • STAFF"

    embed = discord.Embed(
        title=title,
        description="━━━━━━━━━━━━━━━━━━━━",
    )
    embed.add_field(
        name="💰 Presupuesto",
        value=_fmt_money(balance) if club else "—",
        inline=False,
    )
    embed.add_field(
        name="👥 Jugadores",
        value=str(len(players)) if club else "—",
        inline=False,
    )
    embed.add_field(
        name="📈 Valor plantilla",
        value=_fmt_money(squad_value) if club else "—",
        inline=False,
    )
    embed.add_field(
        name="🔁 Mercado",
        value="🟢 ABIERTO" if open_market else "🔒 CERRADO",
        inline=False,
    )
    embed.set_footer(text="AJAP Transfer Market • PES 6")
    return embed


class CallbackButton(discord.ui.Button):
    def __init__(self, *, label, emoji, callback, style=discord.ButtonStyle.secondary, row=0, custom_id=None):
        super().__init__(
            label=label,
            emoji=emoji,
            style=style,
            row=row,
            custom_id=custom_id,
        )
        self._target = callback

    async def callback(self, interaction: discord.Interaction):
        await self._target(interaction)


class BackMainButton(discord.ui.Button):
    def __init__(self, row=4):
        super().__init__(
            label="Volver al menú",
            emoji="⬅️",
            style=discord.ButtonStyle.secondary,
            row=row,
            custom_id=f"ajap_manager_back_{row}",
        )

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.edit_message(
            content=None,
            embeds=[manager_panel_embed(interaction.user.id)],
            view=market_view_for(interaction),
        )


class BackMainView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=300)
        self.add_item(BackMainButton(row=0))


class MarketSectionView(discord.ui.View):
    def __init__(self, callbacks):
        super().__init__(timeout=300)
        row = 0
        specs = [
            ("mercado_publicar", "PUBLICAR", "📤", discord.ButtonStyle.success),
            ("mercado_transferibles", "TRANSFERIBLES", "📋", discord.ButtonStyle.primary),
            ("mercado_clausulazo", "CLAUSULAZO", "💥", discord.ButtonStyle.danger),
        ]
        for key, label, emoji, style in specs:
            cb = callbacks.get(key)
            if cb:
                self.add_item(
                    CallbackButton(
                        label=label,
                        emoji=emoji,
                        callback=cb,
                        style=style,
                        row=row,
                        custom_id=f"ajap_manager_section_{key}",
                    )
                )
        self.add_item(BackMainButton(row=1))


class AdminSectionView(discord.ui.View):
    def __init__(self, callbacks):
        super().__init__(timeout=300)
        specs = [
            ("mercado_admin", "ADMINISTRACIÓN", "⚙️", discord.ButtonStyle.primary),
            ("mercado_asignaciones", "ASIGNACIONES", "👥", discord.ButtonStyle.secondary),
        ]
        for key, label, emoji, style in specs:
            cb = callbacks.get(key)
            if cb:
                self.add_item(
                    CallbackButton(
                        label=label,
                        emoji=emoji,
                        callback=cb,
                        style=style,
                        row=0,
                        custom_id=f"ajap_manager_section_{key}",
                    )
                )
        self.add_item(BackMainButton(row=1))


class MarketHubButton(discord.ui.Button):
    def __init__(self, callbacks):
        super().__init__(
            label="MERCADO",
            emoji="🔁",
            style=discord.ButtonStyle.primary,
            row=0,
            custom_id="ajap_manager_market",
        )
        self.callbacks = callbacks

    async def callback(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="🔁 MERCADO DE PASES",
            description="Elegí qué querés hacer dentro del mercado.",
        )
        await interaction.response.edit_message(
            content=None,
            embeds=[embed],
            view=MarketSectionView(self.callbacks),
        )


class AdminHubButton(discord.ui.Button):
    def __init__(self, callbacks):
        super().__init__(
            label="ADMINISTRACIÓN",
            emoji="⚙️",
            style=discord.ButtonStyle.secondary,
            row=3,
            custom_id="ajap_manager_admin",
        )
        self.callbacks = callbacks

    async def callback(self, interaction: discord.Interaction):
        if not APP.es_admin(interaction):
            await interaction.response.send_message("⛔ Este menú es solo para administradores.", ephemeral=True)
            return
        embed = discord.Embed(
            title="⚙️ ADMINISTRACIÓN",
            description="Herramientas de gestión del mercado y asignaciones.",
        )
        await interaction.response.edit_message(
            content=None,
            embeds=[embed],
            view=AdminSectionView(self.callbacks),
        )


class LeagueButton(discord.ui.Button):
    def __init__(self):
        super().__init__(
            label="LIGA",
            emoji="🏆",
            style=discord.ButtonStyle.secondary,
            row=2,
            custom_id="ajap_manager_league",
        )

    async def callback(self, interaction: discord.Interaction):
        if not interaction.guild_id:
            await interaction.response.send_message("⚠️ La Liga solo está disponible dentro del servidor.", ephemeral=True)
            return
        conn = league.db(APP, interaction.guild_id)
        try:
            embeds = [league.standings_embed(conn), league.scorers_embed(conn)]
        finally:
            conn.close()
        await interaction.response.edit_message(
            content=None,
            embeds=embeds,
            view=BackMainView(),
        )


class ManagerMenuView(discord.ui.View):
    def __init__(self, base_view_cls):
        # This class is only used as an implementation helper and never instantiated directly.
        super().__init__(timeout=None)
        self.base_view_cls = base_view_cls


def build_manager_market_view(base_view):
    class FinalManagerMarketView(base_view):
        def __init__(self):
            super().__init__()

            callbacks = {}
            resignation_cb = None
            for item in list(self.children):
                cid = getattr(item, "custom_id", None)
                label = str(getattr(item, "label", "") or "")
                if cid:
                    callbacks[cid] = item.callback
                if label.casefold().startswith("renunciar"):
                    resignation_cb = item.callback

            self.clear_items()

            plantilla_cb = callbacks.get("mercado_mi_club")
            if plantilla_cb:
                self.add_item(
                    CallbackButton(
                        label="PLANTILLA",
                        emoji="👥",
                        callback=plantilla_cb,
                        style=discord.ButtonStyle.primary,
                        row=0,
                        custom_id="ajap_manager_roster",
                    )
                )

            self.add_item(MarketHubButton(callbacks))

            ofertas_cb = callbacks.get("mercado_ofertas")
            if ofertas_cb:
                self.add_item(
                    CallbackButton(
                        label="OFERTAS",
                        emoji="📩",
                        callback=ofertas_cb,
                        style=discord.ButtonStyle.secondary,
                        row=1,
                        custom_id="ajap_manager_offers",
                    )
                )

            buscar_cb = callbacks.get("mercado_buscar")
            if buscar_cb:
                self.add_item(
                    CallbackButton(
                        label="BUSCAR",
                        emoji="🔎",
                        callback=buscar_cb,
                        style=discord.ButtonStyle.secondary,
                        row=1,
                        custom_id="ajap_manager_search",
                    )
                )

            historial_cb = callbacks.get("mercado_transferencias")
            if historial_cb:
                self.add_item(
                    CallbackButton(
                        label="HISTORIAL",
                        emoji="📜",
                        callback=historial_cb,
                        style=discord.ButtonStyle.secondary,
                        row=2,
                        custom_id="ajap_manager_history",
                    )
                )

            self.add_item(LeagueButton())

            if callbacks.get("mercado_admin") or callbacks.get("mercado_asignaciones"):
                self.add_item(AdminHubButton(callbacks))

            if resignation_cb:
                self.add_item(
                    CallbackButton(
                        label="RENUNCIAR AL CLUB",
                        emoji="🚪",
                        callback=resignation_cb,
                        style=discord.ButtonStyle.danger,
                        row=4,
                        custom_id="ajap_manager_resign",
                    )
                )

    FinalManagerMarketView.__name__ = "MercadoView"
    return FinalManagerMarketView


def market_view_for(interaction: discord.Interaction):
    view = APP.MercadoView()

    if not APP.es_admin(interaction):
        for item in list(view.children):
            if getattr(item, "custom_id", None) == "ajap_manager_admin":
                view.remove_item(item)

    if not APP.club_de(interaction.user.id):
        for item in list(view.children):
            if getattr(item, "custom_id", None) == "ajap_manager_resign":
                view.remove_item(item)

    return view


async def mercado_command(interaction: discord.Interaction):
    # Staff can administrate without choosing a club. Normal users still must
    # choose one before seeing their personal market panel.
    if not APP.es_admin(interaction) and not APP.club_de(interaction.user.id):
        import team_assignment as teams
        await interaction.response.send_message(
            embed=teams.welcome_embed(),
            view=teams.TeamChoiceView(),
            ephemeral=True,
        )
        return

    await interaction.response.send_message(
        embed=manager_panel_embed(interaction.user.id),
        view=market_view_for(interaction),
        ephemeral=True,
    )


async def _navigation_back(self, interaction: discord.Interaction):
    await interaction.response.edit_message(
        content=None,
        embeds=[manager_panel_embed(interaction.user.id)],
        view=market_view_for(interaction),
    )


def apply_manager_menu_patch(runtime, bot):
    global APP, BOT
    APP = runtime
    BOT = bot
    if getattr(runtime, "_ajap_manager_menu_patch", False):
        return

    runtime.panel_embed = manager_panel_embed
    runtime.MercadoView = build_manager_market_view(runtime.MercadoView)
    runtime.manager_market_view_for = market_view_for

    # Re-register the slash command after all previous UI patches. The channel
    # gate and guild-isolation context are installed at tree dispatch level, so
    # this command keeps both protections.
    bot.tree.remove_command("mercado")
    bot.tree.command(
        name="mercado",
        description="Abre el panel principal de AJAP Transfer Market",
    )(mercado_command)

    # Existing secondary screens already use this button. Point it at the new
    # manager panel so navigation remains consistent everywhere.
    try:
        import navigation_patch as navigation
        navigation.MainMenuButton.callback = _navigation_back
    except Exception as exc:
        print(f"WARNING AJAP manager menu: no se pudo actualizar navegación: {exc}")

    runtime._ajap_manager_menu_patch = True
    print("AJAP panel manager activo: plantilla/mercado/ofertas/buscar/historial/liga/admin/renuncia")


# bot.py imports this module after the Liga/renuncia wrappers are installed and
# before run_bot invokes guild isolation. We become the outermost layer so the
# final menu sees every button/callback already instalado.
_original_apply_guild_isolation_patch = guild_isolation.apply_guild_isolation_patch


def _apply_guild_isolation_then_manager(runtime, bot):
    _original_apply_guild_isolation_patch(runtime, bot)
    apply_manager_menu_patch(runtime, bot)


if not getattr(
    guild_isolation.apply_guild_isolation_patch,
    "_ajap_manager_menu_wrapped",
    False,
):
    _apply_guild_isolation_then_manager._ajap_manager_menu_wrapped = True
    guild_isolation.apply_guild_isolation_patch = _apply_guild_isolation_then_manager
