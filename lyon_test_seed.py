"""Olympique de Lyon PES6 test roster for AJAP Transfer Market.

Seeds only Lyon once on the persistent database and extends the existing UI
with fixed OVR ratings and minimum sale values. The seed marker prevents
players from being reset to Lyon after future transfers/restarts.
"""

import discord

APP = None
LYON = "Olympique de Lyon"

# Fixed test ratings derived from the PES6-era attribute profile we agreed to use.
LYON_ROSTER = [
    ("Grégory Coupet", "GK", 87),
    ("Rémy Vercoutre", "GK", 73),
    ("Joan Hartock", "GK", 64),
    ("Cris", "CB", 86),
    ("Éric Abidal", "LB/CB", 84),
    ("Cláudio Caçapa", "CB", 82),
    ("Sébastien Squillaci", "CB", 82),
    ("Anthony Réveillère", "RB", 80),
    ("Patrick Müller", "CB", 78),
    ("François Clerc", "RB", 76),
    ("Jérémy Berthod", "LB", 72),
    ("Mourad Benhamida", "DF", 65),
    ("Juninho Pernambucano", "AMF/CMF", 90),
    ("Tiago Mendes", "CMF", 84),
    ("Florent Malouda", "LMF", 84),
    ("Sidney Govou", "RMF/SS", 82),
    ("Kim Källström", "CMF/DMF", 81),
    ("Jérémy Toulalan", "DMF/CMF", 80),
    ("Alou Diarra", "DMF", 79),
    ("Hatem Ben Arfa", "AMF/SMF", 76),
    ("Romain Beynié", "CMF", 65),
    ("Yacine Hima", "MF", 63),
    ("Sylvain Idangar", "MF", 63),
    ("Sylvain Wiltord", "CF", 84),
    ("Fred", "CF", 83),
    ("John Carew", "CF", 82),
    ("Karim Benzema", "CF/SS", 74),
    ("Loïc Rémy", "CF", 66),
]

# The roster opens on these OVR groups instead of dumping every player at once.
OVR_RANGES = [
    ("90–99", 90, 99),
    ("80–89", 80, 89),
    ("70–79", 70, 79),
    ("60–69", 60, 69),
    ("50–59", 50, 59),
    ("Menos de 50", 0, 49),
]


def minimum_for_rating(rating: int) -> int:
    """Fixed-price curve with no age/potential component."""
    tiers = [
        (90, 30_000_000),
        (88, 25_000_000),
        (87, 22_000_000),
        (86, 18_000_000),
        (85, 16_000_000),
        (84, 14_000_000),
        (83, 12_000_000),
        (82, 10_000_000),
        (81, 8_500_000),
        (80, 7_500_000),
        (79, 6_500_000),
        (78, 5_500_000),
        (77, 4_800_000),
        (76, 4_000_000),
        (75, 3_500_000),
        (74, 3_000_000),
        (73, 2_500_000),
        (72, 2_200_000),
        (70, 1_800_000),
        (68, 1_500_000),
        (66, 1_200_000),
        (65, 1_000_000),
        (64, 900_000),
        (63, 800_000),
    ]
    for threshold, value in tiers:
        if rating >= threshold:
            return value
    return 600_000


def fmt_money(value: int) -> str:
    return f"${int(value):,}".replace(",", ".")


def player_rating(player):
    if "rating" not in player.keys() or player["rating"] is None:
        return -1
    return int(player["rating"])


def sorted_roster(club: str):
    jugadores = list(APP.jugadores_de_club(club, 50))
    return sorted(
        jugadores,
        key=lambda j: (-player_rating(j), str(j["name"]).casefold()),
    )


def players_in_range(club: str, min_ovr: int, max_ovr: int):
    return [
        j
        for j in sorted_roster(club)
        if min_ovr <= player_rating(j) <= max_ovr
    ]


