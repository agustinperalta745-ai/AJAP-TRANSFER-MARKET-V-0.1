"""Arranque explícito y determinista de AJAP Transfer Market en Railway.

Railway ejecuta bot.py. Ese archivo importa este módulo. Acá cargamos el bot
estable desde core_bot.py sin conectarlo todavía, habilitamos los equipos
permanentes y sus plantillas, y recién después conectamos Discord.
"""

import os
import sys
from pathlib import Path
from types import ModuleType

# Configura DB_PATH sobre el volumen de Railway antes de cargar el bot.
import sitecustomize  # noqa: F401
import member_nickname_patch

from team_assignment import apply_team_assignment_patch
from lyon_test_seed import apply_lyon_test_patch
from multi_team_extension import enable_additional_teams, seed_additional_rosters
from publish_ovr_patch import apply_publish_ovr_patch
from publication_announce_patch import apply_publication_announce_patch
from publication_loan_options_patch import apply_publication_loan_options_patch
from flexible_offer_patch import apply_flexible_offer_patch
from offer_value_floor_patch import apply_offer_value_floor_patch
from loan_terms_patch import apply_loan_terms_offer_patch, apply_loan_terms_negotiation_patch
from loan_lifecycle_patch import apply_loan_lifecycle_patch
from loan_integrity_patch import apply_loan_integrity_patch
from offer_notifications_patch import apply_offer_notifications_patch
from pes6_attributes_patch import apply_pes6_attributes_patch
from pes6_stats_importer import import_pes6_original_stats
from global_player_search_patch import apply_global_player_search_patch
from negotiation_picker_patch import apply_negotiation_picker_patch
from publication_management_patch import apply_publication_management_patch
from split_transferibles_patch import apply_split_transferibles_patch
from inline_offer_actions_patch import apply_inline_offer_actions_patch
from market_close_report_patch import apply_market_close_report_patch
from market_channel_report_patch import apply_market_channel_report_patch
from clausulazo_patch import apply_clausulazo_patch
from clausulazo_safety_patch import apply_clausulazo_safety_patch
from clausulazo_club_protection_patch import apply_clausulazo_club_protection_patch
from clausulazo_announce_patch import apply_clausulazo_announce_patch
from clausulazo_report_bridge_patch import apply_clausulazo_report_bridge
from staff_review_channel_patch import apply_staff_review_channel_patch
from staff_review_runtime_fix_patch import apply_staff_review_runtime_fix
from budget_patch import apply_budget_patch
from navigation_patch import apply_navigation_patch
from admin_finance_patch import apply_admin_finance_patch
from market_persistence_patch import apply_market_persistence_patch
from market_usage_channel_patch import apply_market_usage_channel_patch
from guild_isolation_patch import apply_guild_isolation_patch
from aston_villa_roster_patch_v2 import apply_aston_villa_json
from benfica_roster_patch import apply_benfica_json
from porto_roster_patch import apply_porto_json
from ajax_roster_patch import apply_ajax_json
from celta_roster_patch import apply_celta_json
from zaragoza_roster_patch import apply_zaragoza_json
from atletico_madrid_roster_patch import apply_atletico_json
from galatasaray_roster_patch import apply_galatasaray_json


# Compatibilidad con nombres de variable usados en hosts/bots anteriores.
# Nunca imprimimos el valor del token; solo el nombre de la variable encontrada.
if not os.getenv("DISCORD_TOKEN"):
    for alias in ("BOT_TOKEN", "DISCORD_BOT_TOKEN", "TOKEN"):
        value = os.getenv(alias)
        if value:
            os.environ["DISCORD_TOKEN"] = value
            print(f"AJAP Discord token loaded from alias: {alias}")
            break

BOT_PATH = Path(__file__).with_name("core_bot.py")
source = BOT_PATH.read_text(encoding="utf-8")

# core_bot.py termina iniciando Discord. Lo quitamos temporalmente para poder
# aplicar la interfaz nueva ANTES de que Discord registre comandos y vistas.
run_line = "\nbot.run(TOKEN)"
if run_line not in source:
    raise RuntimeError("No se encontró la línea de arranque bot.run(TOKEN) en core_bot.py")
source = source.rsplit(run_line, 1)[0] + "\n"

