"""Manual authoritative GES -> AJPA synchronization.

GES is the competitive source of truth. Nothing in this module watches Discord
messages: synchronization only runs when an authenticated Staff user presses
"GES actualizada" in AJPA Mobile.
"""

from __future__ import annotations

import asyncio
import hashlib
import html
import os
import re
import threading
import unicodedata
import urllib.request
from html.parser import HTMLParser
from http import HTTPStatus
from urllib.parse import urlparse

import discord

import league_automation_patch as league

GES_LEAGUE_ID = (os.getenv("AJPA_GES_LEAGUE_ID") or "511502").strip()
GES_CLASSIFICATION_URL = (
    os.getenv("AJPA_GES_CLASSIFICATION_URL")
    or f"https://www.gesliga.com/Clasificacion.aspx?Liga={GES_LEAGUE_ID}"
).strip()
GES_SCORERS_URL = (
    os.getenv("AJPA_GES_SCORERS_URL")
    or f"https://www.gesliga.com/Estadisticas.aspx?Liga={GES_LEAGUE_ID}"
).strip()

_RUNTIME = None
_BOT = None
_LOOP = None
_SYNC_LOCK = threading.Lock()
_BASE_STANDINGS = league.standings
_BASE_STANDINGS_EMBED = league.standings_embed
_BASE_SCORERS_EMBED = league.scorers_embed


