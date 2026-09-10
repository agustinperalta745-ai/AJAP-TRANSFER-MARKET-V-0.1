"""Shared AJPA season-closing countdown for Discord and AJPA Mobile.

There is exactly one deadline per current season. The deadline is stored in the
same persistent SQLite database used by the competition cycle, so Discord and
the mobile app always read the same value. Admins may move the deadline, but the
countdown itself never advances/ends the competition automatically.
"""

from __future__ import annotations

import re
import time
from datetime import datetime, timezone
from http import HTTPStatus
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import discord

import competition_cycle as cycle
import guild_isolation_patch as guild_isolation
import staff_admin_organized_patch as staff

ARGENTINA_TZ_NAME = "America/Argentina/Buenos_Aires"
ARGENTINA_TZ = ZoneInfo(ARGENTINA_TZ_NAME)


class CountdownError(RuntimeError):
    pass


def _table(conn, name: str) -> bool:
    return bool(
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
            (name,),
        ).fetchone()
    )


def ensure_schema(conn) -> None:
    cycle.ensure_schema(conn)
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS season_countdown_state (
            id INTEGER PRIMARY KEY CHECK(id=1),
            season_number INTEGER NOT NULL,
            deadline_utc INTEGER NOT NULL,
            updated_by INTEGER,
            updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS season_countdown_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            season_number INTEGER NOT NULL,
            old_deadline_utc INTEGER,
            new_deadline_utc INTEGER NOT NULL,
            changed_by INTEGER,
            changed_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """
    )


def _current_cycle(conn) -> tuple[str, int]:
    ensure_schema(conn)
    row = conn.execute(
        "SELECT phase,season_number FROM competition_cycle_state WHERE id=1"
    ).fetchone()
    if row:
        return str(row["phase"] or "season"), int(row["season_number"] or 1)

    # Compatibility only for a database created before competition_cycle_state.
    if _table(conn, "seasons"):
        row = conn.execute(
            "SELECT id,name FROM seasons WHERE active=1 ORDER BY id DESC LIMIT 1"
        ).fetchone()
        if row:
            match = re.search(r"(\d+)", str(row["name"] or ""))
            return "season", int(match.group(1)) if match else int(row["id"])
    return "season", 1


def _parse_local_deadline(date_text: str, time_text: str) -> datetime:
    raw_date = str(date_text or "").strip()
    raw_time = str(time_text or "").strip()
    if not raw_date or not raw_time:
        raise CountdownError("Completá la fecha y la hora del cierre.")

    parsed_date = None
    for fmt in ("%d/%m/%Y", "%Y-%m-%d"):
        try:
            parsed_date = datetime.strptime(raw_date, fmt).date()
            break
        except ValueError:
            continue
    if parsed_date is None:
        raise CountdownError("La fecha debe tener formato DD/MM/AAAA.")

    try:
        parsed_time = datetime.strptime(raw_time, "%H:%M").time()
    except ValueError as exc:
        raise CountdownError("La hora debe tener formato HH:MM (24 horas).") from exc

    return datetime.combine(parsed_date, parsed_time, tzinfo=ARGENTINA_TZ)


def countdown_payload(conn) -> dict:
    phase, season_number = _current_cycle(conn)
    row = conn.execute(
        "SELECT season_number,deadline_utc,updated_by,updated_at FROM season_countdown_state WHERE id=1"
    ).fetchone()

    if not row or int(row["season_number"]) != int(season_number):
        return {
            "configured": False,
            "season_number": int(season_number),
            "phase": phase,
            "deadline_utc": None,
            "deadline_iso": None,
            "deadline_local": None,
            "date": "",
            "time": "",
            "timezone": ARGENTINA_TZ_NAME,
            "remaining_seconds": None,
            "closed": False,
            "updated_at": None,
        }

    deadline_utc = int(row["deadline_utc"])
    now = int(time.time())
    local = datetime.fromtimestamp(deadline_utc, timezone.utc).astimezone(ARGENTINA_TZ)
    remaining = max(0, deadline_utc - now)
    return {
        "configured": True,
        "season_number": int(season_number),
        "phase": phase,
        "deadline_utc": deadline_utc,
        "deadline_iso": datetime.fromtimestamp(deadline_utc, timezone.utc).isoformat().replace("+00:00", "Z"),
        "deadline_local": local.strftime("%d/%m/%Y %H:%M"),
        "date": local.strftime("%d/%m/%Y"),
        "time": local.strftime("%H:%M"),
        "timezone": ARGENTINA_TZ_NAME,
        "remaining_seconds": remaining,
        "closed": deadline_utc <= now,
        "updated_at": str(row["updated_at"] or ""),
    }


def set_countdown(conn, user_id: int, date_text: str, time_text: str) -> dict:
    phase, season_number = _current_cycle(conn)
    local = _parse_local_deadline(date_text, time_text)
    deadline_utc = int(local.astimezone(timezone.utc).timestamp())
    if deadline_utc <= int(time.time()):
        raise CountdownError("El cierre tiene que ser una fecha y hora futura.")

    previous = conn.execute(
        "SELECT season_number,deadline_utc FROM season_countdown_state WHERE id=1"
    ).fetchone()
    old_deadline = None
    if previous and int(previous["season_number"]) == int(season_number):
        old_deadline = int(previous["deadline_utc"])

    conn.execute(
        """INSERT INTO season_countdown_state(id,season_number,deadline_utc,updated_by,updated_at)
           VALUES(1,?,?,?,CURRENT_TIMESTAMP)
           ON CONFLICT(id) DO UPDATE SET
             season_number=excluded.season_number,
             deadline_utc=excluded.deadline_utc,
             updated_by=excluded.updated_by,
             updated_at=CURRENT_TIMESTAMP""",
        (int(season_number), deadline_utc, int(user_id)),
    )
    conn.execute(
        """INSERT INTO season_countdown_history(
             season_number,old_deadline_utc,new_deadline_utc,changed_by
           ) VALUES(?,?,?,?)""",
        (int(season_number), old_deadline, deadline_utc, int(user_id)),
    )
    return countdown_payload(conn)


def runtime_payload(runtime) -> dict:
    with runtime.db() as conn:
        payload = countdown_payload(conn)
        conn.commit()
        return payload


def runtime_set(runtime, user_id: int, date_text: str, time_text: str) -> dict:
    conn = runtime.db()
    try:
        payload = set_countdown(conn, int(user_id), date_text, time_text)
        conn.commit()
        return payload
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _remaining_text(seconds: int | None) -> str:
    if seconds is None:
        return "SIN CONFIGURAR"
    safe = max(0, int(seconds))
    days, rest = divmod(safe, 86400)
    hours, rest = divmod(rest, 3600)
    minutes, secs = divmod(rest, 60)
    return f"{days}d {hours:02d}h {minutes:02d}m {secs:02d}s"


def countdown_embed(payload: dict) -> discord.Embed:
    number = int(payload.get("season_number") or 1)
    if not payload.get("configured"):
        embed = discord.Embed(
            title=f"⏳ CIERRE DE TEMPORADA {number}",
            description="Todavía no hay una fecha de cierre configurada.",
            color=discord.Color.orange(),
        )
        embed.set_footer(text="Un administrador puede configurarla desde Administración → Gestión.")
        return embed

    deadline = int(payload["deadline_utc"])
    closed = bool(payload.get("closed"))
    status = "🔴 **TEMPORADA CERRADA**" if closed else f"⏳ **{_remaining_text(payload.get('remaining_seconds'))}**"
    embed = discord.Embed(
        title=f"⏳ CIERRE DE TEMPORADA {number}",
        description=f"{status}\n\n📅 **{payload['deadline_local']} hs (Argentina)**\n🕒 <t:{deadline}:F>\n⏱️ <t:{deadline}:R>",
        color=discord.Color.red() if closed else discord.Color.blurple(),
    )
    embed.set_footer(text="Bot y app usan exactamente la misma fecha de cierre.")
    return embed


class CountdownModal(discord.ui.Modal):
    def __init__(self, runtime):
        super().__init__(title="Cierre de temporada")
        self.runtime = runtime
        current = runtime_payload(runtime)
        self.date_input = discord.ui.TextInput(
            label="Fecha (DD/MM/AAAA)",
            placeholder="Ej: 30/09/2026",
            default=str(current.get("date") or ""),
            max_length=10,
            required=True,
        )
        self.time_input = discord.ui.TextInput(
            label="Hora Argentina (HH:MM)",
            placeholder="Ej: 23:59",
            default=str(current.get("time") or ""),
            max_length=5,
            required=True,
        )
        self.add_item(self.date_input)
        self.add_item(self.time_input)

    async def on_submit(self, interaction: discord.Interaction):
        if not self.runtime.es_admin(interaction):
            await interaction.response.send_message("⛔ Solo administradores.", ephemeral=True)
            return
        try:
            payload = runtime_set(
                self.runtime,
                interaction.user.id,
                str(self.date_input.value),
                str(self.time_input.value),
            )
        except CountdownError as exc:
            await interaction.response.send_message(f"⚠️ {exc}", ephemeral=True)
            return
        await interaction.response.send_message(
            "✅ Cierre de temporada actualizado. El cambio ya es compartido por bot y app.",
            embed=countdown_embed(payload),
            ephemeral=True,
        )


class CountdownAdminButton(discord.ui.Button):
    def __init__(self, row=1):
        super().__init__(
            label="CIERRE DE TEMPORADA",
            emoji="⏳",
            style=discord.ButtonStyle.primary,
            row=row,
            custom_id="ajpa_admin_season_countdown",
        )

    async def callback(self, interaction: discord.Interaction):
        if not staff.APP or not staff.APP.es_admin(interaction):
            await interaction.response.send_message("⛔ Solo administradores.", ephemeral=True)
            return
        await interaction.response.send_modal(CountdownModal(staff.APP))


def _patch_admin_views() -> None:
    view = staff.ManagementView
    if getattr(view, "_ajpa_season_countdown", False):
        return
    original_init = view.__init__

    def init(self):
        original_init(self)
        if not any(
            str(getattr(item, "custom_id", "") or "") == "ajpa_admin_season_countdown"
            for item in self.children
        ):
            self.add_item(CountdownAdminButton(row=1))

    view.__init__ = init
    view._ajpa_season_countdown = True

    original_home = staff.admin_home_embed

    def admin_home_embed():
        embed = original_home()
        try:
            payload = runtime_payload(staff.APP)
            value = (
                "Sin configurar"
                if not payload.get("configured")
                else (
                    "🔴 Temporada cerrada"
                    if payload.get("closed")
                    else f"{_remaining_text(payload.get('remaining_seconds'))}\n{payload['deadline_local']} hs"
                )
            )
            embed.add_field(name="⏳ Cierre de temporada", value=value, inline=False)
        except Exception:
            pass
        return embed

    staff.admin_home_embed = admin_home_embed

    original_section = staff.section_embed

    def section_embed(title, description, tools):
        items = list(tools)
        if "gestión" in str(title).casefold() and not any(
            "cierre de temporada" in str(item).casefold() for item in items
        ):
            items.append("⏳ Cierre de temporada")
        return original_section(title, description, items)

    staff.section_embed = section_embed


def _install_discord(runtime, bot) -> None:
    runtime.season_countdown_state = lambda: runtime_payload(runtime)
    runtime.set_season_countdown = lambda user_id, date_text, time_text: runtime_set(
        runtime, user_id, date_text, time_text
    )

    if bot.tree.get_command("cierre") is None:
        @bot.tree.command(name="cierre", description="Muestra la cuenta regresiva del cierre de temporada")
        async def cierre(interaction: discord.Interaction):
            payload = runtime_payload(runtime)
            await interaction.response.send_message(embed=countdown_embed(payload))

    print("AJPA cierre de temporada: cuenta regresiva compartida BOT + APP habilitada")


def _patch_mobile_api() -> None:
    try:
        import mobile_read_api
        import mobile_write_api
    except Exception:
        return

    handler = mobile_read_api.MobileReadHandler
    if getattr(handler, "_ajpa_season_countdown", False):
        return

    original_get = handler.do_GET
    original_post = handler.do_POST

    def get(self):
        path = urlparse(self.path).path.rstrip("/") or "/"
        if path != "/api/v1/season-countdown":
            return original_get(self)
        try:
            with mobile_write_api.write_db() as conn:
                payload = countdown_payload(conn)
                can_edit = False
                raw_auth = str(self.headers.get("Authorization") or "").strip()
                if raw_auth:
                    try:
                        session = mobile_write_api._session(self.headers, conn)
                        can_edit = bool(session.get("is_staff"))
                    except mobile_write_api.ApiFailure:
                        can_edit = False
                payload["can_edit"] = can_edit
                conn.commit()
                self._json(payload)
                return
        except Exception as exc:
            print(f"AJPA countdown mobile GET error: {type(exc).__name__}: {exc}")
            self._json(
                {"error": "internal_error", "message": "No se pudo cargar el cierre de temporada."},
                HTTPStatus.INTERNAL_SERVER_ERROR,
            )

    def post(self):
        path = urlparse(self.path).path.rstrip("/") or "/"
        if path != "/api/v1/admin/season-countdown":
            return original_post(self)
        conn = None
        try:
            body = mobile_write_api._read_json(self)
            conn = mobile_write_api.write_db()
            session = mobile_write_api._session(self.headers, conn)
            if not session.get("is_staff"):
                raise mobile_write_api.ApiFailure(
                    "Solo administradores pueden modificar el cierre de temporada.",
                    HTTPStatus.FORBIDDEN,
                )
            payload = set_countdown(
                conn,
                int(session["user_id"]),
                str(body.get("date") or ""),
                str(body.get("time") or ""),
            )
            conn.commit()
            payload["can_edit"] = True
            self._json(payload)
            return
        except CountdownError as exc:
            if conn is not None:
                try:
                    conn.rollback()
                except Exception:
                    pass
            self._json({"error": "countdown", "message": str(exc)}, HTTPStatus.BAD_REQUEST)
        except mobile_write_api.ApiFailure as exc:
            if conn is not None:
                try:
                    conn.rollback()
                except Exception:
                    pass
            self._json({"error": "request", "message": exc.message}, exc.status)
        except Exception as exc:
            if conn is not None:
                try:
                    conn.rollback()
                except Exception:
                    pass
            print(f"AJPA countdown mobile POST error: {type(exc).__name__}: {exc}")
            self._json(
                {"error": "internal_error", "message": "No se pudo guardar el cierre de temporada."},
                HTTPStatus.INTERNAL_SERVER_ERROR,
            )
        finally:
            if conn is not None:
                conn.close()

    handler.do_GET = get
    handler.do_POST = post
    handler.do_PUT = post
    handler.do_PATCH = post
    handler._ajpa_season_countdown = True


_patch_admin_views()
_patch_mobile_api()

_original_apply_guild_isolation_patch = guild_isolation.apply_guild_isolation_patch


def _apply_guild_isolation_then_countdown(runtime, bot):
    _original_apply_guild_isolation_patch(runtime, bot)
    _install_discord(runtime, bot)


if not getattr(
    guild_isolation.apply_guild_isolation_patch,
    "_ajpa_season_countdown_wrapped",
    False,
):
    _apply_guild_isolation_then_countdown._ajpa_season_countdown_wrapped = True
    guild_isolation.apply_guild_isolation_patch = _apply_guild_isolation_then_countdown
