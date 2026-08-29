"""Consolidated Staff report for rebuilding the PES database after market close.

The old market-close TXT was operation-centric. Staff needs a simpler operational
answer: which players must end up in which clubs in the new PES DB.

This patch replaces the close report with MOVIMIENTOS A PES:
- consolidates multiple same-window events for one player into one net move;
- includes transfers, loans, loan returns, swaps, clauses, free agents and releases;
- keeps purchase options that do not move the player in a separate contractual section;
- keeps pending/rejected operations outside the actionable checklist;
- adds a per-club ALTA/BAJA view plus a chronological audit section;
- preserves /reporte_cierre and adds /movimientos_pes as a clearer alias.
"""

from __future__ import annotations

import io
from collections import defaultdict

import discord
import market_close_report_patch as reports


_ORIGINAL_APPLY = reports.apply_market_close_report_patch
FREE_AGENT = "Jugador Libre"
FINAL_STATUSES = {"APROBADA", "APLICADA"}
REJECTED_STATUS = "RECHAZADA_ADMIN"
PENDING_STATUS = "PENDIENTE_ADMIN"
NO_PHYSICAL_MOVE_TYPES = {"OPCIÓN DE COMPRA", "OPCION DE COMPRA"}


def _has(row, key):
    return row is not None and key in row.keys()


def _table_exists(conn, table):
    return bool(
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
            (table,),
        ).fetchone()
    )


def _season_name(runtime, cycle):
    with runtime.db() as conn:
        if not cycle["season_id"]:
            return "Sin temporada"
        row = conn.execute(
            "SELECT name FROM seasons WHERE id=? LIMIT 1",
            (cycle["season_id"],),
        ).fetchone()
    return row["name"] if row else "Sin temporada"


def _normalize_type(value):
    raw = str(value or "TRANSFERENCIA").strip().upper()
    aliases = {
        "PRESTAMO": "PRÉSTAMO",
        "DEVOLUCION PRESTAMO": "DEVOLUCIÓN PRÉSTAMO",
        "DEVOLUCIÓN PRESTAMO": "DEVOLUCIÓN PRÉSTAMO",
        "OPCION DE COMPRA": "OPCIÓN DE COMPRA",
        "LIBERACION": "LIBERACIÓN",
    }
    return aliases.get(raw, raw)


def _display_type(value):
    op = _normalize_type(value)
    return {
        "JUGADOR LIBRE": "AGENTE LIBRE",
        "DEVOLUCIÓN PRÉSTAMO": "REGRESO DE PRÉSTAMO",
    }.get(op, op)


def _player_key(player_id, player):
    if player_id is not None:
        try:
            return ("id", int(player_id))
        except (TypeError, ValueError):
            pass
    return ("name", str(player or "").strip().casefold())


def _event(*, player_id, player, origin, destination, op_type, created_at,
           source, source_id=None, status="APLICADA", amount=None, note=None):
    return {
        "player_id": int(player_id) if player_id is not None else None,
        "player": str(player or "Jugador sin nombre").strip(),
        "origin": str(origin or "—").strip(),
        "destination": str(destination or "—").strip(),
        "type": _normalize_type(op_type),
        "created_at": str(created_at or ""),
        "source": source,
        "source_id": source_id,
        "status": str(status or "").strip().upper(),
        "amount": amount,
        "note": note,
    }


def _release_events(runtime, cycle):
    with runtime.db() as conn:
        if not _table_exists(conn, "player_releases"):
            return []
        rows = conn.execute(
            """
            SELECT * FROM player_releases
            WHERE created_at >= ? AND created_at <= ?
            ORDER BY created_at ASC, id ASC
            """,
            (cycle["opened_at"], cycle["closed_at"]),
        ).fetchall()

    return [
        _event(
            player_id=row["player_id"],
            player=row["player"],
            origin=row["from_club"],
            destination=FREE_AGENT,
            op_type="LIBERACIÓN",
            created_at=row["created_at"],
            source="LIBERACIÓN",
            source_id=row["id"],
            status="APLICADA",
            amount=(
                f"Costo {int(row['release_cost'])}"
                if _has(row, "release_cost") and row["release_cost"] is not None
                else None
            ),
        )
        for row in rows
    ]


