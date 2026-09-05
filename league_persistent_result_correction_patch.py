"""Persistent Staff tools for correcting official AJPA league results.

Every GES result card gets two permanent actions:
- CORREGIR RESULTADO: edits the existing league_matches row (never duplicates it),
  synchronizes GES/manual review data and refreshes standings/app data.
- GOLEADORES: add, correct or delete a scorer for that exact match.

The view uses timeout=None + stable custom_ids and is registered on every startup.
Existing GES cards are edited in place on_ready so old results gain the buttons too.
"""
from __future__ import annotations

import asyncio
import sqlite3

import discord

import guild_isolation_patch as guild_isolation
import league_automation_patch as league
import league_ges_result_queue_patch as ges
import league_validation_admin_review_patch as strict
import league_manual_scorer_entry_patch as scorer_entry

APP = None
BOT = None
_BASE_GES_VIEW = ges.GesView

CORRECT_ID = "ajap:league:ges:correct-result"
SCORER_ID = "ajap:league:ges:edit-scorer"


def _is_admin(interaction: discord.Interaction) -> bool:
    runtime = APP or strict._runtime()
    try:
        return bool(runtime and runtime.es_admin(interaction))
    except Exception:
        return bool(
            interaction.guild
            and isinstance(interaction.user, discord.Member)
            and interaction.user.guild_permissions.administrator
        )


def _table_exists(conn, table: str) -> bool:
    return bool(
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
            (str(table),),
        ).fetchone()
    )


def _match(runtime, guild_id: int, source_id: int):
    conn = league.db(runtime, int(guild_id))
    try:
        return conn.execute(
            "SELECT * FROM league_matches WHERE source_message_id=? LIMIT 1",
            (int(source_id),),
        ).fetchone()
    finally:
        conn.close()


def _row_for_ges_message(runtime, guild_id: int, ges_message_id: int):
    return ges._find(runtime, int(guild_id), message=int(ges_message_id))


def _scorers_text(runtime, guild_id: int, source_id: int) -> str:
    try:
        return scorer_entry._scorers_text(runtime, int(guild_id), int(source_id))
    except Exception:
        return "⚠️ No pude leer los goleadores actuales."


def _result_embed(guild: discord.Guild, row, actor=None):
    embed = ges._embed(guild, row, actor)
    try:
        source_id = int(row["source_message_id"])
        # Some earlier GES embed layers already add scorer fields. Only append a
        # compact field when no scorer detail is present.
        if not any("⚽" in str(field.name) or str(field.name).casefold() == "goleadores" for field in embed.fields):
            embed.add_field(
                name="Goleadores",
                value=_scorers_text(APP or strict._runtime(), guild.id, source_id)[:1024],
                inline=False,
            )
    except Exception:
        pass
    embed.set_footer(text="AJPA • GES Liga • Botones Staff persistentes: no vencen")
    return embed


def _clean_scorers_after_score_change(conn, source_id: int, home: str, away: str, hg: int, ag: int):
    """Preserve valid scorer data, but never leave impossible totals after a correction."""
    rows = conn.execute(
        "SELECT id,player,team,goals FROM league_goal_events WHERE source_message_id=?",
        (int(source_id),),
    ).fetchall()
    limits = {str(home).casefold(): int(hg), str(away).casefold(): int(ag)}
    valid_ids_by_team = {str(home).casefold(): [], str(away).casefold(): []}
    totals = {str(home).casefold(): 0, str(away).casefold(): 0}
    removed = False

    for row in rows:
        canonical = league.canonical_team(row["team"]) or str(row["team"] or "")
        key = str(canonical).casefold()
        if key not in limits:
            conn.execute("DELETE FROM league_goal_events WHERE id=?", (int(row["id"]),))
            removed = True
            continue
        valid_ids_by_team[key].append(int(row["id"]))
        totals[key] += int(row["goals"] or 0)

    # If a corrected score is lower than the already attributed total, clear that
    # team's attributions instead of guessing which scorer was wrong.
    for key, total in totals.items():
        if total <= limits[key]:
            continue
        ids = valid_ids_by_team[key]
        if ids:
            placeholders = ",".join("?" for _ in ids)
            conn.execute(f"DELETE FROM league_goal_events WHERE id IN ({placeholders})", tuple(ids))
            removed = True
    return removed


