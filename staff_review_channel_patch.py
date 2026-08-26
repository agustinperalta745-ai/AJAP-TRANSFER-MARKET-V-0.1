"""Revisión Staff directamente desde /canal_movimientos.

Convierte el canal Staff/PES en el panel operativo completo:
- azul: pendiente de aprobación Staff, con Aprobar/Rechazar;
- amarillo: aprobado y pendiente de cargar en PES;
- rojo: rechazado, conservando quién/cuándo;
- verde: cargado en PES, conservando quién/cuándo.

Las transferencias, intercambios y préstamos publican la tarjeta al ser aceptados
por los clubes. Los clausulazos publican su solicitud antes de que Staff decida.
Todos los botones son persistentes y resuelven la operación por el ID del mensaje,
por lo que siguen funcionando después de reinicios de Railway.
"""

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import discord

import clausulazo_patch as clauses
import market_channel_report_patch as market_reports
import market_close_report_patch as close_reports

APP = None
BOT = None
LOCAL_TZ = ZoneInfo("America/Argentina/Buenos_Aires")
SPANISH_DAYS = (
    "lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"
)


def _is_staff(interaction):
    return close_reports.is_staff_or_admin(APP, interaction)


def _fmt_time(value):
    if not value:
        return "—"
    raw = str(value).strip()
    try:
        dt = datetime.strptime(raw[:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        local = dt.astimezone(LOCAL_TZ)
        day = SPANISH_DAYS[local.weekday()].capitalize()
        return f"{day} {local.strftime('%d/%m/%Y')} • {local.strftime('%H:%M')}"
    except ValueError:
        return raw


def _status_style(rows):
    key = market_reports._status_key(rows)
    if key == "REJECTED":
        return discord.Color.red(), "🔴 OPERACIÓN RECHAZADA POR ADMINISTRACIÓN", "⛔ NO CARGAR EN PES"
    if key == "LOADED":
        return discord.Color.green(), "🟢 OPERACIÓN CARGADA EN PES", "✅ CARGADO EN PES"
    if key == "PENDING_PES":
        return discord.Color.gold(), "🟡 OPERACIÓN PENDIENTE DE CARGAR EN PES", "⏳ PENDIENTE DE CARGAR EN PES"
    return discord.Color.blue(), "🔵 OPERACIÓN PENDIENTE DE APROBACIÓN STAFF", "🛠️ ESPERANDO DECISIÓN STAFF"


def _validate_rosters(rows):
    for row in rows:
        player = APP.jugador_por_id(int(row["player_id"])) if row["player_id"] else APP.jugador_por_nombre(row["player"])
        if not player:
            return False, f"No se encontró **{row['player']}** en el plantel oficial."
        if (player["club"] or "").casefold() != (row["seller"] or "").casefold():
            return False, (
                f"**{row['player']}** figura actualmente en **{player['club']}**, "
                f"no en **{row['seller']}**."
            )
    return True, None


def _approve_deal(transfer_id, staff_id):
    rows = market_reports._deal_rows(transfer_id)
    if not rows or not all((row["status"] or "").upper() == "PENDIENTE_ADMIN" for row in rows):
        return False, "La operación ya no está pendiente de aprobación."
    ok, error = _validate_rosters(rows)
    if not ok:
        return False, error

    ids = [int(row["id"]) for row in rows]
    placeholders = ",".join("?" for _ in ids)
    with APP.db() as conn:
        conn.execute(
            f"""
            UPDATE transfers
            SET status = 'APROBADA', approved_by = ?, approved_at = CURRENT_TIMESTAMP
            WHERE id IN ({placeholders}) AND status = 'PENDIENTE_ADMIN'
            """,
            (int(staff_id), *ids),
        )
    return True, None


def _reject_deal(transfer_id, staff_id):
    rows = market_reports._deal_rows(transfer_id)
    if not rows or any((row["status"] or "").upper() not in {"PENDIENTE_ADMIN", "APROBADA"} for row in rows):
        return False, "La operación ya no puede rechazarse."

    ids = [int(row["id"]) for row in rows]
    placeholders = ",".join("?" for _ in ids)
    offer_ids = sorted({int(row["offer_id"]) for row in rows if row["offer_id"]})
    with APP.db() as conn:
        conn.execute(
            f"""
            UPDATE transfers
            SET status = 'RECHAZADA_ADMIN', rejected_by = ?, rejected_at = CURRENT_TIMESTAMP
            WHERE id IN ({placeholders})
            """,
            (int(staff_id), *ids),
        )
        for offer_id in offer_ids:
            conn.execute(
                "UPDATE offers SET status = 'CANCELADA_ADMIN' WHERE id = ?",
                (offer_id,),
            )
    return True, None


def _apply_deal_to_pes(transfer_id, staff_id):
    rows = market_reports._deal_rows(transfer_id)
    if not rows:
        return False, "Operación no encontrada."

    statuses = {(row["status"] or "").upper() for row in rows}
    if statuses == {"APLICADA"}:
        market_reports._mark_deal_loaded(transfer_id, staff_id)
        return True, None
    if statuses != {"APROBADA"}:
        return False, "Primero deben estar aprobados todos los movimientos del acuerdo."

    ok, error = _validate_rosters(rows)
    if not ok:
        return False, error

    conn = APP.db()
    try:
        conn.execute("BEGIN IMMEDIATE")
        for row in rows:
            player = conn.execute(
                "SELECT * FROM roster_players WHERE id = ?",
                (int(row["player_id"]),),
            ).fetchone() if row["player_id"] else conn.execute(
                "SELECT * FROM roster_players WHERE name = ? COLLATE NOCASE",
                (row["player"],),
            ).fetchone()
            if not player or (player["club"] or "").casefold() != (row["seller"] or "").casefold():
                conn.rollback()
                current = player["club"] if player else "desconocido"
                return False, f"{row['player']} figura en {current}; no se aplicó ningún movimiento."

        for row in rows:
            player = conn.execute(
                "SELECT * FROM roster_players WHERE id = ?",
                (int(row["player_id"]),),
            ).fetchone() if row["player_id"] else conn.execute(
                "SELECT * FROM roster_players WHERE name = ? COLLATE NOCASE",
                (row["player"],),
            ).fetchone()
            conn.execute(
                "UPDATE roster_players SET club = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (row["buyer"], player["id"]),
            )
            conn.execute(
                """
                UPDATE transfers
                SET status = 'APLICADA', applied_by = ?, applied_at = CURRENT_TIMESTAMP,
                    pes_loaded_by = ?, pes_loaded_at = COALESCE(pes_loaded_at, CURRENT_TIMESTAMP)
                WHERE id = ?
                """,
                (int(staff_id), int(staff_id), int(row["id"])),
            )
            history = conn.execute(
                "SELECT id FROM player_history WHERE transfer_id = ? LIMIT 1",
                (int(row["id"]),),
            ).fetchone()
            if not history:
                conn.execute(
                    """
                    INSERT INTO player_history
                    (player_id, player, from_club, to_club, transfer_id, season_id, event_type)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        player["id"], row["player"], row["seller"], row["buyer"],
                        row["id"], row["season_id"], row["operation_type"],
                    ),
                )
        conn.commit()
        return True, None
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


class StaffOperationView(discord.ui.View):
    """Botones persistentes para una tarjeta de operación."""

    def __init__(self, transfer_id=None):
        super().__init__(timeout=None)
        state = None
        if transfer_id is not None:
            state = market_reports._status_key(market_reports._deal_rows(int(transfer_id)))

        approve = discord.ui.Button(
            label="Aprobar movimiento",
            emoji="✅",
            style=discord.ButtonStyle.success,
            custom_id="ajap:staff-operation:approve",
            disabled=state not in {None, "ADMIN_PENDING"},
        )
        reject = discord.ui.Button(
            label="Rechazar movimiento",
            emoji="⛔",
            style=discord.ButtonStyle.danger,
            custom_id="ajap:staff-operation:reject",
            disabled=state not in {None, "ADMIN_PENDING"},
        )
        loaded = discord.ui.Button(
            label="Cargado en PES",
            emoji="✅" if state == "LOADED" else "🎮",
            style=discord.ButtonStyle.success if state == "LOADED" else discord.ButtonStyle.primary,
            custom_id="ajap:staff-operation:loaded",
            disabled=state not in {None, "PENDING_PES"},
        )
        approve.callback = self._approve
        reject.callback = self._reject
        loaded.callback = self._loaded

        if transfer_id is None or state == "ADMIN_PENDING":
            self.add_item(approve)
            self.add_item(reject)
        elif state == "PENDING_PES":
            self.add_item(loaded)
        elif state == "LOADED":
            loaded.disabled = True
            self.add_item(loaded)

    async def _resolve(self, interaction):
        message = getattr(interaction, "message", None)
        if message is None:
            return None
        return market_reports._transfer_for_message(message.id)

    async def _approve(self, interaction: discord.Interaction):
        if not _is_staff(interaction):
            await interaction.response.send_message("⛔ Solo Staff/administradores.", ephemeral=True)
            return
        transfer_id = await self._resolve(interaction)
        if transfer_id is None:
            await interaction.response.send_message("⚠️ No pude identificar la operación.", ephemeral=True)
            return
        ok, error = _approve_deal(transfer_id, interaction.user.id)
        if not ok:
            await interaction.response.send_message(f"⚠️ {error}", ephemeral=True)
            return
        await interaction.response.edit_message(
            embed=market_reports.movement_embed(transfer_id),
            view=StaffOperationView(transfer_id),
        )

    async def _reject(self, interaction: discord.Interaction):
        if not _is_staff(interaction):
            await interaction.response.send_message("⛔ Solo Staff/administradores.", ephemeral=True)
            return
        transfer_id = await self._resolve(interaction)
        if transfer_id is None:
            await interaction.response.send_message("⚠️ No pude identificar la operación.", ephemeral=True)
            return
        ok, error = _reject_deal(transfer_id, interaction.user.id)
        if not ok:
            await interaction.response.send_message(f"⚠️ {error}", ephemeral=True)
            return
        await interaction.response.edit_message(
            embed=market_reports.movement_embed(transfer_id),
            view=None,
        )

    async def _loaded(self, interaction: discord.Interaction):
        if not _is_staff(interaction):
            await interaction.response.send_message("⛔ Solo Staff/administradores.", ephemeral=True)
            return
        transfer_id = await self._resolve(interaction)
        if transfer_id is None:
            await interaction.response.send_message("⚠️ No pude identificar la operación.", ephemeral=True)
            return
        ok, error = _apply_deal_to_pes(transfer_id, interaction.user.id)
        if not ok:
            await interaction.response.send_message(f"⚠️ {error}", ephemeral=True)
            return
        await interaction.response.edit_message(
            embed=market_reports.movement_embed(transfer_id),
            view=StaffOperationView(transfer_id),
        )


async def publish_or_refresh_operation(interaction, transfer_id: int):
    canonical = market_reports._canonical_id(transfer_id)
    if canonical is None or not interaction.guild:
        return False
    rows = market_reports._deal_rows(canonical)
    if not rows:
        return False
    channel = await market_reports.resolve_channel(interaction)
    if channel is None:
        return False

    stored = rows[0]
    message_id = stored["pes_report_message_id"] if market_reports._has(stored, "pes_report_message_id") else None
    channel_id = stored["pes_report_channel_id"] if market_reports._has(stored, "pes_report_channel_id") else None
    state = market_reports._status_key(rows)
    view = None if state == "REJECTED" else StaffOperationView(canonical)

    if message_id and channel_id:
        try:
            old_channel = interaction.guild.get_channel(int(channel_id))
            if old_channel is None:
                old_channel = await APP.bot.fetch_channel(int(channel_id))
            msg = await old_channel.fetch_message(int(message_id))
            await msg.edit(embed=market_reports.movement_embed(canonical), view=view)
            return True
        except (discord.NotFound, discord.Forbidden, discord.HTTPException, AttributeError):
            pass

    try:
        msg = await channel.send(embed=market_reports.movement_embed(canonical), view=view)
        market_reports._store_report_message(canonical, channel.id, msg.id)
        return True
    except (discord.Forbidden, discord.HTTPException) as exc:
        print(f"WARNING AJAP: tarjeta de revisión Staff #{canonical} no publicada: {exc}")
        return False


def _first_transfer_for_offer(offer_id):
    with APP.db() as conn:
        return conn.execute(
            "SELECT id FROM transfers WHERE offer_id = ? ORDER BY id ASC LIMIT 1",
            (int(offer_id),),
        ).fetchone()


def _install_offer_accept_hook(runtime):
    view_cls = getattr(runtime, "OfertaDecisionView", None)
    if view_cls is None or getattr(view_cls, "_ajap_staff_channel_accept_hook", False):
        return False
    original_init = view_cls.__init__

    def hooked_init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        offer_id = int(getattr(self, "offer_id", getattr(self, "oferta_id", 0)) or 0)
        if not offer_id:
            return
        for child in self.children:
            if not isinstance(child, discord.ui.Button) or child.label != "Aceptar":
                continue
            original_callback = child.callback

            async def accept_and_report(interaction, _original=original_callback, _offer_id=offer_id):
                await _original(interaction)
                offer = APP.oferta_por_id(_offer_id)
                if not offer or (offer["status"] or "").upper() != "ACEPTADA":
                    return
                transfer = _first_transfer_for_offer(_offer_id)
                if not transfer:
                    return
                try:
                    await publish_or_refresh_operation(interaction, int(transfer["id"]))
                except Exception as exc:
                    print(f"WARNING AJAP: alta de tarjeta Staff para oferta #{_offer_id} falló: {exc}")

            child.callback = accept_and_report

    view_cls.__init__ = hooked_init
    view_cls._ajap_staff_channel_accept_hook = True
    return True


# ---------------------------------------------------------------------------
# Clausulazos pendientes en el mismo canal
# ---------------------------------------------------------------------------
def _ensure_clause_schema():
    clauses.ensure_schema()
    with APP.db() as conn:
        APP.add_column_if_missing(conn, "clause_requests", "staff_report_message_id", "INTEGER")
        APP.add_column_if_missing(conn, "clause_requests", "staff_report_channel_id", "INTEGER")


def _clause_for_message(message_id):
    _ensure_clause_schema()
    with APP.db() as conn:
        return conn.execute(
            "SELECT * FROM clause_requests WHERE staff_report_message_id = ? ORDER BY id DESC LIMIT 1",
            (int(message_id),),
        ).fetchone()


def _store_clause_message(request_id, channel_id, message_id):
    _ensure_clause_schema()
    with APP.db() as conn:
        conn.execute(
            """
            UPDATE clause_requests
            SET staff_report_channel_id = ?, staff_report_message_id = ?
            WHERE id = ?
            """,
            (int(channel_id), int(message_id), int(request_id)),
        )


def _clause_embed(req):
    status = (req["status"] or "").upper()
    if status == "RECHAZADO_STAFF":
        embed = discord.Embed(
            title=f"🔴 CLAUSULAZO RECHAZADO POR STAFF • #{req['id']}",
            color=discord.Color.red(),
        )
    elif status == "APROBADO":
        embed = discord.Embed(
            title=f"🟡 CLAUSULAZO APROBADO • #{req['id']}",
            color=discord.Color.gold(),
        )
    else:
        embed = discord.Embed(
            title=f"🔵 CLAUSULAZO PENDIENTE DE APROBACIÓN STAFF • #{req['id']}",
            color=discord.Color.blue(),
        )

    embed.add_field(name="⚽ Jugador", value=f"**{req['player']}**", inline=False)
    embed.add_field(name="⬅️ Club de origen", value=req["seller_club"], inline=True)
    embed.add_field(name="➡️ Club de destino", value=req["buyer_club"], inline=True)
    embed.add_field(name="💰 Cláusula", value=clauses.fmt_money(req["amount"]), inline=True)
    embed.add_field(
        name="👤 Solicitado por",
        value=f"{req['buyer_username']} • <@{int(req['buyer_user_id'])}>",
        inline=False,
    )
    embed.add_field(
        name="🕐 Solicitud",
        value=f"📅 **{_fmt_time(req['requested_at'])} (Argentina)**",
        inline=False,
    )
    if status in {"RECHAZADO_STAFF", "APROBADO"}:
        action = "Aprobado" if status == "APROBADO" else "Rechazado"
        embed.add_field(
            name=f"{'✅' if status == 'APROBADO' else '⛔'} Decisión Staff",
            value=(
                f"📅 **{action}: {_fmt_time(req['decided_at'])} (Argentina)**\n"
                f"👤 **Por:** <@{int(req['decided_by'])}>" if req["decided_by"] else
                f"📅 **{action}: {_fmt_time(req['decided_at'])} (Argentina)**"
            ),
            inline=False,
        )
    embed.add_field(
        name="Estado",
        value=(
            "⛔ RECHAZADO" if status == "RECHAZADO_STAFF" else
            "✅ APROBADO • PENDIENTE DE PES" if status == "APROBADO" else
            "🛠️ ESPERANDO DECISIÓN STAFF"
        ),
        inline=False,
    )
    embed.set_footer(text=f"Mercado #{req['cycle_id']} • AJAP Staff")
    return embed


async def _report_channel_for_guild(guild):
    if guild is None:
        return None
    channel_id = market_reports.get_report_channel_id(guild.id)
    if not channel_id:
        return None
    channel = guild.get_channel(channel_id)
    if channel is None:
        try:
            channel = await BOT.fetch_channel(channel_id)
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            return None
    return channel if hasattr(channel, "send") else None


class ClauseStaffView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        approve = discord.ui.Button(
            label="Aprobar clausulazo", emoji="✅", style=discord.ButtonStyle.success,
            custom_id="ajap:staff-clause:approve",
        )
        reject = discord.ui.Button(
            label="Rechazar clausulazo", emoji="⛔", style=discord.ButtonStyle.danger,
            custom_id="ajap:staff-clause:reject",
        )
        approve.callback = self._approve
        reject.callback = self._reject
        self.add_item(approve)
        self.add_item(reject)

    async def _approve(self, interaction: discord.Interaction):
        if not _is_staff(interaction):
            await interaction.response.send_message("⛔ Solo Staff/administradores.", ephemeral=True)
            return
        req = _clause_for_message(interaction.message.id)
        if not req or (req["status"] or "").upper() != "PENDIENTE_STAFF":
            await interaction.response.send_message("⚠️ Este clausulazo ya fue resuelto.", ephemeral=True)
            return

        ok, result = clauses.approve_request(req, interaction.user.id)
        fresh = clauses.request_by_id(req["id"])
        if not ok:
            if fresh and (fresh["status"] or "").upper() == "RECHAZADO_STAFF":
                await clauses.notify_buyer(interaction.guild, fresh, False)
                await interaction.response.edit_message(embed=_clause_embed(fresh), view=None)
            else:
                await interaction.response.send_message(f"⚠️ {result}", ephemeral=True)
            return

        await clauses.notify_seller(interaction.guild, fresh)
        await clauses.notify_buyer(interaction.guild, fresh, True)
        transfer_id = int(fresh["transfer_id"] or result)
        market_reports._store_report_message(
            transfer_id, interaction.channel_id, interaction.message.id
        )
        await interaction.response.edit_message(
            embed=market_reports.movement_embed(transfer_id),
            view=StaffOperationView(transfer_id),
        )

    async def _reject(self, interaction: discord.Interaction):
        if not _is_staff(interaction):
            await interaction.response.send_message("⛔ Solo Staff/administradores.", ephemeral=True)
            return
        req = _clause_for_message(interaction.message.id)
        if not req or (req["status"] or "").upper() != "PENDIENTE_STAFF":
            await interaction.response.send_message("⚠️ Este clausulazo ya fue resuelto.", ephemeral=True)
            return
        if not clauses.reject_request(req, interaction.user.id):
            await interaction.response.send_message("⚠️ Este clausulazo ya fue resuelto.", ephemeral=True)
            return
        fresh = clauses.request_by_id(req["id"])
        await clauses.notify_buyer(interaction.guild, fresh, False)
        await interaction.response.edit_message(embed=_clause_embed(fresh), view=None)


async def _publish_clause_pending(guild, req):
    if not req or (req["status"] or "").upper() != "PENDIENTE_STAFF":
        return False
    channel = await _report_channel_for_guild(guild)
    if channel is None:
        return False

    if "staff_report_message_id" in req.keys() and req["staff_report_message_id"]:
        try:
            old_channel_id = req["staff_report_channel_id"] or channel.id
            old_channel = guild.get_channel(int(old_channel_id)) or await BOT.fetch_channel(int(old_channel_id))
            msg = await old_channel.fetch_message(int(req["staff_report_message_id"]))
            await msg.edit(embed=_clause_embed(req), view=ClauseStaffView())
            return True
        except (discord.NotFound, discord.Forbidden, discord.HTTPException, AttributeError):
            pass

    try:
        msg = await channel.send(embed=_clause_embed(req), view=ClauseStaffView())
        _store_clause_message(req["id"], channel.id, msg.id)
        return True
    except (discord.Forbidden, discord.HTTPException) as exc:
        print(f"WARNING AJAP: clausulazo Staff #{req['id']} no publicado: {exc}")
        return False


def _install_clause_notify_hook():
    original = clauses.notify_staff
    if getattr(original, "_ajap_staff_channel_hook", False):
        return False

    async def notify_staff_with_channel(guild, req):
        delivered = await original(guild, req)
        try:
            await _publish_clause_pending(guild, clauses.request_by_id(req["id"]))
        except Exception as exc:
            print(f"WARNING AJAP: tarjeta pendiente de clausulazo #{req['id']} falló: {exc}")
        return delivered

    notify_staff_with_channel._ajap_staff_channel_hook = True
    clauses.notify_staff = notify_staff_with_channel
    return True


def _refresh_clause_card_from_request(guild, request_id):
    """Devuelve coroutine interna para refrescar decisiones tomadas fuera del canal."""
    async def runner():
        req = clauses.request_by_id(request_id)
        if not req or "staff_report_message_id" not in req.keys() or not req["staff_report_message_id"]:
            return
        try:
            channel_id = req["staff_report_channel_id"]
            channel = guild.get_channel(int(channel_id)) or await BOT.fetch_channel(int(channel_id))
            msg = await channel.fetch_message(int(req["staff_report_message_id"]))
            if (req["status"] or "").upper() == "APROBADO" and req["transfer_id"]:
                transfer_id = int(req["transfer_id"])
                market_reports._store_report_message(transfer_id, channel.id, msg.id)
                await msg.edit(
                    embed=market_reports.movement_embed(transfer_id),
                    view=StaffOperationView(transfer_id),
                )
            elif (req["status"] or "").upper() == "RECHAZADO_STAFF":
                await msg.edit(embed=_clause_embed(req), view=None)
        except (discord.NotFound, discord.Forbidden, discord.HTTPException, AttributeError):
            pass
    return runner()


def _install_clause_external_decision_hook():
    view_cls = clauses.ClauseDecisionView
    if getattr(view_cls, "_ajap_staff_channel_refresh_hook", False):
        return False
    original_init = view_cls.__init__

    def hooked_init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        request_id = int(getattr(self, "request_id", 0) or 0)
        if not request_id:
            return
        for child in self.children:
            if not isinstance(child, discord.ui.Button) or child.label not in {"Aprobar clausulazo", "Rechazar"}:
                continue
            original_callback = child.callback

            async def callback_and_refresh(interaction, _original=original_callback, _request_id=request_id):
                await _original(interaction)
                if interaction.guild:
                    await _refresh_clause_card_from_request(interaction.guild, _request_id)

            child.callback = callback_and_refresh

    view_cls.__init__ = hooked_init
    view_cls._ajap_staff_channel_refresh_hook = True
    return True


def apply_staff_review_channel_patch(runtime, bot):
    global APP, BOT
    APP = runtime
    BOT = bot
    if getattr(runtime, "_ajap_staff_review_channel_patch", False):
        return

    market_reports._fmt_time = _fmt_time
    market_reports._status_style = _status_style
    market_reports.publish_or_refresh_operation = publish_or_refresh_operation
    runtime.publish_or_refresh_operation_report = publish_or_refresh_operation

    _ensure_clause_schema()
    offer_hook = _install_offer_accept_hook(runtime)
    clause_notify = _install_clause_notify_hook()
    clause_external = _install_clause_external_decision_hook()

    persistent = 0
    for view in (StaffOperationView(), ClauseStaffView()):
        try:
            bot.add_view(view)
            persistent += 1
        except ValueError:
            pass

    runtime.StaffOperationView = StaffOperationView
    runtime.ClauseStaffView = ClauseStaffView
    runtime._ajap_staff_review_channel_patch = True
    print(
        "AJAP canal Staff completo: pendiente→aprobar/rechazar→PES "
        f"| ofertas={'OK' if offer_hook else 'NO'} "
        f"| clausulazos={'OK' if clause_notify else 'NO'} "
        f"| refresh externo={'OK' if clause_external else 'NO'} "
        f"| vistas persistentes={persistent}"
    )
