"""Manual scorer fallback for Staff-resolved Liga results.

If vision misses one or more scorers, the resolved Staff card keeps a persistent
"Agregar goleador" button. Staff can enter a player, club and the player's total
goals for that match. The entry is roster-validated, cannot make a club exceed
the official score, updates the scorer table immediately and survives restarts.
"""

from __future__ import annotations

import difflib

import discord

import guild_isolation_patch as guild_isolation
import league_automation_patch as league
import league_manual_review_parity_patch as parity
import league_validation_admin_review_patch as strict


APP = None
BOT = None
PREFIX = "ajap:league:manual-scorer:"


def _runtime():
    return APP or strict._runtime()


def _review(runtime, guild_id: int, staff_message_id: int):
    return strict._review_for_staff_message(runtime, int(guild_id), int(staff_message_id))


def _club_score(review, club: str):
    if str(club).casefold() == str(review["home_team"] or "").casefold():
        return int(review["home_goals"] or 0)
    if str(club).casefold() == str(review["away_team"] or "").casefold():
        return int(review["away_goals"] or 0)
    return None


def _resolve_match_club(review, raw: str):
    candidate = league.canonical_team(raw)
    home = str(review["home_team"] or "")
    away = str(review["away_team"] or "")
    for club in (home, away):
        if candidate and str(candidate).casefold() == club.casefold():
            return club
        if league.norm(raw) == league.norm(club):
            return club
    return None


def _resolve_roster_player(runtime, guild_id: int, club: str, raw: str):
    key = league.norm(raw)
    if not key:
        return None

    names = []
    for row in league.roster(runtime, int(guild_id)):
        row_club = league.canonical_team(row["club"]) or str(row["club"] or "")
        if str(row_club).casefold() != str(club).casefold():
            continue
        name = str(row["name"] or "").strip()
        if name:
            names.append(name)

    exact = {league.norm(name): name for name in names}
    if key in exact:
        return exact[key]
    hit = difflib.get_close_matches(key, exact.keys(), n=1, cutoff=0.84)
    return exact[hit[0]] if hit else None


def _scorer_rows(runtime, guild_id: int, source_message_id: int):
    conn = league.db(runtime, int(guild_id))
    try:
        return conn.execute(
            """
            SELECT player, team, SUM(goals) AS goals
            FROM league_goal_events
            WHERE source_message_id=?
            GROUP BY player COLLATE NOCASE, COALESCE(team, '') COLLATE NOCASE
            ORDER BY team COLLATE NOCASE, goals DESC, player COLLATE NOCASE
            """,
            (int(source_message_id),),
        ).fetchall()
    finally:
        conn.close()


def _scorers_text(runtime, guild_id: int, source_message_id: int):
    rows = _scorer_rows(runtime, guild_id, source_message_id)
    if not rows:
        return "⚠️ No hay goleadores cargados. Usá **Agregar goleador** para cargarlos manualmente."
    lines = []
    for row in rows[:20]:
        club = f" — {row['team']}" if row["team"] else ""
        lines.append(f"⚽ **{row['player']}**{club} • {int(row['goals'])}")
    return "\n".join(lines)


def _set_scorers_field(embed: discord.Embed, value: str):
    for index, field in enumerate(embed.fields):
        if str(field.name).casefold() == "goleadores":
            embed.set_field_at(index, name="Goleadores", value=value[:1024], inline=False)
            return
    embed.add_field(name="Goleadores", value=value[:1024], inline=False)


async def _refresh_staff_card(interaction: discord.Interaction, review):
    if interaction.message is None:
        return
    embed = (
        interaction.message.embeds[0].copy()
        if interaction.message.embeds
        else discord.Embed(
            title="✅ RESULTADO CARGADO MANUALMENTE",
            description=(
                f"**{review['home_team']} {int(review['home_goals'])}–"
                f"{int(review['away_goals'])} {review['away_team']}**"
            ),
            color=discord.Color.green(),
        )
    )
    _set_scorers_field(
        embed,
        _scorers_text(
            _runtime(), interaction.guild_id, int(review["source_message_id"])
        ),
    )
    await interaction.message.edit(embed=embed, view=ManualScorerView())


