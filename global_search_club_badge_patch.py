"""Show each club's manual Discord badge inside global-search select menus.

The guided player search already uses discord.ui.Select, so every option can carry
an Emoji/PartialEmoji. We reuse the exact same manual club->emoji-name mapping as
the main AJAP team selector and always resolve the emoji from the guild that is
handling the current interaction.
"""

from __future__ import annotations

import guild_isolation_patch as guild_isolation
import global_player_search_patch as global_search
import team_badge_selector_patch as team_badges


BOT = None


def _interaction_guild():
    if BOT is None:
        return None
    try:
        guild_id = int(guild_isolation._CURRENT_GUILD_ID.get())
    except Exception:
        return None
    return BOT.get_guild(guild_id)


def _club_badge(club: str):
    """Resolve one configured badge only from the active Discord guild."""
    guild = _interaction_guild()
    if guild is None:
        return None

    expected_name = team_badges.MANUAL_EMOJI_NAMES.get(str(club))
    if not expected_name:
        return None

    wanted = expected_name.casefold()
    emoji = next(
        (
            item
            for item in guild.emojis
            if str(getattr(item, "name", "")).casefold() == wanted
        ),
        None,
    )
    if emoji is None or not getattr(emoji, "available", True):
        return None
    return emoji


def apply_global_search_club_badge_patch(runtime, bot):
    """Decorate club/player dropdowns without changing any search/filter logic."""
    global BOT
    BOT = bot

    if getattr(runtime, "_ajap_global_search_club_badges", False):
        return

    BaseClubSelect = global_search.ClubSelect
    BasePlayerSelect = global_search.GlobalPlayerSelect

    class BadgedClubSelect(BaseClubSelect):
        def __init__(self, state):
            super().__init__(state)
            for option in self.options:
                if not option.value:
                    continue
                badge = _club_badge(option.value)
                if badge is not None:
                    option.emoji = badge

    class BadgedGlobalPlayerSelect(BasePlayerSelect):
        def __init__(self, players, state=None):
            player_list = list(players)
            super().__init__(player_list, state)
            club_by_id = {str(player["id"]): str(player["club"]) for player in player_list}
            for option in self.options:
                club = club_by_id.get(str(option.value))
                if not club:
                    continue
                badge = _club_badge(club)
                if badge is not None:
                    option.emoji = badge

    global_search.ClubSelect = BadgedClubSelect
    global_search.GlobalPlayerSelect = BadgedGlobalPlayerSelect
    runtime._ajap_global_search_club_badges = True
    print("AJAP búsqueda global: escudos de club activos en selectores")
