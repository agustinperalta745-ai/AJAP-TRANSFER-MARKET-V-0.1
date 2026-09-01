"""Carga/corrección manual de goleadores para partidos de Liga ya persistidos.

Soluciona dos casos:
- Resultado cargado manualmente por Staff: la tarjeta resuelta conserva un botón
  para cargar/corregir los goleadores del mismo partido.
- Partido ya cargado anteriormente: `/cargar_goleadores_manual mensaje:<link>`
  abre el mismo formulario usando el enlace del mensaje original de Resultados.

La operación reemplaza solamente los goleadores asociados a ese partido; nunca
modifica el marcador ni la tabla de posiciones. Se exige que la suma de los
goleadores coincida con el marcador oficial de cada equipo.
"""

from __future__ import annotations

import re

import discord
from discord import app_commands

import guild_isolation_patch as guild_isolation
import league_automation_patch as league
import league_validation_admin_review_patch as strict


APP = None
BOT = None

_MESSAGE_LINK_RE = re.compile(
    r"https?://(?:(?:canary|ptb)\.)?discord(?:app)?\.com/channels/(\d+)/(\d+)/(\d+)(?:/)?(?:\?.*)?$",
    re.IGNORECASE,
)
_COUNT_RE = re.compile(r"^(.*?)(?:\s*(?:\||=|x|×)\s*(\d+))?$", re.IGNORECASE)


def _runtime():
    return APP or strict._runtime()


def _parse_message_link(value: str):
    match = _MESSAGE_LINK_RE.match(str(value or "").strip())
    if not match:
        return None
    return tuple(int(part) for part in match.groups())


def _match_for_source(runtime, guild_id: int, source_message_id: int):
    conn = league.db(runtime, int(guild_id))
    try:
        return conn.execute(
            "SELECT * FROM league_matches WHERE source_message_id=? LIMIT 1",
            (int(source_message_id),),
        ).fetchone()
    finally:
        conn.close()


def _source_from_staff_message(runtime, guild_id: int, staff_message_id: int):
    strict._ensure_schema(runtime, int(guild_id))
    conn = league.db(runtime, int(guild_id))
    try:
        row = conn.execute(
            """
            SELECT source_message_id
            FROM league_manual_reviews
            WHERE staff_message_id=? AND status='RESUELTO'
            LIMIT 1
            """,
            (int(staff_message_id),),
        ).fetchone()
        return int(row["source_message_id"]) if row else None
    finally:
        conn.close()


def _existing_scorers(runtime, guild_id: int, source_message_id: int):
    conn = league.db(runtime, int(guild_id))
    try:
        return conn.execute(
            """
            SELECT player, team, goals
            FROM league_goal_events
            WHERE source_message_id=?
            ORDER BY team COLLATE NOCASE, player COLLATE NOCASE
            """,
            (int(source_message_id),),
        ).fetchall()
    finally:
        conn.close()


def _team_roster(runtime, guild_id: int, team: str):
    rows = []
    for row in league.roster(runtime, int(guild_id)):
        if league.canonical_team(row["club"]) == team:
            rows.append(row["name"])
    return rows


def _resolve_player(runtime, guild_id: int, raw: str, team: str):
    raw = str(raw or "").strip()
    if not raw:
        return None

    roster = _team_roster(runtime, guild_id, team)
    if not roster:
        return raw[:100]

    player, detected_team = league.canonical_player(runtime, int(guild_id), raw, team)
    if not player or detected_team != team:
        return None

    keyed = {league.norm(name): name for name in roster}
    return keyed.get(league.norm(player))


def _format_existing(rows, team: str):
    lines = []
    for row in rows:
        if league.canonical_team(row["team"]) != team:
            continue
        goals = max(1, int(row["goals"] or 1))
        suffix = f" x{goals}" if goals != 1 else ""
        lines.append(f"{row['player']}{suffix}")
    return "\n".join(lines)


