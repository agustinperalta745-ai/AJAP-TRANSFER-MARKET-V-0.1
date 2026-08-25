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
from market_close_report_patch import apply_market_close_report_patch
from clausulazo_patch import apply_clausulazo_patch
from clausulazo_safety_patch import apply_clausulazo_safety_patch
from budget_patch import apply_budget_patch


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
apply_market_close_report_patch(runtime, runtime.bot)
apply_clausulazo_patch(runtime, runtime.bot)
apply_clausulazo_safety_patch(runtime)

budget_status = ""
if budget_seeded is True:
    budget_status = " • Lyon cargado con $100.000.000"
elif budget_seeded is False:
    budget_status = " • presupuesto Lyon persistente"
elif budget_seeded is None:
    budget_status = " • presupuesto Lyon omitido por seguridad"

print(
    "AJAP startup OK: Lyon + Villarreal habilitados antes de conectar Discord"
    + (f" • Villarreal sembrado con {seeded} jugadores" if seeded else "")
    + budget_status
    + " • publicar por rangos OVR activo"
    + " • reporte de cierre Staff activo"
    + " • clausulazo Staff activo"
)
runtime.bot.run(runtime.TOKEN)
