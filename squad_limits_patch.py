"""Regla global de planteles AJAP: mínimo 20, máximo 32.

Mínimo: jugadores activos en el club.
Máximo: jugadores activos + jugadores propios cedidos (su plaza queda reservada).
Los intercambios permanentes 1x1 pueden operar en los límites si el resultado
sigue siendo válido. Los préstamos no usan esa excepción: con 20 no se cede y
con 32 plazas comprometidas no se recibe a préstamo.
"""

from __future__ import annotations

import sys

import discord

import clausulazo_patch as clauses
import publication_loan_options_patch as publication_options
import staff_review_channel_patch as staff_review

MIN_SQUAD_SIZE = 20
MAX_SQUAD_SIZE = 32
ACTIVE_LOAN_STATUSES = ("ACTIVE", "OPTION_PENDING", "RETURN_PENDING", "REVIEW_REQUIRED")
APP = None


def _has(row, key):
    return row is not None and key in row.keys()


def _table_exists(conn, table):
    return bool(conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1", (table,)
    ).fetchone())


def active_count(conn, club):
    row = conn.execute(
        "SELECT COUNT(*) AS n FROM roster_players WHERE club=? COLLATE NOCASE", (club,)
    ).fetchone()
    return int(row["n"] if row else 0)


def loaned_out_count(conn, club):
    """Jugadores propios cedidos que reservan una plaza para volver."""
    count = 0
    if _table_exists(conn, "loans"):
        marks = ",".join("?" for _ in ACTIVE_LOAN_STATUSES)
        row = conn.execute(
            f"""
            SELECT COUNT(DISTINCT player_id) AS n
            FROM loans
            WHERE owner_club=? COLLATE NOCASE
              AND borrower_club<>owner_club COLLATE NOCASE
              AND status IN ({marks})
            """,
            (club, *ACTIVE_LOAN_STATUSES),
        ).fetchone()
        count = int(row["n"] if row else 0)

    # Cubre el instante posterior a aplicar el préstamo en PES y anterior a que
    # loan_lifecycle_patch cree la fila contractual en loans.
    if _table_exists(conn, "transfers"):
        not_linked = ""
        if _table_exists(conn, "loans"):
            not_linked = "AND NOT EXISTS (SELECT 1 FROM loans l WHERE l.source_transfer_id=t.id)"
        row = conn.execute(
            f"""
            SELECT COUNT(DISTINCT t.player_id) AS n
            FROM transfers t
            JOIN roster_players rp ON rp.id=t.player_id
            WHERE t.seller=? COLLATE NOCASE
              AND UPPER(COALESCE(t.operation_type,'')) IN ('PRÉSTAMO','PRESTAMO')
              AND UPPER(COALESCE(t.status,''))='APLICADA'
              AND rp.club<>t.seller COLLATE NOCASE
              {not_linked}
            """,
            (club,),
        ).fetchone()
        count += int(row["n"] if row else 0)
    return count


def state(conn, club):
    active = active_count(conn, club)
    loaned = loaned_out_count(conn, club)
    return {"club": club, "active": active, "loaned": loaned, "committed": active + loaned}


def _state_text(s):
    if s["loaned"]:
        suffix = "s" if s["loaned"] != 1 else ""
        return (
            f"{s['committed']}/{MAX_SQUAD_SIZE} plazas comprometidas "
            f"({s['active']} activos + {s['loaned']} cedido{suffix} que deben regresar)"
        )
    return f"{s['active']}/{MAX_SQUAD_SIZE} jugadores activos"


def min_reason(club, s, action="sacar a este jugador"):
    return (
        f"⛔ No podés {action}. **{club}** tiene **{s['active']}/{MIN_SQUAD_SIZE} jugadores activos**, "
        "el mínimo permitido. Primero incorporá otro jugador o hacé un **intercambio 1x1** "
        "que mantenga el plantel en al menos 20."
    )


def min_loan_reason(club, s):
    return (
        f"⛔ No podés ceder jugadores a préstamo. **{club}** tiene "
        f"**{s['active']}/{MIN_SQUAD_SIZE} jugadores activos**, el mínimo permitido. "
        "Con 20 jugadores no se permiten préstamos salientes. Los intercambios permanentes "
        "**1x1** sí siguen permitidos."
    )


def max_reason(club, s, action="incorporar otro jugador"):
    return (
        f"⛔ No podés {action}. **{club}** ya tiene **{_state_text(s)}**. "
        "Los jugadores propios cedidos reservan su plaza para regresar. Liberá una plaza "
        "permanente o hacé un **intercambio 1x1** que no aumente el total comprometido."
    )


