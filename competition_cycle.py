"""AJPA official competition lifecycle and per-competition statistics.

Authoritative flow:
Pretemporada -> Temporada -> Mercado 1 -> Copa -> Mercado 2 -> next Temporada.

Historical league_matches rows are NEVER deleted. They are tagged with a
competition_id so current standings/scorers can reset without losing classic
rival history, old results or audit data. Rosters, balances and transfers are
never mutated by this module.
"""

from __future__ import annotations

import json
import sqlite3

import discord

PRESEASON = "preseason"
SEASON = "season"
MARKET_1 = "market_1"
CUP = "cup"
MARKET_2 = "market_2"
PLAYABLE = {PRESEASON, SEASON, CUP}
VALID = {PRESEASON, SEASON, MARKET_1, CUP, MARKET_2}


class CycleError(RuntimeError):
    pass


def _table(conn, name):
    return bool(conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1", (name,)
    ).fetchone())


def _cols(conn, table):
    if not _table(conn, table):
        return set()
    return {str(row["name"]) for row in conn.execute(f'PRAGMA table_info("{table}")')}


def _add_col(conn, table, column, definition):
    if _table(conn, table) and column not in _cols(conn, table):
        conn.execute(f'ALTER TABLE "{table}" ADD COLUMN "{column}" {definition}')


def _ensure_market(conn):
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS market_state (
            id INTEGER PRIMARY KEY CHECK(id=1), is_open INTEGER NOT NULL DEFAULT 0,
            updated_by INTEGER, updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS market_state_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT, is_open INTEGER NOT NULL,
            changed_by INTEGER, changed_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS market_cycles (
            id INTEGER PRIMARY KEY AUTOINCREMENT, season_id INTEGER, opened_by INTEGER,
            opened_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP, closed_by INTEGER,
            closed_at DATETIME, report_sent_at DATETIME,
            report_recipient_count INTEGER NOT NULL DEFAULT 0
        );
        INSERT OR IGNORE INTO market_state(id,is_open) VALUES(1,0);
        """
    )


def _season_id(conn):
    if not _table(conn, "seasons"):
        return None
    row = conn.execute("SELECT id FROM seasons WHERE active=1 ORDER BY id DESC LIMIT 1").fetchone()
    return int(row["id"]) if row else None


def _sync_season(conn, number):
    if not _table(conn, "seasons"):
        return
    name = f"Temporada {int(number)}"
    conn.execute("UPDATE seasons SET active=0")
    conn.execute("INSERT OR IGNORE INTO seasons(name,active) VALUES(?,0)", (name,))
    conn.execute("UPDATE seasons SET active=1 WHERE name=?", (name,))


def _market(conn, opened, user_id):
    _ensure_market(conn)
    value = 1 if opened else 0
    old_row = conn.execute("SELECT is_open FROM market_state WHERE id=1").fetchone()
    old = int(old_row["is_open"]) if old_row else None
    conn.execute(
        """INSERT INTO market_state(id,is_open,updated_by,updated_at)
           VALUES(1,?,?,CURRENT_TIMESTAMP)
           ON CONFLICT(id) DO UPDATE SET is_open=excluded.is_open,
           updated_by=excluded.updated_by, updated_at=CURRENT_TIMESTAMP""",
        (value, int(user_id)),
    )
    if old != value:
        conn.execute(
            "INSERT INTO market_state_history(is_open,changed_by) VALUES(?,?)",
            (value, int(user_id)),
        )
    cycle = conn.execute(
        "SELECT id FROM market_cycles WHERE closed_at IS NULL ORDER BY id DESC LIMIT 1"
    ).fetchone()
    if opened:
        if cycle:
            return int(cycle["id"])
        cur = conn.execute(
            "INSERT INTO market_cycles(season_id,opened_by) VALUES(?,?)",
            (_season_id(conn), int(user_id)),
        )
        return int(cur.lastrowid)
    if cycle:
        conn.execute(
            "UPDATE market_cycles SET closed_by=?,closed_at=CURRENT_TIMESTAMP WHERE id=? AND closed_at IS NULL",
            (int(user_id), int(cycle["id"])),
        )
        return int(cycle["id"])
    return None


def ensure_schema(conn):
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS competition_editions (
            id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT NOT NULL,
            season_number INTEGER NOT NULL, label TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'active',
            started_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            ended_at DATETIME, final_snapshot_json TEXT
        );
        CREATE TABLE IF NOT EXISTS competition_cycle_state (
            id INTEGER PRIMARY KEY CHECK(id=1), phase TEXT NOT NULL,
            season_number INTEGER NOT NULL DEFAULT 1, competition_id INTEGER,
            updated_by INTEGER, updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS competition_cycle_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT, from_phase TEXT NOT NULL,
            to_phase TEXT NOT NULL, season_number INTEGER NOT NULL,
            competition_id INTEGER, changed_by INTEGER,
            changed_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """
    )
    _ensure_market(conn)
    _add_col(conn, "league_matches", "competition_id", "INTEGER")
    _add_col(conn, "league_goal_events", "competition_id", "INTEGER")

    state = conn.execute("SELECT * FROM competition_cycle_state WHERE id=1").fetchone()
    if state is None:
        cur = conn.execute(
            "INSERT INTO competition_editions(kind,season_number,label,status) VALUES('preseason',1,'Pretemporada','active')"
        )
        cid = int(cur.lastrowid)
        conn.execute(
            "INSERT INTO competition_cycle_state(id,phase,season_number,competition_id) VALUES(1,'preseason',1,?)",
            (cid,),
        )
        if _table(conn, "league_matches"):
            conn.execute("UPDATE league_matches SET competition_id=? WHERE competition_id IS NULL", (cid,))
        if _table(conn, "league_goal_events"):
            conn.execute("UPDATE league_goal_events SET competition_id=? WHERE competition_id IS NULL", (cid,))
        _market(conn, False, 0)
        state = conn.execute("SELECT * FROM competition_cycle_state WHERE id=1").fetchone()
    elif str(state["phase"]) in PLAYABLE and state["competition_id"] is not None:
        cid = int(state["competition_id"])
        if _table(conn, "league_matches"):
            conn.execute("UPDATE league_matches SET competition_id=? WHERE competition_id IS NULL", (cid,))
        if _table(conn, "league_goal_events"):
            conn.execute("UPDATE league_goal_events SET competition_id=? WHERE competition_id IS NULL", (cid,))

    if _table(conn, "league_matches"):
        conn.executescript(
            """CREATE TRIGGER IF NOT EXISTS ajpa_competition_match_tag
               AFTER INSERT ON league_matches WHEN NEW.competition_id IS NULL
               BEGIN
                 UPDATE league_matches SET competition_id=(
                   SELECT competition_id FROM competition_cycle_state
                   WHERE id=1 AND phase IN ('preseason','season','cup')
                 ) WHERE id=NEW.id;
               END;"""
        )
    if _table(conn, "league_goal_events"):
        conn.executescript(
            """CREATE TRIGGER IF NOT EXISTS ajpa_competition_goal_tag
               AFTER INSERT ON league_goal_events WHEN NEW.competition_id IS NULL
               BEGIN
                 UPDATE league_goal_events SET competition_id=(
                   SELECT competition_id FROM competition_cycle_state
                   WHERE id=1 AND phase IN ('preseason','season','cup')
                 ) WHERE id=NEW.id;
               END;"""
        )


