"""Admin decision workflow for AJAP free-team vacancy requests.

Extends free_team_vacancy_patch with a persistent Staff decision card:
- Aceptar: assigns the free club to the applicant immediately.
- Rechazar: closes the request without assigning the club.
- Poner en espera: keeps the request alive for a later final decision.

Every action is audited with administrator, exact timestamp and history, so an
EN_ESPERA decision remains visible even if another admin later accepts/rejects.
"""

from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import discord

import free_team_vacancy_patch as vacancies
import team_assignment as teams


APP = None
BOT = None
LOCAL_TZ = ZoneInfo("America/Argentina/Buenos_Aires")
SPANISH_DAYS = (
    "lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"
)
ACTIVE_STATUSES = {"PENDIENTE", "EN_ESPERA"}
FINAL_STATUSES = {"ACEPTADA", "RECHAZADA", "CERRADA_AUTOMATICA"}


def _ensure_schema():
    vacancies._ensure_schema()
    with APP.db() as conn:
        APP.add_column_if_missing(conn, "free_team_requests", "staff_channel_id", "INTEGER")
        APP.add_column_if_missing(conn, "free_team_requests", "staff_message_id", "INTEGER")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS free_team_request_decisions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                request_id INTEGER NOT NULL,
                action TEXT NOT NULL,
                admin_id INTEGER NOT NULL,
                note TEXT,
                decided_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_free_team_decisions_request
            ON free_team_request_decisions (request_id, id)
            """
        )


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


def _request_by_id(request_id: int):
    _ensure_schema()
    with APP.db() as conn:
        return conn.execute(
            "SELECT * FROM free_team_requests WHERE id = ? LIMIT 1",
            (int(request_id),),
        ).fetchone()


def _request_for_message(message_id: int):
    _ensure_schema()
    with APP.db() as conn:
        return conn.execute(
            """
            SELECT * FROM free_team_requests
            WHERE staff_message_id = ?
            ORDER BY id DESC LIMIT 1
            """,
            (int(message_id),),
        ).fetchone()


def _decision_history(request_id: int):
    _ensure_schema()
    with APP.db() as conn:
        return conn.execute(
            """
            SELECT * FROM free_team_request_decisions
            WHERE request_id = ?
            ORDER BY id ASC
            """,
            (int(request_id),),
        ).fetchall()


def _status_label(status: str) -> str:
    status = (status or "PENDIENTE").upper()
    return {
        "PENDIENTE": "🟡 Pendiente de administración",
        "EN_ESPERA": "⏸️ En espera",
        "ACEPTADA": "✅ Aceptada",
        "RECHAZADA": "❌ Rechazada",
        "CERRADA_AUTOMATICA": "⚪ Cerrada automáticamente",
    }.get(status, status)


def _status_color(status: str):
    status = (status or "PENDIENTE").upper()
    if status == "ACEPTADA":
        return discord.Color.green()
    if status == "RECHAZADA":
        return discord.Color.red()
    if status == "EN_ESPERA":
        return discord.Color.orange()
    if status == "CERRADA_AUTOMATICA":
        return discord.Color.light_grey()
    return discord.Color.gold()


def _history_text(request_id: int) -> str:
    rows = _decision_history(request_id)
    if not rows:
        return "_Todavía no se tomó ninguna decisión._"

    labels = {
        "EN_ESPERA": "⏸️ Puesta en espera",
        "ACEPTADA": "✅ Aceptada",
        "RECHAZADA": "❌ Rechazada",
        "CERRADA_AUTOMATICA": "⚪ Cerrada automáticamente",
    }
    lines = []
    for row in rows[-8:]:
        label = labels.get((row["action"] or "").upper(), row["action"])
        lines.append(
            f"{label} • <@{int(row['admin_id'])}> • **{_fmt_time(row['decided_at'])} (Argentina)**"
        )
    return "\n".join(lines)


def admin_request_embed(request):
    status = (request["status"] or "PENDIENTE").upper()
    embed = discord.Embed(
        title=f"📥 Solicitud de vacante #{request['id']}",
        description=(
            f"<@{int(request['user_id'])}> quiere hacerse cargo de **{request['club']}**."
        ),
        color=_status_color(status),
    )
    embed.add_field(
        name="👤 Usuario",
        value=f"{request['username']} • `{request['user_id']}`",
        inline=False,
    )
    embed.add_field(name="🏟️ Club solicitado", value=request["club"], inline=True)
    embed.add_field(
        name="💰 Dinero del club",
        value=vacancies._fmt_money(vacancies.clauses.club_balance(request["club"])),
        inline=True,
    )
    embed.add_field(
        name="💥 Clausulazo",
        value=vacancies._clause_availability(request["club"]),
        inline=False,
    )
    embed.add_field(
        name="📨 Solicitud enviada",
        value=f"**{_fmt_time(request['requested_at'])} (Argentina)**",
        inline=False,
    )
    embed.add_field(name="📌 Estado actual", value=_status_label(status), inline=False)
    embed.add_field(
        name="🧾 Historial de decisiones",
        value=_history_text(int(request["id"])),
        inline=False,
    )
    if status in ACTIVE_STATUSES:
        embed.set_footer(text="Aceptar asigna el club • En espera conserva la solicitud • Rechazar la cierra")
    else:
        embed.set_footer(text=f"Solicitud #{request['id']} • decisión registrada y auditada")
    return embed


def _record_decision(request_id: int, status: str, admin_id: int, note=None):
    _ensure_schema()
    status = status.upper()
    with APP.db() as conn:
        current = conn.execute(
            "SELECT status FROM free_team_requests WHERE id = ?",
            (int(request_id),),
        ).fetchone()
        if not current or (current["status"] or "").upper() not in ACTIVE_STATUSES:
            return False
        conn.execute(
            """
            UPDATE free_team_requests
            SET status = ?, resolved_by = ?, resolved_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (status, int(admin_id), int(request_id)),
        )
        conn.execute(
            """
            INSERT INTO free_team_request_decisions
            (request_id, action, admin_id, note)
            VALUES (?, ?, ?, ?)
            """,
            (int(request_id), status, int(admin_id), note),
        )
    return True


