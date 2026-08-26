"""Canal operativo Staff/PES para AJAP Transfer Market.

/canal_movimientos configura un canal por servidor. Cuando Staff resuelve una
operación, el bot mantiene una tarjeta única con toda la información del acuerdo:
- rojo: rechazada por administración;
- amarillo: aprobada y pendiente de cargar en PES;
- verde: cargada en PES.

El botón "Cargado en PES" aplica el movimiento pendiente al plantel AJAP (usando
la misma lógica administrativa existente) y luego deja la tarjeta verde. Así la
fecha/hora de aprobación y la fecha/hora de carga en PES quedan auditadas por
separado. Los intercambios vinculados se muestran en una sola tarjeta.
"""

import io
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import discord
import market_close_report_patch as reports

APP = None
LOCAL_TZ = ZoneInfo("America/Argentina/Buenos_Aires")


# ---------------------------------------------------------------------------
# Esquema y configuración por servidor
# ---------------------------------------------------------------------------

def _ensure_current_schema():
    """Migra también DBs por guild que ya existían antes de esta función."""
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


def ensure_schema():
    _ensure_current_schema()


def set_report_channel(guild_id: int, channel_id: int, user_id: int):
    _ensure_current_schema()
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
            (int(guild_id), int(channel_id), int(user_id)),
        )


def get_report_channel_id(guild_id: int):
    _ensure_current_schema()
    with APP.db() as conn:
        row = conn.execute(
            "SELECT channel_id FROM market_report_channels WHERE guild_id = ?",
            (int(guild_id),),
        ).fetchone()
    return int(row["channel_id"]) if row else None


def _has(row, key):
    return row is not None and key in row.keys()


def _base_transfer(transfer_id: int):
    _ensure_current_schema()
    with APP.db() as conn:
        return conn.execute(
            "SELECT * FROM transfers WHERE id = ? LIMIT 1",
            (int(transfer_id),),
        ).fetchone()


def _canonical_id(transfer_id: int):
    row = _base_transfer(transfer_id)
    if not row:
        return None
    group = row["deal_group"] if _has(row, "deal_group") else None
    if not group:
        return int(row["id"])
    with APP.db() as conn:
        first = conn.execute(
            "SELECT MIN(id) AS id FROM transfers WHERE deal_group = ?",
            (group,),
        ).fetchone()
    return int(first["id"]) if first and first["id"] is not None else int(row["id"])


def _deal_rows(transfer_id: int):
    row = _base_transfer(transfer_id)
    if not row:
        return []
    group = row["deal_group"] if _has(row, "deal_group") else None
    with APP.db() as conn:
        if group:
            return conn.execute(
                "SELECT * FROM transfers WHERE deal_group = ? ORDER BY id ASC",
                (group,),
            ).fetchall()
        return conn.execute(
            "SELECT * FROM transfers WHERE id = ?",
            (int(row["id"]),),
        ).fetchall()


def _deal_details(transfer_id: int):
    canonical = _canonical_id(transfer_id)
    if canonical is None:
        return None
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
            (canonical,),
        ).fetchone()


def _transfer_for_message(message_id: int):
    _ensure_current_schema()
    with APP.db() as conn:
        row = conn.execute(
            """
            SELECT id FROM transfers
            WHERE pes_report_message_id = ?
            ORDER BY id ASC LIMIT 1
            """,
            (int(message_id),),
        ).fetchone()
    return int(row["id"]) if row else None


def _all_status(rows, status):
    return bool(rows) and all((row["status"] or "").upper() == status for row in rows)


def _deal_loaded(rows):
    return bool(rows) and all(_has(row, "pes_loaded_at") and row["pes_loaded_at"] for row in rows)


def _mark_deal_loaded(transfer_id: int, user_id: int):
    rows = _deal_rows(transfer_id)
    if not rows:
        return
    ids = [int(row["id"]) for row in rows]
    placeholders = ",".join("?" for _ in ids)
    with APP.db() as conn:
        conn.execute(
            f"""
            UPDATE transfers
            SET pes_loaded_by = ?, pes_loaded_at = COALESCE(pes_loaded_at, CURRENT_TIMESTAMP)
            WHERE id IN ({placeholders})
            """,
            (int(user_id), *ids),
        )


