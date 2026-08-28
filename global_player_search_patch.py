"""Guided global player search for AJAP Transfer Market.

The old search was a four-field Discord modal. On mobile that forced managers to
remember the exact spelling of positions/clubs and made finding players tedious.
This version keeps the same global roster search, but exposes it as a guided UI:

- position selector
- club selector
- OVR minimum selector
- optional name/AJAP-ID field (one small modal only when needed)
- partial, accent-insensitive and typo-tolerant name matching
- results selector with a clean back-to-filters flow

All filters are optional. A manager can therefore search e.g. CF + 80+, a club
only, a partial name such as "ronal", or simply browse the best-rated players.
"""

from __future__ import annotations

from difflib import SequenceMatcher
import unicodedata

import discord

APP = None

POSITIONS = ("GK", "CB", "SB", "DMF", "CMF", "AMF", "SMF", "WF", "SS", "CF")
OVR_STEPS = (60, 65, 70, 75, 80, 85, 90)


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


def _norm(value):
    """Case/accent-insensitive text used by every human-entered filter."""
    raw = unicodedata.normalize("NFKD", str(value or ""))
    raw = "".join(ch for ch in raw if not unicodedata.combining(ch))
    return " ".join(raw.casefold().strip().split())


def _looks_like_player_id(query):
    raw = _norm(query).replace(" ", "")
    if raw.startswith("ajap-"):
        raw = raw[5:]
    if raw.isdigit():
        try:
            return int(raw)
        except ValueError:
            return None
    return None


def _name_matches(query, player_name):
    """Friendly match: substring first, then conservative typo tolerance."""
    query = _norm(query)
    name = _norm(player_name)
    if not query:
        return True
    if query in name:
        return True

    q_tokens = [token for token in query.split() if token]
    n_tokens = [token for token in name.split() if token]
    if q_tokens and all(
        any(q in n or SequenceMatcher(None, q, n).ratio() >= 0.78 for n in n_tokens)
        for q in q_tokens
    ):
        return True

    # Avoid fuzzy matching very short strings: it creates too many false hits.
    return len(query) >= 4 and SequenceMatcher(None, query, name).ratio() >= 0.70


def buscar_jugadores_global(nombre="", posicion="", club="", ovr_min="", limit=25):
    nombre = (nombre or "").strip()
    posicion_norm = _norm(posicion)
    club_norm = _norm(club)
    raw_ovr = str(ovr_min or "").strip()
    min_ovr = int(raw_ovr) if raw_ovr.isdigit() else None

    with APP.db() as conn:
        rows = conn.execute(
            "SELECT * FROM roster_players ORDER BY name COLLATE NOCASE ASC"
        ).fetchall()

    requested_id = _looks_like_player_id(nombre) if nombre else None
    results = []
    for player in rows:
        if requested_id is not None:
            if int(player["id"]) != requested_id:
                continue
        elif nombre and not _name_matches(nombre, player["name"]):
            continue

        if posicion_norm and posicion_norm not in _norm(player["position"]):
            continue
        if club_norm and club_norm != _norm(player["club"]):
            continue
        if min_ovr is not None and _rating(player) < min_ovr:
            continue
        results.append(player)

    results.sort(key=lambda p: (-_rating(p), _norm(p["name"])))
    return results[: max(1, int(limit))]


def _club_options():
    """Return active clubs first, falling back to clubs present in the roster."""
    clubs = []
    try:
        with APP.db() as conn:
            table = conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name='league_teams' LIMIT 1"
            ).fetchone()
            if table:
                rows = conn.execute(
                    "SELECT name FROM league_teams WHERE active = 1 ORDER BY name COLLATE NOCASE"
                ).fetchall()
                clubs = [str(row["name"] or "").strip() for row in rows]
            if not clubs:
                rows = conn.execute(
                    "SELECT DISTINCT club FROM roster_players WHERE TRIM(club) != '' ORDER BY club COLLATE NOCASE"
                ).fetchall()
                clubs = [str(row["club"] or "").strip() for row in rows]
    except Exception as exc:
        print(f"WARNING AJAP búsqueda guiada: no se pudieron listar clubes: {exc}")
        return []

    unique = []
    seen = set()
    for club in clubs:
        key = _norm(club)
        if club and key not in seen:
            seen.add(key)
            unique.append(club)
    return unique


