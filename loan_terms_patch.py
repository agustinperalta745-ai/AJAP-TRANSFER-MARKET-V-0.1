"""Loan terms for AJAP Transfer Market.

For PRÉSTAMO operations:
- duration in seasons is mandatory;
- purchase option is optional, but when present it must have a numeric value;
- terms survive counteroffers and are copied to the final admin operation;
- the operation type stays PRÉSTAMO instead of being overwritten by the
  cash/player composition of the offer.
"""

import discord

import flexible_offer_patch as flexible
import negotiation_picker_patch as negotiation
import offer_notifications_patch as offer_notifications
import offer_value_floor_patch as value_floor

APP = None
ORIGINAL_PROPOSAL_TEXT = None
ORIGINAL_OFFER_EMBED = None


def _has(row, key):
    return row is not None and key in row.keys()


def _publication_is_loan(publication):
    if not publication:
        return False
    return APP.normalizar_tipo(publication["operation_type"]) == "PRÉSTAMO"


def _offer_is_loan(offer):
    if not offer:
        return False
    if _has(offer, "operation_type") and APP.normalizar_tipo(offer["operation_type"]) == "PRÉSTAMO":
        return True
    if _has(offer, "publication_id"):
        pub = APP.publicacion_por_id(int(offer["publication_id"]))
        return _publication_is_loan(pub)
    return False


def _loan_seasons(offer):
    if _has(offer, "loan_seasons") and offer["loan_seasons"] is not None:
        try:
            return int(offer["loan_seasons"])
        except (TypeError, ValueError):
            return None
    return None


def _purchase_value(offer):
    if _has(offer, "purchase_option_value"):
        value = offer["purchase_option_value"]
        return str(value).strip() if value else None
    return None


def _loan_terms_text(offer):
    seasons = _loan_seasons(offer)
    purchase = _purchase_value(offer)
    duration = f"{seasons} temporada{'s' if seasons != 1 else ''}" if seasons else "Sin definir"
    option = purchase if purchase else "Sin opción de compra"
    return f"⏳ **Duración:** {duration}\n🛒 **Opción de compra:** {option}"


def _parse_loan_terms(duration_raw, purchase_raw):
    raw_duration = (duration_raw or "").strip()
    if not raw_duration.isdigit() or int(raw_duration) <= 0:
        return None, None, "⚠️ En un préstamo, la **cantidad de temporadas es obligatoria** y debe ser un número mayor a 0."

    seasons = int(raw_duration)
    raw_purchase = (purchase_raw or "").strip()
    if not raw_purchase:
        return seasons, None, None

    purchase_number = APP.price_number(raw_purchase)
    if purchase_number is None or purchase_number <= 0:
        return None, None, "⚠️ Si hay **opción de compra**, tenés que indicar un valor numérico mayor a 0."

    return seasons, APP.money(str(purchase_number)), None