class _TableParser(HTMLParser):
    """Small dependency-free table parser suitable for GES' server HTML."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tables: list[list[list[str]]] = []
        self._table_depth = 0
        self._rows: list[list[str]] | None = None
        self._row: list[str] | None = None
        self._cell: list[str] | None = None

    def handle_starttag(self, tag, attrs):
        tag = tag.casefold()
        if tag == "table":
            self._table_depth += 1
            if self._table_depth == 1:
                self._rows = []
        elif self._table_depth == 1 and tag == "tr":
            self._row = []
        elif self._table_depth == 1 and tag in {"td", "th"}:
            self._cell = []
        elif self._cell is not None and tag in {"br", "p", "div"}:
            self._cell.append(" ")

    def handle_endtag(self, tag):
        tag = tag.casefold()
        if self._table_depth == 1 and tag in {"td", "th"} and self._cell is not None:
            value = re.sub(r"\s+", " ", "".join(self._cell)).strip()
            if self._row is not None:
                self._row.append(value)
            self._cell = None
        elif self._table_depth == 1 and tag == "tr" and self._row is not None:
            if any(cell.strip() for cell in self._row):
                assert self._rows is not None
                self._rows.append(self._row)
            self._row = None
        elif tag == "table" and self._table_depth:
            if self._table_depth == 1 and self._rows is not None:
                if self._rows:
                    self.tables.append(self._rows)
                self._rows = None
            self._table_depth -= 1

    def handle_data(self, data):
        if self._cell is not None:
            self._cell.append(data)


def _norm(value: str) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", " ", text.casefold()).strip()


def _clean_ges_team(label: str) -> str:
    text = html.unescape(str(label or "")).replace("\xa0", " ").strip()
    # GES renders "Club - DT". Team hyphens (Paris Saint-Germain) have no
    # surrounding spaces, so splitting on a manager separator is safe.
    text = re.split(r"\s+-\s*", text, maxsplit=1)[0].strip()
    return text


def _canonical_team(label: str) -> str | None:
    clean = _clean_ges_team(label)
    aliases = {
        "paris saint germain": "París Saint-Germain (PSG)",
        "psg": "París Saint-Germain (PSG)",
        "atletico madrid": "Atlético de Madrid",
        "marsella": "Olympique de Marsella",
        "olympique de marsella": "Olympique de Marsella",
        "lyon": "Olympique de Lyon",
        "olympique lyon": "Olympique de Lyon",
        "olympique de lyon": "Olympique de Lyon",
    }
    key = _norm(clean)
    if key in aliases:
        return aliases[key]
    exact = {_norm(name): name for name in league.TEAMS}
    return exact.get(key)


def _fetch(url: str) -> str:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "AJPA-GES-Sync/1.0 (+manual staff sync)",
            "Accept": "text/html,application/xhtml+xml",
        },
        method="GET",
    )
    with urllib.request.urlopen(req, timeout=25) as response:
        charset = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(charset, "replace")


def _tables(page: str) -> list[list[list[str]]]:
    parser = _TableParser()
    parser.feed(page)
    return parser.tables


def _to_int(value: str) -> int | None:
    value = str(value or "").strip().replace("+", "")
    return int(value) if re.fullmatch(r"-?\d+", value) else None


def _parse_standings(tables: list[list[list[str]]]) -> tuple[list[dict], list[str]]:
    warnings: list[str] = []
    found: list[dict] = []
    for table in tables:
        for row in table:
            cells = [re.sub(r"\s+", " ", c).strip() for c in row if c is not None]
            if len(cells) < 9:
                continue
            # A standings row ends in Pt/PJ/PG/PE/PP/GF/GC/DG. Depending on the
            # crest cell, GES may expose one additional empty cell before team.
            nums = [_to_int(c) for c in cells]
            numeric_indices = [i for i, n in enumerate(nums) if n is not None]
            if len(numeric_indices) < 9:
                continue
            pos_idx = numeric_indices[0]
            tail = [nums[i] for i in numeric_indices[-8:]]
            if any(v is None for v in tail):
                continue
            team_candidates = [
                c for i, c in enumerate(cells)
                if i > pos_idx and i < numeric_indices[-8] and c and _to_int(c) is None
            ]
            if not team_candidates:
                continue
            raw_team = max(team_candidates, key=len)
            team = _canonical_team(raw_team)
            if not team:
                warnings.append(f"Equipo de tabla sin vincular: {raw_team}")
                continue
            position = nums[pos_idx]
            if position is None:
                continue
            pt, pj, pg, pe, pp, gf, gc, dg = [int(v) for v in tail]
            found.append({
                "position": int(position), "team": team, "pts": pt, "pj": pj,
                "pg": pg, "pe": pe, "pp": pp, "gf": gf, "gc": gc, "dg": dg,
            })
    # De-duplicate because responsive GES markup may contain the same table twice.
    unique: dict[str, dict] = {}
    for row in found:
        unique.setdefault(row["team"], row)
    rows = sorted(unique.values(), key=lambda r: (r["position"], _norm(r["team"])))
    if len(rows) < 2:
        raise RuntimeError("GES no devolvió una tabla de posiciones reconocible.")
    return rows, warnings


def _parse_matches(tables: list[list[list[str]]]) -> tuple[list[dict], list[str]]:
    warnings: list[str] = []
    out: dict[tuple[str, str], dict] = {}
    score_re = re.compile(r"^\s*(\d{1,2})\s*[-–—]\s*(\d{1,2})\s*$")
    for table in tables:
        for row in table:
            cells = [re.sub(r"\s+", " ", c).strip() for c in row]
            for index, cell in enumerate(cells):
                match = score_re.match(cell)
                if not match:
                    continue
                left = [c for c in cells[:index] if c]
                right = [c for c in cells[index + 1:] if c]
                if not left or not right:
                    continue
                raw_home, raw_away = left[-1], right[0]
                home, away = _canonical_team(raw_home), _canonical_team(raw_away)
                if not home or not away:
                    warnings.append(f"Partido sin vincular: {raw_home} {cell} {raw_away}")
                    continue
                if home == away:
                    continue
                hg, ag = int(match.group(1)), int(match.group(2))
                out[(home, away)] = {
                    "home_team": home, "away_team": away,
                    "home_goals": hg, "away_goals": ag,
                }
    return list(out.values()), warnings


def _parse_scorers(tables: list[list[list[str]]]) -> tuple[list[dict], list[str]]:
    warnings: list[str] = []
    found: dict[tuple[str, str], dict] = {}
    for table in tables:
        for row in table:
            cells = [re.sub(r"\s+", " ", c).strip() for c in row if c.strip()]
            if len(cells) < 2:
                continue
            goals_idx = next((i for i in range(len(cells) - 1, -1, -1) if _to_int(cells[i]) is not None), None)
            if goals_idx is None:
                continue
            goals = _to_int(cells[goals_idx])
            if goals is None or goals <= 0 or goals > 200:
                continue
            textual = [c for i, c in enumerate(cells) if i != goals_idx and _to_int(c) is None]
            if not textual:
                continue
            player = textual[0].strip()
            if _norm(player) in {"jugador", "goleador", "nombre", "total"}:
                continue
            raw_team = textual[1].strip() if len(textual) > 1 else ""
            team = _canonical_team(raw_team) if raw_team else None
            if raw_team and not team:
                # Ignore obvious column headings but keep scorer with a warning.
                if _norm(raw_team) not in {"equipo", "club"}:
                    warnings.append(f"Club de goleador sin vincular: {player} — {raw_team}")
            key = (_norm(player), _norm(team or raw_team))
            if not key[0]:
                continue
            found[key] = {"player": player[:100], "team": team or raw_team[:100], "goals": int(goals)}
    rows = sorted(found.values(), key=lambda r: (-r["goals"], _norm(r["player"])))
    if not rows:
        raise RuntimeError("GES no devolvió una tabla de goleadores reconocible.")
    return rows, warnings


def _ensure_schema(conn) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS league_ges_standings (
            guild_id INTEGER NOT NULL,
            league_id TEXT NOT NULL,
            position INTEGER NOT NULL,
            team TEXT NOT NULL,
            pts INTEGER NOT NULL, pj INTEGER NOT NULL, pg INTEGER NOT NULL,
            pe INTEGER NOT NULL, pp INTEGER NOT NULL, gf INTEGER NOT NULL,
            gc INTEGER NOT NULL, dg INTEGER NOT NULL,
            updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (guild_id, league_id, team)
        );
        CREATE TABLE IF NOT EXISTS league_ges_scorers (
            guild_id INTEGER NOT NULL,
            league_id TEXT NOT NULL,
            player TEXT NOT NULL,
            team TEXT NOT NULL DEFAULT '',
            goals INTEGER NOT NULL,
            updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (guild_id, league_id, player, team)
        );
        CREATE TABLE IF NOT EXISTS league_ges_sync_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            guild_id INTEGER NOT NULL,
            league_id TEXT NOT NULL,
            staff_user_id INTEGER,
            standings_count INTEGER NOT NULL,
            matches_new INTEGER NOT NULL,
            matches_updated INTEGER NOT NULL,
            scorers_count INTEGER NOT NULL,
            warning_count INTEGER NOT NULL,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """
    )
    conn.commit()