def _state(state=None, **changes):
    base = {
        "nombre": "",
        "posicion": "",
        "club": "",
        "ovr_min": "",
    }
    if state:
        base.update({key: str(value or "") for key, value in state.items() if key in base})
    base.update({key: str(value or "") for key, value in changes.items() if key in base})
    return base


def _filter_summary(state):
    values = []
    if state.get("nombre"):
        values.append(f"👤 **{state['nombre']}**")
    if state.get("posicion"):
        values.append(f"📍 **{state['posicion']}**")
    if state.get("club"):
        values.append(f"🏟️ **{state['club']}**")
    if state.get("ovr_min"):
        values.append(f"⭐ **{state['ovr_min']}+**")
    return " • ".join(values) if values else "Sin filtros • muestra los mejores OVR"


def search_panel_embed(state=None):
    state = _state(state)
    embed = discord.Embed(
        title="🔎 BUSCAR JUGADOR",
        description=(
            "Usá los selectores de abajo. **No hace falta completar todo.**\n"
            "El nombre es opcional y acepta partes del nombre o pequeños errores."
        ),
    )
    embed.add_field(name="Filtros actuales", value=_filter_summary(state), inline=False)
    embed.add_field(
        name="Ejemplos rápidos",
        value="`CF + 80+` • `Ajax` • `ronal` • `AJAP-000123`",
        inline=False,
    )
    embed.set_footer(text="Elegí filtros y tocá BUSCAR")
    return embed


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

    key_attributes = None
    formatter = getattr(APP, "pes6_format_key_attributes", None)
    if formatter:
        key_attributes = formatter(player)

    embed.add_field(
        name="⭐ Atributos clave • PES 6",
        value=(
            key_attributes
            or "📊 Los atributos originales de PES 6 de este jugador todavía no están cargados."
        ),
        inline=False,
    )

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


def resultados_globales_embed(players, state=None):
    embed = discord.Embed(
        title=f"🔎 Búsqueda global • {len(players)} resultado(s)",
        description=(
            "Busca en **todos los planteles cargados**, no solo en Transferibles.\n"
            "Elegí un jugador abajo para abrir su ficha completa."
        ),
    )
    if state:
        embed.add_field(name="Filtros", value=_filter_summary(_state(state)), inline=False)
    if not players:
        embed.description = "No encontré jugadores que coincidan con esos filtros."
        embed.set_footer(text="Volvé a filtros y probá una búsqueda más amplia")
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
    embed.set_footer(text="Máximo 25 resultados • ordenados por OVR")
    return embed


