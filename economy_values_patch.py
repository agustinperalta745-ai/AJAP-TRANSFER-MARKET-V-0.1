"""AJAP economy values and dynamic release clauses.

Final economy rules:
- Market value is fixed only by AJAP OVR.
- Release clause = market value x4 (+300%), with a $10M minimum.
- Existing guild databases are migrated lazily on first use.
- Player cards/publications/search show both market value and clause.
- Clausulazo charges the selected player's real clause instead of a universal fee.
"""

from __future__ import annotations

import contextvars

import discord


APP = None
MIGRATION_KEY = "ajap_economy_values_v2"
MIN_CLAUSE_VALUE = 10_000_000
CLAUSE_MULTIPLIER = 4
_CLAUSE_PLAYER = contextvars.ContextVar("ajap_clause_player", default=None)


# OVR -> AJAP market value. Ratings below 60 inherit the lowest band so no
# roster player is left without an economic value.
def market_value_for_rating(rating) -> int:
    try:
        rating = int(rating)
    except (TypeError, ValueError):
        return 0

    tiers = [
        (95, 30_000_000),
        (94, 26_000_000),
        (93, 22_000_000),
        (92, 18_000_000),
        (91, 15_000_000),
        (90, 12_500_000),
        (89, 10_000_000),
        (87, 8_000_000),
        (85, 6_000_000),
        (83, 4_500_000),
        (80, 3_500_000),
        (75, 2_500_000),
        (70, 1_500_000),
        (65, 1_000_000),
    ]
    for threshold, value in tiers:
        if rating >= threshold:
            return value
    return 500_000


def clause_value_for_rating(rating) -> int:
    market_value = market_value_for_rating(rating)
    if market_value <= 0:
        return MIN_CLAUSE_VALUE
    return max(MIN_CLAUSE_VALUE, market_value * CLAUSE_MULTIPLIER)


def _has(row, key):
    return row is not None and key in row.keys()


def player_market_value(player) -> int:
    if not player:
        return 0
    if _has(player, "rating") and player["rating"] is not None:
        value = market_value_for_rating(player["rating"])
        if value:
            return value
    if _has(player, "min_sale_value") and player["min_sale_value"] is not None:
        try:
            return int(player["min_sale_value"])
        except (TypeError, ValueError):
            pass
    return 0


def player_clause_value(player) -> int:
    market_value = player_market_value(player)
    if market_value <= 0:
        return MIN_CLAUSE_VALUE
    return max(MIN_CLAUSE_VALUE, market_value * CLAUSE_MULTIPLIER)


def fmt_money(value) -> str:
    if value is None:
        return "Sin definir"
    try:
        return f"${int(value):,}".replace(",", ".")
    except (TypeError, ValueError):
        return str(value)


