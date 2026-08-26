"""Railway compatibility entry point.

Railway is currently configured to start `python bot.py`. Keep that command
working, but route startup through run_bot.py so the AJAP patches are applied
before Discord connects.
"""

# Extend the fixed-team selector/seed before Bot.run() installs team assignment.
# Import order matters: Everton wraps Newcastle's seed wrapper, so both rosters
# are preserved in the same startup chain.
import newcastle_extension  # noqa: F401
import everton_extension  # noqa: F401
# Existing per-guild DBs need a one-time safe sync for teams added later.
import additional_roster_sync_patch  # noqa: F401

# Patch nickname/vacancy flows before run_bot registers Discord commands/views.
import member_nickname_patch  # noqa: F401
import vacancy_nickname_patch  # noqa: F401
import selector_nickname_patch  # noqa: F401
import dt_resignation_patch  # noqa: F401

# Liga AJAP usa el mismo bot, pero queda separada del mercado. La envolvemos
# alrededor del aislamiento por servidor para que sus tablas/resultados también
# queden persistidos en la DB correspondiente a cada servidor de Discord.
import guild_isolation_patch
from league_automation_patch import apply_league_automation_patch

_original_apply_guild_isolation_patch = guild_isolation_patch.apply_guild_isolation_patch


def _apply_guild_isolation_and_league(runtime, bot):
    _original_apply_guild_isolation_patch(runtime, bot)
    apply_league_automation_patch(runtime, bot)


guild_isolation_patch.apply_guild_isolation_patch = _apply_guild_isolation_and_league

# Capa visual final: transforma el panel en estilo manager sin reemplazar la
# lógica de los botones ya instalados (incluye Liga y renuncia de DT).
import manager_menu_patch  # noqa: F401,E402
# Tras elegir equipo, mostrar inmediatamente el mismo panel final y filtrado.
import manager_selector_patch  # noqa: F401,E402
# Agrupa plantilla, economía, valor e información dentro de MI CLUB.
import my_club_menu_patch  # noqa: F401,E402
# Dashboard informativo de Staff: se mantiene como pantalla principal.
import staff_dashboard_patch  # noqa: F401,E402
# Herramientas administrativas agrupadas por Mercado/Planteles/Economía/Gestión.
import staff_admin_organized_patch  # noqa: F401,E402
# Debe ser la última capa visual: los admins siempre eligen primero entre modo
# usuario (para pruebas) y modo administrador (herramientas Staff).
import staff_profile_gate_patch  # noqa: F401,E402
# Alta administrativa de equipos/jugadores: selector de club + posición,
# 3 stats por puesto y OVR automático. También hace dinámico el catálogo de equipos.
import admin_roster_builder_patch  # noqa: F401,E402

import run_bot  # noqa: F401,E402