def _source_id(home: str, away: str) -> int:
    digest = hashlib.sha256(f"GES|{GES_LEAGUE_ID}|{_norm(home)}|{_norm(away)}".encode()).digest()
    # Negative IDs can never collide with Discord snowflakes.
    return -(int.from_bytes(digest[:7], "big") or 1)


def _ges_standings(conn):
    try:
        rows = conn.execute(
            """SELECT position,team,pts,pj,pg,pe,pp,gf,gc,dg
               FROM league_ges_standings WHERE league_id=?
               ORDER BY position ASC, team COLLATE NOCASE ASC""",
            (GES_LEAGUE_ID,),
        ).fetchall()
    except Exception:
        rows = []
    if not rows:
        return _BASE_STANDINGS(conn)
    return [dict(row) for row in rows]


def _ges_standings_embed(conn):
    rows = _ges_standings(conn)
    lines = []
    for row in rows:
        pos = int(row.get("position") or (len(lines) + 1))
        lines.append(
            f"**P{pos}** — {row['team']} • **{row['pts']} pts** • "
            f"PJ {row['pj']} | {row['pg']}-{row['pe']}-{row['pp']} | "
            f"GF {row['gf']} GC {row['gc']} ({int(row.get('dg', row['gf']-row['gc'])):+d})"
        )
    embed = discord.Embed(title="🏆 Tabla de posiciones", description="\n".join(lines) or "Todavía no hay equipos.")
    embed.set_footer(text="Fuente oficial: GES • Actualización manual desde Administración AJPA")
    return embed


def _ges_scorers_embed(conn):
    try:
        rows = conn.execute(
            """SELECT player,team,goals FROM league_ges_scorers
               WHERE league_id=? ORDER BY goals DESC, player COLLATE NOCASE ASC LIMIT 30""",
            (GES_LEAGUE_ID,),
        ).fetchall()
    except Exception:
        rows = []
    if not rows:
        return _BASE_SCORERS_EMBED(conn)
    lines = []
    for i, row in enumerate(rows, 1):
        club = f" — {row['team']}" if row["team"] else ""
        lines.append(f"**{i}. {row['player']}**{club} • ⚽ {row['goals']}")
    embed = discord.Embed(title="⚽ Tabla de goleadores", description="\n".join(lines))
    embed.set_footer(text="Fuente oficial: GES • Actualización manual desde Administración AJPA")
    return embed


