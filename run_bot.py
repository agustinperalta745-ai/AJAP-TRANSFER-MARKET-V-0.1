"""Arranque explícito y determinista de AJAP Transfer Market en Railway.

Railway ejecuta bot.py. Ese archivo importa este módulo. Acá cargamos el bot
estable desde core_bot.py sin conectarlo todavía, aplicamos primero la selección
de Olympique de Lyon y su plantilla, y recién después conectamos Discord.
"""

import sys
from pathlib import Path
from types import ModuleType

# Configura DB_PATH sobre el volumen de Railway antes de cargar el bot.
import sitecustomize  # noqa: F401

from team_assignment import apply_team_assignment_patch
from lyon_test_seed import apply_lyon_test_patch


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

# Orden obligatorio: selector de equipo primero; plantilla/OVR/precios después.
apply_team_assignment_patch(runtime, runtime.bot)
apply_lyon_test_patch(runtime)

print("AJAP startup OK: selector de Lyon aplicado antes de conectar Discord")
runtime.bot.run(runtime.TOKEN)
