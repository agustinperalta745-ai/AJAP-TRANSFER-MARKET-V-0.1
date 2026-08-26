"""Panel de administración ordenado para AJAP Transfer Market.

Este parche NO modifica el dashboard informativo de Staff ni el menú principal.
Solo reemplaza la pared de botones del panel Administración por cuatro secciones:
Mercado, Planteles, Economía y Gestión.

Las herramientas existentes conservan sus callbacks/validaciones. Además mantiene
Deshacer pase, vista de presupuestos y exportación como utilidades Staff.
"""

from __future__ import annotations

import csv
import io

import discord

import guild_isolation_patch as guild_isolation
import manager_menu_patch as manager


APP = None
BOT = None
ORIGINAL_ADMIN_VIEW = None


def _norm(value):
    return str(value or "").strip().casefold()


def _table_exists(conn, table_name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ? LIMIT 1",
        (table_name,),
    ).fetchone()
    return bool(row)


def _fmt_money(value):
    try:
        return f"${int(value):,}".replace(",", ".")
    except (TypeError, ValueError):
        return "$0"


def _source_buttons():
    """Obtiene los botones del AdminView final anterior a este parche."""
    source = ORIGINAL_ADMIN_VIEW()
    return [
        item for item in source.children
        if isinstance(item, discord.ui.Button)
        and not _norm(getattr(item, "label", "")).startswith("volver")
    ]


def _find_button(buttons, *needles):
    for item in buttons:
        label = _norm(getattr(item, "label", ""))
        if all(_norm(needle) in label for needle in needles):
            return item
    return None


class ProxyAdminButton(discord.ui.Button):
    """Botón visual nuevo que reutiliza exactamente el callback ya existente."""

    def __init__(self, source_button, *, label, emoji, style, row, custom_id):
        super().__init__(
            label=label,
            emoji=emoji,
            style=style,
            disabled=bool(source_button.disabled),
            row=row,
            custom_id=custom_id,
        )
        self._target = source_button.callback

    async def callback(self, interaction: discord.Interaction):
        if not APP.es_admin(interaction):
            await interaction.response.send_message("⛔ Solo administradores.", ephemeral=True)
            return
        await self._target(interaction)


def admin_home_embed():
    season = APP.temporada_activa()
    embed = discord.Embed(
        title="⚙️ ADMINISTRACIÓN",
        description="Elegí la sección que necesitás. Las herramientas quedan agrupadas por función.",
    )
    embed.add_field(
        name="🔁 Mercado",
        value="🟢 ABIERTO" if APP.mercado_abierto() else "🔒 CERRADO",
        inline=True,
    )
    embed.add_field(
        name="🗓️ Temporada",
        value=season["name"] if season else "Sin temporada",
        inline=True,
    )
    embed.add_field(
        name="🧭 Secciones",
        value="🔁 Mercado\n👥 Planteles\n💰 Economía\n⚙️ Gestión",
        inline=False,
    )
    embed.set_footer(text="AJAP Transfer Market • Administración Staff")
    return embed


def section_embed(title, description, tools):
    embed = discord.Embed(title=title, description=description)
    embed.add_field(name="Herramientas", value="\n".join(tools), inline=False)
    embed.set_footer(text="⬅️ VOLVER regresa a Administración")
    return embed


class BackAdminButton(discord.ui.Button):
    def __init__(self, row=3):
        super().__init__(
            label="VOLVER",
            emoji="⬅️",
            style=discord.ButtonStyle.secondary,
            row=row,
            custom_id=f"ajap_admin_back_home_{row}",
        )

    async def callback(self, interaction: discord.Interaction):
        if not APP.es_admin(interaction):
            await interaction.response.send_message("⛔ Solo administradores.", ephemeral=True)
            return
        await interaction.response.edit_message(
            content=None,
            embeds=[admin_home_embed()],
            view=OrganizedAdminHomeView(),
        )


# ---------------------------------------------------------------------------
# DESHACER PASE
# ---------------------------------------------------------------------------
def _ensure_undo_schema():
    with APP.db() as conn:
        APP.add_column_if_missing(conn, "transfers", "reverted_by", "INTEGER")
        APP.add_column_if_missing(conn, "transfers", "reverted_at", "DATETIME")
        APP.add_column_if_missing(conn, "transfers", "revert_reason", "TEXT")


