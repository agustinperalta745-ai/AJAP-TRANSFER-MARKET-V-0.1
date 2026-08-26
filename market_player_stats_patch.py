"""Expose full PES 6/JSON player stats throughout the market workflow.

Market research should not require owning the player. Managers can inspect the
full stored PES 6 card before opening an offer and while evaluating an incoming
offer/counteroffer. This patch reuses roster_player_stats_patch as the single
renderer/source and never derives missing attributes from AJPA OVR.
"""

from __future__ import annotations

import discord

import global_player_search_patch as global_search
import inline_offer_actions_patch as inline_actions
import negotiation_picker_patch as negotiation
import offer_notifications_patch as offer_notifications
import publication_announce_patch as publication_announce
import roster_player_stats_patch as roster_stats
import split_transferibles_patch as transferibles


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _app():
    return (
        transferibles.APP
        or inline_actions.APP
        or publication_announce.APP
        or global_search.APP
        or negotiation.APP
    )


def _player_by_name(name):
    app = _app()
    return app.jugador_por_nombre(name) if app and name else None


def _full_stats_embed(player):
    return roster_stats.player_stats_embed(player)


def _append_full_stats(embed: discord.Embed, player):
    """Append the complete persisted PES6 card to an existing market embed."""
    attrs, abilities = roster_stats._attributes(int(player["id"]))

    # Remove the old 3-stat summary when this is the global-search card. The full
    # card below is more useful and avoids presenting the same data twice.
    for index in range(len(embed.fields) - 1, -1, -1):
        if embed.fields[index].name == "⭐ Atributos clave • PES 6":
            embed.remove_field(index)

    if not attrs:
        embed.add_field(
            name="📊 Estadísticas PES 6",
            value="Este jugador todavía no tiene estadísticas de JSON/PES 6 guardadas.",
            inline=False,
        )
        return embed

    for title, definitions in roster_stats.STAT_GROUPS:
        text = roster_stats._group_text(attrs, definitions)
        if text:
            embed.add_field(name=title, value=text, inline=False)

    if abilities:
        text = " • ".join(abilities)
        if len(text) > 1000:
            text = text[:997] + "..."
        embed.add_field(name="✨ Habilidades especiales", value=text, inline=False)

    return embed


# ---------------------------------------------------------------------------
# Global search: opening any player shows the complete stat sheet directly.
# ---------------------------------------------------------------------------
_original_global_player_embed = global_search.jugador_global_embed


def jugador_global_embed_with_full_stats(player):
    embed, publication = _original_global_player_embed(player)
    _append_full_stats(embed, player)
    return embed, publication


global_search.jugador_global_embed = jugador_global_embed_with_full_stats


# ---------------------------------------------------------------------------
# Transferibles: selecting another club's player opens a research/detail screen
# first. From there the manager can inspect all stats and then press Ofertar.
# ---------------------------------------------------------------------------

def _market_detail_embed(publication):
    app = _app()
    player = app.jugador_por_nombre(publication["player"])
    if not player:
        return discord.Embed(
            title=f"🔎 {publication['player']}",
            description="La ficha del jugador ya no está disponible.",
        )

    embed = discord.Embed(
        title=f"🔎 {player['name']} • Ficha de mercado",
        description="Revisá al jugador antes de decidir si querés negociar.",
    )
    embed.add_field(name="🏟️ Club", value=publication["club"], inline=True)
    embed.add_field(name="📍 Posición", value=player["position"], inline=True)
    rating = player["rating"] if "rating" in player.keys() else None
    embed.add_field(name="⭐ OVR AJPA", value=str(rating) if rating is not None else "—", inline=True)
    embed.add_field(name="🔁 Operación", value=publication["operation_type"], inline=True)
    embed.add_field(name="💰 Precio pedido", value=publication["price"], inline=True)
    minimum = player["min_sale_value"] if "min_sale_value" in player.keys() else None
    embed.add_field(
        name="📉 Valor mínimo",
        value=roster_stats._fmt_money(minimum),
        inline=True,
    )
    detail = str(publication["detail"] or "").strip()
    if detail and detail.casefold() != "sin observaciones":
        embed.add_field(name="📝 Condiciones", value=detail, inline=False)

    _append_full_stats(embed, player)
    embed.set_footer(text=f"Publicación #{publication['id']} • Evaluá y ofertá desde esta ficha")
    return embed


class TransferMarketDetailView(discord.ui.View):
    def __init__(self, publication_id: int, owner_id: int):
        super().__init__(timeout=300)
        self.publication_id = int(publication_id)
        self.owner_id = int(owner_id)

        offer = discord.ui.Button(
            label="Ofertar",
            emoji="💰",
            style=discord.ButtonStyle.success,
            row=0,
        )
        offer.callback = self._offer
        self.add_item(offer)

        back = discord.ui.Button(
            label="Volver a transferibles",
            emoji="⬅️",
            style=discord.ButtonStyle.secondary,
            row=0,
        )
        back.callback = self._back
        self.add_item(back)

    async def _offer(self, interaction: discord.Interaction):
        app = _app()
        publication = app.publicacion_por_id(self.publication_id)
        if not publication:
            await interaction.response.send_message(
                "⚠️ Esa publicación ya no está disponible.", ephemeral=True
            )
            return
        await negotiation._open_offer_picker(interaction, publication)

    async def _back(self, interaction: discord.Interaction):
        view = transferibles.SplitTransferiblesView(
            publicaciones=transferibles._active_publications(),
            owner_id=self.owner_id,
        )
        await interaction.response.edit_message(embed=view.embed(), view=view)


