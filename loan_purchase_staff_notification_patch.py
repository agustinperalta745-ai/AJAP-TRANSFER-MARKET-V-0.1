"""Notify AJAP Staff when a borrowing club executes a loan purchase option.

The loan lifecycle already settles balances and contractual ownership. This
patch only adds an operational notification in the configured /canal_movimientos
Staff channel. It intentionally does not create a "pending PES" task because the
player is already in the borrowing club's roster from the loan.
"""

import discord

import loan_lifecycle_patch as loans


_ORIGINAL_INIT = loans.LoanOptionDecisionView.__init__


def _purchase_snapshot(loan_id: int):
    if loans.APP is None:
        return None, None
    with loans.APP.db() as conn:
        loan = conn.execute(
            "SELECT * FROM loans WHERE id = ? LIMIT 1",
            (int(loan_id),),
        ).fetchone()
        payment = conn.execute(
            """
            SELECT * FROM loan_option_payments
            WHERE loan_id = ?
            ORDER BY id DESC LIMIT 1
            """,
            (int(loan_id),),
        ).fetchone()
    return loan, payment


async def _notify_staff_purchase(interaction: discord.Interaction, loan_id: int):
    if interaction.guild is None:
        return False

    # Imported lazily to avoid changing startup ordering between the loan and
    # Staff/PES patches. At interaction time both modules are already applied.
    import market_channel_report_patch as market_reports

    if market_reports.APP is None:
        return False

    channel = await market_reports.resolve_channel(interaction)
    if channel is None:
        return False

    loan, payment = _purchase_snapshot(loan_id)
    if not loan or (loan["status"] or "").upper() != "PURCHASED":
        return False

    amount = payment["amount"] if payment else loans.APP.price_number(loan["purchase_option_value"] or "")
    amount_text = loans.APP.money(str(int(amount))) if amount is not None else str(loan["purchase_option_value"] or "—")
    transfer_id = loan["purchase_transfer_id"] or "—"

    embed = discord.Embed(
        title="🛒 OPCIÓN DE COMPRA EJECUTADA",
        description=(
            f"**{loan['borrower_club']}** compró definitivamente a "
            f"**{loan['player']}** después de su préstamo."
        ),
        color=discord.Color.green(),
    )
    embed.add_field(name="⚽ Jugador", value=f"**{loan['player']}**", inline=False)
    embed.add_field(name="⬅️ Club propietario", value=loan["owner_club"], inline=True)
    embed.add_field(name="➡️ Nuevo propietario", value=loan["borrower_club"], inline=True)
    embed.add_field(name="💰 Importe", value=amount_text, inline=True)
    embed.add_field(name="📄 Préstamo", value=f"#{loan['id']}", inline=True)
    embed.add_field(name="🧾 Operación", value=f"#{transfer_id}", inline=True)
    embed.add_field(
        name="👤 Ejecutada por",
        value=f"{interaction.user.mention} • `{interaction.user.id}`",
        inline=False,
    )
    embed.add_field(
        name="🎮 Estado en PES",
        value=(
            f"**No requiere mover al jugador.** Ya estaba en **{loan['borrower_club']}** "
            "por la cesión; la compra cambia su propiedad de forma definitiva."
        ),
        inline=False,
    )
    embed.set_footer(text="AJAP Transfer Market • aviso automático a Staff")

    try:
        await channel.send(
            content="🔔 **Aviso automático a administración**",
            embed=embed,
            allowed_mentions=discord.AllowedMentions.none(),
        )
        return True
    except (discord.Forbidden, discord.HTTPException) as exc:
        print(f"WARNING AJAP: aviso Staff compra préstamo #{loan_id} falló: {exc}")
        return False


def _patched_init(self, *args, **kwargs):
    _ORIGINAL_INIT(self, *args, **kwargs)
    loan_id = int(getattr(self, "loan_id", 0) or 0)
    if not loan_id:
        return

    for child in self.children:
        if not isinstance(child, discord.ui.Button) or child.label != "Ejecutar compra":
            continue

        original_callback = child.callback

        async def buy_and_notify(interaction, _original=original_callback, _loan_id=loan_id):
            before = loans.loan_by_id(_loan_id)
            before_status = (before["status"] or "").upper() if before else None
            try:
                await _original(interaction)
            finally:
                fresh = loans.loan_by_id(_loan_id)
                if (
                    before_status != "PURCHASED"
                    and fresh
                    and (fresh["status"] or "").upper() == "PURCHASED"
                ):
                    try:
                        await _notify_staff_purchase(interaction, _loan_id)
                    except Exception as exc:
                        # The purchase must stay valid even if Discord cannot
                        # deliver the auxiliary Staff notification.
                        print(f"WARNING AJAP: notificación Staff préstamo #{_loan_id} falló: {exc}")

        child.callback = buy_and_notify
        break


if not getattr(loans.LoanOptionDecisionView, "_ajap_staff_purchase_notification", False):
    loans.LoanOptionDecisionView.__init__ = _patched_init
    loans.LoanOptionDecisionView._ajap_staff_purchase_notification = True
    print("AJAP préstamos: compras por opción notifican automáticamente al canal Staff")
