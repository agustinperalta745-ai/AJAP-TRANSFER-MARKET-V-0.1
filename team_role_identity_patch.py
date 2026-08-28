"""Automatic Discord club roles + manager identity for AJAP.

Final behaviour:
- Every JSON-backed club gets a Discord role automatically.
- Choosing/receiving a club grants that role and removes any old club role.
- Renouncing/admin-unlinking removes the club role.
- The existing ``Nombre | Club`` nickname stays synchronized.
- If the guild supports Discord ROLE_ICONS, the role uses the club's manual
  server emoji image as its display icon.
- On startup/reconnect, existing assignments are reconciled so Staff never has
  to create or assign club roles manually.

Club assignment in SQLite remains the source of truth. Discord roles/nicknames
are projections of that state, never the other way around.
"""

from __future__ import annotations

import asyncio

import discord

import guild_isolation_patch as guild_isolation
import json_team_selection_patch as json_selector
import member_nickname_patch as nicknames
import team_assignment as teams
import team_badge_selector_patch as badge_selector


APP = None
BOT = None
_SYNC_TASKS = set()


def _club_names():
    """Canonical selectable club names backed by the current JSON catalogue."""
    try:
        rows = json_selector._json_team_rows()
    except Exception as exc:
        print(f"WARNING AJAP roles: no se pudo leer catálogo JSON: {exc}")
        return []

    names = []
    seen = set()
    for row in rows:
        club = str(row.get("name") or "").strip()
        key = club.casefold()
        if not club or key in seen:
            continue
        seen.add(key)
        names.append(club)
    return names


def _managed_role_names():
    # Include badge aliases too so stale historical variants can be removed from
    # a member when the canonical JSON name changed (e.g. Sevilla -> Sevilla FC).
    names = set(_club_names())
    names.update(str(name) for name in badge_selector.MANUAL_EMOJI_NAMES)
    return {name.casefold() for name in names if str(name).strip()}


def _role_for_club(guild: discord.Guild, club: str):
    wanted = str(club).strip().casefold()
    return next(
        (
            role
            for role in guild.roles
            if not role.managed and role.name.casefold() == wanted
        ),
        None,
    )


def _bot_can_manage_role(guild: discord.Guild, role: discord.Role | None = None):
    me = guild.me
    if me is None or not me.guild_permissions.manage_roles:
        return False
    if role is not None and role.position >= me.top_role.position:
        return False
    return True


async def _club_icon_bytes(guild: discord.Guild, club: str):
    if "ROLE_ICONS" not in set(getattr(guild, "features", ())):
        return None
    emoji = badge_selector._manual_badge_emoji(guild, club)
    if emoji is None:
        return None
    try:
        return await emoji.read()
    except (discord.HTTPException, discord.NotFound, discord.Forbidden) as exc:
        print(
            "WARNING AJAP roles: no se pudo leer escudo para icono de rol | "
            f"guild={guild.id} club={club} error={type(exc).__name__}: {exc}"
        )
        return None


async def _ensure_club_role(guild: discord.Guild, club: str):
    role = _role_for_club(guild, club)
    if role is not None:
        # Add the badge later too if the server gained ROLE_ICONS after the role
        # had already been created.
        if (
            "ROLE_ICONS" in set(getattr(guild, "features", ()))
            and getattr(role, "display_icon", None) is None
            and _bot_can_manage_role(guild, role)
        ):
            icon = await _club_icon_bytes(guild, club)
            if icon:
                try:
                    role = await role.edit(
                        display_icon=icon,
                        reason=f"AJAP: escudo automático del club {club}",
                    )
                except (discord.Forbidden, discord.HTTPException, TypeError) as exc:
                    print(
                        "WARNING AJAP roles: no se pudo aplicar icono existente | "
                        f"guild={guild.id} club={club} error={type(exc).__name__}: {exc}"
                    )
        return role

    if not _bot_can_manage_role(guild):
        print(
            "WARNING AJAP roles: falta Administrar roles o jerarquía | "
            f"guild={guild.id} club={club}"
        )
        return None

    kwargs = {
        "name": str(club)[:100],
        "permissions": discord.Permissions.none(),
        "hoist": False,
        "mentionable": False,
        "reason": f"AJAP: rol automático para {club}",
    }
    icon = await _club_icon_bytes(guild, club)
    if icon:
        kwargs["display_icon"] = icon

    try:
        role = await guild.create_role(**kwargs)
    except (discord.HTTPException, TypeError) as exc:
        # Some guild/API combinations reject role icons even when the feature is
        # advertised. The role itself is more important, so retry without icon.
        if "display_icon" not in kwargs:
            print(
                "WARNING AJAP roles: no se pudo crear rol | "
                f"guild={guild.id} club={club} error={type(exc).__name__}: {exc}"
            )
            return None
        kwargs.pop("display_icon", None)
        try:
            role = await guild.create_role(**kwargs)
        except (discord.Forbidden, discord.HTTPException, TypeError) as retry_exc:
            print(
                "WARNING AJAP roles: no se pudo crear rol ni sin icono | "
                f"guild={guild.id} club={club} "
                f"error={type(retry_exc).__name__}: {retry_exc}"
            )
            return None
    except discord.Forbidden as exc:
        print(
            "WARNING AJAP roles: Discord rechazó creación por permisos | "
            f"guild={guild.id} club={club} error={exc}"
        )
        return None

    print(f"AJAP rol creado: guild={guild.id} club={club} role_id={role.id}")
    return role