def active_competition_id(conn):
    ensure_schema(conn)
    row = conn.execute("SELECT phase,competition_id FROM competition_cycle_state WHERE id=1").fetchone()
    if not row or str(row["phase"]) not in PLAYABLE or row["competition_id"] is None:
        return None
    return int(row["competition_id"])


def _phase_label(phase, n):
    return {
        PRESEASON: "Pretemporada",
        SEASON: f"Temporada {n}",
        MARKET_1: f"Mercado 1 • Temporada {n}",
        CUP: f"Copa • Temporada {n}",
        MARKET_2: f"Mercado 2 • Temporada {n}",
    }.get(phase, phase)


def _action(phase, n):
    if phase == PRESEASON:
        return {"key":"start_season","label":f"INICIAR TEMPORADA {n}","description":"Archiva la pretemporada y crea la temporada oficial en cero."}
    if phase == SEASON:
        return {"key":"season_market1","label":"FINALIZAR TEMPORADA + ABRIR MERCADO 1","description":"Archiva la temporada y abre la primera ventana de mercado."}
    if phase == MARKET_1:
        return {"key":"market1_cup","label":"CERRAR MERCADO 1 + INICIAR COPA","description":"Cierra Mercado 1 e inicia una Copa nueva."}
    if phase == CUP:
        return {"key":"cup_market2","label":"FINALIZAR COPA + ABRIR MERCADO 2","description":"Archiva la Copa y abre la segunda ventana de mercado."}
    if phase == MARKET_2:
        return {"key":"market2_season","label":f"CERRAR MERCADO 2 + INICIAR TEMPORADA {n+1}","description":"Cierra Mercado 2 e inicia la siguiente temporada en cero."}
    raise CycleError(f"Etapa inválida: {phase}")