def _upsert_manual_scorer(runtime, guild_id: int, review, player: str, club: str, goals: int):
    source_id = int(review["source_message_id"])
    score_limit = _club_score(review, club)
    if score_limit is None:
        return False, "Ese equipo no pertenece a este partido."
    if goals < 1:
        return False, "Los goles del jugador deben ser al menos 1."
    if goals > score_limit:
        return False, f"{club} hizo {score_limit} gol(es); ese jugador no puede tener {goals}."

    conn = league.db(runtime, int(guild_id))
    try:
        conn.execute("BEGIN IMMEDIATE")
        rows = conn.execute(
            "SELECT id, player, team, goals FROM league_goal_events WHERE source_message_id=?",
            (source_id,),
        ).fetchall()

        same_ids = []
        other_total = 0
        for row in rows:
            same_club = str(row["team"] or "").casefold() == str(club).casefold()
            same_player = league.norm(row["player"]) == league.norm(player)
            if same_club and same_player:
                same_ids.append(int(row["id"]))
            elif same_club:
                other_total += int(row["goals"] or 0)

        if other_total + int(goals) > int(score_limit):
            conn.rollback()
            return (
                False,
                f"Con esa carga, los goleadores de {club} sumarían "
                f"{other_total + int(goals)} pero el resultado fue {score_limit}."
            )

        if same_ids:
            keep = same_ids[0]
            conn.execute(
                "UPDATE league_goal_events SET player=?, team=?, goals=?, confidence=1.0 WHERE id=?",
                (str(player), str(club), int(goals), keep),
            )
            if len(same_ids) > 1:
                placeholders = ",".join("?" for _ in same_ids[1:])
                conn.execute(
                    f"DELETE FROM league_goal_events WHERE id IN ({placeholders})",
                    tuple(same_ids[1:]),
                )
        else:
            conn.execute(
                """
                INSERT INTO league_goal_events
                    (source_message_id, player, team, goals, confidence)
                VALUES (?, ?, ?, ?, 1.0)
                """,
                (source_id, str(player), str(club), int(goals)),
            )
        conn.commit()
        return True, None
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


class ManualScorerModal(discord.ui.Modal, title="Agregar goleador"):
    player = discord.ui.TextInput(
        label="Jugador",
        placeholder="Ej: Diego Milito",
        required=True,
        max_length=100,
    )
    team = discord.ui.TextInput(
        label="Equipo",
        placeholder="Uno de los dos equipos del partido",
        required=True,
        max_length=80,
    )
    goals = discord.ui.TextInput(
        label="Goles de este jugador (total)",
        placeholder="Ej: 2",
        required=True,
        max_length=2,
    )

    def __init__(self, staff_message_id: int):
        super().__init__()
        self.staff_message_id = int(staff_message_id)

    async def on_submit(self, interaction: discord.Interaction):
        runtime = _runtime()
        if not interaction.guild_id or not runtime.es_admin(interaction):
            await interaction.response.send_message("⛔ Solo administradores.", ephemeral=True)
            return

        review = _review(runtime, interaction.guild_id, self.staff_message_id)
        if not review or str(review["status"] or "").upper() != "RESUELTO":
            await interaction.response.send_message(
                "⚠️ Este resultado manual no está disponible para cargar goleadores.",
                ephemeral=True,
            )
            return

        club = _resolve_match_club(review, self.team.value)
        if not club:
            await interaction.response.send_message(
                f"⚠️ El equipo debe ser **{review['home_team']}** o **{review['away_team']}**.",
                ephemeral=True,
            )
            return

        player = _resolve_roster_player(
            runtime, interaction.guild_id, club, self.player.value
        )
        if not player:
            await interaction.response.send_message(
                f"⚠️ No encontré **{self.player.value}** en la plantilla registrada de **{club}**.",
                ephemeral=True,
            )
            return

        try:
            goals = int(str(self.goals.value).strip())
        except ValueError:
            await interaction.response.send_message("⚠️ Los goles deben ser un número entero.", ephemeral=True)
            return

        ok, error = _upsert_manual_scorer(
            runtime, interaction.guild_id, review, player, club, goals
        )
        if not ok:
            await interaction.response.send_message(f"⚠️ {error}", ephemeral=True)
            return

        bot = BOT or strict.BOT or interaction.client
        try:
            await league.refresh(runtime, bot, interaction.guild_id)
        except Exception as exc:
            print(f"AJAP Liga: goleador manual guardado pero refresh falló: {exc}")

        await interaction.response.send_message(
            f"✅ Goleador guardado: **{player} — {club} • ⚽ {goals}**.",
            ephemeral=True,
        )
        try:
            await _refresh_staff_card(interaction, review)
        except Exception as exc:
            print(f"AJAP Liga: no se pudo refrescar tarjeta tras goleador manual: {exc}")


