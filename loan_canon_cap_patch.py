"""Make the 10% loan canon a ceiling instead of a fixed charge."""

from __future__ import annotations

import contextvars
import discord

import flexible_offer_patch as flexible
import loan_canon_patch as canon
import loan_terms_patch as terms
import market_channel_report_patch as market_reports
import offer_value_floor_patch as value_floor
import publication_announce_patch as publication_announce
import publication_loan_options_patch as publication_loans


RATE = canon.CANON_RATE_PERCENT
_LOAN_CONTEXT = contextvars.ContextVar("ajap_loan_cap", default=False)


def _app():
    return canon._app() or publication_loans.APP or terms.APP or flexible.APP


def _has(row, key):
    return row is not None and key in row.keys()


def _fmt(value):
    app = _app()
    if app and hasattr(app, "money"):
        return app.money(str(int(value)))
    return f"${int(value):,}".replace(",", ".")


def _number(value):
    if value is None:
        return None
    app = _app()
    if app and hasattr(app, "price_number"):
        parsed = app.price_number(str(value))
        if parsed is not None:
            return int(parsed)
    raw = str(value).strip()
    if not raw:
        return 0
    negative = raw.startswith("-")
    digits = "".join(ch for ch in raw if ch.isdigit())
    if not digits:
        return None
    amount = int(digits)
    return -amount if negative else amount


def _maximum(player):
    return max(int(canon.canon_for_player(player) or 0), 0)


def _capped(player, amount):
    amount = max(int(amount or 0), 0)
    maximum = _maximum(player)
    return min(amount, maximum) if maximum > 0 else amount


def _validate(player, amount):
    if amount < 0:
        return "⚠️ El cargo por temporada no puede ser negativo."
    maximum = _maximum(player)
    if maximum and amount > maximum:
        return (
            f"⛔ El máximo para **{player['name']}** es **{_fmt(maximum)} por temporada** "
            f"({RATE}% de su valor de mercado). Podés pedir ese monto o uno menor."
        )
    return None


# Publicación: nombre claro + microdescripción + máximo dinámico.
_original_publication_init = publication_loans.LoanPublicationModal.__init__
_original_publication_submit = publication_loans.LoanPublicationModal.on_submit


def _publication_init(self, ficha):
    _original_publication_init(self, ficha)
    maximum = _maximum(ficha)
    self.precio.label = "Cargo por temporada"
    helper = "Monto que recibís por cada temporada"
    if maximum:
        helper += f" • Máx. {_fmt(maximum)}"
    self.precio.placeholder = helper[:100]


async def _publication_submit(self, interaction):
    app = publication_loans.APP or _app()
    player = app.jugador_por_nombre(self.jugador) if app else None
    amount = app.price_number(self.precio.value) if app else _number(self.precio.value)
    if amount is None:
        await interaction.response.send_message("⚠️ El cargo por temporada debe ser un número.", ephemeral=True)
        return
    if player:
        error = _validate(player, int(amount))
        if error:
            await interaction.response.send_message(error, ephemeral=True)
            return
    await _original_publication_submit(self, interaction)


publication_loans.LoanPublicationModal.__init__ = _publication_init
publication_loans.LoanPublicationModal.on_submit = _publication_submit


# En préstamos no rige el piso de una venta definitiva: solo el tope del 10%.
_original_floor_validation = value_floor.validate_equivalent_offer


def _floor_validation(target, offered, cash_value):
    if _LOAN_CONTEXT.get():
        return True, None
    return _original_floor_validation(target, offered, cash_value)


value_floor.validate_equivalent_offer = _floor_validation


_original_apply_offer_terms = terms.apply_loan_terms_offer_patch


def _apply_offer_terms(main_module):
    result = _original_apply_offer_terms(main_module)
    modal = main_module.OfertaModal
    if getattr(modal, "_ajap_loan_cap", False):
        return result

    old_init = modal.__init__
    old_submit = modal.on_submit

    def init(self, publication):
        old_init(self, publication)
        if getattr(self, "_ajap_is_loan", False):
            player = main_module.jugador_por_nombre(publication["player"])
            maximum = _maximum(player)
            self.monto.label = "Cargo por temporada (oferta)"
            self.monto.placeholder = (
                f"Máximo {_fmt(maximum)} por temporada" if maximum else "Monto por cada temporada"
            )[:100]

    async def submit(self, interaction):
        if not getattr(self, "_ajap_is_loan", False):
            await old_submit(self, interaction)
            return
        publication = main_module.publicacion_por_id(self.publicacion_id)
        player = main_module.jugador_por_nombre(publication["player"]) if publication else None
        raw = self.monto.value.strip()
        amount = main_module.price_number(raw) if raw else 0
        if amount is None:
            await interaction.response.send_message("⚠️ El cargo por temporada debe ser un número.", ephemeral=True)
            return
        if player:
            error = _validate(player, int(amount))
            if error:
                await interaction.response.send_message(error, ephemeral=True)
                return
        token = _LOAN_CONTEXT.set(True)
        try:
            await old_submit(self, interaction)
        finally:
            _LOAN_CONTEXT.reset(token)

    modal.__init__ = init
    modal.on_submit = submit
    modal._ajap_loan_cap = True
    return result