def _deal_rows(transfer_id: int, conn=None):
    owns = conn is None
    conn = conn or APP.db()
    try:
        row = conn.execute("SELECT * FROM transfers WHERE id = ?", (int(transfer_id),)).fetchone()
        if not row:
            return []
        group = row["deal_group"] if "deal_group" in row.keys() else None
        if group:
            return conn.execute(
                "SELECT * FROM transfers WHERE deal_group = ? ORDER BY id ASC",
                (group,),
            ).fetchall()
        return [row]
    finally:
        if owns:
            conn.close()


def _recent_reversible(limit=25):
    _ensure_undo_schema()
    with APP.db() as conn:
        rows = conn.execute(
            """
            SELECT * FROM transfers
            WHERE status = 'APLICADA'
              AND UPPER(COALESCE(operation_type,'')) NOT IN ('OPCIÓN DE COMPRA','DEVOLUCIÓN PRÉSTAMO')
            ORDER BY id DESC
            LIMIT 100
            """
        ).fetchall()
    result = []
    seen = set()
    for row in rows:
        group = row["deal_group"] if "deal_group" in row.keys() else None
        key = f"G:{group}" if group else f"O:{row['id']}"
        if key in seen:
            continue
        seen.add(key)
        result.append(row)
        if len(result) >= limit:
            break
    return result


def _undo_preview(transfer_id: int):
    rows = _deal_rows(transfer_id)
    embed = discord.Embed(
        title="↩️ DESHACER PASE",
        description="Confirmá el movimiento. Si hubo un pase posterior, el bot bloquea la reversión para no romper la base.",
        color=discord.Color.orange(),
    )
    if not rows:
        embed.description = "La operación ya no existe."
        return embed
    for row in rows:
        embed.add_field(
            name=f"#{row['id']} • {row['player']}",
            value=f"{row['seller']} ➜ **{row['buyer']}**\n{row['operation_type']} • {row['amount']}",
            inline=False,
        )
    embed.set_footer(text="La reversión queda registrada como REVERTIDA_ADMIN")
    return embed