def plantel_ranges_embed(club: str):
    jugadores = sorted_roster(club)
    embed = discord.Embed(
        title=f"🏟️ Plantilla • {club}",
        description=(
            "Elegí el **rango de media (OVR)** que querés ver.\n"
            "Dentro de cada rango, los jugadores aparecen ordenados de mayor a menor."
        ),
    )

    for label, min_ovr, max_ovr in OVR_RANGES:
        count = sum(min_ovr <= player_rating(j) <= max_ovr for j in jugadores)
        embed.add_field(
            name=f"⭐ OVR {label}",
            value=f"**{count}** jugador{'es' if count != 1 else ''}",
            inline=True,
        )

    embed.set_footer(text=f"{len(jugadores)} jugador(es) en la plantilla")
    return embed


def rated_plantel_embed(
    club: str,
    min_ovr: int | None = None,
    max_ovr: int | None = None,
    range_label: str | None = None,
):
    jugadores = sorted_roster(club)
    if min_ovr is not None and max_ovr is not None:
        jugadores = [
            j for j in jugadores if min_ovr <= player_rating(j) <= max_ovr
        ]

    title = f"🏟️ Plantel oficial • {club}"
    if range_label:
        title += f" • OVR {range_label}"
    embed = discord.Embed(title=title)

    if not jugadores:
        if range_label:
            embed.description = f"No tenés jugadores con OVR **{range_label}**."
        else:
            embed.description = "No hay jugadores cargados para este club."
        return embed

    lines = []
    for j in jugadores[:50]:
        rating = j["rating"] if "rating" in j.keys() else None
        min_sale = j["min_sale_value"] if "min_sale_value" in j.keys() else None
        extra = ""
        if rating is not None:
            extra += f" • ⭐ **{rating}**"
        if min_sale is not None:
            extra += f" • 💰 mín. **{fmt_money(min_sale)}**"
        lines.append(
            f"`{APP.player_code(j['id'])}` • **{j['position']}** • {j['name']}{extra}"
        )

    embed.description = "\n".join(lines)
    if range_label:
        embed.set_footer(
            text=(
                f"{len(jugadores)} jugador(es) en OVR {range_label} • "
                "ordenados de mayor a menor"
            )
        )
    else:
        embed.set_footer(
            text=f"{len(jugadores)} jugador(es) • valoración fija • mínimo para venta definitiva"
        )
    return embed


class OVRRangeButton(discord.ui.Button):
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

        await interaction.response.edit_message(
            embed=rated_plantel_embed(
                self.club,
                self.min_ovr,
                self.max_ovr,
                self.range_label,
            ),
            view=PlantelOVRView(self.club),
        )


class OVRResumenButton(discord.ui.Button):
    def __init__(self, club: str):
        super().__init__(
            label="Ver rangos",
            emoji="📊",
            style=discord.ButtonStyle.secondary,
            row=1,
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
            embed=plantel_ranges_embed(self.club),
            view=PlantelOVRView(self.club),
        )


class PlantelOVRView(discord.ui.View):
    def __init__(self, club: str):
        super().__init__(timeout=300)
        jugadores = sorted_roster(club)

        for index, (label, min_ovr, max_ovr) in enumerate(OVR_RANGES):
            count = sum(min_ovr <= player_rating(j) <= max_ovr for j in jugadores)
            self.add_item(
                OVRRangeButton(
                    club,
                    label,
                    min_ovr,
                    max_ovr,
                    count,
                    row=0 if index < 5 else 1,
                )
            )

        self.add_item(OVRResumenButton(club))