def _request_exists(club: str, user_id: int) -> bool:
    _ensure_schema()
    with APP.db() as conn:
        row = conn.execute(
            """
            SELECT id FROM free_team_requests
            WHERE club = ? COLLATE NOCASE
              AND user_id = ?
              AND status IN ('PENDIENTE', 'EN_ESPERA')
            ORDER BY id DESC LIMIT 1
            """,
            (club, int(user_id)),
        ).fetchone()
    return bool(row)


def _store_staff_message(request_id: int, channel_id: int, message_id: int):
    _ensure_schema()
    with APP.db() as conn:
        conn.execute(
            """
            UPDATE free_team_requests
            SET staff_channel_id = ?, staff_message_id = ?
            WHERE id = ?
            """,
            (int(channel_id), int(message_id), int(request_id)),
        )


async def _request_member(guild, user_id: int):
    if guild is None:
        return None
    member = guild.get_member(int(user_id))
    if member is None:
        try:
            member = await guild.fetch_member(int(user_id))
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            return None
    return member


async def _notify_applicant(guild, request, status: str):
    member = await _request_member(guild, int(request["user_id"]))
    if member is None:
        return False

    status = status.upper()
    if status == "ACEPTADA":
        embed = discord.Embed(
            title="✅ Solicitud de vacante aceptada",
            description=(
                f"Tu solicitud fue aceptada. Desde ahora estás a cargo de **{request['club']}**."
            ),
            color=discord.Color.green(),
        )
    elif status == "RECHAZADA":
        embed = discord.Embed(
            title="❌ Solicitud de vacante rechazada",
            description=f"Tu solicitud para **{request['club']}** fue rechazada por administración.",
            color=discord.Color.red(),
        )
    else:
        embed = discord.Embed(
            title="⏸️ Solicitud de vacante en espera",
            description=(
                f"Administración dejó tu solicitud para **{request['club']}** en espera. "
                "La solicitud sigue activa hasta una decisión final."
            ),
            color=discord.Color.orange(),
        )
    try:
        await member.send(embed=embed)
        return True
    except (discord.Forbidden, discord.HTTPException):
        return False


def _stamp_assignment_admin(user_id: int, club: str, admin_id: int):
    with APP.db() as conn:
        row = conn.execute(
            """
            SELECT id FROM club_assignment_history
            WHERE user_id = ? AND club = ? COLLATE NOCASE
            ORDER BY id DESC LIMIT 1
            """,
            (int(user_id), club),
        ).fetchone()
        if row:
            conn.execute(
                """
                UPDATE club_assignment_history
                SET action = 'ASIGNADO_VACANTE_ADMIN', actor_id = ?
                WHERE id = ?
                """,
                (int(admin_id), int(row["id"])),
            )