def _parse_scorers(runtime, guild_id: int, text: str, team: str):
    parsed = []
    for raw_line in str(text or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue

        match = _COUNT_RE.match(line)
        if not match:
            raise ValueError(f"No pude leer: `{line}`.")

        raw_player = str(match.group(1) or "").strip()
        if not raw_player:
            raise ValueError(f"Falta el nombre del jugador en: `{line}`.")

        try:
            goals = int(match.group(2) or 1)
        except ValueError as exc:
            raise ValueError(f"Cantidad inválida en: `{line}`.") from exc
        if goals < 1 or goals > 20:
            raise ValueError(f"Cantidad de goles fuera de rango en: `{line}`.")

        player = _resolve_player(runtime, guild_id, raw_player, team)
        if not player:
            raise ValueError(
                f"`{raw_player}` no pertenece a **{team}** o no coincide con un jugador de su plantilla."
            )
        parsed.append((player, team, goals))

    grouped = {}
    for player, club, goals in parsed:
        key = (league.norm(player), club)
        if key not in grouped:
            grouped[key] = [player, club, 0]
        grouped[key][2] += goals
    return [tuple(value) for value in grouped.values()]


class ManualScorersModal(discord.ui.Modal):
    def __init__(self, source_message_id: int, match, existing_rows):
        super().__init__(title="Cargar / corregir goleadores", timeout=300)
        self.source_message_id = int(source_message_id)
        self.home_team = str(match["home_team"])
        self.away_team = str(match["away_team"])
        self.home_goals = int(match["home_goals"])
        self.away_goals = int(match["away_goals"])

        home_default = _format_existing(existing_rows, self.home_team)
        away_default = _format_existing(existing_rows, self.away_team)

        self.home_input = discord.ui.TextInput(
            label=f"{self.home_team[:35]} — {self.home_goals} gol(es)",
            placeholder="Uno por línea: Jugador  |  Jugador x2",
            style=discord.TextStyle.paragraph,
            required=self.home_goals > 0,
            default=home_default or None,
            max_length=1800,
        )
        self.away_input = discord.ui.TextInput(
            label=f"{self.away_team[:35]} — {self.away_goals} gol(es)",
            placeholder="Uno por línea: Jugador  |  Jugador x2",
            style=discord.TextStyle.paragraph,
            required=self.away_goals > 0,
            default=away_default or None,
            max_length=1800,
        )
        self.add_item(self.home_input)
        self.add_item(self.away_input)

    async def on_submit(self, interaction: discord.Interaction):
        runtime = _runtime()
        if not interaction.guild_id or not runtime or not runtime.es_admin(interaction):
            await interaction.response.send_message("⛔ Solo administradores.", ephemeral=True)
            return

        current = _match_for_source(runtime, interaction.guild_id, self.source_message_id)
        if not current:
            await interaction.response.send_message(
                "⚠️ Ese partido ya no está cargado en la Liga.", ephemeral=True
            )
            return

        try:
            home_rows = _parse_scorers(
                runtime, interaction.guild_id, self.home_input.value, self.home_team
            )
            away_rows = _parse_scorers(
                runtime, interaction.guild_id, self.away_input.value, self.away_team
            )
        except ValueError as exc:
            await interaction.response.send_message(f"⚠️ {exc}", ephemeral=True)
            return

        home_total = sum(row[2] for row in home_rows)
        away_total = sum(row[2] for row in away_rows)
        if home_total != self.home_goals or away_total != self.away_goals:
            await interaction.response.send_message(
                "⚠️ La suma de goleadores tiene que coincidir con el resultado oficial.\n"
                f"**{self.home_team}:** {home_total}/{self.home_goals} goles cargados\n"
                f"**{self.away_team}:** {away_total}/{self.away_goals} goles cargados",
                ephemeral=True,
            )
            return

        conn = league.db(runtime, interaction.guild_id)
        try:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                "DELETE FROM league_goal_events WHERE source_message_id=?",
                (self.source_message_id,),
            )
            for player, team, goals in home_rows + away_rows:
                conn.execute(
                    """
                    INSERT INTO league_goal_events
                        (source_message_id, player, team, goals, confidence)
                    VALUES (?, ?, ?, ?, 1.0)
                    """,
                    (self.source_message_id, player, team, int(goals)),
                )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

        try:
            if BOT is not None:
                await league.refresh(runtime, BOT, interaction.guild_id)
        except Exception as exc:
            print(f"AJAP Liga: goleadores guardados pero refresh falló: {exc}")

        total_players = len(home_rows) + len(away_rows)
        total_goals = home_total + away_total
        await interaction.response.send_message(
            "✅ Goleadores guardados/corregidos sin modificar el marcador.\n"
            f"**{self.home_team} {self.home_goals}–{self.away_goals} {self.away_team}** · "
            f"{total_players} jugador(es) · ⚽ {total_goals}",
            ephemeral=True,
        )