def state_payload(conn):
    ensure_schema(conn)
    state = conn.execute("SELECT * FROM competition_cycle_state WHERE id=1").fetchone()
    if not state:
        raise CycleError("No existe el estado del ciclo AJPA.")
    phase, n = str(state["phase"]), int(state["season_number"])
    edition = None
    if state["competition_id"] is not None:
        edition = conn.execute("SELECT * FROM competition_editions WHERE id=?", (int(state["competition_id"]),)).fetchone()
    market = conn.execute("SELECT is_open FROM market_state WHERE id=1").fetchone()
    cycle = conn.execute("SELECT id FROM market_cycles WHERE closed_at IS NULL ORDER BY id DESC LIMIT 1").fetchone()
    return {
        "phase": phase,
        "phase_label": _phase_label(phase, n),
        "season_number": n,
        "competition_id": int(state["competition_id"]) if state["competition_id"] is not None else None,
        "competition": ({"id":int(edition["id"]),"kind":str(edition["kind"]),"label":str(edition["label"]),"status":str(edition["status"])} if edition else None),
        "market_open": bool(market and int(market["is_open"])),
        "market_cycle_id": int(cycle["id"]) if cycle else None,
        "next_action": _action(phase, n),
        "timeline": ["Temporada","Mercado 1","Copa","Mercado 2","Temporada"],
        "persistent_note": "Planteles, saldos, fichajes e historial de clásicos nunca se resetean.",
        "competition_note": "Tabla, goleadores y estadísticas activas pertenecen solo a la competencia actual.",
        "updated_at": str(state["updated_at"] or ""),
    }


def _snapshot(conn, cid):
    table = {}
    if _table(conn, "league_matches"):
        rows = conn.execute(
            "SELECT home_team,away_team,home_goals,away_goals FROM league_matches WHERE competition_id=? ORDER BY id",
            (int(cid),),
        ).fetchall()
        for r in rows:
            hn, an = str(r["home_team"]), str(r["away_team"])
            for team in (hn, an):
                table.setdefault(team, {"team":team,"pj":0,"pg":0,"pe":0,"pp":0,"gf":0,"gc":0,"pts":0})
            h, a = table[hn], table[an]
            hg, ag = int(r["home_goals"]), int(r["away_goals"])
            h["pj"] += 1; a["pj"] += 1; h["gf"] += hg; h["gc"] += ag; a["gf"] += ag; a["gc"] += hg
            if hg > ag: h["pg"] += 1; a["pp"] += 1; h["pts"] += 3
            elif ag > hg: a["pg"] += 1; h["pp"] += 1; a["pts"] += 3
            else: h["pe"] += 1; a["pe"] += 1; h["pts"] += 1; a["pts"] += 1
    standings = list(table.values())
    for r in standings: r["dg"] = r["gf"] - r["gc"]
    standings.sort(key=lambda r: (-r["pts"],-r["dg"],-r["gf"],-r["pg"],r["team"].casefold()))
    scorers = []
    if _table(conn, "league_goal_events"):
        rows = conn.execute(
            """SELECT player,team,SUM(goals) goals FROM league_goal_events WHERE competition_id=?
               GROUP BY player COLLATE NOCASE,COALESCE(team,'') COLLATE NOCASE
               ORDER BY goals DESC,player COLLATE NOCASE""", (int(cid),)
        ).fetchall()
        scorers = [{"player":str(r["player"]),"team":str(r["team"] or ""),"goals":int(r["goals"] or 0)} for r in rows]
    return json.dumps({"standings":standings,"scorers":scorers}, ensure_ascii=False, separators=(",",":"))


def _finish(conn, cid):
    if cid is None:
        return
    conn.execute(
        "UPDATE competition_editions SET status='finished',ended_at=CURRENT_TIMESTAMP,final_snapshot_json=? WHERE id=? AND status='active'",
        (_snapshot(conn, int(cid)), int(cid)),
    )


def _new(conn, kind, n, label):
    cur = conn.execute(
        "INSERT INTO competition_editions(kind,season_number,label,status) VALUES(?,?,?,'active')",
        (kind, int(n), label),
    )
    return int(cur.lastrowid)


