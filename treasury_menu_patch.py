"""Tesorería visible para los DT dentro de MI CLUB.

La economía mostraba solamente saldo/valor de plantilla. Esta capa agrega un
menú de TESORERÍA que expone los movimientos que realmente modifican el saldo:
- cánones de préstamo;
- opciones de compra ejecutadas;
- clausulazos aprobados;
- ajustes manuales de administración.

Los movimientos se muestran como ingresos/egresos y pueden filtrarse. No se
crean movimientos ficticios a partir de acuerdos que todavía no hayan afectado
club_finances.
"""

from __future__ import annotations

from datetime import datetime

import discord

import my_club_menu_patch as my_club


APP = None


def _app():
    return APP or my_club.APP


def _table_exists(conn, name: str) -> bool:
    return bool(
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name = ? LIMIT 1",
            (name,),
        ).fetchone()
    )


def _fmt_money(value) -> str:
    try:
        return f"${int(value):,}".replace(",", ".")
    except (TypeError, ValueError):
        return str(value or "$0")


def _fmt_date(value) -> str:
    if not value:
        return "—"
    raw = str(value)
    try:
        return datetime.strptime(raw[:19], "%Y-%m-%d %H:%M:%S").strftime("%d/%m/%Y")
    except ValueError:
        return raw[:10]


def _season_name(conn, season_id):
    if not season_id or not _table_exists(conn, "seasons"):
        return None
    row = conn.execute("SELECT name FROM seasons WHERE id = ?", (int(season_id),)).fetchone()
    return row["name"] if row else None


def _current_balance(club: str) -> int:
    app = _app()
    if not app or not club:
        return 0
    with app.db() as conn:
        if not _table_exists(conn, "club_finances"):
            return 0
        row = conn.execute(
            "SELECT balance FROM club_finances WHERE club = ? COLLATE NOCASE",
            (club,),
        ).fetchone()
    return int(row["balance"] if row else 0)


def _ledger_rows(club: str):
    """Return normalized balance-changing entries for one club."""
    app = _app()
    if not app or not club:
        return []

    entries = []
    with app.db() as conn:
        # Canon de préstamo: esta tabla es la fuente oficial creada por loan_canon_patch.
        if _table_exists(conn, "treasury_transactions"):
            rows = conn.execute(
                """
                SELECT id, season_id, direction, category, amount, player,
                       counterparty, description, created_at
                FROM treasury_transactions
                WHERE club = ? COLLATE NOCASE
                ORDER BY created_at DESC, id DESC
                """,
                (club,),
            ).fetchall()
            for row in rows:
                entries.append(
                    {
                        "direction": row["direction"],
                        "category": row["category"] or "MOVIMIENTO",
                        "amount": int(row["amount"] or 0),
                        "player": row["player"],
                        "counterparty": row["counterparty"],
                        "description": row["description"],
                        "season_id": row["season_id"],
                        "created_at": row["created_at"],
                        "key": f"treasury:{row['id']}",
                    }
                )

        # Ajustes administrativos: sí cambian club_finances y ya están auditados.
        if _table_exists(conn, "finance_adjustments"):
            rows = conn.execute(
                """
                SELECT id, delta, admin_id, created_at
                FROM finance_adjustments
                WHERE club = ? COLLATE NOCASE
                ORDER BY created_at DESC, id DESC
                """,
                (club,),
            ).fetchall()
            for row in rows:
                delta = int(row["delta"] or 0)
                entries.append(
                    {
                        "direction": "INGRESO" if delta >= 0 else "EGRESO",
                        "category": "AJUSTE_ADMIN",
                        "amount": abs(delta),
                        "player": None,
                        "counterparty": "Administración",
                        "description": "Ajuste de presupuesto realizado por Staff",
                        "season_id": None,
                        "created_at": row["created_at"],
                        "key": f"adjustment:{row['id']}",
                    }
                )

        # Opción de compra: el pago se ejecuta directamente en loan_lifecycle_patch.
        if _table_exists(conn, "loan_option_payments"):
            rows = conn.execute(
                """
                SELECT p.*, l.player, l.purchase_transfer_id
                FROM loan_option_payments p
                LEFT JOIN loans l ON l.id = p.loan_id
                WHERE p.buyer_club = ? COLLATE NOCASE OR p.seller_club = ? COLLATE NOCASE
                ORDER BY p.created_at DESC, p.id DESC
                """,
                (club, club),
            ).fetchall()
            for row in rows:
                buying = str(row["buyer_club"]).casefold() == club.casefold()
                season_id = None
                if row["purchase_transfer_id"] and _table_exists(conn, "transfers"):
                    transfer = conn.execute(
                        "SELECT season_id FROM transfers WHERE id = ?",
                        (int(row["purchase_transfer_id"]),),
                    ).fetchone()
                    season_id = transfer["season_id"] if transfer else None
                entries.append(
                    {
                        "direction": "EGRESO" if buying else "INGRESO",
                        "category": "OPCIÓN_COMPRA",
                        "amount": int(row["amount"] or 0),
                        "player": row["player"],
                        "counterparty": row["seller_club"] if buying else row["buyer_club"],
                        "description": "Opción de compra ejecutada al finalizar el préstamo",
                        "season_id": season_id,
                        "created_at": row["created_at"],
                        "key": f"purchase:{row['id']}",
                    }
                )

        # Clausulazo aprobado: el comprador ya pagó y el vendedor ya cobró.
        if _table_exists(conn, "clause_requests"):
            rows = conn.execute(
                """
                SELECT id, season_id, player, seller_club, buyer_club, amount,
                       decided_at, requested_at
                FROM clause_requests
                WHERE status = 'APROBADO'
                  AND (buyer_club = ? COLLATE NOCASE OR seller_club = ? COLLATE NOCASE)
                ORDER BY COALESCE(decided_at, requested_at) DESC, id DESC
                """,
                (club, club),
            ).fetchall()
            for row in rows:
                buying = str(row["buyer_club"]).casefold() == club.casefold()
                entries.append(
                    {
                        "direction": "EGRESO" if buying else "INGRESO",
                        "category": "CLAUSULAZO",
                        "amount": int(row["amount"] or 0),
                        "player": row["player"],
                        "counterparty": row["seller_club"] if buying else row["buyer_club"],
                        "description": "Cláusula de rescisión aprobada por Staff",
                        "season_id": row["season_id"],
                        "created_at": row["decided_at"] or row["requested_at"],
                        "key": f"clause:{row['id']}",
                    }
                )

        # Evitar duplicar categorías que ya estén en treasury_transactions si en
        # el futuro otros módulos empiezan a escribirlas también.
        unique = {}
        for item in entries:
            unique[item["key"]] = item
        entries = list(unique.values())

        for item in entries:
            item["season_name"] = _season_name(conn, item.get("season_id"))

    entries.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
    return entries


