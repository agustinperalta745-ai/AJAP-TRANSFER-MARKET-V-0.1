"""Data consistency hardening for AJAP Transfer Market.

Every menu button must reflect the same persistent SQLite state. This patch:
- opens every SQLite connection with a generous busy timeout;
- enables WAL when the Railway volume supports it;
- retries the main list reads before showing a false empty result;
- retries short SQLite lock/contention windows instead of surfacing bad UI;
- gives Mis ofertas the same guarded read behavior;
- logs Railway service/deployment + DB counts so duplicate bot services can be
  identified immediately from logs.
"""

import asyncio
import os
import sqlite3
import time

import discord


APP = None
_ORIGINAL_DB = None


def _connect(runtime):
    conn = sqlite3.connect(
        runtime.DB_PATH,
        timeout=15.0,
        check_same_thread=False,
    )
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 15000")
    return conn


def _install_connection(runtime):
    global _ORIGINAL_DB
    _ORIGINAL_DB = runtime.db

    # Configure the persistent DB once. WAL prevents short writes from blocking
    # readers. If the filesystem does not support it, keep the normal journal
    # mode and continue: consistency protection must never stop the bot booting.
    conn = _connect(runtime)
    try:
        try:
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute("PRAGMA synchronous = NORMAL")
            conn.execute("PRAGMA wal_autocheckpoint = 1000")
        except sqlite3.Error as exc:
            print(f"WARNING AJAP: WAL no disponible, se usa journal SQLite normal: {exc}")
    finally:
        conn.close()

    runtime.db = lambda: _connect(runtime)


def _read_rows(runtime, sql, args=(), attempts=3):
    """Return a stable result, retrying empty snapshots and short lock windows."""
    best = []
    last_error = None
    for attempt in range(max(1, attempts)):
        try:
            with runtime.db() as conn:
                rows = conn.execute(sql, args).fetchall()
            if len(rows) > len(best):
                best = rows
            if rows:
                return rows
            last_error = None
        except sqlite3.OperationalError as exc:
            last_error = exc
        if attempt < attempts - 1:
            time.sleep(0.05)

    if last_error is not None:
        raise last_error
    return best


def _patch_main_readers(runtime):
    def jugadores_de_club(club: str, limit=50):
        return _read_rows(
            runtime,
            """
            SELECT * FROM roster_players
            WHERE club = ? COLLATE NOCASE
            ORDER BY position, name
            LIMIT ?
            """,
            (club.strip(), limit),
            attempts=3,
        )

    def publicaciones_activas(limit=25):
        return _read_rows(
            runtime,
            "SELECT * FROM publications WHERE active = 1 ORDER BY id DESC LIMIT ?",
            (limit,),
            attempts=3,
        )

    def operaciones_pendientes(limit=25):
        return _read_rows(
            runtime,
            """
            SELECT t.*, s.name AS season_name
            FROM transfers t
            LEFT JOIN seasons s ON s.id = t.season_id
            WHERE t.status IN ('PENDIENTE_ADMIN', 'APROBADA')
            ORDER BY t.id ASC
            LIMIT ?
            """,
            (limit,),
            attempts=3,
        )

    runtime.jugadores_de_club = jugadores_de_club
    runtime.publicaciones_activas = publicaciones_activas
    runtime.operaciones_pendientes = operaciones_pendientes


async def _read_user_offers(runtime, user_id):
    best_own = []
    best_pending = []
    last_error = None

    for attempt in range(3):
        try:
            with runtime.db() as conn:
                own = conn.execute(
                    "SELECT * FROM offers WHERE from_id = ? OR to_id = ? ORDER BY id DESC LIMIT 15",
                    (user_id, user_id),
                ).fetchall()
                pending = conn.execute(
                    "SELECT * FROM offers WHERE to_id = ? AND status = 'PENDIENTE' ORDER BY id DESC LIMIT 25",
                    (user_id,),
                ).fetchall()

            if len(own) > len(best_own):
                best_own = own
            if len(pending) > len(best_pending):
                best_pending = pending
            if own or pending:
                return own, pending
            last_error = None
        except sqlite3.OperationalError as exc:
            last_error = exc

        if attempt < 2:
            await asyncio.sleep(0.06)

    if last_error is not None:
        raise last_error
    return best_own, best_pending


def _offers_embed(offers, user_id):
    embed = discord.Embed(title="💰 Mis ofertas")
    if not offers:
        embed.description = "Todavía no tenés ofertas enviadas ni recibidas."
        return embed

    for offer in offers:
        sent = int(offer["from_id"]) == int(user_id)
        direction = "📤 Enviada" if sent else "📥 Recibida"
        icon = {
            "PENDIENTE": "🟡",
            "ACEPTADA": "🟢",
            "RECHAZADA": "🔴",
            "CANCELADA": "⚫",
            "CANCELADA_ADMIN": "⛔",
        }.get(offer["status"], "⚪")
        embed.add_field(
            name=f"{direction} • #{offer['id']} • {offer['player']}",
            value=(
                f"🔁 {offer['operation_type']} • 💵 **{offer['amount']}**\n"
                f"{icon} {offer['status']}"
            ),
            inline=False,
        )
    return embed


def _patch_market_view(runtime):
    base = runtime.MercadoView

    class ConsistentMercadoView(base):
        def __init__(self):
            super().__init__()
            for item in self.children:
                if getattr(item, "custom_id", None) == "mercado_ofertas":
                    item.callback = self._consistent_offers

        async def _consistent_offers(self, interaction: discord.Interaction):
            own, pending = await _read_user_offers(runtime, interaction.user.id)
            await interaction.response.send_message(
                embed=_offers_embed(own, interaction.user.id),
                view=runtime.OfertasView(pending),
                ephemeral=True,
            )

    ConsistentMercadoView.__name__ = "MercadoView"
    runtime.MercadoView = ConsistentMercadoView


def _log_runtime_identity(runtime):
    service_id = os.getenv("RAILWAY_SERVICE_ID") or "unknown"
    service_name = os.getenv("RAILWAY_SERVICE_NAME") or "unknown"
    deployment_id = os.getenv("RAILWAY_DEPLOYMENT_ID") or "unknown"
    replica_id = os.getenv("RAILWAY_REPLICA_ID") or "unknown"

    with runtime.db() as conn:
        counts = {}
        for table in ("clubs", "roster_players", "publications", "offers", "transfers"):
            try:
                counts[table] = int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])
            except sqlite3.Error:
                counts[table] = -1

    print(
        "AJAP DATA SOURCE | "
        f"service={service_name} service_id={service_id} deployment={deployment_id} replica={replica_id} | "
        f"db={runtime.DB_PATH} | clubs={counts['clubs']} roster={counts['roster_players']} "
        f"publications={counts['publications']} offers={counts['offers']} transfers={counts['transfers']}"
    )


def apply_data_consistency_patch(runtime):
    global APP
    APP = runtime
    if getattr(runtime, "_ajap_data_consistency_patch", False):
        return

    _install_connection(runtime)
    _patch_main_readers(runtime)
    _patch_market_view(runtime)
    _log_runtime_identity(runtime)

    runtime._ajap_data_consistency_patch = True
    print("AJAP consistencia de datos activa: WAL + busy timeout + lecturas protegidas")
