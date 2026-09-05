"""AJPA Staff scorer editor v2.

Replaces free-text scorer entry with a visual workflow:
- current scorers are always visible;
- choose one of the two match clubs;
- search by partial/similar player name OR browse that club's roster;
- choose the player and goal total;
- edit/delete already-loaded scorers;
- repeat without closing the match manager.

Only goal counts can be typed manually. Team/player identity always comes from
AJPA's official match/roster data, avoiding spelling mistakes.
"""
from __future__ import annotations

import asyncio
import difflib

import discord

import guild_isolation_patch as guild_isolation
import league_automation_patch as league
import league_validation_admin_review_patch as strict
import league_manual_scorer_entry_patch as entry
import league_persistent_result_admin_controls_patch as controls
import league_unified_match_manager_patch as unified

APP = None
BOT = None
MANAGE_ID = unified.MANAGE_ID


def _runtime():
    return APP or unified.APP or controls.APP or strict._runtime()


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


def _roster(runtime, guild_id: int, club: str) -> list[str]:
    names: list[str] = []
    seen: set[str] = set()
    for row in league.roster(runtime, int(guild_id)):
        row_club = league.canonical_team(row["club"]) or str(row["club"] or "")
        if row_club.casefold() != str(club).casefold():
            continue
        name = str(row["name"] or "").strip()
        key = league.norm(name)
        if name and key and key not in seen:
            seen.add(key)
            names.append(name)
    return sorted(names, key=str.casefold)


def _scorers(runtime, guild_id: int, source_id: int):
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


def _match_limits(match) -> dict[str, int]:
    return {
        str(match["home_team"]).casefold(): int(match["home_goals"]),
        str(match["away_team"]).casefold(): int(match["away_goals"]),
    }


def _current_total(runtime, guild_id: int, source_id: int, club: str, *, except_player: str | None = None) -> int:
    total = 0
    for row in _scorers(runtime, guild_id, source_id):
        if str(row["team"] or "").casefold() != str(club).casefold():
            continue
        if except_player and league.norm(row["player"]) == league.norm(except_player):
            continue
        total += int(row["goals"] or 0)
    return total


def _manager_text(runtime, guild_id: int, review) -> str:
    match = _match(runtime, guild_id, int(review["source_message_id"]))
    if not match:
        return "📝 **GESTIONAR PARTIDO**\nPrimero cargá/corregí el marcador."

    home, away = str(match["home_team"]), str(match["away_team"])
    hg, ag = int(match["home_goals"]), int(match["away_goals"])
    rows = _scorers(runtime, guild_id, int(match["source_message_id"]))
    by_team = {home.casefold(): [], away.casefold(): []}
    totals = {home.casefold(): 0, away.casefold(): 0}
    for row in rows:
        club = league.canonical_team(row["team"]) or str(row["team"] or "")
        key = club.casefold()
        if key not in by_team:
            continue
        n = int(row["goals"] or 0)
        totals[key] += n
        by_team[key].append(f"• {row['player']} — **{n}** gol{'es' if n != 1 else ''}")

    lines = [
        "🛠️ **GESTIONAR PARTIDO**",
        f"## {home} {hg}–{ag} {away}",
        "",
        "**Goleadores cargados**",
    ]
    for club, limit in ((home, hg), (away, ag)):
        key = club.casefold()
        lines.append(f"**{club}**")
        if by_team[key]:
            lines.extend(by_team[key])
        else:
            lines.append("• Ninguno cargado")
        missing = max(0, int(limit) - totals[key])
        if missing:
            lines.append(f"⚠️ Faltan **{missing}** gol(es) por atribuir")
    lines.extend([
        "",
        "Usá **AGREGAR GOLEADOR** para buscar en las plantillas o **EDITAR / ELIMINAR** para modificar los que ya figuran.",
    ])
    return "\n".join(lines)


async def _refresh(runtime, interaction: discord.Interaction, staff_message_id: int):
    review = _review(runtime, interaction.guild_id, staff_message_id)
    if not review:
        return None
    source_id = int(review["source_message_id"])
    bot = BOT or interaction.client
    try:
        await controls._refresh_everything(runtime, bot, interaction.guild_id)
    except Exception as exc:
        print(f"AJAP scorer editor v2 refresh warning: {type(exc).__name__}: {exc}")
    try:
        await unified._refresh_staff_card(interaction.guild, review)
    except Exception as exc:
        print(f"AJAP scorer editor v2 staff-card warning: {type(exc).__name__}: {exc}")
    try:
        await unified._sync_public(interaction.guild, source_id)
    except Exception as exc:
        print(f"AJAP scorer editor v2 public-sync warning: {type(exc).__name__}: {exc}")
    return _review(runtime, interaction.guild_id, staff_message_id)


