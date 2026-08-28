"""Persistent market-channel access independent from the active DT role.

Problem this solves:
- The Discord role DT represents an active manager.
- Resigning correctly removes DT.
- But some servers use DT as the only role allowed to see #mercado, so resigning
  also locks the user out of the bot and makes choosing another club painful.

Final model:
- DT = currently managing a club.
- MERCADO = may enter/use the interactive market channel.
- MERCADO survives resignation/unlinking and club changes.
- Existing/current/former DTs are migrated automatically to MERCADO.
- /canal_mercado grants channel access to MERCADO, not to @everyone.

This patch is intentionally loaded after the final DT/identity patches. It
replaces the permission-repair helpers in market_usage_channel_patch; listeners
and /canal_mercado already registered there resolve those helper names at runtime,
so they immediately use this policy without duplicate commands/listeners.
"""

from __future__ import annotations

import asyncio

import discord

import dt_role_patch as dt_roles
import guild_isolation_patch as guild_isolation
import market_usage_channel_patch as market_usage
import team_assignment as teams


APP = None
BOT = None
ACCESS_ROLE_NAME = "MERCADO"
_SYNC_TASKS: set[asyncio.Task] = set()


def _guild_context(guild_id: int):
    return guild_isolation.guild_context(int(guild_id))


def _ensure_schema():
    with APP.db() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS market_access_role_config (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                role_id INTEGER,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )


def _stored_role_id():
    _ensure_schema()
    with APP.db() as conn:
        row = conn.execute(
            "SELECT role_id FROM market_access_role_config WHERE id = 1"
        ).fetchone()
    return int(row["role_id"]) if row and row["role_id"] else None


def _store_role_id(role_id: int):
    _ensure_schema()
    with APP.db() as conn:
        conn.execute(
            """
            INSERT INTO market_access_role_config (id, role_id, updated_at)
            VALUES (1, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(id) DO UPDATE SET
                role_id = excluded.role_id,
                updated_at = CURRENT_TIMESTAMP
            """,
            (int(role_id),),
        )


def _configured_role(guild: discord.Guild):
    role_id = None
    try:
        with _guild_context(guild.id):
            role_id = _stored_role_id()
    except Exception:
        role_id = None
    if role_id:
        role = guild.get_role(int(role_id))
        if role is not None and not role.managed:
            return role

    wanted = ACCESS_ROLE_NAME.casefold()
    return next(
        (
            role
            for role in guild.roles
            if not role.managed and (role.name or "").strip().casefold() == wanted
        ),
        None,
    )


async def _ensure_access_role(guild: discord.Guild):
    role = _configured_role(guild)
    if role is not None:
        try:
            with _guild_context(guild.id):
                _store_role_id(role.id)
        except Exception:
            pass
        return role

    me = guild.me
    if me is None or not me.guild_permissions.manage_roles:
        print(
            "WARNING AJAP acceso mercado: falta Administrar roles para crear MERCADO "
            f"guild={guild.id}"
        )
        return None

    try:
        role = await guild.create_role(
            name=ACCESS_ROLE_NAME,
            permissions=discord.Permissions.none(),
            hoist=False,
            mentionable=False,
            reason="AJAP: acceso persistente al canal del mercado",
        )
    except (discord.Forbidden, discord.HTTPException) as exc:
        print(
            "WARNING AJAP acceso mercado: no pude crear rol MERCADO "
            f"guild={guild.id} error={type(exc).__name__}: {exc}"
        )
        return None

    try:
        with _guild_context(guild.id):
            _store_role_id(role.id)
    except Exception as exc:
        print(
            "WARNING AJAP acceso mercado: rol creado pero no pude guardar id "
            f"guild={guild.id} role={role.id} error={type(exc).__name__}: {exc}"
        )
    print(f"AJAP acceso mercado: rol MERCADO listo guild={guild.id} role={role.id}")
    return role


async def _member(guild: discord.Guild, user_id: int):
    member = guild.get_member(int(user_id))
    if member is not None:
        return member
    try:
        return await guild.fetch_member(int(user_id))
    except (discord.NotFound, discord.Forbidden, discord.HTTPException):
        return None


async def grant_market_access(guild: discord.Guild, user_id: int, *, reason: str):
    if guild is None:
        return False
    member = await _member(guild, int(user_id))
    if member is None or member.bot:
        return False
    role = await _ensure_access_role(guild)
    if role is None:
        return False
    if role in member.roles:
        return True

    me = guild.me
    if me is None or not me.guild_permissions.manage_roles or role >= me.top_role:
        print(
            "WARNING AJAP acceso mercado: no puedo asignar rol por permisos/jerarquía "
            f"guild={guild.id} user={user_id} role={role.id}"
        )
        return False
    try:
        await member.add_roles(role, reason=reason)
        print(
            "AJAP acceso mercado: rol MERCADO otorgado "
            f"guild={guild.id} user={user_id}"
        )
        return True
    except (discord.Forbidden, discord.HTTPException) as exc:
        print(
            "WARNING AJAP acceso mercado: no pude otorgar MERCADO "
            f"guild={guild.id} user={user_id} error={type(exc).__name__}: {exc}"
        )
        return False


