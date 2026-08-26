"""Persistencia de botones Ofertar para todas las bases aisladas por servidor.

publication_announce_patch registra vistas persistentes antes de que guild isolation
esté activo, por lo que tras un deploy podía conocer solo las publicaciones de la
base histórica. Este parche se instala después del aislamiento y, en on_ready,
revisa las DB de todos los servidores conectados. Registra una vista persistente
por cada publication_id activo encontrado. Como el callback consulta la DB usando
el guild_id de la interacción, el mismo custom_id funciona correctamente aunque
el mismo número de publicación exista en más de un servidor.
"""

import sqlite3
from pathlib import Path

import publication_announce_patch as announcements


async def _register_all_guild_publication_views(runtime, bot):
    if getattr(bot, "_ajap_all_guild_publication_views_registered", False):
        return

    publication_ids = set()
    checked = 0

    for guild in list(getattr(bot, "guilds", []) or []):
        try:
            path = Path(runtime.guild_db_path(guild.id))
        except Exception as exc:
            print(f"WARNING AJAP: no se pudo resolver DB guild {getattr(guild, 'id', '?')}: {exc}")
            continue

        if not path.exists():
            # Un servidor todavía sin actividad no necesita vistas persistentes.
            continue

        try:
            conn = sqlite3.connect(str(path))
            conn.row_factory = sqlite3.Row
            try:
                table = conn.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name='publications' LIMIT 1"
                ).fetchone()
                if not table:
                    continue
                rows = conn.execute(
                    "SELECT id FROM publications WHERE active = 1 ORDER BY id ASC"
                ).fetchall()
                publication_ids.update(int(row["id"]) for row in rows)
                checked += 1
            finally:
                conn.close()
        except sqlite3.Error as exc:
            print(f"WARNING AJAP: no se pudo leer publicaciones de guild {guild.id}: {exc}")

    registered = 0
    for publication_id in sorted(publication_ids):
        try:
            bot.add_view(announcements.PublicationOfferView(publication_id))
            registered += 1
        except ValueError:
            # Ya estaba registrada por el arranque inicial; no es un error.
            pass

    bot._ajap_all_guild_publication_views_registered = True
    print(
        "AJAP botones Ofertar multi-guild persistentes: "
        f"DBs revisadas={checked} | IDs activos={len(publication_ids)} | nuevos={registered}"
    )


def apply_publication_guild_persistence_patch(runtime, bot):
    if getattr(runtime, "_ajap_publication_guild_persistence_patch", False):
        return

    if not getattr(runtime, "_ajap_guild_isolation_patch", False):
        raise RuntimeError("publication_guild_persistence_patch debe aplicarse después de guild_isolation_patch")

    bot.add_listener(
        lambda: _register_all_guild_publication_views(runtime, bot),
        "on_ready",
    )

    runtime._ajap_publication_guild_persistence_patch = True
    print("AJAP persistencia Ofertar multi-guild preparada para on_ready")
