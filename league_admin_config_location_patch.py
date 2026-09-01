"""Configuración de Liga dentro de Administración -> Gestión.

Además del canal de resultados, Staff puede elegir si la temporada es de solo
ida o ida y vuelta. El formato controla cuántos resultados oficiales pueden
existir entre la misma pareja de clubes y mantiene Buscar Partido alineado con
esa regla.

Para evidencia de una serie ida/vuelta, cada encuentro se envía por separado:
se admiten hasta 2 capturas por encuentro (por ejemplo, un tiempo por captura),
por lo que una pareja puede aportar hasta 4 capturas entre ida y vuelta sin
mezclar marcadores de dos encuentros distintos en una sola lectura de visión.
"""

from __future__ import annotations

import sqlite3
import sys

import discord

import league_channel_panel_patch as league_ui
import league_result_evidence_patch as evidence
import staff_admin_organized_patch as staff


SINGLE = "single"
DOUBLE = "double"


# ---------------------------------------------------------------------------
# Persistencia del formato de temporada.
# ---------------------------------------------------------------------------
def _ensure_season_schema_conn(conn: sqlite3.Connection) -> None:
    league_ui.league.schema(conn)
    cols = {
        str(row["name"] if isinstance(row, sqlite3.Row) else row[1])
        for row in conn.execute("PRAGMA table_info(league_config)").fetchall()
    }
    if "season_format" not in cols:
        conn.execute(
            "ALTER TABLE league_config ADD COLUMN season_format TEXT NOT NULL DEFAULT 'single'"
        )
        conn.commit()


def _season_format(guild_id: int) -> str:
    conn = league_ui.league.db(league_ui._runtime(), int(guild_id))
    try:
        _ensure_season_schema_conn(conn)
        row = conn.execute(
            "SELECT season_format FROM league_config WHERE guild_id=? LIMIT 1",
            (int(guild_id),),
        ).fetchone()
        value = str(row["season_format"] if row else SINGLE).casefold()
        return DOUBLE if value == DOUBLE else SINGLE
    finally:
        conn.close()


def _save_season_format(guild_id: int, value: str) -> None:
    mode = DOUBLE if str(value).casefold() == DOUBLE else SINGLE
    conn = league_ui.league.db(league_ui._runtime(), int(guild_id))
    try:
        _ensure_season_schema_conn(conn)
        conn.execute(
            """
            INSERT INTO league_config (guild_id, season_format, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(guild_id) DO UPDATE SET
                season_format=excluded.season_format,
                updated_at=CURRENT_TIMESTAMP
            """,
            (int(guild_id), mode),
        )
        conn.commit()
    finally:
        conn.close()


def _allowed_legs_from_conn(conn: sqlite3.Connection) -> int:
    try:
        _ensure_season_schema_conn(conn)
        row = conn.execute(
            "SELECT season_format FROM league_config ORDER BY updated_at DESC LIMIT 1"
        ).fetchone()
        value = str(row["season_format"] if row else SINGLE).casefold()
        return 2 if value == DOUBLE else 1
    except Exception:
        return 1


# ---------------------------------------------------------------------------
# UI de Liga para jugadores y Staff.
# ---------------------------------------------------------------------------
class PlayerLeagueView(discord.ui.View):
    """Vista pública de Liga: consulta solamente, incluso si quien entra es admin."""

    def __init__(self, admin_mode=False):
        super().__init__(timeout=300)
        self.add_item(league_ui.RefreshLeagueButton(row=0))
        self.add_item(league_ui.manager.BackMainButton(row=1))


class BackManagementButton(discord.ui.Button):
    def __init__(self, row=2):
        super().__init__(
            label="VOLVER A GESTIÓN",
            emoji="⬅️",
            style=discord.ButtonStyle.secondary,
            row=row,
            custom_id="ajap_admin_league_back_management",
        )

    async def callback(self, interaction: discord.Interaction):
        if not staff.APP.es_admin(interaction):
            await interaction.response.send_message("⛔ Solo administradores.", ephemeral=True)
            return
        embed = staff.section_embed(
            "⚙️ GESTIÓN",
            "Configuración general del torneo y del mercado.",
            [
                "👥 Asignaciones",
                "🗓️ Cambiar temporada",
                "📤 Exportar mercado",
                "🏆 Configurar resultados de Liga",
            ],
        )
        await interaction.response.edit_message(
            content=None,
            embeds=[embed],
            view=staff.ManagementView(),
        )


class AdminResultsChannelSelect(discord.ui.ChannelSelect):
    def __init__(self):
        super().__init__(
            placeholder="📸 Elegí el canal de resultados",
            channel_types=[discord.ChannelType.text],
            min_values=1,
            max_values=1,
            row=0,
            custom_id="ajap_admin_league_results_channel",
        )

    async def callback(self, interaction: discord.Interaction):
        token = league_ui._guild_token(interaction)
        try:
            if not staff.APP.es_admin(interaction):
                await interaction.response.send_message("⛔ Solo administradores.", ephemeral=True)
                return
            if not interaction.guild_id:
                await interaction.response.send_message(
                    "⚠️ La Liga solo funciona dentro del servidor.", ephemeral=True
                )
                return
            channel = self.values[0]
            league_ui._save_intake(interaction.guild_id, channel.id)
            await interaction.response.edit_message(
                content=None,
                embeds=[league_ui.league_config_embed(interaction.guild_id)],
                view=AdminLeagueConfigView(),
            )
        finally:
            league_ui._guild_reset(token)


