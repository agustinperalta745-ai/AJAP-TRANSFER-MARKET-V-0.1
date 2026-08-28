"""Automatic 24h SQLite backups and admin restore picker for AJAP."""

from __future__ import annotations

import asyncio
import os
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import discord

import guild_isolation_patch as guild_isolation
import staff_admin_organized_patch as staff_admin


BACKUP_INTERVAL_SECONDS = 24 * 60 * 60
CHECK_INTERVAL_SECONDS = 5 * 60
MAX_BACKUPS_PER_GUILD = 25
LOCAL_TZ = ZoneInfo("America/Argentina/Buenos_Aires")

APP = None
BOT = None
_BACKUP_TASK = None


def _app():
    return APP or staff_admin.APP


def _backup_dir(runtime, guild_id: int) -> Path:
    db_path = Path(runtime.guild_db_path(int(guild_id))).resolve()
    return db_path.parent / "ajap_backups" / f"guild_{int(guild_id)}"


def _all_backups(runtime, guild_id: int):
    folder = _backup_dir(runtime, guild_id)
    if not folder.exists():
        return []
    files = [
        path for path in folder.glob("*.sqlite3")
        if path.is_file() and path.name.startswith(("daily_", "manual_", "pre_restore_"))
    ]
    return sorted(files, key=lambda path: path.stat().st_mtime, reverse=True)


def _daily_backups(runtime, guild_id: int):
    return [path for path in _all_backups(runtime, guild_id) if path.name.startswith("daily_")]


def _backup_kind(path: Path) -> str:
    if path.name.startswith("pre_restore_"):
        return "Seguridad pre-restauración"
    if path.name.startswith("manual_"):
        return "Manual"
    return "Automático 24 h"


def _backup_datetime(path: Path):
    try:
        stem = path.stem
        for prefix in ("pre_restore_", "daily_", "manual_"):
            if stem.startswith(prefix):
                stem = stem[len(prefix):]
                break
        return datetime.strptime(stem, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
    except ValueError:
        return datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)


def _format_backup(path: Path) -> str:
    return _backup_datetime(path).astimezone(LOCAL_TZ).strftime("%d/%m/%Y • %H:%M")


def _size_text(path: Path) -> str:
    size = path.stat().st_size
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size / (1024 * 1024):.1f} MB"


def _verify_sqlite(path: Path):
    conn = sqlite3.connect(str(path))
    try:
        row = conn.execute("PRAGMA quick_check").fetchone()
        if not row or str(row[0]).lower() != "ok":
            raise RuntimeError(f"quick_check={row[0] if row else 'sin respuesta'}")
    finally:
        conn.close()


def _prune_backups(runtime, guild_id: int):
    for path in _all_backups(runtime, guild_id)[MAX_BACKUPS_PER_GUILD:]:
        try:
            path.unlink()
        except OSError as exc:
            print(f"WARNING AJAP BACKUP: no pude borrar {path.name}: {exc}")


def _create_backup_sync(runtime, guild_id: int, kind="daily", *, prune=True) -> Path:
    guild_id = int(guild_id)
    # Hace existir la DB per-guild antes de resolver/copiar el archivo.
    conn = runtime.db_for_guild(guild_id)
    conn.close()

    source_path = Path(runtime.guild_db_path(guild_id)).resolve()
    if not source_path.exists():
        raise RuntimeError(f"DB del servidor no encontrada: {source_path}")

    folder = _backup_dir(runtime, guild_id)
    folder.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    prefix = {"manual": "manual", "pre_restore": "pre_restore"}.get(kind, "daily")
    final_path = folder / f"{prefix}_{stamp}.sqlite3"
    temp_path = final_path.with_suffix(".sqlite3.tmp")
    if temp_path.exists():
        temp_path.unlink()

    source = sqlite3.connect(str(source_path), timeout=15)
    dest = sqlite3.connect(str(temp_path), timeout=15)
    try:
        source.execute("PRAGMA busy_timeout=15000")
        dest.execute("PRAGMA busy_timeout=15000")
        source.backup(dest)
        dest.commit()
    finally:
        dest.close()
        source.close()

    try:
        _verify_sqlite(temp_path)
        os.replace(temp_path, final_path)
    except Exception:
        if temp_path.exists():
            temp_path.unlink()
        raise

    if prune:
        _prune_backups(runtime, guild_id)
    return final_path