class MainMenuButton(discord.ui.Button):
    def __init__(self, row=4):
        super().__init__(
            label="Menú",
            emoji="🏠",
            style=discord.ButtonStyle.secondary,
            row=row,
        )

    async def callback(self, interaction: discord.Interaction):
        factory = getattr(APP, "manager_market_view_for", None)
        try:
            view = factory(interaction) if callable(factory) else APP.MercadoView()
        except Exception:
            view = APP.MercadoView()
        await interaction.response.edit_message(
            content=None,
            embed=APP.panel_embed(interaction.user.id),
            view=view,
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


class BackToSearchButton(discord.ui.Button):
    def __init__(self, state, row=4, label="Filtros"):
        super().__init__(
            label=label,
            emoji="⬅️",
            style=discord.ButtonStyle.secondary,
            row=row,
        )
        self.state = _state(state)

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.edit_message(
            content=None,
            embed=search_panel_embed(self.state),
            view=GuidedSearchView(self.state),
        )


class BackToResultsButton(discord.ui.Button):
    def __init__(self, state, row=1):
        super().__init__(
            label="Volver a resultados",
            emoji="⬅️",
            style=discord.ButtonStyle.secondary,
            row=row,
        )
        self.state = _state(state)

    async def callback(self, interaction: discord.Interaction):
        players = buscar_jugadores_global(
            self.state["nombre"],
            self.state["posicion"],
            self.state["club"],
            self.state["ovr_min"],
            25,
        )
        await interaction.response.edit_message(
            content=None,
            embed=resultados_globales_embed(players, self.state),
            view=GlobalSearchResultsView(players, self.state),
        )


class PlayerDetailView(discord.ui.View):
    def __init__(self, publication, user_id, state=None):
        super().__init__(timeout=300)
        self.state = _state(state)
        if publication:
            self.add_item(OfferFromSearchButton(publication, user_id))
        self.add_item(BackToResultsButton(self.state, row=1))
        self.add_item(MainMenuButton(row=4))


class GlobalPlayerSelect(discord.ui.Select):
    def __init__(self, players, state=None):
        self.state = _state(state)
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
        await interaction.response.edit_message(
            content=None,
            embed=embed,
            view=PlayerDetailView(publication, interaction.user.id, self.state),
        )


class GlobalSearchResultsView(discord.ui.View):
    def __init__(self, players, state=None):
        super().__init__(timeout=300)
        self.state = _state(state)
        if players:
            self.add_item(GlobalPlayerSelect(players, self.state))
        self.add_item(BackToSearchButton(self.state, row=4, label="Filtros"))
        self.add_item(MainMenuButton(row=4))


class PositionSelect(discord.ui.Select):
    def __init__(self, state):
        self.state = _state(state)
        current = self.state["posicion"].upper()
        options = [
            discord.SelectOption(
                label="Todas las posiciones",
                value="",
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
            for position in POSITIONS
        )
        super().__init__(
            placeholder="📍 Posición",
            options=options,
            min_values=1,
            max_values=1,
            row=0,
        )

    async def callback(self, interaction: discord.Interaction):
        state = _state(self.state, posicion=self.values[0])
        await interaction.response.edit_message(embed=search_panel_embed(state), view=GuidedSearchView(state))


class ClubSelect(discord.ui.Select):
    def __init__(self, state):
        self.state = _state(state)
        current = self.state["club"]
        clubs = _club_options()
        if current and all(_norm(club) != _norm(current) for club in clubs):
            clubs.insert(0, current)
        clubs = clubs[:24]
        options = [
            discord.SelectOption(
                label="Todos los clubes",
                value="",
                emoji="🏟️",
                default=not current,
            )
        ]
        options.extend(
            discord.SelectOption(
                label=club[:100],
                value=club[:100],
                default=bool(current and _norm(current) == _norm(club)),
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
        state = _state(self.state, club=self.values[0])
        await interaction.response.edit_message(embed=search_panel_embed(state), view=GuidedSearchView(state))


class OVRSelect(discord.ui.Select):
    def __init__(self, state):
        self.state = _state(state)
        current = self.state["ovr_min"]
        options = [
            discord.SelectOption(
                label="Cualquier OVR",
                value="",
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
            for value in OVR_STEPS
        )
        super().__init__(
            placeholder="⭐ OVR mínimo",
            options=options,
            min_values=1,
            max_values=1,
            row=2,
        )

    async def callback(self, interaction: discord.Interaction):
        state = _state(self.state, ovr_min=self.values[0])
        await interaction.response.edit_message(embed=search_panel_embed(state), view=GuidedSearchView(state))


class NameSearchModal(discord.ui.Modal, title="Nombre o ID del jugador"):
    query = discord.ui.TextInput(
        label="Nombre parcial o ID AJAP",
        placeholder="Ej: ronal, ronaldino o AJAP-000123",
        required=False,
        max_length=60,
    )

    def __init__(self, state=None):
        super().__init__()
        self.state = _state(state)
        if self.state["nombre"]:
            self.query.default = self.state["nombre"]

    async def on_submit(self, interaction: discord.Interaction):
        state = _state(self.state, nombre=self.query.value.strip())
        players = buscar_jugadores_global(
            state["nombre"], state["posicion"], state["club"], state["ovr_min"], 25
        )
        await interaction.response.send_message(
            embed=resultados_globales_embed(players, state),
            view=GlobalSearchResultsView(players, state),
            ephemeral=True,
        )


# Compatibility name used by older/stale MercadoView callbacks. If one of those
# callbacks survives a deploy, it now opens a single friendly field instead of
# bringing back the old four-text-input form.
class BuscarJugadoresGlobalModal(NameSearchModal):
    pass


class NameFilterButton(discord.ui.Button):
    def __init__(self, state):
        self.state = _state(state)
        super().__init__(
            label="Nombre / ID" if not self.state["nombre"] else "Cambiar nombre",
            emoji="👤",
            style=discord.ButtonStyle.primary,
            row=3,
        )

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(NameSearchModal(self.state))


class ClearNameButton(discord.ui.Button):
    def __init__(self, state):
        self.state = _state(state)
        super().__init__(
            label="Quitar nombre",
            emoji="✖️",
            style=discord.ButtonStyle.secondary,
            row=3,
            disabled=not bool(self.state["nombre"]),
        )

    async def callback(self, interaction: discord.Interaction):
        state = _state(self.state, nombre="")
        await interaction.response.edit_message(embed=search_panel_embed(state), view=GuidedSearchView(state))


class RunSearchButton(discord.ui.Button):
    def __init__(self, state):
        self.state = _state(state)
        super().__init__(
            label="BUSCAR",
            emoji="🔎",
            style=discord.ButtonStyle.success,
            row=4,
        )

    async def callback(self, interaction: discord.Interaction):
        players = buscar_jugadores_global(
            self.state["nombre"],
            self.state["posicion"],
            self.state["club"],
            self.state["ovr_min"],
            25,
        )
        await interaction.response.edit_message(
            content=None,
            embed=resultados_globales_embed(players, self.state),
            view=GlobalSearchResultsView(players, self.state),
        )


class ResetSearchButton(discord.ui.Button):
    def __init__(self):
        super().__init__(
            label="Limpiar",
            emoji="🧹",
            style=discord.ButtonStyle.secondary,
            row=4,
        )

    async def callback(self, interaction: discord.Interaction):
        state = _state()
        await interaction.response.edit_message(embed=search_panel_embed(state), view=GuidedSearchView(state))


class GuidedSearchView(discord.ui.View):
    def __init__(self, state=None):
        super().__init__(timeout=300)
        state = _state(state)
        self.add_item(PositionSelect(state))
        self.add_item(ClubSelect(state))
        self.add_item(OVRSelect(state))
        self.add_item(NameFilterButton(state))
        self.add_item(ClearNameButton(state))
        self.add_item(RunSearchButton(state))
        self.add_item(ResetSearchButton())
        self.add_item(MainMenuButton(row=4))


def _install_guided_search_button(main_module):
    BaseMercadoView = main_module.MercadoView
    if getattr(BaseMercadoView, "_ajap_guided_global_search", False):
        return

    class GuidedSearchMercadoView(BaseMercadoView):
        def __init__(self):
            super().__init__()
            for item in self.children:
                if getattr(item, "custom_id", None) == "mercado_buscar":
                    item.callback = self._open_guided_search

        async def _open_guided_search(self, interaction: discord.Interaction):
            state = _state()
            await interaction.response.send_message(
                embed=search_panel_embed(state),
                view=GuidedSearchView(state),
                ephemeral=True,
            )

    GuidedSearchMercadoView.__name__ = "MercadoView"
    GuidedSearchMercadoView._ajap_guided_global_search = True
    main_module.MercadoView = GuidedSearchMercadoView


def apply_global_player_search_patch(main_module):
    global APP
    APP = main_module

    main_module.buscar_jugadores_global = buscar_jugadores_global
    main_module.BuscarJugadoresModal = BuscarJugadoresGlobalModal
    main_module.GlobalSearchResultsView = GlobalSearchResultsView
    main_module.GuidedSearchView = GuidedSearchView
    main_module.jugador_global_embed = jugador_global_embed

    # Patch the actual button callback before manager_menu_patch snapshots it.
    # This is what removes the four-field modal from the live /mercado interface.
    _install_guided_search_button(main_module)

    main_module._ajap_global_player_search = True
    print(
        "AJAP búsqueda global guiada activa: selectores posición/club/OVR + "
        "nombre parcial tolerante + resultados navegables"
    )