def _undo_transfer(transfer_id: int, admin_id: int):
    _ensure_undo_schema()
    conn = APP.db()
    try:
        conn.execute("BEGIN IMMEDIATE")
        rows = _deal_rows(transfer_id, conn)
        if not rows:
            conn.rollback()
            return False, "Operación no encontrada."

        blocked = {"OPCIÓN DE COMPRA", "DEVOLUCIÓN PRÉSTAMO"}
        if any((r["operation_type"] or "").upper() in blocked for r in rows):
            conn.rollback()
            return False, "Ese movimiento de préstamo necesita una corrección específica."
        if any((r["status"] or "").upper() != "APLICADA" for r in rows):
            conn.rollback()
            return False, "La operación ya no está completamente APLICADA o ya fue revertida."

        players = []
        for row in rows:
            if row["player_id"]:
                player = conn.execute(
                    "SELECT * FROM roster_players WHERE id = ?", (int(row["player_id"]),)
                ).fetchone()
            else:
                player = conn.execute(
                    "SELECT * FROM roster_players WHERE name = ? COLLATE NOCASE", (row["player"],)
                ).fetchone()
            if not player:
                conn.rollback()
                return False, f"No encontré a {row['player']} en el plantel oficial."
            if (player["club"] or "").casefold() != (row["buyer"] or "").casefold():
                conn.rollback()
                return False, (
                    f"{row['player']} ya no está en {row['buyer']} (figura en {player['club']}). "
                    "No se modificó nada."
                )
            players.append((row, player))

        clause_refunds = []
        for row, _ in players:
            if (row["operation_type"] or "").upper() != "CLAUSULAZO":
                continue
            amount = APP.price_number(row["amount"] or "")
            if not amount:
                conn.rollback()
                return False, f"No pude interpretar el monto del clausulazo #{row['id']}."
            for club in (row["seller"], row["buyer"]):
                conn.execute("INSERT OR IGNORE INTO club_finances (club, balance) VALUES (?, 0)", (club,))
            seller = conn.execute(
                "SELECT balance FROM club_finances WHERE club = ? COLLATE NOCASE", (row["seller"],)
            ).fetchone()
            seller_balance = int(seller["balance"] if seller else 0)
            if seller_balance < int(amount):
                conn.rollback()
                return False, (
                    f"{row['seller']} debe devolver {_fmt_money(amount)} pero tiene {_fmt_money(seller_balance)}. "
                    "Ajustá el saldo antes de deshacer el clausulazo."
                )
            clause_refunds.append((row, int(amount)))

        for row, player in players:
            conn.execute(
                "UPDATE roster_players SET club = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (row["seller"], int(player["id"])),
            )
            conn.execute(
                """
                UPDATE transfers
                SET status = 'REVERTIDA_ADMIN', reverted_by = ?, reverted_at = CURRENT_TIMESTAMP,
                    revert_reason = 'Deshecho desde Administración'
                WHERE id = ?
                """,
                (int(admin_id), int(row["id"])),
            )
            conn.execute(
                """
                INSERT INTO player_history
                (player_id, player, from_club, to_club, transfer_id, season_id, event_type)
                VALUES (?, ?, ?, ?, ?, ?, 'REVERSIÓN ADMIN')
                """,
                (int(player["id"]), row["player"], row["buyer"], row["seller"], int(row["id"]), row["season_id"]),
            )
            if (row["operation_type"] or "").upper() == "PRÉSTAMO" and _table_exists(conn, "loans"):
                conn.execute(
                    """
                    UPDATE loans SET status = 'CANCELLED_ADMIN', resolved_at = CURRENT_TIMESTAMP
                    WHERE source_transfer_id = ?
                      AND status IN ('ACTIVE','OPTION_PENDING','RETURN_PENDING','REVIEW_REQUIRED')
                    """,
                    (int(row["id"]),),
                )

        for row, amount in clause_refunds:
            conn.execute(
                "UPDATE club_finances SET balance = balance - ?, updated_at = CURRENT_TIMESTAMP WHERE club = ? COLLATE NOCASE",
                (amount, row["seller"]),
            )
            conn.execute(
                "UPDATE club_finances SET balance = balance + ?, updated_at = CURRENT_TIMESTAMP WHERE club = ? COLLATE NOCASE",
                (amount, row["buyer"]),
            )
            if _table_exists(conn, "clause_requests"):
                conn.execute(
                    """
                    UPDATE clause_requests
                    SET status = 'REVERTIDO_ADMIN', notes = COALESCE(notes || ' | ', '') || 'Revertido por Staff'
                    WHERE transfer_id = ?
                    """,
                    (int(row["id"]),),
                )

        conn.commit()
        return True, rows
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


class UndoSelect(discord.ui.Select):
    def __init__(self, rows):
        super().__init__(
            placeholder="Elegí el pase que querés deshacer",
            min_values=1,
            max_values=1,
            options=[
                discord.SelectOption(
                    label=f"#{row['id']} • {row['player']}"[:100],
                    description=f"{row['seller']} → {row['buyer']} • {row['operation_type']}"[:100],
                    value=str(row["id"]),
                    emoji="↩️",
                )
                for row in rows[:25]
            ],
        )

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.edit_message(
            embed=_undo_preview(int(self.values[0])),
            view=UndoConfirmView(int(self.values[0])),
        )


class UndoListView(discord.ui.View):
    def __init__(self, rows):
        super().__init__(timeout=180)
        if rows:
            self.add_item(UndoSelect(rows))
        self.add_item(BackAdminButton(row=1))


