"""Publish the complete official AJPA standings in Radio Pasillo after every manual GES sync.

Staff's "GES actualizada" action remains the only trigger.  Each successful sync
stores a recoverable Radio Pasillo event, renders the complete table locally,
and posts a short piece of commentary based on what changed in the standings.
"""

from __future__ import annotations

import json
from typing import Any

import discord

import guild_isolation_patch as guild_isolation
import league_ges_manual_sync_patch as ges
import season_ges_authority_patch as seasonal
import league_top5_overtake_radio_patch as top5


_EVENT_TABLE = "radio_pasillo_ges_table_events"


def _table_exists(conn, table: str) -> bool:
    return bool(
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
            (str(table),),
        ).fetchone()
    )


def _ensure_schema(conn) -> None:
    ges._ensure_schema(conn)
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {_EVENT_TABLE} (
            sync_run_id INTEGER PRIMARY KEY,
            guild_id INTEGER NOT NULL,
            league_id TEXT NOT NULL,
            competition_label TEXT NOT NULL DEFAULT '',
            before_json TEXT NOT NULL,
            after_json TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            channel_id INTEGER,
            discord_message_id INTEGER,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            posted_at DATETIME
        )
        """
    )
    conn.commit()


def _row_dict(row: Any) -> dict[str, Any]:
    data = dict(row) if not isinstance(row, dict) else dict(row)
    gf = int(data.get("gf") or 0)
    gc = int(data.get("gc") or 0)
    dg = data.get("dg")
    if dg is None:
        dg = gf - gc
    return {
        "position": int(data.get("position") or 0),
        "team": str(data.get("team") or "").strip(),
        "pts": int(data.get("pts") or 0),
        "pj": int(data.get("pj") or 0),
        "pg": int(data.get("pg") or 0),
        "pe": int(data.get("pe") or 0),
        "pp": int(data.get("pp") or 0),
        "gf": gf,
        "gc": gc,
        "dg": int(dg or 0),
    }


def _standings(runtime, guild_id: int, league_id: str) -> list[dict[str, Any]]:
    league_id = str(league_id or "").strip()
    if not league_id:
        return []
    conn = ges.league.db(runtime, int(guild_id))
    try:
        _ensure_schema(conn)
        rows = conn.execute(
            """SELECT position,team,pts,pj,pg,pe,pp,gf,gc,dg
               FROM league_ges_standings
               WHERE guild_id=? AND league_id=?
               ORDER BY position ASC, team COLLATE NOCASE ASC""",
            (int(guild_id), league_id),
        ).fetchall()
        return [_row_dict(row) for row in rows]
    finally:
        conn.close()


def _latest_sync_run_id(runtime, guild_id: int, league_id: str) -> int | None:
    conn = ges.league.db(runtime, int(guild_id))
    try:
        _ensure_schema(conn)
        row = conn.execute(
            """SELECT id FROM league_ges_sync_runs
               WHERE guild_id=? AND league_id=?
               ORDER BY id DESC LIMIT 1""",
            (int(guild_id), str(league_id)),
        ).fetchone()
        return int(row["id"]) if row else None
    finally:
        conn.close()


def _store_event(
    runtime,
    guild_id: int,
    sync_run_id: int,
    league_id: str,
    competition_label: str,
    before: list[dict[str, Any]],
    after: list[dict[str, Any]],
) -> None:
    conn = ges.league.db(runtime, int(guild_id))
    try:
        _ensure_schema(conn)
        conn.execute(
            f"""INSERT OR IGNORE INTO {_EVENT_TABLE}
                   (sync_run_id,guild_id,league_id,competition_label,before_json,after_json,status)
               VALUES(?,?,?,?,?,?,'pending')""",
            (
                int(sync_run_id),
                int(guild_id),
                str(league_id),
                str(competition_label or ""),
                json.dumps(before, ensure_ascii=False, separators=(",", ":")),
                json.dumps(after, ensure_ascii=False, separators=(",", ":")),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def _event(runtime, guild_id: int, sync_run_id: int):
    conn = ges.league.db(runtime, int(guild_id))
    try:
        _ensure_schema(conn)
        return conn.execute(
            f"SELECT * FROM {_EVENT_TABLE} WHERE sync_run_id=? AND guild_id=? LIMIT 1",
            (int(sync_run_id), int(guild_id)),
        ).fetchone()
    finally:
        conn.close()


def _mark_posted(
    runtime,
    guild_id: int,
    sync_run_id: int,
    channel_id: int,
    message_id: int,
) -> None:
    conn = ges.league.db(runtime, int(guild_id))
    try:
        _ensure_schema(conn)
        conn.execute(
            f"""UPDATE {_EVENT_TABLE}
                SET status='posted', channel_id=?, discord_message_id=?,
                    posted_at=CURRENT_TIMESTAMP
                WHERE sync_run_id=? AND guild_id=?""",
            (int(channel_id), int(message_id), int(sync_run_id), int(guild_id)),
        )
        conn.commit()
    finally:
        conn.close()


def _position_map(rows: list[dict[str, Any]]) -> dict[str, int]:
    out: dict[str, int] = {}
    for index, row in enumerate(rows, start=1):
        key = top5._team_key(row.get("team"))
        if key:
            out[key] = int(row.get("position") or index)
    return out


def _safe_team(team: str) -> str:
    return discord.utils.escape_markdown(str(team or "").strip())


def _ordinal(value: int) -> str:
    return f"{int(value)}.º"


def _commentary(
    guild,
    before: list[dict[str, Any]],
    after: list[dict[str, Any]],
) -> str:
    lines = [
        "📻 **R A D I O - P A S I L L O**",
        "📊 **TABLA ACTUALIZADA**",
        "",
    ]
    if not after:
        lines.append("GES se sincronizó, pero no quedó una tabla disponible para mostrar.")
        return "\n".join(lines)

    leader = after[0]
    runner = after[1] if len(after) > 1 else None
    leader_name = _safe_team(leader["team"])
    leader_badge = top5._club_emoji(guild, leader["team"])

    old_positions = _position_map(before)
    new_positions = _position_map(after)
    old_leader_key = top5._team_key(before[0]["team"]) if before else ""
    new_leader_key = top5._team_key(leader["team"])

    if not before:
        lines.append(
            f"🆕 Primera foto oficial de esta tabla: {leader_badge} **{leader_name}** "
            f"arranca arriba con **{leader['pts']} pts**."
        )
    elif old_leader_key and old_leader_key != new_leader_key:
        old_leader = _safe_team(before[0]["team"])
        lines.append(
            f"🚨 **Hay nuevo puntero.** {leader_badge} **{leader_name}** tomó la cima "
            f"y dejó atrás a **{old_leader}**."
        )
    else:
        climbs = []
        drops = []
        for row in after:
            key = top5._team_key(row["team"])
            if key not in old_positions:
                continue
            new_pos = new_positions.get(key)
            old_pos = old_positions.get(key)
            if new_pos is None or old_pos is None:
                continue
            delta = int(old_pos) - int(new_pos)
            if delta > 0:
                climbs.append((delta, old_pos, new_pos, row))
            elif delta < 0:
                drops.append((-delta, old_pos, new_pos, row))

        climbs.sort(key=lambda item: (-item[0], item[2]))
        if climbs:
            delta, old_pos, new_pos, row = climbs[0]
            name = _safe_team(row["team"])
            emoji = top5._club_emoji(guild, row["team"])
            lines.append(
                f"📈 {emoji} **{name}** fue el que más trepó: pasó del "
                f"**{_ordinal(old_pos)}** al **{_ordinal(new_pos)}** "
                f"({delta} puesto{'s' if delta != 1 else ''})."
            )
        elif drops:
            delta, old_pos, new_pos, row = sorted(
                drops, key=lambda item: (-item[0], item[2])
            )[0]
            name = _safe_team(row["team"])
            emoji = top5._club_emoji(guild, row["team"])
            lines.append(
                f"📉 {emoji} **{name}** sufrió el movimiento más fuerte: cayó del "
                f"**{_ordinal(old_pos)}** al **{_ordinal(new_pos)}**."
            )
        else:
            lines.append(
                f"🔒 No hubo cambios de posiciones: {leader_badge} **{leader_name}** "
                "sigue mandando."
            )

    if runner is not None:
        runner_name = _safe_team(runner["team"])
        runner_badge = top5._club_emoji(guild, runner["team"])
        gap = int(leader["pts"]) - int(runner["pts"])
        if gap > 0:
            lines.append(
                f"👑 La punta: {leader_badge} **{leader_name}** tiene **{leader['pts']} pts**, "
                f"**{gap}** por encima de {runner_badge} **{runner_name}**."
            )
        else:
            lines.append(
                f"⚖️ Arriba están igualados en **{leader['pts']} pts**: "
                f"{leader_badge} **{leader_name}** aparece por delante de "
                f"{runner_badge} **{runner_name}** por los criterios de desempate."
            )

    lines.extend(["", "👇 **Así quedó la tabla completa después de actualizar GES.**"])
    return "\n".join(lines)


def _clean_manager_name(member, club: str) -> str:
    if member is None:
        return ""
    for raw in (
        getattr(member, "global_name", None),
        getattr(member, "name", None),
        getattr(member, "display_name", None),
    ):
        value = str(raw or "").strip()
        if not value:
            continue
        suffix = f" | {club}".casefold()
        if value.casefold().endswith(suffix):
            value = value[: -len(suffix)].strip()
        if value:
            return value
    return ""


def _manager_names(guild) -> dict[str, str]:
    """Resolve DT names from the same live assignment data used by AJPA Mobile."""
    result: dict[str, str] = {}
    cached: dict[str, tuple[int | None, str]] = {}
    try:
        import mobile_write_api

        with mobile_write_api.write_db() as conn:
            if _table_exists(conn, "mobile_manager_names"):
                rows = conn.execute(
                    "SELECT club,user_id,manager_name FROM mobile_manager_names"
                ).fetchall()
                for row in rows:
                    key = top5._team_key(str(row["club"] or ""))
                    if key:
                        cached[key] = (
                            int(row["user_id"]) if row["user_id"] is not None else None,
                            str(row["manager_name"] or "").strip(),
                        )

            if not _table_exists(conn, "clubs"):
                return {key: name for key, (_, name) in cached.items() if name}

            columns = {
                str(row["name"])
                for row in conn.execute("PRAGMA table_info(clubs)").fetchall()
            }
            if not {"name", "user_id"}.issubset(columns):
                return {key: name for key, (_, name) in cached.items() if name}

            rows = conn.execute(
                """SELECT name,user_id FROM clubs
                   WHERE TRIM(COALESCE(name,''))<>''
                   ORDER BY name COLLATE NOCASE"""
            ).fetchall()
            for row in rows:
                club = str(row["name"] or "").strip()
                key = top5._team_key(club)
                if not key:
                    continue
                user_id = int(row["user_id"]) if row["user_id"] is not None else None
                manager_name = ""
                if user_id is not None and guild is not None:
                    manager_name = _clean_manager_name(guild.get_member(user_id), club)
                old_user_id, old_name = cached.get(key, (None, ""))
                if not manager_name and user_id is not None and old_user_id == user_id:
                    manager_name = old_name
                if manager_name:
                    result[key] = manager_name
    except Exception as exc:
        print(f"AJPA GES Tabla Radio: no se pudieron leer DTs: {exc}")
        result = {key: name for key, (_, name) in cached.items() if name}
    return result


async def _publish_event(runtime, bot, guild, sync_run_id: int) -> bool:
    row = _event(runtime, int(guild.id), int(sync_run_id))
    if not row:
        return False
    if str(row["status"] or "").casefold() == "posted":
        return True

    channel = await top5._resolve_radio_channel(runtime, bot, guild)
    if channel is None:
        print(
            f"AJPA GES Tabla Radio pendiente sync={sync_run_id}: Radio Pasillo no encontrado"
        )
        return False

    try:
        before = json.loads(str(row["before_json"] or "[]"))
        after = json.loads(str(row["after_json"] or "[]"))
    except Exception as exc:
        print(f"AJPA GES Tabla Radio payload inválido sync={sync_run_id}: {exc}")
        return False

    if not after:
        return False

    managers = _manager_names(guild)

    # Discord vuelve ilegible una tabla de 24 equipos en una sola imagen.
    # La publicamos como 4 páginas de 6 equipos, cada una en su propio embed:
    # siguen siendo un único mensaje, pero las imágenes quedan apiladas y con
    # tamaño suficiente para leerse desde el celular.
    page_size = 6
    page_count = max(1, (len(after) + page_size - 1) // page_size)
    files = []
    embeds = []
    for page_index in range(page_count):
        start = page_index * page_size
        chunk = after[start : start + page_size]
        if not chunk:
            continue
        first_pos = int(chunk[0].get("position") or (start + 1))
        last_pos = int(chunk[-1].get("position") or (start + len(chunk)))
        page_label = (
            f"TABLA {page_index + 1}/{page_count} • "
            f"PUESTOS {first_pos}–{last_pos}"
        )
        image = top5._render_standings(
            chunk,
            full_table=True,
            managers=managers,
            page_label=page_label,
        )
        filename = (
            f"ajpa-tabla-{int(sync_run_id)}-"
            f"p{page_index + 1}.png"
        )
        files.append(discord.File(image, filename=filename))
        embed = discord.Embed(color=0x181D2A)
        embed.set_image(url=f"attachment://{filename}")
        embeds.append(embed)

    try:
        sent = await channel.send(
            content=_commentary(guild, before, after),
            files=files,
            embeds=embeds,
            allowed_mentions=discord.AllowedMentions.none(),
        )
    except (discord.Forbidden, discord.HTTPException) as exc:
        print(
            f"AJPA GES Tabla Radio envío falló sync={sync_run_id} "
            f"canal={getattr(channel, 'id', None)}: {type(exc).__name__}: {exc}"
        )
        return False

    _mark_posted(runtime, guild.id, int(sync_run_id), channel.id, sent.id)
    print(
        f"AJPA GES Tabla Radio publicado sync={sync_run_id} "
        f"guild={guild.id} channel={channel.id} equipos={len(after)}"
    )
    return True


async def _publish_pending(runtime, bot, guild) -> None:
    conn = ges.league.db(runtime, int(guild.id))
    try:
        _ensure_schema(conn)
        rows = conn.execute(
            f"""SELECT sync_run_id FROM {_EVENT_TABLE}
                WHERE guild_id=? AND status='pending'
                ORDER BY sync_run_id ASC LIMIT 25""",
            (int(guild.id),),
        ).fetchall()
        ids = [int(row["sync_run_id"]) for row in rows]
    finally:
        conn.close()

    for sync_run_id in ids:
        try:
            await _publish_event(runtime, bot, guild, sync_run_id)
        except Exception as exc:
            print(
                f"AJPA GES Tabla Radio retry falló guild={guild.id} "
                f"sync={sync_run_id}: {type(exc).__name__}: {exc}"
            )


def _install_sync_wrapper(runtime, bot) -> None:
    base_sync = ges.sync_from_ges
    if getattr(base_sync, "_ajpa_ges_table_radio", False):
        return

    async def sync_with_table_radio(
        runtime_arg,
        bot_arg,
        guild_id: int,
        staff_user_id: int | None = None,
    ) -> dict:
        before_league_id = str(getattr(ges, "GES_LEAGUE_ID", "") or "")
        try:
            before = _standings(runtime_arg, int(guild_id), before_league_id)
        except Exception as exc:
            print(
                f"AJPA GES Tabla Radio snapshot previo falló guild={guild_id}: "
                f"{type(exc).__name__}: {exc}"
            )
            before = []

        result = await base_sync(
            runtime_arg,
            bot_arg,
            int(guild_id),
            staff_user_id,
        )
        if not result or not result.get("ok"):
            return result

        league_id = str(result.get("league_id") or getattr(ges, "GES_LEAGUE_ID", "") or "")
        if before_league_id and league_id and before_league_id != league_id:
            before = []

        try:
            after = _standings(runtime_arg, int(guild_id), league_id)
            sync_run_id = _latest_sync_run_id(runtime_arg, int(guild_id), league_id)
            if after and sync_run_id is not None:
                _store_event(
                    runtime_arg,
                    int(guild_id),
                    int(sync_run_id),
                    league_id,
                    str(result.get("competition_label") or "Liga AJPA"),
                    before,
                    after,
                )
                guild = bot_arg.get_guild(int(guild_id))
                if guild is not None:
                    try:
                        await _publish_event(
                            runtime_arg,
                            bot_arg,
                            guild,
                            int(sync_run_id),
                        )
                    except Exception as exc:
                        print(
                            f"AJPA GES Tabla Radio post-sync falló guild={guild_id} "
                            f"sync={sync_run_id}: {type(exc).__name__}: {exc}"
                        )
        except Exception as exc:
            # A Radio Pasillo problem must never invalidate a successful official
            # GES synchronization. The competitive snapshot is already committed.
            print(
                f"AJPA GES Tabla Radio no pudo preparar publicación guild={guild_id}: "
                f"{type(exc).__name__}: {exc}"
            )
        return result

    sync_with_table_radio._ajpa_ges_table_radio = True
    sync_with_table_radio._ajpa_ges_table_radio_base = base_sync
    ges.sync_from_ges = sync_with_table_radio


def _patch_seasonal_reinstall() -> None:
    current = seasonal.apply_season_ges_authority
    if getattr(current, "_ajpa_ges_table_radio_reinstall", False):
        return

    def apply_season_with_table_radio(runtime, bot):
        current(runtime, bot)
        _install_sync_wrapper(runtime, bot)

    apply_season_with_table_radio._ajpa_ges_table_radio_reinstall = True
    seasonal.apply_season_ges_authority = apply_season_with_table_radio


def apply_ges_table_radio(runtime, bot) -> None:
    _install_sync_wrapper(runtime, bot)
    _patch_seasonal_reinstall()

    if getattr(runtime, "_ajpa_ges_table_radio_ready", False):
        return

    async def ready_listener():
        for guild in list(getattr(bot, "guilds", []) or []):
            try:
                await _publish_pending(runtime, bot, guild)
            except Exception as exc:
                print(
                    f"AJPA GES Tabla Radio recuperación guild={getattr(guild, 'id', None)}: "
                    f"{type(exc).__name__}: {exc}"
                )

    bot.add_listener(ready_listener, "on_ready")
    runtime._ajpa_ges_table_radio_ready = True
    print(
        "AJPA Radio Pasillo: tabla completa se publica después de cada 'GES actualizada'"
    )


_BASE_APPLY_GUILD = guild_isolation.apply_guild_isolation_patch


def _apply_guild_then_ges_table_radio(runtime, bot):
    _BASE_APPLY_GUILD(runtime, bot)
    apply_ges_table_radio(runtime, bot)


if not getattr(
    guild_isolation.apply_guild_isolation_patch,
    "_ajpa_ges_table_radio_wrapped",
    False,
):
    _apply_guild_then_ges_table_radio._ajpa_ges_table_radio_wrapped = True
    guild_isolation.apply_guild_isolation_patch = _apply_guild_then_ges_table_radio
