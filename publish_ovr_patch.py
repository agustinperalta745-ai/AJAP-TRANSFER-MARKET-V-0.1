"""OVR range selector for the AJAP publish-player flow.

When a manager presses Publicar, show the same OVR buckets used by the roster
screen first. Only players currently eligible to publish are counted/shown.
"""

import discord

from lyon_test_seed import OVR_RANGES, RatedPublicarJugadorModal, fmt_money, player_rating

APP = None


def publishable_players(club: str):
    jugadores = [
        j
        for j in APP.jugadores_de_club(club, 50)
        if not APP.publicacion_activa_del_jugador(j["name"])
        and not APP.operacion_abierta_del_jugador(j["name"])
    ]
    return sorted(
        jugadores,
        key=lambda j: (-player_rating(j), str(j["name"]).casefold()),
    )


def publish_ranges_embed(club: str):
    jugadores = publishable_players(club)
    embed = discord.Embed(
        title=f"📤 Publicar jugador • {club}",
        description=(
            "Elegí el **rango de OVR** del jugador que querés publicar.\n"
            "Solo aparecen jugadores que todavía están disponibles para publicar."
        ),
    )
    for label, min_ovr, max_ovr in OVR_RANGES:
        count = sum(min_ovr <= player_rating(j) <= max_ovr for j in jugadores)
        embed.add_field(
            name=f"⭐ OVR {label}",
            value=f"**{count}** jugador{'es' if count != 1 else ''}",
            inline=True,
        )
    embed.set_footer(text=f"{len(jugadores)} jugador(es) disponibles para publicar")
    return embed


def publish_range_embed(club: str, label: str, jugadores):
    embed = discord.Embed(
        title=f"📤 Publicar jugador • {club} • OVR {label}",
        description="Elegí uno de estos jugadores para continuar con la publicación.",
    )
    for j in jugadores[:25]:
        rating = j["rating"] if "rating" in j.keys() else None
        min_sale = j["min_sale_value"] if "min_sale_value" in j.keys() else None
        value = f"**{j['position']}**"
        if rating is not None:
            value += f" • ⭐ {rating}"
        if min_sale is not None:
            value += f" • 💰 mín. {fmt_money(min_sale)}"
        embed.add_field(name=j["name"], value=value, inline=False)
    embed.set_footer(text=f"{len(jugadores)} jugador(es) disponibles en OVR {label}")
    return embed


class PublishPlayerSelect(discord.ui.Select):
    def __init__(self, club: str, jugadores, group_index: int = 0):
        self.club = club
        options = []
        for j in jugadores:
            rating = j["rating"] if "rating" in j.keys() else None
            min_sale = j["min_sale_value"] if "min_sale_value" in j.keys() else None
            details = [j["position"]]
            if rating is not None:
                details.append(f"OVR {rating}")
            if min_sale is not None:
                details.append(f"Mín {fmt_money(min_sale)}")
            options.append(
                discord.SelectOption(
                    label=j["name"][:100],
                    description=" • ".join(details)[:100],
                    value=str(j["id"]),
                )
            )
        super().__init__(
            placeholder="Elegí un jugador" if group_index == 0 else f"Elegí un jugador • grupo {group_index + 1}",
            min_values=1,
            max_values=1,
            options=options,
            row=group_index,
        )

    async def callback(self, interaction: discord.Interaction):
        current_team = APP.club_de(interaction.user.id)
        if not current_team or current_team.casefold() != self.club.casefold():
            await interaction.response.send_message(
                "⛔ Este plantel ya no está vinculado a tu cuenta.",
                ephemeral=True,
            )
            return

        ficha = APP.jugador_por_id(int(self.values[0]))
        if not ficha or ficha["club"].casefold() != self.club.casefold():
            await interaction.response.send_message(
                "⚠️ Ese jugador ya no está disponible en tu plantel.",
                ephemeral=True,
            )
            return
        if APP.publicacion_activa_del_jugador(ficha["name"]) or APP.operacion_abierta_del_jugador(ficha["name"]):
            await interaction.response.send_message(
                "⚠️ Ese jugador ya no está disponible para publicar.",
                ephemeral=True,
            )
            return

        await interaction.response.send_modal(RatedPublicarJugadorModal(ficha))