class UndoConfirmView(discord.ui.View):
    def __init__(self, transfer_id):
        super().__init__(timeout=120)
        self.transfer_id = int(transfer_id)

    @discord.ui.button(label="CONFIRMAR REVERSIÓN", emoji="↩️", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not APP.es_admin(interaction):
            await interaction.response.send_message("⛔ Solo administradores.", ephemeral=True)
            return
        ok, result = _undo_transfer(self.transfer_id, interaction.user.id)
        if not ok:
            await interaction.response.send_message(f"⚠️ {result}", ephemeral=True)
            return
        movements = "\n".join(f"↩️ **{r['player']}**: {r['buyer']} → {r['seller']}" for r in result)
        embed = discord.Embed(title="✅ Pase deshecho", description=movements, color=discord.Color.green())
        embed.set_footer(text="Operación registrada como REVERTIDA_ADMIN")
        await interaction.response.edit_message(embed=embed, view=BackAdminOnlyView())

    @discord.ui.button(label="CANCELAR", emoji="✖️", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(embed=admin_home_embed(), view=OrganizedAdminHomeView())


class BackAdminOnlyView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=180)
        self.add_item(BackAdminButton(row=0))


class UndoButton(discord.ui.Button):
    def __init__(self, row=1):
        super().__init__(
            label="DESHACER PASE",
            emoji="↩️",
            style=discord.ButtonStyle.danger,
            row=row,
            custom_id="ajap_admin_undo_transfer",
        )

    async def callback(self, interaction: discord.Interaction):
        rows = _recent_reversible(25)
        embed = discord.Embed(
            title="↩️ DESHACER PASE",
            description="Elegí una operación ya aplicada para revertirla de forma segura.",
        )
        if not rows:
            embed.description = "No hay pases aplicados disponibles para revertir."
        await interaction.response.edit_message(embed=embed, view=UndoListView(rows))


# ---------------------------------------------------------------------------
# HERRAMIENTAS EXTRA
# ---------------------------------------------------------------------------
class BudgetOverviewButton(discord.ui.Button):
    def __init__(self, row=1):
        super().__init__(
            label="VER PRESUPUESTOS",
            emoji="📊",
            style=discord.ButtonStyle.secondary,
            row=row,
            custom_id="ajap_admin_budget_overview",
        )

    async def callback(self, interaction: discord.Interaction):
        with APP.db() as conn:
            rows = conn.execute(
                "SELECT club, balance FROM club_finances ORDER BY club COLLATE NOCASE"
            ).fetchall()
        embed = discord.Embed(title="📊 PRESUPUESTOS", description="Saldo actual de los clubes.")
        if not rows:
            embed.description = "Todavía no hay presupuestos registrados."
        else:
            lines = [f"🏟️ **{r['club']}** — {_fmt_money(r['balance'])}" for r in rows]
            chunks = []
            current = []
            size = 0
            for line in lines:
                if current and size + len(line) + 1 > 950:
                    chunks.append(current)
                    current = []
                    size = 0
                current.append(line)
                size += len(line) + 1
            if current:
                chunks.append(current)
            for idx, chunk in enumerate(chunks[:4], 1):
                embed.add_field(name="Clubes" if idx == 1 else f"Clubes • {idx}", value="\n".join(chunk), inline=False)
        await interaction.response.edit_message(embed=embed, view=EconomyView())


class AssignmentsButton(discord.ui.Button):
    def __init__(self, row=0):
        super().__init__(
            label="ASIGNACIONES",
            emoji="👥",
            style=discord.ButtonStyle.secondary,
            row=row,
            custom_id="ajap_admin_assignments",
        )

    async def callback(self, interaction: discord.Interaction):
        source = APP.MercadoView()
        for item in source.children:
            if getattr(item, "custom_id", None) == "mercado_asignaciones":
                await item.callback(interaction)
                return
            callbacks = getattr(item, "callbacks", None)
            if callbacks and callbacks.get("mercado_asignaciones"):
                await callbacks["mercado_asignaciones"](interaction)
                return
        await interaction.response.send_message("⚠️ No encontré la herramienta de asignaciones.", ephemeral=True)


class ExportButton(discord.ui.Button):
    def __init__(self, row=1):
        super().__init__(
            label="EXPORTAR MERCADO",
            emoji="📤",
            style=discord.ButtonStyle.secondary,
            row=row,
            custom_id="ajap_admin_export_market",
        )

    async def callback(self, interaction: discord.Interaction):
        season = APP.temporada_activa()
        if not season:
            await interaction.response.send_message("⚠️ No hay temporada activa.", ephemeral=True)
            return
        with APP.db() as conn:
            rows = conn.execute(
                "SELECT * FROM transfers WHERE season_id = ? ORDER BY id ASC", (season["id"],)
            ).fetchall()
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "operacion_id", "temporada", "jugador_id", "jugador", "tipo", "club_origen",
            "club_destino", "monto", "estado", "aprobada_en", "aplicada_en", "notas",
        ])
        for row in rows:
            writer.writerow([
                row["id"], season["name"], APP.player_code(row["player_id"]) if row["player_id"] else "",
                row["player"], row["operation_type"], row["seller"], row["buyer"], row["amount"],
                row["status"], row["approved_at"] or "", row["applied_at"] or "", row["notes"] or "",
            ])
        safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in season["name"])
        await interaction.response.send_message(
            content=f"📤 **{season['name']}** • {len(rows)} operación(es).",
            file=discord.File(io.BytesIO(output.getvalue().encode("utf-8-sig")), filename=f"AJAP_mercado_{safe}.csv"),
            ephemeral=True,
        )


