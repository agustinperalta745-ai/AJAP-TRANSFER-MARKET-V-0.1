"""One simple persistent Staff panel for AJPA match management.

Flow:
  GESTIONAR PARTIDO -> MARCADOR / GOLEADORES
  GOLEADORES -> equipo -> jugador de la plantilla -> cantidad de goles -> volver

No scorer names or team names need to be typed. Player lists are paged when a
roster has more than Discord's 25 select options. The persistent entry button
survives restarts; the ephemeral wizard is intentionally short-lived.
"""
from __future__ import annotations

import asyncio
import json
import sqlite3

import discord

import guild_isolation_patch as guild_isolation
import league_automation_patch as league
import league_validation_admin_review_patch as strict
import league_manual_scorer_entry_patch as entry
import league_persistent_result_admin_controls_patch as controls

APP = None
BOT = None
MANAGE_ID = "ajap:league:manage-match"


def _runtime():
    return APP or controls.APP or strict._runtime()


def _review(runtime, guild_id: int, staff_message_id: int):
    return strict._review_for_staff_message(runtime, int(guild_id), int(staff_message_id))


def _match(runtime, guild_id: int, source_id: int):
    conn = league.db(runtime, int(guild_id))
    try:
        return conn.execute(
            "SELECT * FROM league_matches WHERE source_message_id=? LIMIT 1",
            (int(source_id),),
        ).fetchone()
    finally:
        conn.close()


def _tables(conn):
    return {str(r[0]) for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}


def _scorer_rows(runtime, guild_id: int, source_id: int):
    conn = league.db(runtime, int(guild_id))
    try:
        return conn.execute(
            """
            SELECT player,team,SUM(goals) AS goals
            FROM league_goal_events
            WHERE source_message_id=?
            GROUP BY player COLLATE NOCASE, COALESCE(team,'') COLLATE NOCASE
            ORDER BY team COLLATE NOCASE, player COLLATE NOCASE
            """,
            (int(source_id),),
        ).fetchall()
    finally:
        conn.close()


def _summary(runtime, guild_id: int, review) -> str:
    source = int(review["source_message_id"])
    match = _match(runtime, guild_id, source)
    if not match:
        home = str(review["home_team"] or "Equipo 1")
        away = str(review["away_team"] or "Equipo 2")
        hg = review["home_goals"]
        ag = review["away_goals"]
        score = f"{home} {hg if hg is not None else '?'}–{ag if ag is not None else '?'} {away}"
        return f"📝 **RESULTADO PENDIENTE**\n**{score}**\n\nPrimero confirmá/corregí el marcador."

    home, away = str(match["home_team"]), str(match["away_team"])
    hg, ag = int(match["home_goals"]), int(match["away_goals"])
    rows = _scorer_rows(runtime, guild_id, source)
    lines = [f"🛠️ **GESTIONAR PARTIDO**\n**{home} {hg}–{ag} {away}**"]
    totals = {home.casefold(): 0, away.casefold(): 0}
    by_team = {home.casefold(): [], away.casefold(): []}
    for row in rows:
        club = league.canonical_team(row["team"]) or str(row["team"] or "")
        key = club.casefold()
        if key not in by_team:
            continue
        goals = int(row["goals"] or 0)
        totals[key] += goals
        by_team[key].append(f"{row['player']}{' x'+str(goals) if goals > 1 else ''}")
    for club, limit in ((home, hg), (away, ag)):
        names = by_team[club.casefold()]
        if names:
            lines.append(f"⚽ **{club}:** {', '.join(names)}")
        missing = max(0, limit - totals[club.casefold()])
        if missing:
            lines.append(f"⚠️ {club}: faltan **{missing}** gol(es) por atribuir")
    return "\n".join(lines)


async def _sync_public(guild: discord.Guild, source_id: int):
    try:
        import league_result_message_sync_patch as public_sync
        await public_sync.sync_public_reply(guild, int(source_id), corrected=True, force=True)
    except Exception as exc:
        print(f"AJAP unified manager public sync omitido source={source_id}: {type(exc).__name__}: {exc}")