async def _member_for(guild: discord.Guild, user_id: int):
    member = guild.get_member(int(user_id))
    if member is not None:
        return member
    try:
        return await guild.fetch_member(int(user_id))
    except (discord.NotFound, discord.Forbidden, discord.HTTPException):
        return None


def _club_for(guild: discord.Guild, user_id: int):
    token = guild_isolation._CURRENT_GUILD_ID.set(int(guild.id))
    try:
        return APP.club_de(int(user_id)) if APP is not None else teams.club_de(int(user_id))
    finally:
        guild_isolation._CURRENT_GUILD_ID.reset(token)


async def _sync_nickname(member: discord.Member, club: str | None):
    if club:
        try:
            nicknames._remember_original_nick(member, club)
            desired = nicknames._nickname_for(member, club)
            if member.nick != desired:
                await member.edit(nick=desired, reason=f"AJAP: club asignado - {club}")
            return True
        except (discord.Forbidden, discord.HTTPException) as exc:
            print(
                "WARNING AJAP roles: no se pudo sincronizar apodo | "
                f"guild={member.guild.id} user={member.id} club={club} error={exc}"
            )
            return False
        except Exception as exc:
            print(
                "WARNING AJAP roles: error inesperado sincronizando apodo | "
                f"guild={member.guild.id} user={member.id} club={club} "
                f"error={type(exc).__name__}: {exc}"
            )
            return False

    try:
        return await nicknames._restore_member_nickname(member.guild, member.id)
    except Exception as exc:
        print(
            "WARNING AJAP roles: no se pudo restaurar apodo | "
            f"guild={member.guild.id} user={member.id} error={type(exc).__name__}: {exc}"
        )
        return False


async def sync_member_identity(guild: discord.Guild, user_id: int):
    """Project the authoritative club assignment into Discord role + nickname."""
    if guild is None:
        return False
    member = await _member_for(guild, int(user_id))
    if member is None:
        return False

    club = _club_for(guild, int(user_id))
    desired_role = await _ensure_club_role(guild, club) if club else None
    managed_names = _managed_role_names()
    stale_roles = [
        role
        for role in member.roles
        if not role.managed
        and role.name.casefold() in managed_names
        and (desired_role is None or role.id != desired_role.id)
        and _bot_can_manage_role(guild, role)
    ]

    try:
        if stale_roles:
            await member.remove_roles(
                *stale_roles,
                reason="AJAP: limpieza automática de rol de club anterior",
            )
        if desired_role is not None and desired_role not in member.roles:
            if _bot_can_manage_role(guild, desired_role):
                await member.add_roles(
                    desired_role,
                    reason=f"AJAP: club asignado - {club}",
                )
            else:
                print(
                    "WARNING AJAP roles: el rol del club está por encima del bot | "
                    f"guild={guild.id} user={user_id} club={club}"
                )
    except (discord.Forbidden, discord.HTTPException) as exc:
        print(
            "WARNING AJAP roles: no se pudo actualizar rol del miembro | "
            f"guild={guild.id} user={user_id} club={club} error={exc}"
        )

    await _sync_nickname(member, club)
    return True


def _schedule_identity_sync(user_id: int):
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

    task = loop.create_task(sync_member_identity(guild, int(user_id)))
    _SYNC_TASKS.add(task)
    task.add_done_callback(_SYNC_TASKS.discard)


