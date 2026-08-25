"""Arranque explícito y determinista de AJAP Transfer Market en Railway.

Railway ejecuta bot.py. Ese archivo importa este módulo. Acá cargamos el bot
estable desde core_bot.py sin conectarlo todavía, habilitamos los equipos
permanentes y sus plantillas, y recién después conectamos Discord.
"""

import sys
from pathlib import Path
from types import ModuleType

# Configura DB_PATH sobre el volumen de Railway antes de cargar el bot.
import sitecustomize  # noqa: F401

from team_assignment import apply_team_assignment_patch
from lyon_test_seed import apply_lyon_test_patch
from multi_team_extension import enable_additional_teams, seed_additional_rosters


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

# Orden obligatorio: ampliar selector, instalar asignación y luego OVR/precios.
enable_additional_teams()
apply_team_assignment_patch(runtime, runtime.bot)
apply_lyon_test_patch(runtime)
seeded = seed_additional_rosters(runtime)

print(
    "AJAP startup OK: Lyon + Villarreal habilitados antes de conectar Discord"
    + (f" • Villarreal sembrado con {seeded} jugadores" if seeded else "")
)
runtime.bot.run(runtime.TOKEN)