def _pending_canon(club: str):
    app = _app()
    if not app or not club:
        return 0, 0
    with app.db() as conn:
        if not (_table_exists(conn, "loan_canon_dues") and _table_exists(conn, "loans")):
            return 0, 0
        row = conn.execute(
            """
            SELECT COUNT(*) AS qty, COALESCE(SUM(d.amount), 0) AS total
            FROM loan_canon_dues d
            JOIN loans l ON l.id = d.loan_id
            WHERE d.status = 'PENDING'
              AND l.borrower_club = ? COLLATE NOCASE
            """,
            (club,),
        ).fetchone()
    return int(row["qty"] or 0), int(row["total"] or 0)


def _category_label(category: str) -> str:
    labels = {
        "CANON_PRÉSTAMO": "Canon de préstamo",
        "OPCIÓN_COMPRA": "Opción de compra",
        "CLAUSULAZO": "Clausulazo",
        "AJUSTE_ADMIN": "Ajuste administrativo",
    }
    return labels.get(category, str(category or "Movimiento").replace("_", " ").title())


def treasury_embed(user_id: int, direction: str | None = None):
    app = _app()
    club = app.club_de(user_id) if app else None
    if not club:
        return my_club.my_club_embed(user_id)

    all_entries = _ledger_rows(club)
    selected = [
        item for item in all_entries
        if direction is None or item["direction"] == direction
    ]
    ingresos = sum(item["amount"] for item in all_entries if item["direction"] == "INGRESO")
    egresos = sum(item["amount"] for item in all_entries if item["direction"] == "EGRESO")
    pending_qty, pending_total = _pending_canon(club)

    filter_name = "TODOS" if direction is None else direction + "S"
    embed = discord.Embed(
        title=f"💼 TESORERÍA • {club.upper()}",
        description=f"Movimientos reales de caja • Vista: **{filter_name}**",
    )
    embed.add_field(name="💰 Saldo actual", value=_fmt_money(_current_balance(club)), inline=True)
    embed.add_field(name="📈 Ingresos registrados", value=_fmt_money(ingresos), inline=True)
    embed.add_field(name="📉 Egresos registrados", value=_fmt_money(egresos), inline=True)
    embed.add_field(
        name="📊 Balance de movimientos",
        value=("+" if ingresos - egresos >= 0 else "−") + _fmt_money(abs(ingresos - egresos)),
        inline=True,
    )
    if pending_qty:
        embed.add_field(
            name="⚠️ Canon pendiente",
            value=f"{pending_qty} pago(s) • **{_fmt_money(pending_total)}**",
            inline=True,
        )

    if not selected:
        embed.add_field(
            name="📜 Movimientos",
            value="Todavía no hay movimientos registrados en esta categoría.",
            inline=False,
        )
    else:
        lines = []
        for item in selected[:12]:
            sign = "+" if item["direction"] == "INGRESO" else "−"
            icon = "📈" if item["direction"] == "INGRESO" else "📉"
            subject = f" • **{item['player']}**" if item.get("player") else ""
            counterparty = f" • {item['counterparty']}" if item.get("counterparty") else ""
            season = f" • {item['season_name']}" if item.get("season_name") else ""
            lines.append(
                f"{icon} **{sign}{_fmt_money(item['amount'])}** • {_category_label(item['category'])}"
                f"{subject}{counterparty}{season}\n"
                f"↳ {_fmt_date(item.get('created_at'))}"
            )
        embed.add_field(name="📜 Últimos movimientos", value="\n\n".join(lines), inline=False)
        if len(selected) > 12:
            embed.set_footer(text=f"Mostrando 12 de {len(selected)} movimiento(s) • AJAP Transfer Market")
        else:
            embed.set_footer(text="AJAP Transfer Market • Tesorería del club")

    if not embed.footer.text:
        embed.set_footer(text="AJAP Transfer Market • Tesorería del club")
    return embed