def _migrate_connection(conn) -> int:
    tables = {
        row["name"]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    if "roster_players" not in tables:
        return 0

    columns = {
        row["name"] for row in conn.execute("PRAGMA table_info(roster_players)").fetchall()
    }
    if "min_sale_value" not in columns:
        conn.execute("ALTER TABLE roster_players ADD COLUMN min_sale_value INTEGER")

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS economy_migrations (
            key TEXT PRIMARY KEY,
            applied_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    done = conn.execute(
        "SELECT 1 FROM economy_migrations WHERE key = ? LIMIT 1",
        (MIGRATION_KEY,),
    ).fetchone()
    if done:
        return 0

    rows = conn.execute(
        "SELECT id, rating FROM roster_players WHERE rating IS NOT NULL"
    ).fetchall()
    updated = 0
    for row in rows:
        value = market_value_for_rating(row["rating"])
        conn.execute(
            "UPDATE roster_players SET min_sale_value = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (value, row["id"]),
        )
        updated += 1

    conn.execute(
        "INSERT OR REPLACE INTO economy_migrations (key) VALUES (?)",
        (MIGRATION_KEY,),
    )
    conn.commit()
    return updated


def _install_db_migration(runtime):
    original_db = runtime.db
    if getattr(original_db, "_ajap_economy_wrapped", False):
        return

    def economy_db():
        conn = original_db()
        _migrate_connection(conn)
        return conn

    economy_db._ajap_economy_wrapped = True
    runtime.db = economy_db

    # Migrate the currently selected (legacy/default) DB immediately as well.
    with runtime.db() as conn:
        _migrate_connection(conn)


def _patch_value_sources(runtime):
    import lyon_test_seed as lyon
    import offer_value_floor_patch as value_floor

    # Future seeds and fallback validations use the definitive curve too.
    lyon.minimum_for_rating = market_value_for_rating
    lyon.clause_for_rating = clause_value_for_rating
    value_floor.player_floor = player_market_value

    runtime.market_value_for_rating = market_value_for_rating
    runtime.player_market_value = player_market_value
    runtime.player_clause_value = player_clause_value
    runtime.player_offer_floor = player_market_value


def _patch_publish_range_cards(runtime):
    import publish_ovr_patch as publish

    def publish_range_embed(club: str, label: str, jugadores):
        embed = discord.Embed(
            title=f"📤 Publicar jugador • {club} • OVR {label}",
            description="Elegí uno de estos jugadores para continuar con la publicación.",
        )
        for player in jugadores[:25]:
            rating = player["rating"] if _has(player, "rating") else None
            value = player_market_value(player)
            clause = player_clause_value(player)
            text = f"**{player['position']}**"
            if rating is not None:
                text += f" • ⭐ {rating}"
            text += (
                f"\n💰 Valor de mercado: **{fmt_money(value)}**"
                f"\n💥 Valor de cláusula: **{fmt_money(clause)}**"
            )
            embed.add_field(name=player["name"], value=text, inline=False)
        embed.set_footer(text=f"{len(jugadores)} jugador(es) disponibles en OVR {label}")
        return embed

    publish.publish_range_embed = publish_range_embed


def _patch_global_search(runtime):
    import global_player_search_patch as global_search

    def jugador_global_embed(player):
        publication = runtime.publicacion_activa_del_jugador(player["name"])
        pending = runtime.operacion_abierta_del_jugador(player["name"])
        rating = player["rating"] if _has(player, "rating") else None
        value = player_market_value(player)
        clause = player_clause_value(player)

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
        embed.add_field(name="🆔 ID", value=f"`{runtime.player_code(player['id'])}`", inline=True)
        embed.add_field(name="🏟️ Club actual", value=player["club"], inline=True)
        embed.add_field(name="📍 Posición", value=player["position"], inline=True)
        embed.add_field(name="⭐ OVR", value=str(rating) if rating is not None else "Sin cargar", inline=True)
        embed.add_field(name="💰 Valor de mercado", value=fmt_money(value), inline=True)
        embed.add_field(name="💥 Valor de cláusula", value=fmt_money(clause), inline=True)
        embed.add_field(name="📋 Estado", value=status, inline=False)

        key_attributes = None
        formatter = getattr(runtime, "pes6_format_key_attributes", None)
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
            if runtime.mercado_abierto():
                embed.set_footer(text="Mercado abierto • Si no es de tu club, podés ofertar desde esta ficha")
            else:
                embed.set_footer(text="Mercado cerrado • La publicación se puede consultar, pero no ofertar")
        else:
            embed.set_footer(text="No está publicado • La búsqueda es solo informativa")

        return embed, publication

    global_search.jugador_global_embed = jugador_global_embed
    runtime.jugador_global_embed = jugador_global_embed


def _patch_publication_cards(runtime):
    import publication_announce_patch as announce
    import publication_management_patch as management

    def publication_embed(publication):
        player = runtime.jugador_por_nombre(publication["player"])
        club = publication["club"]
        name = publication["player"]
        value = player_market_value(player)
        clause = player_clause_value(player)

        embed = discord.Embed(
            title="📢 NUEVO JUGADOR EN TRANSFERIBLES",
            description=f"**{club}** añadió a **{name}** a la lista de transferibles.",
        )
        if player:
            details = []
            if _has(player, "position") and player["position"]:
                details.append(str(player["position"]))
            if _has(player, "rating") and player["rating"] is not None:
                details.append(f"⭐ OVR {player['rating']}")
            suffix = " • " + " • ".join(details) if details else ""
            embed.add_field(name="⚽ Jugador", value=f"**{name}**{suffix}", inline=False)
        else:
            embed.add_field(name="⚽ Jugador", value=f"**{name}**", inline=False)

        embed.add_field(name="🏟️ Club", value=club, inline=True)
        embed.add_field(name="🔁 Tipo", value=publication["operation_type"], inline=True)
        embed.add_field(name="💰 Precio solicitado", value=publication["price"], inline=True)

        detail = (publication["detail"] or "").strip()
        if detail and detail.casefold() != "sin observaciones":
            embed.add_field(name="📝 Condiciones", value=detail, inline=False)

        embed.add_field(name="💰 Valor de mercado", value=fmt_money(value), inline=True)
        embed.add_field(name="💥 Valor de cláusula", value=fmt_money(clause), inline=True)
        embed.set_footer(text=f"Publicación #{publication['id']} • AJAP Transfer Market")
        return embed

    def owner_embed(publication):
        player = runtime.jugador_por_nombre(publication["player"])
        embed = discord.Embed(
            title="⚙️ Gestionar transferible",
            description=(
                f"**{publication['player']}** está publicado por **{publication['club']}**.\n\n"
                "Podés quitarlo de la lista de transferibles cuando quieras."
            ),
        )
        embed.add_field(name="🔁 Tipo", value=publication["operation_type"], inline=True)
        embed.add_field(name="💰 Precio", value=publication["price"], inline=True)
        detail = (publication["detail"] or "").strip()
        if detail and detail.casefold() != "sin observaciones":
            embed.add_field(name="📝 Condiciones", value=detail, inline=False)
        embed.add_field(name="💰 Valor de mercado", value=fmt_money(player_market_value(player)), inline=True)
        embed.add_field(name="💥 Valor de cláusula", value=fmt_money(player_clause_value(player)), inline=True)
        embed.set_footer(text=f"Publicación #{publication['id']} • Solo el propietario puede quitarla")
        return embed

    announce.publication_embed = publication_embed
    management._owner_embed = owner_embed


def _patch_offer_picker(runtime):
    import negotiation_picker_patch as negotiation

    original_embed = negotiation.RosterPickerView.embed
    if getattr(original_embed, "_ajap_economy_values", False):
        return

    def picker_embed(view):
        embed = original_embed(view)
        if view.mode == "offer":
            publication = runtime.publicacion_por_id(view.publication_id)
            player = runtime.jugador_por_nombre(publication["player"]) if publication else None
            if player:
                embed.add_field(
                    name="💰 Valor de mercado",
                    value=fmt_money(player_market_value(player)),
                    inline=True,
                )
                embed.add_field(
                    name="💥 Valor de cláusula",
                    value=fmt_money(player_clause_value(player)),
                    inline=True,
                )
        return embed

    picker_embed._ajap_economy_values = True
    negotiation.RosterPickerView.embed = picker_embed


def _patch_clausulazo(runtime):
    import clausulazo_patch as clauses

    def dynamic_clause_price(player=None):
        target = player if player is not None else _CLAUSE_PLAYER.get()
        return player_clause_value(target)

    original_create = clauses.create_clause_request

    def create_clause_request(interaction, player):
        token = _CLAUSE_PLAYER.set(player)
        try:
            return original_create(interaction, player)
        finally:
            _CLAUSE_PLAYER.reset(token)

    original_select_callback = clauses.ClausePlayerSelect.callback

    async def clause_player_callback(select, interaction):
        player = runtime.jugador_por_id(int(select.values[0])) if select.values else None
        token = _CLAUSE_PLAYER.set(player)
        try:
            return await original_select_callback(select, interaction)
        finally:
            _CLAUSE_PLAYER.reset(token)

    def clause_player_select_init(select, players, row=0):
        cycle = clauses.active_cycle()
        options = []
        for player in players[:25]:
            state = clauses.clause_state(player["id"], cycle["id"]) if cycle else None
            rating = clauses.player_rating(player)
            status = ""
            if state:
                status = " • 🔒 Clausulado" if state["status"] == "APROBADO" else " • ⏳ Pendiente Staff"
            desc = f"{player['club']} • {player['position']}"
            if rating is not None:
                desc += f" • OVR {rating}"
            desc += f" • Cláusula {fmt_money(player_clause_value(player))}"
            desc += status
            discord.ui.Select.__init__(
                select,
                placeholder="Elegí un jugador",
                min_values=1,
                max_values=1,
                options=[*options, discord.SelectOption(label=player["name"][:100], description=desc[:100], value=str(player["id"]))],
                row=row,
            )
            options = list(select.options)
        if not players:
            discord.ui.Select.__init__(
                select,
                placeholder="Elegí un jugador",
                min_values=1,
                max_values=1,
                options=[],
                row=row,
            )

    # Cleaner select init without repeatedly rebuilding the component.
    def clause_player_select_init(select, players, row=0):
        cycle = clauses.active_cycle()
        options = []
        for player in players[:25]:
            state = clauses.clause_state(player["id"], cycle["id"]) if cycle else None
            rating = clauses.player_rating(player)
            status = ""
            if state:
                status = " • 🔒 Clausulado" if state["status"] == "APROBADO" else " • ⏳ Pendiente Staff"
            desc = f"{player['club']} • {player['position']}"
            if rating is not None:
                desc += f" • OVR {rating}"
            desc += f" • Cláusula {fmt_money(player_clause_value(player))}"
            desc += status
            options.append(
                discord.SelectOption(
                    label=player["name"][:100],
                    description=desc[:100],
                    value=str(player["id"]),
                )
            )
        discord.ui.Select.__init__(
            select,
            placeholder="Elegí un jugador",
            min_values=1,
            max_values=1,
            options=options,
            row=row,
        )

    def home_embed(user_id):
        club = runtime.club_de(user_id)
        balance = clauses.club_balance(club) if club else 0
        embed = discord.Embed(
            title="💥 Clausulazo",
            description=(
                "Podés ejecutar la cláusula de **cualquier jugador de otro equipo**, aunque no esté publicado.\n\n"
                "La operación **no necesita aceptación del club propietario**, pero sí aprobación del **Staff**."
            ),
        )
        embed.add_field(
            name="💰 Cálculo de cláusula",
            value="**Valor de mercado × 4** • mínimo **$10.000.000**",
            inline=False,
        )
        embed.add_field(name="🏦 Tu saldo", value=fmt_money(balance), inline=True)
        embed.add_field(name="🔁 Por jugador", value="Máximo 1 clausulazo por mercado", inline=False)
        embed.add_field(
            name="🔒 Protección",
            value="Si un jugador ya fue clausulado en esta ventana, nadie puede volver a clausularlo hasta el próximo mercado.",
            inline=False,
        )
        embed.set_footer(text="El importe real de cada jugador queda reservado mientras Staff revisa la solicitud")
        return embed

    original_approve = clauses.approve_request

    def approve_request(req, staff_id):
        result = original_approve(req, staff_id)
        ok, transfer_id = result
        if ok and isinstance(transfer_id, int):
            with runtime.db() as conn:
                conn.execute(
                    """
                    UPDATE transfers
                    SET notes = REPLACE(notes, 'Cláusula universal', 'Cláusula por OVR')
                    WHERE id = ?
                    """,
                    (transfer_id,),
                )
        return result

    clauses.clause_price = dynamic_clause_price
    clauses.create_clause_request = create_clause_request
    clauses.ClausePlayerSelect.callback = clause_player_callback
    clauses.ClausePlayerSelect.__init__ = clause_player_select_init
    clauses.home_embed = home_embed
    clauses.approve_request = approve_request

    # Universal clause configuration is obsolete under the OVR-based economy.
    try:
        runtime.bot.tree.remove_command("configurar_clausula")
    except Exception:
        pass


def apply_economy_values_patch(runtime, bot=None):
    global APP
    APP = runtime
    if getattr(runtime, "_ajap_economy_values_patch", False):
        return

    _install_db_migration(runtime)
    _patch_value_sources(runtime)
    _patch_publish_range_cards(runtime)
    _patch_global_search(runtime)
    _patch_publication_cards(runtime)
    _patch_offer_picker(runtime)
    _patch_clausulazo(runtime)

    runtime._ajap_economy_values_patch = True
    print(
        "AJAP economía definitiva activa: valores por OVR + cláusula x4 (mínimo $10M) + "
        "fichas/publicaciones/búsqueda actualizadas"
    )
