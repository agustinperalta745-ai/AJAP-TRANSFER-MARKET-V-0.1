"""One-time clean reset for the official AJAP Transfer Market V1 launch."""

from __future__ import annotations

from collections import defaultdict
import json
from pathlib import Path

import guild_isolation_patch as guild_isolation

RESET_KEY = "ajap_v1_official_launch_reset_20260828"
DATA_DIR = Path(__file__).resolve().parent / "data"

# Only market/test state. DT assignments and channel/config tables are preserved.
CLEAR_TABLES = (
    "public_market_announcements",
    "treasury_transactions",
    "loan_canon_dues",
    "loan_canon_payments",
    "loan_option_payments",
    "loans",
    "clause_requests",
    "player_releases",
    "player_history",
    "transfers",
    "offers",
    "publications",
    "market_cycles",
    "market_state_history",
)


def _table_exists(conn, name):
    return bool(conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1", (name,)
    ).fetchone())


def _payloads():
    for path in sorted(DATA_DIR.glob("*.json")):
        try:
            yield path.name, json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            print(f"WARNING AJAP RESET V1: {path.name}: {type(exc).__name__}: {exc}")

    parts = sorted(DATA_DIR.glob("Galatasaray.json.part*"))
    if parts:
        try:
            raw = "".join(path.read_text(encoding="utf-8") for path in parts)
            yield "Galatasaray.json", json.loads(raw)
        except Exception as exc:
            print(
                "WARNING AJAP RESET V1: Galatasaray.json: "
                f"{type(exc).__name__}: {exc}"
            )


def _origins():
    origins = {}
    ambiguous = set()
    for source, payload in _payloads():
        club = str(payload.get("equipo") or "").strip()
        players = payload.get("jugadores") or []
        if not club or not isinstance(players, list):
            print(f"WARNING AJAP RESET V1: {source} sin equipo/jugadores válidos")
            continue
        for item in players:
            if not isinstance(item, dict):
                continue
            name = str(item.get("nombre") or "").strip()
            if not name:
                continue
            key = name.casefold()
            prior = origins.get(key)
            if prior and prior[1].casefold() != club.casefold():
                ambiguous.add(key)
                print(
                    f"WARNING AJAP RESET V1: {name} aparece en "
                    f"{prior[1]} y {club}; se omite"
                )
                continue
            origins[key] = (name, club)
    for key in ambiguous:
        origins.pop(key, None)
    return origins


def _reverse_market_finances(conn):
    """Undo cash effects created by clauses, loans and paid player releases."""
    if not _table_exists(conn, "club_finances"):
        return 0

    delta = defaultdict(int)

    if _table_exists(conn, "loan_canon_payments"):
        cols = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(loan_canon_payments)").fetchall()
        }
        where = "WHERE status='PAID'" if "status" in cols else ""
        for row in conn.execute(
            "SELECT payer_club,payee_club,amount FROM loan_canon_payments " + where
        ).fetchall():
            amount = int(row["amount"] or 0)
            delta[str(row["payer_club"])] += amount
            delta[str(row["payee_club"])] -= amount

    if _table_exists(conn, "loan_option_payments"):
        for row in conn.execute(
            "SELECT buyer_club,seller_club,amount FROM loan_option_payments"
        ).fetchall():
            amount = int(row["amount"] or 0)
            delta[str(row["buyer_club"])] += amount
            delta[str(row["seller_club"])] -= amount

    if _table_exists(conn, "clause_requests"):
        for row in conn.execute(
            "SELECT buyer_club,seller_club,amount,status FROM clause_requests"
        ).fetchall():
            amount = int(row["amount"] or 0)
            status = str(row["status"] or "").upper()
            if status == "PENDIENTE_STAFF":
                delta[str(row["buyer_club"])] += amount
            elif status == "APROBADO":
                delta[str(row["buyer_club"])] += amount
                delta[str(row["seller_club"])] -= amount

    if _table_exists(conn, "player_releases"):
        for row in conn.execute(
            "SELECT from_club, release_cost FROM player_releases"
        ).fetchall():
            amount = int(row["release_cost"] or 0)
            delta[str(row["from_club"])] += amount

    changed = 0
    for club, amount in delta.items():
        if not club or not amount:
            continue
        conn.execute(
            "INSERT OR IGNORE INTO club_finances (club,balance) VALUES (?,0)", (club,)
        )
        conn.execute(
            "UPDATE club_finances SET balance=balance+?, updated_at=CURRENT_TIMESTAMP "
            "WHERE club=? COLLATE NOCASE",
            (int(amount), club),
        )
        changed += 1
    return changed


