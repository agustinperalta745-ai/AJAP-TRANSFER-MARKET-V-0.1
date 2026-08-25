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

from team_assignment import apply_team_assignment_patch
from lyon_test_seed import apply_lyon_test_patch
from multi_team_extension import enable_additional_teams, seed_additional_rosters
from publish_ovr_patch import apply_publish_ovr_patch
from flexible_offer_patch import apply_flexible_offer_patch
from offer_value_floor_patch import apply_offer_value_floor_patch
from offer_notifications_patch import apply_offer_notifications_patch
from pes6_attributes_patch import apply_pes6_attributes_patch
from pes6_stats_importer import import_pes6_original_stats
from global_player_search_patch import apply_global_player_search_patch
from negotiation_picker_patch import apply_negotiation_picker_patch
from market_close_report_patch import apply_market_close_report_patch
from market_channel_report_patch import apply_market_channel_report_patch
from clausulazo_patch import apply_clausulazo_patch
from clausulazo_safety_patch import apply_clausulazo_safety_patch
from clausulazo_club_protection_patch import apply_clausulazo_club_protection_patch
from clausulazo_announce_patch import apply_clausulazo_announce_patch
from budget_patch import apply_budget_patch
from navigation_patch import apply_navigation_patch
from admin_finance_patch import apply_admin_finance_patch
from market_persistence_patch import apply_market_persistence_patch


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
# Primero se define la negociación flexible. Después se protege el valor mínimo
# y recién entonces la capa de notificaciones envuelve el modal definitivo.
apply_flexible_offer_patch(runtime)
apply_offer_value_floor_patch(runtime)
apply_offer_notifications_patch(runtime)
# Los atributos originales PES6 se cargan antes de la lupa. Nunca se calculan
# desde el OVR AJAP: solo se muestran valores verificados que existan en la DB.
apply_pes6_attributes_patch(runtime)
# Si el dataset original está incluido en data/ (CSV/XLSX/XLS), se importa de
# forma automática. Solo vincula jugadores ya existentes en nuestros planteles.
pes6_import = import_pes6_original_stats(runtime)
# Buscar usa la base completa de planteles y, cuando corresponde, reutiliza el
# modal final de ofertas ya protegido por valor mínimo + notificaciones.
apply_global_player_search_patch(runtime)
# Sobre el modal final agregamos selección desde plantel y negociación ida/vuelta.
apply_negotiation_picker_patch(runtime)
# Reporte base de cierre y luego publicación adicional en canal configurado.
apply_market_close_report_patch(runtime, runtime.bot)
apply_market_channel_report_patch(runtime, runtime.bot)
apply_clausulazo_patch(runtime, runtime.bot)
apply_clausulazo_safety_patch(runtime)
apply_clausulazo_club_protection_patch(runtime)
apply_clausulazo_announce_patch(runtime)
# Navegación sobre las vistas finales.
apply_navigation_patch(runtime)
# Debe ir después de navegación para conservar el botón Volver al menú del panel admin.
apply_admin_finance_patch(runtime)
# Última capa del panel: el estado del mercado se lee/escribe siempre desde SQLite.
# Así conserva ABIERTO/CERRADO aunque se cierre Discord o Railway reinicie/redeploye.
apply_market_persistence_patch(runtime)

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
    "AJAP startup OK: Lyon + Villarreal + Real Betis + Sevilla + Lazio + Tottenham Hotspur habilitados antes de conectar Discord"
    + (f" • {seeded} jugador(es) nuevos sembrados" if seeded else " • plantillas adicionales persistentes")
    + budget_status
    + " • publicar por rangos OVR activo"
    + " • ofertas flexibles dinero/jugador/mixtas activas"
    + " • valor mínimo equivalente protegido"
    + " • ofertas DM + anuncio público activas"
    + " • selector de jugador desde plantel activo"
    + " • contraofertas con cambio de jugador activas"
    + " • atributos clave PES6 por posición activos"
    + pes6_status
    + " • búsqueda global de jugadores activa"
    + " • reporte de cierre Staff activo"
    + " • canal automático de movimientos activo"
    + " • clausulazo Staff activo"
    + " • clausulazo DM + anuncio público activo"
    + " • protección doble jugador + club activa"
    + " • navegación interna activa"
    + " • ajustes de dinero admin activos"
    + " • mercado abrir/cerrar persistente"
)
runtime.bot.run(runtime.TOKEN)