def _patch_views() -> None:
    league.standings = _ges_standings
    league.standings_embed = _ges_standings_embed
    league.scorers_embed = _ges_scorers_embed
    try:
        import league_top5_scorers_radio_patch as top_scorers

        def top5(runtime, guild_id: int):
            conn = league.db(runtime, int(guild_id))
            try:
                _ensure_schema(conn)
                rows = conn.execute(
                    """SELECT player,team,goals FROM league_ges_scorers
                       WHERE guild_id=? AND league_id=?
                       ORDER BY goals DESC, player COLLATE NOCASE ASC LIMIT 5""",
                    (int(guild_id), GES_LEAGUE_ID),
                ).fetchall()
                if rows:
                    try:
                        import competition_cycle as cycle
                        cid = cycle.active_competition_id(conn)
                    except Exception:
                        cid = None
                    return cid, [dict(row) for row in rows]
            finally:
                conn.close()
            return top_scorers._BASE_TOP5_SCORERS(runtime, guild_id) if hasattr(top_scorers, "_BASE_TOP5_SCORERS") else (None, [])

        if not hasattr(top_scorers, "_BASE_TOP5_SCORERS"):
            top_scorers._BASE_TOP5_SCORERS = top_scorers._top5_scorers
        top_scorers._top5_scorers = top5
    except Exception as exc:
        print(f"AJPA GES: Top 5 goleadores seguirá usando fallback: {exc}")


async def _refresh_downstream(runtime, bot, guild_id: int, changed_sources: list[int]) -> list[str]:
    warnings: list[str] = []
    try:
        await league.refresh(runtime, bot, int(guild_id))
    except Exception as exc:
        warnings.append(f"No se pudo refrescar el panel de Liga: {exc}")

    guild = bot.get_guild(int(guild_id))
    if guild is not None:
        try:
            import classic_result_radio_patch as classics
            for source_id in changed_sources:
                try:
                    await classics.publish_for_source(runtime, bot, guild, int(source_id))
                except Exception as exc:
                    warnings.append(f"Clásico {source_id}: {exc}")
        except Exception as exc:
            warnings.append(f"Radio Pasillo clásicos no disponible: {exc}")

    # Existing daily/radio modules hook league.refresh in this codebase. Calling
    # the final wrapped refresh above is the single supported refresh trigger and
    # therefore also lets those consumers re-read the now-authoritative DB.
    return warnings


