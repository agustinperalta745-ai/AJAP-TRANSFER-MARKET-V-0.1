"""Put the classic-rival entry on the real final MI CLUB dashboard.

The manager MI CLUB view is rebuilt by treasury_menu_patch after the roster
views are installed. Patching PlantelOVRView therefore does not affect the
screen that contains PLANTILLA / ECONOMÍA / TESORERÍA / VALOR DEL CLUB.
This wrapper is applied late and preserves every existing MI CLUB control.
"""

from __future__ import annotations

import discord

import classic_rival_discord_patch as classic_discord
import my_club_menu_patch as my_club


def apply_classic_rival_myclub_button_patch(runtime, bot) -> None:
    if getattr(bot, "_ajpa_classic_rival_myclub_button_patch", False):
        return

    base_view = my_club.MyClubSectionView
    if getattr(base_view, "_ajpa_classic_rival_myclub_button", False):
        bot._ajpa_classic_rival_myclub_button_patch = True
        return

    class ClassicRivalMyClubSectionView(base_view):
        def __init__(self, roster_callback):
            super().__init__(roster_callback)
            if any(
                getattr(item, "custom_id", None) == "ajap_my_club_clasico"
                for item in self.children
            ):
                return

            button = discord.ui.Button(
                label="CLÁSICO RIVAL",
                emoji="🔥",
                style=discord.ButtonStyle.secondary,
                custom_id="ajap_my_club_clasico",
                row=2,
            )
            button.callback = self._open_classic
            self.add_item(button)

        async def _open_classic(self, interaction: discord.Interaction):
            # Uses the same shared classic tables and response flow as /clasico.
            await classic_discord.classic_command(interaction)

    ClassicRivalMyClubSectionView.__name__ = "MyClubSectionView"
    ClassicRivalMyClubSectionView._ajpa_classic_rival_myclub_button = True
    my_club.MyClubSectionView = ClassicRivalMyClubSectionView

    bot._ajpa_classic_rival_myclub_button_patch = True
    print("AJPA MI CLUB: botón CLÁSICO RIVAL instalado sobre la vista final de Tesorería")