def _reset(conn, guild_id, *, force=False, admin_id=None):
    conn.execute(
        "CREATE TABLE IF NOT EXISTS launch_reset_state ("
        "key TEXT PRIMARY KEY, guild_id INTEGER, "
        "applied_at DATETIME DEFAULT CURRENT_TIMESTAMP)"
    )
    already_applied = conn.execute(
        "SELECT 1 FROM launch_reset_state WHERE key=? LIMIT 1", (RESET_KEY,)
    ).fetchone()
    if already_applied and not force:
        return False, {}

    if not _table_exists(conn, "roster_players"):
        raise RuntimeError("roster_players no existe")

    origins = _origins()
    if not origins:
        raise RuntimeError("no se pudo construir el mapa de origen JSON")

    restored = 0
    for name, club in origins.values():
        cur = conn.execute(
            "UPDATE roster_players SET club=?, updated_at=CURRENT_TIMESTAMP "
            "WHERE name=? COLLATE NOCASE",
            (club, name),
        )
        restored += int(cur.rowcount or 0)

    finance_changes = _reverse_market_finances(conn)

    cleared = 0
    for table in CLEAR_TABLES:
        if _table_exists(conn, table):
            conn.execute(f'DELETE FROM "{table}"')
            cleared += 1

    # DELETE vacía market_cycles, pero SQLite conserva el AUTOINCREMENT en
    # sqlite_sequence. Un reset total debe hacer que la próxima apertura sea
    # nuevamente Ventana #1, no continuar #4, #5, etc.
    if _table_exists(conn, "sqlite_sequence"):
        conn.execute("DELETE FROM sqlite_sequence WHERE name='market_cycles'")

    if _table_exists(conn, "market_state"):
        conn.execute(
            "INSERT INTO market_state (id,is_open,updated_by,updated_at) "
            "VALUES (1,0,NULL,CURRENT_TIMESTAMP) "
            "ON CONFLICT(id) DO UPDATE SET is_open=0,updated_by=NULL,"
            "updated_at=CURRENT_TIMESTAMP"
        )

    conn.execute(
        "INSERT OR IGNORE INTO launch_reset_state (key,guild_id) VALUES (?,?)",
        (RESET_KEY, int(guild_id)),
    )

    if force:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS manual_reset_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                admin_id INTEGER,
                players_restored INTEGER NOT NULL,
                tables_cleared INTEGER NOT NULL,
                finance_accounts_reverted INTEGER NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            INSERT INTO manual_reset_history
            (guild_id, admin_id, players_restored, tables_cleared, finance_accounts_reverted)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                int(guild_id),
                int(admin_id) if admin_id is not None else None,
                int(restored),
                int(cleared),
                int(finance_changes),
            ),
        )

    conn.commit()
    return True, {
        "players": restored,
        "tables": cleared,
        "finances": finance_changes,
    }


def manual_reset_current_guild(runtime, guild_id: int, admin_id: int):
    """Run the same clean reset on demand for one guild, even if launch reset ran."""
    guild_id = int(guild_id)
    with runtime.guild_context(guild_id):
        # Opening runtime.db triggers all JSON roster synchronizers first.
        with runtime.db() as conn:
            applied, stats = _reset(
                conn,
                guild_id,
                force=True,
                admin_id=int(admin_id),
            )
    print(
        "AJAP RESET V1 MANUAL aplicado: "
        f"guild={guild_id} • admin={admin_id} • jugadores={stats['players']} • "
        f"tablas={stats['tables']} • finanzas_revertidas={stats['finances']}"
    )
    return applied, stats


def apply_v1_official_reset(runtime, bot):
    if getattr(runtime, "_ajap_v1_official_reset", False):
        return

    async def reset_official_guilds():
        for guild in list(getattr(bot, "guilds", []) or []):
            # Keep the historical test server intact. The official server(s)
            # introduced after guild isolation are the ones being launched clean.
            if int(guild.id) == int(guild_isolation.LEGACY_GUILD_ID):
                print(f"AJAP RESET V1: guild de pruebas preservado ({guild.id})")
                continue
            try:
                with runtime.guild_context(int(guild.id)):
                    # Opening runtime.db triggers all JSON roster synchronizers first.
                    with runtime.db() as conn:
                        applied, stats = _reset(conn, int(guild.id))
                if applied:
                    print(
                        "AJAP RESET V1 OFICIAL aplicado: "
                        f"guild={guild.id} • jugadores={stats['players']} • "
                        f"tablas={stats['tables']} • "
                        f"finanzas_revertidas={stats['finances']}"
                    )
                else:
                    print(f"AJAP RESET V1 ya aplicado: guild={guild.id}")
            except Exception as exc:
                # Maintenance must never take the bot down.
                print(
                    "WARNING AJAP RESET V1: "
                    f"guild={getattr(guild, 'id', '?')} "
                    f"{type(exc).__name__}: {exc}"
                )

    bot.add_listener(reset_official_guilds, "on_ready")
    runtime._ajap_v1_official_reset = True
    print(
        "AJAP RESET V1 armado: JSON de origen + limpieza de pruebas + "
        "mercado cerrado, una sola vez por servidor oficial"
    )