runtime = ModuleType("ajap_bot_runtime")
runtime.__file__ = str(BOT_PATH)
runtime.__package__ = None
sys.modules[runtime.__name__] = runtime

exec(compile(source, str(BOT_PATH), "exec"), runtime.__dict__)

# Orden obligatorio: equipos/plantillas/UI y luego reportes/reglas de mercado.
enable_additional_teams()
# MultiTeamSelect reemplaza al selector base; el parche de apodos tiene que
# aplicarse después para envolver el selector que realmente usa Discord.
member_nickname_patch.apply_member_nickname_patch()
apply_team_assignment_patch(runtime, runtime.bot)
apply_lyon_test_patch(runtime)
seeded = seed_additional_rosters(runtime)

# El presupuesto es una extensión, no una dependencia crítica. Si su migración
# falla por cualquier estado viejo de SQLite, el bot debe seguir arrancando.
budget_seeded = None
try:
    budget_seeded = apply_budget_patch(runtime)
except Exception as exc:
    print(f"WARNING AJAP: presupuesto Lyon deshabilitado en este arranque: {exc}")

apply_publish_ovr_patch(runtime)
# Cada publicación confirmada genera un aviso visible en el canal donde se hizo.
apply_publication_announce_patch(runtime)
# Antes de ofertar, la publicación define el tipo y los préstamos exigen sus términos.
apply_publication_loan_options_patch(runtime)
# Primero se define la negociación flexible. Después se protege el valor mínimo.
# Los términos de préstamo se agregan antes de notificaciones para que los avisos
# ya salgan con duración y opción de compra completas.
apply_flexible_offer_patch(runtime)
apply_offer_value_floor_patch(runtime)
apply_loan_terms_offer_patch(runtime)
apply_offer_notifications_patch(runtime)
# Los atributos originales PES6 se cargan antes de la lupa. Nunca se calculan
# desde el OVR AJPA: solo se muestran valores verificados que existan en la DB.
apply_pes6_attributes_patch(runtime)
# Si el dataset original está incluido en data/ (CSV/XLSX/XLS), se importa de
# forma automática. Solo vincula jugadores ya existentes en nuestros planteles.
pes6_import = import_pes6_original_stats(runtime)
# Buscar usa la base completa de planteles y, cuando corresponde, reutiliza el
# modal final de ofertas ya protegido por valor mínimo + notificaciones.
apply_global_player_search_patch(runtime)
# Sobre el modal final agregamos selección desde plantel y negociación ida/vuelta.
apply_negotiation_picker_patch(runtime)
# Si el usuario selecciona una publicación propia, puede retirarla sin borrar historial.
apply_publication_management_patch(runtime)
# Después del selector se vuelven loan-aware las contraofertas y la aceptación.
apply_loan_terms_negotiation_patch(runtime)
# Los avisos públicos y DMs de oferta/contraoferta incluyen respuesta directa.
apply_inline_offer_actions_patch(runtime, runtime.bot)
# Reporte base de cierre y canal Staff/PES por operación.
apply_market_close_report_patch(runtime, runtime.bot)
apply_market_channel_report_patch(runtime, runtime.bot)
apply_clausulazo_patch(runtime, runtime.bot)
apply_clausulazo_safety_patch(runtime)
apply_clausulazo_club_protection_patch(runtime)
apply_clausulazo_announce_patch(runtime)
# Clausulazos también generan la tarjeta amarilla al quedar aprobados.
apply_clausulazo_report_bridge(runtime)
# El mismo canal recibe pendientes y permite aprobar/rechazar transferencias,
# préstamos, intercambios y clausulazos sin volver al panel administrativo.
apply_staff_review_channel_patch(runtime, runtime.bot)
# Navegación sobre las vistas finales.
apply_navigation_patch(runtime)
# Debe ir después de navegación para conservar el botón Volver al menú del panel admin.
apply_admin_finance_patch(runtime)
# Última capa visual del mercado: separar publicaciones propias de las ajenas.
apply_split_transferibles_patch(runtime)
# El estado del mercado se lee/escribe siempre desde SQLite.
apply_market_persistence_patch(runtime)
# Última capa: contratos de préstamo, vencimientos y opciones de compra deben ver
# la UI, navegación, presupuesto y persistencia definitivos.
apply_loan_lifecycle_patch(runtime, runtime.bot)
apply_loan_integrity_patch(runtime)
# Registra /canal_mercado y prepara el bloqueo antes de que guild isolation
# envuelva las interacciones con el contexto de la base correspondiente.
apply_market_usage_channel_patch(runtime, runtime.bot)
# Los botones del panel Staff/PES funcionan aunque el canal de reportes sea
# distinto al canal general configurado con /canal_mercado.
apply_staff_review_runtime_fix(runtime, runtime.bot)
# A partir de este punto, cada interacción usa la DB persistente de su servidor.
# El servidor histórico de pruebas conserva su DB; los servidores nuevos nacen limpios.
apply_guild_isolation_patch(runtime, runtime.bot)
# Aston Villa se sincroniza después del aislamiento para sembrar cada servidor por separado.
apply_aston_villa_json(runtime)
# Benfica usa el mismo esquema: JSON completo, OVR AJPA y sincronización por servidor.
apply_benfica_json(runtime)
# Porto usa el mismo esquema y conserva las transferencias ya realizadas.
apply_porto_json(runtime)
# Ajax usa el mismo esquema: JSON completo, OVR AJPA y sincronización por servidor.
apply_ajax_json(runtime)
# Celta de Vigo usa el mismo esquema: JSON completo, OVR AJPA y sincronización por servidor.
apply_celta_json(runtime)
# Real Zaragoza usa el mismo esquema: JSON completo, OVR AJPA y sincronización por servidor.
apply_zaragoza_json(runtime)
# Atletico de Madrid usa el mismo esquema: JSON completo, OVR AJPA y sincronización por servidor.
apply_atletico_json(runtime)
# Galatasaray usa el mismo esquema: JSON completo, OVR AJPA y sincronización por servidor.
apply_galatasaray_json(runtime)