def ensure_schema_and_seed():
    with APP.db() as conn:
        APP.add_column_if_missing(conn, "roster_players", "rating", "INTEGER")
        APP.add_column_if_missing(conn, "roster_players", "min_sale_value", "INTEGER")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS seed_state (
                key TEXT PRIMARY KEY,
                applied_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        seeded = conn.execute(
            "SELECT 1 FROM seed_state WHERE key = 'lyon_pes6_test_v1'"
        ).fetchone()
        if seeded:
            return

        for name, position, rating in LYON_ROSTER:
            min_sale = minimum_for_rating(rating)
            conn.execute(
                """
                INSERT INTO roster_players
                    (name, position, club, added_by, rating, min_sale_value, updated_at)
                VALUES (?, ?, ?, NULL, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(name) DO UPDATE SET
                    position = excluded.position,
                    club = excluded.club,
                    rating = excluded.rating,
                    min_sale_value = excluded.min_sale_value,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (name, position, LYON, rating, min_sale),
            )

        conn.execute(
            "INSERT INTO seed_state (key) VALUES ('lyon_pes6_test_v1')"
        )


class RatedPublicarJugadorModal(discord.ui.Modal):
    def __init__(self, ficha):
        super().__init__(title=f"Publicar {ficha['name'][:30]}")
        self.jugador = ficha["name"]
        min_sale = ficha["min_sale_value"] if "min_sale_value" in ficha.keys() else None
        default_price = str(min_sale) if min_sale else None

        self.tipo = discord.ui.TextInput(
            label="Tipo de operación",
            placeholder="Transferencia / Préstamo / Intercambio",
            default="Transferencia",
            max_length=40,
        )
        self.precio = discord.ui.TextInput(
            label="Precio pedido",
            placeholder=f"Mínimo {fmt_money(min_sale)}" if min_sale else "Ej: 2500000",
            default=default_price,
            max_length=30,
        )
        self.detalle = discord.ui.TextInput(
            label="Observación",
            placeholder="Ej: Negociable / préstamo por 1 temporada",
            required=False,
            max_length=100,
        )
        self.add_item(self.tipo)
        self.add_item(self.precio)
        self.add_item(self.detalle)

    async def on_submit(self, interaction: discord.Interaction):
        club = APP.club_de(interaction.user.id)
        ficha = APP.jugador_por_nombre(self.jugador)
        if not club or not ficha or ficha["club"].casefold() != club.casefold():
            await interaction.response.send_message(
                "⛔ Ese jugador ya no pertenece a tu plantel.", ephemeral=True
            )
            return
        if APP.publicacion_activa_del_jugador(ficha["name"]):
            await interaction.response.send_message(
                f"⚠️ **{ficha['name']}** ya tiene una publicación activa.", ephemeral=True
            )
            return
        if APP.operacion_abierta_del_jugador(ficha["name"]):
            await interaction.response.send_message(
                f"⚠️ **{ficha['name']}** ya tiene una operación aceptada pendiente de administración.",
                ephemeral=True,
            )
            return

        tipo = APP.normalizar_tipo(self.tipo.value)
        raw_price = APP.price_number(self.precio.value)
        min_sale = ficha["min_sale_value"] if "min_sale_value" in ficha.keys() else None

        if raw_price is None:
            await interaction.response.send_message(
                "⚠️ El precio debe ser un número.", ephemeral=True
            )
            return
        if tipo == "TRANSFERENCIA" and min_sale and raw_price < min_sale:
            await interaction.response.send_message(
                f"⛔ **{ficha['name']}** tiene un mínimo de venta de **{fmt_money(min_sale)}**.",
                ephemeral=True,
            )
            return

        precio = APP.money(str(raw_price))
        detalle = self.detalle.value.strip() or "Sin observaciones"
        season = APP.temporada_activa()
        with APP.db() as conn:
            cur = conn.execute(
                """
                INSERT INTO publications
                (player, position, club, price, detail, owner_id, operation_type, season_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    ficha["name"],
                    ficha["position"],
                    club,
                    precio,
                    detalle,
                    interaction.user.id,
                    tipo,
                    season["id"] if season else None,
                ),
            )
            pub_id = cur.lastrowid

        embed = discord.Embed(
            title="✅ Jugador publicado",
            description=f"**{ficha['name']}** ya aparece en Transferibles.",
        )
        embed.add_field(name="ID", value=f"`{APP.player_code(ficha['id'])}`", inline=True)
        if ficha["rating"] is not None:
            embed.add_field(name="Valoración", value=f"⭐ {ficha['rating']}", inline=True)
        if min_sale is not None:
            embed.add_field(name="Mín. venta", value=fmt_money(min_sale), inline=True)
        embed.add_field(name="Tipo", value=tipo, inline=True)
        embed.add_field(name="Precio", value=precio, inline=True)
        embed.add_field(name="Detalle", value=detalle, inline=False)
        embed.set_footer(text=f"Publicación #{pub_id}")
        await interaction.response.send_message(embed=embed, ephemeral=True)


class RatedPublicarSelect(discord.ui.Select):
    def __init__(self, jugadores, group_index=0):
        options = []
        for j in jugadores:
            rating = j["rating"] if "rating" in j.keys() else None
            min_sale = j["min_sale_value"] if "min_sale_value" in j.keys() else None
            details = [APP.player_code(j["id"]), j["position"]]
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
            placeholder=f"Elegí un jugador • grupo {group_index + 1}",
            min_values=1,
            max_values=1,
            options=options,
            row=group_index,
        )

    async def callback(self, interaction: discord.Interaction):
        ficha = APP.jugador_por_id(int(self.values[0]))
        if not ficha:
            await interaction.response.send_message(
                "Jugador no disponible.", ephemeral=True
            )
            return
        await interaction.response.send_modal(RatedPublicarJugadorModal(ficha))


