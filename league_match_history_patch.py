"""Historial visual de partidos dentro de Liga AJAP.

Agrega un botón HISTORIAL al hub de Liga. Cada DT ve los partidos oficiales del
club que dirige actualmente, con una tarjeta por partido:
- verde para victoria;
- roja para derrota;
- gris para empate.

Los datos salen exclusivamente de league_matches, la misma fuente que alimenta
la tabla de posiciones, por lo que no se mantiene un historial paralelo.
"""

from __future__ import annotations

import math

import discord

import guild_isolation_patch as guild_isolation
import league_automation_patch as league
import league_channel_panel_patch as panel


APP = None
BOT = None
BASE_LEAGUE_HUB_VIEW = None
PAGE_SIZE = 5


def _runtime():
    return APP or panel.APP


def _club_for(user_id: int):
    runtime = _runtime()
    if runtime is None:
        return None
    try:
        raw = runtime.club_de(int(user_id))
    except Exception:
        raw = None
    return league.canonical_team(raw) if raw else None


def _matches(guild_id: int, club: str):
    conn = league.db(_runtime(), int(guild_id))
    try:
        return conn.execute(
            """
            SELECT id, source_message_id, source_channel_id,
                   home_team, away_team, home_goals, away_goals, created_at
            FROM league_matches
            WHERE home_team = ? COLLATE NOCASE
               OR away_team = ? COLLATE NOCASE
            ORDER BY datetime(created_at) DESC, id DESC
            """,
            (club, club),
        ).fetchall()
    finally:
        conn.close()


def _perspective(row, club: str):
    is_home = str(row["home_team"]).casefold() == str(club).casefold()
    if is_home:
        rival = str(row["away_team"])
        gf = int(row["home_goals"])
        gc = int(row["away_goals"])
    else:
        rival = str(row["home_team"])
        gf = int(row["away_goals"])
        gc = int(row["home_goals"])

    if gf > gc:
        return "VICTORIA", discord.Color.green(), "🟢", rival, gf, gc
    if gf < gc:
        return "DERROTA", discord.Color.red(), "🔴", rival, gf, gc
    return "EMPATE", discord.Color.from_rgb(110, 110, 110), "⚪", rival, gf, gc


def _date_text(value):
    raw = str(value or "").strip()
    if not raw:
        return "Sin fecha"
    # SQLite guarda normalmente YYYY-MM-DD HH:MM:SS. Para la tarjeta alcanza con
    # mostrar fecha y hora sin forzar una zona horaria distinta a la del servidor.
    if len(raw) >= 16 and raw[4:5] == "-" and raw[7:8] == "-":
        try:
            yyyy, mm, dd = raw[:10].split("-")
            hhmm = raw[11:16]
            return f"{dd}/{mm}/{yyyy} • {hhmm}"
        except Exception:
            pass
    return raw[:32]


def _summary_embed(club: str, rows, page: int, total_pages: int):
    wins = draws = losses = gf = gc = 0
    rivals = set()
    for row in rows:
        result, _color, _dot, rival, scored, conceded = _perspective(row, club)
        rivals.add(rival.casefold())
        gf += scored
        gc += conceded
        if result == "VICTORIA":
            wins += 1
        elif result == "DERROTA":
            losses += 1
        else:
            draws += 1

    embed = discord.Embed(
        title="📜 HISTORIAL DE PARTIDOS",
        description=f"Historial oficial de **{club}** en Liga AJAP.",
        color=discord.Color.blurple(),
    )
    embed.add_field(name="PJ", value=str(len(rows)), inline=True)
    embed.add_field(name="PG", value=str(wins), inline=True)
    embed.add_field(name="PE", value=str(draws), inline=True)
    embed.add_field(name="PP", value=str(losses), inline=True)
    embed.add_field(name="GF", value=str(gf), inline=True)
    embed.add_field(name="GC", value=str(gc), inline=True)
    embed.add_field(
        name="Rivales enfrentados",
        value=str(len(rivals)),
        inline=True,
    )
    embed.add_field(
        name="Leyenda",
        value="🟢 Victoria • 🔴 Derrota • ⚪ Empate",
        inline=False,
    )
    embed.set_footer(text=f"Página {page + 1}/{total_pages} • resultados oficiales de Liga")
    return embed


def _match_embed(guild_id: int, row, club: str):
    result, color, dot, rival, gf, gc = _perspective(row, club)
    home = str(row["home_team"])
    away = str(row["away_team"])
    hg = int(row["home_goals"])
    ag = int(row["away_goals"])

    embed = discord.Embed(
        title=f"{dot} {result} • vs {rival}",
        description=f"## **{home} {hg} — {ag} {away}**",
        color=color,
    )
    embed.add_field(
        name="Desde tu equipo",
        value=f"**{club} {gf} — {gc} {rival}**",
        inline=False,
    )
    embed.add_field(name="Fecha", value=_date_text(row["created_at"]), inline=True)
    embed.add_field(
        name="Resultado",
        value=("✅ Victoria" if result == "VICTORIA" else "❌ Derrota" if result == "DERROTA" else "➖ Empate"),
        inline=True,
    )
    if row["source_message_id"] and row["source_channel_id"]:
        embed.add_field(
            name="Origen",
            value=(
                f"[Ver resultado](https://discord.com/channels/{int(guild_id)}/"
                f"{int(row['source_channel_id'])}/{int(row['source_message_id'])})"
            ),
            inline=False,
        )
    return embed