def _backup_due(runtime, guild_id: int) -> bool:
    daily = _daily_backups(runtime, guild_id)
    if not daily:
        return True
    age = datetime.now(timezone.utc).timestamp() - daily[0].stat().st_mtime
    return age >= BACKUP_INTERVAL_SECONDS


def _resolve_backup(runtime, guild_id: int, filename: str) -> Path:
    allowed = {path.name: path for path in _all_backups(runtime, guild_id)}
    path = allowed.get(str(filename))
    if path is None:
        raise RuntimeError("Ese backup ya no está disponible.")
    resolved = path.resolve()
    if resolved.parent != _backup_dir(runtime, guild_id).resolve():
        raise RuntimeError("Ruta de backup inválida.")
    return resolved


def _restore_backup_sync(runtime, guild_id: int, filename: str, admin_id: int):
    guild_id = int(guild_id)
    selected = _resolve_backup(runtime, guild_id, filename)
    _verify_sqlite(selected)

    # Siempre guarda el estado exacto inmediatamente anterior a la restauración.
    safety = _create_backup_sync(runtime, guild_id, kind="pre_restore", prune=False)
    live_path = Path(runtime.guild_db_path(guild_id)).resolve()

    source = sqlite3.connect(str(selected), timeout=20)
    dest = sqlite3.connect(str(live_path), timeout=20)
    try:
        source.execute("PRAGMA busy_timeout=20000")
        dest.execute("PRAGMA busy_timeout=20000")
        source.backup(dest)
        dest.commit()
        row = dest.execute("PRAGMA quick_check").fetchone()
        if not row or str(row[0]).lower() != "ok":
            raise RuntimeError("La DB restaurada no pasó quick_check.")
        dest.execute(
            """
            CREATE TABLE IF NOT EXISTS backup_restore_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                backup_file TEXT NOT NULL,
                safety_backup_file TEXT,
                restored_by INTEGER NOT NULL,
                restored_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        dest.execute(
            """
            INSERT INTO backup_restore_history
            (guild_id, backup_file, safety_backup_file, restored_by)
            VALUES (?, ?, ?, ?)
            """,
            (guild_id, selected.name, safety.name, int(admin_id)),
        )
        dest.commit()
    finally:
        dest.close()
        source.close()

    _prune_backups(runtime, guild_id)
    return selected, safety


async def _backup_due_guilds():
    runtime = _app()
    if runtime is None or BOT is None:
        return
    for guild in list(getattr(BOT, "guilds", []) or []):
        try:
            if _backup_due(runtime, guild.id):
                path = await asyncio.to_thread(_create_backup_sync, runtime, int(guild.id), "daily")
                print(f"AJAP BACKUP 24H creado: guild={guild.id} • {path.name}")
        except Exception as exc:
            print(
                "WARNING AJAP BACKUP: "
                f"guild={getattr(guild, 'id', '?')} {type(exc).__name__}: {exc}"
            )


async def _backup_loop():
    while True:
        await _backup_due_guilds()
        await asyncio.sleep(CHECK_INTERVAL_SECONDS)


async def _start_backup_loop():
    global _BACKUP_TASK
    await _backup_due_guilds()
    if _BACKUP_TASK is None or _BACKUP_TASK.done():
        _BACKUP_TASK = asyncio.create_task(_backup_loop(), name="ajap-24h-backups")


def backup_home_embed(guild_id: int):
    runtime = _app()
    backups = _all_backups(runtime, guild_id)[:25] if runtime else []
    embed = discord.Embed(
        title="💾 BACKUPS • ESTE SERVIDOR",
        description=(
            "AJAP guarda una copia completa de la base de este servidor cada **24 horas** "
            "en el mismo volumen persistente de Railway."
        ),
        color=discord.Color.blurple(),
    )
    embed.add_field(
        name="📚 Copias disponibles",
        value=f"{len(backups)} backup(s) • se conservan los últimos {MAX_BACKUPS_PER_GUILD}",
        inline=False,
    )
    embed.add_field(
        name="♻️ Restaurar",
        value=(
            "Elegí una copia del selector. Antes de cargarla vas a ver una advertencia "
            "y una confirmación final. Al restaurar también se crea una copia de seguridad "
            "del estado actual."
        ),
        inline=False,
    )
    embed.add_field(
        name="⚠️ Qué vuelve atrás",
        value=(
            "La restauración reemplaza **toda la SQLite de este servidor** por la copia: "
            "planteles, mercado, economía, asignaciones, Liga y configuraciones guardadas "
            "en la base vuelven al estado de esa fecha."
        ),
        inline=False,
    )
    embed.set_footer(text="Los escudos/emojis de Discord no se modifican")
    return embed


class BackupSelect(discord.ui.Select):
    def __init__(self, guild_id: int, backups):
        self.guild_id = int(guild_id)
        options = [
            discord.SelectOption(
                label=_format_backup(path)[:100],
                description=f"{_backup_kind(path)} • {_size_text(path)}"[:100],
                value=path.name,
                emoji="💾",
            )
            for path in backups[:25]
        ]
        super().__init__(
            placeholder="Elegí el backup que querés cargar",
            min_values=1,
            max_values=1,
            options=options,
            row=0,
        )

    async def callback(self, interaction: discord.Interaction):
        runtime = _app()
        if not runtime or not runtime.es_admin(interaction):
            await interaction.response.send_message("⛔ Solo administradores.", ephemeral=True)
            return
        try:
            path = _resolve_backup(runtime, self.guild_id, self.values[0])
        except Exception as exc:
            await interaction.response.send_message(f"⚠️ {exc}", ephemeral=True)
            return

        embed = discord.Embed(
            title="⚠️ RESTAURAR BACKUP",
            description=(
                f"Seleccionaste la copia del **{_format_backup(path)}**.\n\n"
                "**Todavía no se restauró nada.**"
            ),
            color=discord.Color.orange(),
        )
        embed.add_field(name="Tipo", value=_backup_kind(path), inline=True)
        embed.add_field(name="Tamaño", value=_size_text(path), inline=True)
        embed.add_field(
            name="Qué va a pasar",
            value=(
                "La base actual de este servidor será reemplazada por el estado de esa copia. "
                "Todo lo ocurrido después de esa fecha dejará de ser el estado activo."
            ),
            inline=False,
        )
        embed.add_field(
            name="🛟 Seguridad automática",
            value=(
                "Justo antes de restaurar, AJAP creará un backup adicional del estado actual "
                "para que puedas volver atrás si hiciera falta."
            ),
            inline=False,
        )
        await interaction.response.edit_message(
            content=None,
            embeds=[embed],
            view=RestoreFirstConfirmView(self.guild_id, path.name),
        )


class CreateBackupNowButton(discord.ui.Button):
    def __init__(self, guild_id: int, row=1):
        self.guild_id = int(guild_id)
        super().__init__(
            label="CREAR BACKUP AHORA",
            emoji="💾",
            style=discord.ButtonStyle.secondary,
            row=row,
        )

    async def callback(self, interaction: discord.Interaction):
        runtime = _app()
        if not runtime or not runtime.es_admin(interaction):
            await interaction.response.send_message("⛔ Solo administradores.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            path = await asyncio.to_thread(_create_backup_sync, runtime, self.guild_id, "manual")
        except Exception as exc:
            await interaction.edit_original_response(
                content=f"❌ No se pudo crear el backup: `{type(exc).__name__}: {str(exc)[:500]}`",
                embeds=[],
                view=BackupMenuView(self.guild_id),
            )
            return
        await interaction.edit_original_response(
            content=f"✅ Backup creado: **{_format_backup(path)}** • {_size_text(path)}",
            embeds=[backup_home_embed(self.guild_id)],
            view=BackupMenuView(self.guild_id),
        )


class BackToManagementButton(discord.ui.Button):
    def __init__(self, row=1):
        super().__init__(
            label="VOLVER A GESTIÓN",
            emoji="⬅️",
            style=discord.ButtonStyle.secondary,
            row=row,
        )

    async def callback(self, interaction: discord.Interaction):
        runtime = _app()
        if not runtime or not runtime.es_admin(interaction):
            await interaction.response.send_message("⛔ Solo administradores.", ephemeral=True)
            return
        await interaction.response.edit_message(
            content=None,
            embeds=[
                staff_admin.section_embed(
                    "⚙️ GESTIÓN",
                    "Configuración general del torneo y del mercado.",
                    [
                        "👥 Asignaciones",
                        "🗓️ Cambiar temporada",
                        "📤 Exportar mercado",
                        "🚨 Reset V1",
                        "💾 Backups 24 h",
                    ],
                )
            ],
            view=staff_admin.ManagementView(),
        )


class BackToBackupsButton(discord.ui.Button):
    def __init__(self, guild_id: int, row=0):
        self.guild_id = int(guild_id)
        super().__init__(
            label="CANCELAR / VOLVER",
            emoji="✖️",
            style=discord.ButtonStyle.secondary,
            row=row,
        )

    async def callback(self, interaction: discord.Interaction):
        runtime = _app()
        if not runtime or not runtime.es_admin(interaction):
            await interaction.response.send_message("⛔ Solo administradores.", ephemeral=True)
            return
        await interaction.response.edit_message(
            content=None,
            embeds=[backup_home_embed(self.guild_id)],
            view=BackupMenuView(self.guild_id),
        )


class BackupMenuView(discord.ui.View):
    def __init__(self, guild_id: int):
        super().__init__(timeout=300)
        runtime = _app()
        backups = _all_backups(runtime, guild_id)[:25] if runtime else []
        if backups:
            self.add_item(BackupSelect(guild_id, backups))
        self.add_item(CreateBackupNowButton(guild_id, row=1))
        self.add_item(BackToManagementButton(row=1))


class RestoreFirstConfirmView(discord.ui.View):
    def __init__(self, guild_id: int, filename: str):
        super().__init__(timeout=120)
        self.guild_id = int(guild_id)
        self.filename = str(filename)

        proceed = discord.ui.Button(
            label="CONTINUAR",
            emoji="⚠️",
            style=discord.ButtonStyle.danger,
            row=0,
        )
        proceed.callback = self._proceed
        self.add_item(proceed)
        self.add_item(BackToBackupsButton(guild_id, row=0))

    async def _proceed(self, interaction: discord.Interaction):
        runtime = _app()
        if not runtime or not runtime.es_admin(interaction):
            await interaction.response.send_message("⛔ Solo administradores.", ephemeral=True)
            return
        try:
            path = _resolve_backup(runtime, self.guild_id, self.filename)
        except Exception as exc:
            await interaction.response.send_message(f"⚠️ {exc}", ephemeral=True)
            return
        embed = discord.Embed(
            title="⛔ ÚLTIMA CONFIRMACIÓN • CARGAR BACKUP",
            description=(
                f"Vas a reemplazar el estado actual por el backup del **{_format_backup(path)}**.\n\n"
                "Los cambios posteriores a esa copia dejarán de estar activos."
            ),
            color=discord.Color.red(),
        )
        embed.add_field(
            name="🛟 Antes de hacerlo",
            value="AJAP guardará automáticamente una copia del estado actual.",
            inline=False,
        )
        embed.add_field(
            name="Acción",
            value="Solo se ejecuta al presionar **SÍ, CARGAR ESTE BACKUP**.",
            inline=False,
        )
        await interaction.response.edit_message(
            content=None,
            embeds=[embed],
            view=RestoreFinalConfirmView(self.guild_id, path.name),
        )


class RestoreFinalConfirmView(discord.ui.View):
    def __init__(self, guild_id: int, filename: str):
        super().__init__(timeout=90)
        self.guild_id = int(guild_id)
        self.filename = str(filename)

        confirm = discord.ui.Button(
            label="SÍ, CARGAR ESTE BACKUP",
            emoji="♻️",
            style=discord.ButtonStyle.danger,
            row=0,
        )
        confirm.callback = self._confirm
        self.add_item(confirm)
        self.add_item(BackToBackupsButton(guild_id, row=0))

    async def _confirm(self, interaction: discord.Interaction):
        runtime = _app()
        if not runtime or not runtime.es_admin(interaction):
            await interaction.response.send_message("⛔ Solo administradores.", ephemeral=True)
            return
        if not interaction.guild_id or int(interaction.guild_id) != self.guild_id:
            await interaction.response.send_message(
                "⚠️ Este backup pertenece a otro contexto de servidor.", ephemeral=True
            )
            return

        await interaction.response.defer(ephemeral=True, thinking=True)
        try:
            selected, safety = await asyncio.to_thread(
                _restore_backup_sync,
                runtime,
                self.guild_id,
                self.filename,
                int(interaction.user.id),
            )
        except Exception as exc:
            await interaction.edit_original_response(
                content=None,
                embeds=[
                    discord.Embed(
                        title="❌ NO SE PUDO RESTAURAR",
                        description=f"`{type(exc).__name__}: {str(exc)[:700]}`",
                        color=discord.Color.red(),
                    )
                ],
                view=BackupMenuView(self.guild_id),
            )
            return

        embed = discord.Embed(
            title="✅ BACKUP RESTAURADO",
            description=f"Este servidor volvió al estado del **{_format_backup(selected)}**.",
            color=discord.Color.green(),
        )
        embed.add_field(
            name="🛟 Copia previa guardada",
            value=f"{_format_backup(safety)} • {_size_text(safety)}",
            inline=False,
        )
        embed.set_footer(text=f"Restaurado por {interaction.user.display_name}")
        await interaction.edit_original_response(
            content=None,
            embeds=[embed],
            view=BackupMenuView(self.guild_id),
        )


class BackupAdminButton(discord.ui.Button):
    def __init__(self, row=1):
        super().__init__(
            label="BACKUPS",
            emoji="💾",
            style=discord.ButtonStyle.secondary,
            row=row,
            custom_id="ajap_admin_backups",
        )

    async def callback(self, interaction: discord.Interaction):
        runtime = _app()
        if not runtime or not runtime.es_admin(interaction):
            await interaction.response.send_message("⛔ Solo administradores.", ephemeral=True)
            return
        if not interaction.guild_id:
            await interaction.response.send_message(
                "⚠️ Los backups solo están disponibles dentro de un servidor.", ephemeral=True
            )
            return
        await interaction.response.edit_message(
            content=None,
            embeds=[backup_home_embed(int(interaction.guild_id))],
            view=BackupMenuView(int(interaction.guild_id)),
        )


# Capa visual final de Administración -> Gestión.
_ORIGINAL_MANAGEMENT_VIEW = staff_admin.ManagementView
_ORIGINAL_SECTION_EMBED = staff_admin.section_embed


class ManagementViewWithBackups(_ORIGINAL_MANAGEMENT_VIEW):
    def __init__(self):
        super().__init__()
        self.add_item(BackupAdminButton(row=1))


ManagementViewWithBackups.__name__ = "ManagementView"
staff_admin.ManagementView = ManagementViewWithBackups


def _section_embed_with_backups(title, description, tools):
    tools = list(tools)
    if "GESTIÓN" in str(title).upper() and not any(
        "backup" in str(item).casefold() for item in tools
    ):
        tools.append("💾 Backups automáticos cada 24 h")
    return _ORIGINAL_SECTION_EMBED(title, description, tools)


staff_admin.section_embed = _section_embed_with_backups


def apply_automatic_backup_patch(runtime, bot):
    global APP, BOT
    APP = runtime
    BOT = bot
    if getattr(runtime, "_ajap_automatic_backup_patch", False):
        return

    bot.add_listener(_start_backup_loop, "on_ready")
    runtime._ajap_automatic_backup_patch = True
    print(
        "AJAP backups activos: cada 24h por guild + últimos "
        f"{MAX_BACKUPS_PER_GUILD} + selector de restauración Staff"
    )


_original_apply_guild_isolation_patch = guild_isolation.apply_guild_isolation_patch


def _apply_guild_isolation_then_backups(runtime, bot):
    _original_apply_guild_isolation_patch(runtime, bot)
    apply_automatic_backup_patch(runtime, bot)


if not getattr(
    guild_isolation.apply_guild_isolation_patch,
    "_ajap_automatic_backup_wrapped",
    False,
):
    _apply_guild_isolation_then_backups._ajap_automatic_backup_wrapped = True
    guild_isolation.apply_guild_isolation_patch = _apply_guild_isolation_then_backups