# ---------------------------------------------------------------------------
# SECCIONES
# ---------------------------------------------------------------------------
class MarketView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=300)
        buttons = _source_buttons()

        if APP.mercado_abierto():
            toggle = _find_button(buttons, "cerrar mercado")
            if toggle:
                self.add_item(ProxyAdminButton(toggle, label="CERRAR MERCADO", emoji="🔒", style=discord.ButtonStyle.danger, row=0, custom_id="ajap_admin_close_market"))
        else:
            toggle = _find_button(buttons, "abrir mercado")
            if toggle:
                self.add_item(ProxyAdminButton(toggle, label="ABRIR MERCADO", emoji="🟢", style=discord.ButtonStyle.success, row=0, custom_id="ajap_admin_open_market"))

        pending = _find_button(buttons, "operaciones pendientes")
        if pending:
            self.add_item(ProxyAdminButton(pending, label="OPERACIONES PENDIENTES", emoji="🛠️", style=discord.ButtonStyle.primary, row=0, custom_id="ajap_admin_pending_ops"))

        clauses = _find_button(buttons, "clausulazos")
        if clauses:
            self.add_item(ProxyAdminButton(clauses, label="CLAUSULAZOS", emoji="💥", style=discord.ButtonStyle.danger, row=1, custom_id="ajap_admin_clauses"))

        self.add_item(UndoButton(row=1))
        self.add_item(BackAdminButton(row=2))


class RostersView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=300)
        buttons = _source_buttons()
        specs = [
            ("agregar jugador", "AGREGAR JUGADOR", "➕", discord.ButtonStyle.primary, 0, "add"),
            ("mover manual", "MOVER JUGADOR", "🔁", discord.ButtonStyle.primary, 0, "move"),
            ("quitar jugador", "QUITAR JUGADOR", "🗑️", discord.ButtonStyle.danger, 1, "remove"),
            ("ver plantel", "VER PLANTEL", "📋", discord.ButtonStyle.secondary, 1, "view"),
        ]
        for needle, label, emoji, style, row, key in specs:
            source = _find_button(buttons, needle)
            if source:
                self.add_item(ProxyAdminButton(source, label=label, emoji=emoji, style=style, row=row, custom_id=f"ajap_admin_roster_{key}"))
        self.add_item(BackAdminButton(row=2))


class EconomyView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=300)
        buttons = _source_buttons()
        give = _find_button(buttons, "dar dinero")
        take = _find_button(buttons, "quitar dinero")
        if give:
            self.add_item(ProxyAdminButton(give, label="DAR DINERO", emoji="➕", style=discord.ButtonStyle.success, row=0, custom_id="ajap_admin_money_add"))
        if take:
            self.add_item(ProxyAdminButton(take, label="QUITAR DINERO", emoji="➖", style=discord.ButtonStyle.danger, row=0, custom_id="ajap_admin_money_remove"))
        self.add_item(BudgetOverviewButton(row=1))
        self.add_item(BackAdminButton(row=2))