def _store_report_message(transfer_id: int, channel_id: int, message_id: int):
    rows = _deal_rows(transfer_id)
    if not rows:
        return
    ids = [int(row["id"]) for row in rows]
    placeholders = ",".join("?" for _ in ids)
    with APP.db() as conn:
        conn.execute(
            f"""
            UPDATE transfers
            SET pes_report_channel_id = ?, pes_report_message_id = ?
            WHERE id IN ({placeholders})
            """,
            (int(channel_id), int(message_id), *ids),
        )


# ---------------------------------------------------------------------------
# Presentación de la tarjeta
# ---------------------------------------------------------------------------

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


def _status_key(rows):
    if not rows:
        return "ADMIN_PENDING"
    if _all_status(rows, "RECHAZADA_ADMIN"):
        return "REJECTED"
    if _deal_loaded(rows):
        return "LOADED"
    if _all_status(rows, "APROBADA") or _all_status(rows, "APLICADA"):
        return "PENDING_PES"
    return "ADMIN_PENDING"


def _status_style(rows):
    key = _status_key(rows)
    if key == "REJECTED":
        return discord.Color.red(), "🔴 OPERACIÓN RECHAZADA POR ADMINISTRACIÓN", "⛔ NO CARGAR EN PES"
    if key == "LOADED":
        return discord.Color.green(), "🟢 OPERACIÓN CARGADA EN PES", "✅ CARGADO EN PES"
    if key == "PENDING_PES":
        return discord.Color.gold(), "🟡 OPERACIÓN PENDIENTE DE CARGAR EN PES", "⏳ PENDIENTE DE CARGAR EN PES"
    return discord.Color.gold(), "🟡 OPERACIÓN EN REVISIÓN ADMINISTRATIVA", "🛠️ PENDIENTE DE ADMIN"


def _operation_type(details, rows):
    if len(rows) > 1:
        kind = details["offer_kind"] if details and _has(details, "offer_kind") else None
        return kind or "INTERCAMBIO"
    return (details["operation_type"] if details else rows[0]["operation_type"]) or "TRANSFERENCIA"


def _condition_text(details):
    if not details:
        return None
    for key in ("notes", "offer_message", "publication_detail"):
        if _has(details, key) and details[key] and str(details[key]).strip():
            text = str(details[key]).strip()
            if text.casefold() not in {"sin condiciones adicionales", "sin observaciones"}:
                return text
    return None