def ensure_schema():
    with APP.db() as conn:
        APP.add_column_if_missing(conn, "offers", "loan_seasons", "INTEGER")
        APP.add_column_if_missing(conn, "offers", "purchase_option_value", "TEXT")
        APP.add_column_if_missing(conn, "transfers", "loan_seasons", "INTEGER")
        APP.add_column_if_missing(conn, "transfers", "purchase_option_value", "TEXT")


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
            ORDER BY id DESC LIMIT 1
            """,
            (int(publication_id), int(from_id), int(after_id)),
        ).fetchone()


def apply_loan_terms_offer_patch(main_module):
    """Wrap the protected offer modal before the notification layer is installed."""
    global APP
    APP = main_module
    if getattr(main_module, "_ajap_loan_terms_offer_patch", False):
        return

    ensure_schema()
    BaseOfertaModal = main_module.OfertaModal

    class LoanTermsOfertaModal(BaseOfertaModal):
        def __init__(self, publicacion):
            super().__init__(publicacion)
            self._ajap_is_loan = _publication_is_loan(publicacion)
            self.loan_duration = None
            self.purchase_option = None

            if self._ajap_is_loan:
                self.loan_duration = discord.ui.TextInput(
                    label="Duración del préstamo (temporadas)",
                    placeholder="Ej: 1",
                    required=True,
                    max_length=2,
                )
                self.purchase_option = discord.ui.TextInput(
                    label="Opción de compra (valor, opcional)",
                    placeholder="Vacío = sin opción • Ej: 30000000",
                    required=False,
                    max_length=30,
                )
                self.add_item(self.loan_duration)
                self.add_item(self.purchase_option)

        async def on_submit(self, interaction: discord.Interaction):
            if not self._ajap_is_loan:
                await super().on_submit(interaction)
                return

            seasons, purchase, error = _parse_loan_terms(
                self.loan_duration.value,
                self.purchase_option.value,
            )
            if error:
                await interaction.response.send_message(error, ephemeral=True)
                return

            previous_id = _last_offer_id(self.publicacion_id, interaction.user.id)
            await super().on_submit(interaction)

            offer = _new_offer(self.publicacion_id, interaction.user.id, previous_id)
            if not offer:
                return

            with APP.db() as conn:
                conn.execute(
                    """
                    UPDATE offers
                    SET operation_type = 'PRÉSTAMO', loan_seasons = ?, purchase_option_value = ?
                    WHERE id = ?
                    """,
                    (seasons, purchase, offer["id"]),
                )

    LoanTermsOfertaModal.__name__ = "OfertaModal"
    main_module.OfertaModal = LoanTermsOfertaModal
    main_module._ajap_loan_terms_offer_patch = True
    print("AJAP préstamos: duración obligatoria + opción de compra con valor")


class LoanAwareCounterOfferModal(discord.ui.Modal):
    def __init__(self, offer_id, offered_player_id):
        offer = APP.oferta_por_id(int(offer_id))
        target = offer["player"] if offer else "jugador"
        super().__init__(title=f"Contraoferta por {target[:28]}")
        self.offer_id = int(offer_id)
        self.offered_player_id = offered_player_id
        self.is_loan = _offer_is_loan(offer)

        current_cash = APP.price_number(offer["amount"]) if offer else 0
        current_message = offer["message"] if offer else ""
        if current_message == "Sin condiciones adicionales":
            current_message = ""

        self.monto = discord.ui.TextInput(
            label="Dinero en la contraoferta (opcional)",
            placeholder="Ej: 10000000",
            default=str(current_cash) if current_cash else None,
            required=False,
            max_length=30,
        )
        self.mensaje = discord.ui.TextInput(
            label="Mensaje / condiciones",
            placeholder="Opcional",
            default=current_message[:150] if current_message else None,
            required=False,
            max_length=150,
        )
        self.add_item(self.monto)
        self.add_item(self.mensaje)

        self.loan_duration = None
        self.purchase_option = None
        if self.is_loan:
            current_seasons = _loan_seasons(offer)
            current_purchase = _purchase_value(offer)
            self.loan_duration = discord.ui.TextInput(
                label="Duración del préstamo (temporadas)",
                placeholder="Ej: 1",
                default=str(current_seasons) if current_seasons else None,
                required=True,
                max_length=2,
            )
            self.purchase_option = discord.ui.TextInput(
                label="Opción de compra (valor, opcional)",
                placeholder="Vacío = sin opción • Ej: 30000000",
                default=(str(APP.price_number(current_purchase)) if current_purchase and APP.price_number(current_purchase) else None),
                required=False,
                max_length=30,
            )
            self.add_item(self.loan_duration)
            self.add_item(self.purchase_option)

    async def on_submit(self, interaction: discord.Interaction):
        if not APP.mercado_abierto():
            await interaction.response.send_message(
                "🔒 El mercado está cerrado. La negociación queda congelada.", ephemeral=True
            )
            return

        offer = APP.oferta_por_id(self.offer_id)
        if not offer or offer["status"] != "PENDIENTE":
            await interaction.response.send_message("⚠️ Esta oferta ya fue resuelta.", ephemeral=True)
            return
        if interaction.user.id not in (offer["from_id"], offer["to_id"]):
            await interaction.response.send_message("⛔ No pertenecés a esta negociación.", ephemeral=True)
            return
        if interaction.user.id != negotiation._decision_user_id(offer):
            await interaction.response.send_message(
                "⏳ Ahora mismo la respuesta le corresponde al otro club.", ephemeral=True
            )
            return

        raw_cash = self.monto.value.strip()
        cash_value = APP.price_number(raw_cash) if raw_cash else 0
        if raw_cash and cash_value is None:
            await interaction.response.send_message("⚠️ El dinero debe ser un número.", ephemeral=True)
            return

        target = APP.jugador_por_nombre(offer["player"])
        pub = APP.publicacion_por_id(offer["publication_id"])
        if not target or not pub or target["club"].casefold() != offer["to_club"].casefold():
            with APP.db() as conn:
                conn.execute("UPDATE offers SET status = 'CANCELADA' WHERE id = ?", (offer["id"],))
            await interaction.response.send_message(
                "⚠️ La propiedad del jugador cambió. La negociación fue cancelada.", ephemeral=True
            )
            return

        offered = None
        if self.offered_player_id is not None:
            offered = APP.jugador_por_id(int(self.offered_player_id))
            if not offered or offered["club"].casefold() != offer["from_club"].casefold():
                await interaction.response.send_message(
                    f"⛔ Ese jugador ya no pertenece a **{offer['from_club']}**.", ephemeral=True
                )
                return
            if APP.operacion_abierta_del_jugador(offered["name"]):
                await interaction.response.send_message(
                    f"⚠️ **{offered['name']}** ya tiene una operación pendiente.", ephemeral=True
                )
                return

        if cash_value <= 0 and not offered:
            await interaction.response.send_message(
                "⚠️ La contraoferta debe incluir **dinero**, **un jugador**, o **ambos**.",
                ephemeral=True,
            )
            return

        ok, error_embed = value_floor.validate_equivalent_offer(target, offered, cash_value)
        if not ok:
            await interaction.response.send_message(embed=error_embed, ephemeral=True)
            return

        seasons = None
        purchase = None
        if self.is_loan:
            seasons, purchase, error = _parse_loan_terms(
                self.loan_duration.value,
                self.purchase_option.value,
            )
            if error:
                await interaction.response.send_message(error, ephemeral=True)
                return

        kind = flexible.offer_kind(cash_value, offered)
        amount = APP.money(str(cash_value)) if cash_value > 0 else "$0"
        message = self.mensaje.value.strip() or "Sin condiciones adicionales"
        next_user = negotiation._other_user_id(offer, interaction.user.id)
        next_round = negotiation._round(offer) + 1
        operation_type = "PRÉSTAMO" if self.is_loan else kind

        with APP.db() as conn:
            conn.execute(
                """
                UPDATE offers
                SET amount = ?, message = ?, operation_type = ?, offer_kind = ?,
                    offered_player_id = ?, offered_player = ?, decision_user_id = ?,
                    negotiation_round = ?, loan_seasons = ?, purchase_option_value = ?,
                    status = 'PENDIENTE'
                WHERE id = ?
                """,
                (
                    amount,
                    message,
                    operation_type,
                    kind,
                    offered["id"] if offered else None,
                    offered["name"] if offered else None,
                    next_user,
                    next_round,
                    seasons if self.is_loan else None,
                    purchase if self.is_loan else None,
                    offer["id"],
                ),
            )

        refreshed = APP.oferta_por_id(offer["id"])
        embed = discord.Embed(
            title="🔄 Contraoferta enviada",
            description=(
                f"Cambiaste las condiciones de la negociación por **{offer['player']}**.\n\n"
                f"Ahora debe responder **{negotiation._other_club(offer, interaction.user.id)}**."
            ),
        )
        embed.add_field(name="Nueva propuesta", value=negotiation._proposal_text(refreshed), inline=False)
        embed.add_field(name="Ronda", value=str(next_round), inline=True)
        embed.add_field(name="Condiciones", value=message, inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)
        await negotiation._notify_counteroffer(interaction, refreshed, interaction.user.id, next_user)


def apply_loan_terms_negotiation_patch(main_module):
    """Install loan-aware counteroffers/acceptance after negotiation_picker_patch."""
    global APP, ORIGINAL_PROPOSAL_TEXT, ORIGINAL_OFFER_EMBED
    APP = main_module
    if getattr(main_module, "_ajap_loan_terms_negotiation_patch", False):
        return

    ensure_schema()

    ORIGINAL_PROPOSAL_TEXT = negotiation._proposal_text

    def loan_proposal_text(offer):
        text = ORIGINAL_PROPOSAL_TEXT(offer)
        if _offer_is_loan(offer):
            text += "\n" + _loan_terms_text(offer)
        return text

    negotiation._proposal_text = loan_proposal_text

    ORIGINAL_OFFER_EMBED = offer_notifications._offer_embed

    def loan_offer_embed(offer, *, private=False):
        embed = ORIGINAL_OFFER_EMBED(offer, private=private)
        if _offer_is_loan(offer):
            embed.add_field(name="Tipo de operación", value="PRÉSTAMO", inline=True)
            seasons = _loan_seasons(offer)
            embed.add_field(
                name="⏳ Duración",
                value=f"{seasons} temporada{'s' if seasons != 1 else ''}" if seasons else "Sin definir",
                inline=True,
            )
            embed.add_field(
                name="🛒 Opción de compra",
                value=_purchase_value(offer) or "Sin opción de compra",
                inline=False,
            )
        return embed

    offer_notifications._offer_embed = loan_offer_embed

    BaseDecisionView = negotiation.NegotiationDecisionView

    class LoanNegotiationDecisionView(BaseDecisionView):
        @discord.ui.button(label="Aceptar", emoji="✅", style=discord.ButtonStyle.success, row=0)
        async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
            preview = APP.oferta_por_id(self.offer_id)
            if not _offer_is_loan(preview):
                await BaseDecisionView.accept(self, interaction, button)
                return

            offer = await self._current(interaction)
            if not offer:
                return
            if APP.operacion_abierta_del_jugador(offer["player"]):
                await interaction.response.send_message(
                    "⚠️ Ese jugador ya tiene otra operación pendiente de administración.", ephemeral=True
                )
                return

            pub = APP.publicacion_por_id(offer["publication_id"])
            target = APP.jugador_por_nombre(offer["player"])
            if not pub or not target or target["club"].casefold() != offer["to_club"].casefold():
                with APP.db() as conn:
                    conn.execute("UPDATE offers SET status = 'CANCELADA' WHERE id = ?", (offer["id"],))
                await interaction.response.send_message(
                    "⚠️ La publicación o propiedad cambió. La oferta fue cancelada.", ephemeral=True
                )
                return

            seasons = _loan_seasons(offer)
            if not seasons or seasons <= 0:
                await interaction.response.send_message(
                    "⚠️ Este préstamo no tiene una duración válida. Hacé una contraoferta y definí las temporadas.",
                    ephemeral=True,
                )
                return

            offered = None
            offered_id = offer["offered_player_id"] if _has(offer, "offered_player_id") else None
            if offered_id:
                offered = APP.jugador_por_id(int(offered_id))
                if not offered or offered["club"].casefold() != offer["from_club"].casefold():
                    await interaction.response.send_message(
                        "⚠️ El jugador incluido en la propuesta ya no pertenece al club comprador.",
                        ephemeral=True,
                    )
                    return
                if APP.operacion_abierta_del_jugador(offered["name"]):
                    await interaction.response.send_message(
                        f"⚠️ **{offered['name']}** ya tiene otra operación pendiente.", ephemeral=True
                    )
                    return

            deal_group = f"OFERTA-{offer['id']}"
            notes = (
                f"Ronda {negotiation._round(offer)} | {offer['message'] or 'Sin condiciones adicionales'} | "
                f"Préstamo: {seasons} temporada{'s' if seasons != 1 else ''} | "
                f"Opción de compra: {_purchase_value(offer) or 'NO'}"
            )
            if offered:
                notes += f" | Contraparte: {offered['name']} ({APP.player_code(offered['id'])})"

            created_ops = []
            with APP.db() as conn:
                conn.execute("UPDATE offers SET status = 'ACEPTADA' WHERE id = ?", (offer["id"],))
                conn.execute("UPDATE publications SET active = 0 WHERE id = ?", (pub["id"],))
                conn.execute(
                    """
                    UPDATE offers SET status = 'RECHAZADA'
                    WHERE publication_id = ? AND id != ? AND status = 'PENDIENTE'
                    """,
                    (pub["id"], offer["id"]),
                )

                if offered:
                    conn.execute(
                        "UPDATE publications SET active = 0 WHERE player = ? COLLATE NOCASE AND active = 1",
                        (offered["name"],),
                    )
                    conn.execute(
                        "UPDATE offers SET status = 'CANCELADA' WHERE player = ? COLLATE NOCASE AND status = 'PENDIENTE'",
                        (offered["name"],),
                    )

                cur = conn.execute(
                    """
                    INSERT INTO transfers
                    (player, seller, buyer, amount, offer_id, player_id, operation_type, season_id,
                     status, notes, deal_group, loan_seasons, purchase_option_value)
                    VALUES (?, ?, ?, ?, ?, ?, 'PRÉSTAMO', ?, 'PENDIENTE_ADMIN', ?, ?, ?, ?)
                    """,
                    (
                        offer["player"], offer["to_club"], offer["from_club"], offer["amount"],
                        offer["id"], target["id"], offer["season_id"], notes, deal_group,
                        seasons, _purchase_value(offer),
                    ),
                )
                created_ops.append(cur.lastrowid)

                if offered:
                    cur = conn.execute(
                        """
                        INSERT INTO transfers
                        (player, seller, buyer, amount, offer_id, player_id, operation_type, season_id,
                         status, notes, deal_group)
                        VALUES (?, ?, ?, '$0', ?, ?, 'INTERCAMBIO', ?, 'PENDIENTE_ADMIN', ?, ?)
                        """,
                        (
                            offered["name"], offer["from_club"], offer["to_club"], offer["id"],
                            offered["id"], offer["season_id"],
                            f"Contraparte de {offer['player']} | Oferta #{offer['id']} | Ronda {negotiation._round(offer)}",
                            deal_group,
                        ),
                    )
                    created_ops.append(cur.lastrowid)

            embed = discord.Embed(
                title="🤝 Préstamo aceptado • Falta administración",
                description=(
                    f"Se aceptó el préstamo de **{offer['player']}** desde **{offer['to_club']}** "
                    f"hacia **{offer['from_club']}**.\n\n"
                    "El plantel **todavía no fue modificado**."
                ),
            )
            embed.add_field(name="Propuesta final", value=negotiation._proposal_text(offer), inline=False)
            embed.add_field(name="Estado", value="🟡 PENDIENTE_ADMIN", inline=True)
            embed.set_footer(text="Operaciones: " + ", ".join(f"#{op}" for op in created_ops))
            await interaction.response.edit_message(embed=embed, view=None)

    LoanNegotiationDecisionView.__name__ = "NegotiationDecisionView"

    negotiation.CounterOfferModal = LoanAwareCounterOfferModal
    negotiation.NegotiationDecisionView = LoanNegotiationDecisionView
    negotiation.flexible.FlexibleOfertaDecisionView = LoanNegotiationDecisionView
    main_module.CounterOfferModal = LoanAwareCounterOfferModal
    main_module.OfertaDecisionView = LoanNegotiationDecisionView
    main_module._ajap_loan_terms_negotiation_patch = True
    print("AJAP préstamos integrados en contraofertas, aceptación, avisos e informe")
