"""Global player search for AJAP Transfer Market.

Replaces the old search that only looked at active transfer publications.
Managers can now find every player loaded in roster_players, whether or not the
player is listed. A player can only be offered for when an active publication
exists and the market is open; otherwise the search is informational only.
"""

import discord

APP = None


def _rating(player):
    if "rating" not in player.keys() or player["rating"] is None:
        return -1
    try:
        return int(player["rating"])
    except (TypeError, ValueError):
        return -1


def _fmt_money(value):
    if value is None:
        return "Sin definir"
    try:
        return f"${int(value):,}".replace(",", ".")
    except (TypeError, ValueError):
        return str(value)


def buscar_jugadores_global(nombre="", posicion="", club="", ovr_min="", limit=25):
    nombre = (nombre or "").strip().casefold()
    posicion = (posicion or "").strip().casefold()
    club = (club or "").strip().casefold()
    raw_ovr = (ovr_min or "").strip()
    min_ovr = int(raw_ovr) if raw_ovr.isdigit() else None

    with APP.db() as conn:
        rows = conn.execute(
            "SELECT * FROM roster_players ORDER BY name COLLATE NOCASE ASC"
        ).fetchall()

    # Also allow searching by the stable AJAP player code in the Name field.
    requested_id = None
    if nombre.startswith("ajap-"):
        suffix = nombre.split("-", 1)[1]
        if suffix.isdigit():
            requested_id = int(suffix)

    results = []
    for player in rows:
        if requested_id is not None:
            if int(player["id"]) != requested_id:
                continue
        elif nombre and nombre not in str(player["name"]).casefold():
            continue
        if posicion and posicion not in str(player["position"]).casefold():
            continue
        if club and club not in str(player["club"]).casefold():
            continue
        if min_ovr is not None and _rating(player) < min_ovr:
            continue
        results.append(player)

    results.sort(key=lambda p: (-_rating(p), str(p["name"]).casefold()))
    return results[:limit]


def jugador_global_embed(player):
    publication = APP.publicacion_activa_del_jugador(player["name"])
    pending = APP.operacion_abierta_del_jugador(player["name"])
    rating = player["rating"] if "rating" in player.keys() else None
    minimum = player["min_sale_value"] if "min_sale_value" in player.keys() else None

    if pending:
        status = "🟡 Operación aceptada pendiente de administración"
    elif publication:
        status = "🟢 Transferible"
    else:
        status = "⚪ No transferible"

    embed = discord.Embed(
        title=f"🔎 {player['name']}",
        description="Ficha global del jugador en AJAP Transfer Market.",
    )
    embed.add_field(name="🆔 ID", value=f"`{APP.player_code(player['id'])}`", inline=True)
    embed.add_field(name="🏟️ Club actual", value=player["club"], inline=True)
    embed.add_field(name="📍 Posición", value=player["position"], inline=True)
    embed.add_field(name="⭐ OVR", value=str(rating) if rating is not None else "Sin cargar", inline=True)
    embed.add_field(name="💰 Valor mínimo", value=_fmt_money(minimum), inline=True)
    embed.add_field(name="📋 Estado", value=status, inline=True)

    if publication:
        embed.add_field(name="🔁 Tipo", value=publication["operation_type"], inline=True)
        embed.add_field(name="💵 Precio pedido", value=publication["price"], inline=True)
        embed.add_field(name="📝 Condiciones", value=publication["detail"], inline=False)
        if APP.mercado_abierto():
            embed.set_footer(text="Mercado abierto • Si no es de tu club, podés ofertar desde esta ficha")
        else:
            embed.set_footer(text="Mercado cerrado • La publicación se puede consultar, pero no ofertar")
    else:
        embed.set_footer(text="No está publicado • La búsqueda es solo informativa")

    return embed, publication


def resultados_globales_embed(players):
    embed = discord.Embed(
        title=f"🔎 Búsqueda global • {len(players)} resultado(s)",
        description=(
            "Busca en **todos los planteles cargados**, no solo en Transferibles.\n"
            "Elegí un jugador abajo para abrir su ficha completa."
        ),
    )
    if not players:
        embed.description = "No encontré jugadores que coincidan con esos filtros."
        return embed

    lines = []
    for player in players:
        publication = APP.publicacion_activa_del_jugador(player["name"])
        pending = APP.operacion_abierta_del_jugador(player["name"])
        if pending:
            status = "🟡 Pendiente"
        elif publication:
            status = "🟢 Transferible"
        else:
            status = "⚪ No transferible"
        rating = _rating(player)
        ovr = str(rating) if rating >= 0 else "—"
        lines.append(
            f"`{APP.player_code(player['id'])}` • **{player['name']}** • ⭐ {ovr} • {player['club']} • {status}"
        )

    embed.description += "\n\n" + "\n".join(lines)
    embed.set_footer(text="Máximo 25 resultados por búsqueda")
    return embed