_original_transfer_select_callback = transferibles.SectionTransferiblesSelect.callback


async def _transfer_select_with_stats(self, interaction: discord.Interaction):
    app = _app()
    publication = app.publicacion_por_id(int(self.values[0]))
    if not publication:
        await interaction.response.send_message(
            "⚠️ Esa publicación ya no está disponible.", ephemeral=True
        )
        return

    # Keep the existing management path untouched for the owner's own listing.
    if int(publication["owner_id"]) == int(interaction.user.id):
        await _original_transfer_select_callback(self, interaction)
        return

    await interaction.response.edit_message(
        embed=_market_detail_embed(publication),
        view=TransferMarketDetailView(publication["id"], interaction.user.id),
    )


transferibles.SectionTransferiblesSelect.callback = _transfer_select_with_stats


# ---------------------------------------------------------------------------
# Public listing cards: add a neutral stats button next to Ofertar.
# The stats screen includes a back button that restores the publication card.
# ---------------------------------------------------------------------------

class PublicationStatsView(discord.ui.View):
    def __init__(self, publication_id: int):
        super().__init__(timeout=300)
        self.publication_id = int(publication_id)

        back = discord.ui.Button(
            label="Volver a la publicación",
            emoji="⬅️",
            style=discord.ButtonStyle.secondary,
            row=0,
        )
        back.callback = self._back
        self.add_item(back)

    async def _back(self, interaction: discord.Interaction):
        publication = publication_announce._active_publication(self.publication_id)
        if not publication:
            await interaction.response.edit_message(
                content="⚠️ Esta publicación ya no está disponible.",
                embed=None,
                view=None,
            )
            return

        await interaction.response.edit_message(
            content=None,
            embed=publication_announce.publication_embed(publication),
            view=publication_announce.PublicationOfferView(self.publication_id),
        )


_original_publication_view_init = publication_announce.PublicationOfferView.__init__


def _publication_view_init_with_stats(self, publication_id: int):
    _original_publication_view_init(self, publication_id)

    stats = discord.ui.Button(
        label="Ver estadísticas",
        emoji="📊",
        style=discord.ButtonStyle.secondary,
        custom_id=f"ajpa:publication:stats:{int(publication_id)}",
    )

    async def stats_callback(interaction: discord.Interaction):
        publication = publication_announce._active_publication(int(publication_id))
        if not publication:
            await interaction.response.send_message(
                "⚠️ Esta publicación ya no está disponible.", ephemeral=True
            )
            return
        player = _player_by_name(publication["player"])
        if not player:
            await interaction.response.send_message(
                "⚠️ No encontré la ficha de ese jugador.", ephemeral=True
            )
            return
        await interaction.response.send_message(
            embed=_full_stats_embed(player),
            view=PublicationStatsView(publication_id),
            ephemeral=True,
        )

    stats.callback = stats_callback
    self.add_item(stats)


publication_announce.PublicationOfferView.__init__ = _publication_view_init_with_stats


# ---------------------------------------------------------------------------
# Offer/counteroffer notices: everyone can inspect the target player and, when
# the proposal includes an exchange player, inspect that player's stats too.
# Business-action permissions remain enforced by the existing decision buttons.
# ---------------------------------------------------------------------------
_original_inline_view_init = inline_actions.InlineNegotiationDecisionView.__init__


def _inline_view_init_with_stats(self, offer_id):
    _original_inline_view_init(self, offer_id)
    offer_id = int(offer_id)

    target_stats = discord.ui.Button(
        label="Stats buscado",
        emoji="📊",
        style=discord.ButtonStyle.secondary,
        custom_id=f"ajpa:offer:{offer_id}:targetstats",
        row=1,
    )

    async def target_callback(interaction: discord.Interaction):
        app = _app()
        offer = app.oferta_por_id(offer_id)
        player = _player_by_name(offer["player"]) if offer else None
        if not player:
            await interaction.response.send_message(
                "⚠️ No encontré la ficha del jugador.", ephemeral=True
            )
            return
        await interaction.response.send_message(embed=_full_stats_embed(player), ephemeral=True)

    target_stats.callback = target_callback
    self.add_item(target_stats)

    app = _app()
    offer = app.oferta_por_id(offer_id) if app else None
    offered_name = None
    if offer and "offered_player" in offer.keys():
        offered_name = offer["offered_player"]

    if offered_name:
        offered_stats = discord.ui.Button(
            label="Stats ofrecido",
            emoji="🔁",
            style=discord.ButtonStyle.secondary,
            custom_id=f"ajpa:offer:{offer_id}:offeredstats",
            row=1,
        )

        async def offered_callback(interaction: discord.Interaction):
            current = _app().oferta_por_id(offer_id)
            name = current["offered_player"] if current and "offered_player" in current.keys() else None
            player = _player_by_name(name)
            if not player:
                await interaction.response.send_message(
                    "⚠️ La propuesta actual no incluye un jugador con ficha disponible.",
                    ephemeral=True,
                )
                return
            await interaction.response.send_message(embed=_full_stats_embed(player), ephemeral=True)

        offered_stats.callback = offered_callback
        self.add_item(offered_stats)


inline_actions.InlineNegotiationDecisionView.__init__ = _inline_view_init_with_stats

print(
    "AJPA mercado: estadísticas completas visibles en búsqueda, transferibles, "
    "publicaciones y negociaciones"
)
