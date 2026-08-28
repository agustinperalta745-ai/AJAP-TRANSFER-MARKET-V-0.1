"""Hotfix for the guided player-search selects.

Discord select option values cannot be empty strings. The guided search used
``value=""`` for the "all" choices (all positions, all clubs, any OVR), so
constructing the view raised before the interaction could be acknowledged and
Discord showed "la aplicación no ha respondido".

Use a non-empty sentinel in the component payload and translate it back to the
empty internal filter value inside each callback.
"""

from __future__ import annotations

import discord

import global_player_search_patch as search


ALL_VALUE = "__AJAP_ANY__"


class SafePositionSelect(discord.ui.Select):
    def __init__(self, state):
        self.state = search._state(state)
        current = self.state["posicion"].upper()
        options = [
            discord.SelectOption(
                label="Todas las posiciones",
                value=ALL_VALUE,
                emoji="⚽",
                default=not current,
            )
        ]
        options.extend(
            discord.SelectOption(
                label=position,
                value=position,
                default=current == position,
            )
            for position in search.POSITIONS
        )
        super().__init__(
            placeholder="📍 Posición",
            options=options,
            min_values=1,
            max_values=1,
            row=0,
        )

    async def callback(self, interaction: discord.Interaction):
        selected = self.values[0]
        state = search._state(
            self.state,
            posicion="" if selected == ALL_VALUE else selected,
        )
        await interaction.response.edit_message(
            embed=search.search_panel_embed(state),
            view=search.GuidedSearchView(state),
        )


class SafeClubSelect(discord.ui.Select):
    def __init__(self, state):
        self.state = search._state(state)
        current = self.state["club"]
        clubs = search._club_options()
        if current and all(search._norm(club) != search._norm(current) for club in clubs):
            clubs.insert(0, current)
        clubs = clubs[:24]

        options = [
            discord.SelectOption(
                label="Todos los clubes",
                value=ALL_VALUE,
                emoji="🏟️",
                default=not current,
            )
        ]
        options.extend(
            discord.SelectOption(
                label=club[:100],
                value=club[:100],
                default=bool(current and search._norm(current) == search._norm(club)),
            )
            for club in clubs
        )
        super().__init__(
            placeholder="🏟️ Club actual",
            options=options,
            min_values=1,
            max_values=1,
            row=1,
        )

    async def callback(self, interaction: discord.Interaction):
        selected = self.values[0]
        state = search._state(
            self.state,
            club="" if selected == ALL_VALUE else selected,
        )
        await interaction.response.edit_message(
            embed=search.search_panel_embed(state),
            view=search.GuidedSearchView(state),
        )


class SafeOVRSelect(discord.ui.Select):
    def __init__(self, state):
        self.state = search._state(state)
        current = self.state["ovr_min"]
        options = [
            discord.SelectOption(
                label="Cualquier OVR",
                value=ALL_VALUE,
                emoji="⭐",
                default=not current,
            )
        ]
        options.extend(
            discord.SelectOption(
                label=f"OVR {value}+",
                value=str(value),
                default=current == str(value),
            )
            for value in search.OVR_STEPS
        )
        super().__init__(
            placeholder="⭐ OVR mínimo",
            options=options,
            min_values=1,
            max_values=1,
            row=2,
        )

    async def callback(self, interaction: discord.Interaction):
        selected = self.values[0]
        state = search._state(
            self.state,
            ovr_min="" if selected == ALL_VALUE else selected,
        )
        await interaction.response.edit_message(
            embed=search.search_panel_embed(state),
            view=search.GuidedSearchView(state),
        )


# GuidedSearchView resolves these names from global_player_search_patch at
# construction time, so replacing them here fixes both new and navigated views.
search.PositionSelect = SafePositionSelect
search.ClubSelect = SafeClubSelect
search.OVRSelect = SafeOVRSelect

print("AJAP hotfix búsqueda guiada activo: selects sin valores vacíos")