class MainMenuButton(discord.ui.Button):
    def __init__(self, row=4):
        super().__init__(
            label="Volver al menú",
            emoji="🏠",
            style=discord.ButtonStyle.secondary,
            row=row,
        )

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.edit_message(
            content=None,
            embed=APP.panel_embed(interaction.user.id),
            view=APP.MercadoView(),
        )


class OfferFromSearchButton(discord.ui.Button):
    def __init__(self, publication, user_id):
        user_club = APP.club_de(user_id)
        own_player = bool(
            user_club
            and str(user_club).casefold() == str(publication["club"]).casefold()
        )
        market_open = APP.mercado_abierto()
        super().__init__(
            label="Hacer oferta" if market_open else "Mercado cerrado",
            emoji="💰" if market_open else "🔒",
            style=discord.ButtonStyle.success if market_open else discord.ButtonStyle.secondary,
            disabled=(not market_open) or own_player,
            row=0,
        )
        self.publication_id = int(publication["id"])

    async def callback(self, interaction: discord.Interaction):
        if not APP.mercado_abierto():
            await interaction.response.send_message(
                "🔒 El mercado está cerrado. Podés consultar la ficha, pero todavía no ofertar.",
                ephemeral=True,
            )
            return
        publication = APP.publicacion_por_id(self.publication_id)
        if not publication:
            await interaction.response.send_message(
                "⚠️ Ese jugador ya no está publicado.", ephemeral=True
            )
            return
        await interaction.response.send_modal(APP.OfertaModal(publication))


class PlayerDetailView(discord.ui.View):
    def __init__(self, publication, user_id):
        super().__init__(timeout=300)
        if publication:
            self.add_item(OfferFromSearchButton(publication, user_id))
        self.add_item(MainMenuButton(row=4))


class GlobalPlayerSelect(discord.ui.Select):
    def __init__(self, players):
        options = []
        for player in players:
            publication = APP.publicacion_activa_del_jugador(player["name"])
            status = "Transferible" if publication else "No transferible"
            rating = _rating(player)
            parts = [player["club"], status]
            if rating >= 0:
                parts.insert(0, f"OVR {rating}")
            options.append(
                discord.SelectOption(
                    label=player["name"][:100],
                    description=" • ".join(parts)[:100],
                    value=str(player["id"]),
                )
            )
        super().__init__(
            placeholder="Elegí un jugador para ver su ficha",
            min_values=1,
            max_values=1,
            options=options,
            row=0,
        )

    async def callback(self, interaction: discord.Interaction):
        player = APP.jugador_por_id(int(self.values[0]))
        if not player:
            await interaction.response.send_message(
                "⚠️ Ese jugador ya no existe en la base.", ephemeral=True
            )
            return
        embed, publication = jugador_global_embed(player)
        await interaction.response.send_message(
            embed=embed,
            view=PlayerDetailView(publication, interaction.user.id),
            ephemeral=True,
        )


class GlobalSearchResultsView(discord.ui.View):
    def __init__(self, players):
        super().__init__(timeout=300)
        if players:
            self.add_item(GlobalPlayerSelect(players))
        self.add_item(MainMenuButton(row=4))


class BuscarJugadoresGlobalModal(discord.ui.Modal, title="Buscar jugador global"):
    nombre = discord.ui.TextInput(
        label="Nombre o ID AJAP",
        placeholder="Ej: Ronaldinho o AJAP-000123",
        required=False,
        max_length=60,
    )
    posicion = discord.ui.TextInput(
        label="Posición",
        placeholder="Ej: CF / CMF / GK",
        required=False,
        max_length=20,
    )
    club = discord.ui.TextInput(
        label="Club actual",
        required=False,
        max_length=60,
    )
    ovr_min = discord.ui.TextInput(
        label="OVR mínimo",
        placeholder="Ej: 80",
        required=False,
        max_length=3,
    )

    async def on_submit(self, interaction: discord.Interaction):
        raw_ovr = self.ovr_min.value.strip()
        if raw_ovr and (not raw_ovr.isdigit() or not 0 <= int(raw_ovr) <= 99):
            await interaction.response.send_message(
                "⚠️ El OVR mínimo debe ser un número entre 0 y 99.", ephemeral=True
            )
            return

        players = buscar_jugadores_global(
            self.nombre.value,
            self.posicion.value,
            self.club.value,
            raw_ovr,
            25,
        )
        await interaction.response.send_message(
            embed=resultados_globales_embed(players),
            view=GlobalSearchResultsView(players),
            ephemeral=True,
        )


def apply_global_player_search_patch(main_module):
    global APP
    APP = main_module

    # The existing MercadoView callback resolves BuscarJugadoresModal from the
    # runtime module at click time, so replacing this symbol upgrades Search
    # without rebuilding or duplicating the market menu.
    main_module.buscar_jugadores_global = buscar_jugadores_global
    main_module.BuscarJugadoresModal = BuscarJugadoresGlobalModal
    main_module.GlobalSearchResultsView = GlobalSearchResultsView
    main_module.jugador_global_embed = jugador_global_embed
    main_module._ajap_global_player_search = True

    print("AJAP búsqueda global activa: todos los planteles, publicados o no")
