"""AJAP offer notifications.

When a new offer is successfully created, notify the seller by DM and publish a
visible notice in the same Discord channel where the offer was submitted.
Notification failures never roll back or duplicate the actual offer.
"""

import discord


APP = None


def _has(row, key):
    return row is not None and key in row.keys()


def _offer_embed(offer, *, private=False):
    player = offer["player"]
    buyer = offer["from_club"]
    seller = offer["to_club"]
    amount = offer["amount"]
    kind = offer["offer_kind"] if _has(offer, "offer_kind") else offer["operation_type"]
    offered_player = offer["offered_player"] if _has(offer, "offered_player") else None
    conditions = offer["message"] or "Sin condiciones adicionales"

    if private:
        embed = discord.Embed(
            title="📩 NUEVA OFERTA RECIBIDA",
            description=(
                f"**{buyer}** realizó una oferta por **{player}**, jugador de **{seller}**.\n\n"
                "La oferta también quedó guardada en **Mis ofertas**."
            ),
        )
    else:
        embed = discord.Embed(
            title="📢 NUEVA OFERTA",
            description=(
                f"**{buyer}** realizó una oferta por **{player}**, propiedad de **{seller}**."
            ),
        )

    ficha = APP.jugador_por_nombre(player)
    if ficha and "rating" in ficha.keys() and ficha["rating"] is not None:
        embed.add_field(name="Jugador buscado", value=f"{player} • ⭐ {ficha['rating']}", inline=False)
    else:
        embed.add_field(name="Jugador buscado", value=player, inline=False)

    embed.add_field(name="Club ofertante", value=buyer, inline=True)
    embed.add_field(name="Club vendedor", value=seller, inline=True)
    embed.add_field(name="Modalidad", value=kind, inline=True)

    if offered_player:
        offered = APP.jugador_por_nombre(offered_player)
        offered_text = offered_player
        if offered and "rating" in offered.keys() and offered["rating"] is not None:
            offered_text += f" • ⭐ {offered['rating']}"
        embed.add_field(name="🔁 Jugador ofrecido", value=offered_text, inline=False)

    if not offered_player or amount != "$0":
        embed.add_field(name="💰 Dinero ofrecido", value=amount, inline=True)

    embed.add_field(name="Estado", value="🟡 PENDIENTE", inline=True)
    embed.add_field(name="Condiciones", value=conditions, inline=False)

    if private:
        embed.add_field(
            name="¿Qué sigue?",
            value="Entrá a **/mercado → Mis ofertas** para aceptar o rechazar la propuesta.",
            inline=False,
        )
    else:
        embed.set_footer(text=f"Oferta #{offer['id']} • Esperando respuesta del club vendedor")

    return embed


async def _send_seller_dm(offer):
    try:
        seller = APP.bot.get_user(int(offer["to_id"]))
        if seller is None:
            seller = await APP.bot.fetch_user(int(offer["to_id"]))
        await seller.send(embed=_offer_embed(offer, private=True))
        return True
    except (discord.Forbidden, discord.NotFound, discord.HTTPException) as exc:
        print(f"WARNING AJAP: no se pudo enviar DM de oferta #{offer['id']}: {exc}")
        return False


async def _send_public_notice(interaction, offer):
    channel = interaction.channel
    if channel is None or not hasattr(channel, "send"):
        return False
    try:
        await channel.send(embed=_offer_embed(offer, private=False))
        return True
    except (discord.Forbidden, discord.HTTPException) as exc:
        print(f"WARNING AJAP: no se pudo publicar oferta #{offer['id']} en el canal: {exc}")
        return False


def _last_offer_id(publication_id, from_id):
    with APP.db() as conn:
        row = conn.execute(
            """
            SELECT COALESCE(MAX(id), 0) AS last_id
            FROM offers
            WHERE publication_id = ? AND from_id = ?
            """,
            (int(publication_id), int(from_id)),
        ).fetchone()
    return int(row["last_id"] if row else 0)


def _new_offer(publication_id, from_id, after_id):
    with APP.db() as conn:
        return conn.execute(
            """
            SELECT * FROM offers
            WHERE publication_id = ? AND from_id = ? AND id > ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (int(publication_id), int(from_id), int(after_id)),
        ).fetchone()


def apply_offer_notifications_patch(main_module):
    global APP
    APP = main_module

    if getattr(main_module, "_ajap_offer_notifications_patch", False):
        return

    BaseOfertaModal = main_module.OfertaModal

    class NotifyingOfertaModal(BaseOfertaModal):
        async def on_submit(self, interaction: discord.Interaction):
            previous_id = _last_offer_id(self.publicacion_id, interaction.user.id)

            # Preserve every validation and database write from the active market flow.
            await super().on_submit(interaction)

            offer = _new_offer(self.publicacion_id, interaction.user.id, previous_id)
            if not offer:
                return

            dm_ok = await _send_seller_dm(offer)
            public_ok = await _send_public_notice(interaction, offer)
            print(
                f"AJAP offer #{offer['id']} notifications: "
                f"DM={'OK' if dm_ok else 'FAILED'} • PUBLIC={'OK' if public_ok else 'FAILED'}"
            )

    NotifyingOfertaModal.__name__ = "OfertaModal"
    main_module.OfertaModal = NotifyingOfertaModal
    main_module._ajap_offer_notifications_patch = True
    print("Notificaciones de ofertas activas: DM al vendedor + aviso público en el canal")
