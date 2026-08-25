"""Flexible negotiation offers for AJAP Transfer Market.

Supports three offer formats for a published player:
- DINERO: cash only.
- INTERCAMBIO: player for player, no cash required.
- JUGADOR + DINERO: one player plus cash.

When an exchange is accepted, both player movements are created as linked admin
operations and are approved/applied/rejected atomically so the rosters cannot
end up half-swapped.
"""

import discord

APP = None


def ensure_schema():
    with APP.db() as conn:
        APP.add_column_if_missing(conn, "offers", "offer_kind", "TEXT NOT NULL DEFAULT 'DINERO'")
        APP.add_column_if_missing(conn, "offers", "offered_player_id", "INTEGER")
        APP.add_column_if_missing(conn, "offers", "offered_player", "TEXT")
        APP.add_column_if_missing(conn, "transfers", "deal_group", "TEXT")


def _row_has(row, key):
    return row is not None and key in row.keys()


def resolve_player_reference(value: str):
    raw = (value or "").strip()
    if not raw:
        return None
    upper = raw.upper()
    if upper.startswith("AJAP-"):
        suffix = upper[5:]
        if suffix.isdigit():
            return APP.jugador_por_id(int(suffix))
    return APP.jugador_por_nombre(raw)


def offer_kind(cash_value: int, offered_player):
    if offered_player and cash_value > 0:
        return "JUGADOR + DINERO"
    if offered_player:
        return "INTERCAMBIO"
    return "DINERO"


def offer_summary(offer):
    kind = offer["offer_kind"] if _row_has(offer, "offer_kind") else "DINERO"
    amount = offer["amount"]
    player = offer["offered_player"] if _row_has(offer, "offered_player") else None
    if kind == "INTERCAMBIO":
        return f"🔁 **{player or 'Jugador'}**"
    if kind == "JUGADOR + DINERO":
        return f"🔁 **{player or 'Jugador'}** + 💰 **{amount}**"
    return f"💰 **{amount}**"


def linked_operations(op):
    group = op["deal_group"] if _row_has(op, "deal_group") else None
    if not group:
        return [op]
    with APP.db() as conn:
        return conn.execute(
            "SELECT * FROM transfers WHERE deal_group = ? ORDER BY id ASC",
            (group,),
        ).fetchall()


def validate_group_rosters(ops):
    for op in ops:
        ficha = APP.jugador_por_nombre(op["player"])
        if not ficha:
            return False, f"No se encontró **{op['player']}** en el plantel oficial."
        if ficha["club"].casefold() != op["seller"].casefold():
            return False, (
                f"**{op['player']}** figura actualmente en **{ficha['club']}**, "
                f"no en **{op['seller']}**."
            )
    return True, None