class TreasuryFilterButton(discord.ui.Button):
    def __init__(self, *, label, emoji, direction, roster_callback, row=0):
        super().__init__(
            label=label,
            emoji=emoji,
            style=discord.ButtonStyle.secondary,
            row=row,
        )
        self.direction = direction
        self.roster_callback = roster_callback

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.edit_message(
            content=None,
            embeds=[treasury_embed(interaction.user.id, self.direction)],
            view=TreasuryView(self.roster_callback),
        )


class TreasuryBackButton(discord.ui.Button):
    def __init__(self, roster_callback, row=1):
        super().__init__(
            label="Volver a MI CLUB",
            emoji="⬅️",
            style=discord.ButtonStyle.secondary,
            row=row,
        )
        self.roster_callback = roster_callback

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.edit_message(
            content=None,
            embeds=[my_club.my_club_embed(interaction.user.id)],
            view=my_club.MyClubSectionView(self.roster_callback),
        )


class TreasuryView(discord.ui.View):
    def __init__(self, roster_callback):
        super().__init__(timeout=300)
        self.add_item(TreasuryFilterButton(label="INGRESOS", emoji="📈", direction="INGRESO", roster_callback=roster_callback, row=0))
        self.add_item(TreasuryFilterButton(label="EGRESOS", emoji="📉", direction="EGRESO", roster_callback=roster_callback, row=0))
        self.add_item(TreasuryFilterButton(label="TODOS", emoji="📜", direction=None, roster_callback=roster_callback, row=0))
        self.add_item(TreasuryBackButton(roster_callback, row=1))


class TreasuryButton(discord.ui.Button):
    def __init__(self, roster_callback, row=1):
        super().__init__(
            label="TESORERÍA",
            emoji="💼",
            style=discord.ButtonStyle.secondary,
            row=row,
            custom_id="ajap_my_club_tesoreria",
        )
        self.roster_callback = roster_callback

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.edit_message(
            content=None,
            embeds=[treasury_embed(interaction.user.id)],
            view=TreasuryView(self.roster_callback),
        )


def _install_menu_view():
    if getattr(my_club, "_ajap_treasury_menu_patch", False):
        return False

    class TreasuryMyClubSectionView(discord.ui.View):
        def __init__(self, roster_callback):
            super().__init__(timeout=300)
            # Mantener dos accesos principales arriba y separar las herramientas
            # financieras/administrativas para que se lea bien también en móvil.
            self.add_item(
                my_club.MyClubSectionButton(
                    label="PLANTILLA", emoji="👥", action="plantilla",
                    roster_callback=roster_callback, row=0,
                )
            )
            self.add_item(
                my_club.MyClubSectionButton(
                    label="ECONOMÍA", emoji="💰", action="economia",
                    roster_callback=roster_callback, row=0,
                )
            )
            self.add_item(TreasuryButton(roster_callback, row=1))
            self.add_item(
                my_club.MyClubSectionButton(
                    label="VALOR DEL CLUB", emoji="📊", action="valor",
                    roster_callback=roster_callback, row=1,
                )
            )
            self.add_item(
                my_club.MyClubSectionButton(
                    label="INFORMACIÓN", emoji="ℹ️", action="info",
                    roster_callback=roster_callback, row=1,
                )
            )
            self.add_item(my_club.manager.BackMainButton(row=2))

    TreasuryMyClubSectionView.__name__ = "MyClubSectionView"
    my_club.MyClubSectionView = TreasuryMyClubSectionView
    my_club._ajap_treasury_menu_patch = True
    return True


def apply_treasury_menu_patch(runtime):
    global APP
    APP = runtime
    _install_menu_view()
    runtime.treasury_embed = treasury_embed
    runtime._ajap_treasury_menu_patch = True
    print("AJAP TESORERÍA activa: saldo + ingresos/egresos + filtros dentro de MI CLUB")


# La clase visual puede instalarse al importar porque sus consultas recién se
# ejecutan cuando el usuario pulsa el botón. APP se enlaza después desde bot.py.
_install_menu_view()