async def _refresh_staff_card(guild: discord.Guild, review):
    try:
        channel = guild.get_channel(int(review["staff_channel_id"] or 0))
        if channel is None and review["staff_channel_id"]:
            channel = await guild.fetch_channel(int(review["staff_channel_id"]))
        if not channel:
            return
        msg = await channel.fetch_message(int(review["staff_message_id"]))
        runtime = _runtime()
        image_url = controls._image_from_message(msg)
        if str(review["status"] or "").upper() == "RESUELTO":
            embed = controls._control_embed(runtime, guild.id, review, image_url)
            await msg.edit(embed=embed, view=UnifiedPersistentView())
        else:
            await msg.edit(view=UnifiedPersistentView())
    except Exception as exc:
        print(f"AJAP unified manager: no pude refrescar tarjeta: {type(exc).__name__}: {exc}")


class ScoreOnlyModal(discord.ui.Modal, title="Corregir marcador"):
    def __init__(self, staff_message_id: int, home: str, away: str, hg: int, ag: int):
        super().__init__(custom_id="ajap:league:manage-score-modal")
        self.staff_message_id = int(staff_message_id)
        self.home = str(home)
        self.away = str(away)
        self.home_goals = discord.ui.TextInput(
            label=f"Goles {self.home}"[:45], default=str(int(hg)), required=True, max_length=2
        )
        self.away_goals = discord.ui.TextInput(
            label=f"Goles {self.away}"[:45], default=str(int(ag)), required=True, max_length=2
        )
        self.add_item(self.home_goals)
        self.add_item(self.away_goals)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)
        runtime = _runtime()
        if runtime is None or not interaction.guild_id or not runtime.es_admin(interaction):
            await interaction.followup.send("⛔ Solo administradores.", ephemeral=True)
            return
        review = _review(runtime, interaction.guild_id, self.staff_message_id)
        if not review:
            await interaction.followup.send("⚠️ No pude identificar el partido.", ephemeral=True)
            return
        try:
            hg = int(str(self.home_goals.value).strip())
            ag = int(str(self.away_goals.value).strip())
        except ValueError:
            await interaction.followup.send("⚠️ Los goles deben ser números enteros.", ephemeral=True)
            return
        if not (0 <= hg <= 99 and 0 <= ag <= 99):
            await interaction.followup.send("⚠️ Marcador fuera de rango.", ephemeral=True)
            return

        source = int(review["source_message_id"])
        existing = _match(runtime, interaction.guild_id, source)
        conn = league.db(runtime, interaction.guild_id)
        try:
            conn.execute("BEGIN IMMEDIATE")
            if existing:
                conn.execute(
                    "UPDATE league_matches SET home_goals=?,away_goals=?,confidence=1.0 WHERE source_message_id=?",
                    (hg, ag, source),
                )
                # Never retain more attributed goals than the corrected score.
                for club, limit in ((self.home, hg), (self.away, ag)):
                    total = conn.execute(
                        "SELECT COALESCE(SUM(goals),0) FROM league_goal_events WHERE source_message_id=? AND team=? COLLATE NOCASE",
                        (source, club),
                    ).fetchone()[0]
                    if int(total or 0) > int(limit):
                        conn.execute(
                            "DELETE FROM league_goal_events WHERE source_message_id=? AND team=? COLLATE NOCASE",
                            (source, club),
                        )
            else:
                conn.execute(
                    """
                    INSERT INTO league_matches
                        (source_message_id,source_channel_id,author_id,home_team,away_team,home_goals,away_goals,confidence)
                    VALUES(?,?,?,?,?,?,?,1.0)
                    """,
                    (
                        source, int(review["source_channel_id"]),
                        int(review["source_author_id"] or interaction.user.id),
                        self.home, self.away, hg, ag,
                    ),
                )
                if "league_image_hashes" in _tables(conn):
                    try:
                        hashes = json.loads(review["image_hashes_json"] or "[]")
                    except Exception:
                        hashes = []
                    for digest in hashes:
                        conn.execute(
                            "INSERT OR IGNORE INTO league_image_hashes(image_hash,source_message_id) VALUES(?,?)",
                            (str(digest), source),
                        )
            conn.execute(
                """
                UPDATE league_manual_reviews
                SET status='RESUELTO',resolved_by=?,resolved_at=CURRENT_TIMESTAMP,
                    home_team=?,away_team=?,home_goals=?,away_goals=?
                WHERE source_message_id=?
                """,
                (int(interaction.user.id), self.home, self.away, hg, ag, source),
            )
            if "league_ges_result_queue" in _tables(conn):
                try:
                    conn.execute(
                        """
                        UPDATE league_ges_result_queue
                        SET home_team=?,away_team=?,home_goals=?,away_goals=?,updated_at=CURRENT_TIMESTAMP
                        WHERE source_message_id=?
                        """,
                        (self.home, self.away, hg, ag, source),
                    )
                except sqlite3.OperationalError:
                    conn.execute(
                        "UPDATE league_ges_result_queue SET home_goals=?,away_goals=?,updated_at=CURRENT_TIMESTAMP WHERE source_message_id=?",
                        (hg, ag, source),
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
            await controls._refresh_everything(runtime, bot, interaction.guild_id)
        except Exception as exc:
            print(f"AJAP unified manager refresh marcador: {exc}")
        review = _review(runtime, interaction.guild_id, self.staff_message_id)
        await _refresh_staff_card(interaction.guild, review)
        await _sync_public(interaction.guild, source)
        await interaction.followup.send(
            _summary(runtime, interaction.guild_id, review),
            view=ManagerPanelView(self.staff_message_id),
            ephemeral=True,
        )


class ManagerPanelView(discord.ui.View):
    def __init__(self, staff_message_id: int):
        super().__init__(timeout=900)
        self.staff_message_id = int(staff_message_id)

    @discord.ui.button(label="MARCADOR", emoji="✏️", style=discord.ButtonStyle.primary)
    async def score(self, interaction: discord.Interaction, button: discord.ui.Button):
        runtime = _runtime()
        if runtime is None or not interaction.guild_id:
            return
        review = _review(runtime, interaction.guild_id, self.staff_message_id)
        if not review:
            await interaction.response.send_message("⚠️ Partido no encontrado.", ephemeral=True)
            return
        match = _match(runtime, interaction.guild_id, int(review["source_message_id"]))
        home = str((match or review)["home_team"] or "")
        away = str((match or review)["away_team"] or "")
        home = strict._official_team(home) or home
        away = strict._official_team(away) or away
        if not home or not away or home == away:
            # Rare OCR case where teams were not identified; retain legacy editor.
            if match:
                await interaction.response.send_modal(controls.CorrectResultModal(self.staff_message_id, match))
            else:
                await interaction.response.send_modal(strict.LeagueManualScoreModal(self.staff_message_id))
            return
        hg = int((match or review)["home_goals"] or 0)
        ag = int((match or review)["away_goals"] or 0)
        await interaction.response.send_modal(ScoreOnlyModal(self.staff_message_id, home, away, hg, ag))

    @discord.ui.button(label="GOLEADORES", emoji="⚽", style=discord.ButtonStyle.success)
    async def scorers(self, interaction: discord.Interaction, button: discord.ui.Button):
        runtime = _runtime()
        if runtime is None or not interaction.guild_id:
            return
        review = _review(runtime, interaction.guild_id, self.staff_message_id)
        match = _match(runtime, interaction.guild_id, int(review["source_message_id"])) if review else None
        if not review or not match:
            await interaction.response.send_message("⚠️ Primero confirmá el marcador.", ephemeral=True)
            return
        await interaction.response.edit_message(
            content="Elegí el **equipo** del goleador:",
            view=TeamPickerView(self.staff_message_id, match),
        )

    @discord.ui.button(label="CERRAR", emoji="✅", style=discord.ButtonStyle.secondary)
    async def close(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content="✅ Gestión terminada.", view=None)


class TeamPickerView(discord.ui.View):
    def __init__(self, staff_message_id: int, match):
        super().__init__(timeout=900)
        self.staff_message_id = int(staff_message_id)
        options = [
            discord.SelectOption(label=str(match["home_team"])[:100], value=str(match["home_team"])),
            discord.SelectOption(label=str(match["away_team"])[:100], value=str(match["away_team"])),
        ]
        select = discord.ui.Select(placeholder="Elegí un equipo", min_values=1, max_values=1, options=options)
        select.callback = self.choose
        self.select = select
        self.add_item(select)

    async def choose(self, interaction: discord.Interaction):
        club = self.select.values[0]
        await interaction.response.edit_message(
            content=f"**{club}** — elegí el jugador de su plantilla:",
            view=PlayerPickerView(self.staff_message_id, club, page=0),
        )


class PlayerPickerView(discord.ui.View):
    def __init__(self, staff_message_id: int, club: str, page: int = 0):
        super().__init__(timeout=900)
        self.staff_message_id = int(staff_message_id)
        self.club = str(club)
        runtime = _runtime()
        guild_id = None
        # guild id is resolved from interaction at callback; roster rows are global-per-guild,
        # so build lazily in callback if this constructor cannot know it.
        self.page = max(0, int(page))
        placeholder = discord.ui.Select(
            placeholder="Cargando plantilla…",
            options=[discord.SelectOption(label="Abrir plantilla", value="__load__")],
        )
        placeholder.callback = self.load
        self.add_item(placeholder)

    def _players(self, guild_id: int):
        runtime = _runtime()
        names = []
        for row in league.roster(runtime, int(guild_id)):
            row_club = league.canonical_team(row["club"]) or str(row["club"] or "")
            if row_club.casefold() != self.club.casefold():
                continue
            name = str(row["name"] or "").strip()
            if name and name not in names:
                names.append(name)
        return sorted(names, key=str.casefold)

    async def load(self, interaction: discord.Interaction):
        players = self._players(interaction.guild_id)
        if not players:
            await interaction.response.edit_message(content=f"⚠️ No encontré plantilla cargada para **{self.club}**.", view=ManagerPanelView(self.staff_message_id))
            return
        await interaction.response.edit_message(
            content=f"**{self.club}** — elegí jugador:",
            view=PlayerPageView(self.staff_message_id, self.club, players, self.page),
        )


class PlayerPageView(discord.ui.View):
    def __init__(self, staff_message_id: int, club: str, players: list[str], page: int):
        super().__init__(timeout=900)
        self.staff_message_id = int(staff_message_id)
        self.club = str(club)
        self.players = list(players)
        self.page = max(0, int(page))
        start = self.page * 25
        chunk = self.players[start:start + 25]
        options = [discord.SelectOption(label=name[:100], value=str(i)) for i, name in enumerate(chunk, start=start)]
        select = discord.ui.Select(
            placeholder=f"Jugador ({start + 1}-{start + len(chunk)} de {len(self.players)})",
            min_values=1, max_values=1, options=options,
        )
        select.callback = self.choose
        self.select = select
        self.add_item(select)
        if self.page > 0:
            prev = discord.ui.Button(label="ANTERIORES", emoji="⬅️", style=discord.ButtonStyle.secondary)
            prev.callback = self.previous
            self.add_item(prev)
        if start + 25 < len(self.players):
            nxt = discord.ui.Button(label="SIGUIENTES", emoji="➡️", style=discord.ButtonStyle.secondary)
            nxt.callback = self.next
            self.add_item(nxt)

    async def choose(self, interaction: discord.Interaction):
        player = self.players[int(self.select.values[0])]
        runtime = _runtime()
        review = _review(runtime, interaction.guild_id, self.staff_message_id)
        match = _match(runtime, interaction.guild_id, int(review["source_message_id"]))
        limit = int(match["home_goals"] if self.club.casefold() == str(match["home_team"]).casefold() else match["away_goals"])
        await interaction.response.edit_message(
            content=f"**{player} — {self.club}**\n¿Cuántos goles hizo en este partido?",
            view=GoalPickerView(self.staff_message_id, self.club, player, limit),
        )

    async def previous(self, interaction: discord.Interaction):
        await interaction.response.edit_message(view=PlayerPageView(self.staff_message_id, self.club, self.players, self.page - 1))

    async def next(self, interaction: discord.Interaction):
        await interaction.response.edit_message(view=PlayerPageView(self.staff_message_id, self.club, self.players, self.page + 1))


class GoalPickerView(discord.ui.View):
    def __init__(self, staff_message_id: int, club: str, player: str, limit: int):
        super().__init__(timeout=900)
        self.staff_message_id = int(staff_message_id)
        self.club = str(club)
        self.player = str(player)
        max_goal = max(1, min(int(limit), 24))
        options = [discord.SelectOption(label="0 — borrar este goleador", value="0")]
        options.extend(discord.SelectOption(label=f"{n} gol{'es' if n != 1 else ''}", value=str(n)) for n in range(1, max_goal + 1))
        select = discord.ui.Select(placeholder="Cantidad de goles", min_values=1, max_values=1, options=options)
        select.callback = self.save
        self.select = select
        self.add_item(select)

    async def save(self, interaction: discord.Interaction):
        runtime = _runtime()
        review = _review(runtime, interaction.guild_id, self.staff_message_id)
        match = _match(runtime, interaction.guild_id, int(review["source_message_id"])) if review else None
        if not review or not match:
            await interaction.response.edit_message(content="⚠️ Partido no encontrado.", view=None)
            return
        goals = int(self.select.values[0])
        source = int(review["source_message_id"])
        if goals == 0:
            conn = league.db(runtime, interaction.guild_id)
            try:
                conn.execute(
                    "DELETE FROM league_goal_events WHERE source_message_id=? AND team=? COLLATE NOCASE AND lower(trim(player))=lower(trim(?))",
                    (source, self.club, self.player),
                )
                conn.commit()
            finally:
                conn.close()
            action = f"🗑️ {self.player} eliminado"
        else:
            ok, error = entry._upsert_manual_scorer(runtime, interaction.guild_id, review, self.player, self.club, goals)
            if not ok:
                await interaction.response.edit_message(content=f"⚠️ {error}", view=ManagerPanelView(self.staff_message_id))
                return
            action = f"✅ {self.player} x{goals} guardado"
        try:
            await controls._refresh_everything(runtime, BOT or interaction.client, interaction.guild_id)
        except Exception as exc:
            print(f"AJAP unified manager refresh goleador: {exc}")
        review = _review(runtime, interaction.guild_id, self.staff_message_id)
        await _refresh_staff_card(interaction.guild, review)
        await _sync_public(interaction.guild, source)
        await interaction.response.edit_message(
            content=f"{action}\n\n{_summary(runtime, interaction.guild_id, review)}\n\nElegí **GOLEADORES** para cargar al siguiente.",
            view=ManagerPanelView(self.staff_message_id),
        )


class UnifiedPersistentView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="GESTIONAR PARTIDO", emoji="🛠️", style=discord.ButtonStyle.primary,
        custom_id=MANAGE_ID,
    )
    async def manage(self, interaction: discord.Interaction, button: discord.ui.Button):
        runtime = _runtime()
        if runtime is None or not interaction.guild_id or interaction.message is None:
            return
        if not runtime.es_admin(interaction):
            await interaction.response.send_message("⛔ Solo administradores.", ephemeral=True)
            return
        review = _review(runtime, interaction.guild_id, interaction.message.id)
        if not review:
            await interaction.response.send_message("⚠️ No pude vincular esta tarjeta con un partido.", ephemeral=True)
            return
        await interaction.response.send_message(
            _summary(runtime, interaction.guild_id, review),
            view=ManagerPanelView(interaction.message.id),
            ephemeral=True,
        )