class ManagementView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=300)
        buttons = _source_buttons()
        self.add_item(AssignmentsButton(row=0))
        season = _find_button(buttons, "cambiar temporada")
        if season:
            self.add_item(ProxyAdminButton(season, label="CAMBIAR TEMPORADA", emoji="🗓️", style=discord.ButtonStyle.secondary, row=0, custom_id="ajap_admin_change_season"))
        self.add_item(ExportButton(row=1))
        self.add_item(BackAdminButton(row=2))


class SectionButton(discord.ui.Button):
    def __init__(self, *, label, emoji, section, row):
        super().__init__(
            label=label,
            emoji=emoji,
            style=discord.ButtonStyle.secondary,
            row=row,
            custom_id=f"ajap_admin_section_{section}",
        )
        self.section = section

    async def callback(self, interaction: discord.Interaction):
        if not APP.es_admin(interaction):
            await interaction.response.send_message("⛔ Solo administradores.", ephemeral=True)
            return
        if self.section == "market":
            embed = section_embed(
                "🔁 MERCADO",
                "Estado del mercado y control de operaciones.",
                ["🟢/🔒 Abrir o cerrar", "🛠️ Operaciones pendientes", "💥 Clausulazos", "↩️ Deshacer pase"],
            )
            view = MarketView()
        elif self.section == "rosters":
            embed = section_embed(
                "👥 PLANTELES",
                "Correcciones sobre los planteles oficiales.",
                ["➕ Agregar jugador", "🔁 Mover jugador", "🗑️ Quitar jugador", "📋 Ver plantel"],
            )
            view = RostersView()
        elif self.section == "economy":
            embed = section_embed(
                "💰 ECONOMÍA",
                "Administración de presupuestos.",
                ["➕ Dar dinero", "➖ Quitar dinero", "📊 Ver presupuestos"],
            )
            view = EconomyView()
        else:
            embed = section_embed(
                "⚙️ GESTIÓN",
                "Configuración general del torneo y del mercado.",
                ["👥 Asignaciones", "🗓️ Cambiar temporada", "📤 Exportar mercado"],
            )
            view = ManagementView()
        await interaction.response.edit_message(content=None, embeds=[embed], view=view)


class OrganizedAdminHomeView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=300)
        self.add_item(SectionButton(label="MERCADO", emoji="🔁", section="market", row=0))
        self.add_item(SectionButton(label="PLANTELES", emoji="👥", section="rosters", row=0))
        self.add_item(SectionButton(label="ECONOMÍA", emoji="💰", section="economy", row=1))
        self.add_item(SectionButton(label="GESTIÓN", emoji="⚙️", section="management", row=1))
        self.add_item(manager.BackMainButton(row=2))


def apply_staff_admin_organized_patch(runtime, bot):
    global APP, BOT, ORIGINAL_ADMIN_VIEW
    APP = runtime
    BOT = bot
    if getattr(runtime, "_ajap_staff_admin_organized_patch", False):
        return

    # Capturamos la vista final (con persistencia, finanzas, clausulazos, etc.) y
    # reemplazamos únicamente su presentación. El dashboard Staff queda intacto.
    ORIGINAL_ADMIN_VIEW = runtime.AdminView
    _ensure_undo_schema()
    runtime.AdminView = OrganizedAdminHomeView

    runtime._ajap_staff_admin_organized_patch = True
    print("AJAP Administración ordenada: Mercado / Planteles / Economía / Gestión")


_original_apply_guild_isolation_patch = guild_isolation.apply_guild_isolation_patch


def _apply_guild_isolation_then_staff_admin(runtime, bot):
    _original_apply_guild_isolation_patch(runtime, bot)
    apply_staff_admin_organized_patch(runtime, bot)


if not getattr(guild_isolation.apply_guild_isolation_patch, "_ajap_staff_admin_organized_wrapped", False):
    _apply_guild_isolation_then_staff_admin._ajap_staff_admin_organized_wrapped = True
    guild_isolation.apply_guild_isolation_patch = _apply_guild_isolation_then_staff_admin