def _close_conflicting_requests(request, admin_id: int):
    """Close other live requests once one applicant gets the club."""
    _ensure_schema()
    with APP.db() as conn:
        rows = conn.execute(
            """
            SELECT id FROM free_team_requests
            WHERE id != ?
              AND status IN ('PENDIENTE', 'EN_ESPERA')
              AND (
                    club = ? COLLATE NOCASE
                    OR user_id = ?
                  )
            ORDER BY id ASC
            """,
            (int(request["id"]), request["club"], int(request["user_id"])),
        ).fetchall()
        ids = [int(row["id"]) for row in rows]
        for request_id in ids:
            conn.execute(
                """
                UPDATE free_team_requests
                SET status = 'CERRADA_AUTOMATICA', resolved_by = ?, resolved_at = CURRENT_TIMESTAMP
                WHERE id = ?
                """,
                (int(admin_id), request_id),
            )
            conn.execute(
                """
                INSERT INTO free_team_request_decisions
                (request_id, action, admin_id, note)
                VALUES (?, 'CERRADA_AUTOMATICA', ?, ?)
                """,
                (
                    request_id,
                    int(admin_id),
                    "Se cerró automáticamente porque el club o el solicitante ya fue asignado.",
                ),
            )
    return ids


async def _refresh_request_message(guild, request_id: int):
    request = _request_by_id(request_id)
    if not request or not request["staff_message_id"] or not request["staff_channel_id"]:
        return False
    try:
        channel = guild.get_channel(int(request["staff_channel_id"]))
        if channel is None:
            channel = await BOT.fetch_channel(int(request["staff_channel_id"]))
        message = await channel.fetch_message(int(request["staff_message_id"]))
        status = (request["status"] or "").upper()
        view = VacancyAdminDecisionView(status) if status in ACTIVE_STATUSES else None
        await message.edit(embed=admin_request_embed(request), view=view)
        return True
    except (discord.NotFound, discord.Forbidden, discord.HTTPException, AttributeError):
        return False


class VacancyAdminDecisionView(discord.ui.View):
    """One persistent view; callbacks resolve the request from the Staff message id."""

    def __init__(self, status="PENDIENTE"):
        super().__init__(timeout=None)
        status = (status or "PENDIENTE").upper()

        accept = discord.ui.Button(
            label="Aceptar",
            emoji="✅",
            style=discord.ButtonStyle.success,
            custom_id="ajap:free-team-admin:accept",
        )
        reject = discord.ui.Button(
            label="Rechazar",
            emoji="❌",
            style=discord.ButtonStyle.danger,
            custom_id="ajap:free-team-admin:reject",
        )
        wait = discord.ui.Button(
            label="Poner en espera",
            emoji="⏸️",
            style=discord.ButtonStyle.secondary,
            custom_id="ajap:free-team-admin:wait",
            disabled=status == "EN_ESPERA",
        )
        accept.callback = self._accept
        reject.callback = self._reject
        wait.callback = self._wait
        self.add_item(accept)
        self.add_item(reject)
        self.add_item(wait)

    async def _resolve(self, interaction):
        if not APP.es_admin(interaction):
            await interaction.response.send_message("⛔ Solo administradores.", ephemeral=True)
            return None
        if interaction.message is None:
            await interaction.response.send_message("⚠️ No pude identificar la solicitud.", ephemeral=True)
            return None
        request = _request_for_message(interaction.message.id)
        if not request:
            await interaction.response.send_message("⚠️ No pude identificar la solicitud.", ephemeral=True)
            return None
        if (request["status"] or "").upper() not in ACTIVE_STATUSES:
            await interaction.response.send_message(
                f"⚠️ Esta solicitud ya está **{_status_label(request['status'])}**.",
                ephemeral=True,
            )
            return None
        return request

    async def _accept(self, interaction: discord.Interaction):
        request = await self._resolve(interaction)
        if not request:
            return

        if not vacancies._club_is_free(request["club"]):
            _record_decision(
                request["id"],
                "RECHAZADA",
                interaction.user.id,
                "El club ya no estaba libre al intentar aceptar la solicitud.",
            )
            fresh = _request_by_id(request["id"])
            await interaction.response.edit_message(embed=admin_request_embed(fresh), view=None)
            await _notify_applicant(interaction.guild, fresh, "RECHAZADA")
            return

        current_club = APP.club_de(int(request["user_id"]))
        if current_club:
            _record_decision(
                request["id"],
                "RECHAZADA",
                interaction.user.id,
                f"El solicitante ya estaba a cargo de {current_club}.",
            )
            fresh = _request_by_id(request["id"])
            await interaction.response.edit_message(embed=admin_request_embed(fresh), view=None)
            await _notify_applicant(interaction.guild, fresh, "RECHAZADA")
            return

        ok, result = teams.assign_team(int(request["user_id"]), request["club"])
        if not ok:
            await interaction.response.send_message(f"⚠️ {result}", ephemeral=True)
            return

        _stamp_assignment_admin(request["user_id"], request["club"], interaction.user.id)
        _record_decision(request["id"], "ACEPTADA", interaction.user.id)
        fresh = _request_by_id(request["id"])
        closed_ids = _close_conflicting_requests(fresh, interaction.user.id)

        await interaction.response.edit_message(embed=admin_request_embed(fresh), view=None)
        await _notify_applicant(interaction.guild, fresh, "ACEPTADA")
        for request_id in closed_ids:
            await _refresh_request_message(interaction.guild, request_id)

    async def _reject(self, interaction: discord.Interaction):
        request = await self._resolve(interaction)
        if not request:
            return
        if not _record_decision(request["id"], "RECHAZADA", interaction.user.id):
            await interaction.response.send_message("⚠️ La solicitud ya cambió de estado.", ephemeral=True)
            return
        fresh = _request_by_id(request["id"])
        await interaction.response.edit_message(embed=admin_request_embed(fresh), view=None)
        await _notify_applicant(interaction.guild, fresh, "RECHAZADA")

    async def _wait(self, interaction: discord.Interaction):
        request = await self._resolve(interaction)
        if not request:
            return
        if (request["status"] or "").upper() == "EN_ESPERA":
            await interaction.response.send_message("⏸️ Esta solicitud ya está en espera.", ephemeral=True)
            return
        if not _record_decision(request["id"], "EN_ESPERA", interaction.user.id):
            await interaction.response.send_message("⚠️ La solicitud ya cambió de estado.", ephemeral=True)
            return
        fresh = _request_by_id(request["id"])
        await interaction.response.edit_message(
            embed=admin_request_embed(fresh),
            view=VacancyAdminDecisionView("EN_ESPERA"),
        )
        await _notify_applicant(interaction.guild, fresh, "EN_ESPERA")