def _wrap_assignment_mutations():
    original_assign = teams.assign_team
    if not getattr(original_assign, "_ajap_team_role_identity", False):
        def assign_team(user_id, team_name):
            result = original_assign(user_id, team_name)
            try:
                ok = bool(result[0])
            except Exception:
                ok = False
            if ok:
                _schedule_identity_sync(int(user_id))
            return result

        assign_team._ajap_team_role_identity = True
        assign_team._ajap_team_role_identity_base = original_assign
        teams.assign_team = assign_team

    original_unlink = teams.unlink_team
    if not getattr(original_unlink, "_ajap_team_role_identity", False):
        def unlink_team(user_id, admin_id):
            removed = original_unlink(user_id, admin_id)
            if removed:
                _schedule_identity_sync(int(user_id))
            return removed

        unlink_team._ajap_team_role_identity = True
        unlink_team._ajap_team_role_identity_base = original_unlink
        teams.unlink_team = unlink_team

    # Voluntary resignation deletes the assignment directly instead of calling
    # teams.unlink_team(), so mirror that mutation too.
    try:
        import dt_resignation_patch as resignation

        original_resign = resignation._resign_assignment
        if not getattr(original_resign, "_ajap_team_role_identity", False):
            def resign_assignment(user_id: int, expected_club: str):
                removed = original_resign(user_id, expected_club)
                if removed:
                    _schedule_identity_sync(int(user_id))
                return removed

            resign_assignment._ajap_team_role_identity = True
            resign_assignment._ajap_team_role_identity_base = original_resign
            resignation._resign_assignment = resign_assignment
    except Exception as exc:
        print(f"WARNING AJAP roles: no se pudo envolver renuncia: {exc}")


async def _ensure_and_reconcile_guild(guild: discord.Guild):
    token = guild_isolation._CURRENT_GUILD_ID.set(int(guild.id))
    try:
        clubs = _club_names()
        created_or_found = 0
        for club in clubs:
            if await _ensure_club_role(guild, club) is not None:
                created_or_found += 1

        try:
            rows = list(teams.assignments())
        except Exception as exc:
            print(f"WARNING AJAP roles: no se pudieron leer asignaciones guild={guild.id}: {exc}")
            rows = []

        assigned_ids = {int(row["user_id"]) for row in rows}

        # Reconcile users that either have an assignment or currently carry any
        # club role. This also removes stale roles left by old test sessions.
        managed_names = _managed_role_names()
        candidate_ids = set(assigned_ids)
        for member in getattr(guild, "members", []):
            if any(role.name.casefold() in managed_names for role in member.roles):
                candidate_ids.add(int(member.id))

        for user_id in candidate_ids:
            await sync_member_identity(guild, user_id)

        print(
            "AJAP roles sincronizados: "
            f"guild={guild.id} roles={created_or_found}/{len(clubs)} "
            f"asignaciones={len(assigned_ids)} "
            f"role_icons={'si' if 'ROLE_ICONS' in set(getattr(guild, 'features', ())) else 'no'}"
        )
    finally:
        guild_isolation._CURRENT_GUILD_ID.reset(token)


async def _on_ready_team_roles():
    if BOT is None:
        return
    for guild in BOT.guilds:
        try:
            await _ensure_and_reconcile_guild(guild)
        except Exception as exc:
            print(
                "WARNING AJAP roles: reconciliación on_ready falló | "
                f"guild={guild.id} error={type(exc).__name__}: {exc}"
            )


def apply_team_role_identity_patch(runtime, bot):
    global APP, BOT
    APP = runtime
    BOT = bot
    if getattr(runtime, "_ajap_team_role_identity_patch", False):
        return

    _wrap_assignment_mutations()
    bot.add_listener(_on_ready_team_roles, "on_ready")
    runtime.sync_member_club_identity = sync_member_identity
    runtime._ajap_team_role_identity_patch = True
    print(
        "AJAP identidad de club activa: roles automáticos + rol al asignar + "
        "limpieza al renunciar + apodo Nombre | Club + icono de rol si Discord lo permite"
    )


_original_apply_guild_isolation_patch = guild_isolation.apply_guild_isolation_patch


def _apply_guild_isolation_then_team_roles(runtime, bot):
    _original_apply_guild_isolation_patch(runtime, bot)
    apply_team_role_identity_patch(runtime, bot)


if not getattr(
    guild_isolation.apply_guild_isolation_patch,
    "_ajap_team_role_identity_wrapped",
    False,
):
    _apply_guild_isolation_then_team_roles._ajap_team_role_identity_wrapped = True
    guild_isolation.apply_guild_isolation_patch = _apply_guild_isolation_then_team_roles
