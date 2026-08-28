"""Send a Staff movement digest whenever AJAP creates a database backup.

The summary is built from the backup file itself (not from the live DB), so the
message describes exactly what the snapshot contains. The configured
/canal_movimientos channel is reused and every guild remains isolated.
"""

from __future__ import annotations

import asyncio
import io
import queue
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import discord

import automatic_backup_patch as backups
import guild_isolation_patch as guild_isolation


APP = None
BOT = None
_SUMMARY_QUEUE: queue.Queue = queue.Queue()
_SUMMARY_TASK = None
_ORIGINAL_CREATE = backups._create_backup_sync


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return bool(
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
            (name,),
        ).fetchone()
    )


def _columns(conn: sqlite3.Connection, table: str):
    if not _table_exists(conn, table):
        return set()
    return {row["name"] for row in conn.execute(f'PRAGMA table_info("{table}")').fetchall()}


def _latest_expr(columns, preferred):
    available = [name for name in preferred if name in columns]
    if not available:
        return None
    if len(available) == 1:
        return available[0]
    return "COALESCE(" + ", ".join(available) + ")"


def _previous_backup(runtime, guild_id: int, current: Path):
    files = backups._all_backups(runtime, int(guild_id))
    current_resolved = current.resolve()
    found = False
    for path in files:
        if path.resolve() == current_resolved:
            found = True
            continue
        if found:
            return path
    # Fallback for equal mtimes / ordering edge cases.
    older = [
        path for path in files
        if path.resolve() != current_resolved
        and path.stat().st_mtime <= current.stat().st_mtime
    ]
    return older[0] if older else None


