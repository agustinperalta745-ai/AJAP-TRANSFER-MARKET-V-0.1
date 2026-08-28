"""Railway compatibility entry point.

Railway is currently configured to start `python bot.py`. Keep that command
working, but route startup through run_bot.py so the AJAP patches are applied
before Discord connects.
"""

import os
import time

# AJAP must have exactly one Discord gateway writer. This repository is currently
# connected to two different Railway projects, each with its own persistent
# volume/SQLite database. If both projects log in with the same Discord bot token,
# consecutive interactions can be handled by different databases: one instance
# saves "Ajax" and the next /mercado reads "sin equipo" (or an older club).
#
# `sublime-success` (project 6abcd5...) is the deployment that has been healthy
# since the first persistent-volume commits, so it is the canonical writer.
# The secondary Railway project stays alive/healthy but never imports or starts
# the Discord bot. Set AJAP_PRIMARY_RAILWAY_PROJECT_ID explicitly in the future
# before intentionally moving production to another Railway project.
PRIMARY_RAILWAY_PROJECT_ID = (
    os.getenv("AJAP_PRIMARY_RAILWAY_PROJECT_ID")
    or "6abcd5b2-6995-4e18-b7f1-be32f6298fdc"
).strip()
CURRENT_RAILWAY_PROJECT_ID = (os.getenv("RAILWAY_PROJECT_ID") or "").strip()

if (
    CURRENT_RAILWAY_PROJECT_ID
    and PRIMARY_RAILWAY_PROJECT_ID
    and CURRENT_RAILWAY_PROJECT_ID != PRIMARY_RAILWAY_PROJECT_ID
):
    print(
        "AJAP secondary Railway deployment detected: Discord gateway disabled | "
        f"current_project={CURRENT_RAILWAY_PROJECT_ID} | "
        f"primary_project={PRIMARY_RAILWAY_PROJECT_ID}"
    )
    # Keep the secondary worker healthy so Railway does not enter a restart loop.
    # It intentionally performs no DB mutations and never connects to Discord.
    while True:
        time.sleep(3600)

# Extend the fixed-team selector/seed before Bot.run() installs team assignment.
# Import order matters: Everton wraps Newcastle's seed wrapper, so both rosters
# are preserved in the same startup chain.
import newcastle_extension  # noqa: F401,E402
import everton_extension  # noqa: F401,E402
# Existing per-guild DBs need a one-time safe sync for teams added later.
import additional_roster_sync_patch  # noqa: F401,E402
# Betis.json is the source of truth; this overlay also recalculates every Betis
# OVR with the current 3-stat-by-position AJAP formula and bumps the migration.
import betis_roster_replace_patch  # noqa: F401,E402
# Sevilla.json replaces the legacy 22-player Sevilla seed with the canonical
# 24-player roster, full PES6 attributes/abilities and the same AJAP OVR formula.
import sevilla_roster_replace_patch  # noqa: F401,E402
# Villareal.json replaces Villarreal's legacy seed with the uploaded 24-player
# roster, full PES6 attributes/abilities and AJAP 3-stat OVR.
import villarreal_roster_replace_patch  # noqa: F401,E402
# Torino.json adds Torino as a selectable Italian club with the uploaded
# 27-player roster, full PES6 attributes/abilities and AJAP 3-stat OVR.
import torino_roster_patch  # noqa: F401,E402
# Fiorentina.json adds Fiorentina as a selectable Italian club with the uploaded
# 25-player roster, full PES6 attributes/abilities and AJAP 3-stat OVR.
import fiorentina_roster_patch  # noqa: F401,E402
# Lazio.json adds Lazio as a selectable Italian club with the uploaded
# 23-player roster, full PES6 attributes/abilities and AJAP 3-stat OVR.
import lazio_roster_patch  # noqa: F401,E402
# Fulham.json adds Fulham as a selectable English club with the uploaded
# 29-player roster, full PES6 attributes/abilities and AJAP 3-stat OVR.
import fulham_roster_patch  # noqa: F401,E402
# Bolton Wanderers.json adds Bolton Wanderers as a selectable English club with the uploaded
# 21-player roster, full PES6 attributes/abilities and AJAP 3-stat OVR.
import bolton_wanderers_roster_patch  # noqa: F401,E402
# Middle.json adds Middlesbrough as a selectable English club with the uploaded
# 32-player roster, full PES6 attributes/abilities and AJAP 3-stat OVR.
import middlesbrough_roster_patch  # noqa: F401,E402
# Manchester City.json adds Manchester City as a selectable English club with the uploaded
# 28-player roster, full PES6 attributes/abilities and AJAP 3-stat OVR.
import manchester_city_roster_patch  # noqa: F401,E402
# West Ham United.json adds West Ham United as a selectable English club with the uploaded
# 26-player roster, full PES6 attributes/abilities and AJAP 3-stat OVR.
import west_ham_united_roster_patch  # noqa: F401,E402

