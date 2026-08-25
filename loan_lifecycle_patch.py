"""Loan lifecycle for AJAP Transfer Market.

Tracks contractual ownership separately from the roster while a player is on
loan. A loan starts only after its PRÉSTAMO transfer is marked APLICADA in PES.
Every season change consumes one loan season. At expiry the player either:
- gets a purchase-option decision (execute / return), or
- automatically generates a DEVOLUCIÓN PRÉSTAMO admin operation.

If a purchase option is not answered before the next season change, the bot
automatically creates the return operation. Loaned-in players are not allowed
to be published as if the borrowing club owned them.
"""

import discord

import lyon_test_seed as lyon
import publish_ovr_patch as publish

APP = None
BOT = None
_ORIGINAL_PUBLISHABLE = None
_ORIGINAL_RANGES_EMBED = None
_ORIGINAL_RATED_EMBED = None
_ORIGINAL_PUBLISH_SUBMIT = None


def ensure_schema():
    with APP.db() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS loans (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_transfer_id INTEGER NOT NULL UNIQUE,
                offer_id INTEGER,
                player_id INTEGER NOT NULL,
                player TEXT NOT NULL,
                owner_club TEXT NOT NULL,
                borrower_club TEXT NOT NULL,
                owner_user_id INTEGER,
                borrower_user_id INTEGER,
                start_season_id INTEGER,
                last_counted_season_id INTEGER,
                total_seasons INTEGER NOT NULL,
                remaining_seasons INTEGER NOT NULL,
                purchase_option_value TEXT,
                status TEXT NOT NULL DEFAULT 'ACTIVE',
                option_opened_season_id INTEGER,
                return_transfer_id INTEGER,
                purchase_transfer_id INTEGER,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                resolved_at DATETIME
            );

            CREATE TABLE IF NOT EXISTS loan_option_payments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                loan_id INTEGER NOT NULL,
                buyer_club TEXT NOT NULL,
                seller_club TEXT NOT NULL,
                amount INTEGER NOT NULL,
                buyer_balance_before INTEGER NOT NULL,
                buyer_balance_after INTEGER NOT NULL,
                seller_balance_before INTEGER NOT NULL,
                seller_balance_after INTEGER NOT NULL,
                executed_by INTEGER NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS club_finances (
                club TEXT PRIMARY KEY COLLATE NOCASE,
                balance INTEGER NOT NULL DEFAULT 0,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );
            """
        )


def _season_id():
    season = APP.temporada_activa()
    return int(season["id"]) if season else None


def _club_user(club):
    if not club:
        return None
    with APP.db() as conn:
        row = conn.execute(
            "SELECT user_id FROM clubs WHERE name = ? COLLATE NOCASE ORDER BY created_at ASC LIMIT 1",
            (club,),
        ).fetchone()
    return int(row["user_id"]) if row else None


def sync_applied_loans(current_season_id=None):
    """Register applied loan transfers. The clock starts only after APLICADA."""
    current_season_id = current_season_id or _season_id()
    with APP.db() as conn:
        rows = conn.execute(
            """
            SELECT t.*, o.from_id AS borrower_user, o.to_id AS owner_user
            FROM transfers t
            LEFT JOIN offers o ON o.id = t.offer_id
            LEFT JOIN loans l ON l.source_transfer_id = t.id
            WHERE t.operation_type = 'PRÉSTAMO'
              AND t.status = 'APLICADA'
              AND t.loan_seasons IS NOT NULL
              AND t.loan_seasons > 0
              AND l.id IS NULL
            ORDER BY t.id ASC
            """
        ).fetchall()

    created = 0
    for transfer in rows:
        player = APP.jugador_por_id(int(transfer["player_id"])) if transfer["player_id"] else None
        if not player or player["club"].casefold() != transfer["buyer"].casefold():
            continue

        total = int(transfer["loan_seasons"])
        owner_user = transfer["owner_user"] if transfer["owner_user"] is not None else _club_user(transfer["seller"])
        borrower_user = transfer["borrower_user"] if transfer["borrower_user"] is not None else _club_user(transfer["buyer"])
        anchor = current_season_id or transfer["season_id"]
        with APP.db() as conn:
            cur = conn.execute(
                """
                INSERT OR IGNORE INTO loans
                (source_transfer_id, offer_id, player_id, player, owner_club, borrower_club,
                 owner_user_id, borrower_user_id, start_season_id, last_counted_season_id,
                 total_seasons, remaining_seasons, purchase_option_value, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'ACTIVE')
                """,
                (
                    transfer["id"], transfer["offer_id"], transfer["player_id"], transfer["player"],
                    transfer["seller"], transfer["buyer"], owner_user, borrower_user,
                    transfer["season_id"], anchor, total, total, transfer["purchase_option_value"],
                ),
            )
            if cur.rowcount:
                created += 1
    return created


def reconcile_returns():
    with APP.db() as conn:
        rows = conn.execute(
            """
            SELECT l.id, t.status AS transfer_status
            FROM loans l
            LEFT JOIN transfers t ON t.id = l.return_transfer_id
            WHERE l.status = 'RETURN_PENDING'
            """
        ).fetchall()
        for row in rows:
            if row["transfer_status"] == "APLICADA":
                conn.execute(
                    "UPDATE loans SET status = 'RETURNED', resolved_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (row["id"],),
                )


def loan_by_id(loan_id):
    with APP.db() as conn:
        return conn.execute("SELECT * FROM loans WHERE id = ?", (int(loan_id),)).fetchone()


def active_loan_for_player(player_id):
    reconcile_returns()
    sync_applied_loans()
    with APP.db() as conn:
        return conn.execute(
            """
            SELECT * FROM loans
            WHERE player_id = ?
              AND status IN ('ACTIVE','OPTION_PENDING','RETURN_PENDING','REVIEW_REQUIRED')
            ORDER BY id DESC LIMIT 1
            """,
            (int(player_id),),
        ).fetchone()


def loans_for_club(club):
    reconcile_returns()
    sync_applied_loans()
    with APP.db() as conn:
        return conn.execute(
            """
            SELECT * FROM loans
            WHERE (owner_club = ? COLLATE NOCASE OR borrower_club = ? COLLATE NOCASE)
              AND status IN ('ACTIVE','OPTION_PENDING','RETURN_PENDING','REVIEW_REQUIRED')
            ORDER BY id DESC
            """,
            (club, club),
        ).fetchall()


def _cancel_market_activity(conn, player):
    conn.execute(
        "UPDATE publications SET active = 0 WHERE player = ? COLLATE NOCASE AND active = 1",
        (player,),
    )
    conn.execute(
        "UPDATE offers SET status = 'CANCELADA' WHERE player = ? COLLATE NOCASE AND status = 'PENDIENTE'",
        (player,),
    )


def create_return_operation(loan_id, season_id=None, reason="Fin del préstamo"):
    season_id = season_id or _season_id()
    conn = APP.db()
    try:
        conn.execute("BEGIN IMMEDIATE")
        loan = conn.execute("SELECT * FROM loans WHERE id = ?", (int(loan_id),)).fetchone()
        if not loan:
            conn.rollback()
            return False, "Préstamo no encontrado.", None
        if loan["return_transfer_id"]:
            existing = int(loan["return_transfer_id"])
            conn.rollback()
            return True, "La devolución ya estaba creada.", existing
        if loan["status"] in ("PURCHASED", "RETURNED"):
            conn.rollback()
            return False, "El préstamo ya está resuelto.", None

        player = conn.execute("SELECT * FROM roster_players WHERE id = ?", (loan["player_id"],)).fetchone()
        if not player:
            conn.execute("UPDATE loans SET status = 'REVIEW_REQUIRED' WHERE id = ?", (loan["id"],))
            conn.commit()
            return False, "El jugador ya no existe en el plantel oficial.", None
        if player["club"].casefold() == loan["owner_club"].casefold():
            conn.execute(
                "UPDATE loans SET status = 'RETURNED', resolved_at = CURRENT_TIMESTAMP WHERE id = ?",
                (loan["id"],),
            )
            conn.commit()
            return True, "El jugador ya había regresado.", None
        if player["club"].casefold() != loan["borrower_club"].casefold():
            conn.execute("UPDATE loans SET status = 'REVIEW_REQUIRED' WHERE id = ?", (loan["id"],))
            conn.commit()
            return False, f"El jugador figura en {player['club']}; Staff debe revisar el caso.", None

        _cancel_market_activity(conn, loan["player"])
        notes = (
            f"{reason} | Préstamo #{loan['id']} | Dueño contractual: {loan['owner_club']} | "
            f"Club cesionario: {loan['borrower_club']}"
        )
        cur = conn.execute(
            """
            INSERT INTO transfers
            (player, seller, buyer, amount, offer_id, player_id, operation_type, season_id,
             status, notes, deal_group)
            VALUES (?, ?, ?, '$0', ?, ?, 'DEVOLUCIÓN PRÉSTAMO', ?, 'PENDIENTE_ADMIN', ?, ?)
            """,
            (
                loan["player"], loan["borrower_club"], loan["owner_club"], loan["offer_id"] or 0,
                loan["player_id"], season_id, notes, f"PRESTAMO-RETURN-{loan['id']}",
            ),
        )
        op_id = cur.lastrowid
        conn.execute(
            "UPDATE loans SET status = 'RETURN_PENDING', return_transfer_id = ?, remaining_seasons = 0 WHERE id = ?",
            (op_id, loan["id"]),
        )
        conn.commit()
        return True, "Devolución creada.", op_id
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def execute_purchase_option(loan_id, user_id):
    conn = APP.db()
    try:
        conn.execute("BEGIN IMMEDIATE")
        loan = conn.execute("SELECT * FROM loans WHERE id = ?", (int(loan_id),)).fetchone()
        if not loan:
            conn.rollback()
            return False, "Préstamo no encontrado.", None
        if loan["status"] != "OPTION_PENDING":
            conn.rollback()
            return False, "La opción de compra ya no está disponible.", None
        expected = loan["borrower_user_id"] or _club_user(loan["borrower_club"])
        if expected is not None and int(user_id) != int(expected):
            conn.rollback()
            return False, "Solo el manager del club cesionario puede ejecutar la compra.", None

        amount = APP.price_number(loan["purchase_option_value"] or "")
        if amount is None or amount <= 0:
            conn.rollback()
            return False, "La opción de compra no tiene un importe válido.", None

        player = conn.execute("SELECT * FROM roster_players WHERE id = ?", (loan["player_id"],)).fetchone()
        if not player or player["club"].casefold() != loan["borrower_club"].casefold():
            conn.rollback()
            return False, "El jugador ya no figura en el club cesionario. Staff debe revisar el caso.", None

        for club in (loan["borrower_club"], loan["owner_club"]):
            conn.execute("INSERT OR IGNORE INTO club_finances (club, balance) VALUES (?, 0)", (club,))
        buyer = conn.execute(
            "SELECT balance FROM club_finances WHERE club = ? COLLATE NOCASE", (loan["borrower_club"],)
        ).fetchone()
        seller = conn.execute(
            "SELECT balance FROM club_finances WHERE club = ? COLLATE NOCASE", (loan["owner_club"],)
        ).fetchone()
        buyer_before = int(buyer["balance"] if buyer else 0)
        seller_before = int(seller["balance"] if seller else 0)
        if buyer_before < amount:
            conn.rollback()
            return False, (
                f"Saldo insuficiente: {loan['borrower_club']} tiene {APP.money(str(buyer_before))} "
                f"y la opción cuesta {APP.money(str(amount))}."
            ), None

        buyer_after = buyer_before - amount
        seller_after = seller_before + amount
        conn.execute(
            "UPDATE club_finances SET balance = ?, updated_at = CURRENT_TIMESTAMP WHERE club = ? COLLATE NOCASE",
            (buyer_after, loan["borrower_club"]),
        )
        conn.execute(
            "UPDATE club_finances SET balance = ?, updated_at = CURRENT_TIMESTAMP WHERE club = ? COLLATE NOCASE",
            (seller_after, loan["owner_club"]),
        )

        season_id = _season_id()
        cur = conn.execute(
            """
            INSERT INTO transfers
            (player, seller, buyer, amount, offer_id, player_id, operation_type, season_id,
             status, notes, deal_group, approved_at, applied_at)
            VALUES (?, ?, ?, ?, ?, ?, 'OPCIÓN DE COMPRA', ?, 'APLICADA', ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            """,
            (
                loan["player"], loan["owner_club"], loan["borrower_club"], APP.money(str(amount)),
                loan["offer_id"] or 0, loan["player_id"], season_id,
                f"Opción ejecutada al finalizar préstamo #{loan['id']}", f"PRESTAMO-BUY-{loan['id']}",
            ),
        )
        transfer_id = cur.lastrowid
        conn.execute(
            """
            INSERT INTO player_history
            (player_id, player, from_club, to_club, transfer_id, season_id, event_type)
            VALUES (?, ?, ?, ?, ?, ?, 'OPCIÓN DE COMPRA')
            """,
            (loan["player_id"], loan["player"], loan["owner_club"], loan["borrower_club"], transfer_id, season_id),
        )
        conn.execute(
            """
            INSERT INTO loan_option_payments
            (loan_id, buyer_club, seller_club, amount, buyer_balance_before, buyer_balance_after,
             seller_balance_before, seller_balance_after, executed_by)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                loan["id"], loan["borrower_club"], loan["owner_club"], amount,
                buyer_before, buyer_after, seller_before, seller_after, int(user_id),
            ),
        )
        _cancel_market_activity(conn, loan["player"])
        conn.execute(
            """
            UPDATE loans SET status = 'PURCHASED', purchase_transfer_id = ?,
                remaining_seasons = 0, resolved_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (transfer_id, loan["id"]),
        )
        conn.commit()
        return True, "Compra ejecutada.", {
            "amount": amount, "buyer_after": buyer_after, "transfer_id": transfer_id, "loan": loan
        }
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


async def _fetch_user(user_id):
    if not user_id:
        return None
    try:
        user = BOT.get_user(int(user_id))
        if user is None:
            user = await BOT.fetch_user(int(user_id))
        return user
    except (discord.NotFound, discord.HTTPException):
        return None


async def _dm(user_id, *, content=None, embed=None, view=None):
    user = await _fetch_user(user_id)
    if not user:
        return False
    try:
        await user.send(content=content, embed=embed, view=view)
        return True
    except (discord.Forbidden, discord.HTTPException):
        return False


class LoanOptionDecisionView(discord.ui.View):
    def __init__(self, loan_id):
        super().__init__(timeout=None)
        self.loan_id = int(loan_id)
        for item in self.children:
            if getattr(item, "label", None) == "Ejecutar compra":
                item.custom_id = f"ajap:loan:{self.loan_id}:buy"
            elif getattr(item, "label", None) == "Devolver jugador":
                item.custom_id = f"ajap:loan:{self.loan_id}:return"

    @discord.ui.button(label="Ejecutar compra", emoji="✅", style=discord.ButtonStyle.success)
    async def buy(self, interaction: discord.Interaction, button: discord.ui.Button):
        loan = loan_by_id(self.loan_id)
        if not loan:
            await interaction.response.send_message("⚠️ Préstamo no encontrado.", ephemeral=True)
            return
        ok, message, result = execute_purchase_option(self.loan_id, interaction.user.id)
        if not ok:
            await interaction.response.send_message(f"⛔ {message}", ephemeral=True)
            return
        embed = discord.Embed(
            title="✅ Opción de compra ejecutada",
            description=(
                f"**{loan['borrower_club']}** compró definitivamente a **{loan['player']}**.\n\n"
                "El jugador ya estaba en ese plantel por el préstamo, así que no requiere otro movimiento en PES."
            ),
        )
        embed.add_field(name="Importe", value=APP.money(str(result["amount"])), inline=True)
        embed.add_field(name="Operación", value=f"#{result['transfer_id']}", inline=True)
        embed.add_field(name="Saldo nuevo", value=APP.money(str(result["buyer_after"])), inline=True)
        await interaction.response.edit_message(embed=embed, view=None)
        await _dm(
            loan["owner_user_id"],
            content=(
                f"✅ **{loan['borrower_club']} ejecutó la opción de compra de {loan['player']} "
                f"por {APP.money(str(result['amount']))}.**"
            ),
        )

    @discord.ui.button(label="Devolver jugador", emoji="↩️", style=discord.ButtonStyle.danger)
    async def give_back(self, interaction: discord.Interaction, button: discord.ui.Button):
        loan = loan_by_id(self.loan_id)
        if not loan:
            await interaction.response.send_message("⚠️ Préstamo no encontrado.", ephemeral=True)
            return
        expected = loan["borrower_user_id"] or _club_user(loan["borrower_club"])
        if expected is not None and interaction.user.id != int(expected):
            await interaction.response.send_message("⛔ Esta decisión pertenece al otro club.", ephemeral=True)
            return
        if loan["status"] != "OPTION_PENDING":
            await interaction.response.send_message("⚠️ Esta opción ya fue resuelta.", ephemeral=True)
            return
        ok, message, op_id = create_return_operation(
            self.loan_id, reason="Opción de compra no ejecutada por el club cesionario"
        )
        if not ok:
            await interaction.response.send_message(f"⚠️ {message}", ephemeral=True)
            return
        embed = discord.Embed(
            title="↩️ Devolución solicitada",
            description=(
                f"**{loan['player']}** debe volver de **{loan['borrower_club']}** a **{loan['owner_club']}**.\n\n"
                "Staff ya tiene la operación pendiente para aplicarla en PES."
            ),
        )
        if op_id:
            embed.add_field(name="Operación", value=f"#{op_id}", inline=True)
        await interaction.response.edit_message(embed=embed, view=None)
        await _dm(
            loan["owner_user_id"],
            content=f"↩️ **{loan['borrower_club']} no ejecutó la opción de compra de {loan['player']}.**",
        )


def option_embed(loan):
    embed = discord.Embed(
        title="🛒 Opción de compra disponible",
        description=f"El préstamo de **{loan['player']}** llegó a su fin.",
    )
    embed.add_field(name="Dueño contractual", value=loan["owner_club"], inline=True)
    embed.add_field(name="Club cesionario", value=loan["borrower_club"], inline=True)
    embed.add_field(name="💰 Opción de compra", value=loan["purchase_option_value"], inline=True)
    embed.add_field(name="⏳ Plazo", value="Hasta el próximo cambio de temporada", inline=True)
    embed.add_field(
        name="Acción",
        value="Elegí **Ejecutar compra** o **Devolver jugador**. Sin respuesta, se devuelve automáticamente.",
        inline=False,
    )
    embed.set_footer(text=f"Préstamo #{loan['id']}")
    return embed


async def notify_option(loan):
    await _dm(
        loan["borrower_user_id"] or _club_user(loan["borrower_club"]),
        embed=option_embed(loan),
        view=LoanOptionDecisionView(loan["id"]),
    )
    await _dm(
        loan["owner_user_id"],
        content=(
            f"⏳ Terminó el préstamo de **{loan['player']}**. **{loan['borrower_club']}** puede ejecutar "
            f"la opción de **{loan['purchase_option_value']}** hasta el próximo cambio de temporada."
        ),
    )


async def notify_return(loan, op_id, automatic=False):
    prefix = "⏰ La opción venció sin respuesta." if automatic else "⏳ El préstamo terminó sin opción de compra."
    text = (
        f"{prefix}\n**{loan['player']}** debe volver de **{loan['borrower_club']}** a **{loan['owner_club']}**."
        + (f" Operación #{op_id}." if op_id else "")
    )
    await _dm(loan["borrower_user_id"], content=text)
    await _dm(loan["owner_user_id"], content=text)


async def process_season_transition(old_season_id, new_season_id):
    stats = {"advanced": 0, "options": 0, "returns": 0, "auto_returns": 0}
    if not old_season_id or not new_season_id or int(old_season_id) == int(new_season_id):
        return stats

    reconcile_returns()
    sync_applied_loans(int(old_season_id))

    with APP.db() as conn:
        stale = conn.execute(
            "SELECT * FROM loans WHERE status = 'OPTION_PENDING' AND option_opened_season_id = ? ORDER BY id",
            (int(old_season_id),),
        ).fetchall()
    for loan in stale:
        ok, _, op_id = create_return_operation(
            loan["id"], int(new_season_id), reason="Opción de compra vencida sin respuesta"
        )
        if ok:
            stats["auto_returns"] += 1
            await notify_return(loan, op_id, automatic=True)

    with APP.db() as conn:
        active = conn.execute(
            "SELECT * FROM loans WHERE status = 'ACTIVE' AND last_counted_season_id = ? ORDER BY id",
            (int(old_season_id),),
        ).fetchall()
    for loan in active:
        remaining = max(int(loan["remaining_seasons"] or 0) - 1, 0)
        stats["advanced"] += 1
        if remaining > 0:
            with APP.db() as conn:
                conn.execute(
                    "UPDATE loans SET remaining_seasons = ?, last_counted_season_id = ? WHERE id = ?",
                    (remaining, int(new_season_id), loan["id"]),
                )
            continue

        if loan["purchase_option_value"]:
            with APP.db() as conn:
                conn.execute(
                    """
                    UPDATE loans SET remaining_seasons = 0, last_counted_season_id = ?,
                        status = 'OPTION_PENDING', option_opened_season_id = ? WHERE id = ?
                    """,
                    (int(new_season_id), int(new_season_id), loan["id"]),
                )
            refreshed = loan_by_id(loan["id"])
            stats["options"] += 1
            await notify_option(refreshed)
        else:
            with APP.db() as conn:
                conn.execute(
                    "UPDATE loans SET remaining_seasons = 0, last_counted_season_id = ? WHERE id = ?",
                    (int(new_season_id), loan["id"]),
                )
            ok, _, op_id = create_return_operation(
                loan["id"], int(new_season_id), reason="Fin del préstamo sin opción de compra"
            )
            if ok:
                stats["returns"] += 1
                await notify_return(loan, op_id)
    return stats


def _patch_season_modal():
    class LoanAwareSeasonModal(discord.ui.Modal, title="Cambiar temporada activa"):
        nombre = discord.ui.TextInput(label="Nombre", placeholder="Ej: Temporada 2", max_length=60)

        async def on_submit(self, interaction: discord.Interaction):
            if not APP.es_admin(interaction):
                await interaction.response.send_message("⛔ Solo admins.", ephemeral=True)
                return
            old = APP.temporada_activa()
            new = APP.cambiar_temporada(self.nombre.value)
            stats = {"advanced": 0, "options": 0, "returns": 0, "auto_returns": 0}
            warning = None
            if old and int(new["id"]) > int(old["id"]):
                try:
                    stats = await process_season_transition(old["id"], new["id"])
                except Exception as exc:
                    warning = "Hubo un error procesando algún préstamo. Revisá las operaciones/logs."
                    print(f"WARNING AJAP: error procesando vencimientos de préstamos: {exc}")
            elif old and int(new["id"]) < int(old["id"]):
                warning = "Se cambió a una temporada anterior; los préstamos no avanzaron."

            embed = discord.Embed(title="🗓️ Temporada actualizada", description=f"Temporada activa: **{new['name']}**.")
            if old and int(new["id"]) > int(old["id"]):
                embed.add_field(name="Préstamos avanzados", value=str(stats["advanced"]), inline=True)
                embed.add_field(name="Opciones habilitadas", value=str(stats["options"]), inline=True)
                embed.add_field(
                    name="Devoluciones generadas", value=str(stats["returns"] + stats["auto_returns"]), inline=True
                )
            if warning:
                embed.add_field(name="⚠️ Atención", value=warning, inline=False)
            await interaction.response.send_message(embed=embed, ephemeral=True)

    APP.AdminTemporadaModal = LoanAwareSeasonModal


def _patch_publish_protection():
    global _ORIGINAL_PUBLISHABLE, _ORIGINAL_PUBLISH_SUBMIT
    if _ORIGINAL_PUBLISHABLE is None:
        _ORIGINAL_PUBLISHABLE = publish.publishable_players

        def filtered(club):
            result = []
            for player in _ORIGINAL_PUBLISHABLE(club):
                loan = active_loan_for_player(player["id"])
                if loan and loan["borrower_club"].casefold() == club.casefold():
                    continue
                result.append(player)
            return result

        publish.publishable_players = filtered

    if _ORIGINAL_PUBLISH_SUBMIT is None:
        _ORIGINAL_PUBLISH_SUBMIT = lyon.RatedPublicarJugadorModal.on_submit

        async def protected_submit(modal, interaction):
            ficha = APP.jugador_por_nombre(modal.jugador)
            club = APP.club_de(interaction.user.id)
            if ficha and club:
                loan = active_loan_for_player(ficha["id"])
                if loan and loan["borrower_club"].casefold() == club.casefold():
                    await interaction.response.send_message(
                        f"⛔ **{ficha['name']}** está cedido por **{loan['owner_club']}**. No podés publicarlo.",
                        ephemeral=True,
                    )
                    return
            await _ORIGINAL_PUBLISH_SUBMIT(modal, interaction)

        lyon.RatedPublicarJugadorModal.on_submit = protected_submit


def _loan_state(loan):
    if loan["status"] == "OPTION_PENDING":
        return "Vencido • esperando opción de compra"
    if loan["status"] == "RETURN_PENDING":
        return "Vencido • devolución pendiente de Staff"
    if loan["status"] == "REVIEW_REQUIRED":
        return "Revisión administrativa requerida"
    remaining = int(loan["remaining_seasons"] or 0)
    return f"Restan {remaining} temporada{'s' if remaining != 1 else ''}"


def _append_loan_fields(embed, club):
    rows = loans_for_club(club)
    incoming = [r for r in rows if r["borrower_club"].casefold() == club.casefold()]
    outgoing = [r for r in rows if r["owner_club"].casefold() == club.casefold()]
    if incoming:
        embed.add_field(
            name="🔄 Cedidos en tu club",
            value="\n".join(
                f"**{r['player']}** • de {r['owner_club']} • {_loan_state(r)} • 🛒 {r['purchase_option_value'] or 'Sin opción'}"
                for r in incoming[:8]
            ),
            inline=False,
        )
    if outgoing:
        embed.add_field(
            name="📤 Jugadores cedidos",
            value="\n".join(
                f"**{r['player']}** • en {r['borrower_club']} • {_loan_state(r)} • 🛒 {r['purchase_option_value'] or 'Sin opción'}"
                for r in outgoing[:8]
            ),
            inline=False,
        )
    return embed


def _patch_roster_embeds():
    global _ORIGINAL_RANGES_EMBED, _ORIGINAL_RATED_EMBED
    _ORIGINAL_RANGES_EMBED = _ORIGINAL_RANGES_EMBED or lyon.plantel_ranges_embed
    _ORIGINAL_RATED_EMBED = _ORIGINAL_RATED_EMBED or lyon.rated_plantel_embed

    def ranges(club):
        return _append_loan_fields(_ORIGINAL_RANGES_EMBED(club), club)

    def rated(club, min_ovr=None, max_ovr=None, range_label=None):
        return _append_loan_fields(_ORIGINAL_RATED_EMBED(club, min_ovr, max_ovr, range_label), club)

    lyon.plantel_ranges_embed = ranges
    lyon.rated_plantel_embed = rated
    APP.plantel_embed = rated


class LoanSelect(discord.ui.Select):
    def __init__(self, club, rows):
        self.club = club
        options = []
        for loan in rows[:25]:
            direction = "Recibido" if loan["borrower_club"].casefold() == club.casefold() else "Cedido"
            options.append(
                discord.SelectOption(
                    label=f"{direction} • {loan['player']}"[:100],
                    description=f"{_loan_state(loan)} • {loan['status']}"[:100],
                    value=str(loan["id"]),
                )
            )
        super().__init__(placeholder="Elegí un préstamo", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        club = APP.club_de(interaction.user.id)
        if not club or club.casefold() != self.club.casefold():
            await interaction.response.send_message("⛔ Este menú pertenece a otro club.", ephemeral=True)
            return
        loan = loan_by_id(int(self.values[0]))
        if not loan:
            await interaction.response.send_message("⚠️ Préstamo no encontrado.", ephemeral=True)
            return
        embed = discord.Embed(title=f"🔄 Préstamo • {loan['player']}")
        embed.add_field(name="Dueño contractual", value=loan["owner_club"], inline=True)
        embed.add_field(name="Club cesionario", value=loan["borrower_club"], inline=True)
        embed.add_field(name="Estado", value=_loan_state(loan), inline=False)
        embed.add_field(name="Opción de compra", value=loan["purchase_option_value"] or "Sin opción", inline=True)
        view = None
        if loan["status"] == "OPTION_PENDING" and loan["borrower_club"].casefold() == club.casefold():
            view = LoanOptionDecisionView(loan["id"])
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


class LoansView(discord.ui.View):
    def __init__(self, club, rows):
        super().__init__(timeout=300)
        if rows:
            self.add_item(LoanSelect(club, rows))


def _patch_market_view():
    base = APP.MercadoView

    class LoanMarketView(base):
        def __init__(self):
            super().__init__()
            button = discord.ui.Button(
                label="Préstamos", emoji="🔄", style=discord.ButtonStyle.secondary,
                custom_id="mercado_prestamos", row=1,
            )
            button.callback = self._loans
            self.add_item(button)

        async def _loans(self, interaction: discord.Interaction):
            club = APP.club_de(interaction.user.id)
            if not club:
                await interaction.response.send_message("⚠️ Primero elegí tu club.", ephemeral=True)
                return
            rows = loans_for_club(club)
            embed = discord.Embed(
                title=f"🔄 Préstamos • {club}",
                description="Jugadores cedidos/recibidos y opciones de compra pendientes.",
            )
            if not rows:
                embed.description = "No tenés préstamos activos ni decisiones pendientes."
            else:
                embed.add_field(
                    name="Recibidos",
                    value=str(sum(r["borrower_club"].casefold() == club.casefold() for r in rows)),
                    inline=True,
                )
                embed.add_field(
                    name="Cedidos",
                    value=str(sum(r["owner_club"].casefold() == club.casefold() for r in rows)),
                    inline=True,
                )
                embed.add_field(
                    name="Opciones pendientes",
                    value=str(sum(r["status"] == "OPTION_PENDING" and r["borrower_club"].casefold() == club.casefold() for r in rows)),
                    inline=True,
                )
            await interaction.response.send_message(embed=embed, view=LoansView(club, rows), ephemeral=True)

    LoanMarketView.__name__ = "MercadoView"
    APP.MercadoView = LoanMarketView


async def _register_pending_views():
    if getattr(BOT, "_ajap_loan_option_views_registered", False):
        return
    reconcile_returns()
    sync_applied_loans()
    with APP.db() as conn:
        rows = conn.execute("SELECT id FROM loans WHERE status = 'OPTION_PENDING' ORDER BY id").fetchall()
    for row in rows:
        try:
            BOT.add_view(LoanOptionDecisionView(row["id"]))
        except ValueError as exc:
            print(f"WARNING AJAP: no se pudo registrar opción préstamo #{row['id']}: {exc}")
    BOT._ajap_loan_option_views_registered = True
    print(f"AJAP préstamos: {len(rows)} opción(es) persistentes registradas")


def apply_loan_lifecycle_patch(runtime, bot):
    global APP, BOT
    APP = runtime
    BOT = bot
    if getattr(runtime, "_ajap_loan_lifecycle_patch", False):
        return

    ensure_schema()
    reconcile_returns()
    created = sync_applied_loans()
    _patch_publish_protection()
    _patch_roster_embeds()
    _patch_season_modal()
    _patch_market_view()
    bot.add_listener(_register_pending_views, "on_ready")

    runtime.loan_by_id = loan_by_id
    runtime.active_loan_for_player = active_loan_for_player
    runtime.loans_for_club = loans_for_club
    runtime.process_loan_season_transition = process_season_transition
    runtime._ajap_loan_lifecycle_patch = True
    print(
        "AJAP ciclo de préstamos activo: propiedad contractual + vencimientos + opción de compra + devolución automática"
        + (f" • {created} préstamo(s) incorporados" if created else "")
    )
