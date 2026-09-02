"""Bridge AJPA Mobile match searches into a configurable Discord channel.

Mobile remains the source of truth. This module polls the exact same
``mobile_match_searches`` table used by AJPA Mobile and mirrors active searches
as Discord cards. The public card never exposes PES room credentials.

A Discord manager can press ``IR A LA CANCHA`` to accept the SAME search using
``mobile_match_search_patch.join_search``. Therefore all mobile eligibility,
30-minute expiry, already-played checks and atomic race protection remain shared
between app and Discord. Once matched, only either participating DT can reveal
the lobby/room/password through an ephemeral Discord response.
"""

from __future__ import annotations

import asyncio
import sqlite3
from contextlib import closing

import discord
from discord.ext import tasks

import guild_isolation_patch
import mobile_match_result_timeout_patch as result_timeout
import mobile_match_search_patch as match_search
import mobile_write_api


APP = None
BOT = None
_LOCKS: dict[int, asyncio.Lock] = {}
_REGISTERED_VIEWS: set[tuple[int, int, int, str]] = set()


OPEN = match_search.OPEN
MATCHED = match_search.MATCHED
COMPLETED = match_search.COMPLETED
CANCELLED = match_search.CANCELLED
EXPIRED = match_search.EXPIRED


def _lock(guild_id: int) -> asyncio.Lock:
    return _LOCKS.setdefault(int(guild_id), asyncio.Lock())


def _conn_for_guild(guild_id: int):
    if APP is None:
        raise RuntimeError("AJPA runtime todavía no inicializado")
    if hasattr(APP, "db_for_guild"):
        return APP.db_for_guild(int(guild_id))
    if hasattr(APP, "guild_context"):
        with APP.guild_context(int(guild_id)):
            return APP.db()
    return APP.db()


