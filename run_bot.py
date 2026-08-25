"""Arranque explícito de AJAP Transfer Market.

Carga primero los hooks de persistencia/asignación y después ejecuta bot.py.
Esto evita depender de que Python descubra sitecustomize automáticamente en Railway.
"""

import runpy

# Import explícito: instala el hook que aplica team_assignment + lyon_test_seed
# justo antes de que bot.py llame a Bot.run().
import sitecustomize  # noqa: F401

runpy.run_path("bot.py", run_name="__main__")
