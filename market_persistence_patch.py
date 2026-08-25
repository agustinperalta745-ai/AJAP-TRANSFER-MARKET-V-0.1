"""Persistencia fuerte del estado abrir/cerrar mercado de AJAP.

El estado del mercado vive exclusivamente en SQLite (market_state) y no en
memoria/Discord. Abrir o cerrar usa una transacción inmediata + UPSERT para que
la fila exista siempre y sobreviva cierres de Discord, reinicios y redeploys.

También hace que el panel administrativo muestre el estado real leído desde la
base cada vez que se construye la vista.
"""

import discord


def ensure_schema(runtime):
    with runtime.db() as conn:
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

            INSERT OR IGNORE INTO market_state (id, is_open)
            VALUES (1, 0);
            """
        )


def install_persistent_state(runtime):
    def mercado_abierto() -> bool:
        # Siempre se consulta SQLite: nunca se conserva una copia en memoria.
        with runtime.db() as conn:
            row = conn.execute(
                "SELECT is_open FROM market_state WHERE id = 1"
            ).fetchone()
            if row is None:
                conn.execute(
                    "INSERT INTO market_state (id, is_open) VALUES (1, 0)"
                )
                return False
            return bool(int(row["is_open"]))

    def cambiar_estado_mercado(abierto: bool, admin_id: int):
        value = 1 if abierto else 0
        conn = runtime.db()
        try:
            # Evita que dos interacciones concurrentes pisen el estado.
            conn.execute("PRAGMA busy_timeout = 5000")
            conn.execute("BEGIN IMMEDIATE")
            previous = conn.execute(
                "SELECT is_open FROM market_state WHERE id = 1"
            ).fetchone()
            previous_value = int(previous["is_open"]) if previous else None

            conn.execute(
                """
                INSERT INTO market_state (id, is_open, updated_by, updated_at)
                VALUES (1, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(id) DO UPDATE SET
                    is_open = excluded.is_open,
                    updated_by = excluded.updated_by,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (value, int(admin_id)),
            )

            # Auditamos solo cambios reales de estado.
            if previous_value != value:
                conn.execute(
                    """
                    INSERT INTO market_state_history (is_open, changed_by)
                    VALUES (?, ?)
                    """,
                    (value, int(admin_id)),
                )

            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

        # Verificación post-commit: si esto falla, no fingimos que cambió.
        with runtime.db() as verify_conn:
            saved = verify_conn.execute(
                "SELECT is_open FROM market_state WHERE id = 1"
            ).fetchone()
        if saved is None or int(saved["is_open"]) != value:
            raise RuntimeError("AJAP no pudo confirmar el estado persistente del mercado")
        return bool(value)

    runtime.mercado_abierto = mercado_abierto
    runtime.cambiar_estado_mercado = cambiar_estado_mercado


def patch_admin_view(runtime):
    base = runtime.AdminView

    class PersistentMarketAdminView(base):
        def __init__(self):
            super().__init__()
            abierto = runtime.mercado_abierto()

            for item in self.children:
                if not isinstance(item, discord.ui.Button):
                    continue

                if item.label == "Abrir mercado":
                    if abierto:
                        item.label = "Mercado ABIERTO"
                        item.disabled = True
                        item.style = discord.ButtonStyle.success
                    else:
                        item.label = "Abrir mercado"
                        item.disabled = False
                        item.style = discord.ButtonStyle.success

                elif item.label == "Cerrar mercado":
                    if abierto:
                        item.label = "Cerrar mercado"
                        item.disabled = False
                        item.style = discord.ButtonStyle.danger
                    else:
                        item.label = "Mercado CERRADO"
                        item.disabled = True
                        item.style = discord.ButtonStyle.secondary

    PersistentMarketAdminView.__name__ = "AdminView"
    runtime.AdminView = PersistentMarketAdminView


def apply_market_persistence_patch(runtime):
    if getattr(runtime, "_ajap_market_persistence_patch", False):
        return

    ensure_schema(runtime)
    install_persistent_state(runtime)
    patch_admin_view(runtime)
    runtime._ajap_market_persistence_patch = True

    state = "ABIERTO" if runtime.mercado_abierto() else "CERRADO"
    print(
        "AJAP market persistence activo: estado restaurado desde SQLite = "
        + state
    )