async def _save(runtime, interaction: discord.Interaction, staff_message_id: int, club: str, player: str, goals: int):
    review = _review(runtime, interaction.guild_id, staff_message_id)
    if not review or str(review["status"] or "").upper() != "RESUELTO":
        return False, "No pude identificar un resultado oficial para esta tarjeta."
    ok, error = entry._upsert_manual_scorer(
        runtime, interaction.guild_id, review, str(player), str(club), int(goals)
    )
    if not ok:
        return False, str(error)
    await _refresh(runtime, interaction, staff_message_id)
    return True, None


async def _delete(runtime, interaction: discord.Interaction, staff_message_id: int, club: str, player: str):
    review = _review(runtime, interaction.guild_id, staff_message_id)
    if not review:
        return False
    conn = league.db(runtime, interaction.guild_id)
    try:
        conn.execute(
            """
            DELETE FROM league_goal_events
            WHERE source_message_id=? AND team=? COLLATE NOCASE
              AND lower(trim(player))=lower(trim(?))
            """,
            (int(review["source_message_id"]), str(club), str(player)),
        )
        conn.commit()
    finally:
        conn.close()
    await _refresh(runtime, interaction, staff_message_id)
    return True


class ManagePersistentView(discord.ui.View):
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
        match = _match(runtime, interaction.guild_id, int(review["source_message_id"]))
        if not match:
            # Keep the existing durable manual-result flow for genuinely pending results.
            await interaction.response.send_modal(strict.LeagueManualScoreModal(interaction.message.id))
            return
        await interaction.response.send_message(
            _manager_text(runtime, interaction.guild_id, review),
            view=MatchEditorView(interaction.message.id),
            ephemeral=True,
        )


class MatchEditorView(discord.ui.View):
    def __init__(self, staff_message_id: int):
        super().__init__(timeout=900)
        self.staff_message_id = int(staff_message_id)

    @discord.ui.button(label="MARCADOR", emoji="✏️", style=discord.ButtonStyle.primary, row=0)
    async def score(self, interaction: discord.Interaction, button: discord.ui.Button):
        runtime = _runtime()
        review = _review(runtime, interaction.guild_id, self.staff_message_id) if runtime else None
        match = _match(runtime, interaction.guild_id, int(review["source_message_id"])) if review else None
        if not match:
            await interaction.response.send_message("⚠️ Partido no encontrado.", ephemeral=True)
            return
        await interaction.response.send_modal(
            unified.ScoreOnlyModal(
                self.staff_message_id,
                str(match["home_team"]), str(match["away_team"]),
                int(match["home_goals"]), int(match["away_goals"]),
            )
        )

    @discord.ui.button(label="AGREGAR GOLEADOR", emoji="➕", style=discord.ButtonStyle.success, row=0)
    async def add(self, interaction: discord.Interaction, button: discord.ui.Button):
        runtime = _runtime()
        review = _review(runtime, interaction.guild_id, self.staff_message_id) if runtime else None
        match = _match(runtime, interaction.guild_id, int(review["source_message_id"])) if review else None
        if not match:
            await interaction.response.send_message("⚠️ Primero confirmá el marcador.", ephemeral=True)
            return
        await interaction.response.edit_message(
            content="Elegí el **equipo** del goleador:",
            view=TeamChooserView(self.staff_message_id, match),
        )

    @discord.ui.button(label="EDITAR / ELIMINAR", emoji="⚙️", style=discord.ButtonStyle.secondary, row=0)
    async def edit(self, interaction: discord.Interaction, button: discord.ui.Button):
        runtime = _runtime()
        review = _review(runtime, interaction.guild_id, self.staff_message_id) if runtime else None
        if not review:
            await interaction.response.send_message("⚠️ Partido no encontrado.", ephemeral=True)
            return
        rows = list(_scorers(runtime, interaction.guild_id, int(review["source_message_id"])))
        if not rows:
            await interaction.response.edit_message(
                content="ℹ️ Todavía no hay goleadores cargados.",
                view=MatchEditorView(self.staff_message_id),
            )
            return
        await interaction.response.edit_message(
            content="Elegí el goleador que querés **modificar o eliminar**:",
            view=ExistingScorerListView(self.staff_message_id, rows, page=0),
        )

    @discord.ui.button(label="CERRAR", emoji="✅", style=discord.ButtonStyle.secondary, row=1)
    async def close(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content="✅ Gestión terminada.", view=None)