def _sync_related_rows(conn, source_id: int, home: str, away: str, hg: int, ag: int, actor_id: int):
    if _table_exists(conn, "league_ges_result_queue"):
        conn.execute(
            """
            UPDATE league_ges_result_queue
            SET home_team=?,away_team=?,home_goals=?,away_goals=?,updated_at=CURRENT_TIMESTAMP
            WHERE source_message_id=?
            """,
            (home, away, int(hg), int(ag), int(source_id)),
        )
    if _table_exists(conn, "league_manual_reviews"):
        conn.execute(
            """
            UPDATE league_manual_reviews
            SET home_team=?,away_team=?,home_goals=?,away_goals=?,
                status='RESUELTO',resolved_by=?,resolved_at=COALESCE(resolved_at,CURRENT_TIMESTAMP)
            WHERE source_message_id=?
            """,
            (home, away, int(hg), int(ag), int(actor_id), int(source_id)),
        )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS league_result_corrections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_message_id INTEGER NOT NULL,
            corrected_by INTEGER NOT NULL,
            old_home_team TEXT, old_away_team TEXT,
            old_home_goals INTEGER, old_away_goals INTEGER,
            new_home_team TEXT, new_away_team TEXT,
            new_home_goals INTEGER, new_away_goals INTEGER,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """
    )


class CorrectResultModal(discord.ui.Modal):
    def __init__(self, ges_message_id: int, current):
        super().__init__(title="Corregir resultado de Liga", custom_id="ajap:league:ges:correct-modal")
        self.ges_message_id = int(ges_message_id)
        self.home_team = discord.ui.TextInput(
            label="Equipo local",
            default=str(current["home_team"]),
            required=True,
            max_length=80,
        )
        self.home_goals = discord.ui.TextInput(
            label="Goles local",
            default=str(int(current["home_goals"])),
            required=True,
            max_length=2,
        )
        self.away_team = discord.ui.TextInput(
            label="Equipo visitante",
            default=str(current["away_team"]),
            required=True,
            max_length=80,
        )
        self.away_goals = discord.ui.TextInput(
            label="Goles visitante",
            default=str(int(current["away_goals"])),
            required=True,
            max_length=2,
        )
        for item in (self.home_team, self.home_goals, self.away_team, self.away_goals):
            self.add_item(item)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)
        runtime = APP or strict._runtime()
        if not interaction.guild_id or runtime is None or not _is_admin(interaction):
            await interaction.followup.send("⛔ Solo administradores.", ephemeral=True)
            return

        queue = _row_for_ges_message(runtime, interaction.guild_id, self.ges_message_id)
        if not queue:
            await interaction.followup.send("⚠️ No pude vincular esta tarjeta con el partido.", ephemeral=True)
            return
        source_id = int(queue["source_message_id"])
        current = _match(runtime, interaction.guild_id, source_id)
        if not current:
            await interaction.followup.send("⚠️ El partido ya no existe en la Liga.", ephemeral=True)
            return

        home = strict._official_team(self.home_team.value)
        away = strict._official_team(self.away_team.value)
        if not home or not away or home == away:
            await interaction.followup.send(
                "⚠️ Elegí dos equipos oficiales distintos de la Liga.", ephemeral=True
            )
            return
        try:
            hg = int(str(self.home_goals.value).strip())
            ag = int(str(self.away_goals.value).strip())
        except ValueError:
            await interaction.followup.send("⚠️ Los goles deben ser números enteros.", ephemeral=True)
            return
        if hg < 0 or ag < 0 or hg > 99 or ag > 99:
            await interaction.followup.send("⚠️ Marcador fuera de rango.", ephemeral=True)
            return

        old = (
            str(current["home_team"]), str(current["away_team"]),
            int(current["home_goals"]), int(current["away_goals"]),
        )
        scorers_cleared = False
        conn = league.db(runtime, interaction.guild_id)
        try:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                """
                UPDATE league_matches
                SET home_team=?,away_team=?,home_goals=?,away_goals=?,confidence=1.0
                WHERE source_message_id=?
                """,
                (home, away, hg, ag, source_id),
            )
            scorers_cleared = _clean_scorers_after_score_change(conn, source_id, home, away, hg, ag)
            _sync_related_rows(conn, source_id, home, away, hg, ag, interaction.user.id)
            conn.execute(
                """
                INSERT INTO league_result_corrections(
                    source_message_id,corrected_by,
                    old_home_team,old_away_team,old_home_goals,old_away_goals,
                    new_home_team,new_away_team,new_home_goals,new_away_goals
                ) VALUES(?,?,?,?,?,?,?,?,?,?)
                """,
                (source_id, int(interaction.user.id), old[0], old[1], old[2], old[3], home, away, hg, ag),
            )
            league.standings(conn)
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

        bot = BOT or interaction.client
        try:
            await league.refresh(runtime, bot, interaction.guild_id)
        except Exception as exc:
            print(f"AJAP correction refresh warning: {type(exc).__name__}: {exc}")

        queue = _row_for_ges_message(runtime, interaction.guild_id, self.ges_message_id)
        try:
            channel = interaction.guild.get_channel(int(queue["ges_channel_id"])) or await interaction.guild.fetch_channel(int(queue["ges_channel_id"]))
            message = await channel.fetch_message(self.ges_message_id)
            embed = _result_embed(interaction.guild, queue, interaction.user.id)
            # The old rendered PNG contains the old score; remove it after a score correction.
            try:
                await message.edit(embed=embed, view=PersistentGesView(str(queue["status"])), attachments=[])
            except TypeError:
                await message.edit(embed=embed, view=PersistentGesView(str(queue["status"])))
        except Exception as exc:
            print(f"AJAP correction card warning: {type(exc).__name__}: {exc}")

        note = "\n⚠️ Se limpiaron goleadores incompatibles; revisalos con el botón **GOLEADORES**." if scorers_cleared else ""
        await interaction.followup.send(
            f"✅ Resultado corregido: **{home} {hg}–{ag} {away}**. Tabla, historial y app recalculados.{note}",
            ephemeral=True,
        )


class ScorerEditModal(discord.ui.Modal):
    def __init__(self, ges_message_id: int):
        super().__init__(title="Cargar / corregir goleador", custom_id="ajap:league:ges:scorer-modal")
        self.ges_message_id = int(ges_message_id)
        self.player = discord.ui.TextInput(
            label="Jugador",
            placeholder="Ej: Huntelaar",
            required=True,
            max_length=100,
        )
        self.team = discord.ui.TextInput(
            label="Equipo",
            placeholder="Uno de los dos equipos del partido",
            required=True,
            max_length=80,
        )
        self.goals = discord.ui.TextInput(
            label="Goles totales (0 = borrar)",
            placeholder="Ej: 2",
            required=True,
            max_length=2,
        )
        for item in (self.player, self.team, self.goals):
            self.add_item(item)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)
        runtime = APP or strict._runtime()
        if not interaction.guild_id or runtime is None or not _is_admin(interaction):
            await interaction.followup.send("⛔ Solo administradores.", ephemeral=True)
            return
        queue = _row_for_ges_message(runtime, interaction.guild_id, self.ges_message_id)
        if not queue:
            await interaction.followup.send("⚠️ No pude vincular esta tarjeta con el partido.", ephemeral=True)
            return
        source_id = int(queue["source_message_id"])
        match = _match(runtime, interaction.guild_id, source_id)
        if not match:
            await interaction.followup.send("⚠️ El partido ya no existe en la Liga.", ephemeral=True)
            return

        raw_team = league.canonical_team(self.team.value) or str(self.team.value).strip()
        club = None
        for candidate in (str(match["home_team"]), str(match["away_team"])):
            if str(raw_team).casefold() == candidate.casefold() or league.norm(self.team.value) == league.norm(candidate):
                club = candidate
                break
        if not club:
            await interaction.followup.send(
                f"⚠️ El equipo debe ser **{match['home_team']}** o **{match['away_team']}**.", ephemeral=True
            )
            return
        try:
            goals = int(str(self.goals.value).strip())
        except ValueError:
            await interaction.followup.send("⚠️ Los goles deben ser un número entero.", ephemeral=True)
            return
        if goals < 0 or goals > 99:
            await interaction.followup.send("⚠️ Cantidad de goles fuera de rango.", ephemeral=True)
            return

        if goals == 0:
            conn = league.db(runtime, interaction.guild_id)
            try:
                rows = conn.execute(
                    "SELECT id,player,team FROM league_goal_events WHERE source_message_id=?",
                    (source_id,),
                ).fetchall()
                ids = [
                    int(row["id"]) for row in rows
                    if league.norm(row["player"]) == league.norm(self.player.value)
                    and str(league.canonical_team(row["team"]) or row["team"] or "").casefold() == club.casefold()
                ]
                if not ids:
                    await interaction.followup.send("ℹ️ Ese goleador no estaba cargado.", ephemeral=True)
                    return
                conn.execute("BEGIN IMMEDIATE")
                placeholders = ",".join("?" for _ in ids)
                conn.execute(f"DELETE FROM league_goal_events WHERE id IN ({placeholders})", tuple(ids))
                conn.commit()
                player = str(self.player.value).strip()
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.close()
            action = f"eliminado: **{player} — {club}**"
        else:
            player = scorer_entry._resolve_roster_player(runtime, interaction.guild_id, club, self.player.value)
            if not player:
                await interaction.followup.send(
                    f"⚠️ No encontré **{self.player.value}** en la plantilla registrada de **{club}**.", ephemeral=True
                )
                return
            ok, error = scorer_entry._upsert_manual_scorer(runtime, interaction.guild_id, match, player, club, goals)
            if not ok:
                await interaction.followup.send(f"⚠️ {error}", ephemeral=True)
                return
            action = f"guardado: **{player} — {club} • ⚽ {goals}**"

        bot = BOT or interaction.client
        try:
            await league.refresh(runtime, bot, interaction.guild_id)
        except Exception as exc:
            print(f"AJAP scorer correction refresh warning: {type(exc).__name__}: {exc}")

        queue = _row_for_ges_message(runtime, interaction.guild_id, self.ges_message_id)
        try:
            channel = interaction.guild.get_channel(int(queue["ges_channel_id"])) or await interaction.guild.fetch_channel(int(queue["ges_channel_id"]))
            message = await channel.fetch_message(self.ges_message_id)
            embed = _result_embed(interaction.guild, queue, interaction.user.id)
            if message.attachments:
                embed.set_image(url=message.attachments[0].url)
            await message.edit(embed=embed, view=PersistentGesView(str(queue["status"])))
        except Exception as exc:
            print(f"AJAP scorer correction card warning: {type(exc).__name__}: {exc}")

        await interaction.followup.send(f"✅ Goleador {action}.", ephemeral=True)


class PersistentGesView(_BASE_GES_VIEW):
    def __init__(self, status="PENDIENTE"):
        super().__init__(status)
        correct = discord.ui.Button(
            label="CORREGIR RESULTADO",
            emoji="✏️",
            style=discord.ButtonStyle.danger,
            custom_id=CORRECT_ID,
            row=1,
        )
        correct.callback = self.correct_result
        self.add_item(correct)
        scorer = discord.ui.Button(
            label="GOLEADORES",
            emoji="⚽",
            style=discord.ButtonStyle.secondary,
            custom_id=SCORER_ID,
            row=1,
        )
        scorer.callback = self.edit_scorer
        self.add_item(scorer)

    async def correct_result(self, interaction: discord.Interaction):
        if not interaction.guild_id or interaction.message is None or not _is_admin(interaction):
            await interaction.response.send_message("⛔ Solo administradores.", ephemeral=True)
            return
        runtime = APP or strict._runtime()
        row = _row_for_ges_message(runtime, interaction.guild_id, interaction.message.id)
        if not row:
            await interaction.response.send_message("⚠️ Resultado no encontrado.", ephemeral=True)
            return
        current = _match(runtime, interaction.guild_id, int(row["source_message_id"]))
        if not current:
            await interaction.response.send_message("⚠️ Partido oficial no encontrado.", ephemeral=True)
            return
        await interaction.response.send_modal(CorrectResultModal(interaction.message.id, current))

    async def edit_scorer(self, interaction: discord.Interaction):
        if not interaction.guild_id or interaction.message is None or not _is_admin(interaction):
            await interaction.response.send_message("⛔ Solo administradores.", ephemeral=True)
            return
        await interaction.response.send_modal(ScorerEditModal(interaction.message.id))


async def _upgrade_existing_cards():
    await asyncio.sleep(2)
    runtime = APP or strict._runtime()
    bot = BOT or ges.BOT
    if runtime is None or bot is None or not bot.user:
        return
    upgraded = 0
    for guild in list(bot.guilds):
        conn = ges._conn(runtime, guild.id)
        try:
            rows = conn.execute(
                """
                SELECT * FROM league_ges_result_queue
                WHERE ges_message_id IS NOT NULL AND ges_channel_id IS NOT NULL
                ORDER BY created_at DESC
                """
            ).fetchall()
        finally:
            conn.close()
        for row in rows:
            try:
                channel = guild.get_channel(int(row["ges_channel_id"])) or await bot.fetch_channel(int(row["ges_channel_id"]))
                message = await channel.fetch_message(int(row["ges_message_id"]))
                await message.edit(view=PersistentGesView(str(row["status"] or "PENDIENTE")))
                upgraded += 1
            except (discord.NotFound, discord.Forbidden):
                continue
            except Exception as exc:
                print(f"AJAP persistent tools upgrade warning message={row['ges_message_id']}: {type(exc).__name__}: {exc}")
    print(f"AJAP Liga: tarjetas GES con botones persistentes actualizadas={upgraded}")


def _install(runtime, bot):
    global APP, BOT
    APP, BOT = runtime, bot
    ges.APP, ges.BOT = runtime, bot
    if getattr(bot, "_ajap_persistent_result_correction", False):
        return

    # Replace the global class used by all future GES sends/edits.
    ges.GesView = PersistentGesView
    try:
        bot.add_view(PersistentGesView())
    except Exception as exc:
        print(f"AJAP persistent result view registration warning: {exc}")

    # Explicitly register the other two historic persistent workflows too.
    try:
        bot.add_view(strict.LeagueManualReviewView())
    except Exception:
        pass
    try:
        import league_manual_scorer_button_timeout_fix_patch as fast
        bot.add_view(fast.FastManualScorerView())
    except Exception:
        pass

    if not getattr(bot, "_ajap_persistent_result_upgrade_listener", False):
        bot.add_listener(_upgrade_existing_cards, "on_ready")
        bot._ajap_persistent_result_upgrade_listener = True

    bot._ajap_persistent_result_correction = True
    print("AJAP Liga: CORREGIR RESULTADO + GOLEADORES persistentes activos en GES")


_PREVIOUS_APPLY = guild_isolation.apply_guild_isolation_patch


def _apply(runtime, bot):
    _PREVIOUS_APPLY(runtime, bot)
    _install(runtime, bot)


if not getattr(guild_isolation.apply_guild_isolation_patch, "_ajap_persistent_result_correction_wrapper", False):
    _apply._ajap_persistent_result_correction_wrapper = True
    guild_isolation.apply_guild_isolation_patch = _apply
