"""Uniform visual layout for AJAP Staff -> Planteles.

Only changes the presentation of the final RostersView. Existing callbacks and
business logic are preserved. The destructive confirmation screen for deleting
a full team remains red; the main navigation menu uses the same neutral style
as the Administration home panel.
"""

from __future__ import annotations

import discord

import guild_isolation_patch as guild_isolation
import staff_admin_organized_patch as staff


APP = None
BOT = None


def _norm(value):
    return str(value or "").strip().casefold()


def _install_uniform_rosters_view():
    BaseRostersView = staff.RostersView
    if getattr(BaseRostersView, "_ajap_uniform_rosters_visual", False):
        return

    class UniformRostersView(BaseRostersView):
        def __init__(self):
            super().__init__()

            # Same visual language as Administración: neutral buttons in a
            # predictable two-column grid. Logic/callbacks stay untouched.
            for item in self.children:
                if not isinstance(item, discord.ui.Button):
                    continue

                item.style = discord.ButtonStyle.secondary
                label = _norm(getattr(item, "label", ""))
                cid = _norm(getattr(item, "custom_id", ""))

                if "mover jugador" in label or cid == "ajap_admin_roster_move":
                    item.row = 0
                elif "cargar jugador" in label or cid == "ajap_admin_load_player_ovr":
                    item.row = 0
                elif "quitar jugador" in label or cid == "ajap_admin_roster_remove":
                    item.row = 1
                elif "ver plantel" in label or cid == "ajap_admin_roster_view":
                    item.row = 1
                elif "crear equipo" in label or cid == "ajap_admin_create_team":
                    item.row = 2
                elif "eliminar equipo" in label or cid == "ajap_admin_delete_team_full":
                    item.row = 2
                elif label.startswith("volver"):
                    item.row = 3

    UniformRostersView.__name__ = "RostersView"
    UniformRostersView._ajap_uniform_rosters_visual = True
    staff.RostersView = UniformRostersView


def apply_admin_rosters_visual_patch(runtime, bot):
    global APP, BOT
    APP = runtime
    BOT = bot
    if getattr(runtime, "_ajap_admin_rosters_visual_patch", False):
        return

    _install_uniform_rosters_view()
    runtime._ajap_admin_rosters_visual_patch = True
    print("AJAP Staff: Planteles visual uniforme activo")


_original_apply_guild_isolation_patch = guild_isolation.apply_guild_isolation_patch


def _apply_guild_isolation_then_rosters_visual(runtime, bot):
    _original_apply_guild_isolation_patch(runtime, bot)
    apply_admin_rosters_visual_patch(runtime, bot)


if not getattr(
    guild_isolation.apply_guild_isolation_patch,
    "_ajap_admin_rosters_visual_wrapped",
    False,
):
    _apply_guild_isolation_then_rosters_visual._ajap_admin_rosters_visual_wrapped = True
    guild_isolation.apply_guild_isolation_patch = _apply_guild_isolation_then_rosters_visual