def max_loan_reason(club, s):
    return (
        f"⛔ No podés traer un jugador a préstamo. **{club}** ya tiene **{_state_text(s)}**. "
        "Con 32 plazas comprometidas no se permiten préstamos entrantes; las plazas de los "
        "cedidos propios están reservadas para su regreso."
    )


def validate_release(conn, club):
    s = state(conn, club)
    return (False, min_reason(club, s, "liberar a este jugador")) if s["active"] <= MIN_SQUAD_SIZE else (True, None)


def validate_free_agent(conn, club):
    s = state(conn, club)
    if s["committed"] >= MAX_SQUAD_SIZE:
        return False, (
            f"⛔ No podés fichar este agente libre. **{club}** ya tiene **{_state_text(s)}**. "
            "El fichaje sea gratis no cambia que ocupa una plaza del plantel."
        )
    return True, None


def _op_type(value):
    raw = str(value or "").strip().upper()
    return {
        "PRESTAMO": "PRÉSTAMO", "CESION": "PRÉSTAMO", "CESIÓN": "PRÉSTAMO",
        "VENTA": "TRANSFERENCIA", "TRANSFERENCIA DEFINITIVA": "TRANSFERENCIA",
    }.get(raw, raw)


def validate_offer(offer, connection=None):
    """Valida cómo quedarían ambos clubes si se acepta la oferta."""
    if not offer:
        return True, None
    seller, buyer = offer["to_club"], offer["from_club"]
    op = _op_type(offer["operation_type"] if _has(offer, "operation_type") else None)
    if not op and _has(offer, "publication_id"):
        pub = APP.publicacion_por_id(int(offer["publication_id"]))
        op = _op_type(pub["operation_type"] if pub else None)
    offered_id = offer["offered_player_id"] if _has(offer, "offered_player_id") else None
    offered = APP.jugador_por_id(int(offered_id)) if offered_id else None

    own = connection is None
    conn = connection or APP.db()
    try:
        ss, bs = state(conn, seller), state(conn, buyer)
        if op == "PRÉSTAMO":
            if ss["active"] <= MIN_SQUAD_SIZE:
                return False, min_loan_reason(seller, ss)
            if bs["committed"] >= MAX_SQUAD_SIZE:
                return False, max_loan_reason(buyer, bs)
            if offered and ss["committed"] + 1 > MAX_SQUAD_SIZE:
                return False, max_reason(seller, ss, f"recibir a **{offered['name']}** en esta operación")
            return True, None

        swap = 1 if offered else 0
        buyer_active = bs["active"] + 1 - swap
        buyer_committed = bs["committed"] + 1 - swap
        seller_active = ss["active"] - 1 + swap
        seller_committed = ss["committed"] - 1 + swap
        if buyer_committed > MAX_SQUAD_SIZE:
            return False, max_reason(buyer, bs, "comprar a este jugador")
        if seller_active < MIN_SQUAD_SIZE:
            return False, min_reason(seller, ss, "vender a este jugador")
        if seller_committed > MAX_SQUAD_SIZE:
            return False, max_reason(seller, ss, "recibir al jugador del intercambio")
        if buyer_active < MIN_SQUAD_SIZE:
            return False, min_reason(buyer, bs, "entregar al jugador del intercambio")
        return True, None
    finally:
        if own:
            conn.close()


