"""Minimum equivalent value protection for AJAP negotiated offers.

A published player's minimum sale value is always protected, regardless of the
offer format. The bot values an offered player using that player's own AJAP
minimum sale value and adds any cash included in the proposal.

Examples:
- Target minimum $30M, cash $30M -> valid.
- Target minimum $30M, offered player worth $30M -> valid.
- Target minimum $30M, offered player worth $14M + $16M cash -> valid.
- Any equivalent value below $30M -> rejected before the offer is created.
"""

import discord
import flexible_offer_patch as flexible

APP = None


def _has(row, key):
    return row is not None and key in row.keys()


def fmt_money(value: int) -> str:
    return f"${int(value):,}".replace(",", ".")


def player_floor(player) -> int:
    if not player:
        return 0
    if _has(player, "min_sale_value") and player["min_sale_value"] is not None:
        return int(player["min_sale_value"])

    # Safety fallback for older rows that have OVR but were created before the
    # min_sale_value migration/seed.
    rating = player["rating"] if _has(player, "rating") else None
    if rating is not None:
        try:
            from lyon_test_seed import minimum_for_rating
            return int(minimum_for_rating(int(rating)))
        except Exception:
            pass
    return 0


def equivalent_value(target, offered, cash_value: int):
    target_min = player_floor(target)
    offered_min = player_floor(offered)
    total = offered_min + max(int(cash_value or 0), 0)
    missing = max(target_min - total, 0)
    return target_min, offered_min, total, missing


def proposal_values_from_modal(modal):
    raw_cash = modal.monto.value.strip()
    if raw_cash:
        cash_value = APP.price_number(raw_cash)
        if cash_value is None:
            # Base modal will show the normal invalid-number message.
            return None
    else:
        cash_value = 0
    offered = flexible.resolve_player_reference(modal.jugador.value)
    return cash_value, offered


def proposal_values_from_offer(offer):
    cash_value = APP.price_number(offer["amount"] or "") or 0
    offered = None
    if _has(offer, "offered_player_id") and offer["offered_player_id"]:
        offered = APP.jugador_por_id(int(offer["offered_player_id"]))
    return cash_value, offered


def insufficient_embed(target, offered, cash_value, target_min, offered_min, total, missing):
    embed = discord.Embed(
        title="⛔ Oferta por debajo del valor mínimo",
        description=(
            f"La propuesta por **{target['name']}** no alcanza su valor mínimo protegido.\n\n"
            f"Te faltan **{fmt_money(missing)}** de valor para poder enviar esta oferta."
        ),
    )
    target_ovr = target["rating"] if _has(target, "rating") else None
    target_label = target["name"]
    if target_ovr is not None:
        target_label += f" • ⭐ {target_ovr}"
    embed.add_field(
        name="Jugador buscado",
        value=f"{target_label}\n💰 Mínimo protegido: **{fmt_money(target_min)}**",
        inline=False,
    )
    if offered:
        offered_ovr = offered["rating"] if _has(offered, "rating") else None
        offered_label = offered["name"]
        if offered_ovr is not None:
            offered_label += f" • ⭐ {offered_ovr}"
        embed.add_field(
            name="Jugador ofrecido",
            value=f"{offered_label}\n💰 Valor AJAP: **{fmt_money(offered_min)}**",
            inline=False,
        )
    if cash_value > 0:
        embed.add_field(name="Dinero ofrecido", value=fmt_money(cash_value), inline=True)
    embed.add_field(name="Valor total de la propuesta", value=fmt_money(total), inline=True)
    embed.add_field(name="Falta compensar", value=fmt_money(missing), inline=True)
    return embed


def validate_equivalent_offer(target, offered, cash_value):
    target_min, offered_min, total, missing = equivalent_value(target, offered, cash_value)
    # If a legacy player has no floor at all, preserve compatibility instead of
    # inventing a value. Seeded AJAP players with OVR do have a protected floor.
    if target_min <= 0:
        return True, None
    if missing <= 0:
        return True, None
    return False, insufficient_embed(
        target, offered, cash_value, target_min, offered_min, total, missing
    )


def apply_offer_value_floor_patch(main_module):
    global APP
    APP = main_module
    if getattr(main_module, "_ajap_offer_value_floor_patch", False):
        return

    BaseOfertaModal = main_module.OfertaModal

    class ValueProtectedOfertaModal(BaseOfertaModal):
        async def on_submit(self, interaction: discord.Interaction):
            pub = APP.publicacion_por_id(self.publicacion_id)
            if pub:
                target = APP.jugador_por_nombre(pub["player"])
                proposal = proposal_values_from_modal(self)
                if target and proposal is not None:
                    cash_value, offered = proposal
                    # Only run the floor calculation when the offered-player
                    # reference is either blank or valid. The base modal owns the
                    # normal "player not found / not yours" validation.
                    if not self.jugador.value.strip() or offered:
                        ok, error_embed = validate_equivalent_offer(target, offered, cash_value)
                        if not ok:
                            await interaction.response.send_message(
                                embed=error_embed,
                                ephemeral=True,
                            )
                            return
            await super().on_submit(interaction)

    ValueProtectedOfertaModal.__name__ = "OfertaModal"
    main_module.OfertaModal = ValueProtectedOfertaModal

    # Also protect acceptance of pending offers created before this rule existed.
    BaseDecisionView = flexible.FlexibleOfertaDecisionView

    class ValueProtectedOfertaDecisionView(BaseDecisionView):
        async def aceptar(self, interaction: discord.Interaction, button: discord.ui.Button):
            offer = APP.oferta_por_id(self.oferta_id)
            if offer and offer["status"] == "PENDIENTE":
                target = APP.jugador_por_nombre(offer["player"])
                if target:
                    cash_value, offered = proposal_values_from_offer(offer)
                    ok, error_embed = validate_equivalent_offer(target, offered, cash_value)
                    if not ok:
                        error_embed.description += (
                            "\n\nEsta oferta quedó pendiente de antes de aplicar la nueva regla y "
                            "**ya no puede aceptarse**. El comprador debe enviar una propuesta nueva."
                        )
                        await interaction.response.send_message(embed=error_embed, ephemeral=True)
                        return
            await super().aceptar(interaction, button)

    ValueProtectedOfertaDecisionView.__name__ = "OfertaDecisionView"
    # FlexibleOfertasSelect resolves this module global at callback time.
    flexible.FlexibleOfertaDecisionView = ValueProtectedOfertaDecisionView
    main_module.OfertaDecisionView = ValueProtectedOfertaDecisionView

    main_module.offer_equivalent_value = equivalent_value
    main_module.player_offer_floor = player_floor
    main_module._ajap_offer_value_floor_patch = True
    print("Protección de valor activa: jugador ofrecido + dinero deben cubrir el mínimo AJAP")
