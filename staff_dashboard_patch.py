"""Dashboard y perfiles de Staff para AJAP Transfer Market.

Al ejecutar /mercado un administrador siempre entra al tablero Staff con la
información operativa. Desde ahí puede cambiar entre:
- PERFIL USUARIO: exactamente la experiencia manager normal, sin controles admin,
  útil para probar el bot como lo ve un DT.
- PERFIL ADMINISTRADOR: herramientas de gestión, corrección y auditoría.

Incluye además una herramienta segura de DESHACER PASE para revertir operaciones
ya aplicadas cuando el jugador todavía está en el club destino esperado.
"""

from __future__ import annotations

import csv
import io

import discord

import guild_isolation_patch as guild_isolation
import manager_menu_patch as manager


APP = None
BOT = None
_ORIGINAL_MANAGER_PANEL_EMBED = None
_ORIGINAL_MARKET_VIEW_FOR = None
_ORIGINAL_MERCADO_COMMAND = None
_MODES = {}  # (guild_id, user_id) -> staff | user | admin


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


def _guild_id(interaction=None):
    if interaction is not None and getattr(interaction, "guild_id", None):
        return int(interaction.guild_id)
    getter = getattr(APP, "current_guild_id", None)
    if getter:
        try:
            return int(getter())
        except Exception:
            pass
    return int(guild_isolation.LEGACY_GUILD_ID)


def _mode_key(user_id: int, interaction=None):
    return (_guild_id(interaction), int(user_id))


def _set_mode(interaction, mode: str):
    _MODES[_mode_key(interaction.user.id, interaction)] = mode


def _mode_for(user_id: int):
    return _MODES.get(_mode_key(user_id))


def _cycle_for_dashboard(conn, market_open: bool):
    if not _table_exists(conn, "market_cycles"):
        return None
    if market_open:
        return conn.execute(
            "SELECT * FROM market_cycles WHERE closed_at IS NULL ORDER BY id DESC LIMIT 1"
        ).fetchone()
    return conn.execute(
        "SELECT * FROM market_cycles WHERE closed_at IS NOT NULL ORDER BY id DESC LIMIT 1"
    ).fetchone()


def _window_sql(cycle, column="created_at"):
    if not cycle:
        return "", []
    if cycle["closed_at"]:
        return f" AND {column} >= ? AND {column} <= ?", [cycle["opened_at"], cycle["closed_at"]]
    return f" AND {column} >= ?", [cycle["opened_at"]]