class AdminSeasonFormatSelect(discord.ui.Select):
    def __init__(self):
        super().__init__(
            placeholder="🔁 Elegí: solo ida o ida y vuelta",
            min_values=1,
            max_values=1,
            row=1,
            custom_id="ajap_admin_league_season_format",
            options=[
                discord.SelectOption(
                    label="Solo ida",
                    value=SINGLE,
                    emoji="1️⃣",
                    description="Cada pareja de equipos juega una sola vez.",
                ),
                discord.SelectOption(
                    label="Ida y vuelta",
                    value=DOUBLE,
                    emoji="🔁",
                    description="Cada pareja puede registrar dos partidos oficiales.",
                ),
            ],
        )

    async def callback(self, interaction: discord.Interaction):
        token = league_ui._guild_token(interaction)
        try:
            if not staff.APP.es_admin(interaction):
                await interaction.response.send_message("⛔ Solo administradores.", ephemeral=True)
                return
            if not interaction.guild_id:
                await interaction.response.send_message(
                    "⚠️ La Liga solo funciona dentro del servidor.", ephemeral=True
                )
                return
            _save_season_format(interaction.guild_id, self.values[0])
            await interaction.response.edit_message(
                content=None,
                embeds=[league_ui.league_config_embed(interaction.guild_id)],
                view=AdminLeagueConfigView(),
            )
        finally:
            league_ui._guild_reset(token)


class AdminLeagueConfigView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=300)
        self.add_item(AdminResultsChannelSelect())
        self.add_item(AdminSeasonFormatSelect())
        self.add_item(BackManagementButton(row=2))


class AdminConfigureResultsButton(discord.ui.Button):
    def __init__(self, row=1):
        super().__init__(
            label="CONFIGURAR RESULTADOS",
            emoji="🏆",
            style=discord.ButtonStyle.primary,
            row=row,
            custom_id="ajap_admin_league_config_results",
        )

    async def callback(self, interaction: discord.Interaction):
        token = league_ui._guild_token(interaction)
        try:
            if not staff.APP.es_admin(interaction):
                await interaction.response.send_message("⛔ Solo administradores.", ephemeral=True)
                return
            await interaction.response.edit_message(
                content=None,
                embeds=[league_ui.league_config_embed(interaction.guild_id)],
                view=AdminLeagueConfigView(),
            )
        finally:
            league_ui._guild_reset(token)


# Mostrar el formato actual dentro de la misma pantalla de configuración.
_original_league_config_embed = league_ui.league_config_embed


def _league_config_embed_with_format(guild_id: int):
    # Crear/migrar la columna antes del SELECT del embed original.
    mode = _season_format(guild_id)
    embed = _original_league_config_embed(guild_id)
    embed.title = "⚙️ RESULTADOS DE LIGA"
    if mode == DOUBLE:
        format_text = (
            "🔁 **Ida y vuelta**\n"
            "Cada pareja puede registrar **2 resultados oficiales** y ambos cuentan "
            "por separado para la tabla."
        )
    else:
        format_text = (
            "1️⃣ **Solo ida**\n"
            "Cada pareja puede registrar **1 resultado oficial**."
        )
    embed.add_field(name="Formato de temporada", value=format_text, inline=False)
    embed.add_field(
        name="📷 Capturas por cruce",
        value=(
            "Subí cada encuentro en **un mensaje separado**. El bot toma hasta "
            "**2 capturas por encuentro** (por ejemplo, una por cada tiempo). "
            "En ida y vuelta son hasta **4 capturas en total** entre los dos partidos."
        ),
        inline=False,
    )
    return embed


league_ui.league_config_embed = _league_config_embed_with_format

# Evita que visión mezcle en un solo análisis las capturas de ida y de vuelta.
league_ui.league.MAX_IMAGES = 2


# ---------------------------------------------------------------------------
# Política de duplicados del lector de resultados.
# ---------------------------------------------------------------------------
def _existing_official_pair_configurable(
    runtime, guild_id: int, home: str, away: str, exclude_source=None
):
    conn = league_ui.league.db(runtime, int(guild_id))
    try:
        _ensure_season_schema_conn(conn)
        limit = _allowed_legs_from_conn(conn)
        rows = conn.execute(
            """
            SELECT * FROM league_matches
            WHERE (home_team=? AND away_team=?) OR (home_team=? AND away_team=?)
            ORDER BY id DESC
            """,
            (home, away, away, home),
        ).fetchall()
        valid = [
            row
            for row in rows
            if exclude_source is None
            or int(row["source_message_id"]) != int(exclude_source)
        ]
        # _persist_official interpreta un row como "ya alcanzaste el límite".
        return valid[0] if len(valid) >= limit else None
    finally:
        conn.close()


