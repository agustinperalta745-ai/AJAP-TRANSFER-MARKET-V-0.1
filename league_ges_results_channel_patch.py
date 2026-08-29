"""Publica resultados oficiales de Liga en un canal configurable para carga en GES.

Flujo:
- Staff configura el destino con /canal_resultados_cerrados.
- Cada resultado que queda oficialmente persistido en league_matches se publica allí.
- La tarjeta muestra ambos clubes, sus emojis/escudos del servidor y el marcador grande.
- Estado inicial: EN REVISIÓN.
- Staff pulsa CARGADO EN GES y la misma tarjeta queda marcada de forma persistente.

La publicación es idempotente por source_message_id: reprocesar una captura de prueba
actualiza/reutiliza la tarjeta en vez de duplicarla.
"""

from __future__ import annotations

import asyncio

import discord
from discord import app_commands

import guild_isolation_patch as guild_isolation
import league_automation_patch as league
import league_result_evidence_patch as evidence
import league_validation_admin_review_patch as strict
import market_usage_channel_patch as market_gate
import team_badge_selector_patch as badges


APP = None
BOT = None

STATUS_REVIEW = "EN_REVISION"
STATUS_LOADED = "CARGADO_GES"

# Liga/GES vive fuera del canal exclusivo de Mercado.
market_gate.EXEMPT_COMMANDS.add("canal_resultados_cerrados")