async def _repair_ajax_tottenham(runtime, guild_id: int):
    """User-verified 04/09 match: Ajax 2-2 Tottenham; four named scorers x1."""
    conn = league.db(runtime, int(guild_id))
    try:
        rows = conn.execute(
            """
            SELECT * FROM league_matches
            WHERE created_at >= '2026-09-04 00:00:00'
              AND home_team='Ajax' AND away_team='Tottenham Hotspur'
              AND home_goals=2 AND away_goals=2
            ORDER BY id DESC
            """
        ).fetchall()
        candidates = []
        for row in rows:
            scorers = conn.execute(
                "SELECT player,team,goals FROM league_goal_events WHERE source_message_id=?",
                (int(row["source_message_id"]),),
            ).fetchall()
            fingerprint = {(league.norm(s["player"]), str(s["team"] or "").casefold(), int(s["goals"] or 0)) for s in scorers}
            if (league.norm("Huntelaar"), "ajax", 2) in fingerprint or (
                any(league.norm(s["player"]) == league.norm("Huntelaar") for s in scorers)
                and not any(league.norm(s["player"]) == league.norm("Robbie Keane") for s in scorers)
            ):
                candidates.append(row)
        if len(candidates) != 1:
            return None
        row = candidates[0]
        source = int(row["source_message_id"])
        conn.execute("BEGIN IMMEDIATE")
        conn.execute("DELETE FROM league_goal_events WHERE source_message_id=?", (source,))
        for player, club in (
            ("Huntelaar", "Ajax"), ("Mitea", "Ajax"),
            ("Robbie Keane", "Tottenham Hotspur"), ("Defoe", "Tottenham Hotspur"),
        ):
            conn.execute(
                "INSERT INTO league_goal_events(source_message_id,player,team,goals,confidence) VALUES(?,?,?,?,1.0)",
                (source, player, club, 1),
            )
        conn.execute(
            "UPDATE league_manual_reviews SET home_team='Ajax',away_team='Tottenham Hotspur',home_goals=2,away_goals=2,status='RESUELTO' WHERE source_message_id=?",
            (source,),
        )
        if "league_ges_result_queue" in _tables(conn):
            try:
                conn.execute(
                    "UPDATE league_ges_result_queue SET home_team='Ajax',away_team='Tottenham Hotspur',home_goals=2,away_goals=2,updated_at=CURRENT_TIMESTAMP WHERE source_message_id=?",
                    (source,),
                )
            except sqlite3.OperationalError:
                pass
        league.standings(conn)
        conn.commit()
        return source
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


