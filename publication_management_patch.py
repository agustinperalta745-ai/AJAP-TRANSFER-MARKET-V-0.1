"""Owner controls for AJAP transfer-list publications.

When a manager selects one of their own active publications from Transferibles,
show management controls instead of trying to open the offer flow. Withdrawing a
listing keeps history intact and cancels any still-pending offers tied to it.
"""

import discord

import negotiation_picker_patch as negotiation


APP = None


def _owner_embed(publication):
    embed = discord.Embed(
        title="⚙️ Gestionar transferible",
        description=(
            f"**{publication['player']}** está publicado por **{publication['club']}**.\n\n"
            "Podés quitarlo de la lista de transferibles cuando quieras."
        ),
    )
    embed.add_field(name="🔁 Tipo", value=publication["operation_type"], inline=True)
    embed.add_field(name="💰 Precio", value=publication["price"], inline=True)
    detail = (publication["detail"] or "").strip()
    if detail and detail.casefold() != "sin observaciones":
        embed.add_field(name="📝 Condiciones", value=detail, inline=False)
    embed.set_footer(text=f"Publicación #{publication['id']} • Solo el propietario puede quitarla")
    return embed


class OwnerPublicationView(discord.ui.View):
    def __init__(self, publication_id: int, owner_id: int):
        super().__init__(timeout=300)
        self.publication_id = int(publication_id)
        self.owner_id = int(owner_id)

    @discord.ui.button(
        label="Quitar de transferibles",
        emoji="🗑️",
        style=discord.ButtonStyle.danger,
    )
    async def remove(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message(
                "⛔ Solo el propietario de la publicación puede quitarla.",
                ephemeral=True,
            )
            return

        publication = APP.publicacion_por_id(self.publication_id)
        if not publication:
            await interaction.response.send_message(
                "⚠️ Esta publicación ya no está activa.",
                ephemeral=True,
            )
            return
        if int(publication["owner_id"]) != int(interaction.user.id):
            await interaction.response.send_message(
                "⛔ Esta publicación no te pertenece.",
                ephemeral=True,
            )
            return

        with APP.db() as conn:
            pending = conn.execute(
                "SELECT COUNT(*) AS total FROM offers WHERE publication_id = ? AND status = 'PENDIENTE'",
                (self.publication_id,),
            ).fetchone()
            pending_count = int(pending["total"] if pending else 0)
            conn.execute(
                "UPDATE publications SET active = 0 WHERE id = ? AND owner_id = ? AND active = 1",
                (self.publication_id, interaction.user.id),
            )
            conn.execute(
                "UPDATE offers SET status = 'CANCELADA' WHERE publication_id = ? AND status = 'PENDIENTE'",
                (self.publication_id,),
            )

        embed = discord.Embed(
            title="🗑️ Jugador retirado de transferibles",
            description=(
                f"**{publication['player']}** ya no aparece en la lista de transferibles."
            ),
        )
        if pending_count:
            embed.add_field(
                name="Negociaciones",
                value=f"Se cancelaron **{pending_count} oferta(s) pendiente(s)** asociadas a esta publicación.",
                inline=False,
            )
        embed.set_footer(text=f"Publicación #{self.publication_id} conservada en el historial")
        await interaction.response.edit_message(embed=embed, view=None)


async def _transferibles_owner_aware_callback(select_self, interaction: discord.Interaction):
    publication = APP.publicacion_por_id(int(select_self.values[0]))
    if not publication:
        await interaction.response.send_message("Publicación no disponible.", ephemeral=True)
        return

    if int(publication["owner_id"]) == int(interaction.user.id):
        await interaction.response.send_message(
            embed=_owner_embed(publication),
            view=OwnerPublicationView(publication["id"], publication["owner_id"]),
            ephemeral=True,
        )
        return

    await negotiation._open_offer_picker(interaction, publication)


def apply_publication_management_patch(runtime):
    global APP
    APP = runtime
    if getattr(runtime, "_ajap_publication_management_patch", False):
        return

    # negotiation_picker_patch already owns this callback for buyers. This final
    # layer only intercepts the owner's own listings and delegates every other
    # selection back to the normal offer flow.
    runtime.TransferiblesSelect.callback = _transferibles_owner_aware_callback
    runtime.OwnerPublicationView = OwnerPublicationView
    runtime._ajap_publication_management_patch = True
    print("AJAP gestión de publicaciones activa: propietario puede quitar transferibles")