def _staff_snapshot():
    market_open = APP.mercado_abierto()
    data = {
        "market_open": market_open,
        "cycle_id": None,
        "assigned": 0,
        "total_clubs": 0,
        "active_offers": 0,
        "awaiting_response": 0,
        "closed_operations": 0,
        "money_moved": 0,
        "clauses": 0,
        "active_loans": 0,
        "pending_admin": 0,
        "pending_pes": 0,
        "pending_clauses": 0,
        "low_balance": 0,
        "loan_attention": 0,
        "last_move": None,
    }

    try:
        with APP.db() as conn:
            cycle = _cycle_for_dashboard(conn, market_open)
            if cycle:
                data["cycle_id"] = int(cycle["id"])

            if _table_exists(conn, "clubs"):
                row = conn.execute("SELECT COUNT(DISTINCT name) AS n FROM clubs").fetchone()
                data["assigned"] = int(row["n"] or 0)

            if _table_exists(conn, "league_teams"):
                row = conn.execute(
                    "SELECT COUNT(*) AS n FROM league_teams WHERE active = 1"
                ).fetchone()
                data["total_clubs"] = int(row["n"] or 0)

            if not data["total_clubs"]:
                try:
                    import team_assignment as teams
                    data["total_clubs"] = len(teams.OFFICIAL_TEAMS)
                except Exception:
                    data["total_clubs"] = data["assigned"]

            if _table_exists(conn, "offers"):
                offer_window, offer_params = _window_sql(cycle, "created_at")
                row = conn.execute(
                    "SELECT COUNT(*) AS n FROM offers WHERE status = 'PENDIENTE'" + offer_window,
                    offer_params,
                ).fetchone()
                data["active_offers"] = int(row["n"] or 0)
                row = conn.execute(
                    "SELECT COUNT(DISTINCT publication_id) AS n FROM offers "
                    "WHERE status = 'PENDIENTE'" + offer_window,
                    offer_params,
                ).fetchone()
                data["awaiting_response"] = int(row["n"] or 0)

            if _table_exists(conn, "transfers"):
                transfer_window, transfer_params = _window_sql(cycle, "created_at")
                valid_rows = conn.execute(
                    "SELECT * FROM transfers "
                    "WHERE status NOT IN ('RECHAZADA_ADMIN','REVERTIDA_ADMIN')" + transfer_window +
                    " ORDER BY id ASC",
                    transfer_params,
                ).fetchall()
                data["closed_operations"] = len(valid_rows)
                total_money = 0
                for transfer in valid_rows:
                    try:
                        amount = APP.price_number(transfer["amount"] or "")
                    except Exception:
                        amount = None
                    if amount is not None and amount > 0:
                        total_money += int(amount)
                data["money_moved"] = total_money
                if valid_rows:
                    data["last_move"] = valid_rows[-1]

                row = conn.execute(
                    "SELECT COUNT(*) AS n FROM transfers WHERE status = 'PENDIENTE_ADMIN'" + transfer_window,
                    transfer_params,
                ).fetchone()
                data["pending_admin"] = int(row["n"] or 0)
                row = conn.execute(
                    "SELECT COUNT(*) AS n FROM transfers WHERE status = 'APROBADA'" + transfer_window,
                    transfer_params,
                ).fetchone()
                data["pending_pes"] = int(row["n"] or 0)

            if _table_exists(conn, "clause_requests"):
                if cycle:
                    row = conn.execute(
                        "SELECT COUNT(*) AS n FROM clause_requests WHERE cycle_id = ? AND status = 'APROBADO'",
                        (cycle["id"],),
                    ).fetchone()
                    data["clauses"] = int(row["n"] or 0)
                    row = conn.execute(
                        "SELECT COUNT(*) AS n FROM clause_requests WHERE cycle_id = ? AND status = 'PENDIENTE_STAFF'",
                        (cycle["id"],),
                    ).fetchone()
                    data["pending_clauses"] = int(row["n"] or 0)
                else:
                    row = conn.execute(
                        "SELECT COUNT(*) AS n FROM clause_requests WHERE status = 'APROBADO'"
                    ).fetchone()
                    data["clauses"] = int(row["n"] or 0)
                    row = conn.execute(
                        "SELECT COUNT(*) AS n FROM clause_requests WHERE status = 'PENDIENTE_STAFF'"
                    ).fetchone()
                    data["pending_clauses"] = int(row["n"] or 0)

            if _table_exists(conn, "loans"):
                row = conn.execute(
                    """
                    SELECT COUNT(*) AS n FROM loans
                    WHERE status IN ('ACTIVE','OPTION_PENDING','RETURN_PENDING','REVIEW_REQUIRED')
                    """
                ).fetchone()
                data["active_loans"] = int(row["n"] or 0)
                row = conn.execute(
                    """
                    SELECT COUNT(*) AS n FROM loans
                    WHERE status IN ('OPTION_PENDING','RETURN_PENDING','REVIEW_REQUIRED')
                    """
                ).fetchone()
                data["loan_attention"] = int(row["n"] or 0)

            if _table_exists(conn, "club_finances"):
                if _table_exists(conn, "league_teams"):
                    row = conn.execute(
                        """
                        SELECT COUNT(*) AS n
                        FROM league_teams lt
                        LEFT JOIN club_finances cf ON cf.club = lt.name COLLATE NOCASE
                        WHERE lt.active = 1 AND COALESCE(cf.balance, 0) < 1000000
                        """
                    ).fetchone()
                else:
                    row = conn.execute(
                        "SELECT COUNT(*) AS n FROM club_finances WHERE balance < 1000000"
                    ).fetchone()
                data["low_balance"] = int(row["n"] or 0)
    except Exception as exc:
        print(f"WARNING AJAP staff dashboard: snapshot parcial: {exc}")

    return data


