"""Canal de movimientos Staff/PES para AJAP.

Los administradores configuran el destino con /canal_movimientos. Cada operación
que llega a administración obtiene su propia tarjeta persistente en ese canal:
roja si fue rechazada, amarilla si quedó aplicada en AJAP pero todavía falta
cargarla manualmente en PES, y verde una vez que Staff confirma "Cargado en PES".

La tarjeta nunca pierde los datos del negocio. Conserva tipo, origen/destino,
monto, intercambio/jugador ofrecido, condiciones y fechas reales (Argentina).
El cierre de mercado sigue publicando el TXT/resumen general como respaldo.
"""

import io
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import discord
import market_close_report_patch as reports

APP = None
LOCAL_TZ = ZoneInfo("America/Argentina/Buenos_Aires")


# ---------------------------------------------------------------------------
# Persistencia / configuración
# ---------------------------------------------------------------------------

def ensure_schema():
    with APP.db() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS market_report_channels (
                guild_id INTEGER PRIMARY KEY,
                channel_id INTEGER NOT NULL,
                configured_by INTEGER,
                configured_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        APP.add_column_if_missing(conn, "transfers", "pes_loaded_by", "INTEGER")
        APP.add_column_if_missing(conn, "transfers", "pes_loaded_at", "DATETIME")
        APP.add_column_if_missing(conn, "transfers", "pes_report_message_id", "INTEGER")
        APP.add_column_if_missing(conn, "transfers", "pes_report_channel_id", "INTEGER")


def set_report_channel(guild_id: int, channel_id: int, user_id: int):
    with APP.db() as conn:
        conn.execute(
            """
            INSERT INTO market_report_channels
            (guild_id, channel_id, configured_by, configured_at, updated_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            ON CONFLICT(guild_id) DO UPDATE SET
                channel_id = excluded.channel_id,
                configured_by = excluded.configured_by,
                updated_at = CURRENT_TIMESTAMP
            """,
            (guild_id, channel_id, user_id),
        )


def get_report_channel_id(guild_id: int):
    with APP.db() as conn:
        row = conn.execute(
            "SELECT channel_id FROM market_report_channels WHERE guild_id = ?",
            (guild_id,),
        ).fetchone()
    return int(row["channel_id"]) if row else None


def _has(row, key):
    return row is not None and key in row.keys()


def _transfer(transfer_id: int):
    with APP.db() as conn:
        return conn.execute(
            """
            SELECT t.*, o.offered_player, o.offer_kind, o.message AS offer_message,
                   p.price AS listed_price, p.detail AS publication_detail
            FROM transfers t
            LEFT JOIN offers o ON o.id = t.offer_id
            LEFT JOIN publications p ON p.id = o.publication_id
            WHERE t.id = ?
            LIMIT 1
            """,
            (int(transfer_id),),
        ).fetchone()


def _configured_channel_from_guild(guild):
    if guild is None:
        return None
    channel_id = get_report_channel_id(guild.id)
    if not channel_id:
        return None
    return guild.get_channel(channel_id)


async def resolve_channel(interaction: discord.Interaction):
    if not interaction.guild:
        return None
    channel_id = get_report_channel_id(interaction.guild.id)
    if not channel_id:
        return None
    channel = interaction.guild.get_channel(channel_id)
    if channel is None:
        try:
            channel = await APP.bot.fetch_channel(channel_id)
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            return None
    return channel if hasattr(channel, "send") else None


def _fmt_time(value):
    if not value:
        return "—"
    raw = str(value).strip()
    try:
        dt = datetime.strptime(raw[:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        return dt.astimezone(LOCAL_TZ).strftime("%d/%m/%Y • %H:%M")
    except ValueError:
        return raw


def _fmt_user(user_id):
    return f"<@{int(user_id)}>" if user_id else "—"


def _status_key(row):
    status = (row["status"] or "").strip().upper()
    if status == "RECHAZADA_ADMIN":
        return "REJECTED"
    if _has(row, "pes_loaded_at") and row["pes_loaded_at"]:
        return "LOADED"
    # Solo las operaciones aplicadas al plantel AJAP están listas para replicarse en PES.
    if status == "APLICADA":
        return "PENDING_PES"
    return "ADMIN_PENDING"


def _status_style(row):
    key = _status_key(row)
    if key == "REJECTED":
        return (
            discord.Color.red(),
            "🔴 OPERACIÓN RECHAZADA POR ADMINISTRACIÓN",
            "⛔ NO CARGAR EN PES",
        )
    if key == "LOADED":
        return (
            discord.Color.green(),
            "🟢 OPERACIÓN CARGADA EN PES",
            "✅ CARGADO EN PES",
        )
    if key == "PENDING_PES":
        return (
            discord.Color.gold(),
            "🟡 OPERACIÓN PENDIENTE DE CARGAR EN PES",
            "⏳ PENDIENTE DE CARGAR EN PES",
        )
    return (
        discord.Color.gold(),
        "🟡 OPERACIÓN EN REVISIÓN ADMINISTRATIVA",
        "🛠️ PENDIENTE DE RESOLUCIÓN ADMIN",
    )


def _operation_details(row):
    details = []
    operation_type = (row["operation_type"] or "TRANSFERENCIA").strip()
    details.append(f"🔄 **Tipo:** {operation_type}")
    details.append(f"💰 **Monto final:** {row['amount'] or '$0'}")

    if _has(row, "offered_player") and row["offered_player"]:
        details.append(f"🔁 **Jugador incluido en el acuerdo:** {row['offered_player']}")

    notes = None
    for key in ("notes", "offer_message", "publication_detail"):
        if _has(row, key) and row[key] and str(row[key]).strip():
            value = str(row[key]).strip()
            if value.casefold() not in {"sin condiciones adicionales", "sin observaciones"}:
                notes = value
                break
    if notes:
        details.append(f"📝 **Condiciones:** {notes}")

    if _has(row, "listed_price") and row["listed_price"]:
        details.append(f"🏷️ **Precio publicado:** {row['listed_price']}")

    return "\n".join(details)


def movement_embed(row):
    color, title, status_text = _status_style(row)
    embed = discord.Embed(
        title=f"{title} • #{row['id']}",
        color=color,
    )
    embed.add_field(name="⚽ Jugador", value=f"**{row['player']}**", inline=False)
    embed.add_field(name="⬅️ Club de origen", value=row["seller"] or "—", inline=True)
    embed.add_field(name="➡️ Club de destino", value=row["buyer"] or "—", inline=True)
    embed.add_field(name="📋 Datos de la operación", value=_operation_details(row), inline=False)

    # "Fecha de operación" = momento real en que quedó definitiva/aplicada en AJAP.
    definitive_at = row["applied_at"] if _has(row, "applied_at") and row["applied_at"] else row["approved_at"]
    embed.add_field(
        name="📅 Operación definitiva",
        value=(
            f"**{_fmt_time(definitive_at)} (Argentina)**\n"
            f"Aprobada por: {_fmt_user(row['approved_by'] if _has(row, 'approved_by') else None)}"
        ),
        inline=False,
    )

    if _status_key(row) == "REJECTED":
        embed.add_field(
            name="⛔ Rechazo administrativo",
            value=(
                f"**{_fmt_time(row['rejected_at'] if _has(row, 'rejected_at') else None)} (Argentina)**\n"
                f"Rechazada por: {_fmt_user(row['rejected_by'] if _has(row, 'rejected_by') else None)}"
            ),
            inline=False,
        )
    elif _status_key(row) == "LOADED":
        embed.add_field(
            name="🎮 Carga en PES",
            value=(
                f"**{_fmt_time(row['pes_loaded_at'])} (Argentina)**\n"
                f"Cargado por: {_fmt_user(row['pes_loaded_by'])}"
            ),
            inline=False,
        )

    embed.add_field(name="Estado", value=status_text, inline=False)
    embed.set_footer(text="AJAP Transfer Market • control Staff/PES")
    return embed


# ---------------------------------------------------------------------------
# Botón persistente "Cargado en PES"
# ---------------------------------------------------------------------------
class PesLoadedView(discord.ui.View):
    def __init__(self, transfer_id: int):
        super().__init__(timeout=None)
        self.transfer_id = int(transfer_id)
        row = _transfer(self.transfer_id) if APP is not None else None
        loaded = bool(row and _status_key(row) == "LOADED")
        unavailable = bool(row and _status_key(row) in {"REJECTED", "ADMIN_PENDING"})
        button = discord.ui.Button(
            label="Cargado en PES" if not loaded else "Cargado en PES",
            emoji="✅" if loaded else "🎮",
            style=discord.ButtonStyle.success if loaded else discord.ButtonStyle.primary,
            custom_id=f"ajap:pes-loaded:{self.transfer_id}",
            disabled=loaded or unavailable,
        )
        button.callback = self._mark_loaded
        self.add_item(button)

    async def _mark_loaded(self, interaction: discord.Interaction):
        if not APP.es_admin(interaction):
            await interaction.response.send_message(
                "⛔ Solo administradores pueden marcar una operación como cargada en PES.",
                ephemeral=True,
            )
            return

        row = _transfer(self.transfer_id)
        if not row:
            await interaction.response.send_message("⚠️ Operación no encontrada.", ephemeral=True)
            return
        if _status_key(row) == "REJECTED":
            await interaction.response.send_message(
                "⛔ Esta operación fue rechazada y no debe cargarse en PES.", ephemeral=True
            )
            return
        if (row["status"] or "").upper() != "APLICADA":
            await interaction.response.send_message(
                "⚠️ La operación todavía no quedó definitiva en AJAP.", ephemeral=True
            )
            return
        if _status_key(row) == "LOADED":
            await interaction.response.send_message(
                "✅ Esta operación ya estaba marcada como cargada en PES.", ephemeral=True
            )
            return

        with APP.db() as conn:
            conn.execute(
                """
                UPDATE transfers
                SET pes_loaded_by = ?, pes_loaded_at = CURRENT_TIMESTAMP
                WHERE id = ? AND pes_loaded_at IS NULL
                """,
                (interaction.user.id, self.transfer_id),
            )

        refreshed = _transfer(self.transfer_id)
        await interaction.response.edit_message(
            embed=movement_embed(refreshed),
            view=PesLoadedView(self.transfer_id),
        )


def _register_persistent_pes_views(runtime):
    with runtime.db() as conn:
        rows = conn.execute(
            """
            SELECT id FROM transfers
            WHERE pes_report_message_id IS NOT NULL
              AND status != 'RECHAZADA_ADMIN'
            ORDER BY id ASC
            """
        ).fetchall()
    count = 0
    for row in rows:
        try:
            runtime.bot.add_view(PesLoadedView(int(row["id"])))
            count += 1
        except ValueError:
            pass
    return count


# ---------------------------------------------------------------------------
# Publicación/actualización de tarjetas por operación
# ---------------------------------------------------------------------------
async def publish_or_refresh_operation(interaction, transfer_id: int):
    row = _transfer(transfer_id)
    if not row or not interaction.guild:
        return False

    channel = await resolve_channel(interaction)
    if channel is None:
        return False

    message_id = row["pes_report_message_id"] if _has(row, "pes_report_message_id") else None
    saved_channel_id = row["pes_report_channel_id"] if _has(row, "pes_report_channel_id") else None

    # Si ya existe la tarjeta, se edita la misma: conserva historial visual y evita duplicados.
    if message_id and saved_channel_id:
        try:
            old_channel = interaction.guild.get_channel(int(saved_channel_id)) or channel
            msg = await old_channel.fetch_message(int(message_id))
            await msg.edit(embed=movement_embed(row), view=PesLoadedView(row["id"]))
            return True
        except (discord.NotFound, discord.Forbidden, discord.HTTPException, AttributeError):
            pass

    try:
        msg = await channel.send(embed=movement_embed(row), view=PesLoadedView(row["id"]))
        with APP.db() as conn:
            conn.execute(
                """
                UPDATE transfers
                SET pes_report_message_id = ?, pes_report_channel_id = ?
                WHERE id = ?
                """,
                (msg.id, channel.id, row["id"]),
            )
        return True
    except (discord.Forbidden, discord.HTTPException) as exc:
        print(f"WARNING AJAP: no se pudo publicar operación #{row['id']} en canal PES: {exc}")
        return False


# ---------------------------------------------------------------------------
# Informe general de cierre (se conserva)
# ---------------------------------------------------------------------------
def fmt_status(status: str) -> str:
    return {
        "PENDIENTE_ADMIN": "🟡 Pendiente admin",
        "APROBADA": "🟡 Aprobada / pendiente de aplicar",
        "APLICADA": "✅ Aplicada",
        "RECHAZADA_ADMIN": "⛔ Rechazada admin",
    }.get(status or "", status or "—")


def movement_lines(rows):
    lines = []
    for row in rows:
        op_type = row["operation_type"] or "TRANSFERENCIA"
        amount = row["amount"] or "$0"
        line = (
            f"**#{row['id']} • {row['player']}**\n"
            f"⬅️ {row['seller']}\n"
            f"➡️ {row['buyer']}\n"
            f"🔄 {op_type} • 💰 {amount} • {fmt_status(row['status'])}"
        )
        lines.append(line)
    return lines


def chunk_lines(lines, max_chars=3600):
    chunks = []
    current = []
    size = 0
    for line in lines:
        addition = len(line) + 2
        if current and size + addition > max_chars:
            chunks.append("\n\n".join(current))
            current = []
            size = 0
        current.append(line)
        size += addition
    if current:
        chunks.append("\n\n".join(current))
    return chunks


async def post_close_report(interaction, text, filename):
    channel = await resolve_channel(interaction)
    if channel is None:
        return False

    cycle = reports.latest_closed_cycle(APP)
    if not cycle:
        return False
    rows = reports.cycle_rows(APP, cycle)
    with APP.db() as conn:
        season = (
            conn.execute("SELECT name FROM seasons WHERE id = ?", (cycle["season_id"],)).fetchone()
            if cycle["season_id"]
            else None
        )
    season_name = season["name"] if season else "Sin temporada"

    loaded = 0
    pending = 0
    rejected = 0
    for row in rows:
        current = _transfer(row["id"])
        key = _status_key(current) if current else "ADMIN_PENDING"
        loaded += key == "LOADED"
        pending += key == "PENDING_PES"
        rejected += key == "REJECTED"

    summary = discord.Embed(
        title="🔒 MERCADO CERRADO • MOVIMIENTOS",
        description=(
            f"**{season_name}** • Ventana **#{cycle['id']}**\n"
            f"📋 Movimientos registrados: **{len(rows)}**\n"
            f"🟢 Cargados en PES: **{loaded}**\n"
            f"🟡 Pendientes de cargar: **{pending}**\n"
            f"🔴 Rechazados: **{rejected}**\n\n"
            "Las tarjetas individuales del canal son el checklist operativo. "
            "El TXT adjunto queda como respaldo completo."
        ),
    )

    try:
        await channel.send(
            embed=summary,
            file=discord.File(io.BytesIO(text.encode("utf-8-sig")), filename=filename),
        )
        return True
    except (discord.Forbidden, discord.HTTPException) as exc:
        print(f"WARNING AJAP: no se pudo publicar cierre en canal configurado: {exc}")
        return False


def apply_market_channel_report_patch(main_module, bot):
    global APP
    APP = main_module
    if getattr(main_module, "_ajap_market_channel_report_patch", False):
        return

    ensure_schema()

    # El cierre general sigue funcionando como hasta ahora.
    base_deliver = reports.deliver

    async def deliver_with_channel(runtime, interaction, text, filename):
        delivered, detected, failures = await base_deliver(runtime, interaction, text, filename)
        channel_ok = await post_close_report(interaction, text, filename)
        print(
            "AJAP cierre de mercado: "
            f"Staff DM {delivered}/{detected} • canal={'OK' if channel_ok else 'NO CONFIGURADO/FAILED'}"
        )
        return delivered, detected, failures

    reports.deliver = deliver_with_channel

    # Enganchamos las acciones del panel administrativo existente. No cambiamos su
    # lógica: solo refrescamos/publicamos la tarjeta después de resolver la acción.
    base_admin_view = getattr(main_module, "OperacionAdminView", None)
    if base_admin_view is not None and not getattr(base_admin_view, "_ajap_pes_report_wrapped", False):
        for method_name in ("aprobar", "aplicar", "rechazar"):
            original = getattr(base_admin_view, method_name, None)
            if original is None:
                continue

            async def wrapped(self, interaction, button, _original=original):
                transfer_id = int(getattr(self, "op_id", getattr(self, "operation_id", 0)) or 0)
                await _original(self, interaction, button)
                if transfer_id:
                    try:
                        await publish_or_refresh_operation(interaction, transfer_id)
                    except Exception as exc:
                        print(f"WARNING AJAP: refresco tarjeta operación #{transfer_id} falló: {exc}")

            setattr(base_admin_view, method_name, wrapped)
        base_admin_view._ajap_pes_report_wrapped = True

    if bot.tree.get_command("canal_movimientos") is None:
        @bot.tree.command(
            name="canal_movimientos",
            description="Usa este canal para recibir y controlar movimientos Staff/PES",
        )
        async def canal_movimientos(interaction: discord.Interaction):
            if not APP.es_admin(interaction):
                await interaction.response.send_message("⛔ Solo administradores.", ephemeral=True)
                return
            if not interaction.guild or not interaction.channel:
                await interaction.response.send_message(
                    "⚠️ Este comando debe usarse dentro de un canal del servidor.",
                    ephemeral=True,
                )
                return
            if not isinstance(interaction.channel, discord.TextChannel):
                await interaction.response.send_message(
                    "⚠️ Elegí un canal de texto normal para los reportes del mercado.",
                    ephemeral=True,
                )
                return

            set_report_channel(interaction.guild.id, interaction.channel.id, interaction.user.id)
            await interaction.response.send_message(
                f"✅ **Canal de movimientos configurado:** {interaction.channel.mention}\n"
                "Desde ahora cada operación tendrá su propia tarjeta: 🔴 rechazada, 🟡 pendiente de PES y 🟢 cargada en PES.",
                ephemeral=True,
            )

    main_module.market_report_channel_id = get_report_channel_id
    main_module.publish_or_refresh_operation_report = publish_or_refresh_operation
    main_module.PesLoadedView = PesLoadedView

    persistent = _register_persistent_pes_views(main_module)
    main_module._ajap_market_channel_report_patch = True
    print(
        "Canal Staff/PES activo: tarjetas rojo/amarillo/verde + botón Cargado en PES "
        f"| vistas persistentes: {persistent}"
    )