evidence._existing_official_pair = _existing_official_pair_configurable


# ---------------------------------------------------------------------------
# Buscar Partido móvil: respetar ida/vuelta y no reutilizar el resultado de ida
# para cerrar instantáneamente la búsqueda de la vuelta.
# ---------------------------------------------------------------------------
mobile_match_search = sys.modules.get("mobile_match_search_patch")
if mobile_match_search is not None:

    def _mobile_pair_result_count(conn: sqlite3.Connection, club_a: str, club_b: str) -> int:
        if not mobile_match_search.mobile_write_api._table_exists(conn, "league_matches"):
            return 0
        a = mobile_match_search._norm_team(club_a)
        b = mobile_match_search._norm_team(club_b)
        count = 0
        for row in conn.execute(
            "SELECT home_team, away_team FROM league_matches"
        ).fetchall():
            home = mobile_match_search._norm_team(row["home_team"])
            away = mobile_match_search._norm_team(row["away_team"])
            if {home, away} == {a, b}:
                count += 1
        return count

    def _mobile_already_played(conn: sqlite3.Connection, club_a: str, club_b: str) -> bool:
        return _mobile_pair_result_count(conn, club_a, club_b) >= _allowed_legs_from_conn(conn)

    def _mobile_official_result_after(
        conn: sqlite3.Connection,
        club_a: str,
        club_b: str,
        matched_at,
    ):
        if not mobile_match_search.mobile_write_api._table_exists(conn, "league_matches"):
            return None
        a = mobile_match_search._norm_team(club_a)
        b = mobile_match_search._norm_team(club_b)
        try:
            if matched_at:
                rows = conn.execute(
                    """
                    SELECT id, source_message_id, home_team, away_team,
                           home_goals, away_goals, created_at
                    FROM league_matches
                    WHERE datetime(created_at) >= datetime(?)
                    ORDER BY id DESC
                    """,
                    (str(matched_at),),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT id, source_message_id, home_team, away_team,
                           home_goals, away_goals, created_at
                    FROM league_matches
                    ORDER BY id DESC
                    """
                ).fetchall()
        except sqlite3.OperationalError:
            return None
        for row in rows:
            home = mobile_match_search._norm_team(row["home_team"])
            away = mobile_match_search._norm_team(row["away_team"])
            if {home, away} == {a, b}:
                return row
        return None

    def _mobile_reconcile_completed(conn: sqlite3.Connection) -> None:
        rows = conn.execute(
            """
            SELECT id, status, creator_club, opponent_club, matched_at
            FROM mobile_match_searches
            WHERE opponent_club IS NOT NULL
              AND (
                    status='MATCHED'
                    OR (status='COMPLETED' AND result_home_goals IS NULL)
                  )
            """
        ).fetchall()
        for row in rows:
            result = _mobile_official_result_after(
                conn,
                str(row["creator_club"]),
                str(row["opponent_club"]),
                row["matched_at"],
            )
            if not result:
                continue
            conn.execute(
                """
                UPDATE mobile_match_searches
                SET status='COMPLETED',
                    completed_at=COALESCE(completed_at, CURRENT_TIMESTAMP),
                    result_home_team=?,
                    result_away_team=?,
                    result_home_goals=?,
                    result_away_goals=?,
                    result_source_message_id=?
                WHERE id=?
                  AND status IN ('MATCHED', 'COMPLETED')
                """,
                (
                    str(result["home_team"]),
                    str(result["away_team"]),
                    int(result["home_goals"]),
                    int(result["away_goals"]),
                    int(result["source_message_id"]),
                    int(row["id"]),
                ),
            )

    mobile_match_search._already_played = _mobile_already_played
    mobile_match_search._reconcile_completed = _mobile_reconcile_completed


# 1) Nunca mostrar configuración dentro del menú LIGA de jugadores.
league_ui.LeagueHubView = PlayerLeagueView

# 2) Agregar la herramienta al bloque Administración -> Gestión.
_ORIGINAL_MANAGEMENT_VIEW = staff.ManagementView


class ManagementViewWithLeague(_ORIGINAL_MANAGEMENT_VIEW):
    def __init__(self):
        super().__init__()
        self.add_item(AdminConfigureResultsButton(row=1))


staff.ManagementView = ManagementViewWithLeague

# 3) Reflejar la herramienta también en la descripción de Gestión.
_original_section_embed = staff.section_embed


def _section_embed_with_league(title, description, tools):
    items = list(tools)
    if "GESTIÓN" in str(title).upper() and not any(
        "resultado" in str(x).casefold() for x in items
    ):
        items.append("🏆 Configurar resultados de Liga")
    return _original_section_embed(title, description, items)


staff.section_embed = _section_embed_with_league

print(
    "AJAP Liga: resultados en Administración -> Gestión • formato solo ida / ida y vuelta • hasta 2 capturas por encuentro"
)