async def _open_for_source(interaction: discord.Interaction, source_message_id: int):
    runtime = _runtime()
    if not interaction.guild_id or not runtime or not runtime.es_admin(interaction):
        await interaction.response.send_message("⛔ Solo administradores.", ephemeral=True)
        return

    match = _match_for_source(runtime, interaction.guild_id, int(source_message_id))
    if not match:
        await interaction.response.send_message(
            "⚠️ No encontré un resultado oficial asociado a ese mensaje.", ephemeral=True
        )
        return

    existing = _existing_scorers(runtime, interaction.guild_id, int(source_message_id))
    await interaction.response.send_modal(
        ManualScorersModal(int(source_message_id), match, existing)
    )


class ManualScorersView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        button = discord.ui.Button(
            label="CARGAR / CORREGIR GOLEADORES",
            emoji="⚽",
            style=discord.ButtonStyle.secondary,
            custom_id="ajap:league:manual-scorers",
        )
        button.callback = self._open
        self.add_item(button)

    async def _open(self, interaction: discord.Interaction):
        runtime = _runtime()
        if not interaction.guild_id or not runtime or not runtime.es_admin(interaction):
            await interaction.response.send_message("⛔ Solo administradores.", ephemeral=True)
            return

        source_message_id = _source_from_staff_message(
            runtime, interaction.guild_id, interaction.message.id
        )
        if not source_message_id:
            await interaction.response.send_message(
                "⚠️ Esta tarjeta no está vinculada a un resultado manual resuelto.",
                ephemeral=True,
            )
            return
        await _open_for_source(interaction, source_message_id)


@app_commands.command(
    name="cargar_goleadores_manual",
    description="Carga o corrige goleadores de un resultado de Liga ya guardado (Staff).",
)
@app_commands.describe(mensaje="Enlace del mensaje original del resultado en Discord")
async def cargar_goleadores_manual(interaction: discord.Interaction, mensaje: str):
    runtime = _runtime()
    if not interaction.guild_id or not runtime or not runtime.es_admin(interaction):
        await interaction.response.send_message("⛔ Solo administradores.", ephemeral=True)
        return

    parsed = _parse_message_link(mensaje)
    if not parsed:
        await interaction.response.send_message(
            "⚠️ Pegá el enlace completo del mensaje original del resultado.", ephemeral=True
        )
        return

    guild_id, _channel_id, message_id = parsed
    if int(guild_id) != int(interaction.guild_id):
        await interaction.response.send_message(
            "⚠️ El mensaje tiene que pertenecer a este mismo servidor.", ephemeral=True
        )
        return

    await _open_for_source(interaction, int(message_id))


_original_manual_score_submit = strict.LeagueManualScoreModal.on_submit


async def _manual_score_submit_with_scorers(self, interaction: discord.Interaction):
    await _original_manual_score_submit(self, interaction)

    try:
        runtime = _runtime()
        if (
            interaction.guild_id
            and runtime
            and runtime.es_admin(interaction)
            and interaction.message is not None
        ):
            source_message_id = _source_from_staff_message(
                runtime, interaction.guild_id, self.staff_message_id
            )
            if source_message_id and _match_for_source(
                runtime, interaction.guild_id, source_message_id
            ):
                await interaction.message.edit(view=ManualScorersView())
    except Exception as exc:
        print(f"AJAP Liga: no se pudo agregar botón manual de goleadores: {exc}")