def _market_permissions(overwrite: discord.PermissionOverwrite):
    changed = False
    for name in (
        "view_channel",
        "send_messages",
        "read_message_history",
        "use_application_commands",
    ):
        if getattr(overwrite, name) is not True:
            setattr(overwrite, name, True)
            changed = True
    return changed


def _looks_like_old_bot_member_overwrite(overwrite: discord.PermissionOverwrite):
    """Identify the exact 4-permission individual allow created by the old hotfix."""
    expected = {
        "view_channel",
        "send_messages",
        "read_message_history",
        "use_application_commands",
    }
    enabled = set()
    other = False
    for name, value in overwrite:
        if value is None:
            continue
        if name in expected and value is True:
            enabled.add(name)
        else:
            other = True
    return enabled == expected and not other


async def _repair_channel_permissions(
    guild: discord.Guild,
    channel_id: int,
    *,
    reason: str,
):
    """Restrict the market to MERCADO while keeping it independent from DT."""
    channel = await market_usage._resolve_text_channel(guild, int(channel_id))
    if channel is None:
        return False

    me = guild.me
    if me is None or not channel.permissions_for(me).manage_channels:
        print(
            "WARNING AJAP acceso mercado: necesito Administrar canales "
            f"guild={guild.id} channel={channel.id}"
        )
        return False

    access_role = await _ensure_access_role(guild)
    if access_role is None:
        return False

    # @everyone stays outside. The previous hotfix temporarily enabled these
    # permissions globally; clear those allows while explicitly hiding the channel.
    everyone = channel.overwrites_for(guild.default_role)
    everyone_changed = False
    if everyone.view_channel is not False:
        everyone.view_channel = False
        everyone_changed = True
    for name in ("send_messages", "read_message_history", "use_application_commands"):
        if getattr(everyone, name) is True:
            setattr(everyone, name, None)
            everyone_changed = True
    if everyone_changed:
        await channel.set_permissions(
            guild.default_role,
            overwrite=everyone,
            reason="AJAP: el acceso al mercado usa rol MERCADO, no @everyone",
        )

    access_overwrite = channel.overwrites_for(access_role)
    if _market_permissions(access_overwrite):
        await channel.set_permissions(
            access_role,
            overwrite=access_overwrite,
            reason=reason,
        )

    # Clean only the very specific individual overwrite produced by our previous
    # emergency fix. Custom/manual member overwrites are left untouched.
    for target, overwrite in list(channel.overwrites.items()):
        if not isinstance(target, discord.Member) or target.bot:
            continue
        if not _looks_like_old_bot_member_overwrite(overwrite):
            continue
        try:
            await channel.set_permissions(
                target,
                overwrite=None,
                reason="AJAP: migrar acceso individual antiguo al rol MERCADO",
            )
        except (discord.Forbidden, discord.HTTPException):
            pass

    print(
        "AJAP acceso mercado: permisos OK "
        f"guild={guild.id} channel={channel.id} role={access_role.id}"
    )
    return True


async def _ensure_member_access_via_role(
    guild: discord.Guild,
    channel: discord.TextChannel,
    member: discord.Member,
    *,
    reason: str,
):
    # market_usage's existing listeners call this helper for users that lose DT
    # or are currently clubless. We turn that into a persistent role grant instead
    # of creating per-user channel overwrites.
    return await grant_market_access(guild, member.id, reason=reason)


def _historical_manager_ids():
    with APP.db() as conn:
        try:
            rows = conn.execute(
                "SELECT DISTINCT user_id FROM club_assignment_history WHERE user_id IS NOT NULL"
            ).fetchall()
        except Exception:
            rows = []
    return {int(row["user_id"]) for row in rows}


def _active_manager_ids():
    with APP.db() as conn:
        try:
            rows = conn.execute(
                "SELECT DISTINCT user_id FROM clubs WHERE user_id IS NOT NULL"
            ).fetchall()
        except Exception:
            rows = []
    return {int(row["user_id"]) for row in rows}


async def _migrate_guild(guild: discord.Guild):
    role = await _ensure_access_role(guild)
    if role is None:
        return

    ids = set()
    try:
        with _guild_context(guild.id):
            ids.update(_historical_manager_ids())
            ids.update(_active_manager_ids())
    except Exception as exc:
        print(
            "WARNING AJAP acceso mercado: no pude leer managers históricos "
            f"guild={guild.id} error={type(exc).__name__}: {exc}"
        )

    # Current DT holders are also definitely eligible, even if old history is
    # incomplete after a reset/migration.
    try:
        with _guild_context(guild.id):
            dt_role = dt_roles._dt_role(guild)
    except Exception:
        dt_role = next(
            (r for r in guild.roles if (r.name or "").strip().casefold() == "dt"),
            None,
        )
    if dt_role is not None:
        ids.update(member.id for member in dt_role.members if not member.bot)

    for user_id in ids:
        await grant_market_access(
            guild,
            user_id,
            reason="AJAP: migración automática de DT/manager al rol MERCADO",
        )

    channel_id = None
    try:
        with _guild_context(guild.id):
            channel_id = market_usage.get_market_channel_id(guild.id)
    except Exception:
        channel_id = None
    if channel_id:
        await _repair_channel_permissions(
            guild,
            int(channel_id),
            reason="AJAP: permitir mercado al rol MERCADO",
        )