def validate_rows(rows, connection=None):
    """Backstop atómico para Staff/PES; evalúa el acuerdo completo."""
    rows = list(rows or [])
    if not rows:
        return True, None
    own = connection is None
    conn = connection or APP.db()
    try:
        clubs = {str(r[k]) for r in rows for k in ("seller", "buyer") if r[k]}
        states = {c: state(conn, c) for c in clubs}
        active_delta = {c: 0 for c in clubs}
        committed_delta = {c: 0 for c in clubs}
        return_parties = set()

        for row in rows:
            seller, buyer = str(row["seller"]), str(row["buyer"])
            op = _op_type(row["operation_type"] if _has(row, "operation_type") else None)
            if op == "PRÉSTAMO":
                if states[seller]["active"] <= MIN_SQUAD_SIZE:
                    return False, min_loan_reason(seller, states[seller])
                if states[buyer]["committed"] >= MAX_SQUAD_SIZE:
                    return False, max_loan_reason(buyer, states[buyer])
            if op == "DEVOLUCIÓN PRÉSTAMO":
                return_parties.update((seller, buyer))

            active_delta[seller] -= 1
            active_delta[buyer] += 1
            if op == "PRÉSTAMO":
                committed_delta[buyer] += 1
            elif op == "DEVOLUCIÓN PRÉSTAMO":
                committed_delta[seller] -= 1
            else:
                committed_delta[seller] -= 1
                committed_delta[buyer] += 1

        for club in clubs:
            s = states[club]
            final_active = s["active"] + active_delta[club]
            final_committed = s["committed"] + committed_delta[club]
            # Una devolución contractual siempre tiene prioridad. En estado normal
            # no aumenta plazas comprometidas porque el lugar ya estaba reservado.
            if club not in return_parties and final_active < MIN_SQUAD_SIZE:
                return False, (
                    f"⛔ La operación dejaría a **{club}** con **{final_active} jugadores activos**; "
                    f"el mínimo es **{MIN_SQUAD_SIZE}**."
                )
            if club not in return_parties and final_committed > MAX_SQUAD_SIZE:
                return False, (
                    f"⛔ La operación dejaría a **{club}** con **{final_committed} plazas comprometidas**; "
                    f"el máximo es **{MAX_SQUAD_SIZE}**. Estado actual: {_state_text(s)}."
                )
        return True, None
    finally:
        if own:
            conn.close()


def _guard_offer_modal(runtime):
    cls = getattr(runtime, "OfertaModal", None)
    if cls is None or getattr(cls, "_ajap_squad_limits", False):
        return
    original = cls.on_submit

    async def guarded(self, interaction):
        pub_id = getattr(self, "publicacion_id", None)
        pub = APP.publicacion_por_id(int(pub_id)) if pub_id else None
        buyer = APP.club_de(interaction.user.id)
        if pub and buyer:
            raw = getattr(getattr(self, "jugador", None), "value", "") or ""
            offered = APP.jugador_por_nombre(str(raw).strip()) if str(raw).strip() else None
            fake = {
                "to_club": pub["club"], "from_club": buyer,
                "operation_type": pub["operation_type"] if _has(pub, "operation_type") else "TRANSFERENCIA",
                "offered_player_id": offered["id"] if offered else None,
            }
            ok, reason = validate_offer(fake)
            if not ok:
                await interaction.response.send_message(reason, ephemeral=True)
                return
        await original(self, interaction)

    cls.on_submit = guarded
    cls._ajap_squad_limits = True


def _guard_decision_view(runtime):
    cls = getattr(runtime, "OfertaDecisionView", None)
    if cls is None or getattr(cls, "_ajap_squad_limits", False):
        return
    original_init = cls.__init__

    def guarded_init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        offer_id = int(getattr(self, "offer_id", getattr(self, "oferta_id", 0)) or 0)
        for child in self.children:
            if not offer_id or not isinstance(child, discord.ui.Button) or str(child.label or "").casefold() != "aceptar":
                continue
            original_callback = child.callback

            async def accept(interaction, _original=original_callback, _id=offer_id):
                offer = APP.oferta_por_id(_id)
                if offer and (offer["status"] or "").upper() == "PENDIENTE":
                    ok, reason = validate_offer(offer)
                    if not ok:
                        await interaction.response.send_message(reason, ephemeral=True)
                        return
                await _original(interaction)

            child.callback = accept

    cls.__init__ = guarded_init
    cls._ajap_squad_limits = True


def _guard_loan_publication():
    cls = publication_options.PublicationTypeView
    if getattr(cls, "_ajap_squad_limits", False):
        return
    original_init = cls.__init__

    def guarded_init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        for child in self.children:
            if not isinstance(child, discord.ui.Button) or str(child.label or "").casefold() != "préstamo":
                continue
            original_callback = child.callback

            async def loan(interaction, _original=original_callback):
                club = getattr(self, "club", None) or APP.club_de(interaction.user.id)
                if club:
                    with APP.db() as conn:
                        s = state(conn, club)
                    if s["active"] <= MIN_SQUAD_SIZE:
                        await interaction.response.send_message(min_loan_reason(club, s), ephemeral=True)
                        return
                await _original(interaction)

            child.callback = loan

    cls.__init__ = guarded_init
    cls._ajap_squad_limits = True