def _history_extra_events(runtime, cycle):
    """Catch manual/admin roster changes not represented by transfers/releases."""
    with runtime.db() as conn:
        if not _table_exists(conn, "player_history"):
            return []
        rows = conn.execute(
            """
            SELECT h.*
            FROM player_history h
            WHERE h.created_at >= ? AND h.created_at <= ?
              AND h.transfer_id IS NULL
              AND UPPER(TRIM(COALESCE(h.event_type,''))) <> 'LIBERACIÓN'
            ORDER BY h.created_at ASC, h.id ASC
            """,
            (cycle["opened_at"], cycle["closed_at"]),
        ).fetchall()

    events = []
    for row in rows:
        origin = row["from_club"] if _has(row, "from_club") else None
        destination = row["to_club"] if _has(row, "to_club") else None
        if not origin or not destination:
            continue
        events.append(
            _event(
                player_id=row["player_id"] if _has(row, "player_id") else None,
                player=row["player"],
                origin=origin,
                destination=destination,
                op_type=row["event_type"],
                created_at=row["created_at"],
                source="HISTORIAL",
                source_id=row["id"],
                status="APLICADA",
            )
        )
    return events


def _transfer_groups(runtime, cycle):
    rows = list(reports.cycle_rows(runtime, cycle))
    physical = []
    contractual = []
    pending = []
    rejected = []

    for row in rows:
        status = str(row["status"] or "").strip().upper()
        op_type = _normalize_type(row["operation_type"])
        item = _event(
            player_id=row["player_id"] if _has(row, "player_id") else None,
            player=row["player"],
            origin=row["seller"],
            destination=row["buyer"],
            op_type=op_type,
            created_at=row["created_at"],
            source="OPERACIÓN",
            source_id=row["id"],
            status=status,
            amount=row["amount"] if _has(row, "amount") else None,
            note=(row["notes"] if _has(row, "notes") else None),
        )

        if status == REJECTED_STATUS:
            rejected.append(item)
        elif status == PENDING_STATUS:
            pending.append(item)
        elif status not in FINAL_STATUSES:
            pending.append(item)
        elif op_type in NO_PHYSICAL_MOVE_TYPES:
            contractual.append(item)
        else:
            physical.append(item)

    return rows, physical, contractual, pending, rejected


def _compress_chain(events):
    if not events:
        return []
    chain = [events[0]["origin"]]
    for event in events:
        destination = event["destination"]
        if not chain or chain[-1].casefold() != destination.casefold():
            chain.append(destination)
    return chain


def _net_movements(events):
    grouped = defaultdict(list)
    for event in sorted(events, key=lambda item: (item["created_at"], str(item["source_id"] or ""))):
        grouped[_player_key(event["player_id"], event["player"])].append(event)

    net = []
    no_change = []
    for group in grouped.values():
        group.sort(key=lambda item: (item["created_at"], str(item["source_id"] or "")))
        first, last = group[0], group[-1]
        types = []
        for item in group:
            label = _display_type(item["type"])
            if label not in types:
                types.append(label)
        summary = {
            "player_id": first["player_id"],
            "player": first["player"],
            "origin": first["origin"],
            "destination": last["destination"],
            "types": types,
            "chain": _compress_chain(group),
            "events": group,
        }
        if first["origin"].casefold() == last["destination"].casefold():
            no_change.append(summary)
        else:
            net.append(summary)

    net.sort(key=lambda item: (item["origin"].casefold(), item["destination"].casefold(), item["player"].casefold()))
    no_change.sort(key=lambda item: item["player"].casefold())
    return net, no_change


def _club_summary(net):
    clubs = defaultdict(lambda: {"altas": [], "bajas": []})
    for item in net:
        origin = item["origin"]
        destination = item["destination"]
        player = item["player"]
        if origin.casefold() != FREE_AGENT.casefold() and origin != "—":
            clubs[origin]["bajas"].append((player, destination))
        if destination.casefold() != FREE_AGENT.casefold() and destination != "—":
            clubs[destination]["altas"].append((player, origin))
    return clubs


def _safe_name(value):
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in str(value)).strip("_") or "mercado"