async def _on_ready_market_access():
    if BOT is None:
        return
    for guild in BOT.guilds:
        try:
            await _migrate_guild(guild)
        except Exception as exc:
            print(
                "WARNING AJAP acceso mercado: migración on_ready falló "
                f"guild={guild.id} error={type(exc).__name__}: {exc}"
            )


def _schedule_access_for_current_guild(user_id: int, reason: str):
    if BOT is None:
        return
    try:
        guild_id = int(guild_isolation._CURRENT_GUILD_ID.get())
    except Exception:
        return
    guild = BOT.get_guild(guild_id)
    if guild is None:
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return
    task = loop.create_task(grant_market_access(guild, int(user_id), reason=reason))
    _SYNC_TASKS.add(task)
    task.add_done_callback(_SYNC_TASKS.discard)


def _wrap_assignment():
    current = teams.assign_team
    if getattr(current, "_ajap_market_access_role", False):
        return

    def assign_team_with_market_access(user_id, team_name):
        result = current(user_id, team_name)
        try:
            ok = bool(result[0])
        except Exception:
            ok = False
        if ok:
            _schedule_access_for_current_guild(
                int(user_id),
                "AJAP: acceso al mercado conservado al asignar club",
            )
        return result

    assign_team_with_market_access._ajap_market_access_role = True
    assign_team_with_market_access._ajap_market_access_role_base = current
    teams.assign_team = assign_team_with_market_access


def _wrap_dt_lifecycle():
    grant_base = dt_roles._grant_dt
    if not getattr(grant_base, "_ajap_market_access_role", False):
        async def grant_dt_with_market_access(guild, user_id: int, reason: str):
            # Market access is independent: even if DT assignment later fails,
            # the participant can still enter the bot/channel and resolve it.
            await grant_market_access(
                guild,
                int(user_id),
                reason="AJAP: participante habilitado para usar el mercado",
            )
            return await grant_base(guild, user_id, reason)

        grant_dt_with_market_access._ajap_market_access_role = True
        grant_dt_with_market_access._ajap_market_access_role_base = grant_base
        dt_roles._grant_dt = grant_dt_with_market_access

    remove_base = dt_roles._remove_dt
    if not getattr(remove_base, "_ajap_market_access_role", False):
        async def remove_dt_keep_market_access(
            guild,
            user_id: int,
            reason: str,
            *,
            require_config=False,
        ):
            # Grant/verify MERCADO before removing DT so there is never a moment
            # where a resignation locks the member out of the channel.
            await grant_market_access(
                guild,
                int(user_id),
                reason="AJAP: conservar acceso al mercado al dejar un club",
            )
            return await remove_base(
                guild,
                user_id,
                reason,
                require_config=require_config,
            )

        remove_dt_keep_market_access._ajap_market_access_role = True
        remove_dt_keep_market_access._ajap_market_access_role_base = remove_base
        dt_roles._remove_dt = remove_dt_keep_market_access


def apply_market_access_role_patch(runtime, bot):
    global APP, BOT
    APP = runtime
    BOT = bot
    if getattr(runtime, "_ajap_market_access_role_patch", False):
        return

    # Replace the old emergency policy (@everyone/per-member overwrites) with the
    # persistent MERCADO role policy. Existing listeners/commands use these names.
    market_usage._repair_market_channel_permissions = _repair_channel_permissions
    market_usage._ensure_member_market_access = _ensure_member_access_via_role
    runtime.repair_market_channel_permissions = _repair_channel_permissions

    _wrap_dt_lifecycle()
    _wrap_assignment()
    bot.add_listener(_on_ready_market_access, "on_ready")

    runtime.grant_market_access = grant_market_access
    runtime.market_access_role = _configured_role
    runtime._ajap_market_access_role_patch = True
    print(
        "AJAP acceso mercado separado: MERCADO persiste | DT solo representa club activo"
    )


# Loaded after the final guild-isolation wrappers. Apply immediately through the
# same wrapper chain when run_bot initializes runtime/bot.
_original_apply_guild_isolation = guild_isolation.apply_guild_isolation_patch


def _apply_guild_isolation_then_market_access(runtime, bot):
    _original_apply_guild_isolation(runtime, bot)
    apply_market_access_role_patch(runtime, bot)


if not getattr(
    guild_isolation.apply_guild_isolation_patch,
    "_ajap_market_access_role_wrapped",
    False,
):
    _apply_guild_isolation_then_market_access._ajap_market_access_role_wrapped = True
    guild_isolation.apply_guild_isolation_patch = _apply_guild_isolation_then_market_access
