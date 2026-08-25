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


def rated_plantel_embed(club: str):
    jugadores = APP.jugadores_de_club(club)
    embed = discord.Embed(title=f"🏟️ Plantel oficial • {club}")
    if not jugadores:
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
    embed.set_footer(
        text=f"{len(jugadores)} jugador(es) • valoración fija • mínimo para venta definitiva"
    )
    return embed


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
    def __init__(self, jugadores):
        options = []
        for j in jugadores[:25]:
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
            placeholder="Elegí un jugador de tu plantel",
            min_values=1,
            max_values=1,
            options=options,
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
        self.add_item(RatedPublicarSelect(jugadores))


def apply_lyon_test_patch(main_module):
    global APP
    APP = main_module
    ensure_schema_and_seed()

    # Runtime UI hooks. Fixed-team assignment calls these through the main module.
    main_module.plantel_embed = rated_plantel_embed
    main_module.PublicarJugadorModal = RatedPublicarJugadorModal
    main_module.PublicarSelect = RatedPublicarSelect
    main_module.PublicarView = RatedPublicarView

    print(
        f"Lyon PES6 test roster enabled: {len(LYON_ROSTER)} players with fixed ratings/minimum sale values."
    )