terms.apply_loan_terms_offer_patch = _apply_offer_terms


# loan_canon_patch ya envuelve esta función; agregamos el control final para contraofertas.
_original_apply_negotiation = terms.apply_loan_terms_negotiation_patch


def _apply_negotiation(main_module):
    result = _original_apply_negotiation(main_module)
    modal = terms.LoanAwareCounterOfferModal
    if getattr(modal, "_ajap_loan_cap", False):
        return result

    old_init = modal.__init__
    old_submit = modal.on_submit

    def init(self, offer_id, offered_player_id):
        old_init(self, offer_id, offered_player_id)
        if self.is_loan:
            offer = main_module.oferta_por_id(int(offer_id))
            player = main_module.jugador_por_nombre(offer["player"]) if offer else None
            maximum = _maximum(player)
            self.monto.label = "Cargo por temporada"
            self.monto.placeholder = (
                f"Máximo {_fmt(maximum)} por temporada" if maximum else "Monto por cada temporada"
            )[:100]

    async def submit(self, interaction):
        if not self.is_loan:
            await old_submit(self, interaction)
            return
        offer = main_module.oferta_por_id(self.offer_id)
        player = main_module.jugador_por_nombre(offer["player"]) if offer else None
        raw = self.monto.value.strip()
        amount = main_module.price_number(raw) if raw else 0
        if amount is None:
            await interaction.response.send_message("⚠️ El cargo por temporada debe ser un número.", ephemeral=True)
            return
        if player:
            error = _validate(player, int(amount))
            if error:
                await interaction.response.send_message(error, ephemeral=True)
                return
        token = _LOAN_CONTEXT.set(True)
        try:
            await old_submit(self, interaction)
        finally:
            _LOAN_CONTEXT.reset(token)

    modal.__init__ = init
    modal.on_submit = submit
    modal._ajap_loan_cap = True
    return result


terms.apply_loan_terms_negotiation_patch = _apply_negotiation


# Textos: mostrar monto acordado + techo, no "10% fijo/no negociable".
def _canon_summary(offer):
    player = canon._player_for_name(offer["player"]) if offer else None
    maximum = _maximum(player)
    amount = _number(offer["amount"]) if offer and _has(offer, "amount") else None
    if amount is None:
        return "Cargo pendiente de definir"
    amount = _capped(player, amount)
    seasons = terms._loan_seasons(offer) or 0
    text = f"{_fmt(amount)} por temporada"
    if maximum:
        text += f" • máximo {_fmt(maximum)} ({RATE}% del valor de mercado)"
    if seasons:
        text += f"\n🧾 Total previsto: **{_fmt(amount * int(seasons))}**"
    return text


canon._canon_summary = _canon_summary


_old_publication_embed = publication_announce.publication_embed


def _publication_embed(publication):
    embed = _old_publication_embed(publication)
    app = _app() or publication_announce.APP
    if not app or str(publication["operation_type"] or "").upper() not in {"PRÉSTAMO", "PRESTAMO"}:
        return embed
    player = app.jugador_por_nombre(publication["player"])
    maximum = _maximum(player)
    asked = _capped(player, _number(publication["price"]) or 0)
    for i, field in enumerate(embed.fields):
        if field.name == "💵 Canon de cesión":
            embed.set_field_at(
                i,
                name="💵 Cargo por temporada",
                value=(
                    f"**{_fmt(asked)} por temporada**\n"
                    f"Máximo permitido: **{_fmt(maximum)}** ({RATE}% del valor de mercado)"
                ),
                inline=False,
            )
    return embed


publication_announce.publication_embed = _publication_embed


_old_movement_embed = market_reports.movement_embed


def _movement_embed(transfer_id):
    embed = _old_movement_embed(transfer_id)
    rows = market_reports._deal_rows(transfer_id)
    row = next((r for r in rows if str(r["operation_type"] or "").upper() in {"PRÉSTAMO", "PRESTAMO"}), None)
    if not row:
        return embed
    app = market_reports.APP or _app()
    player = app.jugador_por_id(int(row["player_id"])) if app and row["player_id"] else None
    maximum = _maximum(player)
    amount = _capped(player, _number(row["amount"]) or 0)
    seasons = int(row["loan_seasons"] or 0) if _has(row, "loan_seasons") else 0
    for i, field in enumerate(embed.fields):
        if field.name == "💵 Canon de préstamo":
            text = f"**{_fmt(amount)} por temporada** • máximo {_fmt(maximum)} ({RATE}%)"
            if seasons:
                text += f"\n🧾 Total previsto: **{_fmt(amount * seasons)}**"
            embed.set_field_at(i, name="💵 Cargo por temporada", value=text, inline=False)
    return embed