class TeamChooserView(discord.ui.View):
    def __init__(self, staff_message_id: int, match):
        super().__init__(timeout=900)
        self.staff_message_id = int(staff_message_id)
        self.match = match
        self.select = discord.ui.Select(
            placeholder="Elegí uno de los dos equipos",
            min_values=1,
            max_values=1,
            options=[
                discord.SelectOption(label=str(match["home_team"])[:100], value=str(match["home_team"])),
                discord.SelectOption(label=str(match["away_team"])[:100], value=str(match["away_team"])),
            ],
        )
        self.select.callback = self.choose
        self.add_item(self.select)

    async def choose(self, interaction: discord.Interaction):
        club = self.select.values[0]
        await interaction.response.edit_message(
            content=_club_text(_runtime(), interaction.guild_id, self.staff_message_id, club),
            view=ClubScorerView(self.staff_message_id, club),
        )


def _club_text(runtime, guild_id: int, staff_message_id: int, club: str) -> str:
    review = _review(runtime, guild_id, staff_message_id)
    if not review:
        return f"**{club}**"
    match = _match(runtime, guild_id, int(review["source_message_id"]))
    rows = _scorers(runtime, guild_id, int(review["source_message_id"]))
    current = [
        f"• {r['player']} — {int(r['goals'] or 0)}"
        for r in rows if str(r["team"] or "").casefold() == str(club).casefold()
    ]
    limit = _match_limits(match).get(str(club).casefold(), 0) if match else 0
    used = sum(int(r["goals"] or 0) for r in rows if str(r["team"] or "").casefold() == str(club).casefold())
    lines = [f"## {club}", f"Marcador del equipo: **{limit}** · atribuidos: **{used}**"]
    lines.append("**Ya cargados:** " + (" · ".join(current) if current else "ninguno"))
    lines.append("\nElegí **BUSCAR JUGADOR** o **VER PLANTILLA**.")
    return "\n".join(lines)