def staff_dashboard_embed():
    snapshot = _staff_snapshot()
    market_text = "🟢 ABIERTO" if snapshot["market_open"] else "🔒 CERRADO"
    if snapshot["cycle_id"]:
        market_text += f" • Ventana #{snapshot['cycle_id']}"

    total = snapshot["total_clubs"]
    assignments = f"{snapshot['assigned']} / {total}" if total else str(snapshot["assigned"])

    embed = discord.Embed(
        title="⚙️ AJAP TRANSFER MARKET • STAFF",
        description="━━━━━━━━━━━━━━━━━━━━",
    )
    embed.add_field(name="🔁 Mercado", value=market_text, inline=False)
    embed.add_field(name="🏟️ Clubes asignados", value=assignments, inline=False)
    embed.add_field(name="📨 Ofertas activas", value=str(snapshot["active_offers"]), inline=False)
    embed.add_field(name="⏳ Pendientes de respuesta", value=str(snapshot["awaiting_response"]), inline=False)
    embed.add_field(name="✅ Operaciones cerradas", value=str(snapshot["closed_operations"]), inline=False)
    embed.add_field(name="💰 Dinero movido", value=_fmt_money(snapshot["money_moved"]), inline=False)
    embed.add_field(name="🚨 Clausulazos", value=str(snapshot["clauses"]), inline=False)
    embed.add_field(name="🤝 Préstamos activos", value=str(snapshot["active_loans"]), inline=False)

    alerts = []
    unassigned = max(snapshot["total_clubs"] - snapshot["assigned"], 0)
    if unassigned:
        alerts.append(f"🏟️ {unassigned} club(es) todavía sin dueño")
    if snapshot["pending_admin"]:
        alerts.append(f"🟡 {snapshot['pending_admin']} operación(es) esperando revisión Staff")
    if snapshot["pending_pes"]:
        alerts.append(f"🎮 {snapshot['pending_pes']} operación(es) aprobada(s) pendiente(s) de aplicar en PES")
    if snapshot["pending_clauses"]:
        alerts.append(f"🚨 {snapshot['pending_clauses']} clausulazo(s) pendiente(s) de revisión")
    if snapshot["loan_attention"]:
        alerts.append(f"🤝 {snapshot['loan_attention']} préstamo(s) requieren atención")
    if snapshot["low_balance"]:
        alerts.append(f"💸 {snapshot['low_balance']} club(es) con menos de $1.000.000")

    embed.add_field(
        name="⚠️ Alertas Staff",
        value="\n".join(alerts[:6]) if alerts else "✅ Sin alertas pendientes",
        inline=False,
    )

    last = snapshot["last_move"]
    if last:
        amount = last["amount"] or "$0"
        embed.add_field(
            name="🕘 Último movimiento",
            value=(
                f"**{last['player']}**\n"
                f"{last['seller']} ➜ {last['buyer']}\n"
                f"💰 {amount} • {last['operation_type']}"
            ),
            inline=False,
        )
    else:
        embed.add_field(
            name="🕘 Último movimiento",
            value="Todavía no hubo movimientos en esta ventana.",
            inline=False,
        )

    embed.set_footer(text="AJAP Transfer Market • PES 6")
    return embed


def _user_profile_embed(user_id: int):
    club = APP.club_de(user_id)
    if club:
        return _ORIGINAL_MANAGER_PANEL_EMBED(user_id)

    embed = discord.Embed(
        title="👤 PERFIL USUARIO • MODO PRUEBA",
        description=(
            "Vista de jugador activada. No tenés un club asignado, por eso las "
            "herramientas que dependen de una plantilla no aparecen o pedirán un club."
        ),
    )
    embed.add_field(
        name="🔁 Mercado",
        value="🟢 ABIERTO" if APP.mercado_abierto() else "🔒 CERRADO",
        inline=False,
    )
    embed.set_footer(text="Modo prueba Staff • mismas funciones que un usuario normal")
    return embed


def _strip_admin_controls(view):
    for item in list(view.children):
        cid = str(getattr(item, "custom_id", "") or "")
        label = str(getattr(item, "label", "") or "").casefold()
        if cid in {"ajap_manager_admin", "mercado_admin", "mercado_asignaciones"}:
            view.remove_item(item)
            continue
        if "administración" in label or label == "asignaciones":
            view.remove_item(item)
    return view


class BackToStaffButton(discord.ui.Button):
    def __init__(self, row=4):
        super().__init__(
            label="VOLVER A STAFF",
            emoji="⬅️",
            style=discord.ButtonStyle.secondary,
            row=row,
            custom_id="ajap_staff_back_home",
        )

    async def callback(self, interaction: discord.Interaction):
        if not APP.es_admin(interaction):
            await interaction.response.send_message("⛔ Solo administradores.", ephemeral=True)
            return
        _set_mode(interaction, "staff")
        await interaction.response.edit_message(
            content=None,
            embeds=[staff_dashboard_embed()],
            view=StaffHomeView(),
        )


