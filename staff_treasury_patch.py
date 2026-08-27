"""Tesorería de auditoría para Staff en AJAP Transfer Market.

Agrega a Administración -> Economía una vista por club con saldo, ingresos,
egresos y movimientos reales de caja. Reutiliza la misma fuente de datos que
MI CLUB -> TESORERÍA para que Staff y DT vean exactamente la misma contabilidad.
"""

from __future__ import annotations

import discord

import staff_admin_organized_patch as staff_admin
import treasury_menu_patch as treasury


def _app():
    return staff_admin.APP or treasury._app()


def _is_admin(interaction: discord.Interaction) -> bool:
    app = _app()
    return bool(app and app.es_admin(interaction))


def _clubs():
    app = _app()
    if not app:
        return []

    names = set()
    with app.db() as conn:
        if treasury._table_exists(conn, "roster_players"):
            rows = conn.execute(
                "SELECT DISTINCT club FROM roster_players "
                "WHERE club IS NOT NULL AND TRIM(club) <> '' "
                "ORDER BY club COLLATE NOCASE"
            ).fetchall()
            names.update(str(row["club"]).strip() for row in rows if row["club"])

        if treasury._table_exists(conn, "club_finances"):
            rows = conn.execute(
                "SELECT club FROM club_finances "
                "WHERE club IS NOT NULL AND TRIM(club) <> '' "
                "ORDER BY club COLLATE NOCASE"
            ).fetchall()
            names.update(str(row["club"]).strip() for row in rows if row["club"])

    return sorted(names, key=str.casefold)


def _direction_label(direction):
    if direction == "INGRESO":
        return "INGRESOS"
    if direction == "EGRESO":
        return "EGRESOS"
    return "TODOS"


def _movement_lines(entries):
    lines = []
    for item in entries:
        incoming = item.get("direction") == "INGRESO"
        icon = "📈" if incoming else "📉"
        sign = "+" if incoming else "−"
        category = treasury._category_label(item.get("category"))
        player = f" • **{item['player']}**" if item.get("player") else ""
        counterparty = f" • {item['counterparty']}" if item.get("counterparty") else ""
        season = f" • {item['season_name']}" if item.get("season_name") else ""
        date = treasury._fmt_date(item.get("created_at"))
        description = (item.get("description") or "").strip()

        line = (
            f"{icon} **{sign}{treasury._fmt_money(item.get('amount', 0))}** "
            f"• {category}{player}{counterparty}{season}\n"
            f"↳ {date}"
        )
        if description:
            line += f" • {description}"
        lines.append(line)
    return lines


def _add_movement_fields(embed: discord.Embed, entries):
    if not entries:
        embed.add_field(
            name="📜 Movimientos",
            value="Todavía no hay movimientos registrados en esta categoría.",
            inline=False,
        )
        return

    # Discord limita cada field a 1024 caracteres. Armamos bloques compactos
    # sin cortar una operación por la mitad.
    chunks = []
    current = []
    current_size = 0
    for line in _movement_lines(entries[:20]):
        extra = len(line) + (2 if current else 0)
        if current and current_size + extra > 950:
            chunks.append(current)
            current = []
            current_size = 0
        current.append(line)
        current_size += extra
    if current:
        chunks.append(current)

    for index, chunk in enumerate(chunks[:4], start=1):
        embed.add_field(
            name="📜 Últimos movimientos" if index == 1 else f"📜 Movimientos • {index}",
            value="\n\n".join(chunk),
            inline=False,
        )


def staff_treasury_embed(club: str, direction=None):
    all_entries = treasury._ledger_rows(club)
    selected = [
        item
        for item in all_entries
        if direction is None or item.get("direction") == direction
    ]

    ingresos = sum(
        int(item.get("amount") or 0)
        for item in all_entries
        if item.get("direction") == "INGRESO"
    )
    egresos = sum(
        int(item.get("amount") or 0)
        for item in all_entries
        if item.get("direction") == "EGRESO"
    )
    pending_qty, pending_total = treasury._pending_canon(club)

    embed = discord.Embed(
        title=f"💼 TESORERÍA STAFF • {club.upper()}",
        description=(
            "Auditoría económica del club • "
            f"Vista: **{_direction_label(direction)}**"
        ),
    )
    embed.add_field(
        name="💰 Saldo actual",
        value=treasury._fmt_money(treasury._current_balance(club)),
        inline=True,
    )
    embed.add_field(
        name="📈 Ingresos registrados",
        value=treasury._fmt_money(ingresos),
        inline=True,
    )
    embed.add_field(
        name="📉 Egresos registrados",
        value=treasury._fmt_money(egresos),
        inline=True,
    )

    net = ingresos - egresos
    embed.add_field(
        name="📊 Balance de movimientos",
        value=("+" if net >= 0 else "−") + treasury._fmt_money(abs(net)),
        inline=True,
    )
    if pending_qty:
        embed.add_field(
            name="⚠️ Canon pendiente",
            value=f"{pending_qty} pago(s) • **{treasury._fmt_money(pending_total)}**",
            inline=True,
        )

    _add_movement_fields(embed, selected)

    shown = min(len(selected), 20)
    if len(selected) > shown:
        footer = f"Mostrando {shown} de {len(selected)} movimiento(s)"
    else:
        footer = f"{len(selected)} movimiento(s) en esta vista"
    embed.set_footer(text=f"{footer} • Auditoría Staff")
    return embed