class BackToPublishRanges(discord.ui.Button):
    def __init__(self, club: str, row: int):
        super().__init__(
            label="Volver a rangos",
            emoji="📊",
            style=discord.ButtonStyle.secondary,
            row=row,
        )
        self.club = club

    async def callback(self, interaction: discord.Interaction):
        current_team = APP.club_de(interaction.user.id)
        if not current_team or current_team.casefold() != self.club.casefold():
            await interaction.response.send_message(
                "⛔ Este plantel ya no está vinculado a tu cuenta.",
                ephemeral=True,
            )
            return
        await interaction.response.edit_message(
            embed=publish_ranges_embed(self.club),
            view=PublishOVRView(self.club),
        )


class PublishRangePlayersView(discord.ui.View):
    def __init__(self, club: str, jugadores):
        super().__init__(timeout=300)
        groups = [jugadores[i:i + 25] for i in range(0, len(jugadores), 25)]
        for group_index, group in enumerate(groups[:4]):
            self.add_item(PublishPlayerSelect(club, group, group_index))
        self.add_item(BackToPublishRanges(club, row=min(len(groups), 4)))


class PublishOVRRangeButton(discord.ui.Button):
    def __init__(self, club: str, label: str, min_ovr: int, max_ovr: int, count: int, row: int):
        super().__init__(
            label=f"{label} ({count})",
            emoji="⭐",
            style=discord.ButtonStyle.primary if count else discord.ButtonStyle.secondary,
            disabled=count == 0,
            row=row,
        )
        self.club = club
        self.range_label = label
        self.min_ovr = min_ovr
        self.max_ovr = max_ovr

    async def callback(self, interaction: discord.Interaction):
        current_team = APP.club_de(interaction.user.id)
        if not current_team or current_team.casefold() != self.club.casefold():
            await interaction.response.send_message(
                "⛔ Este plantel ya no está vinculado a tu cuenta.",
                ephemeral=True,
            )
            return

        jugadores = [
            j
            for j in publishable_players(self.club)
            if self.min_ovr <= player_rating(j) <= self.max_ovr
        ]
        if not jugadores:
            await interaction.response.edit_message(
                embed=publish_ranges_embed(self.club),
                view=PublishOVRView(self.club),
            )
            return

        await interaction.response.edit_message(
            embed=publish_range_embed(self.club, self.range_label, jugadores),
            view=PublishRangePlayersView(self.club, jugadores),
        )


class PublishOVRView(discord.ui.View):
    def __init__(self, club: str):
        super().__init__(timeout=300)
        jugadores = publishable_players(club)
        for index, (label, min_ovr, max_ovr) in enumerate(OVR_RANGES):
            count = sum(min_ovr <= player_rating(j) <= max_ovr for j in jugadores)
            self.add_item(
                PublishOVRRangeButton(
                    club,
                    label,
                    min_ovr,
                    max_ovr,
                    count,
                    row=0 if index < 5 else 1,
                )
            )


def build_publish_ovr_market_view(base_view):
    class PublishOVRMarketView(base_view):
        async def _fixed_publicar(self, interaction):
            team = APP.club_de(interaction.user.id)
            if not team:
                await super()._fixed_publicar(interaction)
                return

            jugadores = publishable_players(team)
            if not jugadores:
                await interaction.response.send_message(
                    "⚠️ No tenés jugadores disponibles para publicar.",
                    ephemeral=True,
                )
                return

            await interaction.response.send_message(
                embed=publish_ranges_embed(team),
                view=PublishOVRView(team),
                ephemeral=True,
            )

    PublishOVRMarketView.__name__ = "MercadoView"
    return PublishOVRMarketView


def apply_publish_ovr_patch(main_module):
    global APP
    APP = main_module
    main_module.PublishOVRView = PublishOVRView
    main_module.MercadoView = build_publish_ovr_market_view(main_module.MercadoView)
    print("AJAP publish flow enabled: OVR range selector before player selection")