def history_embeds(guild_id: int, club: str, page: int = 0):
    rows = _matches(guild_id, club)
    if not rows:
        empty = discord.Embed(
            title="📜 HISTORIAL DE PARTIDOS",
            description=f"**{club}** todavía no tiene partidos oficiales cargados.",
            color=discord.Color.blurple(),
        )
        empty.set_footer(text="Cuando se cargue un resultado oficial aparecerá acá")
        return [empty], 0, 1, 0

    total_pages = max(1, math.ceil(len(rows) / PAGE_SIZE))
    page = max(0, min(int(page), total_pages - 1))
    start = page * PAGE_SIZE
    chunk = rows[start : start + PAGE_SIZE]
    embeds = [_summary_embed(club, rows, page, total_pages)]
    embeds.extend(_match_embed(guild_id, row, club) for row in chunk)
    return embeds, page, total_pages, len(rows)


class HistoryPrevButton(discord.ui.Button):
    def __init__(self, owner_id: int, club: str, page: int, total_pages: int):
        super().__init__(
            label="ANTERIOR",
            emoji="⬅️",
            style=discord.ButtonStyle.secondary,
            row=0,
            disabled=page <= 0,
        )
        self.owner_id = int(owner_id)
        self.club = str(club)
        self.page = int(page)
        self.total_pages = int(total_pages)

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("⛔ Este historial pertenece a otro usuario.", ephemeral=True)
            return
        await _render_history(interaction, self.owner_id, self.club, self.page - 1)


class HistoryNextButton(discord.ui.Button):
    def __init__(self, owner_id: int, club: str, page: int, total_pages: int):
        super().__init__(
            label="SIGUIENTE",
            emoji="➡️",
            style=discord.ButtonStyle.secondary,
            row=0,
            disabled=page >= total_pages - 1,
        )
        self.owner_id = int(owner_id)
        self.club = str(club)
        self.page = int(page)
        self.total_pages = int(total_pages)

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("⛔ Este historial pertenece a otro usuario.", ephemeral=True)
            return
        await _render_history(interaction, self.owner_id, self.club, self.page + 1)


class HistoryBackLeagueButton(discord.ui.Button):
    def __init__(self, owner_id: int):
        super().__init__(
            label="VOLVER A LIGA",
            emoji="↩️",
            style=discord.ButtonStyle.secondary,
            row=1,
        )
        self.owner_id = int(owner_id)

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("⛔ Este menú pertenece a otro usuario.", ephemeral=True)
            return
        token = panel._guild_token(interaction)
        try:
            await interaction.response.edit_message(
                content=None,
                embeds=panel.league_hub_embeds(interaction.guild_id),
                view=panel.LeagueHubView(admin_mode=panel._is_admin(interaction)),
            )
        finally:
            panel._guild_reset(token)


class MatchHistoryView(discord.ui.View):
    def __init__(self, owner_id: int, club: str, page: int, total_pages: int):
        super().__init__(timeout=300)
        self.add_item(HistoryPrevButton(owner_id, club, page, total_pages))
        self.add_item(HistoryNextButton(owner_id, club, page, total_pages))
        self.add_item(HistoryBackLeagueButton(owner_id))


async def _render_history(interaction: discord.Interaction, owner_id: int, club: str, page: int):
    token = panel._guild_token(interaction)
    try:
        current = _club_for(owner_id)
        if current != club:
            await interaction.response.send_message(
                "⚠️ Tu asignación de club cambió. Volvé a abrir Liga para ver el historial correcto.",
                ephemeral=True,
            )
            return
        embeds, page, total_pages, _count = history_embeds(interaction.guild_id, club, page)
        await interaction.response.edit_message(
            content=None,
            embeds=embeds,
            view=MatchHistoryView(owner_id, club, page, total_pages),
        )
    finally:
        panel._guild_reset(token)


class MatchHistoryButton(discord.ui.Button):
    def __init__(self, row=0):
        super().__init__(
            label="HISTORIAL",
            emoji="📜",
            style=discord.ButtonStyle.primary,
            row=row,
            custom_id="ajap_league_match_history",
        )

    async def callback(self, interaction: discord.Interaction):
        if not interaction.guild_id:
            await interaction.response.send_message("⚠️ La Liga solo funciona dentro del servidor.", ephemeral=True)
            return
        club = _club_for(interaction.user.id)
        if not club:
            await interaction.response.send_message(
                "⚠️ Necesitás tener un equipo asignado para ver tu historial de Liga.",
                ephemeral=True,
            )
            return
        await _render_history(interaction, interaction.user.id, club, 0)


def apply_league_match_history_patch(runtime, bot):
    global APP, BOT, BASE_LEAGUE_HUB_VIEW
    APP = runtime
    BOT = bot
    if getattr(runtime, "_ajap_league_match_history_patch", False):
        return

    BASE_LEAGUE_HUB_VIEW = panel.LeagueHubView

    class LeagueHubWithHistory(BASE_LEAGUE_HUB_VIEW):
        def __init__(self, admin_mode=False):
            super().__init__(admin_mode=admin_mode)
            self.add_item(MatchHistoryButton(row=0))

    LeagueHubWithHistory.__name__ = "LeagueHubView"
    panel.LeagueHubView = LeagueHubWithHistory
    runtime.LeagueHubView = LeagueHubWithHistory
    runtime.league_match_history_embeds = history_embeds
    runtime._ajap_league_match_history_patch = True
    print("AJAP Liga: historial visual activo (verde victoria / rojo derrota / gris empate)")


_original_apply_guild_isolation_patch = guild_isolation.apply_guild_isolation_patch


def _apply_guild_isolation_then_match_history(runtime, bot):
    _original_apply_guild_isolation_patch(runtime, bot)
    apply_league_match_history_patch(runtime, bot)


if not getattr(
    guild_isolation.apply_guild_isolation_patch,
    "_ajap_league_match_history_wrapped",
    False,
):
    _apply_guild_isolation_then_match_history._ajap_league_match_history_wrapped = True
    guild_isolation.apply_guild_isolation_patch = _apply_guild_isolation_then_match_history
