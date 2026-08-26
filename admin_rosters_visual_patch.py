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


def _button_key(item):
    label = _norm(getattr(item, "label", ""))
    cid = _norm(getattr(item, "custom_id", ""))

    if "mover jugador" in label or cid == "ajap_admin_roster_move":
        return "move"
    if "cargar jugador" in label or cid == "ajap_admin_load_player_ovr":
        return "load"
    if "quitar jugador" in label or cid == "ajap_admin_roster_remove":
        return "remove"
    if "ver plantel" in label or cid == "ajap_admin_roster_view":
        return "view"
    if "crear equipo" in label or cid == "ajap_admin_create_team":
        return "create"
    if "eliminar equipo" in label or cid == "ajap_admin_delete_team_full":
        return "delete"
    if label.startswith("volver"):
        return "back"
    return None


def _install_uniform_rosters_view():
    BaseRostersView = staff.RostersView
    if getattr(BaseRostersView, "_ajap_uniform_rosters_visual", False):
        return

    class UniformRostersView(BaseRostersView):
        def __init__(self):
            super().__init__()

            # Changing item.row after the item is already inside a View does not
            # reliably rebuild discord.py's internal row weights. Rebuild the
            # view with the SAME button objects/callbacks in the desired order.
            original_items = list(self.children)
            buttons = {
                _button_key(item): item
                for item in original_items
                if isinstance(item, discord.ui.Button) and _button_key(item)
            }
            extras = [
                item for item in original_items
                if not (isinstance(item, discord.ui.Button) and _button_key(item))
            ]

            self.clear_items()

            layout = (
                ("move", 0),
                ("load", 0),
                ("remove", 1),
                ("view", 1),
                ("create", 2),
                ("delete", 2),
                ("back", 3),
            )

            for key, row in layout:
                item = buttons.get(key)
                if item is None:
                    continue
                item.style = discord.ButtonStyle.secondary
                item.row = row
                self.add_item(item)

            # Preserve any future/unknown controls instead of silently dropping
            # them. They are placed on the last available row.
            for item in extras:
                if isinstance(item, discord.ui.Button):
                    item.style = discord.ButtonStyle.secondary
                    item.row = 4
                self.add_item(item)

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
    print("AJAP Staff: Planteles visual uniforme 2x3 + volver activo")


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
