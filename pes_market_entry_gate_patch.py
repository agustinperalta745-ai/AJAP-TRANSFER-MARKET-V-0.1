"""Require every active AJAP manager to link their PES username before using /mercado.

This is deliberately retroactive. Having a club assigned is not enough: if the
manager does not yet have a row in ``pes_username_links``, /mercado opens a
single-purpose PES-link screen and the rest of the market is blocked. Existing
links remain valid and are never requested again.

Staff members without an assigned club are not trapped by this manager gate;
the existing Staff/admin access rules continue to apply to them. As soon as a
user has an assigned club, however, the PES link is mandatory even if that user
is also an administrator.
"""

from __future__ import annotations

import discord

import guild_isolation_patch as guild_isolation
import pes_username_link_patch as pes


APP = None
BOT = None


def _assigned_club(guild_id: int, user_id: int):
    if APP is None:
        return None
    return pes._club_for_user(APP, int(guild_id), int(user_id))


def _saved_link(guild_id: int, user_id: int):
    if APP is None:
        return None
    return pes._link_for_user(APP, int(guild_id), int(user_id))


def _requires_pes_link(guild_id: int | None, user_id: int) -> bool:
    """Only active managers are gated; assigned managers must all be linked."""
    if guild_id is None:
        return False
    club = _assigned_club(int(guild_id), int(user_id))
    if not club:
        return False
    return _saved_link(int(guild_id), int(user_id)) is None


def _required_embed(club: str):
    embed = discord.Embed(
        title="🎮 ENLAZÁ TU USUARIO DE PES",
        description=(
            "Antes de entrar al mercado tenés que asociar **una sola vez** el nombre "
            "de usuario que usás en PES 6.\n\n"
            "Esto permite identificar tu equipo por tu usuario en las capturas y evita "
            "depender de los nombres de clubes que muestra PES."
        ),
    )
    embed.add_field(name="🏟️ Tu club", value=club, inline=True)
    embed.add_field(name="🔒 Mercado", value="Bloqueado hasta enlazar tu usuario PES", inline=False)
    embed.set_footer(text="AJAP • El enlace queda guardado y no se vuelve a pedir")
    return embed


async def _send_required(interaction: discord.Interaction):
    club = _assigned_club(interaction.guild_id, interaction.user.id) if interaction.guild_id else None
    embed = _required_embed(club or "Club asignado")
    view = PesRequiredEntryView()
    if not interaction.response.is_done():
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
    else:
        await interaction.followup.send(embed=embed, view=view, ephemeral=True)


class OpenMarketAfterLinkButton(discord.ui.Button):
    def __init__(self):
        super().__init__(
            label="ENTRAR AL MERCADO",
            emoji="➡️",
            style=discord.ButtonStyle.success,
            row=0,
        )

    async def callback(self, interaction: discord.Interaction):
        if not interaction.guild_id:
            await interaction.response.send_message(
                "⚠️ Esta opción solo funciona dentro del servidor.", ephemeral=True
            )
            return
        if _requires_pes_link(interaction.guild_id, interaction.user.id):
            await _send_required(interaction)
            return
        await interaction.response.send_message(
            embed=APP.panel_embed(interaction.user.id),
            view=APP.MercadoView(),
            ephemeral=True,
        )


class OpenMarketAfterLinkView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=300)
        self.add_item(OpenMarketAfterLinkButton())


class RequiredPesUsernameModal(discord.ui.Modal):
    def __init__(self, current_username: str | None = None):
        super().__init__(title="Enlazar usuario de PES")
        self.username_input = discord.ui.TextInput(
            label="Nombre de usuario PES",
            placeholder="Escribilo exactamente como aparece en PES 6",
            default=current_username or None,
            required=True,
            max_length=40,
        )
        self.add_item(self.username_input)

    async def on_submit(self, interaction: discord.Interaction):
        if not interaction.guild_id:
            await interaction.response.send_message(
                "⚠️ Este enlace solo se puede guardar dentro del servidor.",
                ephemeral=True,
            )
            return

        club = _assigned_club(interaction.guild_id, interaction.user.id)
        if not club:
            await interaction.response.send_message(
                "⛔ Primero tenés que tener un club asignado.", ephemeral=True
            )
            return

        try:
            username = pes._save_link(
                APP,
                interaction.guild_id,
                interaction.user.id,
                str(self.username_input.value),
            )
        except ValueError as exc:
            await interaction.response.send_message(f"⚠️ {exc}", ephemeral=True)
            return
        except Exception as exc:
            print(
                "AJAP PES market gate: error guardando enlace "
                f"{type(exc).__name__}: {exc}"
            )
            await interaction.response.send_message(
                "❌ No pude guardar el enlace. No se modificó nada.",
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            (
                f'✅ Usuario PES **{discord.utils.escape_markdown(username)}** enlazado a **{club}**.\n'
                "Ya quedó habilitado tu acceso al mercado y **no te lo voy a volver a pedir**."
            ),
            view=OpenMarketAfterLinkView(),
            ephemeral=True,
        )