async def _on_ready():
    await asyncio.sleep(3)
    runtime = _runtime()
    bot = BOT
    if runtime is None or bot is None:
        return
    for guild in list(bot.guilds):
        try:
            source = await _repair_ajax_tottenham(runtime, guild.id)
            if source:
                await controls._refresh_everything(runtime, bot, guild.id)
                await _sync_public(guild, source)
                print(f"AJAP repair: Ajax 2-2 Tottenham scorers completos source={source}")
        except Exception as exc:
            print(f"AJAP Ajax-Tottenham repair warning guild={guild.id}: {type(exc).__name__}: {exc}")


# Keep the existing persistent machinery, but render one simple entry button.
controls.ResultAdminView = UnifiedPersistentView
strict.LeagueManualReviewView = UnifiedPersistentView

_ORIGINAL_APPLY = guild_isolation.apply_guild_isolation_patch


def _apply(runtime, bot):
    global APP, BOT
    _ORIGINAL_APPLY(runtime, bot)
    APP, BOT = runtime, bot
    controls.APP, controls.BOT = runtime, bot
    try:
        bot.add_view(UnifiedPersistentView())
    except Exception as exc:
        print(f"AJAP unified manager persistent view warning: {exc}")
    if not getattr(bot, "_ajap_unified_match_manager_ready", False):
        bot.add_listener(_on_ready, "on_ready")
        bot._ajap_unified_match_manager_ready = True
    print("AJAP Liga: GESTIONAR PARTIDO unificado activo (marcador + goleadores por selector)")


if not getattr(guild_isolation.apply_guild_isolation_patch, "_ajap_unified_match_manager_wrapper", False):
    _apply._ajap_unified_match_manager_wrapper = True
    guild_isolation.apply_guild_isolation_patch = _apply
