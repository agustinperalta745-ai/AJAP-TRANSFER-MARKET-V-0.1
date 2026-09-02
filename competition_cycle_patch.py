"""Official AJPA competition lifecycle.

The live league state advances through one authoritative cycle:
Pretemporada -> Temporada -> Mercado 1 -> Copa -> Mercado 2 -> next Temporada.

Competition statistics are isolated by competition_id. Historical match rows are
never deleted, so classic-rival head-to-head and result history remain all-time.
Rosters, balances and transfers are deliberately outside every reset/transition.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass

import discord


PHASE_PRESEASON = "preseason"
PHASE_SEASON = "season"
PHASE_MARKET_1 = "market_1"
PHASE_CUP = "cup"
PHASE_MARKET_2 = "market_2"
PLAYABLE_PHASES = {PHASE_PRESEASON, PHASE_SEASON, PHASE_CUP}
VALID_PHASES = {
    PHASE_PRESEASON,
    PHASE_SEASON,
    PHASE_MARKET_1,
    PHASE_CUP,
    PHASE_MARKET_2,
}


class CycleError(RuntimeError):
    pass


@dataclass(frozen=True)
class Transition:
    from_phase: str
    to_phase: str
    season_number: int
    competition_id: int | None


def _table_exists(conn: sqlite3.Connection, table: str) -> bool:
    return bool(
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
            (table,),
        ).fetchone()
    )


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    if not _table_exists(conn, table):
        return set()
    return {str(row["name"]) for row in conn.execute(f'PRAGMA table_info("{table}")')}


def _add_column(conn: sqlite3.Connection, table: str, column: str, definition: str) -> None:
    if _table_exists(conn, table) and column not in _columns(conn, table):
        conn.execute(f'ALTER TABLE "{table}" ADD COLUMN "{column}" {definition}')


def _active_season_id(conn: sqlite3.Connection) -> int | None:
    if not _table_exists(conn, "seasons"):
        return None
    row = conn.execute(
        "SELECT id FROM seasons WHERE active=1 ORDER BY id DESC LIMIT 1"
    ).fetchone()
    return int(row["id"]) if row else None


def _sync_legacy_season(conn: sqlite3.Connection, season_number: int) -> int | None:
    if not _table_exists(conn, "seasons"):
        return None
    name = f"Temporada {int(season_number)}"
    conn.execute("UPDATE seasons SET active=0")
    conn.execute("INSERT OR IGNORE INTO seasons(name, active) VALUES(?, 0)", (name,))
    conn.execute("UPDATE seasons SET active=1 WHERE name=?", (name,))
    row = conn.execute("SELECT id FROM seasons WHERE name=?", (name,)).fetchone()
    return int(row["id"]) if row else None


def _ensure_market_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS market_state (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            is_open INTEGER NOT NULL DEFAULT 0,
            updated_by INTEGER,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS market_state_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            is_open INTEGER NOT NULL,
            changed_by INTEGER,
            changed_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS market_cycles (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            season_id INTEGER,
            opened_by INTEGER,
            opened_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            closed_by INTEGER,
            closed_at DATETIME,
            report_sent_at DATETIME,
            report_recipient_count INTEGER NOT NULL DEFAULT 0
        );
        INSERT OR IGNORE INTO market_state(id, is_open) VALUES(1, 0);
        """
    )


def _set_market(conn: sqlite3.Connection, opened: bool, user_id: int) -> int | None:
    _ensure_market_schema(conn)
    value = 1 if opened else 0
    previous = conn.execute("SELECT is_open FROM market_state WHERE id=1").fetchone()
    old = int(previous["is_open"]) if previous else None
    conn.execute(
        """
        INSERT INTO market_state(id, is_open, updated_by, updated_at)
        VALUES(1, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(id) DO UPDATE SET
            is_open=excluded.is_open,
            updated_by=excluded.updated_by,
            updated_at=CURRENT_TIMESTAMP
        """,
        (value, int(user_id)),
    )
    if old != value:
        conn.execute(
            "INSERT INTO market_state_history(is_open, changed_by) VALUES(?, ?)",
            (value, int(user_id)),
        )

    current = conn.execute(
        "SELECT * FROM market_cycles WHERE closed_at IS NULL ORDER BY id DESC LIMIT 1"
    ).fetchone()
    if opened:
        if current:
            return int(current["id"])
        cur = conn.execute(
            "INSERT INTO market_cycles(season_id, opened_by) VALUES(?, ?)",
            (_active_season_id(conn), int(user_id)),
        )
        return int(cur.lastrowid)

    if current:
        conn.execute(
            """
            UPDATE market_cycles
            SET closed_by=?, closed_at=CURRENT_TIMESTAMP
            WHERE id=? AND closed_at IS NULL
            """,
            (int(user_id), int(current["id"])),
        )
        return int(current["id"])
    return None


