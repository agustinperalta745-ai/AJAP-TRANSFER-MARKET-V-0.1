"""Direct negotiation actions on offer/counteroffer notifications.

The user who currently has the turn can accept, counteroffer or reject directly
from the public market notice (and from the DM copy). Views are persistent and
pending offers are re-registered after a bot restart.
"""

import discord

import offer_notifications_patch as offer_notifications
import negotiation_picker_patch as negotiation


APP = None
BOT = None


def _make_action_view(offer_id):
    return InlineNegotiationDecisionView(int(offer_id))


class InlineNegotiationDecisionView(negotiation.NegotiationDecisionView):
    """Persistent version of the existing negotiation decision view."""

    def __init__(self, offer_id):
        # Keep all validation/business logic from NegotiationDecisionView, then
        # make the view persistent and give every button a deterministic id.
        super().__init__(int(offer_id))
        self.timeout = None

        action_by_label = {
            "Aceptar": "accept",
            "Contraofertar": "counter",
            "Rechazar": "reject",
        }
        for item in self.children:
            action = action_by_label.get(getattr(item, "label", None))
            if action:
                item.custom_id = f"ajap:offer:{self.offer_id}:{action}"


def _replace_next_step(embed):
    for index, field in enumerate(embed.fields):
        if field.name == "¿Qué sigue?":
            embed.set_field_at(
                index,
                name="¿Qué sigue?",
                value="Respondé directamente con **Aceptar**, **Contraofertar** o **Rechazar**.",
                inline=False,
            )
            break
    return embed


async def _send_seller_dm(offer):
    try:
        seller = APP.bot.get_user(int(offer["to_id"]))
        if seller is None:
            seller = await APP.bot.fetch_user(int(offer["to_id"]))
        embed = _replace_next_step(offer_notifications._offer_embed(offer, private=True))
        await seller.send(embed=embed, view=_make_action_view(offer["id"]))
        return True
    except (discord.Forbidden, discord.NotFound, discord.HTTPException) as exc:
        print(f"WARNING AJAP: no se pudo enviar DM de oferta #{offer['id']}: {exc}")
        return False


async def _send_public_notice(interaction, offer):
    channel = interaction.channel
    if channel is None or not hasattr(channel, "send"):
        return False
    try:
        seller_mention = f"<@{int(offer['to_id'])}>"
        buyer = offer["from_club"]
        player = offer["player"]
        embed = offer_notifications._offer_embed(offer, private=False)
        embed.add_field(
            name="Respuesta directa",
            value="El club que tiene el turno puede responder con los botones de abajo.",
            inline=False,
        )
        embed.set_footer(text=f"Oferta #{offer['id']} • Aceptar, contraofertar o rechazar abajo")
        await channel.send(
            content=f"{seller_mention} 📩 **{buyer} hizo una oferta por tu jugador {player}.**",
            embed=embed,
            view=_make_action_view(offer["id"]),
            allowed_mentions=discord.AllowedMentions(users=True, roles=False, everyone=False),
        )
        return True
    except (discord.Forbidden, discord.HTTPException) as exc:
        print(f"WARNING AJAP: no se pudo publicar oferta #{offer['id']} en el canal: {exc}")
        return False


def _counter_embed(offer, actor_id, recipient_id):
    actor_club = negotiation._club_for_user(offer, actor_id) or "Un club"
    recipient_club = negotiation._club_for_user(offer, recipient_id) or "el otro club"
    embed = discord.Embed(
        title="🔄 NUEVA CONTRAOFERTA",
        description=(
            f"**{actor_club}** modificó la propuesta por **{offer['player']}**.\n\n"
            f"Turno de respuesta: **{recipient_club}**."
        ),
    )
    embed.add_field(name="Propuesta actual", value=negotiation._proposal_text(offer), inline=False)
    embed.add_field(name="Ronda", value=str(negotiation._round(offer)), inline=True)
    embed.add_field(name="Condiciones", value=offer["message"], inline=False)
    embed.add_field(
        name="Respuesta directa",
        value="Usá **Aceptar**, **Contraofertar** o **Rechazar** sin volver a /mercado.",
        inline=False,
    )
    embed.set_footer(text=f"Oferta #{offer['id']} • Respondé con los botones de abajo")
    return embed, actor_club


async def _notify_counteroffer(interaction, offer, actor_id, recipient_id):
    embed, actor_club = _counter_embed(offer, actor_id, recipient_id)

    try:
        user = APP.bot.get_user(int(recipient_id))
        if user is None:
            user = await APP.bot.fetch_user(int(recipient_id))
        await user.send(embed=embed, view=_make_action_view(offer["id"]))
    except (discord.Forbidden, discord.NotFound, discord.HTTPException) as exc:
        print(f"WARNING AJAP: DM contraoferta #{offer['id']} falló: {exc}")

    channel = interaction.channel
    if channel is not None and hasattr(channel, "send"):
        try:
            public_embed, _ = _counter_embed(offer, actor_id, recipient_id)
            await channel.send(
                content=(
                    f"<@{int(recipient_id)}> 🔄 **{actor_club} hizo una contraoferta "
                    f"por {offer['player']}.**"
                ),
                embed=public_embed,
                view=_make_action_view(offer["id"]),
                allowed_mentions=discord.AllowedMentions(users=True, roles=False, everyone=False),
            )
        except (discord.Forbidden, discord.HTTPException) as exc:
            print(f"WARNING AJAP: aviso público contraoferta #{offer['id']} falló: {exc}")


async def _register_pending_views():
    if getattr(BOT, "_ajap_inline_offer_views_registered", False):
        return

    with APP.db() as conn:
        rows = conn.execute(
            "SELECT id FROM offers WHERE status = 'PENDIENTE' ORDER BY id"
        ).fetchall()

    registered = 0
    for row in rows:
        try:
            BOT.add_view(_make_action_view(row["id"]))
            registered += 1
        except ValueError as exc:
            print(f"WARNING AJAP: no se pudo registrar vista persistente oferta #{row['id']}: {exc}")

    BOT._ajap_inline_offer_views_registered = True
    print(f"AJAP botones persistentes: {registered} negociación(es) pendiente(s) registradas")


def apply_inline_offer_actions_patch(main_module, bot):
    global APP, BOT
    APP = main_module
    BOT = bot

    if getattr(main_module, "_ajap_inline_offer_actions_patch", False):
        return

    # Make the direct-action view the canonical decision view everywhere.
    negotiation.NegotiationDecisionView = InlineNegotiationDecisionView
    negotiation.flexible.FlexibleOfertaDecisionView = InlineNegotiationDecisionView
    main_module.OfertaDecisionView = InlineNegotiationDecisionView

    # The notification functions resolve these globals at interaction time, so
    # replacing them here affects both new offers and every future counteroffer.
    offer_notifications._send_seller_dm = _send_seller_dm
    offer_notifications._send_public_notice = _send_public_notice
    negotiation._notify_counteroffer = _notify_counteroffer

    # Re-attach persistent callbacks for pending messages after Railway restarts.
    bot.add_listener(_register_pending_views, "on_ready")

    main_module._ajap_inline_offer_actions_patch = True
    print("AJAP respuesta directa activa: aceptar/contraofertar/rechazar desde cada aviso")
