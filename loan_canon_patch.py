"""Fixed seasonal loan canon for AJAP Transfer Market.

Rule:
- every loan pays a non-negotiable canon equal to 10% of the player's AJAP
  market value per contracted season;
- the first canon is due when Staff applies the loan to the official roster;
- later canons are charged automatically when each new contracted season starts;
- loan screens/notices show the per-season canon and expected total before the
  clubs accept the operation;
- every successful canon payment is audited in treasury_transactions so the
  future Tesoreria UI can expose the same source of truth.
"""

from __future__ import annotations

import discord

import economy_values_patch as economy
import loan_lifecycle_patch as loans
import loan_terms_patch as terms
import market_channel_report_patch as market_reports
import offer_notifications_patch as offer_notifications
import publication_announce_patch as publication_announce


CANON_RATE_PERCENT = 10
CANON_RATE = CANON_RATE_PERCENT / 100

_ORIGINAL_LOAN_TERMS_TEXT = terms._loan_terms_text
_ORIGINAL_APPLY_NEGOTIATION = terms.apply_loan_terms_negotiation_patch
_ORIGINAL_PUBLICATION_EMBED = publication_announce.publication_embed
_ORIGINAL_MOVEMENT_EMBED = market_reports.movement_embed
_ORIGINAL_ENSURE_SCHEMA = loans.ensure_schema
_ORIGINAL_SYNC_APPLIED_LOANS = loans.sync_applied_loans
_ORIGINAL_PROCESS_SEASON_TRANSITION = loans.process_season_transition
_ORIGINAL_APPLY_LIFECYCLE = loans.apply_loan_lifecycle_patch


def _has(row, key):
    return row is not None and key in row.keys()


def _app():
    return loans.APP or terms.APP or market_reports.APP


def _market_value(player) -> int:
    if not player:
        return 0
    app = _app()
    resolver = getattr(app, "player_market_value", None) if app else None
    if resolver:
        try:
            value = int(resolver(player) or 0)
            if value > 0:
                return value
        except (TypeError, ValueError):
            pass
    if _has(player, "min_sale_value") and player["min_sale_value"] is not None:
        try:
            value = int(player["min_sale_value"])
            if value > 0:
                return value
        except (TypeError, ValueError):
            pass
    if _has(player, "rating") and player["rating"] is not None:
        return int(economy.market_value_for_rating(player["rating"]) or 0)
    return 0


def canon_for_player(player) -> int:
    value = _market_value(player)
    return int(round(value * CANON_RATE)) if value > 0 else 0


def _player_for_name(name):
    app = _app()
    return app.jugador_por_nombre(name) if app and name else None


def _canon_for_offer(offer) -> int:
    if not offer:
        return 0
    return canon_for_player(_player_for_name(offer["player"]))


def _fmt(value: int) -> str:
    app = _app()
    if app and hasattr(app, "money"):
        return app.money(str(int(value)))
    return f"${int(value):,}".replace(",", ".")


def _seasons_for_offer(offer) -> int:
    seasons = terms._loan_seasons(offer)
    return int(seasons or 0)


def _canon_summary(offer) -> str:
    canon = _canon_for_offer(offer)
    seasons = _seasons_for_offer(offer)
    if canon <= 0:
        return "Canon pendiente de calcular"
    text = f"{_fmt(canon)} por temporada • fijo ({CANON_RATE_PERCENT}% del valor de mercado)"
    if seasons > 0:
        text += f"\n🧾 Total previsto: **{_fmt(canon * seasons)}**"
    return text


# ---------------------------------------------------------------------------
# Before acceptance: show the fixed canon everywhere the loan terms are shown.
# ---------------------------------------------------------------------------
def _loan_terms_text_with_canon(offer):
    text = _ORIGINAL_LOAN_TERMS_TEXT(offer)
    if terms._offer_is_loan(offer):
        text += f"\n💵 **Canon:** {_canon_summary(offer)}"
    return text


terms._loan_terms_text = _loan_terms_text_with_canon