class ClubScorerView(discord.ui.View):
    def __init__(self, staff_message_id: int, club: str):
        super().__init__(timeout=900)
        self.staff_message_id = int(staff_message_id)
        self.club = str(club)

    @discord.ui.button(label="BUSCAR JUGADOR", emoji="🔎", style=discord.ButtonStyle.primary)
    async def search(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(PlayerSearchModal(self.staff_message_id, self.club))

    @discord.ui.button(label="VER PLANTILLA", emoji="📋", style=discord.ButtonStyle.secondary)
    async def roster(self, interaction: discord.Interaction, button: discord.ui.Button):
        players = _roster(_runtime(), interaction.guild_id, self.club)
        if not players:
            await interaction.response.edit_message(
                content=f"⚠️ No encontré jugadores cargados para **{self.club}**.",
                view=MatchEditorView(self.staff_message_id),
            )
            return
        await interaction.response.edit_message(
            content=f"**{self.club}** — elegí un jugador:",
            view=PlayerListView(self.staff_message_id, self.club, players, page=0),
        )

    @discord.ui.button(label="VOLVER", emoji="↩️", style=discord.ButtonStyle.secondary)
    async def back(self, interaction: discord.Interaction, button: discord.ui.Button):
        runtime = _runtime()
        review = _review(runtime, interaction.guild_id, self.staff_message_id)
        await interaction.response.edit_message(
            content=_manager_text(runtime, interaction.guild_id, review),
            view=MatchEditorView(self.staff_message_id),
        )


class PlayerSearchModal(discord.ui.Modal, title="Buscar jugador"):
    query = discord.ui.TextInput(
        label="Nombre o parte del nombre",
        placeholder="Ej: hun, mite, robbie, van hooij...",
        required=True,
        min_length=1,
        max_length=60,
    )

    def __init__(self, staff_message_id: int, club: str):
        super().__init__(custom_id="ajap:league:scorer-search-v2")
        self.staff_message_id = int(staff_message_id)
        self.club = str(club)

    async def on_submit(self, interaction: discord.Interaction):
        players = _roster(_runtime(), interaction.guild_id, self.club)
        q = league.norm(self.query.value)
        ranked: list[tuple[float, str]] = []
        for name in players:
            key = league.norm(name)
            if not key:
                continue
            if q in key:
                score = 2.0 + min(1.0, len(q) / max(1, len(key)))
            else:
                score = difflib.SequenceMatcher(None, q, key).ratio()
            if score >= 0.45:
                ranked.append((score, name))
        ranked.sort(key=lambda item: (-item[0], item[1].casefold()))
        matches = [name for _, name in ranked[:25]]
        if not matches:
            await interaction.response.edit_message(
                content=f"No encontré jugadores parecidos a **{self.query.value}** en **{self.club}**. Probá otra búsqueda o abrí la plantilla.",
                view=ClubScorerView(self.staff_message_id, self.club),
            )
            return
        await interaction.response.edit_message(
            content=f"Resultados en **{self.club}** para **{self.query.value}** — tocá el jugador:",
            view=PlayerResultsView(self.staff_message_id, self.club, matches),
        )


class PlayerResultsView(discord.ui.View):
    def __init__(self, staff_message_id: int, club: str, players: list[str]):
        super().__init__(timeout=900)
        self.staff_message_id = int(staff_message_id)
        self.club = str(club)
        self.players = list(players)[:25]
        self.select = discord.ui.Select(
            placeholder="Elegí el jugador encontrado",
            min_values=1,
            max_values=1,
            options=[discord.SelectOption(label=name[:100], value=str(i)) for i, name in enumerate(self.players)],
        )
        self.select.callback = self.choose
        self.add_item(self.select)

    async def choose(self, interaction: discord.Interaction):
        player = self.players[int(self.select.values[0])]
        await _open_amount(interaction, self.staff_message_id, self.club, player)


class PlayerListView(discord.ui.View):
    PAGE = 25

    def __init__(self, staff_message_id: int, club: str, players: list[str], page: int = 0):
        super().__init__(timeout=900)
        self.staff_message_id = int(staff_message_id)
        self.club = str(club)
        self.players = list(players)
        self.page = max(0, int(page))
        start = self.page * self.PAGE
        chunk = self.players[start:start + self.PAGE]
        self.select = discord.ui.Select(
            placeholder=f"Plantilla · página {self.page + 1}",
            min_values=1,
            max_values=1,
            options=[discord.SelectOption(label=name[:100], value=str(start + i)) for i, name in enumerate(chunk)],
        )
        self.select.callback = self.choose
        self.add_item(self.select)

    async def choose(self, interaction: discord.Interaction):
        player = self.players[int(self.select.values[0])]
        await _open_amount(interaction, self.staff_message_id, self.club, player)

    @discord.ui.button(label="ANTERIOR", emoji="⬅️", style=discord.ButtonStyle.secondary, row=1)
    async def previous(self, interaction: discord.Interaction, button: discord.ui.Button):
        page = max(0, self.page - 1)
        await interaction.response.edit_message(
            view=PlayerListView(self.staff_message_id, self.club, self.players, page),
        )

    @discord.ui.button(label="SIGUIENTE", emoji="➡️", style=discord.ButtonStyle.secondary, row=1)
    async def next(self, interaction: discord.Interaction, button: discord.ui.Button):
        max_page = max(0, (len(self.players) - 1) // self.PAGE)
        page = min(max_page, self.page + 1)
        await interaction.response.edit_message(
            view=PlayerListView(self.staff_message_id, self.club, self.players, page),
        )

    @discord.ui.button(label="BUSCAR", emoji="🔎", style=discord.ButtonStyle.primary, row=1)
    async def search(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(PlayerSearchModal(self.staff_message_id, self.club))


async def _open_amount(interaction: discord.Interaction, staff_message_id: int, club: str, player: str):
    runtime = _runtime()
    review = _review(runtime, interaction.guild_id, staff_message_id)
    match = _match(runtime, interaction.guild_id, int(review["source_message_id"])) if review else None
    if not match:
        await interaction.response.edit_message(content="⚠️ Partido no encontrado.", view=MatchEditorView(staff_message_id))
        return
    limit = _match_limits(match).get(str(club).casefold(), 0)
    other = _current_total(runtime, interaction.guild_id, int(match["source_message_id"]), club, except_player=player)
    available = max(0, int(limit) - int(other))
    if available < 1:
        await interaction.response.edit_message(
            content=f"⚠️ **{club}** ya tiene todos sus {limit} gol(es) atribuidos. Editá/eliminá uno antes de agregar otro.",
            view=MatchEditorView(staff_message_id),
        )
        return
    await interaction.response.edit_message(
        content=f"**{player} — {club}**\n¿Cuántos goles hizo? Máximo disponible: **{available}**.",
        view=GoalAmountView(staff_message_id, club, player, available),
    )


class GoalAmountView(discord.ui.View):
    def __init__(self, staff_message_id: int, club: str, player: str, maximum: int):
        super().__init__(timeout=900)
        self.staff_message_id = int(staff_message_id)
        self.club = str(club)
        self.player = str(player)
        self.maximum = max(1, int(maximum))
        quick_max = min(self.maximum, 25)
        self.select = discord.ui.Select(
            placeholder="Elegí cantidad de goles",
            min_values=1,
            max_values=1,
            options=[
                discord.SelectOption(label=f"{n} gol{'es' if n != 1 else ''}", value=str(n))
                for n in range(1, quick_max + 1)
            ],
        )
        self.select.callback = self.save
        self.add_item(self.select)

    async def save(self, interaction: discord.Interaction):
        goals = int(self.select.values[0])
        await interaction.response.defer(ephemeral=True)
        ok, error = await _save(_runtime(), interaction, self.staff_message_id, self.club, self.player, goals)
        if not ok:
            await interaction.edit_original_response(content=f"⚠️ {error}", view=MatchEditorView(self.staff_message_id))
            return
        review = _review(_runtime(), interaction.guild_id, self.staff_message_id)
        await interaction.edit_original_response(
            content="✅ Goleador guardado.\n\n" + _manager_text(_runtime(), interaction.guild_id, review),
            view=MatchEditorView(self.staff_message_id),
        )

    @discord.ui.button(label="OTRA CANTIDAD", emoji="⌨️", style=discord.ButtonStyle.secondary, row=1)
    async def manual(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(
            ManualAmountModal(self.staff_message_id, self.club, self.player, self.maximum)
        )


class ManualAmountModal(discord.ui.Modal, title="Cantidad de goles"):
    goals = discord.ui.TextInput(
        label="Cantidad",
        placeholder="Ej: 2",
        required=True,
        max_length=2,
    )

    def __init__(self, staff_message_id: int, club: str, player: str, maximum: int):
        super().__init__(custom_id="ajap:league:scorer-amount-v2")
        self.staff_message_id = int(staff_message_id)
        self.club = str(club)
        self.player = str(player)
        self.maximum = int(maximum)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            goals = int(str(self.goals.value).strip())
        except ValueError:
            await interaction.response.send_message("⚠️ Ingresá un número entero.", ephemeral=True)
            return
        if goals < 1 or goals > self.maximum:
            await interaction.response.send_message(
                f"⚠️ La cantidad debe estar entre 1 y {self.maximum}.", ephemeral=True
            )
            return
        await interaction.response.defer(ephemeral=True)
        ok, error = await _save(_runtime(), interaction, self.staff_message_id, self.club, self.player, goals)
        if not ok:
            await interaction.edit_original_response(content=f"⚠️ {error}", view=MatchEditorView(self.staff_message_id))
            return
        review = _review(_runtime(), interaction.guild_id, self.staff_message_id)
        await interaction.edit_original_response(
            content="✅ Goleador guardado.\n\n" + _manager_text(_runtime(), interaction.guild_id, review),
            view=MatchEditorView(self.staff_message_id),
        )


class ExistingScorerListView(discord.ui.View):
    PAGE = 25

    def __init__(self, staff_message_id: int, rows, page: int = 0):
        super().__init__(timeout=900)
        self.staff_message_id = int(staff_message_id)
        self.rows = [(str(r["player"]), str(r["team"] or ""), int(r["goals"] or 0)) for r in rows]
        self.page = max(0, int(page))
        start = self.page * self.PAGE
        chunk = self.rows[start:start + self.PAGE]
        self.select = discord.ui.Select(
            placeholder=f"Goleadores cargados · página {self.page + 1}",
            min_values=1,
            max_values=1,
            options=[
                discord.SelectOption(
                    label=f"{player} · {team}"[:100],
                    description=f"{goals} gol{'es' if goals != 1 else ''}",
                    value=str(start + i),
                )
                for i, (player, team, goals) in enumerate(chunk)
            ],
        )
        self.select.callback = self.choose
        self.add_item(self.select)

    async def choose(self, interaction: discord.Interaction):
        player, club, goals = self.rows[int(self.select.values[0])]
        runtime = _runtime()
        review = _review(runtime, interaction.guild_id, self.staff_message_id)
        match = _match(runtime, interaction.guild_id, int(review["source_message_id"])) if review else None
        limit = _match_limits(match).get(club.casefold(), goals) if match else goals
        other = _current_total(runtime, interaction.guild_id, int(review["source_message_id"]), club, except_player=player)
        maximum = max(1, int(limit) - int(other))
        await interaction.response.edit_message(
            content=f"**{player} — {club}**\nActualmente: **{goals}** gol(es). Elegí nueva cantidad o eliminá este goleador.",
            view=ExistingScorerEditView(self.staff_message_id, club, player, goals, maximum),
        )

    @discord.ui.button(label="ANTERIOR", emoji="⬅️", style=discord.ButtonStyle.secondary, row=1)
    async def previous(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(
            view=ExistingScorerListView(self.staff_message_id, self.rows, max(0, self.page - 1)),
        )

    @discord.ui.button(label="SIGUIENTE", emoji="➡️", style=discord.ButtonStyle.secondary, row=1)
    async def next(self, interaction: discord.Interaction, button: discord.ui.Button):
        max_page = max(0, (len(self.rows) - 1) // self.PAGE)
        await interaction.response.edit_message(
            view=ExistingScorerListView(self.staff_message_id, self.rows, min(max_page, self.page + 1)),
        )


class ExistingScorerEditView(discord.ui.View):
    def __init__(self, staff_message_id: int, club: str, player: str, current: int, maximum: int):
        super().__init__(timeout=900)
        self.staff_message_id = int(staff_message_id)
        self.club = str(club)
        self.player = str(player)
        self.current = int(current)
        self.maximum = max(1, int(maximum))
        self.select = discord.ui.Select(
            placeholder="Cambiar cantidad de goles",
            min_values=1,
            max_values=1,
            options=[
                discord.SelectOption(
                    label=f"{n} gol{'es' if n != 1 else ''}",
                    value=str(n),
                    default=(n == self.current),
                )
                for n in range(1, min(self.maximum, 25) + 1)
            ],
        )
        self.select.callback = self.change
        self.add_item(self.select)

    async def change(self, interaction: discord.Interaction):
        goals = int(self.select.values[0])
        await interaction.response.defer(ephemeral=True)
        ok, error = await _save(_runtime(), interaction, self.staff_message_id, self.club, self.player, goals)
        if not ok:
            await interaction.edit_original_response(content=f"⚠️ {error}", view=MatchEditorView(self.staff_message_id))
            return
        review = _review(_runtime(), interaction.guild_id, self.staff_message_id)
        await interaction.edit_original_response(
            content="✅ Cantidad corregida.\n\n" + _manager_text(_runtime(), interaction.guild_id, review),
            view=MatchEditorView(self.staff_message_id),
        )

    @discord.ui.button(label="OTRA CANTIDAD", emoji="⌨️", style=discord.ButtonStyle.secondary, row=1)
    async def manual(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(
            ManualAmountModal(self.staff_message_id, self.club, self.player, self.maximum)
        )

    @discord.ui.button(label="ELIMINAR", emoji="🗑️", style=discord.ButtonStyle.danger, row=1)
    async def delete(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        await _delete(_runtime(), interaction, self.staff_message_id, self.club, self.player)
        review = _review(_runtime(), interaction.guild_id, self.staff_message_id)
        await interaction.edit_original_response(
            content=f"🗑️ **{self.player}** eliminado.\n\n" + _manager_text(_runtime(), interaction.guild_id, review),
            view=MatchEditorView(self.staff_message_id),
        )


async def _upgrade_cards_v2():
    await asyncio.sleep(3)
    runtime = _runtime()
    bot = BOT
    if runtime is None or bot is None:
        return
    changed = 0
    for guild in list(bot.guilds):
        conn = league.db(runtime, guild.id)
        try:
            try:
                rows = conn.execute(
                    """
                    SELECT * FROM league_manual_reviews
                    WHERE status='RESUELTO' AND staff_channel_id IS NOT NULL AND staff_message_id IS NOT NULL
                    ORDER BY created_at DESC
                    LIMIT 150
                    """
                ).fetchall()
            except Exception:
                rows = []
        finally:
            conn.close()
        for row in rows:
            try:
                channel = guild.get_channel(int(row["staff_channel_id"])) or await guild.fetch_channel(int(row["staff_channel_id"]))
                message = await channel.fetch_message(int(row["staff_message_id"]))
                await message.edit(view=ManagePersistentView())
                changed += 1
            except (discord.NotFound, discord.Forbidden):
                continue
            except Exception as exc:
                print(f"AJAP scorer editor v2 upgrade warning: {type(exc).__name__}: {exc}")
    print(f"AJAP Liga: editor visual de goleadores actualizado en {changed} tarjeta(s)")


async def _repair_ajax_tottenham_2_2():
    """Repair only the reported bad 2-2 whose current scorer state is Huntelaar x2."""
    await asyncio.sleep(7)
    runtime = _runtime()
    bot = BOT
    if runtime is None or bot is None:
        return
    for guild in list(bot.guilds):
        conn = league.db(runtime, guild.id)
        repaired: list[int] = []
        try:
            rows = conn.execute(
                """
                SELECT * FROM league_matches
                WHERE home_goals=2 AND away_goals=2
                  AND ((home_team='Ajax' AND away_team='Tottenham Hotspur')
                    OR (home_team='Tottenham Hotspur' AND away_team='Ajax'))
                ORDER BY id DESC LIMIT 10
                """
            ).fetchall()
            for match in rows:
                source = int(match["source_message_id"])
                scorers = conn.execute(
                    """
                    SELECT player,team,SUM(goals) AS goals
                    FROM league_goal_events WHERE source_message_id=?
                    GROUP BY player COLLATE NOCASE, team COLLATE NOCASE
                    """,
                    (source,),
                ).fetchall()
                state = {(league.norm(r["player"]), str(r["team"] or "").casefold()): int(r["goals"] or 0) for r in scorers}
                # Exact bad state shown by Staff: Ajax Huntelaar x2, Spurs empty.
                if state.get((league.norm("Huntelaar"), "ajax")) != 2:
                    continue
                if any(team == "tottenham hotspur" and goals > 0 for (_, team), goals in state.items()):
                    continue
                conn.execute("DELETE FROM league_goal_events WHERE source_message_id=?", (source,))
                for player, club in (
                    ("Huntelaar", "Ajax"),
                    ("Mitea", "Ajax"),
                    ("Robbie Keane", "Tottenham Hotspur"),
                    ("Defoe", "Tottenham Hotspur"),
                ):
                    conn.execute(
                        """
                        INSERT INTO league_goal_events(source_message_id,player,team,goals,confidence)
                        VALUES(?,?,?,?,1.0)
                        """,
                        (source, player, club, 1),
                    )
                repaired.append(source)
            conn.commit()
        finally:
            conn.close()
        if repaired:
            try:
                await controls._refresh_everything(runtime, bot, guild.id)
            except Exception:
                pass
            for source in repaired:
                try:
                    await unified._sync_public(guild, source)
                except Exception:
                    pass
            print(f"AJAP Liga: Ajax 2-2 Tottenham goleadores reparados source={repaired}")


_ORIGINAL_APPLY = guild_isolation.apply_guild_isolation_patch


def _apply(runtime, bot):
    global APP, BOT
    _ORIGINAL_APPLY(runtime, bot)
    APP, BOT = runtime, bot
    if getattr(bot, "_ajap_scorer_editor_v2", False):
        return

    # Make every future admin-control refresh use this one persistent entry point.
    unified.UnifiedPersistentView = ManagePersistentView
    controls.ResultAdminView = ManagePersistentView
    try:
        bot.add_view(ManagePersistentView())
    except Exception as exc:
        print(f"AJAP scorer editor v2 persistent registration warning: {exc}")

    bot.add_listener(_upgrade_cards_v2, "on_ready")
    bot.add_listener(_repair_ajax_tottenham_2_2, "on_ready")
    bot._ajap_scorer_editor_v2 = True
    print("AJAP Liga: editor v2 de goleadores activo (lista + editar + buscar plantilla)")


if not getattr(guild_isolation.apply_guild_isolation_patch, "_ajap_scorer_editor_v2_wrapper", False):
    _apply._ajap_scorer_editor_v2_wrapper = True
    guild_isolation.apply_guild_isolation_patch = _apply