def advance(conn, user_id, expected_phase=None):
    ensure_schema(conn)
    conn.commit()
    conn.execute("PRAGMA busy_timeout=5000")
    try:
        conn.execute("BEGIN IMMEDIATE")
        s = conn.execute("SELECT * FROM competition_cycle_state WHERE id=1").fetchone()
        if not s:
            raise CycleError("No existe el estado del ciclo.")
        phase, n = str(s["phase"]), int(s["season_number"])
        if phase not in VALID:
            raise CycleError(f"Etapa inválida: {phase}")
        if expected_phase and str(expected_phase) != phase:
            raise CycleError("La etapa cambió desde que abriste el panel. Actualizá y volvé a intentar.")
        cid = int(s["competition_id"]) if s["competition_id"] is not None else None
        next_phase, next_n, next_cid = phase, n, None

        if phase == PRESEASON:
            _finish(conn, cid); _market(conn, False, user_id); _sync_season(conn, n)
            next_phase, next_cid = SEASON, _new(conn, "season", n, f"Temporada {n}")
        elif phase == SEASON:
            _finish(conn, cid); _market(conn, True, user_id)
            next_phase = MARKET_1
        elif phase == MARKET_1:
            _market(conn, False, user_id)
            next_phase, next_cid = CUP, _new(conn, "cup", n, f"Copa • Temporada {n}")
        elif phase == CUP:
            _finish(conn, cid); _market(conn, True, user_id)
            next_phase = MARKET_2
        elif phase == MARKET_2:
            _market(conn, False, user_id); next_n = n + 1; _sync_season(conn, next_n)
            next_phase, next_cid = SEASON, _new(conn, "season", next_n, f"Temporada {next_n}")

        conn.execute(
            "UPDATE competition_cycle_state SET phase=?,season_number=?,competition_id=?,updated_by=?,updated_at=CURRENT_TIMESTAMP WHERE id=1",
            (next_phase, next_n, next_cid, int(user_id)),
        )
        conn.execute(
            "INSERT INTO competition_cycle_history(from_phase,to_phase,season_number,competition_id,changed_by) VALUES(?,?,?,?,?)",
            (phase, next_phase, next_n, next_cid, int(user_id)),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return state_payload(conn)


def runtime_state(runtime):
    with runtime.db() as conn:
        payload = state_payload(conn); conn.commit(); return payload


def runtime_advance(runtime, user_id, expected_phase=None):
    conn = runtime.db()
    try: return advance(conn, int(user_id), expected_phase)
    finally: conn.close()


def cycle_embed(payload):
    action = payload["next_action"]
    embed = discord.Embed(
        title="🗓️ CICLO AJPA",
        description=f"**Etapa actual:** {payload['phase_label']}\n\n**Temporada → Mercado 1 → Copa → Mercado 2 → Temporada**",
        color=discord.Color.blurple(),
    )
    embed.add_field(name="Siguiente acción", value=f"**{action['label']}**\n{action['description']}", inline=False)
    embed.add_field(name="🔒 Nunca se resetea", value="Planteles • saldos • fichajes • historial de transferencias • historial de clásicos", inline=False)
    embed.add_field(name="🔄 Por competencia", value="Tabla • goleadores • PJ/PG/PE/PP • GF/GC • estadísticas activas", inline=False)
    embed.set_footer(text="Los resultados históricos quedan archivados por competencia; no se borran.")
    return embed


class ConfirmView(discord.ui.View):
    def __init__(self, runtime, bot, expected):
        super().__init__(timeout=120); self.runtime=runtime; self.bot=bot; self.expected=expected

    @discord.ui.button(label="CONFIRMAR CAMBIO DE ETAPA", emoji="✅", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction, button):
        if not self.runtime.es_admin(interaction):
            await interaction.response.send_message("⛔ Solo administradores.", ephemeral=True); return
        try:
            payload = runtime_advance(self.runtime, interaction.user.id, self.expected)
        except CycleError as exc:
            await interaction.response.send_message(f"⚠️ {exc}", ephemeral=True); return
        try:
            import league_automation_patch as league
            if interaction.guild_id: await league.refresh(self.runtime, self.bot, int(interaction.guild_id))
        except Exception as exc:
            print(f"AJPA cycle refresh warning: {type(exc).__name__}: {exc}")
        await interaction.response.edit_message(embed=cycle_embed(payload), view=CycleView(self.runtime,self.bot,payload))

    @discord.ui.button(label="CANCELAR", emoji="✖️", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction, button):
        payload = runtime_state(self.runtime)
        await interaction.response.edit_message(embed=cycle_embed(payload), view=CycleView(self.runtime,self.bot,payload))


class CycleView(discord.ui.View):
    def __init__(self, runtime, bot, payload=None):
        super().__init__(timeout=300); self.runtime=runtime; self.bot=bot; self.payload=payload or runtime_state(runtime)
        label = str(self.payload["next_action"]["label"])
        b = discord.ui.Button(label=label[:80], emoji="➡️", style=discord.ButtonStyle.primary, custom_id="ajpa_cycle_advance")
        b.callback = self._go; self.add_item(b)

    async def _go(self, interaction):
        if not self.runtime.es_admin(interaction):
            await interaction.response.send_message("⛔ Solo administradores.", ephemeral=True); return
        action = self.payload["next_action"]
        embed = discord.Embed(
            title="⚠️ Confirmar cambio de etapa",
            description=f"Vas a ejecutar **{action['label']}**.\n\nSe archiva la competencia que termina cuando corresponda.\n**NO se tocan planteles, dinero, fichajes ni historial de clásicos.**",
            color=discord.Color.orange(),
        )
        await interaction.response.edit_message(embed=embed, view=ConfirmView(self.runtime,self.bot,self.payload["phase"]))


def install_league_filters():
    try: import league_automation_patch as league
    except Exception: return
    if getattr(league, "_ajpa_cycle_filters", False): return

    def standings(conn):
        ensure_schema(conn); cid = active_competition_id(conn)
        table = {t:{"team":t,"pj":0,"pg":0,"pe":0,"pp":0,"gf":0,"gc":0,"pts":0} for t in league.TEAMS}
        rows = [] if cid is None else conn.execute(
            "SELECT home_team,away_team,home_goals,away_goals FROM league_matches WHERE competition_id=? ORDER BY id", (cid,)
        ).fetchall()
        for r in rows:
            h,a=table.get(r["home_team"]),table.get(r["away_team"])
            if not h or not a: continue
            hg,ag=int(r["home_goals"]),int(r["away_goals"]); h["pj"]+=1; a["pj"]+=1; h["gf"]+=hg; h["gc"]+=ag; a["gf"]+=ag; a["gc"]+=hg
            if hg>ag: h["pg"]+=1; a["pp"]+=1; h["pts"]+=3
            elif ag>hg: a["pg"]+=1; h["pp"]+=1; a["pts"]+=3
            else: h["pe"]+=1; a["pe"]+=1; h["pts"]+=1; a["pts"]+=1
        out=list(table.values()); out.sort(key=lambda x:(-x["pts"],-(x["gf"]-x["gc"]),-x["gf"],-x["pg"],league.norm(x["team"])))
        return out[:24]

    def scorers_embed(conn):
        ensure_schema(conn); cid=active_competition_id(conn)
        rows=[] if cid is None else conn.execute(
            """SELECT player,team,SUM(goals) goals FROM league_goal_events WHERE competition_id=?
               GROUP BY player COLLATE NOCASE,COALESCE(team,'') COLLATE NOCASE
               ORDER BY goals DESC,player COLLATE NOCASE LIMIT 30""", (cid,)
        ).fetchall()
        lines=[]
        for i,row in enumerate(rows,1):
            club = f" — {row['team']}" if row["team"] else ""
            lines.append(f"**{i}. {row['player']}**{club} • ⚽ {row['goals']}")
        embed=discord.Embed(title="⚽ Tabla de goleadores",description="\n".join(lines) or "Todavía no hay goles registrados en la competencia actual.")
        embed.set_footer(text="Estadísticas de la competencia activa"); return embed

    league.standings=standings; league.scorers_embed=scorers_embed; league._ajpa_cycle_filters=True


def apply_competition_cycle(runtime, bot):
    if getattr(runtime, "_ajpa_competition_cycle", False): return
    with runtime.db() as conn: ensure_schema(conn); conn.commit()
    install_league_filters()
    runtime.competition_cycle_state=lambda: runtime_state(runtime)
    runtime.advance_competition_cycle=lambda user_id,expected_phase=None: runtime_advance(runtime,user_id,expected_phase)
    if bot.tree.get_command("etapa") is None:
        @bot.tree.command(name="etapa", description="Gestiona la etapa oficial de AJPA")
        async def etapa(interaction: discord.Interaction):
            if not runtime.es_admin(interaction):
                await interaction.response.send_message("⛔ Solo administradores.",ephemeral=True); return
            payload=runtime_state(runtime)
            await interaction.response.send_message(embed=cycle_embed(payload),view=CycleView(runtime,bot,payload),ephemeral=True)
    runtime._ajpa_competition_cycle=True
    print("AJPA ciclo oficial: Pretemporada -> Temporada -> Mercado 1 -> Copa -> Mercado 2")