# Patch nickname/vacancy flows before run_bot registers Discord commands/views.
import member_nickname_patch  # noqa: F401,E402
import vacancy_nickname_patch  # noqa: F401,E402
import selector_nickname_patch  # noqa: F401,E402
import dt_resignation_patch  # noqa: F401,E402

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
# Dentro de LIGA se renderizan tabla y goleadores en vivo, sin canal de tablas.
import league_channel_panel_patch  # noqa: F401,E402
# El ✅ sobre una captura aparece solamente después de comprobar que el resultado
# quedó persistido y ya participa del cálculo que usa el menú LIGA.
import league_result_confirmation_patch  # noqa: F401,E402
# Regla definitiva de Liga: solo cruces entre participantes oficiales. Si la
# captura falla o es inválida, crea una tarjeta Staff con carga manual persistente.
import league_validation_admin_review_patch  # noqa: F401,E402
# Regla final de evidencia: una captura parcial jamás toca la tabla; si hubo
# reinicio se decide entre resultado total o suma de tramos, y sin captura final
# el marcador manual necesita confirmación del DT rival.
import league_result_evidence_patch  # noqa: F401,E402
# Liga vive fuera del canal único de Mercado: sus botones y modales funcionan en
# Resultados/Staff aunque /canal_mercado apunte a otro canal.
import league_market_channel_exemption_patch  # noqa: F401,E402
# Corrige el puente entre /canal_movimientos y listeners en background: siempre
# consulta la DB del guild explícito y evita duplicar una misma revisión.
import guild_report_channel_bridge_patch  # noqa: F401,E402
# Si OpenAI rechaza el análisis, la revisión Staff muestra solo el HTTP/categoría
# segura (sin exponer la clave) para distinguir billing, permisos o formato.
import league_api_error_diagnostic_patch  # noqa: F401,E402
# Evita que una captura parezca ignorada: avisa canal mal configurado, muestra
# procesamiento inmediato y deja estado visible para parcial/revisión/pendiente.
import league_result_feedback_patch  # noqa: F401,E402
# Tras elegir equipo, mostrar inmediatamente el mismo panel final y filtrado.
import manager_selector_patch  # noqa: F401,E402
# Agrupa plantilla, economía, valor e información dentro de MI CLUB.
import my_club_menu_patch  # noqa: F401,E402
# Dashboard informativo de Staff: se mantiene como pantalla principal.
import staff_dashboard_patch  # noqa: F401,E402
# Herramientas administrativas agrupadas por Mercado/Planteles/Economía/Gestión.
import staff_admin_organized_patch  # noqa: F401,E402
# Configurar el canal de resultados pertenece a Administración -> Gestión;
# el menú LIGA de los jugadores queda exclusivamente para consulta.
import league_admin_config_location_patch  # noqa: F401,E402
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
# Autoridad final de asignaciones: una renuncia/desvinculación auditada siempre
# libera al DT, el club vivo no puede ser pisado por una asignación histórica y,
# si falta la fila viva, solo la última asignación auditada puede reconstruirla.
# Se importa explícitamente para que esta protección no dependa de otro selector.
import assignment_history_authority_patch  # noqa: F401,E402
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
# Guardia final de renuncia: evita paneles efímeros viejos y responde al clic
# antes de tocar roles/apodos para que Discord no venza la interacción.
import resignation_consistency_patch  # noqa: F401,E402
# Filtro visual FINAL: al elegir club, solo se muestran equipos respaldados por
# un JSON real en data/. Los equipos viejos quedan en DB para no romper historial.
import json_team_selection_patch  # noqa: F401,E402
# Escudos oficiales: miniatura en embeds + emoji del club en el selector inicial.
# Discord no admite PNG directos dentro de SelectOption, por eso se crean emojis
# del servidor automáticamente desde assets/teams (con bandera como fallback).
import team_badge_selector_patch  # noqa: F401,E402
# Capa de fiabilidad: limpia revisiones rotas del City, crea un emoji fresco y
# usa la URL CDN de Discord para los thumbnails en lugar del raw de GitHub.
import badge_reliability_patch  # noqa: F401,E402
# Última defensa para formularios: ejecuta el submit con firma flexible y contexto
# correcto incluso si discord.py cambia nuevamente sus argumentos privados.
import modal_submit_hardening_patch  # noqa: F401,E402
# Hotfix de la búsqueda guiada: Discord no admite valores vacíos en opciones de
# select; usa un sentinel seguro para "Todos/Cualquiera" y evita el timeout.
import guided_search_select_fix_patch  # noqa: F401,E402
# Liberaciones de jugadores: solo con mercado abierto, costo fijo del 20% del
# valor de mercado, descuento automático, historial/tesorería y pase a libre.
import player_release_patch  # noqa: F401,E402
# Diferencia visualmente LIBERAR JUGADOR de RENUNCIAR AL CLUB: liberación queda
# gris con 🆓; la renuncia conserva el botón rojo 🚪.
import release_button_visual_patch  # noqa: F401,E402

import run_bot  # noqa: F401,E402
