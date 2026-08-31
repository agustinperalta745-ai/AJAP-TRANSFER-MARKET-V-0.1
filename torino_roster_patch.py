"""Compatibility shim for the retired Torino team.

Torino is no longer part of the active AJPA competition.  This module is kept
only because older startup code still imports it.  It intentionally performs no
catalog registration, roster seeding, DB wrapping, or team activation.

Historical rows already stored in SQLite are preserved for referential/history
safety, but Torino cannot be recreated or reactivated by this module.
"""

TORINO = "Torino"
COUNTRY = "Italia"
TORINO_ROSTER = []
OVR_BY_PLAYER = {}


def apply_torino_json(runtime):
    """No-op: Torino is retired and must never be seeded again."""
    if not getattr(runtime, "_ajap_torino_retired", False):
        runtime._ajap_torino_retired = True
        print("AJAP Torino retirado: bootstrap deshabilitado")
    return None


print("AJAP Torino retirado: módulo de compatibilidad sin activación")