class FlexibleOfertaModal(discord.ui.Modal):
    def __init__(self, publicacion):
        super().__init__(title=f"Oferta por {publicacion['player'][:30]}")
        self.publicacion_id = publicacion["id"]
        self.monto = discord.ui.TextInput(
            label="Dinero ofrecido (opcional)",
            placeholder="Ej: 2000000 • dejá vacío si es jugador por jugador",
            required=False,
            max_length=30,
        )
        self.jugador = discord.ui.TextInput(
            label="Jugador ofrecido (opcional)",
            placeholder="Nombre exacto o ID AJAP-000123",
            required=False,
            max_length=80,
        )
        self.mensaje = discord.ui.TextInput(
            label="Mensaje / condiciones",
            placeholder="Opcional",
            required=False,
            max_length=150,
        )
        self.add_item(self.monto)
        self.add_item(self.jugador)
        self.add_item(self.mensaje)

    async def on_submit(self, interaction: discord.Interaction):
        if not APP.mercado_abierto():
            await interaction.response.send_message(
                "🔒 El mercado está cerrado. Las ofertas todavía no están habilitadas.",
                ephemeral=True,
            )
            return

        pub = APP.publicacion_por_id(self.publicacion_id)
        if not pub:
            await interaction.response.send_message("⚠️ Esa publicación ya no está disponible.", ephemeral=True)
            return

        target = APP.jugador_por_nombre(pub["player"])
        if not target or target["club"].casefold() != pub["club"].casefold():
            await interaction.response.send_message(
                "⚠️ La propiedad del jugador cambió. La publicación ya no es válida.",
                ephemeral=True,
            )
            return
        if APP.operacion_abierta_del_jugador(pub["player"]):
            await interaction.response.send_message(
                "⚠️ Ese jugador ya tiene un acuerdo aceptado pendiente de administración.",
                ephemeral=True,
            )
            return
        if interaction.user.id == pub["owner_id"]:
            await interaction.response.send_message("⚠️ No podés ofertar por una publicación propia.", ephemeral=True)
            return

        buyer_club = APP.club_de(interaction.user.id)
        if not buyer_club:
            await interaction.response.send_message("⚠️ Primero elegí tu club.", ephemeral=True)
            return
        if buyer_club.casefold() == pub["club"].casefold():
            await interaction.response.send_message("⚠️ El jugador ya pertenece a tu club.", ephemeral=True)
            return

        raw_cash = self.monto.value.strip()
        if raw_cash:
            cash_value = APP.price_number(raw_cash)
            if cash_value is None:
                await interaction.response.send_message(
                    "⚠️ El dinero ofrecido debe ser un número.", ephemeral=True
                )
                return
        else:
            cash_value = 0

        offered = resolve_player_reference(self.jugador.value)
        if self.jugador.value.strip() and not offered:
            await interaction.response.send_message(
                "⚠️ No encontré ese jugador. Usá el nombre exacto o su ID AJAP.",
                ephemeral=True,
            )
            return
        if offered:
            if offered["club"].casefold() != buyer_club.casefold():
                await interaction.response.send_message(
                    f"⛔ **{offered['name']}** no pertenece a **{buyer_club}**.",
                    ephemeral=True,
                )
                return
            if offered["id"] == target["id"]:
                await interaction.response.send_message(
                    "⚠️ No podés ofrecer el mismo jugador por el que estás negociando.",
                    ephemeral=True,
                )
                return
            if APP.operacion_abierta_del_jugador(offered["name"]):
                await interaction.response.send_message(
                    f"⚠️ **{offered['name']}** ya tiene una operación pendiente.",
                    ephemeral=True,
                )
                return

        if cash_value <= 0 and not offered:
            await interaction.response.send_message(
                "⚠️ La oferta debe incluir **dinero**, **un jugador**, o **ambos**.",
                ephemeral=True,
            )
            return

        kind = offer_kind(cash_value, offered)
        amount = APP.money(str(cash_value)) if cash_value > 0 else "$0"
        message = self.mensaje.value.strip() or "Sin condiciones adicionales"

        with APP.db() as conn:
            cur = conn.execute(
                """
                INSERT INTO offers
                (publication_id, player, amount, message, from_id, from_club, to_id, to_club,
                 operation_type, season_id, offer_kind, offered_player_id, offered_player)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    pub["id"], pub["player"], amount, message,
                    interaction.user.id, buyer_club, pub["owner_id"], pub["club"],
                    kind, pub["season_id"], kind,
                    offered["id"] if offered else None,
                    offered["name"] if offered else None,
                ),
            )
            offer_id = cur.lastrowid

        embed = discord.Embed(
            title="💰 Oferta enviada",
            description=f"Tu propuesta por **{pub['player']}** fue registrada.",
        )
        embed.add_field(name="Modalidad", value=kind, inline=True)
        if cash_value > 0:
            embed.add_field(name="Dinero", value=amount, inline=True)
        if offered:
            ovr = offered["rating"] if _row_has(offered, "rating") else None
            label = f"{offered['name']}"
            if ovr is not None:
                label += f" • ⭐ {ovr}"
            embed.add_field(name="Jugador ofrecido", value=label, inline=False)
        embed.add_field(name="Estado", value="🟡 PENDIENTE", inline=True)
        embed.add_field(name="Condiciones", value=message, inline=False)
        embed.set_footer(text=f"Oferta #{offer_id}")
        await interaction.response.send_message(embed=embed, ephemeral=True)


class FlexibleOfertaDecisionView(discord.ui.View):
    def __init__(self, oferta_id: int):
        super().__init__(timeout=180)
        self.oferta_id = oferta_id

    @discord.ui.button(label="Aceptar", emoji="✅", style=discord.ButtonStyle.success)
    async def aceptar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not APP.mercado_abierto():
            await interaction.response.send_message("🔒 El mercado está cerrado. La oferta queda congelada.", ephemeral=True)
            return

        offer = APP.oferta_por_id(self.oferta_id)
        if not offer or interaction.user.id != offer["to_id"]:
            await interaction.response.send_message("No podés gestionar esta oferta.", ephemeral=True)
            return
        if offer["status"] != "PENDIENTE":
            await interaction.response.send_message("Esta oferta ya fue resuelta.", ephemeral=True)
            return
        if APP.operacion_abierta_del_jugador(offer["player"]):
            await interaction.response.send_message(
                "⚠️ Ese jugador ya tiene otra operación pendiente de administración.", ephemeral=True
            )
            return

        pub = APP.publicacion_por_id(offer["publication_id"])
        target = APP.jugador_por_nombre(offer["player"])
        if not pub or not target or target["club"].casefold() != offer["to_club"].casefold():
            with APP.db() as conn:
                conn.execute("UPDATE offers SET status = 'CANCELADA' WHERE id = ?", (offer["id"],))
            await interaction.response.send_message(
                "⚠️ La publicación o propiedad cambió. La oferta fue cancelada.", ephemeral=True
            )
            return

        offered = None
        offered_id = offer["offered_player_id"] if _row_has(offer, "offered_player_id") else None
        if offered_id:
            offered = APP.jugador_por_id(int(offered_id))
            if not offered or offered["club"].casefold() != offer["from_club"].casefold():
                await interaction.response.send_message(
                    "⚠️ El jugador incluido en la oferta ya no pertenece al club comprador. No se aceptó nada.",
                    ephemeral=True,
                )
                return
            if APP.operacion_abierta_del_jugador(offered["name"]):
                await interaction.response.send_message(
                    f"⚠️ **{offered['name']}** ya tiene otra operación pendiente.", ephemeral=True
                )
                return

        kind = offer["offer_kind"] if _row_has(offer, "offer_kind") else "DINERO"
        deal_group = f"OFERTA-{offer['id']}"
        notes = offer["message"] or "Sin condiciones adicionales"
        if offered:
            notes = f"{notes} | Contraparte: {offered['name']} ({APP.player_code(offered['id'])})"

        created_ops = []
        with APP.db() as conn:
            conn.execute("UPDATE offers SET status = 'ACEPTADA' WHERE id = ?", (offer["id"],))
            conn.execute("UPDATE publications SET active = 0 WHERE id = ?", (pub["id"],))
            conn.execute(
                """
                UPDATE offers SET status = 'RECHAZADA'
                WHERE publication_id = ? AND id != ? AND status = 'PENDIENTE'
                """,
                (pub["id"], offer["id"]),
            )

            if offered:
                conn.execute(
                    "UPDATE publications SET active = 0 WHERE player = ? COLLATE NOCASE AND active = 1",
                    (offered["name"],),
                )
                conn.execute(
                    "UPDATE offers SET status = 'CANCELADA' WHERE player = ? COLLATE NOCASE AND status = 'PENDIENTE'",
                    (offered["name"],),
                )

            primary_type = "TRANSFERENCIA" if kind == "DINERO" else kind
            cur = conn.execute(
                """
                INSERT INTO transfers
                (player, seller, buyer, amount, offer_id, player_id, operation_type, season_id,
                 status, notes, deal_group)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'PENDIENTE_ADMIN', ?, ?)
                """,
                (
                    offer["player"], offer["to_club"], offer["from_club"], offer["amount"],
                    offer["id"], target["id"], primary_type, offer["season_id"], notes, deal_group,
                ),
            )
            created_ops.append(cur.lastrowid)

            if offered:
                cur = conn.execute(
                    """
                    INSERT INTO transfers
                    (player, seller, buyer, amount, offer_id, player_id, operation_type, season_id,
                     status, notes, deal_group)
                    VALUES (?, ?, ?, '$0', ?, ?, 'INTERCAMBIO', ?, 'PENDIENTE_ADMIN', ?, ?)
                    """,
                    (
                        offered["name"], offer["from_club"], offer["to_club"], offer["id"],
                        offered["id"], offer["season_id"],
                        f"Contraparte de {offer['player']} | Oferta #{offer['id']}", deal_group,
                    ),
                )
                created_ops.append(cur.lastrowid)

        embed = discord.Embed(
            title="🤝 Acuerdo aceptado • Falta administración",
            description=(
                f"**{offer['to_club']}** aceptó la propuesta de **{offer['from_club']}** por **{offer['player']}**.\n\n"
                "Los planteles **todavía no fueron modificados**."
            ),
        )
        embed.add_field(name="Modalidad", value=kind, inline=True)
        embed.add_field(name="Propuesta", value=offer_summary(offer), inline=False)
        if offered:
            embed.add_field(
                name="Movimientos pendientes",
                value=(
                    f"➡️ {offer['player']}: {offer['to_club']} → {offer['from_club']}\n"
                    f"⬅️ {offered['name']}: {offer['from_club']} → {offer['to_club']}"
                ),
                inline=False,
            )
        embed.add_field(name="Estado", value="🟡 PENDIENTE_ADMIN", inline=True)
        embed.set_footer(text="Operaciones: " + ", ".join(f"#{op}" for op in created_ops))
        await interaction.response.edit_message(embed=embed, view=None)

    @discord.ui.button(label="Rechazar", emoji="❌", style=discord.ButtonStyle.danger)
    async def rechazar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not APP.mercado_abierto():
            await interaction.response.send_message("🔒 El mercado está cerrado. La oferta queda congelada.", ephemeral=True)
            return
        offer = APP.oferta_por_id(self.oferta_id)
        if not offer or interaction.user.id != offer["to_id"]:
            await interaction.response.send_message("No podés gestionar esta oferta.", ephemeral=True)
            return
        if offer["status"] != "PENDIENTE":
            await interaction.response.send_message("Esta oferta ya fue resuelta.", ephemeral=True)
            return
        with APP.db() as conn:
            conn.execute("UPDATE offers SET status = 'RECHAZADA' WHERE id = ?", (offer["id"],))
        await interaction.response.edit_message(
            embed=discord.Embed(
                title="❌ Oferta rechazada",
                description=f"Rechazaste la propuesta por **{offer['player']}**.",
            ),
            view=None,
        )


class FlexibleOfertasSelect(discord.ui.Select):
    def __init__(self, offers):
        options = []
        for offer in offers[:25]:
            kind = offer["offer_kind"] if _row_has(offer, "offer_kind") else "DINERO"
            player = offer["offered_player"] if _row_has(offer, "offered_player") else None
            if kind == "INTERCAMBIO":
                desc = f"{player or 'Jugador'} • {offer['status']}"
            elif kind == "JUGADOR + DINERO":
                desc = f"{player or 'Jugador'} + {offer['amount']} • {offer['status']}"
            else:
                desc = f"{offer['amount']} • {offer['status']}"
            options.append(
                discord.SelectOption(
                    label=f"#{offer['id']} • {offer['player']}"[:100],
                    description=desc[:100],
                    value=str(offer["id"]),
                )
            )
        super().__init__(
            placeholder="Elegí una oferta recibida",
            min_values=1,
            max_values=1,
            options=options,
        )

    async def callback(self, interaction: discord.Interaction):
        offer = APP.oferta_por_id(int(self.values[0]))
        if not offer or offer["to_id"] != interaction.user.id:
            await interaction.response.send_message("Oferta no disponible.", ephemeral=True)
            return
        kind = offer["offer_kind"] if _row_has(offer, "offer_kind") else "DINERO"
        embed = discord.Embed(
            title=f"💰 Oferta #{offer['id']}",
            description=f"Oferta recibida por **{offer['player']}**.",
        )
        embed.add_field(name="Club comprador", value=offer["from_club"], inline=True)
        embed.add_field(name="Modalidad", value=kind, inline=True)
        embed.add_field(name="Propuesta", value=offer_summary(offer), inline=False)
        embed.add_field(name="Estado", value=offer["status"], inline=True)
        embed.add_field(name="Condiciones", value=offer["message"], inline=False)
        view = FlexibleOfertaDecisionView(offer["id"]) if offer["status"] == "PENDIENTE" else None
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


class FlexibleOfertasView(discord.ui.View):
    def __init__(self, offers):
        super().__init__(timeout=180)
        if offers:
            self.add_item(FlexibleOfertasSelect(offers))


class GroupOperacionAdminView(discord.ui.View):
    def __init__(self, operacion_id: int):
        super().__init__(timeout=180)
        self.operacion_id = operacion_id

    @discord.ui.button(label="Aprobar", emoji="✅", style=discord.ButtonStyle.success)
    async def aprobar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not APP.es_admin(interaction):
            await interaction.response.send_message("⛔ Solo admins.", ephemeral=True)
            return
        op = APP.operacion_por_id(self.operacion_id)
        if not op:
            await interaction.response.send_message("⚠️ Operación no encontrada.", ephemeral=True)
            return
        ops = linked_operations(op)
        if any(item["status"] != "PENDIENTE_ADMIN" for item in ops):
            await interaction.response.send_message("⚠️ El acuerdo ya no está completamente pendiente de aprobación.", ephemeral=True)
            return
        ok, error = validate_group_rosters(ops)
        if not ok:
            await interaction.response.send_message(f"⚠️ {error}", ephemeral=True)
            return
        with APP.db() as conn:
            for item in ops:
                conn.execute(
                    "UPDATE transfers SET status = 'APROBADA', approved_by = ?, approved_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (interaction.user.id, item["id"]),
                )
        lines = "\n".join(f"• **{item['player']}**: {item['seller']} → {item['buyer']}" for item in ops)
        await interaction.response.edit_message(
            embed=discord.Embed(
                title="✅ Acuerdo aprobado",
                description=f"Se aprobaron **{len(ops)} movimiento(s)** vinculados:\n{lines}\n\nTodavía falta aplicarlos en PES.",
            ),
            view=GroupOperacionAdminView(op["id"]),
        )

    @discord.ui.button(label="Aplicado en PES", emoji="🎮", style=discord.ButtonStyle.primary)
    async def aplicar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not APP.es_admin(interaction):
            await interaction.response.send_message("⛔ Solo admins.", ephemeral=True)
            return
        op = APP.operacion_por_id(self.operacion_id)
        if not op:
            await interaction.response.send_message("⚠️ Operación no encontrada.", ephemeral=True)
            return
        ops = linked_operations(op)
        if any(item["status"] != "APROBADA" for item in ops):
            await interaction.response.send_message("⚠️ Primero deben estar aprobados todos los movimientos del acuerdo.", ephemeral=True)
            return
        ok, error = validate_group_rosters(ops)
        if not ok:
            await interaction.response.send_message(f"⚠️ {error} No se aplicó nada.", ephemeral=True)
            return

        with APP.db() as conn:
            for item in ops:
                ficha = APP.jugador_por_nombre(item["player"])
                conn.execute(
                    "UPDATE roster_players SET club = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (item["buyer"], ficha["id"]),
                )
                conn.execute(
                    "UPDATE transfers SET status = 'APLICADA', applied_by = ?, applied_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (interaction.user.id, item["id"]),
                )
                conn.execute(
                    """
                    INSERT INTO player_history
                    (player_id, player, from_club, to_club, transfer_id, season_id, event_type)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        ficha["id"], ficha["name"], item["seller"], item["buyer"],
                        item["id"], item["season_id"], item["operation_type"],
                    ),
                )
        lines = "\n".join(f"• **{item['player']}**: {item['seller']} → {item['buyer']}" for item in ops)
        await interaction.response.edit_message(
            embed=discord.Embed(
                title="🎮 Acuerdo aplicado al juego",
                description=f"Los planteles se actualizaron juntos:\n{lines}",
            ),
            view=None,
        )

    @discord.ui.button(label="Rechazar admin", emoji="⛔", style=discord.ButtonStyle.danger)
    async def rechazar_admin(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not APP.es_admin(interaction):
            await interaction.response.send_message("⛔ Solo admins.", ephemeral=True)
            return
        op = APP.operacion_por_id(self.operacion_id)
        if not op:
            await interaction.response.send_message("⚠️ Operación no encontrada.", ephemeral=True)
            return
        ops = linked_operations(op)
        if any(item["status"] not in ("PENDIENTE_ADMIN", "APROBADA") for item in ops):
            await interaction.response.send_message("⚠️ Ese acuerdo ya no puede rechazarse.", ephemeral=True)
            return
        with APP.db() as conn:
            for item in ops:
                conn.execute(
                    "UPDATE transfers SET status = 'RECHAZADA_ADMIN', rejected_by = ?, rejected_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (interaction.user.id, item["id"]),
                )
            if op["offer_id"]:
                conn.execute("UPDATE offers SET status = 'CANCELADA_ADMIN' WHERE id = ?", (op["offer_id"],))
        await interaction.response.edit_message(
            embed=discord.Embed(
                title="⛔ Acuerdo rechazado por administración",
                description=f"Se cancelaron **{len(ops)} movimiento(s)** vinculados. Ningún plantel fue modificado.",
            ),
            view=None,
        )


def apply_flexible_offer_patch(main_module):
    global APP
    APP = main_module
    if getattr(main_module, "_ajap_flexible_offer_patch", False):
        return

    ensure_schema()
    main_module.OfertaModal = FlexibleOfertaModal
    main_module.OfertaDecisionView = FlexibleOfertaDecisionView
    main_module.OfertasSelect = FlexibleOfertasSelect
    main_module.OfertasView = FlexibleOfertasView
    main_module.OperacionAdminView = GroupOperacionAdminView
    main_module.offer_summary = offer_summary
    main_module._ajap_flexible_offer_patch = True
    print("Ofertas flexibles activas: dinero / jugador / jugador + dinero")
