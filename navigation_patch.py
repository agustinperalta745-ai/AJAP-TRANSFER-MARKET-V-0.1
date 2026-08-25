"""Navigation helpers for AJAP Transfer Market.

Adds a way back to the main market panel from the most-used secondary screens,
so managers do not need to type /mercado again after viewing their squad,
publishing, browsing offers, administration, or clausulazos.
"""

import discord

import clausulazo_patch as clauses
import lyon_test_seed as lyon
import publish_ovr_patch as publish


class MainMenuButton(discord.ui.Button):
    def __init__(self, runtime, row=4, label="Menú principal"):
        super().__init__(
            label=label,
            emoji="🏠",
            style=discord.ButtonStyle.secondary,
            row=row,
        )
        self.runtime = runtime

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.edit_message(
            content=None,
            embed=self.runtime.panel_embed(interaction.user.id),
            view=self.runtime.MercadoView(),
        )


class MainMenuOnlyView(discord.ui.View):
    def __init__(self, runtime):
        super().__init__(timeout=300)
        self.add_item(MainMenuButton(runtime, row=0))


def _patch_plantel(runtime):
    base = lyon.PlantelOVRView

    class NavigablePlantelOVRView(base):
        def __init__(self, club: str):
            super().__init__(club)
            self.add_item(MainMenuButton(runtime, row=2, label="Volver al menú"))

    NavigablePlantelOVRView.__name__ = "PlantelOVRView"
    lyon.PlantelOVRView = NavigablePlantelOVRView
    runtime.PlantelOVRView = NavigablePlantelOVRView


def _patch_publish(runtime):
    base_ranges = publish.PublishOVRView

    class NavigablePublishOVRView(base_ranges):
        def __init__(self, club: str):
            super().__init__(club)
            self.add_item(MainMenuButton(runtime, row=2, label="Volver al menú"))

    NavigablePublishOVRView.__name__ = "PublishOVRView"
    publish.PublishOVRView = NavigablePublishOVRView
    runtime.PublishOVRView = NavigablePublishOVRView

    base_players = publish.PublishRangePlayersView

    class NavigablePublishRangePlayersView(base_players):
        def __init__(self, club: str, jugadores):
            super().__init__(club, jugadores)
            self.add_item(MainMenuButton(runtime, row=4, label="Menú principal"))

    NavigablePublishRangePlayersView.__name__ = "PublishRangePlayersView"
    publish.PublishRangePlayersView = NavigablePublishRangePlayersView


def _patch_core_secondary_views(runtime):
    base_transferibles = runtime.TransferiblesView

    class NavigableTransferiblesView(base_transferibles):
        def __init__(self, publicaciones):
            super().__init__(publicaciones)
            self.add_item(MainMenuButton(runtime, row=4))

    NavigableTransferiblesView.__name__ = "TransferiblesView"
    runtime.TransferiblesView = NavigableTransferiblesView

    base_ofertas = runtime.OfertasView

    class NavigableOfertasView(base_ofertas):
        def __init__(self, ofertas):
            super().__init__(ofertas)
            self.add_item(MainMenuButton(runtime, row=4))

    NavigableOfertasView.__name__ = "OfertasView"
    runtime.OfertasView = NavigableOfertasView

    base_admin = runtime.AdminView

    class NavigableAdminView(base_admin):
        def __init__(self):
            super().__init__()
            self.add_item(MainMenuButton(runtime, row=4, label="Volver al menú"))

    NavigableAdminView.__name__ = "AdminView"
    runtime.AdminView = NavigableAdminView


def _patch_clausulazo(runtime):
    base_home = clauses.ClauseHomeView

    class NavigableClauseHomeView(base_home):
        def __init__(self, buyer_club):
            super().__init__(buyer_club)
            self.add_item(MainMenuButton(runtime, row=4, label="Volver al menú"))

    NavigableClauseHomeView.__name__ = "ClauseHomeView"
    clauses.ClauseHomeView = NavigableClauseHomeView

    base_players = clauses.ClausePlayersView

    class BackToClauseHomeButton(discord.ui.Button):
        def __init__(self):
            super().__init__(
                label="Volver a Clausulazo",
                emoji="⬅️",
                style=discord.ButtonStyle.secondary,
                row=4,
            )

        async def callback(self, interaction: discord.Interaction):
            buyer = runtime.club_de(interaction.user.id)
            if not buyer:
                await interaction.response.edit_message(
                    content=None,
                    embed=runtime.panel_embed(interaction.user.id),
                    view=runtime.MercadoView(),
                )
                return
            await interaction.response.edit_message(
                content=None,
                embed=clauses.home_embed(interaction.user.id),
                view=clauses.ClauseHomeView(buyer),
            )

    class NavigableClausePlayersView(base_players):
        def __init__(self, players):
            super().__init__(players)
            self.add_item(BackToClauseHomeButton())
            self.add_item(MainMenuButton(runtime, row=4))

    NavigableClausePlayersView.__name__ = "ClausePlayersView"
    clauses.ClausePlayersView = NavigableClausePlayersView

    base_confirm = clauses.ClauseConfirmView

    class NavigableClauseConfirmView(base_confirm):
        def __init__(self, player_id):
            super().__init__(player_id)
            self.add_item(BackToClauseHomeButton())
            self.add_item(MainMenuButton(runtime, row=4))

    NavigableClauseConfirmView.__name__ = "ClauseConfirmView"
    clauses.ClauseConfirmView = NavigableClauseConfirmView


def _patch_market_view(runtime):
    base = runtime.MercadoView

    class NavigableMercadoView(base):
        def __init__(self):
            super().__init__()
            for item in self.children:
                if getattr(item, "custom_id", None) == "mercado_transferencias":
                    item.callback = self._nav_transferencias

        async def _nav_transferencias(self, interaction):
            await interaction.response.send_message(
                embed=runtime.transferencias_embed(),
                view=MainMenuOnlyView(runtime),
                ephemeral=True,
            )

    NavigableMercadoView.__name__ = "MercadoView"
    runtime.MercadoView = NavigableMercadoView


def apply_navigation_patch(runtime):
    if getattr(runtime, "_ajap_navigation_patch", False):
        return

    # Patch child views first; the final MercadoView then points back to all of them.
    _patch_plantel(runtime)
    _patch_publish(runtime)
    _patch_core_secondary_views(runtime)
    _patch_clausulazo(runtime)
    _patch_market_view(runtime)

    runtime._ajap_navigation_patch = True
    print("AJAP navegación activa: volver/menú principal sin repetir /mercado")