def movement_embed(transfer_id: int):
    details = _deal_details(transfer_id)
    rows = _deal_rows(transfer_id)
    if not details or not rows:
        return discord.Embed(title="⚠️ Operación no encontrada", color=discord.Color.red())

    color, title, status_text = _status_style(rows)
    canonical = int(details["id"])
    embed = discord.Embed(title=f"{title} • #{canonical}", color=color)

    if len(rows) == 1:
        row = rows[0]
        embed.add_field(name="⚽ Jugador", value=f"**{row['player']}**", inline=False)
        embed.add_field(name="⬅️ Club de origen", value=row["seller"] or "—", inline=True)
        embed.add_field(name="➡️ Club de destino", value=row["buyer"] or "—", inline=True)
    else:
        movements = "\n".join(
            f"• **{row['player']}**: {row['seller']} ➜ **{row['buyer']}**"
            for row in rows
        )
        embed.add_field(name="🔁 Movimientos del intercambio", value=movements, inline=False)

    op_type = _operation_type(details, rows)
    info = [f"🔄 **Tipo:** {op_type}"]
    amount = details["amount"] or "$0"
    if amount not in ("$0", "0", "-", "—"):
        info.append(f"💰 **Monto final / adicional:** {amount}")
    elif len(rows) == 1:
        info.append(f"💰 **Monto final:** {amount}")

    if _has(details, "loan_seasons") and details["loan_seasons"]:
        seasons = int(details["loan_seasons"])
        info.append(f"⏳ **Duración del préstamo:** {seasons} temporada{'s' if seasons != 1 else ''}")
    if _has(details, "purchase_option_value"):
        purchase = details["purchase_option_value"]
        if purchase:
            info.append(f"🛒 **Opción de compra:** {purchase}")
        elif "PRÉSTAMO" in str(op_type).upper():
            info.append("🛒 **Opción de compra:** Sin opción")

    if _has(details, "listed_price") and details["listed_price"]:
        info.append(f"🏷️ **Precio publicado:** {details['listed_price']}")

    conditions = _condition_text(details)
    if conditions:
        info.append(f"📝 **Condiciones:** {conditions}")

    embed.add_field(name="📋 Información del acuerdo", value="\n".join(info), inline=False)

    created_at = details["created_at"] if _has(details, "created_at") else None
    approved_at = details["approved_at"] if _has(details, "approved_at") else None
    approved_by = details["approved_by"] if _has(details, "approved_by") else None
    embed.add_field(
        name="🕐 Fechas reales del acuerdo",
        value=(
            f"🤝 **Acuerdo registrado:** {_fmt_time(created_at)} (Argentina)\n"
            f"✅ **Aprobación definitiva:** {_fmt_time(approved_at)} (Argentina)\n"
            f"👤 **Aprobada por:** {_fmt_user(approved_by)}"
        ),
        inline=False,
    )

    key = _status_key(rows)
    if key == "REJECTED":
        rejected = next((row for row in rows if row["rejected_at"]), rows[0])
        embed.add_field(
            name="⛔ Rechazo administrativo",
            value=(
                f"📅 **{_fmt_time(rejected['rejected_at'])} (Argentina)**\n"
                f"👤 **Rechazada por:** {_fmt_user(rejected['rejected_by'])}"
            ),
            inline=False,
        )
    elif key == "LOADED":
        loaded = next((row for row in rows if row["pes_loaded_at"]), rows[0])
        applied_at = loaded["applied_at"] if _has(loaded, "applied_at") else None
        embed.add_field(
            name="🎮 Carga en PES",
            value=(
                f"📅 **Cargado:** {_fmt_time(loaded['pes_loaded_at'])} (Argentina)\n"
                f"👤 **Cargado por:** {_fmt_user(loaded['pes_loaded_by'])}\n"
                f"💾 **Plantel AJAP actualizado:** {_fmt_time(applied_at)} (Argentina)"
            ),
            inline=False,
        )

    embed.add_field(name="Estado", value=status_text, inline=False)
    embed.set_footer(text="AJAP Transfer Market • checklist Staff/PES")
    return embed