market_reports.movement_embed = _movement_embed


# Persistir como canon el dinero realmente acordado en la transferencia.
def _source_amount(conn, loan):
    row = conn.execute("SELECT amount FROM transfers WHERE id = ?", (int(loan["source_transfer_id"]),)).fetchone()
    return _number(row["amount"]) if row else None


def _initialize():
    if canon.loans.APP is None:
        return 0
    canon._ensure_canon_tables()
    updated = 0
    with canon.loans.APP.db() as conn:
        rows = conn.execute("SELECT * FROM loans ORDER BY id").fetchall()
        for loan in rows:
            player = conn.execute("SELECT * FROM roster_players WHERE id = ?", (int(loan["player_id"]),)).fetchone()
            amount = _source_amount(conn, loan)
            if amount is None:
                current = loan["canon_per_season"]
                amount = int(current) if current is not None else _maximum(player)
            amount = _capped(player, amount)
            if loan["canon_per_season"] is None or int(loan["canon_per_season"] or 0) != amount:
                conn.execute("UPDATE loans SET canon_per_season = ? WHERE id = ?", (amount, int(loan["id"])))
                updated += 1
    return updated


_original_charge = canon._charge_canon


def _charge(loan_id, season_id):
    _initialize()
    with canon.loans.APP.db() as conn:
        loan = conn.execute("SELECT * FROM loans WHERE id = ?", (int(loan_id),)).fetchone()
        amount = int(loan["canon_per_season"] or 0) if loan else 0

    if not loan or amount > 0:
        return _original_charge(loan_id, season_id)

    with canon.loans.APP.db() as conn:
        loan = conn.execute("SELECT * FROM loans WHERE id = ?", (int(loan_id),)).fetchone()
        if not loan:
            return False, "Préstamo no encontrado."
        paid = conn.execute(
            "SELECT 1 FROM loan_canon_payments WHERE loan_id = ? AND season_id = ?",
            (int(loan_id), int(season_id)),
        ).fetchone()
        if paid:
            return True, "Cargo ya registrado."
        for club in (loan["borrower_club"], loan["owner_club"]):
            conn.execute("INSERT OR IGNORE INTO club_finances (club, balance) VALUES (?, 0)", (club,))
        payer = conn.execute("SELECT balance FROM club_finances WHERE club = ? COLLATE NOCASE", (loan["borrower_club"],)).fetchone()
        payee = conn.execute("SELECT balance FROM club_finances WHERE club = ? COLLATE NOCASE", (loan["owner_club"],)).fetchone()
        pb = int(payer["balance"] if payer else 0)
        sb = int(payee["balance"] if payee else 0)
        conn.execute(
            """INSERT INTO loan_canon_payments
            (loan_id, season_id, player_id, player, payer_club, payee_club, amount,
             payer_balance_before, payer_balance_after, payee_balance_before, payee_balance_after)
            VALUES (?, ?, ?, ?, ?, ?, 0, ?, ?, ?, ?)""",
            (loan["id"], int(season_id), loan["player_id"], loan["player"], loan["borrower_club"], loan["owner_club"], pb, pb, sb, sb),
        )
        return True, "Préstamo sin cargo esta temporada."


def _transfer_canon(row):
    app = canon.loans.APP or _app()
    player = app.jugador_por_id(int(row["player_id"])) if app and row and row["player_id"] else None
    amount = _number(row["amount"]) if row else 0
    return _capped(player, amount or 0)


def _affordability(transfer_id):
    rows = [r for r in market_reports._deal_rows(int(transfer_id)) if str(r["operation_type"] or "").upper() in {"PRÉSTAMO", "PRESTAMO"}]
    if not rows:
        return True, None
    totals = {}
    for row in rows:
        totals[row["buyer"]] = totals.get(row["buyer"], 0) + _transfer_canon(row)
    with canon.loans.APP.db() as conn:
        for club, needed in totals.items():
            if needed <= 0:
                continue
            finance = conn.execute("SELECT balance FROM club_finances WHERE club = ? COLLATE NOCASE", (club,)).fetchone()
            balance = int(finance["balance"] if finance else 0)
            if balance < needed:
                return False, f"**{club}** necesita **{_fmt(needed)}** para la primera temporada y tiene **{_fmt(balance)}**."
    return True, None


canon._initialize_loan_canons = _initialize
canon._charge_canon = _charge
canon._canon_for_transfer_row = _transfer_canon
canon._initial_canon_affordability = _affordability

print("AJAP préstamos: 10% = tope por temporada; el cargo puede ser menor y se cobra el monto acordado")
