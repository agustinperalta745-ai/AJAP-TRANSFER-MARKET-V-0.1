"""Submenú MI CLUB para el panel manager de AJAP Transfer Market.

Convierte el acceso directo PLANTILLA del menú principal en MI CLUB y agrupa
ahí plantilla, economía, valor del club e información general. El resto del
panel conserva exactamente sus callbacks actuales.
"""

from __future__ import annotations

import discord

import guild_isolation_patch as guild_isolation
import manager_menu_patch as manager


APP = None
BOT = None


def _guild_context(interaction: discord.Interaction):
    """Mantiene la DB del servidor correcto dentro del task real del botón."""
    return guild_isolation._CURRENT_GUILD_ID.set(
        guild_isolation._interaction_guild_id(interaction)
    )


def _reset_guild_context(token):
    guild_isolation._CURRENT_GUILD_ID.reset(token)


def _club_players(club):
    if not club:
        return []
    try:
        return list(APP.jugadores_de_club(club, 100))
    except Exception:
        return []


def _club_snapshot(user_id: int):
    club = APP.club_de(user_id)
    players = _club_players(club)
    balance = manager._club_balance(club) if club else None
    squad_value = manager._squad_value(players) if club else 0
    return club, players, balance, squad_value


def my_club_embed(user_id: int):
    club, players, balance, squad_value = _club_snapshot(user_id)
    if not club:
        return discord.Embed(
            title="🏟️ MI CLUB",
            description="No tenés un club asignado en este servidor.",
        )

    embed = discord.Embed(
        title=f"🏟️ MI CLUB • {club.upper()}",
        description="Gestión general de tu equipo.",
    )
    embed.add_field(name="💰 Presupuesto", value=manager._fmt_money(balance), inline=True)
    embed.add_field(name="👥 Jugadores", value=str(len(players)), inline=True)
    embed.add_field(name="📊 Valor plantilla", value=manager._fmt_money(squad_value), inline=True)
    embed.set_footer(text="AJAP Transfer Market • PES 6")
    return embed


def economy_embed(user_id: int):
    club, players, balance, squad_value = _club_snapshot(user_id)
    if not club:
        return my_club_embed(user_id)

    embed = discord.Embed(
        title=f"💰 ECONOMÍA • {club.upper()}",
        description="Estado económico actual del club.",
    )
    embed.add_field(
        name="Presupuesto disponible",
        value=manager._fmt_money(balance),
        inline=False,
    )
    embed.add_field(
        name="Valor de la plantilla",
        value=manager._fmt_money(squad_value),
        inline=False,
    )
    embed.add_field(
        name="Jugadores en plantilla",
        value=str(len(players)),
        inline=False,
    )
    embed.set_footer(text="AJAP Transfer Market • PES 6")
    return embed


def club_value_embed(user_id: int):
    club, players, balance, squad_value = _club_snapshot(user_id)
    if not club:
        return my_club_embed(user_id)

    average = int(squad_value / len(players)) if players else 0
    embed = discord.Embed(
        title=f"📊 VALOR DEL CLUB • {club.upper()}",
        description="Valoración económica estimada de la plantilla actual.",
    )
    embed.add_field(
        name="Valor total de plantilla",
        value=manager._fmt_money(squad_value),
        inline=False,
    )
    embed.add_field(
        name="Valor promedio por jugador",
        value=manager._fmt_money(average),
        inline=False,
    )
    embed.add_field(
        name="Cantidad de jugadores",
        value=str(len(players)),
        inline=False,
    )
    embed.set_footer(text="AJAP Transfer Market • PES 6")
    return embed


def club_info_embed(interaction: discord.Interaction):
    club, players, balance, squad_value = _club_snapshot(interaction.user.id)
    if not club:
        return my_club_embed(interaction.user.id)

    market_status = "🟢 ABIERTO" if APP.mercado_abierto() else "🔒 CERRADO"
    manager_name = getattr(interaction.user, "display_name", None) or str(interaction.user)
    embed = discord.Embed(
        title=f"ℹ️ INFORMACIÓN • {club.upper()}",
        description="Ficha general del club dentro de AJAP Transfer Market.",
    )
    embed.add_field(name="Club", value=club, inline=False)
    embed.add_field(name="DT", value=manager_name, inline=False)
    embed.add_field(name="Jugadores", value=str(len(players)), inline=True)
    embed.add_field(name="Mercado", value=market_status, inline=True)
    embed.add_field(name="Presupuesto", value=manager._fmt_money(balance), inline=False)
    embed.add_field(name="Valor plantilla", value=manager._fmt_money(squad_value), inline=False)
    embed.set_footer(text="AJAP Transfer Market • PES 6")
    return embed


