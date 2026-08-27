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
# Betis.json is the source of truth; this overlay also recalculates every Betis
# OVR with the current 3-stat-by-position AJAP formula and bumps the migration.
import betis_roster_replace_patch  # noqa: F401

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
# Dentro de LIGA, Staff elige únicamente el canal de resultados; tabla y
# goleadores se renderizan en vivo dentro del menú, sin canal de tablas.
import league_channel_panel_patch  # noqa: F401,E402
# El ✅ sobre una captura aparece solamente después de comprobar que el resultado
# quedó persistido y ya participa del cálculo que usa el menú LIGA.
import league_result_confirmation_patch  # noqa: F401,E402
# Regla definitiva de Liga: solo cruces entre participantes oficiales. Si la
# captura falla o es inválida, crea una tarjeta Staff con carga manual persistente.
import league_validation_admin_review_patch  # noqa: F401,E402
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
# Permite eliminar un equipo completo (plantilla, presupuesto, asignación y estado
# de mercado) y volver a crearlo desde cero sin que los seeds lo reactiven solos.
import admin_team_delete_patch  # noqa: F401,E402
# IMPORTANTE: esta capa debe ir DESPUÉS del guard de eliminación. Así envuelve el
# catálogo final (incluyendo deleted_teams) y toda plantilla JSON/seed cargada
# queda automáticamente registrada como equipo seleccionable.
import roster_catalog_autosync_patch  # noqa: F401,E402
# Fuente única de verdad para la asignación: si existe en clubs dentro de la DB
# del servidor, MI CLUB y el resto del bot deben reconocerla aunque falle el apodo.
import club_assignment_consistency_patch  # noqa: F401,E402
# Última capa visual de Planteles: misma estética neutral que Administración,
# dos botones por fila y confirmaciones destructivas separadas.
import admin_rosters_visual_patch  # noqa: F401,E402
# Ver plantel ya no pide escribir el club: muestra un selector y difiere la
# interacción antes de tocar la DB para evitar expiraciones de Discord.
import admin_roster_view_selector_patch  # noqa: F401,E402
# En MI CLUB -> PLANTILLA, cada rango OVR agrega selector de jugador y abre la
# ficha completa con todas las estadísticas PES6 guardadas desde el JSON/dataset.
import roster_player_stats_patch  # noqa: F401,E402
# Mercado completo: búsqueda, transferibles, publicaciones y ofertas permiten
# consultar las estadísticas PES6/JSON antes de cerrar cualquier negocio.
import market_player_stats_patch  # noqa: F401,E402
# Base económica de préstamos: calcula el 10% del valor de mercado por temporada.
import loan_canon_patch  # noqa: F401,E402
# Regla final: ese 10% es el TOPE; el dueño puede pedir menos y se cobra por
# temporada el monto realmente acordado en la negociación.
import loan_canon_cap_patch  # noqa: F401,E402
# Conecta la auditoría económica al menú MI CLUB: saldo, ingresos, egresos,
# cánones, opciones de compra, clausulazos y ajustes de administración.
import treasury_menu_patch  # noqa: F401,E402
# Expone esa misma auditoría dentro de Staff -> Administración -> Economía,
# con selector de club y filtros de ingresos/egresos.
import staff_treasury_patch  # noqa: F401,E402
# Al ejecutar una opción de compra de un préstamo, avisar automáticamente al
# canal de movimientos Staff sin crear una falsa tarea pendiente de carga en PES.
import loan_purchase_staff_notification_patch  # noqa: F401,E402
# Las DB por servidor pueden ser más viejas que las migraciones de publicaciones;
# antes de enviar un modal se asegura el schema del guild actual.
import publication_submit_guild_schema_patch  # noqa: F401,E402
# Guardia FINAL del modal de préstamo: la capa per-guild anterior reemplaza
# on_submit, así que acá volvemos a imponer el tope real del 10% antes del INSERT.
import loan_publication_cap_guard_patch  # noqa: F401,E402
# discord.py 2.x reciente agregó un argumento interno al submit de modales. La
# capa de aislamiento se adapta a ambas firmas para que ningún modal muera antes
# de llegar a on_submit.
import discord_modal_guild_context_compat_patch  # noqa: F401,E402

import run_bot  # noqa: F401,E402