def _apply_negotiation_with_canon(main_module):
    _ORIGINAL_APPLY_NEGOTIATION(main_module)
    if getattr(main_module, "_ajap_loan_canon_offer_embed", False):
        return

    current_offer_embed = offer_notifications._offer_embed

    def offer_embed_with_canon(offer, *, private=False):
        embed = current_offer_embed(offer, private=private)
        if terms._offer_is_loan(offer):
            embed.add_field(
                name="💵 Canon obligatorio",
                value=_canon_summary(offer),
                inline=False,
            )
        return embed

    offer_notifications._offer_embed = offer_embed_with_canon
    main_module._ajap_loan_canon_offer_embed = True


terms.apply_loan_terms_negotiation_patch = _apply_negotiation_with_canon


def _publication_embed_with_canon(publication):
    embed = _ORIGINAL_PUBLICATION_EMBED(publication)
    app = _app() or publication_announce.APP
    if not app:
        return embed
    try:
        is_loan = app.normalizar_tipo(publication["operation_type"]) == "PRÉSTAMO"
    except Exception:
        is_loan = str(publication["operation_type"] or "").upper() in {"PRÉSTAMO", "PRESTAMO"}
    if not is_loan:
        return embed
    player = app.jugador_por_nombre(publication["player"])
    canon = canon_for_player(player)
    if canon > 0:
        embed.add_field(
            name="💵 Canon de cesión",
            value=(
                f"**{_fmt(canon)} por temporada**\n"
                f"Fijo: {CANON_RATE_PERCENT}% del valor de mercado • no negociable"
            ),
            inline=False,
        )
    return embed


publication_announce.publication_embed = _publication_embed_with_canon


def _movement_embed_with_canon(transfer_id: int):
    embed = _ORIGINAL_MOVEMENT_EMBED(transfer_id)
    rows = market_reports._deal_rows(transfer_id)
    loan_row = next(
        (
            row for row in rows
            if str(row["operation_type"] or "").upper() in {"PRÉSTAMO", "PRESTAMO"}
        ),
        None,
    )
    if not loan_row:
        return embed
    app = market_reports.APP or _app()
    player = app.jugador_por_id(int(loan_row["player_id"])) if app and loan_row["player_id"] else None
    canon = canon_for_player(player)
    seasons = int(loan_row["loan_seasons"] or 0) if _has(loan_row, "loan_seasons") else 0
    if canon > 0:
        text = f"**{_fmt(canon)} por temporada** • fijo ({CANON_RATE_PERCENT}%)"
        if seasons > 0:
            text += f"\n🧾 Total previsto del contrato: **{_fmt(canon * seasons)}**"
        embed.add_field(name="💵 Canon de préstamo", value=text, inline=False)
    return embed


market_reports.movement_embed = _movement_embed_with_canon