class MyClubSectionButton(discord.ui.Button):
    def __init__(self, *, label, emoji, action, roster_callback, row=0):
        super().__init__(
            label=label,
            emoji=emoji,
            style=discord.ButtonStyle.secondary,
            row=row,
            custom_id=f"ajap_my_club_{action}",
        )
        self.action = action
        self.roster_callback = roster_callback

    async def callback(self, interaction: discord.Interaction):
        token = _guild_context(interaction)
        try:
            if self.action == "plantilla":
                await self.roster_callback(interaction)
                return

            if self.action == "economia":
                embed = economy_embed(interaction.user.id)
            elif self.action == "valor":
                embed = club_value_embed(interaction.user.id)
            else:
                embed = club_info_embed(interaction)

            await interaction.response.edit_message(
                content=None,
                embeds=[embed],
                view=MyClubSectionView(self.roster_callback),
            )
        finally:
            _reset_guild_context(token)


class MyClubSectionView(discord.ui.View):
    def __init__(self, roster_callback):
        super().__init__(timeout=300)
        self.add_item(
            MyClubSectionButton(
                label="PLANTILLA",
                emoji="👥",
                action="plantilla",
                roster_callback=roster_callback,
                row=0,
            )
        )
        self.add_item(
            MyClubSectionButton(
                label="ECONOMÍA",
                emoji="💰",
                action="economia",
                roster_callback=roster_callback,
                row=0,
            )
        )
        self.add_item(
            MyClubSectionButton(
                label="VALOR DEL CLUB",
                emoji="📊",
                action="valor",
                roster_callback=roster_callback,
                row=0,
            )
        )
        self.add_item(
            MyClubSectionButton(
                label="INFORMACIÓN",
                emoji="ℹ️",
                action="info",
                roster_callback=roster_callback,
                row=0,
            )
        )
        self.add_item(manager.BackMainButton(row=1))


class MyClubHubButton(discord.ui.Button):
    def __init__(self, roster_callback):
        super().__init__(
            label="MI CLUB",
            emoji="🏟️",
            style=discord.ButtonStyle.primary,
            row=0,
            custom_id="ajap_manager_my_club",
        )
        self.roster_callback = roster_callback

    async def callback(self, interaction: discord.Interaction):
        token = _guild_context(interaction)
        try:
            if not APP.club_de(interaction.user.id):
                await interaction.response.send_message(
                    "⚠️ No tenés un club asignado en este servidor.",
                    ephemeral=True,
                )
                return

            await interaction.response.edit_message(
                content=None,
                embeds=[my_club_embed(interaction.user.id)],
                view=MyClubSectionView(self.roster_callback),
            )
        finally:
            _reset_guild_context(token)


def build_my_club_market_view(base_view):
    class FinalMyClubMarketView(base_view):
        def __init__(self):
            super().__init__()

            roster_item = None
            for item in list(self.children):
                if getattr(item, "custom_id", None) == "ajap_manager_roster":
                    roster_item = item
                    break

            if roster_item is None:
                return

            roster_callback = roster_item.callback
            old_children = list(self.children)
            self.clear_items()

            self.add_item(MyClubHubButton(roster_callback))
            for item in old_children:
                if item is roster_item:
                    continue
                self.add_item(item)

    FinalMyClubMarketView.__name__ = "MercadoView"
    return FinalMyClubMarketView


def apply_my_club_menu_patch(runtime, bot):
    global APP, BOT
    APP = runtime
    BOT = bot

    if getattr(runtime, "_ajap_my_club_menu_patch", False):
        return

    runtime.MercadoView = build_my_club_market_view(runtime.MercadoView)

    base_market_view_for = manager.market_view_for

    def market_view_for(interaction: discord.Interaction):
        view = base_market_view_for(interaction)

        if not APP.club_de(interaction.user.id):
            for item in list(view.children):
                if getattr(item, "custom_id", None) == "ajap_manager_my_club":
                    view.remove_item(item)

        return view

    manager.market_view_for = market_view_for
    runtime.manager_market_view_for = market_view_for

    runtime._ajap_my_club_menu_patch = True
    print("AJAP MI CLUB activo: plantilla/economía/valor/información")


_original_apply_guild_isolation_patch = guild_isolation.apply_guild_isolation_patch


def _apply_guild_isolation_then_my_club(runtime, bot):
    _original_apply_guild_isolation_patch(runtime, bot)
    apply_my_club_menu_patch(runtime, bot)


if not getattr(
    guild_isolation.apply_guild_isolation_patch,
    "_ajap_my_club_menu_wrapped",
    False,
):
    _apply_guild_isolation_then_my_club._ajap_my_club_menu_wrapped = True
    guild_isolation.apply_guild_isolation_patch = _apply_guild_isolation_then_my_club