class RequiredPesUsernameButton(discord.ui.Button):
    def __init__(self):
        super().__init__(
            label="ENLAZAR USUARIO PES",
            emoji="🎮",
            style=discord.ButtonStyle.primary,
            row=0,
        )

    async def callback(self, interaction: discord.Interaction):
        if not interaction.guild_id:
            await interaction.response.send_message(
                "⚠️ Esta opción solo funciona dentro del servidor.", ephemeral=True
            )
            return
        club = _assigned_club(interaction.guild_id, interaction.user.id)
        if not club:
            await interaction.response.send_message(
                "⛔ Primero tenés que tener un club asignado.", ephemeral=True
            )
            return
        current = _saved_link(interaction.guild_id, interaction.user.id)
        await interaction.response.send_modal(
            RequiredPesUsernameModal(current["pes_username"] if current else None)
        )


class PesRequiredEntryView(discord.ui.View):
    """The only screen an unlinked active manager gets from /mercado."""

    def __init__(self):
        super().__init__(timeout=300)
        self.add_item(RequiredPesUsernameButton())


def _wrap_market_view(runtime):
    base_view = runtime.MercadoView
    if getattr(base_view, "_ajap_required_pes_market_gate", False):
        return

    class PesRequiredMarketView(base_view):
        _ajap_required_pes_market_gate = True

        async def interaction_check(self, interaction: discord.Interaction) -> bool:
            guild_id = interaction.guild_id
            user_id = interaction.user.id
            if _requires_pes_link(guild_id, user_id):
                data = getattr(interaction, "data", None) or {}
                custom_id = data.get("custom_id") if isinstance(data, dict) else None
                # Old/persistent market panels may still expose the optional PES
                # button. Let that one through so the user can satisfy the gate.
                if str(custom_id or "") == "ajap_manager_pes_username":
                    return True
                await _send_required(interaction)
                return False

            parent_check = getattr(super(), "interaction_check", None)
            if parent_check is None:
                return True
            result = parent_check(interaction)
            if hasattr(result, "__await__"):
                result = await result
            return bool(result)

    PesRequiredMarketView.__name__ = getattr(base_view, "__name__", "MercadoView")
    runtime.MercadoView = PesRequiredMarketView


def _wrap_market_command(runtime, bot):
    command = bot.tree.get_command("mercado")
    if command is None or getattr(command, "_ajap_required_pes_market_gate", False):
        return

    base_callback = getattr(command, "_callback", None)
    if base_callback is None:
        base_callback = getattr(command, "callback", None)
    if base_callback is None:
        print("WARNING AJAP PES market gate: /mercado callback no encontrado")
        return

    async def gated_market_command(interaction: discord.Interaction, *args, **kwargs):
        if _requires_pes_link(interaction.guild_id, interaction.user.id):
            await _send_required(interaction)
            return None
        return await base_callback(interaction, *args, **kwargs)

    gated_market_command.__name__ = getattr(base_callback, "__name__", "mercado")
    gated_market_command._ajap_required_pes_market_gate = True

    if hasattr(command, "_callback"):
        command._callback = gated_market_command
    else:
        command.callback = gated_market_command
    command._ajap_required_pes_market_gate = True


def _install(runtime, bot):
    global APP, BOT
    APP, BOT = runtime, bot
    if getattr(runtime, "_ajap_required_pes_market_gate", False):
        return

    _wrap_market_view(runtime)
    _wrap_market_command(runtime, bot)

    runtime.market_requires_pes_link = _requires_pes_link
    runtime._ajap_required_pes_market_gate = True
    print(
        "AJAP mercado: usuario PES obligatorio para todo DT con club "
        "(retroactivo, una sola vez)"
    )


_ORIGINAL_APPLY = guild_isolation.apply_guild_isolation_patch


def _apply(runtime, bot):
    _ORIGINAL_APPLY(runtime, bot)
    _install(runtime, bot)


if not getattr(
    guild_isolation.apply_guild_isolation_patch,
    "_ajap_required_pes_market_gate_wrapper",
    False,
):
    _apply._ajap_required_pes_market_gate_wrapper = True
    guild_isolation.apply_guild_isolation_patch = _apply