def ensure_schema(conn: sqlite3.Connection) -> None:
    """Install lifecycle tables and migrate current results as Pretemporada."""
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS competition_editions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            kind TEXT NOT NULL,
            season_number INTEGER NOT NULL,
            label TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'active',
            started_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            ended_at DATETIME,
            final_snapshot_json TEXT
        );
        CREATE TABLE IF NOT EXISTS competition_cycle_state (
            id INTEGER PRIMARY KEY CHECK(id=1),
            phase TEXT NOT NULL,
            season_number INTEGER NOT NULL DEFAULT 1,
            competition_id INTEGER,
            updated_by INTEGER,
            updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS competition_cycle_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            from_phase TEXT NOT NULL,
            to_phase TEXT NOT NULL,
            season_number INTEGER NOT NULL,
            competition_id INTEGER,
            changed_by INTEGER,
            changed_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """
    )
    _ensure_market_schema(conn)

    _add_column(conn, "league_matches", "competition_id", "INTEGER")
    _add_column(conn, "league_goal_events", "competition_id", "INTEGER")

    state = conn.execute("SELECT * FROM competition_cycle_state WHERE id=1").fetchone()
    if state is None:
        cur = conn.execute(
            """
            INSERT INTO competition_editions(kind, season_number, label, status)
            VALUES('preseason', 1, 'Pretemporada', 'active')
            """
        )
        competition_id = int(cur.lastrowid)
        conn.execute(
            """
            INSERT INTO competition_cycle_state
            (id, phase, season_number, competition_id)
            VALUES(1, 'preseason', 1, ?)
            """,
            (competition_id,),
        )
        # Everything that already exists today belongs to the current preseason.
        if _table_exists(conn, "league_matches"):
            conn.execute(
                "UPDATE league_matches SET competition_id=? WHERE competition_id IS NULL",
                (competition_id,),
            )
        if _table_exists(conn, "league_goal_events"):
            conn.execute(
                "UPDATE league_goal_events SET competition_id=? WHERE competition_id IS NULL",
                (competition_id,),
            )
        _set_market(conn, False, 0)
        state = conn.execute("SELECT * FROM competition_cycle_state WHERE id=1").fetchone()
    elif str(state["phase"]) in PLAYABLE_PHASES and state["competition_id"] is not None:
        # Covers rows written during a rolling deploy before the trigger existed.
        cid = int(state["competition_id"])
        if _table_exists(conn, "league_matches"):
            conn.execute(
                "UPDATE league_matches SET competition_id=? WHERE competition_id IS NULL",
                (cid,),
            )
        if _table_exists(conn, "league_goal_events"):
            conn.execute(
                "UPDATE league_goal_events SET competition_id=? WHERE competition_id IS NULL",
                (cid,),
            )

    if _table_exists(conn, "league_matches"):
        conn.executescript(
            """
            CREATE TRIGGER IF NOT EXISTS ajpa_competition_match_tag
            AFTER INSERT ON league_matches
            WHEN NEW.competition_id IS NULL
            BEGIN
                UPDATE league_matches
                SET competition_id=(
                    SELECT competition_id FROM competition_cycle_state
                    WHERE id=1 AND phase IN ('preseason','season','cup')
                )
                WHERE id=NEW.id;
            END;
            """
        )
    if _table_exists(conn, "league_goal_events"):
        conn.executescript(
            """
            CREATE TRIGGER IF NOT EXISTS ajpa_competition_goal_tag
            AFTER INSERT ON league_goal_events
            WHEN NEW.competition_id IS NULL
            BEGIN
                UPDATE league_goal_events
                SET competition_id=(
                    SELECT competition_id FROM competition_cycle_state
                    WHERE id=1 AND phase IN ('preseason','season','cup')
                )
                WHERE id=NEW.id;
            END;
            """
        )


def _edition(conn: sqlite3.Connection, competition_id: int | None):
    if competition_id is None:
        return None
    return conn.execute(
        "SELECT * FROM competition_editions WHERE id=?", (int(competition_id),)
    ).fetchone()


def _phase_label(phase: str, season_number: int) -> str:
    return {
        PHASE_PRESEASON: "Pretemporada",
        PHASE_SEASON: f"Temporada {season_number}",
        PHASE_MARKET_1: f"Mercado 1 • Temporada {season_number}",
        PHASE_CUP: f"Copa • Temporada {season_number}",
        PHASE_MARKET_2: f"Mercado 2 • Temporada {season_number}",
    }.get(phase, phase)


def _next_action(phase: str, season_number: int) -> dict:
    if phase == PHASE_PRESEASON:
        return {
            "key": "start_season",
            "label": f"INICIAR TEMPORADA {season_number}",
            "description": "Finaliza y archiva la pretemporada; la temporada oficial empieza en cero.",
        }
    if phase == PHASE_SEASON:
        return {
            "key": "season_to_market_1",
            "label": "FINALIZAR TEMPORADA + ABRIR MERCADO 1",
            "description": "Archiva tabla/goleadores/resultados de la temporada y abre la primera ventana.",
        }
    if phase == PHASE_MARKET_1:
        return {
            "key": "market_1_to_cup",
            "label": "CERRAR MERCADO 1 + INICIAR COPA",
            "description": "Cierra la primera ventana y crea una Copa nueva con estadísticas propias.",
        }
    if phase == PHASE_CUP:
        return {
            "key": "cup_to_market_2",
            "label": "FINALIZAR COPA + ABRIR MERCADO 2",
            "description": "Archiva la Copa y abre la segunda ventana de mercado.",
        }
    if phase == PHASE_MARKET_2:
        return {
            "key": "market_2_to_season",
            "label": f"CERRAR MERCADO 2 + INICIAR TEMPORADA {season_number + 1}",
            "description": "Cierra el segundo mercado e inicia la siguiente temporada oficial en cero.",
        }
    raise CycleError(f"Etapa AJPA inválida: {phase}")


def state_payload(conn: sqlite3.Connection) -> dict:
    ensure_schema(conn)
    state = conn.execute("SELECT * FROM competition_cycle_state WHERE id=1").fetchone()
    if not state:
        raise CycleError("No existe el estado del ciclo AJPA.")
    phase = str(state["phase"])
    season_number = int(state["season_number"])
    edition = _edition(conn, state["competition_id"])
    market = conn.execute("SELECT is_open FROM market_state WHERE id=1").fetchone()
    current_cycle = conn.execute(
        "SELECT id FROM market_cycles WHERE closed_at IS NULL ORDER BY id DESC LIMIT 1"
    ).fetchone()
    return {
        "phase": phase,
        "phase_label": _phase_label(phase, season_number),
        "season_number": season_number,
        "competition_id": int(state["competition_id"]) if state["competition_id"] is not None else None,
        "competition": {
            "id": int(edition["id"]),
            "kind": str(edition["kind"]),
            "label": str(edition["label"]),
            "status": str(edition["status"]),
        } if edition else None,
        "market_open": bool(market and int(market["is_open"])),
        "market_cycle_id": int(current_cycle["id"]) if current_cycle else None,
        "next_action": _next_action(phase, season_number),
        "timeline": ["Temporada", "Mercado 1", "Copa", "Mercado 2", "Temporada"],
        "persistent_note": "Planteles, saldos, fichajes e historial de clásicos nunca se resetean.",
        "competition_note": "Tabla, goleadores y estadísticas activas pertenecen solo a la competencia actual.",
        "updated_at": str(state["updated_at"] or ""),
    }


def active_competition_id(conn: sqlite3.Connection) -> int | None:
    ensure_schema(conn)
    row = conn.execute(
        "SELECT phase, competition_id FROM competition_cycle_state WHERE id=1"
    ).fetchone()
    if not row or str(row["phase"]) not in PLAYABLE_PHASES or row["competition_id"] is None:
        return None
    return int(row["competition_id"])


def _snapshot(conn: sqlite3.Connection, competition_id: int) -> str:
    table: dict[str, dict] = {}
    if _table_exists(conn, "league_matches"):
        rows = conn.execute(
            """
            SELECT home_team, away_team, home_goals, away_goals
            FROM league_matches WHERE competition_id=? ORDER BY id ASC
            """,
            (int(competition_id),),
        ).fetchall()
        for row in rows:
            for team in (str(row["home_team"]), str(row["away_team"])):
                table.setdefault(team, {"team": team, "pj": 0, "pg": 0, "pe": 0, "pp": 0, "gf": 0, "gc": 0, "pts": 0})
            h, a = table[str(row["home_team"])], table[str(row["away_team"])]
            hg, ag = int(row["home_goals"]), int(row["away_goals"])
            h["pj"] += 1; a["pj"] += 1
            h["gf"] += hg; h["gc"] += ag; a["gf"] += ag; a["gc"] += hg
            if hg > ag:
                h["pg"] += 1; a["pp"] += 1; h["pts"] += 3
            elif ag > hg:
                a["pg"] += 1; h["pp"] += 1; a["pts"] += 3
            else:
                h["pe"] += 1; a["pe"] += 1; h["pts"] += 1; a["pts"] += 1
    standings = list(table.values())
    for row in standings:
        row["dg"] = int(row["gf"]) - int(row["gc"])
    standings.sort(key=lambda r: (-r["pts"], -r["dg"], -r["gf"], -r["pg"], r["team"].casefold()))

    scorers = []
    if _table_exists(conn, "league_goal_events"):
        rows = conn.execute(
            """
            SELECT player, team, SUM(goals) AS goals
            FROM league_goal_events WHERE competition_id=?
            GROUP BY player COLLATE NOCASE, COALESCE(team,'') COLLATE NOCASE
            ORDER BY goals DESC, player COLLATE NOCASE ASC
            """,
            (int(competition_id),),
        ).fetchall()
        scorers = [
            {"player": str(r["player"]), "team": str(r["team"] or ""), "goals": int(r["goals"] or 0)}
            for r in rows
        ]
    return json.dumps({"standings": standings, "scorers": scorers}, ensure_ascii=False, separators=(",", ":"))


def _finish_current(conn: sqlite3.Connection, competition_id: int | None) -> None:
    if competition_id is None:
        return
    snapshot = _snapshot(conn, int(competition_id))
    conn.execute(
        """
        UPDATE competition_editions
        SET status='finished', ended_at=CURRENT_TIMESTAMP, final_snapshot_json=?
        WHERE id=? AND status='active'
        """,
        (snapshot, int(competition_id)),
    )


def _new_edition(conn: sqlite3.Connection, kind: str, season_number: int, label: str) -> int:
    cur = conn.execute(
        """
        INSERT INTO competition_editions(kind, season_number, label, status)
        VALUES(?, ?, ?, 'active')
        """,
        (kind, int(season_number), label),
    )
    return int(cur.lastrowid)


def advance(conn: sqlite3.Connection, user_id: int, expected_phase: str | None = None) -> dict:
    ensure_schema(conn)
    conn.commit()
    conn.execute("PRAGMA busy_timeout=5000")
    try:
        conn.execute("BEGIN IMMEDIATE")
        state = conn.execute("SELECT * FROM competition_cycle_state WHERE id=1").fetchone()
        if not state:
            raise CycleError("No existe el estado actual del ciclo.")
        phase = str(state["phase"])
        if phase not in VALID_PHASES:
            raise CycleError(f"Etapa inválida: {phase}")
        if expected_phase and str(expected_phase) != phase:
            raise CycleError("La etapa cambió desde que abriste el panel. Actualizá y volvé a intentar.")

        season_number = int(state["season_number"])
        current_competition = int(state["competition_id"]) if state["competition_id"] is not None else None
        next_phase = phase
        next_season = season_number
        next_competition: int | None = None

        if phase == PHASE_PRESEASON:
            _finish_current(conn, current_competition)
            _set_market(conn, False, user_id)
            _sync_legacy_season(conn, season_number)
            next_phase = PHASE_SEASON
            next_competition = _new_edition(conn, "season", season_number, f"Temporada {season_number}")
        elif phase == PHASE_SEASON:
            _finish_current(conn, current_competition)
            next_phase = PHASE_MARKET_1
            next_competition = None
            _set_market(conn, True, user_id)
        elif phase == PHASE_MARKET_1:
            _set_market(conn, False, user_id)
            next_phase = PHASE_CUP
            next_competition = _new_edition(conn, "cup", season_number, f"Copa • Temporada {season_number}")
        elif phase == PHASE_CUP:
            _finish_current(conn, current_competition)
            next_phase = PHASE_MARKET_2
            next_competition = None
            _set_market(conn, True, user_id)
        elif phase == PHASE_MARKET_2:
            _set_market(conn, False, user_id)
            next_season = season_number + 1
            _sync_legacy_season(conn, next_season)
            next_phase = PHASE_SEASON
            next_competition = _new_edition(conn, "season", next_season, f"Temporada {next_season}")

        conn.execute(
            """
            UPDATE competition_cycle_state
            SET phase=?, season_number=?, competition_id=?, updated_by=?, updated_at=CURRENT_TIMESTAMP
            WHERE id=1
            """,
            (next_phase, next_season, next_competition, int(user_id)),
        )
        conn.execute(
            """
            INSERT INTO competition_cycle_history
            (from_phase, to_phase, season_number, competition_id, changed_by)
            VALUES(?, ?, ?, ?, ?)
            """,
            (phase, next_phase, next_season, next_competition, int(user_id)),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return state_payload(conn)


def runtime_state(runtime) -> dict:
    with runtime.db() as conn:
        payload = state_payload(conn)
        conn.commit()
        return payload


def runtime_advance(runtime, user_id: int, expected_phase: str | None = None) -> dict:
    conn = runtime.db()
    try:
        return advance(conn, int(user_id), expected_phase)
    finally:
        conn.close()


def cycle_embed(payload: dict) -> discord.Embed:
    action = payload["next_action"]
    embed = discord.Embed(
        title="🗓️ CICLO AJPA",
        description=(
            f"**Etapa actual:** {payload['phase_label']}\n\n"
            "**Temporada → Mercado 1 → Copa → Mercado 2 → Temporada**"
        ),
        color=discord.Color.blurple(),
    )
    embed.add_field(
        name="Siguiente acción",
        value=f"**{action['label']}**\n{action['description']}",
        inline=False,
    )
    embed.add_field(
        name="🔒 Datos permanentes",
        value="Planteles • saldos • fichajes • historial de transferencias • historial de clásicos",
        inline=False,
    )
    embed.add_field(
        name="🔄 Datos por competencia",
        value="Tabla • goleadores • PJ/PG/PE/PP • GF/GC • estadísticas de la competencia activa",
        inline=False,
    )
    embed.set_footer(text="Los partidos históricos no se borran: quedan archivados por competencia.")
    return embed


class ConfirmAdvanceView(discord.ui.View):
    def __init__(self, runtime, bot, expected_phase: str):
        super().__init__(timeout=120)
        self.runtime = runtime
        self.bot = bot
        self.expected_phase = expected_phase

    @discord.ui.button(label="CONFIRMAR CAMBIO DE ETAPA", emoji="✅", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.runtime.es_admin(interaction):
            await interaction.response.send_message("⛔ Solo administradores.", ephemeral=True)
            return
        try:
            payload = runtime_advance(self.runtime, interaction.user.id, self.expected_phase)
        except CycleError as exc:
            await interaction.response.send_message(f"⚠️ {exc}", ephemeral=True)
            return
        try:
            import league_automation_patch as league
            if interaction.guild_id:
                await league.refresh(self.runtime, self.bot, int(interaction.guild_id))
        except Exception as exc:
            print(f"AJPA cycle refresh warning: {type(exc).__name__}: {exc}")
        await interaction.response.edit_message(
            embed=cycle_embed(payload),
            view=CompetitionCycleView(self.runtime, self.bot, payload),
        )

    @discord.ui.button(label="CANCELAR", emoji="✖️", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        payload = runtime_state(self.runtime)
        await interaction.response.edit_message(
            embed=cycle_embed(payload),
            view=CompetitionCycleView(self.runtime, self.bot, payload),
        )


class CompetitionCycleView(discord.ui.View):
    def __init__(self, runtime, bot, payload: dict | None = None):
        super().__init__(timeout=300)
        self.runtime = runtime
        self.bot = bot
        self.payload = payload or runtime_state(runtime)
        action = self.payload["next_action"]
        label = str(action["label"])
        if len(label) > 80:
            label = label[:77] + "..."
        button = discord.ui.Button(
            label=label,
            emoji="➡️",
            style=discord.ButtonStyle.primary,
            custom_id="ajpa_cycle_advance",
        )
        button.callback = self._advance
        self.add_item(button)

    async def _advance(self, interaction: discord.Interaction):
        if not self.runtime.es_admin(interaction):
            await interaction.response.send_message("⛔ Solo administradores.", ephemeral=True)
            return
        action = self.payload["next_action"]
        embed = discord.Embed(
            title="⚠️ Confirmar cambio de etapa",
            description=(
                f"Vas a ejecutar **{action['label']}**.\n\n"
                "Se archivarán las estadísticas de la competencia que termina cuando corresponda.\n"
                "**NO se tocarán planteles, dinero, fichajes ni historial de clásicos.**"
            ),
            color=discord.Color.orange(),
        )
        await interaction.response.edit_message(
            embed=embed,
            view=ConfirmAdvanceView(self.runtime, self.bot, self.payload["phase"]),
        )


def _install_league_filters() -> None:
    try:
        import league_automation_patch as league
    except Exception:
        return
    if getattr(league, "_ajpa_competition_cycle_filters", False):
        return

    def standings(conn):
        ensure_schema(conn)
        cid = active_competition_id(conn)
        table = {
            t: {"team": t, "pj": 0, "pg": 0, "pe": 0, "pp": 0, "gf": 0, "gc": 0, "pts": 0}
            for t in league.TEAMS
        }
        rows = [] if cid is None else conn.execute(
            """
            SELECT home_team, away_team, home_goals, away_goals
            FROM league_matches WHERE competition_id=? ORDER BY id ASC
            """,
            (cid,),
        ).fetchall()
        for row in rows:
            h = table.get(row["home_team"])
            a = table.get(row["away_team"])
            if not h or not a:
                continue
            hg, ag = int(row["home_goals"]), int(row["away_goals"])
            h["pj"] += 1; a["pj"] += 1
            h["gf"] += hg; h["gc"] += ag; a["gf"] += ag; a["gc"] += hg
            if hg > ag:
                h["pg"] += 1; a["pp"] += 1; h["pts"] += 3
            elif ag > hg:
                a["pg"] += 1; h["pp"] += 1; a["pts"] += 3
            else:
                h["pe"] += 1; a["pe"] += 1; h["pts"] += 1; a["pts"] += 1
        output = list(table.values())
        output.sort(key=lambda x: (-x["pts"], -(x["gf"] - x["gc"]), -x["gf"], -x["pg"], league.norm(x["team"])))
        return output[:24]

    def scorers_embed(conn):
        ensure_schema(conn)
        cid = active_competition_id(conn)
        rows = [] if cid is None else conn.execute(
            """
            SELECT player, team, SUM(goals) AS goals
            FROM league_goal_events WHERE competition_id=?
            GROUP BY player COLLATE NOCASE, COALESCE(team,'') COLLATE NOCASE
            ORDER BY goals DESC, player COLLATE NOCASE ASC LIMIT 30
            """,
            (cid,),
        ).fetchall()
        if rows:
            desc = "\n".join(
                f"**{i}. {row['player']}**{f' — {row[\"team\"]}' if row['team'] else ''} • ⚽ {row['goals']}"
                for i, row in enumerate(rows, 1)
            )
        else:
            desc = "Todavía no hay goles registrados en la competencia actual."
        embed = discord.Embed(title="⚽ Tabla de goleadores", description=desc)
        embed.set_footer(text="Estadísticas de la competencia activa")
        return embed

    league.standings = standings
    league.scorers_embed = scorers_embed
    league._ajpa_competition_cycle_filters = True


def apply_competition_cycle_patch(runtime, bot) -> None:
    if getattr(runtime, "_ajpa_competition_cycle_patch", False):
        return

    with runtime.db() as conn:
        ensure_schema(conn)
        conn.commit()

    _install_league_filters()
    runtime.competition_cycle_state = lambda: runtime_state(runtime)
    runtime.advance_competition_cycle = lambda user_id, expected_phase=None: runtime_advance(
        runtime, user_id, expected_phase
    )

    if bot.tree.get_command("etapa") is None:
        @bot.tree.command(name="etapa", description="Gestiona la etapa oficial de AJPA")
        async def etapa(interaction: discord.Interaction):
            if not runtime.es_admin(interaction):
                await interaction.response.send_message("⛔ Solo administradores.", ephemeral=True)
                return
            payload = runtime_state(runtime)
            await interaction.response.send_message(
                embed=cycle_embed(payload),
                view=CompetitionCycleView(runtime, bot, payload),
                ephemeral=True,
            )

    runtime._ajpa_competition_cycle_patch = True
    print("AJPA ciclo oficial activo: Pretemporada -> Temporada -> Mercado 1 -> Copa -> Mercado 2")