async def _notify_admins(guild, request_id: int, club: str, user) -> int:
    """Send actionable card to Staff channel and informational DMs to admins."""
    if guild is None:
        return 0

    request = _request_by_id(request_id)
    if not request:
        return 0

    delivered = 0
    staff_channel = await vacancies._staff_report_channel(guild)
    if staff_channel is not None:
        try:
            message = await staff_channel.send(
                embed=admin_request_embed(request),
                view=VacancyAdminDecisionView(request["status"]),
            )
            _store_staff_message(request_id, staff_channel.id, message.id)
            delivered += 1
        except (discord.Forbidden, discord.HTTPException):
            pass

    # Admin DMs are informational. The actionable buttons live in the Staff
    # channel so the correct guild-isolated database is always selected.
    recipients = {}
    owner = getattr(guild, "owner", None)
    if owner is not None and not owner.bot:
        recipients[owner.id] = owner
    for member in getattr(guild, "members", []):
        try:
            if not member.bot and member.guild_permissions.administrator:
                recipients[member.id] = member
        except AttributeError:
            continue

    dm_embed = admin_request_embed(request)
    dm_embed.set_footer(text="Resolver con Aceptar / Rechazar / Poner en espera desde el canal Staff/PES")
    for member in recipients.values():
        try:
            await member.send(embed=dm_embed)
            delivered += 1
        except (discord.Forbidden, discord.HTTPException):
            pass

    return delivered


def apply_free_team_admin_decision_patch(runtime, bot):
    global APP, BOT
    APP = runtime
    BOT = bot

    if getattr(runtime, "_ajap_free_team_admin_decision_patch", False):
        return

    _ensure_schema()

    # Existing apply button resolves these globals at click time, so replacing
    # them upgrades the current vacancy flow without rebuilding public messages.
    vacancies._request_exists = _request_exists
    vacancies._notify_admins = _notify_admins

    try:
        BOT.add_view(VacancyAdminDecisionView())
    except ValueError:
        pass

    runtime.VacancyAdminDecisionView = VacancyAdminDecisionView
    runtime.free_team_admin_request_embed = admin_request_embed
    runtime._ajap_free_team_admin_decision_patch = True

    print(
        "AJAP decisiones de vacante activas: Aceptar + Rechazar + En espera + "
        "auditoría de admin/fecha/hora"
    )
