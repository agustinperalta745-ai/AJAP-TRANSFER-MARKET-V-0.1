import io
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import discord

STAFF_ROLE_NAMES = {"staff"}
LOCAL_TZ = ZoneInfo("America/Argentina/Buenos_Aires")


def ensure_schema(runtime):
    with runtime.db() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS market_cycles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                season_id INTEGER,
                opened_by INTEGER,
                opened_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                closed_by INTEGER,
                closed_at DATETIME,
                report_sent_at DATETIME,
                report_recipient_count INTEGER NOT NULL DEFAULT 0
            )
            """
        )


def active_cycle(runtime):
    with runtime.db() as conn:
        return conn.execute(
            "SELECT * FROM market_cycles WHERE closed_at IS NULL ORDER BY id DESC LIMIT 1"
        ).fetchone()


def latest_closed_cycle(runtime):
    with runtime.db() as conn:
        return conn.execute(
            "SELECT * FROM market_cycles WHERE closed_at IS NOT NULL ORDER BY id DESC LIMIT 1"
        ).fetchone()


def start_cycle(runtime, user_id, opened_at=None):
    current = active_cycle(runtime)
    if current:
        return current
    season = runtime.temporada_activa()
    with runtime.db() as conn:
        if opened_at:
            cur = conn.execute(
                "INSERT INTO market_cycles (season_id, opened_by, opened_at) VALUES (?, ?, ?)",
                (season["id"] if season else None, user_id, opened_at),
            )
        else:
            cur = conn.execute(
                "INSERT INTO market_cycles (season_id, opened_by) VALUES (?, ?)",
                (season["id"] if season else None, user_id),
            )
        return conn.execute("SELECT * FROM market_cycles WHERE id = ?", (cur.lastrowid,)).fetchone()


def recover_cycle(runtime, user_id):
    current = active_cycle(runtime)
    if current:
        return current
    with runtime.db() as conn:
        state = conn.execute("SELECT updated_at FROM market_state WHERE id = 1").fetchone()
    return start_cycle(runtime, user_id, state["updated_at"] if state else None)


def close_cycle(runtime, cycle_id, user_id):
    with runtime.db() as conn:
        conn.execute(
            "UPDATE market_cycles SET closed_by = ?, closed_at = CURRENT_TIMESTAMP WHERE id = ? AND closed_at IS NULL",
            (user_id, cycle_id),
        )
        return conn.execute("SELECT * FROM market_cycles WHERE id = ?", (cycle_id,)).fetchone()


def cycle_rows(runtime, cycle):
    with runtime.db() as conn:
        return conn.execute(
            """
            SELECT t.*, s.name AS season_name, rp.position AS player_position,
                   p.price AS listed_price, p.detail AS publication_detail
            FROM transfers t
            LEFT JOIN seasons s ON s.id = t.season_id
            LEFT JOIN roster_players rp ON rp.id = t.player_id
            LEFT JOIN offers o ON o.id = t.offer_id
            LEFT JOIN publications p ON p.id = o.publication_id
            WHERE t.created_at >= ? AND t.created_at <= ?
            ORDER BY t.id ASC
            """,
            (cycle["opened_at"], cycle["closed_at"]),
        ).fetchall()


def local_time(value):
    if not value:
        return "—"
    raw = str(value).strip()
    try:
        dt = datetime.strptime(raw[:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        return dt.astimezone(LOCAL_TZ).strftime("%d/%m/%Y %H:%M")
    except ValueError:
        return raw


def deal_mode(runtime, row):
    op_type = (row["operation_type"] or "").strip().upper()
    if op_type in {"INTERCAMBIO", "JUGADOR LIBRE", "AJUSTE ADMIN"}:
        return "NO APLICA"
    listed = runtime.price_number(row["listed_price"] or "") if row["listed_price"] else None
    final = runtime.price_number(row["amount"] or "") if row["amount"] else None
    if listed is None or final is None:
        return "REVISAR"
    return "FIJA" if listed == final else "NEGOCIADA"


def status_action(status):
    return {
        "RECHAZADA_ADMIN": "NO APLICAR EN PES — operación anulada",
        "APLICADA": "VERIFICAR EN PES — ya figura aplicada en el bot",
        "APROBADA": "APLICAR EN PES",
        "PENDIENTE_ADMIN": "REVISAR/APROBAR Y LUEGO APLICAR EN PES",
    }.get(status, "REVISAR ESTADO ANTES DE APLICAR")


def safe_name(value):
    return "".join(c if c.isalnum() or c in "-_" else "_" for c in value).strip("_") or "mercado"


def build_report(runtime, cycle):
    rows = cycle_rows(runtime, cycle)
    with runtime.db() as conn:
        season = conn.execute("SELECT name FROM seasons WHERE id = ?", (cycle["season_id"],)).fetchone() if cycle["season_id"] else None
    season_name = season["name"] if season else "Sin temporada"
    valid = [r for r in rows if r["status"] != "RECHAZADA_ADMIN"]
    rejected = [r for r in rows if r["status"] == "RECHAZADA_ADMIN"]

    lines = [
        "AJAP TRANSFER MARKET — INFORME DE CIERRE",
        "========================================",
        f"Temporada: {season_name}",
        f"Ventana de mercado: #{cycle['id']}",
        f"Apertura: {local_time(cycle['opened_at'])} (Argentina)",
        f"Cierre: {local_time(cycle['closed_at'])} (Argentina)",
        f"Movimientos registrados: {len(rows)}",
        f"Movimientos vigentes: {len(valid)}",
        f"Anulados/rechazados: {len(rejected)}",
        "",
        "CRITERIO",
        "--------",
        "FIJA = monto final igual al precio publicado.",
        "NEGOCIADA = monto final distinto al precio publicado.",
        "RECHAZADA_ADMIN = NO aplicar en PES.",
        "",
    ]

    if not rows:
        lines += ["No hubo movimientos durante esta ventana de mercado.", ""]

    for i, row in enumerate(rows, 1):
        code = runtime.player_code(row["player_id"]) if row["player_id"] else "SIN-ID"
        mode = deal_mode(runtime, row)
        notes = row["notes"] or row["publication_detail"] or "Sin condiciones adicionales"
        lines += [
            f"MOVIMIENTO {i:02d} — OPERACIÓN #{row['id']}",
            "----------------------------------------",
            f"Jugador: {row['player']}",
            f"ID AJAP: {code}",
            f"Posición: {row['player_position'] or '—'}",
            f"Club origen: {row['seller']}",
            f"Club destino: {row['buyer']}",
            f"Tipo de operación: {row['operation_type']}",
            f"Modalidad: {mode}",
            f"Precio publicado: {row['listed_price'] or '—'}",
            f"Monto final: {row['amount']}",
            f"Condiciones/notas: {notes}",
            f"Estado administrativo: {row['status']}",
            f"Oferta vinculada: #{row['offer_id']}" if row["offer_id"] else "Oferta vinculada: —",
            f"Acuerdo registrado: {local_time(row['created_at'])} (Argentina)",
            f"ACCIÓN STAFF: {status_action(row['status'])}",
            f"ACCIÓN PES: {row['seller']} -> {row['buyer']} | {row['player']}",
            "",
        ]

    if valid:
        lines += ["RESUMEN RÁPIDO", "--------------"]
        for row in valid:
            lines.append(
                f"#{row['id']} | {row['player']} | {row['seller']} -> {row['buyer']} | "
                f"{row['operation_type']} | {deal_mode(runtime, row)} | FINAL {row['amount']} | {row['status']}"
            )
        lines.append("")

    if rejected:
        lines += ["ANULADAS — NO APLICAR", "---------------------"]
        for row in rejected:
            lines.append(f"#{row['id']} | {row['player']} | {row['seller']} -> {row['buyer']}")
        lines.append("")

    lines += ["Fin del informe.", "Generado automáticamente por AJAP Transfer Market v0.1."]
    text = "\n".join(lines)
    filename = f"AJAP_cierre_{safe_name(season_name)}_mercado_{cycle['id']}.txt"
    return text, filename, rows, season_name


def has_staff_role(member):
    return isinstance(member, discord.Member) and any(
        (role.name or "").strip().casefold() in STAFF_ROLE_NAMES for role in member.roles
    )


def is_staff_or_admin(runtime, interaction):
    return runtime.es_admin(interaction) or has_staff_role(interaction.user)


def staff_members(guild):
    found = {}
    for role in guild.roles:
        if (role.name or "").strip().casefold() in STAFF_ROLE_NAMES:
            for member in role.members:
                if not member.bot:
                    found[member.id] = member
    return list(found.values())


async def deliver(runtime, interaction, text, filename):
    members = staff_members(interaction.guild) if interaction.guild else []
    if isinstance(interaction.user, discord.Member) and not interaction.user.bot:
        if is_staff_or_admin(runtime, interaction) and all(m.id != interaction.user.id for m in members):
            members.append(interaction.user)
    delivered = 0
    failures = 0
    payload = text.encode("utf-8-sig")
    for member in members:
        try:
            await member.send(
                embed=discord.Embed(
                    title="🔒 Mercado cerrado • Informe Staff",
                    description="Adjunto: movimientos, origen/destino, tipo, monto final, modalidad fija/negociada y estado para aplicar en PES.",
                ),
                file=discord.File(io.BytesIO(payload), filename=filename),
            )
            delivered += 1
        except Exception:
            failures += 1
    return delivered, len(members), failures


def apply_market_close_report_patch(runtime, bot):
    ensure_schema(runtime)

    class AdminView(discord.ui.View):
        def __init__(self):
            super().__init__(timeout=180)

        @discord.ui.button(label="Abrir mercado", emoji="🟢", style=discord.ButtonStyle.success, row=0)
        async def abrir(self, interaction, button):
            if not runtime.es_admin(interaction):
                await interaction.response.send_message("⛔ Solo admins.", ephemeral=True)
                return
            if runtime.mercado_abierto():
                cycle = active_cycle(runtime) or recover_cycle(runtime, interaction.user.id)
                await interaction.response.send_message(f"🟢 El mercado ya estaba abierto. Ventana **#{cycle['id']}**.", ephemeral=True)
                return
            runtime.cambiar_estado_mercado(True, interaction.user.id)
            cycle = start_cycle(runtime, interaction.user.id)
            await interaction.response.send_message(f"🟢 Mercado abierto. Ventana **#{cycle['id']}** iniciada.", ephemeral=True)

        @discord.ui.button(label="Cerrar mercado", emoji="🔒", style=discord.ButtonStyle.danger, row=0)
        async def cerrar(self, interaction, button):
            if not runtime.es_admin(interaction):
                await interaction.response.send_message("⛔ Solo admins.", ephemeral=True)
                return
            if not runtime.mercado_abierto():
                latest = latest_closed_cycle(runtime)
                extra = f" Último cierre: **#{latest['id']}**." if latest else ""
                await interaction.response.send_message(f"🔒 El mercado ya estaba cerrado.{extra}", ephemeral=True)
                return
            await interaction.response.defer(ephemeral=True, thinking=True)
            cycle = active_cycle(runtime) or recover_cycle(runtime, interaction.user.id)
            runtime.cambiar_estado_mercado(False, interaction.user.id)
            cycle = close_cycle(runtime, cycle["id"], interaction.user.id)
            text, filename, rows, season_name = build_report(runtime, cycle)
            delivered, detected, failures = await deliver(runtime, interaction, text, filename)
            with runtime.db() as conn:
                conn.execute(
                    "UPDATE market_cycles SET report_sent_at = CURRENT_TIMESTAMP, report_recipient_count = ? WHERE id = ?",
                    (delivered, cycle["id"]),
                )
            msg = (
                f"🔒 **Mercado cerrado.** Ventana **#{cycle['id']}** • **{season_name}**.\n"
                f"📋 Movimientos: **{len(rows)}**.\n"
                f"📨 TXT enviado por DM a **{delivered}/{detected}** Staff detectados."
            )
            if failures:
                msg += "\n⚠️ Algún Staff tiene los MD cerrados o Discord rechazó la entrega."
            msg += "\n💾 Se puede recuperar con **/reporte_cierre**."
            await interaction.followup.send(
                msg,
                file=discord.File(io.BytesIO(text.encode("utf-8-sig")), filename=filename),
                ephemeral=True,
            )

        @discord.ui.button(label="Operaciones pendientes", emoji="🛠️", style=discord.ButtonStyle.primary, row=0)
        async def ops(self, interaction, button):
            if not runtime.es_admin(interaction):
                await interaction.response.send_message("⛔ Solo admins.", ephemeral=True)
                return
            ops = runtime.operaciones_pendientes(25)
            await interaction.response.send_message(embed=runtime.operaciones_pendientes_embed(), view=runtime.OperacionesAdminListView(ops), ephemeral=True)

        @discord.ui.button(label="Agregar jugador", emoji="➕", style=discord.ButtonStyle.primary, row=1)
        async def agregar(self, interaction, button):
            if not runtime.es_admin(interaction):
                await interaction.response.send_message("⛔ Solo admins.", ephemeral=True)
                return
            await interaction.response.send_modal(runtime.AdminAgregarModal())

        @discord.ui.button(label="Mover manual", emoji="🔁", style=discord.ButtonStyle.primary, row=1)
        async def mover(self, interaction, button):
            if not runtime.es_admin(interaction):
                await interaction.response.send_message("⛔ Solo admins.", ephemeral=True)
                return
            await interaction.response.send_modal(runtime.AdminMoverModal())

        @discord.ui.button(label="Quitar jugador", emoji="🗑️", style=discord.ButtonStyle.secondary, row=1)
        async def quitar(self, interaction, button):
            if not runtime.es_admin(interaction):
                await interaction.response.send_message("⛔ Solo admins.", ephemeral=True)
                return
            await interaction.response.send_modal(runtime.AdminQuitarModal())

        @discord.ui.button(label="Ver plantel", emoji="📋", style=discord.ButtonStyle.secondary, row=2)
        async def ver_plantel(self, interaction, button):
            if not runtime.es_admin(interaction):
                await interaction.response.send_message("⛔ Solo admins.", ephemeral=True)
                return
            await interaction.response.send_modal(runtime.AdminPlantelModal())

        @discord.ui.button(label="Cambiar temporada", emoji="🗓️", style=discord.ButtonStyle.secondary, row=2)
        async def temporada(self, interaction, button):
            if not runtime.es_admin(interaction):
                await interaction.response.send_message("⛔ Solo admins.", ephemeral=True)
                return
            await interaction.response.send_modal(runtime.AdminTemporadaModal())

    runtime.AdminView = AdminView

    if bot.tree.get_command("reporte_cierre") is None:
        @bot.tree.command(name="reporte_cierre", description="Descarga el TXT del último cierre de mercado")
        async def reporte_cierre(interaction: discord.Interaction):
            if not is_staff_or_admin(runtime, interaction):
                await interaction.response.send_message("⛔ Solo Staff/administradores.", ephemeral=True)
                return
            cycle = latest_closed_cycle(runtime)
            if not cycle:
                await interaction.response.send_message("⚠️ Todavía no hay un cierre registrado.", ephemeral=True)
                return
            text, filename, rows, season_name = build_report(runtime, cycle)
            await interaction.response.send_message(
                content=f"📄 Cierre **#{cycle['id']}** • **{season_name}** • {len(rows)} movimiento(s).",
                file=discord.File(io.BytesIO(text.encode("utf-8-sig")), filename=filename),
                ephemeral=True,
            )

    print("AJAP patch activo: informe TXT automático al cerrar mercado + /reporte_cierre")
