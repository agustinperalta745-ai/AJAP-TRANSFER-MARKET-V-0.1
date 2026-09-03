"""One-time authoritative AJPA preseason reconciliation from the 2026-09-03 manual audit.

Scope is deliberately narrow:
- only the historical/legacy AJPA guild;
- only while the active competition is Pretemporada;
- one persisted marker prevents a second DB rewrite;
- GES channel rebuild is retried independently until all 38 cards exist.

The audited match ledger is the source of truth for current preseason standings,
scorers and result history. Own goals count for the score/standings but never for
an individual scorer.
"""
from __future__ import annotations

import json
from collections import defaultdict

import discord

import competition_cycle as cycle
import guild_isolation_patch as guild_isolation
import league_automation_patch as league
import league_ges_result_queue_patch as ges
import league_ges_scorer_details_patch as ges_details
import league_scorer_pending_patch as scorer_pending

APP = None
BOT = None
MARKER = "authoritative_preseason_audit_2026_09_03_v1"
TARGET_GUILD_ID = int(guild_isolation.LEGACY_GUILD_ID)
SYNTHETIC_BASE = -202609030000

# (home, away, home_goals, away_goals, [(player, team, goals)], [(beneficiary_team, goals)])
AUDITED_MATCHES = [
    ("Villarreal", "Everton", 1, 2, [("Pires", "Villarreal", 1), ("Carsley", "Everton", 1), ("Beattie", "Everton", 1)], []),
    ("París Saint-Germain (PSG)", "Real Zaragoza", 1, 1, [("Kalou", "París Saint-Germain (PSG)", 1), ("Aimar", "Real Zaragoza", 1)], []),
    ("Real Zaragoza", "París Saint-Germain (PSG)", 2, 0, [("Ewerthon", "Real Zaragoza", 1), ("Aimar", "Real Zaragoza", 1)], []),
    ("Real Zaragoza", "Everton", 2, 3, [("D’Alessandro", "Real Zaragoza", 2), ("Van der Meyde", "Everton", 3)], []),
    ("Everton", "Real Zaragoza", 2, 3, [("Van der Meyde", "Everton", 1), ("Beattie", "Everton", 1), ("Aimar", "Real Zaragoza", 1), ("D. Milito", "Real Zaragoza", 2)], []),
    ("Real Zaragoza", "Ajax", 1, 2, [("Ewerthon", "Real Zaragoza", 1), ("Huntelaar", "Ajax", 1)], [("Ajax", 1)]),
    ("Ajax", "Real Zaragoza", 3, 1, [("Huntelaar", "Ajax", 1), ("Sneijder", "Ajax", 1), ("Babel", "Ajax", 1), ("Aimar", "Real Zaragoza", 1)], []),
    ("Ajax", "Everton", 2, 1, [("Babel", "Ajax", 2), ("Van der Meyde", "Everton", 1)], []),
    ("Everton", "Ajax", 2, 3, [("Carsley", "Everton", 1), ("Beattie", "Everton", 1), ("Mitea", "Ajax", 1), ("Huntelaar", "Ajax", 2)], []),
    ("Real Zaragoza", "Manchester City", 1, 1, [("Movilla", "Real Zaragoza", 1), ("Andy Cole", "Manchester City", 1)], []),
    ("Manchester City", "Real Zaragoza", 3, 3, [("Beasley", "Manchester City", 1), ("Barton", "Manchester City", 1), ("Vassell", "Manchester City", 1), ("Celades", "Real Zaragoza", 1), ("Ewerthon", "Real Zaragoza", 2)], []),
    ("París Saint-Germain (PSG)", "Porto", 1, 2, [("P.A. Frau", "París Saint-Germain (PSG)", 1), ("Quaresma", "Porto", 1), ("Lisandro Lopez", "Porto", 1)], []),
    ("Porto", "París Saint-Germain (PSG)", 2, 0, [("Alan", "Porto", 2)], []),
    ("West Ham United", "Manchester City", 0, 6, [("Samaras", "Manchester City", 1), ("Hamann", "Manchester City", 4), ("Vassell", "Manchester City", 1)], []),
    ("Real Zaragoza", "Porto", 0, 1, [("Quaresma", "Porto", 1)], []),
    ("Manchester City", "Everton", 2, 2, [("Ireland", "Manchester City", 1), ("Corradi", "Manchester City", 1), ("Van der Meyde", "Everton", 1), ("Carsley", "Everton", 1)], []),
    ("Everton", "Manchester City", 0, 3, [("Andy Cole", "Manchester City", 2), ("Samaras", "Manchester City", 1)], []),
    ("Real Zaragoza", "Bolton Wanderers", 4, 1, [("Óscar", "Real Zaragoza", 1), ("D. Milito", "Real Zaragoza", 2), ("Anelka", "Bolton Wanderers", 1)], [("Real Zaragoza", 1)]),
    ("Bolton Wanderers", "Real Zaragoza", 0, 2, [("D. Milito", "Real Zaragoza", 2)], []),
    ("Manchester City", "Bolton Wanderers", 2, 1, [("Vassell", "Manchester City", 1), ("Hamann", "Manchester City", 1), ("Nolan", "Bolton Wanderers", 1)], []),
    ("Tottenham Hotspur", "Manchester City", 2, 1, [("Mido", "Tottenham Hotspur", 1), ("Robbie Keane", "Tottenham Hotspur", 1), ("Vassell", "Manchester City", 1)], []),
    ("Manchester City", "Tottenham Hotspur", 3, 4, [("Vassell", "Manchester City", 3), ("Defoe", "Tottenham Hotspur", 1), ("Robbie Keane", "Tottenham Hotspur", 1), ("Berbatov", "Tottenham Hotspur", 2)], []),
    ("Ajax", "París Saint-Germain (PSG)", 2, 2, [("Babel", "Ajax", 2), ("Pauleta", "París Saint-Germain (PSG)", 2)], []),
    ("París Saint-Germain (PSG)", "Ajax", 2, 3, [("Pauleta", "París Saint-Germain (PSG)", 1), ("Rothen", "París Saint-Germain (PSG)", 1), ("Emanuelson", "Ajax", 1), ("Huntelaar", "Ajax", 2)], []),
    ("Real Zaragoza", "Real Betis", 1, 0, [("D. Milito", "Real Zaragoza", 1)], []),
    ("West Ham United", "Tottenham Hotspur", 0, 3, [("Mido", "Tottenham Hotspur", 1), ("Berbatov", "Tottenham Hotspur", 1), ("Jenas", "Tottenham Hotspur", 1)], []),
    ("París Saint-Germain (PSG)", "Manchester City", 1, 0, [("Pauleta", "París Saint-Germain (PSG)", 1)], []),
    ("Tottenham Hotspur", "West Ham United", 3, 1, [("Berbatov", "Tottenham Hotspur", 1), ("Danny Murphy", "Tottenham Hotspur", 1), ("Robbie Keane", "Tottenham Hotspur", 1), ("Bowyer", "West Ham United", 1)], []),
    ("Real Betis", "Real Zaragoza", 0, 5, [("Ewerthon", "Real Zaragoza", 1), ("D. Milito", "Real Zaragoza", 2), ("Óscar", "Real Zaragoza", 1)], [("Real Zaragoza", 1)]),
    ("Villarreal", "Manchester City", 1, 1, [("Franco", "Villarreal", 1), ("Andy Cole", "Manchester City", 1)], []),
    ("París Saint-Germain (PSG)", "Bolton Wanderers", 1, 0, [("Dhorasoo", "París Saint-Germain (PSG)", 1)], []),
    ("Villarreal", "Bolton Wanderers", 2, 4, [("Riquelme", "Villarreal", 1), ("Forlán", "Villarreal", 1), ("Pedersen", "Bolton Wanderers", 1), ("Nolan", "Bolton Wanderers", 2), ("Anelka", "Bolton Wanderers", 1)], []),
    ("Bolton Wanderers", "Villarreal", 2, 0, [("Anelka", "Bolton Wanderers", 2)], []),
    ("Manchester City", "París Saint-Germain (PSG)", 1, 1, [("Beasley", "Manchester City", 1), ("Pauleta", "París Saint-Germain (PSG)", 1)], []),
    ("Manchester City", "Villarreal", 1, 0, [("Andy Cole", "Manchester City", 1)], []),
    ("Villarreal", "West Ham United", 3, 1, [("Forlán", "Villarreal", 1), ("Riquelme", "Villarreal", 2), ("Tévez", "West Ham United", 1)], []),
    ("West Ham United", "Villarreal", 3, 0, [("Tévez", "West Ham United", 2), ("Harewood", "West Ham United", 1)], []),
    ("Feyenoord", "Real Zaragoza", 1, 1, [("van Hooijdonk", "Feyenoord", 1), ("Ewerthon", "Real Zaragoza", 1)], []),
]