def _ensure_schema(runtime, guild_id: int):
    conn = league.db(runtime, int(guild_id))
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS league_ges_config (
                guild_id INTEGER PRIMARY KEY,
                channel_id INTEGER NOT NULL,
                configured_by INTEGER,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS league_ges_results (
                source_message_id INTEGER PRIMARY KEY,
                guild_id INTEGER NOT NULL,
                source_channel_id INTEGER NOT NULL,
                report_channel_id INTEGER,
                report_message_id INTEGER UNIQUE,
                home_team TEXT NOT NULL,
                away_team TEXT NOT NULL,
                home_goals INTEGER NOT NULL,
                away_goals INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'EN_REVISION',
                marked_by INTEGER,
                marked_at DATETIME,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        conn.commit()
    finally:
        conn.close()


def _configured_channel_id(runtime, guild_id: int):
    _ensure_schema(runtime, guild_id)
    conn = league.db(runtime, int(guild_id))
    try:
        row = conn.execute(
            "SELECT channel_id FROM league_ges_config WHERE guild_id=? LIMIT 1",
            (int(guild_id),),
        ).fetchone()
        return int(row["channel_id"]) if row and row["channel_id"] else None
    finally:
        conn.close()


def _result_row(runtime, guild_id: int, *, source_message_id=None, report_message_id=None):
    _ensure_schema(runtime, guild_id)
    conn = league.db(runtime, int(guild_id))
    try:
        if source_message_id is not None:
            return conn.execute(
                "SELECT * FROM league_ges_results WHERE source_message_id=? LIMIT 1",
                (int(source_message_id),),
            ).fetchone()
        if report_message_id is not None:
            return conn.execute(
                "SELECT * FROM league_ges_results WHERE report_message_id=? LIMIT 1",
                (int(report_message_id),),
            ).fetchone()
        return None
    finally:
        conn.close()


def _official_match(runtime, guild_id: int, source_message_id: int):
    conn = league.db(runtime, int(guild_id))
    try:
        return conn.execute(
            "SELECT * FROM league_matches WHERE source_message_id=? LIMIT 1",
            (int(source_message_id),),
        ).fetchone()
    finally:
        conn.close()


def _badge(guild: discord.Guild, club: str):
    try:
        emoji = badges._manual_badge_emoji(guild, club)
    except Exception:
        emoji = None
    return str(emoji) if emoji is not None else "⚽"


def _result_embed(guild: discord.Guild, row):
    loaded = str(row["status"] or "").upper() == STATUS_LOADED
    status_text = "✅ **CARGADO EN GES**" if loaded else "🟡 **EN REVISIÓN • PENDIENTE DE GES**"
    color = discord.Color.green() if loaded else discord.Color.gold()

    home_icon = _badge(guild, row["home_team"])
    away_icon = _badge(guild, row["away_team"])
    score = f"# {int(row['home_goals'])}  —  {int(row['away_goals'])}"

    embed = discord.Embed(
        title="🏁 RESULTADO CERRADO",
        description=(
            f"### {home_icon} {row['home_team']}\n"
            f"{score}\n"
            f"### {away_icon} {row['away_team']}\n\n"
            f"{status_text}"
        ),
        color=color,
    )
    embed.add_field(
        name="📸 Evidencia original",
        value=(
            f"[Abrir captura](https://discord.com/channels/{int(row['guild_id'])}/"
            f"{int(row['source_channel_id'])}/{int(row['source_message_id'])})"
        ),
        inline=False,
    )
    if loaded and row["marked_by"]:
        embed.add_field(name="Cargado por", value=f"<@{int(row['marked_by'])}>", inline=True)
    embed.set_footer(text="AJPA Liga • resultado confirmado por el bot")
    return embed


class GESResultView(discord.ui.View):
    def __init__(self, loaded: bool = False):
        super().__init__(timeout=None)
        if loaded:
            self.add_item(
                discord.ui.Button(
                    label="CARGADO EN GES",
                    emoji="✅",
                    style=discord.ButtonStyle.success,
                    disabled=True,
                    custom_id="ajap:league:ges:loaded-state",
                )
            )
        else:
            self.add_item(
                discord.ui.Button(
                    label="EN REVISIÓN",
                    emoji="🟡",
                    style=discord.ButtonStyle.secondary,
                    disabled=True,
                    custom_id="ajap:league:ges:review-state",
                )
            )
            button = discord.ui.Button(
                label="CARGADO EN GES",
                emoji="✅",
                style=discord.ButtonStyle.success,
                custom_id="ajap:league:ges:mark-loaded",
            )
            button.callback = self._mark_loaded
            self.add_item(button)

    async def _mark_loaded(self, interaction: discord.Interaction):
        runtime = APP
        if not runtime or not interaction.guild_id:
            await interaction.response.send_message("⚠️ El módulo de resultados no está listo.", ephemeral=True)
            return
        if not runtime.es_admin(interaction):
            await interaction.response.send_message("⛔ Solo Staff puede marcar un resultado como cargado en GES.", ephemeral=True)
            return

        row = _result_row(runtime, interaction.guild_id, report_message_id=interaction.message.id)
        if not row:
            await interaction.response.send_message("⚠️ No encontré este resultado en la base.", ephemeral=True)
            return
        if str(row["status"] or "").upper() == STATUS_LOADED:
            await interaction.response.edit_message(embed=_result_embed(interaction.guild, row), view=GESResultView(True))
            return

        conn = league.db(runtime, interaction.guild_id)
        try:
            conn.execute(
                """
                UPDATE league_ges_results
                SET status=?, marked_by=?, marked_at=CURRENT_TIMESTAMP, updated_at=CURRENT_TIMESTAMP
                WHERE report_message_id=?
                """,
                (STATUS_LOADED, int(interaction.user.id), int(interaction.message.id)),
            )
            conn.commit()
        finally:
            conn.close()

        current = _result_row(runtime, interaction.guild_id, report_message_id=interaction.message.id)
        await interaction.response.edit_message(
            embed=_result_embed(interaction.guild, current),
            view=GESResultView(True),
        )


async def _resolve_channel(guild: discord.Guild, channel_id: int):
    channel = guild.get_channel(int(channel_id))
    if channel is None and BOT is not None:
        try:
            channel = await BOT.fetch_channel(int(channel_id))
        except Exception:
            channel = None
    return channel if isinstance(channel, discord.TextChannel) else None


async def _publish_closed_result(runtime, guild_id: int, source_message_id: int):
    if BOT is None:
        return
    guild = BOT.get_guild(int(guild_id))
    if guild is None:
        return

    channel_id = _configured_channel_id(runtime, guild_id)
    if not channel_id:
        return
    channel = await _resolve_channel(guild, channel_id)
    if channel is None:
        print(f"WARNING AJAP GES: canal configurado no accesible guild={guild_id} channel={channel_id}")
        return

    match = _official_match(runtime, guild_id, source_message_id)
    if not match:
        return

    existing = _result_row(runtime, guild_id, source_message_id=source_message_id)
    conn = league.db(runtime, int(guild_id))
    try:
        conn.execute(
            """
            INSERT INTO league_ges_results
                (source_message_id, guild_id, source_channel_id, report_channel_id,
                 home_team, away_team, home_goals, away_goals, status, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(source_message_id) DO UPDATE SET
                source_channel_id=excluded.source_channel_id,
                report_channel_id=excluded.report_channel_id,
                home_team=excluded.home_team,
                away_team=excluded.away_team,
                home_goals=excluded.home_goals,
                away_goals=excluded.away_goals,
                status=CASE
                    WHEN league_ges_results.home_team != excluded.home_team
                      OR league_ges_results.away_team != excluded.away_team
                      OR league_ges_results.home_goals != excluded.home_goals
                      OR league_ges_results.away_goals != excluded.away_goals
                    THEN 'EN_REVISION'
                    ELSE league_ges_results.status
                END,
                marked_by=CASE
                    WHEN league_ges_results.home_team != excluded.home_team
                      OR league_ges_results.away_team != excluded.away_team
                      OR league_ges_results.home_goals != excluded.home_goals
                      OR league_ges_results.away_goals != excluded.away_goals
                    THEN NULL ELSE league_ges_results.marked_by END,
                marked_at=CASE
                    WHEN league_ges_results.home_team != excluded.home_team
                      OR league_ges_results.away_team != excluded.away_team
                      OR league_ges_results.home_goals != excluded.home_goals
                      OR league_ges_results.away_goals != excluded.away_goals
                    THEN NULL ELSE league_ges_results.marked_at END,
                updated_at=CURRENT_TIMESTAMP
            """,
            (
                int(match["source_message_id"]), int(guild_id), int(match["source_channel_id"]), int(channel.id),
                str(match["home_team"]), str(match["away_team"]), int(match["home_goals"]), int(match["away_goals"]),
                STATUS_REVIEW,
            ),
        )
        conn.commit()
    finally:
        conn.close()

    current = _result_row(runtime, guild_id, source_message_id=source_message_id)
    loaded = str(current["status"] or "").upper() == STATUS_LOADED

    report = None
    if existing and existing["report_message_id"]:
        old_channel_id = int(existing["report_channel_id"] or channel.id)
        old_channel = await _resolve_channel(guild, old_channel_id)
        if old_channel is not None:
            try:
                report = await old_channel.fetch_message(int(existing["report_message_id"]))
            except Exception:
                report = None

    if report is not None:
        try:
            await report.edit(embed=_result_embed(guild, current), view=GESResultView(loaded))
            return
        except Exception:
            report = None

    try:
        report = await channel.send(embed=_result_embed(guild, current), view=GESResultView(loaded))
    except Exception as exc:
        print(f"WARNING AJAP GES: no se pudo publicar resultado source={source_message_id}: {exc}")
        return

    conn = league.db(runtime, int(guild_id))
    try:
        conn.execute(
            """
            UPDATE league_ges_results
            SET report_channel_id=?, report_message_id=?, updated_at=CURRENT_TIMESTAMP
            WHERE source_message_id=?
            """,
            (int(channel.id), int(report.id), int(source_message_id)),
        )
        conn.commit()
    finally:
        conn.close()


def _schedule_publish(runtime, guild_id: int, source_message_id: int):
    try:
        asyncio.get_running_loop().create_task(
            _publish_closed_result(runtime, int(guild_id), int(source_message_id))
        )
    except RuntimeError:
        pass


def _wrap_evidence_persist():
    original = evidence._persist_official
    if getattr(original, "_ajap_ges_wrapped", False):
        return

    def wrapped(runtime, guild_id, row, *args, **kwargs):
        result = original(runtime, guild_id, row, *args, **kwargs)
        try:
            ok = bool(result[0])
        except Exception:
            ok = False
        if ok:
            _schedule_publish(runtime, int(guild_id), int(row["source_message_id"]))
        return result

    wrapped._ajap_ges_wrapped = True
    wrapped._ajap_ges_original = original
    evidence._persist_official = wrapped


def _wrap_legacy_store():
    original = getattr(league, "store", None)
    if not callable(original) or getattr(original, "_ajap_ges_wrapped", False):
        return

    def wrapped(runtime, message, *args, **kwargs):
        result = original(runtime, message, *args, **kwargs)
        try:
            score_ok = bool(result[0])
        except Exception:
            score_ok = False
        if score_ok and getattr(message, "guild", None):
            _schedule_publish(runtime, message.guild.id, message.id)
        return result

    wrapped._ajap_ges_wrapped = True
    wrapped._ajap_ges_original = original
    league.store = wrapped


def _wrap_manual_staff_modal():
    original = strict.LeagueManualScoreModal.on_submit
    if getattr(original, "_ajap_ges_wrapped", False):
        return

    async def wrapped(self, interaction: discord.Interaction):
        runtime = strict._runtime()
        review = None
        if runtime and interaction.guild_id:
            try:
                review = strict._review_for_staff_message(runtime, interaction.guild_id, self.staff_message_id)
            except Exception:
                review = None
        await original(self, interaction)
        if runtime and interaction.guild_id and review:
            match = _official_match(runtime, interaction.guild_id, int(review["source_message_id"]))
            if match:
                await _publish_closed_result(runtime, interaction.guild_id, int(review["source_message_id"]))

    wrapped._ajap_ges_wrapped = True
    wrapped._ajap_ges_original = original
    strict.LeagueManualScoreModal.on_submit = wrapped


def _install_command(runtime, bot):
    existing = bot.tree.get_command("canal_resultados_cerrados")
    if existing is not None:
        bot.tree.remove_command("canal_resultados_cerrados")

    @bot.tree.command(
        name="canal_resultados_cerrados",
        description="Elige dónde publicar resultados confirmados pendientes de cargar en GES",
    )
    @app_commands.describe(canal="Canal donde llegarán los resultados cerrados")
    async def canal_resultados_cerrados(
        interaction: discord.Interaction,
        canal: discord.TextChannel | None = None,
    ):
        if not interaction.guild_id or not runtime.es_admin(interaction):
            await interaction.response.send_message("⛔ Solo administradores.", ephemeral=True)
            return
        target = canal or interaction.channel
        if not isinstance(target, discord.TextChannel) or target.guild.id != interaction.guild_id:
            await interaction.response.send_message("⚠️ Elegí un canal de texto de este servidor.", ephemeral=True)
            return

        _ensure_schema(runtime, interaction.guild_id)
        conn = league.db(runtime, interaction.guild_id)
        try:
            conn.execute(
                """
                INSERT INTO league_ges_config (guild_id, channel_id, configured_by, updated_at)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(guild_id) DO UPDATE SET
                    channel_id=excluded.channel_id,
                    configured_by=excluded.configured_by,
                    updated_at=CURRENT_TIMESTAMP
                """,
                (int(interaction.guild_id), int(target.id), int(interaction.user.id)),
            )
            conn.commit()
        finally:
            conn.close()

        await interaction.response.send_message(
            f"✅ Canal de **resultados cerrados / GES** configurado en {target.mention}.\n"
            "Desde ahora, cada resultado confirmado por AJPA llegará ahí como **EN REVISIÓN** hasta que Staff pulse **CARGADO EN GES**.",
            ephemeral=True,
        )


def _install(runtime, bot):
    global APP, BOT
    APP, BOT = runtime, bot
    if getattr(runtime, "_ajap_league_ges_results_patch", False):
        return

    _ensure_schema(runtime, guild_isolation.LEGACY_GUILD_ID)
    _wrap_evidence_persist()
    _wrap_legacy_store()
    _wrap_manual_staff_modal()
    _install_command(runtime, bot)

    try:
        bot.add_view(GESResultView(False))
        bot.add_view(GESResultView(True))
    except Exception as exc:
        print(f"WARNING AJAP GES: no se pudo registrar vista persistente: {exc}")

    runtime._ajap_league_ges_results_patch = True
    print("AJAP Liga GES activo: canal configurable + resultados cerrados + estado cargado")


_original_apply_guild_isolation_patch = guild_isolation.apply_guild_isolation_patch


def _apply_guild_isolation_then_ges(runtime, bot):
    _original_apply_guild_isolation_patch(runtime, bot)
    _install(runtime, bot)


if not getattr(guild_isolation.apply_guild_isolation_patch, "_ajap_league_ges_wrapped", False):
    _apply_guild_isolation_then_ges._ajap_league_ges_wrapped = True
    guild_isolation.apply_guild_isolation_patch = _apply_guild_isolation_then_ges