def build_report(runtime, cycle):
    transfer_rows, transfer_events, contractual, pending, rejected = _transfer_groups(runtime, cycle)
    release_events = _release_events(runtime, cycle)
    history_events = _history_extra_events(runtime, cycle)
    physical_events = transfer_events + release_events + history_events
    net, no_change = _net_movements(physical_events)
    clubs = _club_summary(net)
    season_name = _season_name(runtime, cycle)

    lines = [
        "AJPA TRANSFER MARKET — MOVIMIENTOS A PES",
        "========================================",
        f"Temporada: {season_name}",
        f"Ventana de mercado: #{cycle['id']}",
        f"Apertura: {reports.local_time(cycle['opened_at'])} (Argentina)",
        f"Cierre: {reports.local_time(cycle['closed_at'])} (Argentina)",
        "",
        "OBJETIVO",
        "--------",
        "Esta hoja indica cómo debe quedar la NUEVA DB de PES al terminar el mercado.",
        "Si un jugador tuvo varios movimientos dentro de la misma ventana, se muestra un solo cambio NETO:",
        "club al inicio de la ventana -> club final al cierre.",
        "",
        "RESUMEN GENERAL",
        "---------------",
        f"Cambios netos de plantel a cargar: {len(net)}",
        f"Movimientos intermedios sin cambio neto final: {len(no_change)}",
        f"Cambios contractuales sin mover jugador: {len(contractual)}",
        f"Operaciones pendientes de revisión Staff: {len(pending)}",
        f"Operaciones anuladas/rechazadas: {len(rejected)}",
        "",
        "CHECKLIST GENERAL — HACER EN LA NUEVA DB",
        "-----------------------------------------",
    ]

    if not net:
        lines.append("No hay cambios netos de plantel para cargar.")
    for index, item in enumerate(net, 1):
        types = " + ".join(item["types"])
        lines.append(
            f"[ ] {index:02d}. {item['player']} | {item['origin']} -> {item['destination']} | {types}"
        )
        if len(item["chain"]) > 2:
            lines.append(f"       Recorrido AJPA: {' -> '.join(item['chain'])}")
    lines.append("")

    lines += [
        "CONTROL POR CLUB",
        "----------------",
    ]
    if not clubs:
        lines.append("Sin altas/bajas netas por club.")
    for club in sorted(clubs, key=str.casefold):
        lines.append(f"{club.upper()}")
        altas = sorted(clubs[club]["altas"], key=lambda item: item[0].casefold())
        bajas = sorted(clubs[club]["bajas"], key=lambda item: item[0].casefold())
        if altas:
            lines.append("  ALTAS")
            for player, origin in altas:
                lines.append(f"    [ ] {player} <- {origin}")
        if bajas:
            lines.append("  BAJAS")
            for player, destination in bajas:
                lines.append(f"    [ ] {player} -> {destination}")
        lines.append("")

    if no_change:
        lines += [
            "SIN CAMBIO NETO DE PLANTEL",
            "--------------------------",
            "Estos jugadores tuvieron movimientos durante la ventana pero terminan donde empezaron; no requieren cambio final en la nueva DB.",
        ]
        for item in no_change:
            lines.append(f"[i] {item['player']} | {' -> '.join(item['chain'])}")
        lines.append("")

    if contractual:
        lines += [
            "CAMBIOS CONTRACTUALES — NO MOVER JUGADOR",
            "----------------------------------------",
        ]
        for item in contractual:
            lines.append(
                f"[i] #{item['source_id']} | {item['player']} | {_display_type(item['type'])} | "
                f"permanece en {item['destination']} | {item['amount'] or '$0'}"
            )
        lines.append("")

    if pending:
        lines += [
            "REVISAR ANTES DE TOCAR PES",
            "--------------------------",
            "Estas operaciones NO entran todavía al checklist final porque siguen pendientes de Staff.",
        ]
        for item in pending:
            lines.append(
                f"[?] #{item['source_id']} | {item['player']} | {item['origin']} -> {item['destination']} | "
                f"{_display_type(item['type'])} | {item['status'] or 'SIN ESTADO'}"
            )
        lines.append("")

    if rejected:
        lines += [
            "ANULADOS / RECHAZADOS — NO CARGAR",
            "----------------------------------",
        ]
        for item in rejected:
            lines.append(
                f"[X] #{item['source_id']} | {item['player']} | {item['origin']} -> {item['destination']} | "
                f"{_display_type(item['type'])}"
            )
        lines.append("")

    lines += [
        "AUDITORÍA CRONOLÓGICA",
        "---------------------",
        "Detalle de los eventos usados para construir el cambio neto final.",
    ]
    all_audit = sorted(
        physical_events + contractual + pending + rejected,
        key=lambda item: (item["created_at"], str(item["source_id"] or "")),
    )
    if not all_audit:
        lines.append("No hubo eventos durante esta ventana.")
    for item in all_audit:
        source_id = f"#{item['source_id']}" if item["source_id"] is not None else "—"
        amount = f" | {item['amount']}" if item["amount"] else ""
        lines.append(
            f"{reports.local_time(item['created_at'])} | {item['source']} {source_id} | {item['player']} | "
            f"{item['origin']} -> {item['destination']} | {_display_type(item['type'])} | {item['status']}{amount}"
        )
    lines += ["", "Fin de MOVIMIENTOS A PES.", "Generado automáticamente por AJPA Transfer Market."]

    text = "\n".join(lines)
    filename = f"MOVIMIENTOS_A_PES_{_safe_name(season_name)}_mercado_{cycle['id']}.txt"

    # The original caller only uses len(rows) for the close/recovery message.
    # Return every source record so that number reflects the whole report, not
    # only ordinary transfers.
    source_records = list(transfer_rows) + release_events + history_events
    return text, filename, source_records, season_name