def _player_view(interaction: discord.Interaction):
    view = _ORIGINAL_MARKET_VIEW_FOR(interaction)
    _strip_admin_controls(view)
    if not any(getattr(i, "custom_id", None) == "ajap_staff_back_home" for i in view.children):
        view.add_item(BackToStaffButton(row=4))
    return view


def _admin_profile_embed():
    season = APP.temporada_activa()
    embed = discord.Embed(
        title="⚙️ PERFIL ADMINISTRADOR",
        description="Centro de herramientas para operar, corregir y auditar el mercado.",
    )
    embed.add_field(
        name="🔁 Estado",
        value="🟢 Mercado ABIERTO" if APP.mercado_abierto() else "🔒 Mercado CERRADO",
        inline=True,
    )
    embed.add_field(
        name="🗓️ Temporada",
        value=season["name"] if season else "Sin temporada",
        inline=True,
    )
    embed.add_field(
        name="🧰 Herramientas",
        value=(
            "Abrir/cerrar mercado • operaciones pendientes • dar/quitar dinero • "
            "agregar/mover/quitar jugadores • ver planteles • asignaciones • "
            "cambiar temporada • deshacer pases • exportar mercado"
        ),
        inline=False,
    )
    embed.set_footer(text="Las correcciones sensibles quedan registradas en SQLite")
    return embed


def _ensure_undo_schema():
    with APP.db() as conn:
        APP.add_column_if_missing(conn, "transfers", "reverted_by", "INTEGER")
        APP.add_column_if_missing(conn, "transfers", "reverted_at", "DATETIME")
        APP.add_column_if_missing(conn, "transfers", "revert_reason", "TEXT")


def _deal_rows_for_undo(transfer_id: int, conn=None):
    owns_conn = conn is None
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
        if owns_conn:
            conn.close()


def _recent_reversible_deals(limit=25):
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


def _undo_preview_embed(transfer_id: int):
    rows = _deal_rows_for_undo(transfer_id)
    embed = discord.Embed(
        title="↩️ DESHACER PASE",
        description=(
            "Revisá el movimiento antes de confirmar. El bot solo lo revierte si "
            "todos los jugadores siguen en el club destino esperado."
        ),
        color=discord.Color.orange(),
    )
    if not rows:
        embed.description = "La operación ya no existe."
        return embed

    for row in rows:
        embed.add_field(
            name=f"#{row['id']} • {row['player']}",
            value=(
                f"{row['seller']} ➜ **{row['buyer']}**\n"
                f"Tipo: **{row['operation_type']}** • Monto: **{row['amount']}**"
            ),
            inline=False,
        )
    if any((row["operation_type"] or "").upper() == "CLAUSULAZO" for row in rows):
        embed.add_field(
            name="💰 Clausulazo",
            value="También se intentará devolver el importe al comprador y retirarlo del club vendedor.",
            inline=False,
        )
    embed.set_footer(text="Esta acción queda auditada como REVERTIDA_ADMIN")
    return embed