class RatedPublicarView(discord.ui.View):
    def __init__(self, jugadores):
        super().__init__(timeout=180)
        for group_index, start in enumerate(range(0, len(jugadores), 25)):
            self.add_item(
                RatedPublicarSelect(jugadores[start:start + 25], group_index=group_index)
            )


def build_lyon_market_view(base_view):
    class LyonMarketView(base_view):
        async def _fixed_mi_club(self, interaction):
            team = APP.club_de(interaction.user.id)
            if not team:
                await super()._fixed_mi_club(interaction)
                return

            await interaction.response.send_message(
                embed=plantel_ranges_embed(team),
                view=PlantelOVRView(team),
                ephemeral=True,
            )

        async def _fixed_publicar(self, interaction):
            team = APP.club_de(interaction.user.id)
            if not team:
                await super()._fixed_publicar(interaction)
                return
            jugadores = [
                j for j in APP.jugadores_de_club(team, 50)
                if not APP.publicacion_activa_del_jugador(j["name"])
                and not APP.operacion_abierta_del_jugador(j["name"])
            ]
            if not jugadores:
                await interaction.response.send_message(
                    "⚠️ No tenés jugadores disponibles para publicar. Puede que la plantilla todavía no esté cargada.",
                    ephemeral=True,
                )
                return
            await interaction.response.send_message(
                "📤 Elegí el jugador que querés publicar:",
                view=RatedPublicarView(jugadores),
                ephemeral=True,
            )

    LyonMarketView.__name__ = "MercadoView"
    return LyonMarketView


def apply_lyon_test_patch(main_module):
    global APP
    APP = main_module
    ensure_schema_and_seed()

    # Runtime UI hooks. Fixed-team assignment calls these through the main module.
    main_module.plantel_embed = rated_plantel_embed
    main_module.PlantelOVRView = PlantelOVRView
    main_module.PublicarJugadorModal = RatedPublicarJugadorModal
    main_module.PublicarSelect = RatedPublicarSelect
    main_module.PublicarView = RatedPublicarView
    main_module.MercadoView = build_lyon_market_view(main_module.MercadoView)

    print(
        f"Lyon PES6 test roster enabled: {len(LYON_ROSTER)} players with fixed ratings/minimum sale values."
    )