# ---------------------------------------------------------------------------
# Persistence and audit.
# ---------------------------------------------------------------------------
def _ensure_canon_tables():
    if loans.APP is None:
        return
    with loans.APP.db() as conn:
        columns = {row["name"] for row in conn.execute("PRAGMA table_info(loans)").fetchall()}
        if "canon_per_season" not in columns:
            conn.execute("ALTER TABLE loans ADD COLUMN canon_per_season INTEGER")
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS loan_canon_payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                loan_id INTEGER NOT NULL,
                season_id INTEGER NOT NULL,
                player_id INTEGER,
                player TEXT NOT NULL,
                payer_club TEXT NOT NULL,
                payee_club TEXT NOT NULL,
                amount INTEGER NOT NULL,
                payer_balance_before INTEGER NOT NULL,
                payer_balance_after INTEGER NOT NULL,
                payee_balance_before INTEGER NOT NULL,
                payee_balance_after INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'PAID',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(loan_id, season_id)
            );

            CREATE TABLE IF NOT EXISTS loan_canon_dues (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                loan_id INTEGER NOT NULL,
                season_id INTEGER NOT NULL,
                amount INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'PENDING',
                reason TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                resolved_at DATETIME,
                UNIQUE(loan_id, season_id)
            );

            CREATE TABLE IF NOT EXISTS treasury_transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                club TEXT NOT NULL COLLATE NOCASE,
                season_id INTEGER,
                direction TEXT NOT NULL,
                category TEXT NOT NULL,
                amount INTEGER NOT NULL,
                player_id INTEGER,
                player TEXT,
                counterparty TEXT,
                reference_type TEXT,
                reference_id INTEGER,
                description TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(club, direction, category, reference_type, reference_id, season_id)
            );
            """
        )


def _ensure_schema_with_canon():
    _ORIGINAL_ENSURE_SCHEMA()
    _ensure_canon_tables()


loans.ensure_schema = _ensure_schema_with_canon


def _initialize_loan_canons():
    if loans.APP is None:
        return 0
    _ensure_canon_tables()
    with loans.APP.db() as conn:
        rows = conn.execute(
            "SELECT * FROM loans WHERE canon_per_season IS NULL ORDER BY id"
        ).fetchall()
        updated = 0
        for loan in rows:
            player = conn.execute(
                "SELECT * FROM roster_players WHERE id = ? LIMIT 1",
                (int(loan["player_id"]),),
            ).fetchone()
            canon = canon_for_player(player)
            conn.execute(
                "UPDATE loans SET canon_per_season = ? WHERE id = ?",
                (int(canon), int(loan["id"])),
            )
            updated += 1
    return updated


def _record_treasury(conn, *, club, season_id, direction, amount, loan, counterparty):
    conn.execute(
        """
        INSERT OR IGNORE INTO treasury_transactions
        (club, season_id, direction, category, amount, player_id, player, counterparty,
         reference_type, reference_id, description)
        VALUES (?, ?, ?, 'CANON_PRÉSTAMO', ?, ?, ?, ?, 'LOAN_CANON', ?, ?)
        """,
        (
            club,
            int(season_id) if season_id else None,
            direction,
            int(amount),
            loan["player_id"],
            loan["player"],
            counterparty,
            int(loan["id"]),
            (
                f"Canon temporada {season_id} de {loan['player']} • "
                f"Préstamo #{loan['id']}"
            ),
        ),
    )


def _mark_due(conn, loan, season_id, amount, reason):
    conn.execute(
        """
        INSERT INTO loan_canon_dues (loan_id, season_id, amount, status, reason)
        VALUES (?, ?, ?, 'PENDING', ?)
        ON CONFLICT(loan_id, season_id) DO UPDATE SET
            amount = excluded.amount,
            status = 'PENDING',
            reason = excluded.reason,
            resolved_at = NULL
        """,
        (int(loan["id"]), int(season_id), int(amount), reason),
    )


def _charge_canon(loan_id: int, season_id: int):
    _ensure_canon_tables()
    conn = loans.APP.db()
    try:
        conn.execute("BEGIN IMMEDIATE")
        loan = conn.execute("SELECT * FROM loans WHERE id = ?", (int(loan_id),)).fetchone()
        if not loan:
            conn.rollback()
            return False, "Préstamo no encontrado."

        paid = conn.execute(
            "SELECT 1 FROM loan_canon_payments WHERE loan_id = ? AND season_id = ? LIMIT 1",
            (int(loan_id), int(season_id)),
        ).fetchone()
        if paid:
            conn.rollback()
            return True, "Canon ya pagado."

        amount = int(loan["canon_per_season"] or 0)
        if amount <= 0:
            player = conn.execute(
                "SELECT * FROM roster_players WHERE id = ? LIMIT 1",
                (int(loan["player_id"]),),
            ).fetchone()
            amount = canon_for_player(player)
            conn.execute(
                "UPDATE loans SET canon_per_season = ? WHERE id = ?",
                (int(amount), int(loan_id)),
            )
        if amount <= 0:
            conn.rollback()
            return False, "No se pudo calcular el canon del jugador."

        for club in (loan["borrower_club"], loan["owner_club"]):
            conn.execute("INSERT OR IGNORE INTO club_finances (club, balance) VALUES (?, 0)", (club,))

        payer = conn.execute(
            "SELECT balance FROM club_finances WHERE club = ? COLLATE NOCASE",
            (loan["borrower_club"],),
        ).fetchone()
        payee = conn.execute(
            "SELECT balance FROM club_finances WHERE club = ? COLLATE NOCASE",
            (loan["owner_club"],),
        ).fetchone()
        payer_before = int(payer["balance"] if payer else 0)
        payee_before = int(payee["balance"] if payee else 0)

        if payer_before < amount:
            reason = (
                f"Saldo insuficiente: {loan['borrower_club']} tiene {_fmt(payer_before)} "
                f"y debe {_fmt(amount)} de canon."
            )
            _mark_due(conn, loan, season_id, amount, reason)
            conn.commit()
            return False, reason

        payer_after = payer_before - amount
        payee_after = payee_before + amount
        conn.execute(
            "UPDATE club_finances SET balance = ?, updated_at = CURRENT_TIMESTAMP WHERE club = ? COLLATE NOCASE",
            (payer_after, loan["borrower_club"]),
        )
        conn.execute(
            "UPDATE club_finances SET balance = ?, updated_at = CURRENT_TIMESTAMP WHERE club = ? COLLATE NOCASE",
            (payee_after, loan["owner_club"]),
        )
        conn.execute(
            """
            INSERT INTO loan_canon_payments
            (loan_id, season_id, player_id, player, payer_club, payee_club, amount,
             payer_balance_before, payer_balance_after, payee_balance_before, payee_balance_after)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                loan["id"], int(season_id), loan["player_id"], loan["player"],
                loan["borrower_club"], loan["owner_club"], amount,
                payer_before, payer_after, payee_before, payee_after,
            ),
        )
        conn.execute(
            """
            UPDATE loan_canon_dues
            SET status = 'PAID', resolved_at = CURRENT_TIMESTAMP
            WHERE loan_id = ? AND season_id = ?
            """,
            (int(loan_id), int(season_id)),
        )
        _record_treasury(
            conn,
            club=loan["borrower_club"],
            season_id=season_id,
            direction="EGRESO",
            amount=amount,
            loan=loan,
            counterparty=loan["owner_club"],
        )
        _record_treasury(
            conn,
            club=loan["owner_club"],
            season_id=season_id,
            direction="INGRESO",
            amount=amount,
            loan=loan,
            counterparty=loan["borrower_club"],
        )
        conn.commit()
        return True, f"Canon pagado: {_fmt(amount)}."
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _sync_with_first_canon(current_season_id=None):
    created = _ORIGINAL_SYNC_APPLIED_LOANS(current_season_id)
    _initialize_loan_canons()
    if loans.APP is None:
        return created
    with loans.APP.db() as conn:
        pending = conn.execute(
            """
            SELECT l.*
            FROM loans l
            LEFT JOIN loan_canon_payments p
              ON p.loan_id = l.id AND p.season_id = l.last_counted_season_id
            WHERE l.status = 'ACTIVE'
              AND l.last_counted_season_id IS NOT NULL
              AND p.id IS NULL
            ORDER BY l.id
            """
        ).fetchall()
    for loan in pending:
        _charge_canon(int(loan["id"]), int(loan["last_counted_season_id"]))
    return created