budget_status = ""
if budget_seeded is True:
    budget_status = " • Lyon cargado con $100.000.000"
elif budget_seeded is False:
    budget_status = " • presupuesto Lyon persistente"
elif budget_seeded is None:
    budget_status = " • presupuesto Lyon omitido por seguridad"

pes6_status = ""
if pes6_import.get("files"):
    pes6_status = f" • {pes6_import['matched']} jugador(es) con stats PES6 originales importados"
else:
    pes6_status = " • importador PES6 listo (dataset externo pendiente de incorporar)"

print(
    "AJAP startup OK: Lyon + Villarreal + Real Betis + Sevilla + Lazio + Tottenham Hotspur + Aston Villa + Benfica + Porto + Ajax + Celta de Vigo + Real Zaragoza + Atletico de Madrid + Galatasaray habilitados antes de conectar Discord"
    + (f" • {seeded} jugador(es) nuevos sembrados" if seeded else " • plantillas adicionales persistentes")
    + budget_status
    + " • publicar por rangos OVR activo"
    + " • publicación de préstamos con términos obligatorios activa"
    + " • anuncios públicos de transferibles activos"
    + " • gestión propia de transferibles activa"
    + " • transferibles separados otros/míos activos"
    + " • ofertas flexibles dinero/jugador/mixtas activas"
    + " • valor mínimo equivalente protegido"
    + " • préstamos con temporadas + opción de compra activos"
    + " • ciclo completo de préstamos activo"
    + " • cedidos protegidos de publicación/clausulazo"
    + " • ofertas DM + anuncio público activas"
    + " • selector de jugador desde plantel activo"
    + " • contraofertas con cambio de jugador activas"
    + " • respuesta directa desde avisos activa"
    + " • atributos clave PES6 por posición activos"
    + pes6_status
    + " • búsqueda global de jugadores activa"
    + " • reporte de cierre Staff activo"
    + " • checklist Staff/PES rojo-amarillo-verde activo"
    + " • aprobación Staff directa desde canal activa"
    + " • botones Staff persistentes fuera del canal de mercado"
    + " • clausulazo Staff activo"
    + " • clausulazo integrado al checklist PES"
    + " • clausulazo DM + anuncio público activo"
    + " • protección doble jugador + club activa"
    + " • navegación interna activa"
    + " • ajustes de dinero admin activos"
    + " • mercado abrir/cerrar persistente"
    + " • canal único de uso configurable"
    + " • datos separados por servidor"
)
runtime.bot.run(runtime.TOKEN)