class ManualScorerView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Agregar goleador",
        emoji="⚽",
        style=discord.ButtonStyle.primary,
        custom_id=PREFIX + "add",
    )
    async def add(self, interaction: discord.Interaction, button: discord.ui.Button):
        runtime = _runtime()
        if not interaction.guild_id or interaction.message is None:
            return
        if not runtime.es_admin(interaction):
            await interaction.response.send_message("⛔ Solo administradores.", ephemeral=True)
            return
        review = _review(runtime, interaction.guild_id, interaction.message.id)
        if not review or str(review["status"] or "").upper() != "RESUELTO":
            await interaction.response.send_message(
                "⚠️ No pude vincular esta tarjeta con un resultado manual resuelto.",
                ephemeral=True,
            )
            return
        await interaction.response.send_modal(ManualScorerModal(interaction.message.id))


async def _edit_staff_review_message_with_scorer_button(interaction, review, embed):
    try:
        channel = interaction.guild.get_channel(int(review["staff_channel_id"] or 0))
        if channel is None and review["staff_channel_id"]:
            channel = await interaction.guild.fetch_channel(int(review["staff_channel_id"]))
        if channel is None:
            return
        message = await channel.fetch_message(int(review["staff_message_id"]))
        _set_scorers_field(
            embed,
            _scorers_text(
                _runtime(), interaction.guild_id, int(review["source_message_id"])
            ),
        )
        await message.edit(embed=embed, view=ManualScorerView())
    except Exception as exc:
        print(f"AJAP Liga: no se pudo activar carga manual de goleadores: {exc}")


# The parity finalizer calls this global dynamically, so replacing it here makes
# every newly resolved Staff card keep the manual scorer fallback button.
parity._edit_staff_review_message = _edit_staff_review_message_with_scorer_button


_ORIGINAL_APPLY = guild_isolation.apply_guild_isolation_patch


def _apply(runtime, bot):
    global APP, BOT
    _ORIGINAL_APPLY(runtime, bot)
    APP, BOT = runtime, bot
    if getattr(runtime, "_ajap_manual_scorer_entry", False):
        return
    try:
        bot.add_view(ManualScorerView())
    except Exception as exc:
        print(f"AJAP Liga: no se pudo registrar vista persistente de goleadores manuales: {exc}")
    runtime._ajap_manual_scorer_entry = True
    print("AJAP Liga: fallback manual de goleadores activo")


if not getattr(guild_isolation.apply_guild_isolation_patch, "_ajap_manual_scorer_wrapper", False):
    _apply._ajap_manual_scorer_wrapper = True
    guild_isolation.apply_guild_isolation_patch = _apply