loans.sync_applied_loans = _sync_with_first_canon


async def _process_transition_with_canon(old_season_id, new_season_id):
    stats = await _ORIGINAL_PROCESS_SEASON_TRANSITION(old_season_id, new_season_id)
    stats.setdefault("canon_paid", 0)
    stats.setdefault("canon_pending", 0)
    if not old_season_id or not new_season_id or int(old_season_id) == int(new_season_id):
        return stats

    _initialize_loan_canons()
    with loans.APP.db() as conn:
        continuing = conn.execute(
            """
            SELECT * FROM loans
            WHERE status = 'ACTIVE'
              AND last_counted_season_id = ?
              AND remaining_seasons > 0
            ORDER BY id
            """,
            (int(new_season_id),),
        ).fetchall()

    for loan in continuing:
        ok, message = _charge_canon(int(loan["id"]), int(new_season_id))
        if ok:
            stats["canon_paid"] += 1
        else:
            stats["canon_pending"] += 1
            text = (
                f"⚠️ Canon pendiente de **{loan['player']}** para la nueva temporada.\n"
                f"**{loan['borrower_club']}** debe pagar **{_fmt(int(loan['canon_per_season'] or 0))}** "
                f"a **{loan['owner_club']}**.\n{message}"
            )
            try:
                await loans._dm(loan["borrower_user_id"], content=text)
                await loans._dm(loan["owner_user_id"], content=text)
            except Exception:
                pass
    return stats


