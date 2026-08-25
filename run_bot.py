"""Arranque explícito y determinista de AJAP Transfer Market en Railway.

Carga bot.py sin iniciar Discord, aplica primero las capas de asignación de club
y plantilla de Lyon, y recién después conecta el bot. De esta forma la interfaz
vieja de "Registrar / actualizar club" no puede arrancar antes del parche.
"""

import sys
from pathlib import Path
from types import ModuleType

# Configura DB_PATH sobre el volumen de Railway antes de cargar bot.py.
import sitecustomize  # noqa: F401

from team_assignment import apply_team_assignment_patch
from lyon_test_seed import apply_lyon_test_patch


BOT_PATH = Path(__file__).with_name("bot.py")
source = BOT_PATH.read_text(encoding="utf-8")

# bot.py termina iniciando Discord. Lo quitamos temporalmente para poder aplicar
# la interfaz nueva ANTES de que Discord registre comandos y vistas persistentes.
run_line = "\nbot.run(TOKEN)"
if run_line not in source:
    raise RuntimeError("No se encontró la línea de arranque bot.run(TOKEN) en bot.py")
source = source.rsplit(run_line, 1)[0] + "\n"

runtime = ModuleType("ajap_bot_runtime")
runtime.__file__ = str(BOT_PATH)
runtime.__package__ = None
sys.modules[runtime.__name__] = runtime

exec(compile(source, str(BOT_PATH), "exec"), runtime.__dict__)

# Orden obligatorio: primero reemplazamos el registro manual de club por el
# selector de equipos; después cargamos la plantilla/OVR/precios de Lyon.
apply_team_assignment_patch(runtime, runtime.bot)
apply_lyon_test_patch(runtime)

print("AJAP startup OK: selector de Lyon aplicado antes de conectar Discord")
runtime.bot.run(runtime.TOKEN)
