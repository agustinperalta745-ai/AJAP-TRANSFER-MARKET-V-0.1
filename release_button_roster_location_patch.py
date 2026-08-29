"""Move LIBERAR JUGADOR from MI CLUB into the PLANTILLA section.

The release business rules stay in player_release_patch. This layer only changes
navigation/location:
- MI CLUB no longer shows the release action;
- PLANTILLA (OVR ranges screen) shows LIBERAR JUGADOR below the roster controls;
- leaving the release flow returns to PLANTILLA instead of MI CLUB.
"""

from __future__ import annotations

import discord

import lyon_test_seed as roster_ui
import my_club_menu_patch as my_club
import player_release_patch as release


RELEASE_CUSTOM_ID = "ajap_my_club_release_player"


def _remove_release_from_my_club():
    base_view = my_club.MyClubSectionView
    if getattr(base_view, "_ajap_release_removed_from_my_club", False):
        return False

    class MyClubWithoutRelease(base_view):
        def __init__(self, roster_callback):
            super().__init__(roster_callback)
            for item in list(self.children):
                if getattr(item, "custom_id", None) == RELEASE_CUSTOM_ID:
                    self.remove_item(item)

    MyClubWithoutRelease.__name__ = "MyClubSectionView"
    MyClubWithoutRelease._ajap_release_removed_from_my_club = True
    my_club.MyClubSectionView = MyClubWithoutRelease
    return True


def _add_release_to_roster():
    base_view = roster_ui.PlantelOVRView
    if getattr(base_view, "_ajap_release_inside_roster", False):
        return False

    class PlantelWithRelease(base_view):
        def __init__(self, club: str):
            super().__init__(club)
            # None is an intentional navigation marker: release back buttons
            # return to the PLANTILLA range screen instead of MI CLUB.
            self.add_item(release.ReleaseHubButton(None, row=2))

    PlantelWithRelease.__name__ = "PlantelOVRView"
    PlantelWithRelease._ajap_release_inside_roster = True
    roster_ui.PlantelOVRView = PlantelWithRelease
    return True


def _patch_release_back_navigation():
    button_cls = release.ReleaseBackToClubButton
    if getattr(button_cls.callback, "_ajap_back_to_roster", False):
        return False

    original_init = button_cls.__init__
    original_callback = button_cls.callback

    def init(self, roster_callback, row=2):
        original_init(self, roster_callback, row=row)
        if roster_callback is None:
            self.label = "Volver a PLANTILLA"
            self.emoji = "👥"

    async def callback(self, interaction: discord.Interaction):
        if self.roster_callback is not None:
            await original_callback(self, interaction)
            return

        app = release._app()
        club = app.club_de(interaction.user.id) if app is not None else None
        if not club:
            await interaction.response.send_message(
                "⚠️ No tenés un club asignado.",
                ephemeral=True,
            )
            return

        await interaction.response.edit_message(
            content=None,
            embed=roster_ui.plantel_ranges_embed(club),
            view=roster_ui.PlantelOVRView(club),
        )

    callback._ajap_back_to_roster = True
    button_cls.__init__ = init
    button_cls.callback = callback
    return True


_remove_release_from_my_club()
_add_release_to_roster()
_patch_release_back_navigation()

print(
    "AJAP liberaciones UI: LIBERAR JUGADOR movido de MI CLUB a PLANTILLA; "
    "volver retorna a PLANTILLA"
)