async def sync_from_ges(runtime, bot, guild_id: int, staff_user_id: int | None = None) -> dict:
    if not _SYNC_LOCK.acquire(blocking=False):
        raise RuntimeError("Ya hay una sincronización GES en curso.")
    try:
        classification_html, scorers_html = await asyncio.gather(
            asyncio.to_thread(_fetch, GES_CLASSIFICATION_URL),
            asyncio.to_thread(_fetch, GES_SCORERS_URL),
        )
        classification_tables = _tables(classification_html)
        scorer_tables = _tables(scorers_html)
        standings, warnings_a = _parse_standings(classification_tables)
        matches, warnings_b = _parse_matches(classification_tables)
        scorers, warnings_c = _parse_scorers(scorer_tables)
        warnings = list(dict.fromkeys(warnings_a + warnings_b + warnings_c))

        conn = league.db(runtime, int(guild_id))
        changed_sources: list[int] = []
        matches_new = 0
        matches_updated = 0
        try:
            _ensure_schema(conn)
            conn.execute("BEGIN IMMEDIATE")
            conn.execute("DELETE FROM league_ges_standings WHERE guild_id=? AND league_id=?", (int(guild_id), GES_LEAGUE_ID))
            for row in standings:
                conn.execute(
                    """INSERT INTO league_ges_standings
                       (guild_id,league_id,position,team,pts,pj,pg,pe,pp,gf,gc,dg)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (int(guild_id), GES_LEAGUE_ID, row["position"], row["team"], row["pts"], row["pj"], row["pg"], row["pe"], row["pp"], row["gf"], row["gc"], row["dg"]),
                )

            for item in matches:
                existing = conn.execute(
                    """SELECT id,source_message_id,home_goals,away_goals FROM league_matches
                       WHERE home_team=? AND away_team=? ORDER BY id DESC LIMIT 1""",
                    (item["home_team"], item["away_team"]),
                ).fetchone()
                if existing:
                    source_id = int(existing["source_message_id"])
                    if int(existing["home_goals"]) != item["home_goals"] or int(existing["away_goals"]) != item["away_goals"]:
                        conn.execute(
                            "UPDATE league_matches SET home_goals=?,away_goals=?,confidence=1.0 WHERE id=?",
                            (item["home_goals"], item["away_goals"], int(existing["id"])),
                        )
                        matches_updated += 1
                        changed_sources.append(source_id)
                else:
                    source_id = _source_id(item["home_team"], item["away_team"])
                    conn.execute(
                        """INSERT INTO league_matches
                           (source_message_id,source_channel_id,author_id,home_team,away_team,home_goals,away_goals,confidence)
                           VALUES(?,?,?,?,?,?,?,1.0)""",
                        (source_id, 0, int(staff_user_id or 0), item["home_team"], item["away_team"], item["home_goals"], item["away_goals"]),
                    )
                    matches_new += 1
                    changed_sources.append(source_id)

            conn.execute("DELETE FROM league_ges_scorers WHERE guild_id=? AND league_id=?", (int(guild_id), GES_LEAGUE_ID))
            for row in scorers:
                conn.execute(
                    "INSERT INTO league_ges_scorers(guild_id,league_id,player,team,goals) VALUES(?,?,?,?,?)",
                    (int(guild_id), GES_LEAGUE_ID, row["player"], row["team"] or "", row["goals"]),
                )
            conn.execute(
                """INSERT INTO league_ges_sync_runs
                   (guild_id,league_id,staff_user_id,standings_count,matches_new,matches_updated,scorers_count,warning_count)
                   VALUES(?,?,?,?,?,?,?,?)""",
                (int(guild_id), GES_LEAGUE_ID, staff_user_id, len(standings), matches_new, matches_updated, len(scorers), len(warnings)),
            )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

        warnings.extend(await _refresh_downstream(runtime, bot, int(guild_id), changed_sources))
        warnings = list(dict.fromkeys(warnings))
        return {
            "ok": True,
            "league_id": GES_LEAGUE_ID,
            "standings": len(standings),
            "matches_read": len(matches),
            "matches_new": matches_new,
            "matches_updated": matches_updated,
            "scorers": len(scorers),
            "warnings": warnings[:40],
        }
    finally:
        _SYNC_LOCK.release()


def _install_mobile_endpoint() -> None:
    import mobile_read_api
    import mobile_write_api

    handler = mobile_read_api.MobileReadHandler
    if getattr(handler, "_ajpa_ges_manual_sync_api", False):
        return
    original_post = handler.do_POST

    def post(self):
        path = urlparse(self.path).path.rstrip("/") or "/"
        if path != "/api/v1/admin/ges-sync":
            return original_post(self)
        try:
            if _RUNTIME is None or _BOT is None or _LOOP is None or not _LOOP.is_running():
                raise mobile_write_api.ApiFailure("AJPA todavía está terminando de iniciar.", HTTPStatus.SERVICE_UNAVAILABLE)
            with mobile_write_api.write_db() as conn:
                mobile_write_api.ensure_schema(conn)
                session = mobile_write_api._session(self.headers, conn)
                if not session.get("is_staff"):
                    raise mobile_write_api.ApiFailure("Esta herramienta es exclusiva para Staff.", HTTPStatus.FORBIDDEN)
            raw_guild = (os.getenv("AJPA_MOBILE_GUILD_ID") or os.getenv("DISCORD_GUILD_ID") or "").strip()
            if not raw_guild.isdigit():
                raise mobile_write_api.ApiFailure("AJPA Mobile no tiene servidor configurado.", HTTPStatus.SERVICE_UNAVAILABLE)
            future = asyncio.run_coroutine_threadsafe(
                sync_from_ges(_RUNTIME, _BOT, int(raw_guild), int(session["user_id"])),
                _LOOP,
            )
            result = future.result(timeout=60)
            self._json(result)
        except mobile_write_api.ApiFailure as exc:
            self._json({"error": "request", "message": exc.message}, exc.status)
        except Exception as exc:
            print(f"AJPA GES sync API error: {type(exc).__name__}: {exc}")
            status = HTTPStatus.CONFLICT if "curso" in str(exc).casefold() else HTTPStatus.BAD_GATEWAY
            self._json({"error": "ges_sync", "message": str(exc) or "No se pudo releer GES."}, status)

    handler.do_POST = post
    handler._ajpa_ges_manual_sync_api = True
    print("AJPA Mobile: POST /api/v1/admin/ges-sync enabled (Staff only)")


def apply_manual_ges_sync(runtime, bot) -> None:
    global _RUNTIME, _BOT
    _RUNTIME, _BOT = runtime, bot
    _patch_views()
    _install_mobile_endpoint()

    if getattr(runtime, "_ajpa_manual_ges_sync_ready", False):
        return

    async def ready_listener():
        global _LOOP
        _LOOP = asyncio.get_running_loop()

    bot.add_listener(ready_listener, "on_ready")
    runtime._ajpa_manual_ges_sync_ready = True
    print(f"AJPA GES manual sync ready • liga={GES_LEAGUE_ID} • no automatic polling")
