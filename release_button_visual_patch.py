"""Visual distinction between releasing a player and resigning as DT.

The main MI CLUB action for player releases must not look like the destructive
"RENUNCIAR AL CLUB" action. Keep resignation red, but render player release as a
neutral secondary action with the free-agent icon. The final confirmation of an
actual release remains red/danger because that step is intentionally destructive.
"""

from __future__ import annotations

import discord

import player_release_patch as release


_original_release_hub_init = release.ReleaseHubButton.__init__
_original_release_intro_embed = release.release_intro_embed


def _release_hub_init_neutral(self, roster_callback, row=2):
    _original_release_hub_init(self, roster_callback, row=row)
    self.emoji = "🆓"
    self.style = discord.ButtonStyle.secondary


def _release_intro_embed_clear(club: str):
    embed = _original_release_intro_embed(club)
    embed.title = f"🆓 LIBERAR JUGADOR • {club.upper()}"
    embed.description = (
        "Elegí al jugador que querés dejar libre. Antes de confirmar vas a ver el costo exacto.\n\n"
        f"💸 **Costo fijo: {release.RELEASE_PERCENT}% del valor de mercado**\n"
        "🔒 Solo se puede liberar con el mercado abierto.\n"
        "ℹ️ Esta acción libera a un jugador de la plantilla; **no renuncia tu cargo como DT**."
    )
    return embed


release.ReleaseHubButton.__init__ = _release_hub_init_neutral
release.release_intro_embed = _release_intro_embed_clear

print("AJAP visual liberaciones activo: botón gris 🆓; renuncia conserva rojo 🚪")

# La liberación ya modifica AJAP al confirmar, pero Staff todavía debe reflejarla
# manualmente en PES 6. Esta capa publica una tarjeta amarilla en /canal_movimientos
# y permite marcarla verde con "Cargado en PES" sin mover al jugador dos veces.
import release_staff_pes_patch  # noqa: F401,E402

# RESET V1 OFICIAL: esta es la última capa importada antes de run_bot. Envolvemos
# guild isolation para armar un reset de lanzamiento que se ejecuta en on_ready,
# cuando todos los sincronizadores JSON ya quedaron instalados. El servidor
# histórico de pruebas se conserva y cada servidor oficial se resetea una sola vez.
import guild_isolation_patch as _guild_isolation  # noqa: E402
from v1_official_reset_patch import apply_v1_official_reset as _apply_v1_reset  # noqa: E402

_prior_guild_isolation = _guild_isolation.apply_guild_isolation_patch
if not getattr(_prior_guild_isolation, "_ajap_v1_reset_wrapped", False):
    def _apply_guild_isolation_then_v1_reset(runtime, bot):
        _prior_guild_isolation(runtime, bot)
        _apply_v1_reset(runtime, bot)

    _apply_guild_isolation_then_v1_reset._ajap_v1_reset_wrapped = True
    _guild_isolation.apply_guild_isolation_patch = _apply_guild_isolation_then_v1_reset

# Herramienta manual para Staff: Administración -> Gestión -> RESET V1.
# Usa la misma lógica del reset oficial, pero puede ejecutarse bajo demanda y
# exige dos confirmaciones antes de tocar la base del servidor actual.
import admin_manual_reset_patch  # noqa: F401,E402
# Antes de la primera confirmación muestra un resumen claro de todo lo que va a
# restaurarse, limpiarse, revertirse y conservarse si finalmente se ejecuta.
import reset_explanation_patch  # noqa: F401,E402
# Backups de seguridad: copia completa por servidor cada 24 horas, selector Staff
# para restaurar una fecha y backup preventivo automático antes de cada restore.
import automatic_backup_patch  # noqa: F401,E402
# Serializa backup/restore y evita que el primer snapshot compita con migraciones.
import backup_reliability_patch  # noqa: F401,E402