def _table(conn, name: str) -> bool:
    return bool(conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1", (name,)).fetchone())


def _cols(conn, table: str) -> set[str]:
    if not _table(conn, table):
        return set()
    return {str(row["name"]) for row in conn.execute(f'PRAGMA table_info("{table}")').fetchall()}


def _json_row(row):
    return json.dumps({key: row[key] for key in row.keys()}, ensure_ascii=False, default=str)


def _canon(raw):
    return league.canonical_team(raw) or str(raw or "").strip()


def _same_result(candidate, home, away, hg, ag):
    ch, ca = _canon(candidate.get("home_team")), _canon(candidate.get("away_team"))
    try:
        cg_h, cg_a = int(candidate.get("home_goals")), int(candidate.get("away_goals"))
    except Exception:
        return False
    if ch == home and ca == away and cg_h == int(hg) and cg_a == int(ag):
        return True
    return ch == away and ca == home and cg_h == int(ag) and cg_a == int(hg)


def _candidate_sources(conn):
    candidates = {}

    def add(source_id, priority, home, away, hg, ag, channel=0, author=0, created_at=None):
        if source_id is None:
            return
        try:
            source_id = int(source_id)
        except Exception:
            return
        item = {
            "source_message_id": source_id,
            "priority": int(priority),
            "home_team": str(home or ""),
            "away_team": str(away or ""),
            "home_goals": hg,
            "away_goals": ag,
            "source_channel_id": int(channel or 0),
            "author_id": int(author or 0),
            "created_at": str(created_at or ""),
        }
        previous = candidates.get(source_id)
        if previous is None or item["priority"] < previous["priority"]:
            candidates[source_id] = item

    if _table(conn, "league_matches"):
        for row in conn.execute("SELECT * FROM league_matches ORDER BY id ASC").fetchall():
            add(row["source_message_id"], 0, row["home_team"], row["away_team"], row["home_goals"], row["away_goals"], row["source_channel_id"], row["author_id"], row["created_at"])

    if _table(conn, "league_result_evidence"):
        cols = _cols(conn, "league_result_evidence")
        needed = {"source_message_id", "home_team", "away_team", "home_goals", "away_goals"}
        if needed.issubset(cols):
            for row in conn.execute("SELECT * FROM league_result_evidence ORDER BY source_message_id ASC").fetchall():
                add(row["source_message_id"], 1, row["home_team"], row["away_team"], row["home_goals"], row["away_goals"], row["source_channel_id"] if "source_channel_id" in cols else 0, row["author_id"] if "author_id" in cols else 0, row["created_at"] if "created_at" in cols else None)

    if _table(conn, "league_ges_result_queue"):
        cols = _cols(conn, "league_ges_result_queue")
        for row in conn.execute("SELECT * FROM league_ges_result_queue ORDER BY source_message_id ASC").fetchall():
            add(row["source_message_id"], 2, row["home_team"], row["away_team"], row["home_goals"], row["away_goals"], row["source_channel_id"] if "source_channel_id" in cols else 0, 0, row["created_at"] if "created_at" in cols else None)

    return sorted(candidates.values(), key=lambda item: (item["priority"], item["source_message_id"]))


def _choose_sources(conn):
    pool = _candidate_sources(conn)
    used = set()
    chosen = []
    for index, (home, away, hg, ag, _scorers, _own) in enumerate(AUDITED_MATCHES, 1):
        found = None
        for candidate in pool:
            sid = int(candidate["source_message_id"])
            if sid in used or sid <= 0:
                continue
            if _same_result(candidate, home, away, hg, ag):
                found = candidate
                break
        if found is None:
            found = {"source_message_id": SYNTHETIC_BASE - index, "source_channel_id": 0, "author_id": 0, "created_at": f"2026-09-03 00:00:{index:02d}"}
        used.add(int(found["source_message_id"]))
        chosen.append(found)
    return chosen


def _ensure_reconcile_schema(conn):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS league_authoritative_reconcile_state (
            marker TEXT PRIMARY KEY,
            competition_id INTEGER,
            match_count INTEGER NOT NULL DEFAULT 0,
            db_applied_at DATETIME,
            ges_applied_at DATETIME,
            note TEXT
        );
        CREATE TABLE IF NOT EXISTS league_authoritative_reconcile_backup (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            marker TEXT NOT NULL,
            table_name TEXT NOT NULL,
            row_json TEXT NOT NULL,
            archived_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS league_own_goal_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_message_id INTEGER NOT NULL,
            beneficiary_team TEXT NOT NULL,
            goals INTEGER NOT NULL DEFAULT 1,
            competition_id INTEGER,
            note TEXT,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_league_own_goals_source ON league_own_goal_events(source_message_id);
        CREATE INDEX IF NOT EXISTS idx_league_own_goals_competition ON league_own_goal_events(competition_id);
    """)


def _active_preseason(conn):
    cycle.ensure_schema(conn)
    row = conn.execute("SELECT phase,competition_id FROM competition_cycle_state WHERE id=1 LIMIT 1").fetchone()
    if not row or str(row["phase"] or "") != cycle.PRESEASON or row["competition_id"] is None:
        return None
    return int(row["competition_id"])


def _backup_rows(conn, table: str, rows):
    for row in rows:
        conn.execute("INSERT INTO league_authoritative_reconcile_backup(marker,table_name,row_json) VALUES(?,?,?)", (MARKER, table, _json_row(row)))


def _normalize_player_name(conn, raw: str) -> str:
    raw = str(raw or "").strip()
    if not raw or not _table(conn, "roster_players"):
        return raw
    rows = conn.execute("SELECT name FROM roster_players").fetchall()
    exact = {league.norm(row["name"]): str(row["name"]) for row in rows}
    key = league.norm(raw)
    return exact.get(key, raw)


def _expected_standings():
    stats = defaultdict(lambda: {"pj": 0, "pg": 0, "pe": 0, "pp": 0, "gf": 0, "gc": 0, "pts": 0})
    for home, away, hg, ag, _scorers, _own in AUDITED_MATCHES:
        stats[home]["pj"] += 1; stats[away]["pj"] += 1
        stats[home]["gf"] += hg; stats[home]["gc"] += ag; stats[away]["gf"] += ag; stats[away]["gc"] += hg
        if hg > ag: stats[home]["pg"] += 1; stats[away]["pp"] += 1; stats[home]["pts"] += 3
        elif ag > hg: stats[away]["pg"] += 1; stats[home]["pp"] += 1; stats[away]["pts"] += 3
        else: stats[home]["pe"] += 1; stats[away]["pe"] += 1; stats[home]["pts"] += 1; stats[away]["pts"] += 1
    return dict(stats)


EXPECTED_STANDINGS = _expected_standings()


def _rebuild_database(runtime, guild_id: int):
    conn = league.db(runtime, int(guild_id))
    try:
        _ensure_reconcile_schema(conn)
        cid = _active_preseason(conn)
        if cid is None:
            print("AJAP authoritative audit: skipped because active phase is not Pretemporada")
            return False, None
        state = conn.execute("SELECT db_applied_at FROM league_authoritative_reconcile_state WHERE marker=?", (MARKER,)).fetchone()
        if state and state["db_applied_at"]:
            return False, cid

        selected_sources = _choose_sources(conn)
        conn.commit()
        conn.execute("BEGIN IMMEDIATE")
        match_cols, goal_cols = _cols(conn, "league_matches"), _cols(conn, "league_goal_events")
        old_matches = conn.execute("SELECT * FROM league_matches WHERE competition_id=? ORDER BY id ASC", (cid,)).fetchall() if "competition_id" in match_cols else conn.execute("SELECT * FROM league_matches ORDER BY id ASC").fetchall()
        old_source_ids = [int(row["source_message_id"]) for row in old_matches]
        _backup_rows(conn, "league_matches", old_matches)

        if _table(conn, "league_goal_events"):
            if "competition_id" in goal_cols:
                old_goals = conn.execute("SELECT * FROM league_goal_events WHERE competition_id=? ORDER BY id ASC", (cid,)).fetchall()
            elif old_source_ids:
                placeholders = ",".join("?" for _ in old_source_ids)
                old_goals = conn.execute(f"SELECT * FROM league_goal_events WHERE source_message_id IN ({placeholders}) ORDER BY id ASC", tuple(old_source_ids)).fetchall()
            else:
                old_goals = []
            _backup_rows(conn, "league_goal_events", old_goals)

        if _table(conn, "league_ges_result_queue"):
            old_ges = conn.execute("SELECT * FROM league_ges_result_queue WHERE guild_id=? ORDER BY created_at ASC", (int(guild_id),)).fetchall()
            _backup_rows(conn, "league_ges_result_queue", old_ges)
            conn.execute("DELETE FROM league_ges_result_queue WHERE guild_id=?", (int(guild_id),))

        if "competition_id" in goal_cols: conn.execute("DELETE FROM league_goal_events WHERE competition_id=?", (cid,))
        elif old_source_ids:
            placeholders = ",".join("?" for _ in old_source_ids)
            conn.execute(f"DELETE FROM league_goal_events WHERE source_message_id IN ({placeholders})", tuple(old_source_ids))
        conn.execute("DELETE FROM league_own_goal_events WHERE competition_id=?", (cid,))
        if "competition_id" in match_cols: conn.execute("DELETE FROM league_matches WHERE competition_id=?", (cid,))
        else: conn.execute("DELETE FROM league_matches")

        if old_source_ids and _table(conn, "league_manual_reviews"):
            review_cols = _cols(conn, "league_manual_reviews")
            placeholders = ",".join("?" for _ in old_source_ids)
            if "status" in review_cols:
                bits = ["status='RESUELTO_AUDITORIA_20260903'"]
                if "resolved_at" in review_cols: bits.append("resolved_at=COALESCE(resolved_at,CURRENT_TIMESTAMP)")
                conn.execute(f"UPDATE league_manual_reviews SET {','.join(bits)} WHERE source_message_id IN ({placeholders})", tuple(old_source_ids))

        for index, ((home, away, hg, ag, scorers, own_goals), source) in enumerate(zip(AUDITED_MATCHES, selected_sources), 1):
            sid = int(source["source_message_id"]); channel_id = int(source.get("source_channel_id") or 0); author_id = int(source.get("author_id") or 0)
            created_at = str(source.get("created_at") or f"2026-09-03 00:00:{index:02d}")
            conn.execute("""INSERT INTO league_matches(source_message_id,source_channel_id,author_id,home_team,away_team,home_goals,away_goals,confidence,created_at,competition_id) VALUES(?,?,?,?,?,?,?,?,?,?)""", (sid, channel_id, author_id, home, away, int(hg), int(ag), 1.0, created_at, cid))
            for player, team, goals in scorers:
                conn.execute("""INSERT INTO league_goal_events(source_message_id,player,team,goals,confidence,created_at,competition_id) VALUES(?,?,?,?,?,?,?)""", (sid, _normalize_player_name(conn, player), team, int(goals), 1.0, created_at, cid))
            for beneficiary, goals in own_goals:
                conn.execute("""INSERT INTO league_own_goal_events(source_message_id,beneficiary_team,goals,competition_id,note,created_at) VALUES(?,?,?,?,?,?)""", (sid, beneficiary, int(goals), cid, "Gol en contra confirmado en auditoría manual; no se atribuye a jugador.", created_at))

        count = int(conn.execute("SELECT COUNT(*) AS n FROM league_matches WHERE competition_id=?", (cid,)).fetchone()["n"])
        if count != len(AUDITED_MATCHES): raise RuntimeError(f"reconcile count mismatch: {count} != {len(AUDITED_MATCHES)}")
        for row in conn.execute("SELECT source_message_id,home_team,away_team,home_goals,away_goals FROM league_matches WHERE competition_id=?", (cid,)).fetchall():
            attributed = defaultdict(int)
            for goal in conn.execute("SELECT team,SUM(goals) AS goals FROM league_goal_events WHERE source_message_id=? GROUP BY team", (int(row["source_message_id"]),)).fetchall(): attributed[str(goal["team"] or "")] += int(goal["goals"] or 0)
            for own in conn.execute("SELECT beneficiary_team,SUM(goals) AS goals FROM league_own_goal_events WHERE source_message_id=? GROUP BY beneficiary_team", (int(row["source_message_id"]),)).fetchall(): attributed[str(own["beneficiary_team"] or "")] += int(own["goals"] or 0)
            if attributed[str(row["home_team"])] != int(row["home_goals"]) or attributed[str(row["away_team"])] != int(row["away_goals"]): raise RuntimeError(f"goal attribution mismatch source={row['source_message_id']}")

        conn.execute("""INSERT INTO league_authoritative_reconcile_state(marker,competition_id,match_count,db_applied_at,note) VALUES(?,?,?,CURRENT_TIMESTAMP,?) ON CONFLICT(marker) DO UPDATE SET competition_id=excluded.competition_id,match_count=excluded.match_count,db_applied_at=COALESCE(league_authoritative_reconcile_state.db_applied_at,CURRENT_TIMESTAMP),note=excluded.note""", (MARKER, cid, len(AUDITED_MATCHES), "77 fotos únicas auditadas; 38 resultados oficiales; 3 goles en contra sin jugador."))
        conn.commit()
        print(f"AJAP authoritative audit DB applied: guild={guild_id} competition={cid} matches={count}")
        return True, cid
    except Exception:
        if conn.in_transaction: conn.rollback()
        raise
    finally:
        conn.close()


def _active_cid(conn):
    try: row = conn.execute("SELECT phase,competition_id FROM competition_cycle_state WHERE id=1 LIMIT 1").fetchone()
    except Exception: return None
    if not row or str(row["phase"] or "") not in cycle.PLAYABLE or row["competition_id"] is None: return None
    return int(row["competition_id"])


def _standings_current(conn):
    teams = list(dict.fromkeys(list(league.TEAMS) + [m[0] for m in AUDITED_MATCHES] + [m[1] for m in AUDITED_MATCHES]))
    table = {team: {"team": team, "pj": 0, "pg": 0, "pe": 0, "pp": 0, "gf": 0, "gc": 0, "pts": 0} for team in teams}
    cid = _active_cid(conn)
    rows = conn.execute("SELECT home_team,away_team,home_goals,away_goals FROM league_matches WHERE competition_id=?", (cid,)).fetchall() if cid is not None and "competition_id" in _cols(conn, "league_matches") else conn.execute("SELECT home_team,away_team,home_goals,away_goals FROM league_matches").fetchall()
    for row in rows:
        home, away = str(row["home_team"]), str(row["away_team"])
        if home not in table: table[home] = {"team": home, "pj": 0, "pg": 0, "pe": 0, "pp": 0, "gf": 0, "gc": 0, "pts": 0}
        if away not in table: table[away] = {"team": away, "pj": 0, "pg": 0, "pe": 0, "pp": 0, "gf": 0, "gc": 0, "pts": 0}
        hg, ag = int(row["home_goals"]), int(row["away_goals"]); h, a = table[home], table[away]
        h["pj"] += 1; a["pj"] += 1; h["gf"] += hg; h["gc"] += ag; a["gf"] += ag; a["gc"] += hg
        if hg > ag: h["pg"] += 1; a["pp"] += 1; h["pts"] += 3
        elif ag > hg: a["pg"] += 1; h["pp"] += 1; a["pts"] += 3
        else: h["pe"] += 1; a["pe"] += 1; h["pts"] += 1; a["pts"] += 1
    rows = list(table.values()); rows.sort(key=lambda x: (-x["pts"], -(x["gf"] - x["gc"]), -x["gf"], -x["pg"], league.norm(x["team"])))
    return rows[:24]


def _scorers_embed_current(conn):
    cid = _active_cid(conn)
    if cid is not None and "competition_id" in _cols(conn, "league_goal_events"):
        rows = conn.execute("SELECT player,team,SUM(goals) AS goals FROM league_goal_events WHERE competition_id=? GROUP BY player COLLATE NOCASE,COALESCE(team,'') COLLATE NOCASE ORDER BY goals DESC,player COLLATE NOCASE ASC LIMIT 30", (cid,)).fetchall()
    else:
        rows = conn.execute("SELECT player,team,SUM(goals) AS goals FROM league_goal_events GROUP BY player COLLATE NOCASE,COALESCE(team,'') COLLATE NOCASE ORDER BY goals DESC,player COLLATE NOCASE ASC LIMIT 30").fetchall()
    if rows:
        lines = []
        for i, row in enumerate(rows, 1):
            club = f" — {row['team']}" if row["team"] else ""
            lines.append(f"**{i}. {row['player']}**{club} • ⚽ {int(row['goals'])}")
        desc = "\n".join(lines)
    else:
        desc = "Todavía no hay goles registrados."
    embed = discord.Embed(title="⚽ Tabla de goleadores", description=desc)
    embed.set_footer(text="Pretemporada actual • goles en contra no se atribuyen a jugadores")
    return embed


league.standings = _standings_current
league.scorers_embed = _scorers_embed_current
_BASE_SCORER_ROWS = ges_details._scorer_rows


def _ges_scorer_rows_with_own_goals(runtime, guild_id: int, source_message_id: int):
    rows = list(_BASE_SCORER_ROWS(runtime, guild_id, source_message_id))
    if runtime is None: return rows
    conn = league.db(runtime, int(guild_id))
    try:
        if not _table(conn, "league_own_goal_events"): return rows
        own = conn.execute("SELECT beneficiary_team AS team,SUM(goals) AS goals FROM league_own_goal_events WHERE source_message_id=? GROUP BY beneficiary_team COLLATE NOCASE", (int(source_message_id),)).fetchall()
        rows.extend({"player": "Gol en contra", "team": str(row["team"]), "goals": int(row["goals"] or 0)} for row in own)
        return rows
    finally: conn.close()


ges_details._scorer_rows = _ges_scorer_rows_with_own_goals
_BASE_PENDING_TOTALS = scorer_pending._totals


def _pending_totals_with_own_goals(runtime, guild_id, source_id):
    totals = dict(_BASE_PENDING_TOTALS(runtime, guild_id, source_id))
    conn = league.db(runtime, int(guild_id))
    try:
        if _table(conn, "league_own_goal_events"):
            for row in conn.execute("SELECT beneficiary_team,SUM(goals) AS goals FROM league_own_goal_events WHERE source_message_id=? GROUP BY beneficiary_team COLLATE NOCASE", (int(source_id),)).fetchall():
                team = str(row["beneficiary_team"] or ""); totals[team] = int(totals.get(team, 0)) + int(row["goals"] or 0)
    finally: conn.close()
    return totals


scorer_pending._totals = _pending_totals_with_own_goals
_BASE_GES_EMBED = ges_details._BASE_GES_EMBED


def _ges_base_without_fake_origin(guild, row, actor=None):
    embed = _BASE_GES_EMBED(guild, row, actor)
    try: synthetic = int(row["source_message_id"]) <= 0 or int(row["source_channel_id"] or 0) <= 0
    except Exception: synthetic = False
    if synthetic:
        for index in range(len(embed.fields) - 1, -1, -1):
            if str(embed.fields[index].name).casefold() == "origen": embed.remove_field(index)
    return embed


ges_details._BASE_GES_EMBED = _ges_base_without_fake_origin


def _ges_state(runtime, guild_id):
    conn = league.db(runtime, int(guild_id))
    try:
        _ensure_reconcile_schema(conn)
        return conn.execute("SELECT * FROM league_authoritative_reconcile_state WHERE marker=?", (MARKER,)).fetchone()
    finally: conn.close()


def _mark_ges_done(runtime, guild_id):
    conn = league.db(runtime, int(guild_id))
    try:
        _ensure_reconcile_schema(conn); conn.execute("UPDATE league_authoritative_reconcile_state SET ges_applied_at=CURRENT_TIMESTAMP WHERE marker=?", (MARKER,)); conn.commit()
    finally: conn.close()


async def _purge_channel(channel):
    deleted = 0
    async for message in channel.history(limit=None, oldest_first=False):
        try: await message.delete(); deleted += 1
        except Exception as exc: print(f"AJAP GES cleanup: could not delete message={getattr(message,'id','?')}: {type(exc).__name__}: {exc}")
    return deleted


async def _rebuild_ges(runtime, bot, guild):
    state = _ges_state(runtime, guild.id)
    if not state or not state["db_applied_at"] or state["ges_applied_at"]: return False
    channel_id = ges._get_channel_id(runtime, guild.id)
    if not channel_id:
        print("AJAP authoritative audit: GES channel not configured; DB is already canonical"); return False
    channel = guild.get_channel(int(channel_id))
    if channel is None:
        try: channel = await bot.fetch_channel(int(channel_id))
        except Exception: channel = None
    if not isinstance(channel, discord.TextChannel):
        print("AJAP authoritative audit: configured GES destination is not a text channel"); return False

    conn = ges._conn(runtime, guild.id)
    try: conn.execute("DELETE FROM league_ges_result_queue WHERE guild_id=?", (int(guild.id),)); conn.commit()
    finally: conn.close()
    deleted = await _purge_channel(channel)
    header = discord.Embed(title="✅ RESULTADOS OFICIALES • PRETEMPORADA", description="Auditoría cerrada al **03/09/2026**.\n**38 partidos oficiales** reconstruidos desde las capturas verificadas.\nLos **3 goles en contra** cuentan en el marcador pero no en la tabla de goleadores.", color=discord.Color.green())
    header.set_footer(text="AJPA • Fuente oficial para carga en GES")
    await channel.send(embed=header, allowed_mentions=discord.AllowedMentions.none())

    db = league.db(runtime, guild.id)
    try: rows = db.execute("SELECT * FROM league_matches WHERE competition_id=? ORDER BY id ASC", (int(state["competition_id"]),)).fetchall()
    finally: db.close()
    if len(rows) != len(AUDITED_MATCHES): raise RuntimeError(f"GES rebuild aborted: expected 38 canonical matches, got {len(rows)}")
    for row in rows: await ges._send(runtime, guild.id, row, str(row["home_team"]), str(row["away_team"]), int(row["home_goals"]), int(row["away_goals"]))

    conn = ges._conn(runtime, guild.id)
    try: published = int(conn.execute("SELECT COUNT(*) AS n FROM league_ges_result_queue WHERE guild_id=? AND ges_message_id IS NOT NULL", (int(guild.id),)).fetchone()["n"])
    finally: conn.close()
    if published != len(AUDITED_MATCHES): raise RuntimeError(f"GES rebuild incomplete: {published}/{len(AUDITED_MATCHES)}")
    _mark_ges_done(runtime, guild.id)
    print(f"AJAP authoritative GES rebuilt: deleted={deleted} published={published}")
    return True


async def _run_authoritative_reconcile():
    if APP is None or BOT is None: return
    guild = BOT.get_guild(TARGET_GUILD_ID)
    if guild is None: return
    try:
        changed, _cid = _rebuild_database(APP, guild.id)
        if changed:
            try: await league.refresh(APP, BOT, guild.id)
            except Exception as exc: print(f"WARNING AJAP authoritative table refresh: {type(exc).__name__}: {exc}")
        await _rebuild_ges(APP, BOT, guild)
    except Exception as exc:
        print(f"ERROR AJAP authoritative audit reconcile: {type(exc).__name__}: {exc}")


def _install(runtime, bot):
    global APP, BOT
    APP, BOT = runtime, bot
    if getattr(runtime, "_ajap_authoritative_audit_reconcile", False): return
    if not getattr(bot, "_ajap_authoritative_audit_listener", False):
        bot.add_listener(_run_authoritative_reconcile, "on_ready"); bot._ajap_authoritative_audit_listener = True
    runtime._ajap_authoritative_audit_reconcile = True
    print("AJAP authoritative audit armed: 38 resultados + goleadores + GES clean rebuild")


_PREVIOUS = guild_isolation.apply_guild_isolation_patch


def _apply(runtime, bot):
    _PREVIOUS(runtime, bot)
    _install(runtime, bot)


if not getattr(guild_isolation.apply_guild_isolation_patch, "_ajap_authoritative_audit_wrapper", False):
    _apply._ajap_authoritative_audit_wrapper = True
    guild_isolation.apply_guild_isolation_patch = _apply