def _guard_staff():
    if getattr(staff_review, "_ajap_squad_limits", False):
        return
    original_approve = staff_review._approve_deal
    original_apply = staff_review._apply_deal_to_pes

    def approve(transfer_id, staff_id):
        rows = staff_review.market_reports._deal_rows(transfer_id)
        if rows and all((r["status"] or "").upper() == "PENDIENTE_ADMIN" for r in rows):
            ok, reason = validate_rows(rows)
            if not ok:
                return False, reason
        return original_approve(transfer_id, staff_id)

    def apply(transfer_id, staff_id):
        rows = staff_review.market_reports._deal_rows(transfer_id)
        if rows and all((r["status"] or "").upper() == "APROBADA" for r in rows):
            ok, reason = validate_rows(rows)
            if not ok:
                return False, reason
        return original_apply(transfer_id, staff_id)

    staff_review._approve_deal = approve
    staff_review._apply_deal_to_pes = apply
    staff_review._ajap_squad_limits = True


def _guard_clauses():
    if getattr(clauses, "_ajap_squad_limits", False):
        return
    original_create = clauses.create_clause_request
    original_approve = clauses.approve_request

    def create(interaction, ficha):
        buyer = APP.club_de(interaction.user.id)
        seller = ficha["club"] if ficha else None
        if buyer and seller:
            with APP.db() as conn:
                bs, ss = state(conn, buyer), state(conn, seller)
            if bs["committed"] >= MAX_SQUAD_SIZE:
                return False, max_reason(buyer, bs, "ejecutar este clausulazo")
            if ss["active"] <= MIN_SQUAD_SIZE:
                return False, min_reason(seller, ss, "perder a este jugador por clausulazo")
        return original_create(interaction, ficha)

    def approve(req, staff_id):
        fresh = clauses.request_by_id(req["id"]) if req else None
        if fresh and (fresh["status"] or "").upper() == "PENDIENTE_STAFF":
            with APP.db() as conn:
                bs, ss = state(conn, fresh["buyer_club"]), state(conn, fresh["seller_club"])
            reason = None
            if bs["committed"] >= MAX_SQUAD_SIZE:
                reason = max_reason(fresh["buyer_club"], bs, "completar este clausulazo")
            elif ss["active"] <= MIN_SQUAD_SIZE:
                reason = min_reason(fresh["seller_club"], ss, "perder a este jugador por clausulazo")
            if reason:
                clauses.reject_request(fresh, staff_id, "Bloqueado por límite global de plantel 20–32")
                return False, reason + " La solicitud fue rechazada y el importe reservado fue devuelto."
        return original_approve(req, staff_id)

    clauses.create_clause_request = create
    clauses.approve_request = approve
    clauses._ajap_squad_limits = True


def _guard_release_if_loaded():
    releases = sys.modules.get("player_release_patch")
    if releases is None or getattr(releases, "_ajap_squad_limits", False):
        return

    original_preview = releases._preview
    def preview(player, club):
        value, cost, balance, blocker = original_preview(player, club)
        if not blocker:
            with APP.db() as conn:
                ok, reason = validate_release(conn, club)
            blocker = None if ok else reason
        return value, cost, balance, blocker
    releases._preview = preview

    original_confirm = releases.ConfirmReleaseButton.callback
    async def confirm(self, interaction):
        club = APP.club_de(interaction.user.id)
        if club:
            with APP.db() as conn:
                ok, reason = validate_release(conn, club)
            if not ok:
                await interaction.response.send_message(reason, ephemeral=True)
                return
        await original_confirm(self, interaction)
    releases.ConfirmReleaseButton.callback = confirm
    releases._ajap_squad_limits = True


def apply_squad_limits_patch(runtime, bot=None):
    global APP
    APP = runtime
    if getattr(runtime, "_ajap_squad_limits_patch", False):
        return

    runtime.MIN_SQUAD_SIZE = MIN_SQUAD_SIZE
    runtime.MAX_SQUAD_SIZE = MAX_SQUAD_SIZE
    runtime.squad_state = lambda club: _runtime_state(club)
    runtime.validate_release_squad_limit = validate_release
    runtime.validate_free_agent_squad_limit = validate_free_agent

    _guard_offer_modal(runtime)
    _guard_decision_view(runtime)
    _guard_loan_publication()
    _guard_staff()
    _guard_clauses()
    _guard_release_if_loaded()

    runtime._ajap_squad_limits_patch = True
    print(
        "AJAP límites de plantel activos: mínimo 20 activos • máximo 32 comprometidos "
        "• cedidos propios reservan plaza • 1x1 permanente permitido"
    )


def _runtime_state(club):
    with APP.db() as conn:
        return state(conn, club)