async def deliver(runtime, interaction, text, filename):
    members = reports.staff_members(interaction.guild) if interaction.guild else []
    if isinstance(interaction.user, discord.Member) and not interaction.user.bot:
        if reports.is_staff_or_admin(runtime, interaction) and all(member.id != interaction.user.id for member in members):
            members.append(interaction.user)

    delivered = 0
    failures = 0
    payload = text.encode("utf-8-sig")
    for member in members:
        try:
            await member.send(
                embed=discord.Embed(
                    title="🎮 MOVIMIENTOS A PES",
                    description=(
                        "Checklist general para actualizar la nueva DB de PES después del cierre.\n"
                        "Primero muestra el cambio neto por jugador y después el control de altas/bajas por club."
                    ),
                ),
                file=discord.File(io.BytesIO(payload), filename=filename),
            )
            delivered += 1
        except Exception:
            failures += 1
    return delivered, len(members), failures


def apply_market_close_report_patch(runtime, bot):
    # Replace module globals before the original AdminView is created; its close
    # callback resolves build_report/deliver dynamically from this module.
    reports.build_report = build_report
    reports.deliver = deliver
    result = _ORIGINAL_APPLY(runtime, bot)

    if bot.tree.get_command("movimientos_pes") is None:
        @bot.tree.command(
            name="movimientos_pes",
            description="Descarga los movimientos del último mercado para actualizar PES",
        )
        async def movimientos_pes(interaction: discord.Interaction):
            if not reports.is_staff_or_admin(runtime, interaction):
                await interaction.response.send_message("⛔ Solo Staff/administradores.", ephemeral=True)
                return
            cycle = reports.latest_closed_cycle(runtime)
            if not cycle:
                await interaction.response.send_message(
                    "⚠️ Todavía no hay un cierre de mercado registrado.",
                    ephemeral=True,
                )
                return
            text, filename, rows, season_name = build_report(runtime, cycle)
            await interaction.response.send_message(
                content=(
                    f"🎮 **MOVIMIENTOS A PES** • Cierre **#{cycle['id']}** • **{season_name}**\n"
                    f"📋 Fuentes registradas: **{len(rows)}**."
                ),
                file=discord.File(io.BytesIO(text.encode("utf-8-sig")), filename=filename),
                ephemeral=True,
            )

    runtime.build_pes_movement_report = build_report
    runtime._ajap_pes_movement_summary = True
    print("AJPA cierre de mercado: MOVIMIENTOS A PES netos + control por club + auditoría")
    return result


reports.apply_market_close_report_patch = apply_market_close_report_patch