if not getattr(strict.LeagueManualScoreModal.on_submit, "_ajap_manual_scorers_wrapped", False):
    _manual_score_submit_with_scorers._ajap_manual_scorers_wrapped = True
    strict.LeagueManualScoreModal.on_submit = _manual_score_submit_with_scorers


async def _restore_resolved_buttons(guild: discord.Guild):
    runtime = _runtime()
    if not runtime:
        return

    strict._ensure_schema(runtime, guild.id)
    conn = league.db(runtime, guild.id)
    try:
        rows = conn.execute(
            """
            SELECT staff_channel_id, staff_message_id, source_message_id
            FROM league_manual_reviews
            WHERE status='RESUELTO'
              AND staff_channel_id IS NOT NULL
              AND staff_message_id IS NOT NULL
            ORDER BY resolved_at DESC
            LIMIT 100
            """
        ).fetchall()
    finally:
        conn.close()

    for row in rows:
        if not _match_for_source(runtime, guild.id, int(row["source_message_id"])):
            continue
        channel = guild.get_channel(int(row["staff_channel_id"]))
        if channel is None and BOT is not None:
            try:
                channel = await BOT.fetch_channel(int(row["staff_channel_id"]))
            except Exception:
                continue
        if channel is None or not hasattr(channel, "fetch_message"):
            continue
        try:
            message = await channel.fetch_message(int(row["staff_message_id"]))
            await message.edit(view=ManualScorersView())
        except Exception:
            continue


async def _sync_manual_scorers_to_guilds():
    bot = BOT
    if bot is None or not bot.user:
        return

    for guild in list(bot.guilds):
        target = discord.Object(id=int(guild.id))
        try:
            bot.tree.add_command(
                cargar_goleadores_manual,
                guild=target,
                override=True,
            )
            await bot.tree.sync(guild=target)
        except Exception as exc:
            print(
                f"ERROR AJAP Liga sync cargar_goleadores_manual guild={getattr(guild, 'id', '?')}: {exc}"
            )

        try:
            await _restore_resolved_buttons(guild)
        except Exception as exc:
            print(
                f"AJAP Liga: no se pudieron restaurar botones de goleadores guild={guild.id}: {exc}"
            )


def _install(runtime, bot):
    global APP, BOT
    APP, BOT = runtime, bot
    if getattr(runtime, "_ajap_league_manual_scorers_patch", False):
        return

    existing = bot.tree.get_command("cargar_goleadores_manual")
    if existing is not None:
        bot.tree.remove_command("cargar_goleadores_manual")
    bot.tree.add_command(cargar_goleadores_manual)

    try:
        bot.add_view(ManualScorersView())
    except Exception as exc:
        print(f"AJAP Liga: no se pudo registrar vista persistente de goleadores: {exc}")

    if not getattr(bot, "_ajap_manual_scorers_sync_listener", False):
        bot.add_listener(_sync_manual_scorers_to_guilds, "on_ready")
        bot._ajap_manual_scorers_sync_listener = True

    runtime._ajap_league_manual_scorers_patch = True
    print("AJAP Liga: carga/corrección manual de goleadores activa")


_original_apply_guild_isolation_patch = guild_isolation.apply_guild_isolation_patch


def _apply_guild_isolation_then_manual_scorers(runtime, bot):
    _original_apply_guild_isolation_patch(runtime, bot)
    _install(runtime, bot)


if not getattr(
    guild_isolation.apply_guild_isolation_patch,
    "_ajap_league_manual_scorers_wrapped",
    False,
):
    _apply_guild_isolation_then_manual_scorers._ajap_league_manual_scorers_wrapped = True
    guild_isolation.apply_guild_isolation_patch = _apply_guild_isolation_then_manual_scorers