loans.process_season_transition = _process_transition_with_canon


def _canon_for_transfer_row(row):
    app = loans.APP
    if not app or not row:
        return 0
    player = app.jugador_por_id(int(row["player_id"])) if row["player_id"] else app.jugador_por_nombre(row["player"])
    return canon_for_player(player)


def _initial_canon_affordability(transfer_id: int):
    rows = market_reports._deal_rows(int(transfer_id))
    loan_rows = [
        row for row in rows
        if str(row["operation_type"] or "").upper() in {"PRÉSTAMO", "PRESTAMO"}
    ]
    if not loan_rows:
        return True, None

    totals = {}
    for row in loan_rows:
        canon = _canon_for_transfer_row(row)
        if canon <= 0:
            return False, f"No se pudo calcular el canon de **{row['player']}**."
        totals[row["buyer"]] = totals.get(row["buyer"], 0) + canon

    with loans.APP.db() as conn:
        for club, required in totals.items():
            finance = conn.execute(
                "SELECT balance FROM club_finances WHERE club = ? COLLATE NOCASE",
                (club,),
            ).fetchone()
            balance = int(finance["balance"] if finance else 0)
            if balance < required:
                return False, (
                    f"**{club}** no puede iniciar el préstamo: necesita **{_fmt(required)}** "
                    f"para el canon de la primera temporada y tiene **{_fmt(balance)}**."
                )
    return True, None


def _patch_runtime_admin_apply(runtime):
    view_cls = getattr(runtime, "OperacionAdminView", None)
    if view_cls is None or getattr(view_cls, "_ajap_loan_canon_guard", False):
        return
    original_init = view_cls.__init__

    def guarded_init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        transfer_id = int(getattr(self, "operacion_id", 0) or 0)
        if not transfer_id:
            return
        for child in self.children:
            if not isinstance(child, discord.ui.Button) or child.label != "Aplicado en PES":
                continue
            original_callback = child.callback

            async def apply_with_canon(interaction, _original=original_callback, _transfer_id=transfer_id):
                ok, error = _initial_canon_affordability(_transfer_id)
                if not ok:
                    await interaction.response.send_message(f"⛔ {error}", ephemeral=True)
                    return
                await _original(interaction)
                try:
                    loans.sync_applied_loans()
                except Exception as exc:
                    print(f"WARNING AJAP: canon inicial operación #{_transfer_id} no sincronizado: {exc}")

            child.callback = apply_with_canon
            break

    view_cls.__init__ = guarded_init
    view_cls._ajap_loan_canon_guard = True


def _patch_staff_channel_apply():
    import staff_review_channel_patch as staff_review

    if getattr(staff_review, "_ajap_loan_canon_guard", False):
        return
    original_apply = staff_review._apply_deal_to_pes

    def apply_with_canon(transfer_id, staff_id):
        ok, error = _initial_canon_affordability(int(transfer_id))
        if not ok:
            return False, error
        result = original_apply(transfer_id, staff_id)
        if result[0]:
            try:
                loans.sync_applied_loans()
            except Exception as exc:
                print(f"WARNING AJAP: canon inicial Staff operación #{transfer_id} no sincronizado: {exc}")
        return result

    staff_review._apply_deal_to_pes = apply_with_canon
    staff_review._ajap_loan_canon_guard = True


def _apply_lifecycle_with_canon(runtime, bot):
    result = _ORIGINAL_APPLY_LIFECYCLE(runtime, bot)
    _ensure_canon_tables()
    _initialize_loan_canons()
    _patch_runtime_admin_apply(runtime)
    _patch_staff_channel_apply()
    runtime.loan_canon_rate_percent = CANON_RATE_PERCENT
    runtime.loan_canon_for_player = canon_for_player
    runtime.charge_loan_canon = _charge_canon
    runtime._ajap_loan_canon_patch = True
    print(
        "AJAP préstamos: canon fijo 10% por temporada + primer pago al aplicar + "
        "cobro automático por nueva temporada + auditoría de tesorería"
    )
    return result


loans.apply_loan_lifecycle_patch = _apply_lifecycle_with_canon
