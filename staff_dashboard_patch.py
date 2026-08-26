"""Panel informativo de Staff para AJAP Transfer Market.

Reemplaza los guiones del panel principal cuando un administrador entra sin
club asignado por un resumen operativo de la ventana de mercado actual (o la
última cerrada): asignaciones, ofertas, operaciones, dinero movido,
clausulazos, préstamos, alertas y último movimiento.
"""

from __future__ import annotations

import discord

import guild_isolation_patch as guild_isolation
import manager_menu_patch as manager


APP = None
BOT = None
_ORIGINAL_MANAGER_PANEL_EMBED = None


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
                    "SELECT * FROM transfers WHERE status != 'RECHAZADA_ADMIN'" + transfer_window +
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
    embed.add_field(
        name="⏳ Pendientes de respuesta",
        value=str(snapshot["awaiting_response"]),
        inline=False,
    )
    embed.add_field(
        name="✅ Operaciones cerradas",
        value=str(snapshot["closed_operations"]),
        inline=False,
    )
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
        embed.add_field(name="🕘 Último movimiento", value="Todavía no hubo movimientos en esta ventana.", inline=False)

    embed.set_footer(text="AJAP Transfer Market • PES 6")
    return embed


def apply_staff_dashboard_patch(runtime, bot):
    global APP, BOT, _ORIGINAL_MANAGER_PANEL_EMBED
    APP = runtime
    BOT = bot

    if getattr(runtime, "_ajap_staff_dashboard_patch", False):
        return

    _ORIGINAL_MANAGER_PANEL_EMBED = manager.manager_panel_embed

    def manager_panel_embed(user_id: int):
        # Los administradores sin club usan este panel como centro de control.
        # Un usuario con club conserva intacto el panel de su equipo.
        if not APP.club_de(user_id):
            return staff_dashboard_embed()
        return _ORIGINAL_MANAGER_PANEL_EMBED(user_id)

    manager.manager_panel_embed = manager_panel_embed
    runtime.panel_embed = manager_panel_embed
    runtime.staff_dashboard_embed = staff_dashboard_embed
    runtime._ajap_staff_dashboard_patch = True
    print("AJAP panel Staff activo: asignaciones/ofertas/operaciones/dinero/clausulazos/préstamos/alertas")


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