def _undo_deal(transfer_id: int, admin_id: int):
    _ensure_undo_schema()
    conn = APP.db()
    try:
        conn.execute("BEGIN IMMEDIATE")
        rows = _deal_rows_for_undo(transfer_id, conn=conn)
        if not rows:
            conn.rollback()
            return False, "Operación no encontrada."

        blocked = {"OPCIÓN DE COMPRA", "DEVOLUCIÓN PRÉSTAMO"}
        if any((row["operation_type"] or "").upper() in blocked for row in rows):
            conn.rollback()
            return False, "Ese tipo de movimiento de préstamo requiere una corrección específica y no se revierte desde este botón."

        if any((row["status"] or "").upper() != "APLICADA" for row in rows):
            conn.rollback()
            return False, "El acuerdo ya no está completamente APLICADO o ya fue revertido."

        players = []
        for row in rows:
            player = conn.execute(
                "SELECT * FROM roster_players WHERE id = ?",
                (int(row["player_id"]),),
            ).fetchone() if row["player_id"] else conn.execute(
                "SELECT * FROM roster_players WHERE name = ? COLLATE NOCASE",
                (row["player"],),
            ).fetchone()
            if not player:
                conn.rollback()
                return False, f"No encontré a {row['player']} en el plantel oficial."
            if (player["club"] or "").casefold() != (row["buyer"] or "").casefold():
                conn.rollback()
                return False, (
                    f"{row['player']} ya no está en {row['buyer']} (figura en {player['club']}). "
                    "No se tocó nada para evitar romper movimientos posteriores."
                )
            players.append((row, player))

        # Los clausulazos sí mueven dinero automáticamente al ser aprobados.
        clause_refunds = []
        for row, _player in players:
            if (row["operation_type"] or "").upper() != "CLAUSULAZO":
                continue
            amount = APP.price_number(row["amount"] or "")
            if not amount:
                conn.rollback()
                return False, f"No pude interpretar el monto del clausulazo #{row['id']}."
            for club in (row["seller"], row["buyer"]):
                conn.execute(
                    "INSERT OR IGNORE INTO club_finances (club, balance) VALUES (?, 0)",
                    (club,),
                )
            seller_balance = conn.execute(
                "SELECT balance FROM club_finances WHERE club = ? COLLATE NOCASE",
                (row["seller"],),
            ).fetchone()
            seller_balance = int(seller_balance["balance"] if seller_balance else 0)
            if seller_balance < int(amount):
                conn.rollback()
                return False, (
                    f"No se puede revertir el clausulazo: {row['seller']} tiene {_fmt_money(seller_balance)} "
                    f"y debe devolver {_fmt_money(amount)}. Ajustá el saldo primero."
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
                    revert_reason = 'Deshecho desde Perfil Administrador'
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
                (
                    int(player["id"]), row["player"], row["buyer"], row["seller"],
                    int(row["id"]), row["season_id"],
                ),
            )

            if (row["operation_type"] or "").upper() == "PRÉSTAMO" and _table_exists(conn, "loans"):
                conn.execute(
                    """
                    UPDATE loans
                    SET status = 'CANCELLED_ADMIN', resolved_at = CURRENT_TIMESTAMP
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


class UndoDealSelect(discord.ui.Select):
    def __init__(self, rows):
        options = []
        for row in rows[:25]:
            group = row["deal_group"] if "deal_group" in row.keys() else None
            suffix = " • acuerdo" if group else ""
            options.append(
                discord.SelectOption(
                    label=f"#{row['id']} • {row['player']}"[:100],
                    description=(
                        f"{row['seller']} → {row['buyer']} • {row['operation_type']}{suffix}"
                    )[:100],
                    value=str(row["id"]),
                    emoji="↩️",
                )
            )
        super().__init__(
            placeholder="Elegí el pase que querés deshacer",
            min_values=1,
            max_values=1,
            options=options,
        )

    async def callback(self, interaction: discord.Interaction):
        if not APP.es_admin(interaction):
            await interaction.response.send_message("⛔ Solo administradores.", ephemeral=True)
            return
        transfer_id = int(self.values[0])
        await interaction.response.edit_message(
            embed=_undo_preview_embed(transfer_id),
            view=UndoConfirmView(transfer_id),
        )


class UndoDealListView(discord.ui.View):
    def __init__(self, rows):
        super().__init__(timeout=180)
        if rows:
            self.add_item(UndoDealSelect(rows))
        self.add_item(AdminBackButton(row=1))


class UndoConfirmView(discord.ui.View):
    def __init__(self, transfer_id: int):
        super().__init__(timeout=120)
        self.transfer_id = int(transfer_id)

    @discord.ui.button(label="Sí, deshacer pase", emoji="↩️", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not APP.es_admin(interaction):
            await interaction.response.send_message("⛔ Solo administradores.", ephemeral=True)
            return
        ok, result = _undo_deal(self.transfer_id, interaction.user.id)
        if not ok:
            await interaction.response.send_message(f"⚠️ {result}", ephemeral=True)
            return

        rows = result
        movements = "\n".join(
            f"↩️ **{row['player']}**: {row['buyer']} → {row['seller']}" for row in rows
        )
        embed = discord.Embed(
            title="✅ Pase deshecho",
            description=movements,
            color=discord.Color.green(),
        )
        embed.add_field(name="Estado", value="REVERTIDA_ADMIN", inline=True)
        embed.set_footer(text=f"Revertido por {interaction.user.display_name}")
        await interaction.response.edit_message(embed=embed, view=AdminBackOnlyView())

    @discord.ui.button(label="Cancelar", emoji="✖️", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(
            embed=_admin_profile_embed(),
            view=_admin_profile_view(),
        )


class AdminBackButton(discord.ui.Button):
    def __init__(self, row=4):
        super().__init__(
            label="VOLVER A ADMIN",
            emoji="⬅️",
            style=discord.ButtonStyle.secondary,
            row=row,
            custom_id=f"ajap_staff_back_admin_{row}",
        )

    async def callback(self, interaction: discord.Interaction):
        if not APP.es_admin(interaction):
            await interaction.response.send_message("⛔ Solo administradores.", ephemeral=True)
            return
        _set_mode(interaction, "admin")
        await interaction.response.edit_message(
            content=None,
            embeds=[_admin_profile_embed()],
            view=_admin_profile_view(),
        )


class AdminBackOnlyView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=180)
        self.add_item(AdminBackButton(row=0))


class UndoPassButton(discord.ui.Button):
    def __init__(self, row=4):
        super().__init__(
            label="DESHACER PASE",
            emoji="↩️",
            style=discord.ButtonStyle.danger,
            row=row,
            custom_id="ajap_staff_undo_pass",
        )

    async def callback(self, interaction: discord.Interaction):
        if not APP.es_admin(interaction):
            await interaction.response.send_message("⛔ Solo administradores.", ephemeral=True)
            return
        rows = _recent_reversible_deals(25)
        embed = discord.Embed(
            title="↩️ Deshacer pase",
            description=(
                "Elegí una operación ya aplicada. No se muestran opciones de compra ni devoluciones "
                "de préstamo porque requieren un flujo específico."
            ),
        )
        if not rows:
            embed.description = "No hay pases aplicados que puedan deshacerse desde esta herramienta."
        await interaction.response.edit_message(
            embed=embed,
            view=UndoDealListView(rows),
        )


class AssignmentsButton(discord.ui.Button):
    def __init__(self, row=4):
        super().__init__(
            label="ASIGNACIONES",
            emoji="👥",
            style=discord.ButtonStyle.secondary,
            row=row,
            custom_id="ajap_staff_assignments",
        )

    async def callback(self, interaction: discord.Interaction):
        if not APP.es_admin(interaction):
            await interaction.response.send_message("⛔ Solo administradores.", ephemeral=True)
            return
        source = APP.MercadoView()
        for item in source.children:
            if getattr(item, "custom_id", None) == "mercado_asignaciones":
                await item.callback(interaction)
                return
        await interaction.response.send_message(
            "⚠️ No encontré la herramienta de asignaciones en esta versión.",
            ephemeral=True,
        )


class ExportMarketButton(discord.ui.Button):
    def __init__(self, row=4):
        super().__init__(
            label="EXPORTAR",
            emoji="📤",
            style=discord.ButtonStyle.secondary,
            row=row,
            custom_id="ajap_staff_export_market",
        )

    async def callback(self, interaction: discord.Interaction):
        if not APP.es_admin(interaction):
            await interaction.response.send_message("⛔ Solo administradores.", ephemeral=True)
            return
        season = APP.temporada_activa()
        if not season:
            await interaction.response.send_message("⚠️ No hay temporada activa.", ephemeral=True)
            return
        with APP.db() as conn:
            rows = conn.execute(
                "SELECT * FROM transfers WHERE season_id = ? ORDER BY id ASC",
                (season["id"],),
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

        data = output.getvalue().encode("utf-8-sig")
        safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in season["name"])
        await interaction.response.send_message(
            content=f"📤 Exportación de **{season['name']}** • {len(rows)} operación(es).",
            file=discord.File(io.BytesIO(data), filename=f"AJAP_mercado_{safe_name}.csv"),
            ephemeral=True,
        )


def _admin_profile_view():
    Base = APP.AdminView

    class StaffAdminProfileView(Base):
        def __init__(self):
            super().__init__()

            # El panel admin antiguo podía traer un "Volver al menú" de navegación.
            # Lo reemplazamos por una salida explícita al dashboard Staff.
            for item in list(self.children):
                label = str(getattr(item, "label", "") or "").casefold()
                if label.startswith("volver"):
                    self.remove_item(item)

            self.add_item(UndoPassButton(row=4))
            self.add_item(AssignmentsButton(row=4))
            self.add_item(ExportMarketButton(row=4))
            self.add_item(BackToStaffButton(row=4))

    StaffAdminProfileView.__name__ = "StaffAdminProfileView"
    return StaffAdminProfileView()


class StaffHomeView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=300)

    @discord.ui.button(
        label="PERFIL USUARIO",
        emoji="👤",
        style=discord.ButtonStyle.primary,
        row=0,
        custom_id="ajap_staff_profile_user",
    )
    async def user_profile(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not APP.es_admin(interaction):
            await interaction.response.send_message("⛔ Solo administradores.", ephemeral=True)
            return
        _set_mode(interaction, "user")
        await interaction.response.edit_message(
            content=None,
            embeds=[_user_profile_embed(interaction.user.id)],
            view=_player_view(interaction),
        )

    @discord.ui.button(
        label="PERFIL ADMINISTRADOR",
        emoji="⚙️",
        style=discord.ButtonStyle.secondary,
        row=0,
        custom_id="ajap_staff_profile_admin",
    )
    async def admin_profile(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not APP.es_admin(interaction):
            await interaction.response.send_message("⛔ Solo administradores.", ephemeral=True)
            return
        _set_mode(interaction, "admin")
        await interaction.response.edit_message(
            content=None,
            embeds=[_admin_profile_embed()],
            view=_admin_profile_view(),
        )


def apply_staff_dashboard_patch(runtime, bot):
    global APP, BOT, _ORIGINAL_MANAGER_PANEL_EMBED, _ORIGINAL_MARKET_VIEW_FOR, _ORIGINAL_MERCADO_COMMAND
    APP = runtime
    BOT = bot

    if getattr(runtime, "_ajap_staff_dashboard_patch", False):
        return

    _ORIGINAL_MANAGER_PANEL_EMBED = manager.manager_panel_embed
    _ORIGINAL_MARKET_VIEW_FOR = manager.market_view_for
    _ORIGINAL_MERCADO_COMMAND = manager.mercado_command
    _ensure_undo_schema()

    def contextual_manager_panel_embed(user_id: int):
        mode = _mode_for(user_id)
        if mode == "user":
            return _user_profile_embed(user_id)
        if mode in {"staff", "admin"}:
            return staff_dashboard_embed()
        return _ORIGINAL_MANAGER_PANEL_EMBED(user_id)

    def contextual_market_view_for(interaction: discord.Interaction):
        if APP.es_admin(interaction) and _mode_for(interaction.user.id) == "user":
            return _player_view(interaction)
        return _ORIGINAL_MARKET_VIEW_FOR(interaction)

    async def mercado_command(interaction: discord.Interaction):
        if APP.es_admin(interaction):
            _set_mode(interaction, "staff")
            await interaction.response.send_message(
                embed=staff_dashboard_embed(),
                view=StaffHomeView(),
                ephemeral=True,
            )
            return
        await _ORIGINAL_MERCADO_COMMAND(interaction)

    manager.manager_panel_embed = contextual_manager_panel_embed
    manager.market_view_for = contextual_market_view_for
    manager.mercado_command = mercado_command
    runtime.panel_embed = contextual_manager_panel_embed
    runtime.manager_market_view_for = contextual_market_view_for
    runtime.market_view_for = contextual_market_view_for
    runtime.staff_dashboard_embed = staff_dashboard_embed
    runtime.StaffHomeView = StaffHomeView

    bot.tree.remove_command("mercado")
    bot.tree.command(
        name="mercado",
        description="Abre el panel principal de AJAP Transfer Market",
    )(mercado_command)

    runtime._ajap_staff_dashboard_patch = True
    print(
        "AJAP Staff hub activo: dashboard + perfil usuario + perfil admin + "
        "deshacer pase/asignaciones/exportar"
    )


_original_apply_guild_isolation_patch = guild_isolation.apply_guild_isolation_patch


def _apply_guild_isolation_then_staff_dashboard(runtime, bot):
    _original_apply_guild_isolation_patch(runtime, bot)
    apply_staff_dashboard_patch(runtime, bot)


if not getattr(
    guild_isolation.apply_guild_isolation_patch,
    "_ajap_staff_dashboard_wrapped",
    False,
):
    _apply_guild_isolation_then_staff_dashboard._ajap_staff_dashboard_wrapped = True
    guild_isolation.apply_guild_isolation_patch = _apply_guild_isolation_then_staff_dashboard
