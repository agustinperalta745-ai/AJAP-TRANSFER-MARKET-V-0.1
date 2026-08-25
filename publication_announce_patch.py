"""Public announcements for new AJAP transfer-list publications.

After a publication is successfully stored, post a visible announcement in the
same Discord channel where the manager submitted it. Failed validations never
produce an announcement and notification failures never roll back the listing.
"""

import discord

import lyon_test_seed as lyon
import publish_ovr_patch as publish


APP = None


def _last_publication_id(player: str, owner_id: int) -> int:
    with APP.db() as conn:
        row = conn.execute(
            """
            SELECT COALESCE(MAX(id), 0) AS last_id
            FROM publications
            WHERE player = ? COLLATE NOCASE AND owner_id = ?
            """,
            (player, int(owner_id)),
        ).fetchone()
    return int(row["last_id"] if row else 0)


def _new_publication(player: str, owner_id: int, after_id: int):
    with APP.db() as conn:
        return conn.execute(
            """
            SELECT * FROM publications
            WHERE player = ? COLLATE NOCASE
              AND owner_id = ?
              AND id > ?
              AND active = 1
            ORDER BY id DESC
            LIMIT 1
            """,
            (player, int(owner_id), int(after_id)),
        ).fetchone()


def _active_publication(publication_id: int):
    with APP.db() as conn:
        return conn.execute(
            "SELECT * FROM publications WHERE id = ? AND active = 1 LIMIT 1",
            (int(publication_id),),
        ).fetchone()


def _active_publication_ids():
    with APP.db() as conn:
        rows = conn.execute(
            "SELECT id FROM publications WHERE active = 1 ORDER BY id ASC"
        ).fetchall()
    return [int(row["id"]) for row in rows]


def _fmt_minimum(player):
    if not player or "min_sale_value" not in player.keys() or player["min_sale_value"] is None:
        return "No definido"
    try:
        return APP.money(str(int(player["min_sale_value"])))
    except (TypeError, ValueError):
        return str(player["min_sale_value"])


def publication_embed(publication):
    player = APP.jugador_por_nombre(publication["player"])
    club = publication["club"]
    name = publication["player"]

    embed = discord.Embed(
        title="📢 NUEVO JUGADOR EN TRANSFERIBLES",
        description=(
            f"**{club}** añadió a **{name}** a la lista de transferibles."
        ),
    )

    if player:
        details = []
        if "position" in player.keys() and player["position"]:
            details.append(str(player["position"]))
        if "rating" in player.keys() and player["rating"] is not None:
            details.append(f"⭐ OVR {player['rating']}")
        if details:
            embed.add_field(name="⚽ Jugador", value=f"**{name}** • " + " • ".join(details), inline=False)
        else:
            embed.add_field(name="⚽ Jugador", value=f"**{name}**", inline=False)
    else:
        embed.add_field(name="⚽ Jugador", value=f"**{name}**", inline=False)

    embed.add_field(name="🏟️ Club", value=club, inline=True)
    embed.add_field(name="🔁 Tipo", value=publication["operation_type"], inline=True)
    embed.add_field(name="💰 Precio solicitado", value=publication["price"], inline=True)
    embed.add_field(name="📉 Valor mínimo", value=_fmt_minimum(player), inline=True)

    detail = (publication["detail"] or "").strip()
    if detail and detail.casefold() != "sin observaciones":
        embed.add_field(name="📝 Condiciones", value=detail, inline=False)

    embed.set_footer(text=f"Publicación #{publication['id']} • AJAP Transfer Market")
    return embed


class PublicationOfferView(discord.ui.View):
    """Persistent public button that jumps straight into the offer flow."""

    def __init__(self, publication_id: int):
        super().__init__(timeout=None)
        self.publication_id = int(publication_id)
        button = discord.ui.Button(
            label="Ofertar",
            emoji="💰",
            style=discord.ButtonStyle.success,
            custom_id=f"ajap:publication:offer:{self.publication_id}",
        )
        button.callback = self._offer
        self.add_item(button)

    async def _offer(self, interaction: discord.Interaction):
        publication = _active_publication(self.publication_id)
        if not publication:
            await interaction.response.send_message(
                "⚠️ Esta publicación ya no está disponible.",
                ephemeral=True,
            )
            return

        # Import here to avoid changing startup order. By the time Discord is
        # connected, negotiation_picker_patch has already been applied.
        import negotiation_picker_patch as negotiation

        if negotiation.APP is None:
            await interaction.response.send_message(
                "⚠️ El menú de ofertas todavía no está disponible.",
                ephemeral=True,
            )
            return
        await negotiation._open_offer_picker(interaction, publication)


async def _send_public_announcement(interaction: discord.Interaction, publication):
    channel = interaction.channel
    if channel is None or not hasattr(channel, "send"):
        return False
    try:
        await channel.send(
            content="@everyone",
            embed=publication_embed(publication),
            view=PublicationOfferView(publication["id"]),
            allowed_mentions=discord.AllowedMentions(
                everyone=True,
                users=False,
                roles=False,
                replied_user=False,
            ),
        )
        return True
    except (discord.Forbidden, discord.HTTPException) as exc:
        print(f"WARNING AJAP: anuncio publicación #{publication['id']} falló: {exc}")
        return False


def _register_persistent_offer_views(runtime):
    registered = 0
    for publication_id in _active_publication_ids():
        try:
            runtime.bot.add_view(PublicationOfferView(publication_id))
            registered += 1
        except ValueError as exc:
            print(
                f"WARNING AJAP: no se pudo registrar botón persistente de publicación "
                f"#{publication_id}: {exc}"
            )
    return registered


def apply_publication_announce_patch(runtime):
    global APP
    APP = runtime
    if getattr(runtime, "_ajap_publication_announce_patch", False):
        return

    original_submit = lyon.RatedPublicarJugadorModal.on_submit

    async def announcing_submit(modal, interaction: discord.Interaction):
        previous_id = _last_publication_id(modal.jugador, interaction.user.id)

        # Preserve all current validation and the actual publication write.
        await original_submit(modal, interaction)

        publication = _new_publication(modal.jugador, interaction.user.id, previous_id)
        if not publication:
            return

        public_ok = await _send_public_announcement(interaction, publication)
        print(
            f"AJAP publicación #{publication['id']} anuncio público: "
            f"{'OK' if public_ok else 'FAILED'}"
        )

    # publish_ovr_patch imports this class directly. Patching the class method
    # keeps every existing selector path on the same announcing behavior.
    lyon.RatedPublicarJugadorModal.on_submit = announcing_submit
    publish.RatedPublicarJugadorModal = lyon.RatedPublicarJugadorModal
    runtime.PublicarJugadorModal = lyon.RatedPublicarJugadorModal
    runtime.PublicationOfferView = PublicationOfferView

    persistent_views = _register_persistent_offer_views(runtime)
    runtime._ajap_publication_announce_patch = True
    print(
        "AJAP anuncios de transferibles activos: @everyone + botón Ofertar + "
        f"club + jugador + precio + mínimo | vistas persistentes: {persistent_views}"
    )
