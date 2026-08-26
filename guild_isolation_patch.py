"""Aislamiento persistente de AJAP por servidor de Discord.

El servidor de pruebas conserva la base histórica. Cada guild adicional obtiene
su propio archivo SQLite dentro del mismo volumen de Railway. La primera vez se
clona la estructura/datos estáticos de la base histórica y se limpian todos los
datos operativos para que el nuevo servidor arranque como una liga nueva.
"""

from __future__ import annotations

import contextvars
import os
import sqlite3
from pathlib import Path


# Servidor histórico usado durante las pruebas de AJAP. Las operaciones de
# arranque (seeds/migraciones) siguen apuntando a esta base por compatibilidad.
LEGACY_GUILD_ID = int(os.getenv("AJAP_LEGACY_GUILD_ID", "1501062815920816360"))

_CURRENT_GUILD_ID = contextvars.ContextVar(
    "ajap_current_guild_id", default=LEGACY_GUILD_ID
)

# Tablas que contienen el catálogo/planteles. Se copian al crear una liga nueva.
# El resto se considera estado de la liga y se limpia en el clon.
def _is_static_table(name: str) -> bool:
    low = name.casefold()
    return (
        low == "roster_players"
        or low == "league_teams"
        or "pes6" in low
        or "attribute" in low
        or "stat" in low and "state" not in low
    )


def _guild_db_path(base_path: Path, guild_id: int) -> Path:
    if int(guild_id) == LEGACY_GUILD_ID:
        return base_path
    suffix = base_path.suffix or ".db"
    stem = base_path.name[: -len(suffix)] if suffix else base_path.name
    return base_path.with_name(f"{stem}.guild_{int(guild_id)}{suffix}")


def _restore_rosters_to_pre_test_state(conn: sqlite3.Connection) -> None:
    """Revierte movimientos de prueba usando el primer club conocido del historial."""
    names = {
        row["name"]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    if "roster_players" not in names or "player_history" not in names:
        return

    history_cols = {
        row["name"] for row in conn.execute("PRAGMA table_info(player_history)").fetchall()
    }
    if not {"player", "from_club"}.issubset(history_cols):
        return

    # Para cada jugador tocado durante las pruebas usamos el from_club del evento
    # más antiguo como club de origen. Si no hay from_club, no alteramos el plantel.
    rows = conn.execute(
        """
        SELECT h.player, h.from_club
        FROM player_history h
        JOIN (
            SELECT player, MIN(id) AS first_id
            FROM player_history
            WHERE from_club IS NOT NULL AND TRIM(from_club) != ''
            GROUP BY player
        ) first_move ON first_move.first_id = h.id
        """
    ).fetchall()
    for row in rows:
        conn.execute(
            """
            UPDATE roster_players
            SET club = ?, updated_at = CURRENT_TIMESTAMP
            WHERE name = ? COLLATE NOCASE
            """,
            (row["from_club"], row["player"]),
        )


def _clean_new_guild_database(conn: sqlite3.Connection) -> None:
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = OFF")
    _restore_rosters_to_pre_test_state(conn)

    tables = [
        row["name"]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
    ]

    for table in tables:
        if _is_static_table(table):
            continue
        safe_name = table.replace('"', '""')
        conn.execute(f'DELETE FROM "{safe_name}"')

    # Estado inicial de una liga nueva.
    if "market_state" in tables:
        conn.execute(
            "INSERT OR REPLACE INTO market_state (id, is_open) VALUES (1, 0)"
        )
    if "seasons" in tables:
        conn.execute(
            "INSERT OR IGNORE INTO seasons (name, active) VALUES ('Temporada 1', 1)"
        )
        conn.execute(
            "UPDATE seasons SET active = CASE WHEN name = 'Temporada 1' THEN 1 ELSE 0 END"
        )

    conn.commit()
    conn.execute("PRAGMA foreign_keys = ON")


def _bootstrap_guild_database(base_path: Path, target_path: Path) -> None:
    """Crea el DB del guild de forma atómica a partir del DB histórico."""
    if target_path.exists():
        return

    target_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = target_path.with_suffix(target_path.suffix + ".tmp")
    if temp_path.exists():
        temp_path.unlink()

    source = sqlite3.connect(str(base_path))
    source.row_factory = sqlite3.Row
    dest = sqlite3.connect(str(temp_path))
    dest.row_factory = sqlite3.Row
    try:
        source.backup(dest)
        _clean_new_guild_database(dest)
    finally:
        dest.close()
        source.close()

    os.replace(temp_path, target_path)
    print(f"AJAP guild DB creado: guild={target_path.stem.split('guild_')[-1]}")


def _interaction_guild_id(interaction) -> int:
    guild_id = getattr(interaction, "guild_id", None)
    return int(guild_id) if guild_id else LEGACY_GUILD_ID


def _install_interaction_context(bot) -> None:
    """Propaga guild_id a slash commands, botones/selects y modales."""
    tree = bot.tree
    original_tree_call = tree._call

    async def guild_tree_call(interaction):
        token = _CURRENT_GUILD_ID.set(_interaction_guild_id(interaction))
        try:
            return await original_tree_call(interaction)
        finally:
            _CURRENT_GUILD_ID.reset(token)

    tree._call = guild_tree_call

    store = bot._connection._view_store
    original_dispatch_view = store.dispatch_view

    def guild_dispatch_view(component_type, custom_id, interaction):
        token = _CURRENT_GUILD_ID.set(_interaction_guild_id(interaction))
        try:
            # discord.py crea la Task del callback aquí; ContextVar se copia a esa Task.
            return original_dispatch_view(component_type, custom_id, interaction)
        finally:
            _CURRENT_GUILD_ID.reset(token)

    store.dispatch_view = guild_dispatch_view

    original_dispatch_modal = getattr(store, "dispatch_modal", None)
    if original_dispatch_modal is not None:
        def guild_dispatch_modal(custom_id, interaction, components, *extra):
            token = _CURRENT_GUILD_ID.set(_interaction_guild_id(interaction))
            try:
                return original_dispatch_modal(custom_id, interaction, components, *extra)
            finally:
                _CURRENT_GUILD_ID.reset(token)

        store.dispatch_modal = guild_dispatch_modal


def apply_guild_isolation_patch(runtime, bot):
    if getattr(runtime, "_ajap_guild_isolation_patch", False):
        return

    base_path = Path(runtime.DB_PATH).resolve()

    def guild_db():
        guild_id = int(_CURRENT_GUILD_ID.get())
        path = _guild_db_path(base_path, guild_id)
        if path != base_path and not path.exists():
            _bootstrap_guild_database(base_path, path)
        conn = sqlite3.connect(str(path))
        conn.row_factory = sqlite3.Row
        return conn

    runtime.db = guild_db
    runtime.current_guild_id = lambda: int(_CURRENT_GUILD_ID.get())
    runtime.guild_db_path = lambda guild_id: str(
        _guild_db_path(base_path, int(guild_id))
    )

    _install_interaction_context(bot)
    runtime._ajap_guild_isolation_patch = True
    print(
        "AJAP guild isolation activo: datos operativos separados por servidor "
        f"(legacy={LEGACY_GUILD_ID})"
    )