class StaffTreasuryClubSelect(discord.ui.Select):
    def __init__(self, clubs):
        options = [
            discord.SelectOption(
                label=club[:100],
                description=f"Saldo: {treasury._fmt_money(treasury._current_balance(club))}"[:100],
                value=club,
                emoji="🏟️",
            )
            for club in clubs[:25]
        ]
        super().__init__(
            placeholder="Elegí el equipo a revisar",
            min_values=1,
            max_values=1,
            options=options,
            custom_id="ajap_staff_treasury_club",
        )

    async def callback(self, interaction: discord.Interaction):
        if not _is_admin(interaction):
            await interaction.response.send_message("⛔ Solo administradores.", ephemeral=True)
            return
        club = self.values[0]
        await interaction.response.edit_message(
            content=None,
            embeds=[staff_treasury_embed(club)],
            view=StaffTreasuryView(club),
        )


class StaffTreasuryPickerView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=300)
        clubs = _clubs()
        if clubs:
            self.add_item(StaffTreasuryClubSelect(clubs))
        self.add_item(StaffEconomyBackButton(row=1))


class StaffTreasuryFilterButton(discord.ui.Button):
    def __init__(self, *, club, label, emoji, direction, row=0):
        super().__init__(
            label=label,
            emoji=emoji,
            style=discord.ButtonStyle.secondary,
            row=row,
        )
        self.club = club
        self.direction = direction

    async def callback(self, interaction: discord.Interaction):
        if not _is_admin(interaction):
            await interaction.response.send_message("⛔ Solo administradores.", ephemeral=True)
            return
        await interaction.response.edit_message(
            content=None,
            embeds=[staff_treasury_embed(self.club, self.direction)],
            view=StaffTreasuryView(self.club),
        )


class StaffTreasuryChangeClubButton(discord.ui.Button):
    def __init__(self, row=1):
        super().__init__(
            label="CAMBIAR EQUIPO",
            emoji="🏟️",
            style=discord.ButtonStyle.secondary,
            row=row,
        )

    async def callback(self, interaction: discord.Interaction):
        if not _is_admin(interaction):
            await interaction.response.send_message("⛔ Solo administradores.", ephemeral=True)
            return
        await interaction.response.edit_message(
            content=None,
            embeds=[
                discord.Embed(
                    title="💼 TESORERÍA STAFF",
                    description="Elegí el equipo cuya tesorería querés auditar.",
                )
            ],
            view=StaffTreasuryPickerView(),
        )


class StaffEconomyBackButton(discord.ui.Button):
    def __init__(self, row=1):
        super().__init__(
            label="VOLVER A ECONOMÍA",
            emoji="⬅️",
            style=discord.ButtonStyle.secondary,
            row=row,
        )

    async def callback(self, interaction: discord.Interaction):
        if not _is_admin(interaction):
            await interaction.response.send_message("⛔ Solo administradores.", ephemeral=True)
            return
        await interaction.response.edit_message(
            content=None,
            embeds=[
                staff_admin.section_embed(
                    "💰 ECONOMÍA",
                    "Administración de presupuestos y auditoría de movimientos.",
                    [
                        "➕ Dar dinero",
                        "➖ Quitar dinero",
                        "📊 Ver presupuestos",
                        "💼 Tesorería por equipo",
                    ],
                )
            ],
            view=staff_admin.EconomyView(),
        )


class StaffTreasuryView(discord.ui.View):
    def __init__(self, club: str):
        super().__init__(timeout=300)
        self.add_item(
            StaffTreasuryFilterButton(
                club=club,
                label="INGRESOS",
                emoji="📈",
                direction="INGRESO",
                row=0,
            )
        )
        self.add_item(
            StaffTreasuryFilterButton(
                club=club,
                label="EGRESOS",
                emoji="📉",
                direction="EGRESO",
                row=0,
            )
        )
        self.add_item(
            StaffTreasuryFilterButton(
                club=club,
                label="TODOS",
                emoji="📜",
                direction=None,
                row=0,
            )
        )
        self.add_item(StaffTreasuryChangeClubButton(row=1))
        self.add_item(StaffEconomyBackButton(row=1))


class StaffTreasuryButton(discord.ui.Button):
    def __init__(self, row=1):
        super().__init__(
            label="TESORERÍA",
            emoji="💼",
            style=discord.ButtonStyle.primary,
            row=row,
            custom_id="ajap_admin_treasury",
        )

    async def callback(self, interaction: discord.Interaction):
        if not _is_admin(interaction):
            await interaction.response.send_message("⛔ Solo administradores.", ephemeral=True)
            return
        clubs = _clubs()
        embed = discord.Embed(
            title="💼 TESORERÍA STAFF",
            description="Elegí el equipo cuya tesorería querés auditar.",
        )
        if not clubs:
            embed.description = "Todavía no hay equipos con datos económicos para revisar."
        await interaction.response.edit_message(
            content=None,
            embeds=[embed],
            view=StaffTreasuryPickerView(),
        )


def install_staff_treasury():
    if getattr(staff_admin, "_ajap_staff_treasury_patch", False):
        return False

    base_economy_view = staff_admin.EconomyView

    class TreasuryEconomyView(base_economy_view):
        def __init__(self):
            super().__init__()
            self.add_item(StaffTreasuryButton(row=1))

    TreasuryEconomyView.__name__ = "EconomyView"
    staff_admin.EconomyView = TreasuryEconomyView

    original_section_embed = staff_admin.section_embed

    def section_embed_with_treasury(title, description, tools):
        tools = list(tools)
        if "ECONOMÍA" in str(title).upper() and not any(
            "tesorer" in str(tool).casefold() for tool in tools
        ):
            tools.append("💼 Tesorería por equipo")
            description = "Administración de presupuestos y auditoría de movimientos."
        return original_section_embed(title, description, tools)

    staff_admin.section_embed = section_embed_with_treasury
    staff_admin._ajap_staff_treasury_patch = True
    print("AJAP Staff Tesorería activa: selector de club + auditoría de movimientos")
    return True


install_staff_treasury()