def _ensure_schema(conn: sqlite3.Connection) -> None:
    match_search._ensure_schema(conn)
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS match_search_discord_channels (
            guild_id INTEGER PRIMARY KEY,
            channel_id INTEGER NOT NULL,
            configured_by INTEGER,
            configured_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS match_search_discord_messages (
            search_id INTEGER PRIMARY KEY,
            channel_id INTEGER NOT NULL,
            message_id INTEGER NOT NULL,
            last_status TEXT NOT NULL,
            updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """
    )
    conn.commit()


def _refresh_search_state(conn: sqlite3.Connection) -> None:
    _ensure_schema(conn)
    match_search._expire_stale_open(conn)
    # Same result-aware timeout used by the app for MATCHED cards.
    result_timeout._expire_stale_matched(conn)
    match_search._reconcile_completed(conn)
    conn.commit()


def _channel_id(conn: sqlite3.Connection, guild_id: int) -> int | None:
    _ensure_schema(conn)
    row = conn.execute(
        "SELECT channel_id FROM match_search_discord_channels WHERE guild_id=? LIMIT 1",
        (int(guild_id),),
    ).fetchone()
    return int(row["channel_id"]) if row and row["channel_id"] else None


def _set_channel(
    conn: sqlite3.Connection,
    guild_id: int,
    channel_id: int,
    configured_by: int,
) -> None:
    _ensure_schema(conn)
    conn.execute(
        """
        INSERT INTO match_search_discord_channels
            (guild_id, channel_id, configured_by, configured_at, updated_at)
        VALUES (?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        ON CONFLICT(guild_id) DO UPDATE SET
            channel_id=excluded.channel_id,
            configured_by=excluded.configured_by,
            updated_at=CURRENT_TIMESTAMP
        """,
        (int(guild_id), int(channel_id), int(configured_by)),
    )
    conn.commit()


def _is_admin(interaction: discord.Interaction) -> bool:
    try:
        if APP is not None and hasattr(APP, "es_admin"):
            return bool(APP.es_admin(interaction))
    except Exception:
        pass
    return bool(
        interaction.guild
        and isinstance(interaction.user, discord.Member)
        and interaction.user.guild_permissions.administrator
    )


def _escape(value) -> str:
    return discord.utils.escape_markdown(str(value or ""))


def _expiry_unix(conn: sqlite3.Connection, search_id: int) -> int | None:
    row = conn.execute(
        """
        SELECT CAST(strftime('%s', datetime(created_at, '+' || ? || ' minutes')) AS INTEGER) AS ts
        FROM mobile_match_searches
        WHERE id=?
        LIMIT 1
        """,
        (int(match_search.SEARCH_TTL_MINUTES), int(search_id)),
    ).fetchone()
    return int(row["ts"]) if row and row["ts"] is not None else None


def _search_row(conn: sqlite3.Connection, search_id: int):
    _refresh_search_state(conn)
    return conn.execute(
        "SELECT * FROM mobile_match_searches WHERE id=? LIMIT 1",
        (int(search_id),),
    ).fetchone()


def _public_embed(conn: sqlite3.Connection, row) -> discord.Embed:
    search_id = int(row["id"])
    status = str(row["status"] or "").upper()
    creator = _escape(row["creator_club"])
    opponent = _escape(row["opponent_club"]) if row["opponent_club"] else None

    if status == OPEN:
        expires = _expiry_unix(conn, search_id)
        expiry_text = f"<t:{expires}:R>" if expires else "en 30 minutos"
        embed = discord.Embed(
            title="⚽ BUSCA RIVAL",
            description=(
                f"🟢 **{creator} está disponible para jugar ahora.**\n\n"
                "Esta búsqueda fue publicada desde **AJPA Mobile** y también puede "
                "aceptarse desde Discord.\n\n"
                f"⏱️ **Vence {expiry_text}.**\n"
                "Tocá **⚽ IR A LA CANCHA** para tomar el partido."
            ),
            color=discord.Color.green(),
        )
        embed.add_field(name="🏟️ Club", value=creator, inline=True)
        embed.add_field(name="📡 Estado", value="Disponible ahora", inline=True)
        embed.add_field(
            name="🔐 Datos de sala",
            value="Se muestran en privado únicamente cuando el partido queda aceptado.",
            inline=False,
        )
        embed.set_footer(text="AJPA • Buscar Partido • App + Discord sincronizados")
        return embed

    if status == MATCHED:
        embed = discord.Embed(
            title="✅ RIVAL ENCONTRADO",
            description=(
                f"⚔️ **{creator} vs {opponent or 'Rival'}**\n\n"
                "El partido ya fue tomado. Los dos DT pueden usar "
                "**🏟️ IR A LA CANCHA** para ver vestíbulo, sala y contraseña de forma privada."
            ),
            color=discord.Color.blue(),
        )
        embed.set_footer(text="AJPA • Partido confirmado • Esperando resultado")
        return embed

    if status == COMPLETED:
        home = _escape(row["result_home_team"])
        away = _escape(row["result_away_team"])
        if row["result_home_goals"] is not None and row["result_away_goals"] is not None:
            score = (
                f"🏁 **{home} {int(row['result_home_goals'])}–"
                f"{int(row['result_away_goals'])} {away}**"
            )
        else:
            score = "🏁 **Resultado oficial cargado.**"
        embed = discord.Embed(
            title="🏁 PARTIDO FINALIZADO",
            description=f"⚔️ **{creator} vs {opponent or 'Rival'}**\n\n{score}",
            color=discord.Color.gold(),
        )
        embed.set_footer(text="AJPA • Resultado detectado por Liga")
        return embed

    if status == CANCELLED:
        embed = discord.Embed(
            title="🚫 BÚSQUEDA CANCELADA",
            description=f"**{creator}** cerró esta búsqueda de partido.",
            color=discord.Color.dark_grey(),
        )
        embed.set_footer(text="AJPA • Buscar Partido")
        return embed

    embed = discord.Embed(
        title="⌛ BÚSQUEDA VENCIDA",
        description=(
            f"La búsqueda de **{creator}** terminó sin rival disponible.\n"
            "La tarjeta ya no puede aceptarse."
        ),
        color=discord.Color.dark_grey(),
    )
    embed.set_footer(text="AJPA • Buscar Partido • 30 minutos")
    return embed


def _public_text(conn: sqlite3.Connection, row) -> str:
    status = str(row["status"] or "").upper()
    creator = _escape(row["creator_club"])
    opponent = _escape(row["opponent_club"]) if row["opponent_club"] else None
    if status == OPEN:
        expires = _expiry_unix(conn, int(row["id"]))
        expiry = f"<t:{expires}:R>" if expires else "en 30 minutos"
        return (
            "⚽ **BUSCA RIVAL**\n"
            f"🟢 **{creator} está disponible para jugar ahora.**\n"
            f"⏱️ Vence {expiry}.\n"
            "Usá **⚽ IR A LA CANCHA** para aceptar. Los datos de sala son privados."
        )
    if status == MATCHED:
        return (
            "✅ **RIVAL ENCONTRADO**\n"
            f"⚔️ **{creator} vs {opponent or 'Rival'}**\n"
            "Los dos DT pueden usar **🏟️ IR A LA CANCHA** para ver la sala en privado."
        )
    if status == COMPLETED:
        return f"🏁 **PARTIDO FINALIZADO**\n⚔️ **{creator} vs {opponent or 'Rival'}**"
    if status == CANCELLED:
        return f"🚫 **BÚSQUEDA CANCELADA**\n**{creator}** cerró la búsqueda."
    return f"⌛ **BÚSQUEDA VENCIDA**\nLa búsqueda de **{creator}** ya no puede aceptarse."


def _room_embed(row) -> discord.Embed:
    room = match_search._room_access(row)
    creator = _escape(row["creator_club"])
    opponent = _escape(row["opponent_club"])
    password = str(room.get("password") or "Sin contraseña")
    embed = discord.Embed(
        title="🏟️ DATOS PARA ENTRAR A LA CANCHA",
        description=f"⚔️ **{creator} vs {opponent}**",
        color=discord.Color.green(),
    )
    embed.add_field(name="🌐 Vestíbulo PES", value=f"`{room['pes_lobby']}`", inline=False)
    embed.add_field(name="🚪 Sala", value=f"`{room['room_name']}`", inline=False)
    embed.add_field(name="🔑 Contraseña", value=f"`{password}`", inline=False)
    embed.set_footer(text="Solo los dos DT del partido pueden ver estos datos")
    return embed


def _viewer_club(conn: sqlite3.Connection, user_id: int) -> str | None:
    try:
        club = mobile_write_api.mobile_auth.resolve_club_readonly(conn, int(user_id))
        return str(club) if club else None
    except Exception:
        return None


def _is_participant(row, club: str | None) -> bool:
    if not club:
        return False
    viewer = match_search._norm_team(club)
    creator = match_search._norm_team(row["creator_club"])
    opponent = match_search._norm_team(row["opponent_club"])
    return viewer in {creator, opponent}


async def _safe_followup(interaction: discord.Interaction, *, content=None, embed=None):
    try:
        await interaction.followup.send(content=content, embed=embed, ephemeral=True)
    except (discord.NotFound, discord.Forbidden, discord.HTTPException):
        pass


async def _join_from_discord(interaction: discord.Interaction, search_id: int) -> None:
    if not interaction.guild_id or interaction.guild is None:
        await interaction.response.send_message("⚠️ Usá este botón dentro del servidor.", ephemeral=True)
        return

    await interaction.response.defer(ephemeral=True, thinking=True)
    result = None
    try:
        with closing(_conn_for_guild(interaction.guild_id)) as conn:
            _ensure_schema(conn)
            try:
                result = match_search.join_search(
                    conn,
                    {"user_id": int(interaction.user.id), "is_staff": False},
                    int(search_id),
                )
                conn.commit()
            except Exception:
                if conn.in_transaction:
                    conn.rollback()
                raise
    except mobile_write_api.ApiFailure as exc:
        await _safe_followup(interaction, content=f"⚠️ {exc.message}")
        try:
            await sync_guild(interaction.guild)
        except Exception:
            pass
        return
    except Exception as exc:
        print(
            f"AJPA Discord match join error guild={interaction.guild_id} "
            f"search={search_id}: {type(exc).__name__}: {exc}"
        )
        await _safe_followup(
            interaction,
            content="❌ No pude aceptar el partido. La búsqueda no fue modificada.",
        )
        return

    try:
        await sync_guild(interaction.guild)
    except Exception as exc:
        print(f"AJPA Discord match card sync after join #{search_id}: {exc}")

    if result and result.get("room_access"):
        # Read the committed row so the response and public card use the same state.
        with closing(_conn_for_guild(interaction.guild_id)) as conn:
            row = _search_row(conn, int(search_id))
        if row:
            await _safe_followup(interaction, embed=_room_embed(row))
            return

    await _safe_followup(
        interaction,
        content="✅ Rival encontrado. El partido quedó sincronizado con AJPA Mobile.",
    )


async def _show_room_from_discord(
    interaction: discord.Interaction, search_id: int
) -> None:
    if not interaction.guild_id:
        await interaction.response.send_message("⚠️ Usá este botón dentro del servidor.", ephemeral=True)
        return
    await interaction.response.defer(ephemeral=True, thinking=True)
    try:
        with closing(_conn_for_guild(interaction.guild_id)) as conn:
            row = _search_row(conn, int(search_id))
            if not row:
                await _safe_followup(interaction, content="⚠️ Este partido ya no existe.")
                return
            status = str(row["status"] or "").upper()
            if status != MATCHED:
                await _safe_followup(
                    interaction,
                    content="ℹ️ Este partido ya no está esperando jugarse.",
                )
                return
            club = _viewer_club(conn, int(interaction.user.id))
            if not _is_participant(row, club):
                await _safe_followup(
                    interaction,
                    content="🔒 Solo los dos DT de este partido pueden ver los datos de la sala.",
                )
                return
            embed = _room_embed(row)
        await _safe_followup(interaction, embed=embed)
    except Exception as exc:
        print(
            f"AJPA Discord match room error guild={interaction.guild_id} "
            f"search={search_id}: {type(exc).__name__}: {exc}"
        )
        await _safe_followup(interaction, content="❌ No pude abrir los datos de la cancha.")


class MatchSearchDiscordView(discord.ui.View):
    def __init__(self, guild_id: int, search_id: int, status: str):
        super().__init__(timeout=None)
        self.guild_id = int(guild_id)
        self.search_id = int(search_id)
        status = str(status or "").upper()

        if status == OPEN:
            button = discord.ui.Button(
                label="IR A LA CANCHA",
                emoji="⚽",
                style=discord.ButtonStyle.success,
                custom_id=f"ajpa:match:join:{self.guild_id}:{self.search_id}",
            )

            async def join_callback(interaction: discord.Interaction):
                if interaction.guild_id != self.guild_id:
                    await interaction.response.send_message("⚠️ Partido de otro servidor.", ephemeral=True)
                    return
                await _join_from_discord(interaction, self.search_id)

            button.callback = join_callback
            self.add_item(button)

        elif status == MATCHED:
            button = discord.ui.Button(
                label="IR A LA CANCHA",
                emoji="🏟️",
                style=discord.ButtonStyle.success,
                custom_id=f"ajpa:match:room:{self.guild_id}:{self.search_id}",
            )

            async def room_callback(interaction: discord.Interaction):
                if interaction.guild_id != self.guild_id:
                    await interaction.response.send_message("⚠️ Partido de otro servidor.", ephemeral=True)
                    return
                await _show_room_from_discord(interaction, self.search_id)

            button.callback = room_callback
            self.add_item(button)


def _view_for(guild_id: int, row):
    status = str(row["status"] or "").upper()
    if status in {OPEN, MATCHED}:
        return MatchSearchDiscordView(guild_id, int(row["id"]), status)
    return None


async def _resolve_channel(guild: discord.Guild, channel_id: int):
    channel = guild.get_channel(int(channel_id))
    if channel is None:
        try:
            channel = await BOT.fetch_channel(int(channel_id))
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            return None
    return channel if hasattr(channel, "send") else None


def _register_view(guild_id: int, row, message_id: int) -> None:
    status = str(row["status"] or "").upper()
    if status not in {OPEN, MATCHED}:
        return
    key = (int(guild_id), int(row["id"]), int(message_id), status)
    if key in _REGISTERED_VIEWS:
        return
    view = MatchSearchDiscordView(guild_id, int(row["id"]), status)
    BOT.add_view(view, message_id=int(message_id))
    _REGISTERED_VIEWS.add(key)


async def _send_card(channel, guild_id: int, conn: sqlite3.Connection, row):
    view = _view_for(guild_id, row)
    try:
        return await channel.send(
            embed=_public_embed(conn, row),
            view=view,
            allowed_mentions=discord.AllowedMentions.none(),
        )
    except discord.Forbidden:
        return None
    except discord.HTTPException as embed_exc:
        print(
            f"AJPA match card embed failed search={row['id']} channel={channel.id}: "
            f"{embed_exc}; trying text"
        )
        try:
            return await channel.send(
                content=_public_text(conn, row),
                view=view,
                allowed_mentions=discord.AllowedMentions.none(),
            )
        except (discord.Forbidden, discord.HTTPException):
            return None


async def _edit_card(message, guild_id: int, conn: sqlite3.Connection, row) -> bool:
    view = _view_for(guild_id, row)
    try:
        await message.edit(
            content=None,
            embed=_public_embed(conn, row),
            view=view,
            allowed_mentions=discord.AllowedMentions.none(),
        )
        return True
    except discord.NotFound:
        return False
    except discord.Forbidden:
        return False
    except discord.HTTPException:
        try:
            await message.edit(
                content=_public_text(conn, row),
                embed=None,
                view=view,
                allowed_mentions=discord.AllowedMentions.none(),
            )
            return True
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            return False


async def sync_guild(guild: discord.Guild) -> None:
    if APP is None or BOT is None or guild is None:
        return

    async with _lock(guild.id):
        with closing(_conn_for_guild(guild.id)) as conn:
            _refresh_search_state(conn)
            configured_id = _channel_id(conn, guild.id)
            if not configured_id:
                return

            rows = conn.execute(
                """
                SELECT s.*,
                       m.channel_id AS discord_channel_id,
                       m.message_id AS discord_message_id,
                       m.last_status AS discord_last_status
                FROM mobile_match_searches s
                LEFT JOIN match_search_discord_messages m ON m.search_id=s.id
                WHERE s.status IN ('OPEN','MATCHED') OR m.search_id IS NOT NULL
                ORDER BY s.id DESC
                LIMIT 250
                """
            ).fetchall()

            # Copy row values now; no DB object is kept across network awaits.
            snapshots = [dict(row) for row in rows]

        configured_channel = await _resolve_channel(guild, configured_id)
        if configured_channel is None:
            return

        for snapshot in reversed(snapshots):
            search_id = int(snapshot["id"])
            status = str(snapshot["status"] or "").upper()
            mapped_message_id = snapshot.get("discord_message_id")
            mapped_channel_id = snapshot.get("discord_channel_id")
            last_status = str(snapshot.get("discord_last_status") or "")

            # Re-read this search before each edit/send so an app mutation that
            # happened during the Discord network calls cannot revive stale state.
            with closing(_conn_for_guild(guild.id)) as conn:
                row = _search_row(conn, search_id)
                if not row:
                    continue
                status = str(row["status"] or "").upper()

                if not mapped_message_id:
                    # Never backfill old history when a channel is first configured.
                    # Active OPEN/MATCHED cards are the only ones that matter now.
                    if status not in {OPEN, MATCHED}:
                        continue
                    sent = await _send_card(configured_channel, guild.id, conn, row)
                    if sent is None:
                        continue
                    conn.execute(
                        """
                        INSERT OR REPLACE INTO match_search_discord_messages
                            (search_id, channel_id, message_id, last_status, updated_at)
                        VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                        """,
                        (search_id, int(sent.channel.id), int(sent.id), status),
                    )
                    conn.commit()
                    _register_view(guild.id, row, sent.id)
                    continue

                if status == last_status:
                    _register_view(guild.id, row, int(mapped_message_id))
                    continue

                target_channel = await _resolve_channel(
                    guild, int(mapped_channel_id or configured_id)
                )
                message = None
                if target_channel is not None:
                    try:
                        message = await target_channel.fetch_message(int(mapped_message_id))
                    except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                        message = None

                edited = False
                if message is not None:
                    edited = await _edit_card(message, guild.id, conn, row)

                if not edited and status in {OPEN, MATCHED}:
                    sent = await _send_card(configured_channel, guild.id, conn, row)
                    if sent is not None:
                        mapped_channel_id = int(sent.channel.id)
                        mapped_message_id = int(sent.id)
                        edited = True

                if edited:
                    conn.execute(
                        """
                        INSERT OR REPLACE INTO match_search_discord_messages
                            (search_id, channel_id, message_id, last_status, updated_at)
                        VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
                        """,
                        (
                            search_id,
                            int(mapped_channel_id or configured_id),
                            int(mapped_message_id),
                            status,
                        ),
                    )
                    conn.commit()
                    _register_view(guild.id, row, int(mapped_message_id))


async def _restore_views_for_guild(guild: discord.Guild) -> None:
    with closing(_conn_for_guild(guild.id)) as conn:
        _refresh_search_state(conn)
        rows = conn.execute(
            """
            SELECT s.*, m.message_id AS discord_message_id
            FROM mobile_match_searches s
            JOIN match_search_discord_messages m ON m.search_id=s.id
            WHERE s.status IN ('OPEN','MATCHED')
            """
        ).fetchall()
        snapshots = [(dict(row), int(row["discord_message_id"])) for row in rows]
    for snapshot, message_id in snapshots:
        _register_view(guild.id, snapshot, message_id)


def _install_channel_command(bot) -> None:
    if bot.tree.get_command("canal_partidos") is not None:
        return

    @bot.tree.command(
        name="canal_partidos",
        description="Elige el canal donde se publican las búsquedas de partido de AJPA Mobile",
    )
    async def canal_partidos(
        interaction: discord.Interaction,
        canal: discord.TextChannel,
    ):
        if not interaction.guild_id or interaction.guild is None:
            await interaction.response.send_message("⚠️ Usalo dentro del servidor.", ephemeral=True)
            return
        if not _is_admin(interaction):
            await interaction.response.send_message("⛔ Solo administradores.", ephemeral=True)
            return

        me = interaction.guild.me
        if me is not None:
            perms = canal.permissions_for(me)
            if not perms.view_channel or not perms.send_messages:
                await interaction.response.send_message(
                    "⚠️ Necesito permiso para ver y enviar mensajes en ese canal.",
                    ephemeral=True,
                )
                return

        with closing(_conn_for_guild(interaction.guild_id)) as conn:
            _set_channel(conn, interaction.guild_id, canal.id, interaction.user.id)

        await interaction.response.send_message(
            f"✅ Las búsquedas de partido de **AJPA Mobile** se publicarán en {canal.mention}.\n"
            "Los DT también podrán aceptarlas desde ahí con **⚽ IR A LA CANCHA**.",
            ephemeral=True,
        )
        try:
            await sync_guild(interaction.guild)
        except Exception as exc:
            print(f"AJPA match channel initial sync error: {exc}")


def apply_match_search_discord_bridge(runtime, bot) -> None:
    global APP, BOT
    APP, BOT = runtime, bot
    if getattr(runtime, "_ajpa_match_search_discord_bridge", False):
        return

    _install_channel_command(bot)

    @tasks.loop(seconds=3)
    async def worker():
        for guild in list(getattr(bot, "guilds", [])):
            try:
                await sync_guild(guild)
            except Exception as exc:
                print(
                    f"AJPA Discord match sync error guild={guild.id}: "
                    f"{type(exc).__name__}: {exc}"
                )

    async def on_ready():
        for guild in list(getattr(bot, "guilds", [])):
            try:
                await _restore_views_for_guild(guild)
                await sync_guild(guild)
            except Exception as exc:
                print(f"AJPA Discord match ready error guild={guild.id}: {exc}")
        if not worker.is_running():
            worker.start()

    bot.add_listener(on_ready, "on_ready")
    runtime._ajpa_match_search_discord_bridge = True
    runtime._ajpa_match_search_discord_worker = worker
    print("AJPA Buscar Partido: bridge App ↔ Discord + IR A LA CANCHA activo")


_original_apply_guild_isolation_patch = guild_isolation_patch.apply_guild_isolation_patch


def _apply_guild_isolation_then_match_bridge(runtime, bot):
    _original_apply_guild_isolation_patch(runtime, bot)
    apply_match_search_discord_bridge(runtime, bot)


if not getattr(
    guild_isolation_patch.apply_guild_isolation_patch,
    "_ajpa_match_search_discord_bridge_wrapped",
    False,
):
    _apply_guild_isolation_then_match_bridge._ajpa_match_search_discord_bridge_wrapped = True
    guild_isolation_patch.apply_guild_isolation_patch = _apply_guild_isolation_then_match_bridge