def _utc_sql(dt: datetime | None):
    if dt is None:
        return None
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def _fmt_dt(value):
    if not value:
        return "—"
    raw = str(value).strip()
    try:
        dt = datetime.strptime(raw[:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        return dt.astimezone(backups.LOCAL_TZ).strftime("%d/%m/%Y %H:%M")
    except ValueError:
        return raw


def _money(value):
    raw = str(value or "").strip()
    if not raw:
        return "—"
    if raw.startswith("$"):
        return raw
    try:
        return f"${int(raw):,}".replace(",", ".")
    except (TypeError, ValueError):
        return raw


def _window_rows(conn, table, time_expr, start_sql, order="id ASC"):
    if not _table_exists(conn, table) or not time_expr:
        return []
    if start_sql:
        return conn.execute(
            f'SELECT * FROM "{table}" WHERE {time_expr} > ? ORDER BY {order}',
            (start_sql,),
        ).fetchall()
    return conn.execute(f'SELECT * FROM "{table}" ORDER BY {order}').fetchall()


def _snapshot_channel_id(conn, guild_id: int):
    if not _table_exists(conn, "market_report_channels"):
        return None
    row = conn.execute(
        "SELECT channel_id FROM market_report_channels WHERE guild_id=? LIMIT 1",
        (int(guild_id),),
    ).fetchone()
    return int(row["channel_id"]) if row else None


def _collect_snapshot_summary(runtime, guild_id: int, path: Path):
    previous = _previous_backup(runtime, guild_id, path)
    start_dt = backups._backup_datetime(previous) if previous else None
    start_sql = _utc_sql(start_dt)
    end_dt = backups._backup_datetime(path)

    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    try:
        channel_id = _snapshot_channel_id(conn, guild_id)

        transfer_cols = _columns(conn, "transfers")
        transfer_time = _latest_expr(
            transfer_cols,
            [
                "pes_loaded_at",
                "reverted_at",
                "rejected_at",
                "applied_at",
                "approved_at",
                "created_at",
            ],
        )
        transfers = _window_rows(conn, "transfers", transfer_time, start_sql)

        release_cols = _columns(conn, "player_releases")
        release_time = _latest_expr(release_cols, ["pes_loaded_at", "created_at"])
        releases = _window_rows(conn, "player_releases", release_time, start_sql)

        clause_cols = _columns(conn, "clause_requests")
        clause_time = _latest_expr(clause_cols, ["decided_at", "requested_at"])
        clauses = _window_rows(conn, "clause_requests", clause_time, start_sql)

        loan_cols = _columns(conn, "loans")
        loan_time = _latest_expr(loan_cols, ["resolved_at", "created_at"])
        loans = _window_rows(conn, "loans", loan_time, start_sql)

        treasury_cols = _columns(conn, "treasury_transactions")
        treasury_time = "created_at" if "created_at" in treasury_cols else None
        treasury = _window_rows(conn, "treasury_transactions", treasury_time, start_sql)

        adjustment_cols = _columns(conn, "finance_adjustments")
        adjustment_time = "created_at" if "created_at" in adjustment_cols else None
        adjustments = _window_rows(conn, "finance_adjustments", adjustment_time, start_sql)

        option_cols = _columns(conn, "loan_option_payments")
        option_time = "created_at" if "created_at" in option_cols else None
        option_payments = _window_rows(conn, "loan_option_payments", option_time, start_sql)

        market_cols = _columns(conn, "market_state_history")
        market_time = "changed_at" if "changed_at" in market_cols else None
        market_changes = _window_rows(conn, "market_state_history", market_time, start_sql)

        return {
            "channel_id": channel_id,
            "previous": previous,
            "start_dt": start_dt,
            "end_dt": end_dt,
            "transfers": transfers,
            "releases": releases,
            "clauses": clauses,
            "loans": loans,
            "treasury": treasury,
            "adjustments": adjustments,
            "option_payments": option_payments,
            "market_changes": market_changes,
        }
    finally:
        conn.close()


def _transfer_lines(rows):
    lines = []
    for row in rows:
        op = str(row["operation_type"] or "TRANSFERENCIA") if "operation_type" in row.keys() else "TRANSFERENCIA"
        status = str(row["status"] or "—") if "status" in row.keys() else "—"
        amount = _money(row["amount"]) if "amount" in row.keys() else "—"
        lines.append(
            f"#{row['id']} | {op} | {row['player']} | {row['seller']} -> {row['buyer']} | {amount} | {status}"
        )
    return lines


def _release_lines(rows):
    lines = []
    for row in rows:
        cost = _money(row["release_cost"]) if "release_cost" in row.keys() else "—"
        lines.append(
            f"#{row['id']} | LIBERACIÓN | {row['player']} | {row['from_club']} -> Jugador Libre | costo {cost}"
        )
    return lines


def _clause_lines(rows):
    lines = []
    for row in rows:
        lines.append(
            f"#{row['id']} | CLAUSULAZO | {row['player']} | {row['seller_club']} -> {row['buyer_club']} | "
            f"{_money(row['amount'])} | {row['status']}"
        )
    return lines


def _loan_lines(rows):
    lines = []
    for row in rows:
        remaining = row["remaining_seasons"] if "remaining_seasons" in row.keys() else "—"
        lines.append(
            f"#{row['id']} | PRÉSTAMO | {row['player']} | {row['owner_club']} -> {row['borrower_club']} | "
            f"estado {row['status']} | temporadas restantes {remaining}"
        )
    return lines


def _treasury_lines(treasury, adjustments, option_payments):
    lines = []
    for row in treasury:
        direction = str(row["direction"] or "MOV") if "direction" in row.keys() else "MOV"
        category = str(row["category"] or "MOVIMIENTO") if "category" in row.keys() else "MOVIMIENTO"
        club = str(row["club"] or "—") if "club" in row.keys() else "—"
        player = f" | {row['player']}" if "player" in row.keys() and row["player"] else ""
        lines.append(f"TES#{row['id']} | {club} | {direction} {category} | {_money(row['amount'])}{player}")
    for row in adjustments:
        delta = int(row["delta"] or 0) if "delta" in row.keys() else 0
        club = str(row["club"] or "—") if "club" in row.keys() else "—"
        sign = "+" if delta >= 0 else "-"
        lines.append(f"AJUSTE#{row['id']} | {club} | {sign}{_money(abs(delta))} | ajuste Staff")
    for row in option_payments:
        lines.append(
            f"OPCIÓN#{row['id']} | {row['buyer_club']} -> {row['seller_club']} | {_money(row['amount'])} | préstamo #{row['loan_id']}"
        )
    return lines


def _market_lines(rows):
    lines = []
    for row in rows:
        state = "ABIERTO" if int(row["is_open"] or 0) else "CERRADO"
        lines.append(f"MERCADO | {state} | {_fmt_dt(row['changed_at'])}")
    return lines


def _short(lines, limit=6):
    if not lines:
        return "Sin movimientos."
    visible = lines[:limit]
    text = "\n".join(f"• {line}" for line in visible)
    if len(lines) > limit:
        text += f"\n… y {len(lines) - limit} más (ver TXT adjunto)."
    return text[:1024]


def _build_digest(runtime, guild_id: int, path: Path, data):
    transfer_lines = _transfer_lines(data["transfers"])
    release_lines = _release_lines(data["releases"])
    clause_lines = _clause_lines(data["clauses"])
    loan_lines = _loan_lines(data["loans"])
    treasury_lines = _treasury_lines(
        data["treasury"], data["adjustments"], data["option_payments"]
    )
    market_lines = _market_lines(data["market_changes"])

    all_lines = (
        transfer_lines
        + release_lines
        + clause_lines
        + loan_lines
        + treasury_lines
        + market_lines
    )

    previous = data["previous"]
    start_text = backups._format_backup(previous) if previous else "inicio del registro"
    end_text = backups._format_backup(path)
    kind = backups._backup_kind(path)

    embed = discord.Embed(
        title="💾 BACKUP COMPLETADO • RESUMEN STAFF",
        description=(
            f"Se guardó una copia **{kind}** de este servidor.\n"
            "Este resumen muestra los movimientos incluidos desde el backup anterior."
        ),
        color=discord.Color.blurple(),
    )
    embed.add_field(
        name="🕐 Período respaldado",
        value=f"**Desde:** {start_text}\n**Hasta:** {end_text}",
        inline=False,
    )
    embed.add_field(
        name="📦 Copia",
        value=f"{kind} • {backups._size_text(path)}",
        inline=False,
    )

    if not all_lines:
        embed.add_field(
            name="✅ Movimientos",
            value="No hubo movimientos nuevos desde el backup anterior. La copia igualmente fue guardada correctamente.",
            inline=False,
        )
    else:
        embed.add_field(
            name=f"🔁 Operaciones ({len(transfer_lines)})",
            value=_short(transfer_lines),
            inline=False,
        )
        if release_lines:
            embed.add_field(
                name=f"🆓 Liberaciones ({len(release_lines)})",
                value=_short(release_lines),
                inline=False,
            )
        if clause_lines:
            embed.add_field(
                name=f"💥 Clausulazos ({len(clause_lines)})",
                value=_short(clause_lines),
                inline=False,
            )
        if loan_lines:
            embed.add_field(
                name=f"🤝 Préstamos ({len(loan_lines)})",
                value=_short(loan_lines),
                inline=False,
            )
        if treasury_lines:
            embed.add_field(
                name=f"💰 Tesorería ({len(treasury_lines)})",
                value=_short(treasury_lines),
                inline=False,
            )
        if market_lines:
            embed.add_field(
                name=f"🔐 Estado de mercado ({len(market_lines)})",
                value=_short(market_lines),
                inline=False,
            )

    embed.set_footer(text="AJAP Transfer Market • backup verificado • canal Staff")

    text = [
        "AJAP TRANSFER MARKET — RESUMEN DE BACKUP",
        "========================================",
        f"Servidor Discord: {guild_id}",
        f"Backup: {path.name}",
        f"Tipo: {kind}",
        f"Período: {start_text} -> {end_text}",
        f"Tamaño: {backups._size_text(path)}",
        "",
    ]
    sections = [
        ("OPERACIONES", transfer_lines),
        ("LIBERACIONES", release_lines),
        ("CLAUSULAZOS", clause_lines),
        ("PRÉSTAMOS", loan_lines),
        ("TESORERÍA", treasury_lines),
        ("CAMBIOS DE ESTADO DEL MERCADO", market_lines),
    ]
    for title, lines in sections:
        text += [title, "-" * len(title)]
        text += lines or ["Sin movimientos."]
        text.append("")
    text += [
        f"Total de registros resumidos: {len(all_lines)}",
        "Fin del resumen.",
    ]
    return embed, "\n".join(text), len(all_lines)


def _create_with_staff_summary(runtime, guild_id: int, kind="daily", *, prune=True):
    path = _ORIGINAL_CREATE(runtime, guild_id, kind, prune=prune)
    try:
        _SUMMARY_QUEUE.put_nowait((int(guild_id), str(path)))
    except Exception as exc:
        print(f"WARNING AJAP BACKUP STAFF: no pude encolar resumen: {exc}")
    return path


async def _resolve_staff_channel(guild_id: int, channel_id: int):
    if BOT is None or not channel_id:
        return None
    guild = BOT.get_guild(int(guild_id))
    if guild is None:
        return None
    channel = guild.get_channel(int(channel_id))
    if channel is None:
        try:
            channel = await BOT.fetch_channel(int(channel_id))
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            return None
    return channel if hasattr(channel, "send") else None


async def _send_summary(guild_id: int, path_text: str):
    runtime = APP
    if runtime is None:
        return
    path = Path(path_text)
    if not path.exists():
        print(f"WARNING AJAP BACKUP STAFF: backup desapareció antes del resumen: {path.name}")
        return

    try:
        data = await asyncio.to_thread(_collect_snapshot_summary, runtime, guild_id, path)
        channel = await _resolve_staff_channel(guild_id, data["channel_id"])
        if channel is None:
            print(
                f"AJAP BACKUP STAFF: guild={guild_id} sin /canal_movimientos configurado; "
                f"resumen de {path.name} no enviado"
            )
            return
        embed, text, count = await asyncio.to_thread(_build_digest, runtime, guild_id, path, data)
        payload = text.encode("utf-8-sig")
        filename = f"AJAP_backup_resumen_{path.stem}.txt"
        await channel.send(
            embed=embed,
            file=discord.File(io.BytesIO(payload), filename=filename),
            allowed_mentions=discord.AllowedMentions.none(),
        )
        print(
            f"AJAP BACKUP STAFF enviado: guild={guild_id} • backup={path.name} • movimientos={count}"
        )
    except Exception as exc:
        # El resumen nunca debe invalidar un backup que ya fue creado correctamente.
        print(
            "WARNING AJAP BACKUP STAFF: "
            f"guild={guild_id} backup={path.name} {type(exc).__name__}: {exc}"
        )


async def _summary_loop():
    while True:
        try:
            guild_id, path = await asyncio.to_thread(_SUMMARY_QUEUE.get)
            await _send_summary(int(guild_id), str(path))
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            print(f"WARNING AJAP BACKUP STAFF LOOP: {type(exc).__name__}: {exc}")


async def _start_summary_loop():
    global _SUMMARY_TASK
    if _SUMMARY_TASK is None or _SUMMARY_TASK.done():
        _SUMMARY_TASK = asyncio.create_task(
            _summary_loop(), name="ajap-backup-staff-summary"
        )


def apply_backup_staff_summary_patch(runtime, bot):
    global APP, BOT
    APP = runtime
    BOT = bot
    if getattr(runtime, "_ajap_backup_staff_summary_patch", False):
        return
    bot.add_listener(_start_summary_loop, "on_ready")
    runtime._ajap_backup_staff_summary_patch = True
    print(
        "AJAP backup Staff activo: cada copia envía resumen + TXT a /canal_movimientos"
    )


# Wrap the final reliability-protected creator. Every automatic, manual and
# pre-restore snapshot passes through this function.
backups._create_backup_sync = _create_with_staff_summary


_original_apply_guild_isolation_patch = guild_isolation.apply_guild_isolation_patch


def _apply_guild_isolation_then_backup_summary(runtime, bot):
    _original_apply_guild_isolation_patch(runtime, bot)
    apply_backup_staff_summary_patch(runtime, bot)


if not getattr(
    guild_isolation.apply_guild_isolation_patch,
    "_ajap_backup_staff_summary_wrapped",
    False,
):
    _apply_guild_isolation_then_backup_summary._ajap_backup_staff_summary_wrapped = True
    guild_isolation.apply_guild_isolation_patch = _apply_guild_isolation_then_backup_summary