# ---------------------------------------------------------------------------
# Botón persistente. Custom ID fijo: funciona en todos los guilds tras reinicio.
# ---------------------------------------------------------------------------
class PesLoadedView(discord.ui.View):
    def __init__(self, transfer_id=None):
        super().__init__(timeout=None)
        disabled = False
        loaded = False
        if transfer_id is not None:
            rows = _deal_rows(int(transfer_id))
            state = _status_key(rows)
            loaded = state == "LOADED"
            disabled = state in {"LOADED", "REJECTED", "ADMIN_PENDING"}

        button = discord.ui.Button(
            label="Cargado en PES",
            emoji="✅" if loaded else "🎮",
            style=discord.ButtonStyle.success if loaded else discord.ButtonStyle.primary,
            custom_id="ajap:pes-loaded",
            disabled=disabled,
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

        message = getattr(interaction, "message", None)
        if message is None:
            await interaction.response.send_message("⚠️ No pude identificar la tarjeta.", ephemeral=True)
            return

        transfer_id = _transfer_for_message(message.id)
        if transfer_id is None:
            await interaction.response.send_message(
                "⚠️ Esta tarjeta no está vinculada a una operación de este servidor.", ephemeral=True
            )
            return

        rows = _deal_rows(transfer_id)
        state = _status_key(rows)
        if state == "REJECTED":
            await interaction.response.send_message("⛔ Esta operación fue rechazada.", ephemeral=True)
            return
        if state == "LOADED":
            await interaction.response.send_message("✅ Ya estaba cargada en PES.", ephemeral=True)
            return
        if state == "ADMIN_PENDING":
            await interaction.response.send_message(
                "⚠️ Primero la administración debe aprobar la operación.", ephemeral=True
            )
            return

        # Si está APROBADA, reutilizamos la lógica administrativa definitiva para
        # mover todos los jugadores vinculados (incluye intercambios) sin duplicarla.
        if _all_status(rows, "APROBADA"):
            admin_view = APP.OperacionAdminView(_canonical_id(transfer_id))
            apply_button = next(
                (
                    child for child in admin_view.children
                    if isinstance(child, discord.ui.Button) and child.label == "Aplicado en PES"
                ),
                None,
            )
            if apply_button is None:
                await interaction.response.send_message(
                    "⚠️ No encontré la acción administrativa para aplicar esta operación.", ephemeral=True
                )
                return
            await apply_button.callback(interaction)
            rows = _deal_rows(transfer_id)
            if not _all_status(rows, "APLICADA"):
                return

            # El callback administrativo ya puede haber marcado la carga. Si no,
            # lo hacemos acá; luego restauramos la tarjeta completa en el mensaje.
            if not _deal_loaded(rows):
                _mark_deal_loaded(transfer_id, interaction.user.id)
            try:
                await interaction.edit_original_response(
                    embed=movement_embed(transfer_id),
                    view=PesLoadedView(transfer_id),
                )
            except (discord.NotFound, discord.HTTPException):
                pass
            return

        # Compatibilidad con operaciones APLICADA antiguas que todavía no tenían
        # el checklist PES nuevo.
        if _all_status(rows, "APLICADA"):
            _mark_deal_loaded(transfer_id, interaction.user.id)
            await interaction.response.edit_message(
                embed=movement_embed(transfer_id),
                view=PesLoadedView(transfer_id),
            )


def _register_persistent_pes_view(runtime):
    try:
        runtime.bot.add_view(PesLoadedView())
        return 1
    except ValueError:
        return 0


# ---------------------------------------------------------------------------
# Publicar/actualizar una única tarjeta por acuerdo
# ---------------------------------------------------------------------------
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


async def publish_or_refresh_operation(interaction, transfer_id: int):
    canonical = _canonical_id(transfer_id)
    if canonical is None or not interaction.guild:
        return False

    rows = _deal_rows(canonical)
    if not rows:
        return False
    state = _status_key(rows)
    if state == "ADMIN_PENDING":
        return False

    channel = await resolve_channel(interaction)
    if channel is None:
        return False

    stored = rows[0]
    message_id = stored["pes_report_message_id"] if _has(stored, "pes_report_message_id") else None
    channel_id = stored["pes_report_channel_id"] if _has(stored, "pes_report_channel_id") else None
    view = None if state == "REJECTED" else PesLoadedView(canonical)

    if message_id and channel_id:
        try:
            old_channel = interaction.guild.get_channel(int(channel_id))
            if old_channel is None:
                old_channel = await APP.bot.fetch_channel(int(channel_id))
            msg = await old_channel.fetch_message(int(message_id))
            await msg.edit(embed=movement_embed(canonical), view=view)
            return True
        except (discord.NotFound, discord.Forbidden, discord.HTTPException, AttributeError):
            pass

    try:
        msg = await channel.send(embed=movement_embed(canonical), view=view)
        _store_report_message(canonical, channel.id, msg.id)
        return True
    except (discord.Forbidden, discord.HTTPException) as exc:
        print(f"WARNING AJAP: tarjeta Staff/PES #{canonical} no publicada: {exc}")
        return False


# ---------------------------------------------------------------------------
# Enganche seguro al OperacionAdminView final.
# Se envuelven callbacks de los botones al crear cada View; esto funciona aunque
# discord.py ya haya procesado los decoradores @discord.ui.button.
# ---------------------------------------------------------------------------

def _install_admin_operation_hooks(runtime):
    view_cls = getattr(runtime, "OperacionAdminView", None)
    if view_cls is None or getattr(view_cls, "_ajap_pes_report_hooks", False):
        return False

    original_init = view_cls.__init__

    def reporting_init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        transfer_id = int(getattr(self, "operacion_id", 0) or 0)
        if not transfer_id:
            return

        for child in self.children:
            if not isinstance(child, discord.ui.Button):
                continue
            label = child.label or ""
            if label not in {"Aprobar", "Aplicado en PES", "Rechazar admin"}:
                continue
            original_callback = child.callback

            async def reporting_callback(
                interaction,
                _original=original_callback,
                _label=label,
                _transfer_id=transfer_id,
            ):
                await _original(interaction)
                rows = _deal_rows(_transfer_id)
                if not rows:
                    return

                should_publish = False
                if _label == "Aprobar" and _all_status(rows, "APROBADA"):
                    should_publish = True
                elif _label == "Rechazar admin" and _all_status(rows, "RECHAZADA_ADMIN"):
                    should_publish = True
                elif _label == "Aplicado en PES" and _all_status(rows, "APLICADA"):
                    _mark_deal_loaded(_transfer_id, interaction.user.id)
                    should_publish = True

                if should_publish:
                    try:
                        await publish_or_refresh_operation(interaction, _transfer_id)
                    except Exception as exc:
                        print(
                            f"WARNING AJAP: refresco Staff/PES operación #{_transfer_id} falló: {exc}"
                        )

            child.callback = reporting_callback

    view_cls.__init__ = reporting_init
    view_cls._ajap_pes_report_hooks = True
    return True


# ---------------------------------------------------------------------------
# Cierre general: se conserva como respaldo y suma el semáforo PES.
# ---------------------------------------------------------------------------

def fmt_status(status: str) -> str:
    return {
        "PENDIENTE_ADMIN": "🟡 Pendiente admin",
        "APROBADA": "🟡 Pendiente de PES",
        "APLICADA": "✅ Aplicada",
        "RECHAZADA_ADMIN": "🔴 Rechazada admin",
    }.get(status or "", status or "—")


async def post_close_report(interaction, text, filename):
    channel = await resolve_channel(interaction)
    if channel is None:
        return False

    cycle = reports.latest_closed_cycle(APP)
    if not cycle:
        return False
    rows = reports.cycle_rows(APP, cycle)

    loaded = 0
    pending = 0
    rejected = 0
    seen = set()
    for row in rows:
        canonical = _canonical_id(row["id"])
        if canonical is None or canonical in seen:
            continue
        seen.add(canonical)
        state = _status_key(_deal_rows(canonical))
        loaded += int(state == "LOADED")
        pending += int(state == "PENDING_PES")
        rejected += int(state == "REJECTED")

    with APP.db() as conn:
        season = (
            conn.execute("SELECT name FROM seasons WHERE id = ?", (cycle["season_id"],)).fetchone()
            if cycle["season_id"] else None
        )
    season_name = season["name"] if season else "Sin temporada"

    summary = discord.Embed(
        title="🔒 MERCADO CERRADO • CONTROL STAFF/PES",
        description=(
            f"**{season_name}** • Ventana **#{cycle['id']}**\n"
            f"📋 Acuerdos registrados: **{len(seen)}**\n"
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
    hooks = _install_admin_operation_hooks(main_module)

    if bot.tree.get_command("canal_movimientos") is None:
        @bot.tree.command(
            name="canal_movimientos",
            description="Usa este canal para controlar todos los movimientos Staff/PES",
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
                f"✅ **Canal Staff/PES configurado:** {interaction.channel.mention}\n"
                "Cada acuerdo resuelto aparecerá acá: 🔴 rechazado, 🟡 pendiente de PES o 🟢 cargado en PES.",
                ephemeral=True,
            )

    main_module.market_report_channel_id = get_report_channel_id
    main_module.publish_or_refresh_operation_report = publish_or_refresh_operation
    main_module.PesLoadedView = PesLoadedView

    persistent = _register_persistent_pes_view(main_module)
    main_module._ajap_market_channel_report_patch = True
    print(
        "Canal Staff/PES activo: tarjetas rojo/amarillo/verde + botón Cargado en PES "
        f"| hooks admin={'OK' if hooks else 'NO'} | vista persistente={persistent}"
    )
