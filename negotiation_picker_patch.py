"""Roster picker + two-way counteroffers for AJAP Transfer Market.

Goals:
- Never make managers type the offered player's name.
- Pick the offered player from the buyer club roster (or choose cash only).
- Let the current decision maker counteroffer and replace the offered player.
- Keep the target player fixed while money/player terms can change round by round.
- Preserve the existing minimum-value protection and new-offer notifications.
"""

import discord

import flexible_offer_patch as flexible
import global_player_search_patch as global_search
import offer_value_floor_patch as value_floor


APP = None
FINAL_OFFER_MODAL = None
PAGE_SIZE = 24  # + "solo dinero" = Discord's 25 select-option limit.


def _has(row, key):
    return row is not None and key in row.keys()


def _decision_user_id(offer):
    if _has(offer, "decision_user_id") and offer["decision_user_id"] is not None:
        return int(offer["decision_user_id"])
    return int(offer["to_id"])


def _round(offer):
    if _has(offer, "negotiation_round") and offer["negotiation_round"]:
        return int(offer["negotiation_round"])
    return 1


def _club_for_user(offer, user_id):
    if int(user_id) == int(offer["from_id"]):
        return offer["from_club"]
    if int(user_id) == int(offer["to_id"]):
        return offer["to_club"]
    return None


def _other_user_id(offer, user_id):
    if int(user_id) == int(offer["from_id"]):
        return int(offer["to_id"])
    return int(offer["from_id"])


def _other_club(offer, user_id):
    if int(user_id) == int(offer["from_id"]):
        return offer["to_club"]
    return offer["from_club"]


def _player_label(player):
    parts = [str(player["position"])]
    if _has(player, "rating") and player["rating"] is not None:
        parts.append(f"OVR {player['rating']}")
    return " • ".join(parts)


def _picker_embed(title, description, club, page, pages):
    embed = discord.Embed(title=title, description=description)
    embed.add_field(name="Plantel", value=club, inline=True)
    if pages > 1:
        embed.add_field(name="Página", value=f"{page + 1}/{pages}", inline=True)
    embed.set_footer(text="Elegí un jugador del desplegable o seleccioná Solo dinero")
    return embed


def _proposal_text(offer):
    return flexible.offer_summary(offer)


def ensure_schema():
    with APP.db() as conn:
        APP.add_column_if_missing(conn, "offers", "decision_user_id", "INTEGER")
        APP.add_column_if_missing(conn, "offers", "negotiation_round", "INTEGER NOT NULL DEFAULT 1")
        conn.execute(
            "UPDATE offers SET decision_user_id = to_id WHERE decision_user_id IS NULL"
        )
        conn.execute(
            "UPDATE offers SET negotiation_round = 1 WHERE negotiation_round IS NULL OR negotiation_round < 1"
        )


class _FixedValue:
    """Small adapter so the existing protected modal can consume a picked player."""

    def __init__(self, value=""):
        self.value = value


class PickedOfertaModal:
    """Factory around the final wrapped OfertaModal.

    It removes the free-text player field but keeps every existing validation,
    minimum-value rule and notification layer by subclassing the final modal.
    """

    @staticmethod
    def build(publication, offered_player_id):
        class _PickedModal(FINAL_OFFER_MODAL):
            def __init__(self, publicacion, player_id):
                super().__init__(publicacion)
                picked = APP.jugador_por_id(int(player_id)) if player_id is not None else None
                old_player_input = self.jugador
                self.remove_item(old_player_input)
                self.jugador = _FixedValue(picked["name"] if picked else "")

        _PickedModal.__name__ = "OfertaModalConJugadorElegido"
        return _PickedModal(publication, offered_player_id)


class RosterPlayerSelect(discord.ui.Select):
    def __init__(self, owner_view, players):
        self.owner_view = owner_view
        options = [
            discord.SelectOption(
                label="Solo dinero",
                description="No incluir ningún jugador en la propuesta",
                value="cash-only",
                emoji="💵",
            )
        ]
        for player in players:
            options.append(
                discord.SelectOption(
                    label=str(player["name"])[:100],
                    description=_player_label(player)[:100],
                    value=str(player["id"]),
                    emoji="⚽",
                )
            )
        super().__init__(
            placeholder="Elegí el jugador que entra en la negociación",
            min_values=1,
            max_values=1,
            options=options,
            row=0,
        )

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.owner_view.actor_id:
            await interaction.response.send_message(
                "⛔ Este selector pertenece a otra negociación.", ephemeral=True
            )
            return

        selected = None if self.values[0] == "cash-only" else int(self.values[0])
        if self.owner_view.mode == "offer":
            publication = APP.publicacion_por_id(self.owner_view.publication_id)
            if not publication:
                await interaction.response.send_message(
                    "⚠️ Esa publicación ya no está disponible.", ephemeral=True
                )
                return
            await interaction.response.send_modal(PickedOfertaModal.build(publication, selected))
            return

        offer = APP.oferta_por_id(self.owner_view.offer_id)
        if not offer or offer["status"] != "PENDIENTE":
            await interaction.response.send_message(
                "⚠️ La negociación ya no está disponible.", ephemeral=True
            )
            return
        await interaction.response.send_modal(CounterOfferModal(offer["id"], selected))


class RosterPickerView(discord.ui.View):
    def __init__(self, *, actor_id, club, mode, publication_id=None, offer_id=None, page=0):
        super().__init__(timeout=300)
        self.actor_id = int(actor_id)
        self.club = club
        self.mode = mode
        self.publication_id = publication_id
        self.offer_id = offer_id

        self.players = list(APP.jugadores_de_club(club, 100))
        self.pages = max(1, (len(self.players) + PAGE_SIZE - 1) // PAGE_SIZE)
        self.page = max(0, min(int(page), self.pages - 1))
        start = self.page * PAGE_SIZE
        chunk = self.players[start : start + PAGE_SIZE]
        self.add_item(RosterPlayerSelect(self, chunk))

        self.previous.disabled = self.page <= 0
        self.next.disabled = self.page >= self.pages - 1

    def embed(self):
        if self.mode == "offer":
            pub = APP.publicacion_por_id(self.publication_id)
            target = pub["player"] if pub else "jugador"
            return _picker_embed(
                "🔁 Armá tu oferta",
                (
                    f"Estás ofertando por **{target}**.\n\n"
                    "Elegí un jugador de tu plantel para incluirlo. "
                    "También podés elegir **Solo dinero**."
                ),
                self.club,
                self.page,
                self.pages,
            )

        offer = APP.oferta_por_id(self.offer_id)
        target = offer["player"] if offer else "jugador"
        return _picker_embed(
            "🔄 Contraoferta • cambiar jugador",
            (
                f"Negociación por **{target}**.\n\n"
                f"Podés reemplazar al jugador actual por **cualquier jugador de {self.club}** "
                "o pasar la propuesta a solo dinero."
            ),
            self.club,
            self.page,
            self.pages,
        )

    async def _move(self, interaction, page):
        if interaction.user.id != self.actor_id:
            await interaction.response.send_message("⛔ Este selector no es tuyo.", ephemeral=True)
            return
        new_view = RosterPickerView(
            actor_id=self.actor_id,
            club=self.club,
            mode=self.mode,
            publication_id=self.publication_id,
            offer_id=self.offer_id,
            page=page,
        )
        await interaction.response.edit_message(embed=new_view.embed(), view=new_view)

    @discord.ui.button(label="Anterior", emoji="⬅️", style=discord.ButtonStyle.secondary, row=1)
    async def previous(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._move(interaction, self.page - 1)

    @discord.ui.button(label="Siguiente", emoji="➡️", style=discord.ButtonStyle.secondary, row=1)
    async def next(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._move(interaction, self.page + 1)


class CounterOfferModal(discord.ui.Modal):
    def __init__(self, offer_id, offered_player_id):
        offer = APP.oferta_por_id(int(offer_id))
        target = offer["player"] if offer else "jugador"
        super().__init__(title=f"Contraoferta por {target[:28]}")
        self.offer_id = int(offer_id)
        self.offered_player_id = offered_player_id

        current_cash = APP.price_number(offer["amount"]) if offer else 0
        current_message = offer["message"] if offer else ""
        if current_message == "Sin condiciones adicionales":
            current_message = ""

        self.monto = discord.ui.TextInput(
            label="Dinero en la contraoferta (opcional)",
            placeholder="Ej: 10000000",
            default=str(current_cash) if current_cash else None,
            required=False,
            max_length=30,
        )
        self.mensaje = discord.ui.TextInput(
            label="Mensaje / condiciones",
            placeholder="Opcional",
            default=current_message[:150] if current_message else None,
            required=False,
            max_length=150,
        )
        self.add_item(self.monto)
        self.add_item(self.mensaje)

    async def on_submit(self, interaction: discord.Interaction):
        if not APP.mercado_abierto():
            await interaction.response.send_message(
                "🔒 El mercado está cerrado. La negociación queda congelada.", ephemeral=True
            )
            return

        offer = APP.oferta_por_id(self.offer_id)
        if not offer or offer["status"] != "PENDIENTE":
            await interaction.response.send_message("⚠️ Esta oferta ya fue resuelta.", ephemeral=True)
            return
        if interaction.user.id not in (offer["from_id"], offer["to_id"]):
            await interaction.response.send_message("⛔ No pertenecés a esta negociación.", ephemeral=True)
            return
        if interaction.user.id != _decision_user_id(offer):
            await interaction.response.send_message(
                "⏳ Ahora mismo la respuesta le corresponde al otro club.", ephemeral=True
            )
            return

        raw_cash = self.monto.value.strip()
        cash_value = APP.price_number(raw_cash) if raw_cash else 0
        if raw_cash and cash_value is None:
            await interaction.response.send_message(
                "⚠️ El dinero debe ser un número.", ephemeral=True
            )
            return

        target = APP.jugador_por_nombre(offer["player"])
        pub = APP.publicacion_por_id(offer["publication_id"])
        if not target or not pub or target["club"].casefold() != offer["to_club"].casefold():
            with APP.db() as conn:
                conn.execute("UPDATE offers SET status = 'CANCELADA' WHERE id = ?", (offer["id"],))
            await interaction.response.send_message(
                "⚠️ La propiedad del jugador cambió. La negociación fue cancelada.", ephemeral=True
            )
            return

        offered = None
        if self.offered_player_id is not None:
            offered = APP.jugador_por_id(int(self.offered_player_id))
            if not offered or offered["club"].casefold() != offer["from_club"].casefold():
                await interaction.response.send_message(
                    f"⛔ Ese jugador ya no pertenece a **{offer['from_club']}**.", ephemeral=True
                )
                return
            if APP.operacion_abierta_del_jugador(offered["name"]):
                await interaction.response.send_message(
                    f"⚠️ **{offered['name']}** ya tiene una operación pendiente.", ephemeral=True
                )
                return

        if cash_value <= 0 and not offered:
            await interaction.response.send_message(
                "⚠️ La contraoferta debe incluir **dinero**, **un jugador**, o **ambos**.",
                ephemeral=True,
            )
            return

        ok, error_embed = value_floor.validate_equivalent_offer(target, offered, cash_value)
        if not ok:
            await interaction.response.send_message(embed=error_embed, ephemeral=True)
            return

        kind = flexible.offer_kind(cash_value, offered)
        amount = APP.money(str(cash_value)) if cash_value > 0 else "$0"
        message = self.mensaje.value.strip() or "Sin condiciones adicionales"
        next_user = _other_user_id(offer, interaction.user.id)
        next_round = _round(offer) + 1

        with APP.db() as conn:
            conn.execute(
                """
                UPDATE offers
                SET amount = ?, message = ?, operation_type = ?, offer_kind = ?,
                    offered_player_id = ?, offered_player = ?, decision_user_id = ?,
                    negotiation_round = ?, status = 'PENDIENTE'
                WHERE id = ?
                """,
                (
                    amount,
                    message,
                    kind,
                    kind,
                    offered["id"] if offered else None,
                    offered["name"] if offered else None,
                    next_user,
                    next_round,
                    offer["id"],
                ),
            )

        refreshed = APP.oferta_por_id(offer["id"])
        embed = discord.Embed(
            title="🔄 Contraoferta enviada",
            description=(
                f"Cambiaste las condiciones de la negociación por **{offer['player']}**.\n\n"
                f"Ahora debe responder **{_other_club(offer, interaction.user.id)}**."
            ),
        )
        embed.add_field(name="Nueva propuesta", value=_proposal_text(refreshed), inline=False)
        embed.add_field(name="Ronda", value=str(next_round), inline=True)
        embed.add_field(name="Condiciones", value=message, inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)
        await _notify_counteroffer(interaction, refreshed, interaction.user.id, next_user)


async def _notify_counteroffer(interaction, offer, actor_id, recipient_id):
    actor_club = _club_for_user(offer, actor_id) or "Un club"
    recipient_club = _club_for_user(offer, recipient_id) or "el otro club"
    embed = discord.Embed(
        title="🔄 NUEVA CONTRAOFERTA",
        description=(
            f"**{actor_club}** modificó la propuesta por **{offer['player']}**.\n\n"
            f"Turno de respuesta: **{recipient_club}**."
        ),
    )
    embed.add_field(name="Propuesta actual", value=_proposal_text(offer), inline=False)
    embed.add_field(name="Ronda", value=str(_round(offer)), inline=True)
    embed.add_field(name="Condiciones", value=offer["message"], inline=False)
    embed.set_footer(text=f"Oferta #{offer['id']} • /mercado → Mis ofertas")

    try:
        user = APP.bot.get_user(int(recipient_id))
        if user is None:
            user = await APP.bot.fetch_user(int(recipient_id))
        await user.send(embed=embed)
    except (discord.Forbidden, discord.NotFound, discord.HTTPException) as exc:
        print(f"WARNING AJAP: DM contraoferta #{offer['id']} falló: {exc}")

    channel = interaction.channel
    if channel is not None and hasattr(channel, "send"):
        try:
            await channel.send(
                content=(
                    f"<@{int(recipient_id)}> 🔄 **{actor_club} hizo una contraoferta "
                    f"por {offer['player']}.**"
                ),
                embed=embed,
                allowed_mentions=discord.AllowedMentions(users=True, roles=False, everyone=False),
            )
        except (discord.Forbidden, discord.HTTPException) as exc:
            print(f"WARNING AJAP: aviso público contraoferta #{offer['id']} falló: {exc}")


class NegotiationDecisionView(discord.ui.View):
    def __init__(self, offer_id):
        super().__init__(timeout=300)
        self.offer_id = int(offer_id)

    async def _current(self, interaction):
        if not APP.mercado_abierto():
            await interaction.response.send_message(
                "🔒 El mercado está cerrado. La negociación queda congelada.", ephemeral=True
            )
            return None
        offer = APP.oferta_por_id(self.offer_id)
        if not offer or offer["status"] != "PENDIENTE":
            await interaction.response.send_message("⚠️ Esta oferta ya fue resuelta.", ephemeral=True)
            return None
        if interaction.user.id != _decision_user_id(offer):
            await interaction.response.send_message(
                "⏳ La respuesta le corresponde al otro club.", ephemeral=True
            )
            return None
        return offer

    @discord.ui.button(label="Aceptar", emoji="✅", style=discord.ButtonStyle.success, row=0)
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        offer = await self._current(interaction)
        if not offer:
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
        offered_id = offer["offered_player_id"] if _has(offer, "offered_player_id") else None
        if offered_id:
            offered = APP.jugador_por_id(int(offered_id))
            if not offered or offered["club"].casefold() != offer["from_club"].casefold():
                await interaction.response.send_message(
                    "⚠️ El jugador pedido ya no pertenece al club comprador.", ephemeral=True
                )
                return
            if APP.operacion_abierta_del_jugador(offered["name"]):
                await interaction.response.send_message(
                    f"⚠️ **{offered['name']}** ya tiene otra operación pendiente.", ephemeral=True
                )
                return

        kind = offer["offer_kind"] if _has(offer, "offer_kind") else "DINERO"
        deal_group = f"OFERTA-{offer['id']}"
        notes = f"Ronda {_round(offer)} | {offer['message'] or 'Sin condiciones adicionales'}"
        if offered:
            notes += f" | Contraparte: {offered['name']} ({APP.player_code(offered['id'])})"

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
                        f"Contraparte de {offer['player']} | Oferta #{offer['id']} | Ronda {_round(offer)}",
                        deal_group,
                    ),
                )
                created_ops.append(cur.lastrowid)

        embed = discord.Embed(
            title="🤝 Acuerdo aceptado • Falta administración",
            description=(
                f"Se aceptó la negociación por **{offer['player']}** entre "
                f"**{offer['to_club']}** y **{offer['from_club']}**.\n\n"
                "Los planteles **todavía no fueron modificados**."
            ),
        )
        embed.add_field(name="Propuesta final", value=_proposal_text(offer), inline=False)
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

    @discord.ui.button(label="Contraofertar", emoji="🔄", style=discord.ButtonStyle.primary, row=0)
    async def counter(self, interaction: discord.Interaction, button: discord.ui.Button):
        offer = await self._current(interaction)
        if not offer:
            return
        buyer_roster_club = offer["from_club"]
        picker = RosterPickerView(
            actor_id=interaction.user.id,
            club=buyer_roster_club,
            mode="counter",
            offer_id=offer["id"],
        )
        await interaction.response.send_message(embed=picker.embed(), view=picker, ephemeral=True)

    @discord.ui.button(label="Rechazar", emoji="❌", style=discord.ButtonStyle.danger, row=0)
    async def reject(self, interaction: discord.Interaction, button: discord.ui.Button):
        offer = await self._current(interaction)
        if not offer:
            return
        with APP.db() as conn:
            conn.execute("UPDATE offers SET status = 'RECHAZADA' WHERE id = ?", (offer["id"],))
        await interaction.response.edit_message(
            embed=discord.Embed(
                title="❌ Negociación rechazada",
                description=f"La negociación por **{offer['player']}** quedó cerrada.",
            ),
            view=None,
        )


class NegotiationOffersSelect(discord.ui.Select):
    def __init__(self, offers):
        options = []
        for offer in offers[:25]:
            round_no = _round(offer)
            offered_name = offer["offered_player"] if _has(offer, "offered_player") else None
            proposal = offered_name or offer["amount"]
            options.append(
                discord.SelectOption(
                    label=f"#{offer['id']} • {offer['player']}"[:100],
                    description=f"Ronda {round_no} • {proposal} • {offer['status']}"[:100],
                    value=str(offer["id"]),
                )
            )
        super().__init__(
            placeholder="Elegí una negociación",
            min_values=1,
            max_values=1,
            options=options,
            row=0,
        )

    async def callback(self, interaction: discord.Interaction):
        offer = APP.oferta_por_id(int(self.values[0]))
        if not offer or interaction.user.id not in (offer["from_id"], offer["to_id"]):
            await interaction.response.send_message("Oferta no disponible.", ephemeral=True)
            return

        direction = "enviada" if interaction.user.id == offer["from_id"] else "recibida"
        embed = discord.Embed(
            title=f"💰 Oferta #{offer['id']} • Ronda {_round(offer)}",
            description=f"Oferta {direction} por **{offer['player']}**.",
        )
        embed.add_field(name="Club comprador", value=offer["from_club"], inline=True)
        embed.add_field(name="Club vendedor", value=offer["to_club"], inline=True)
        embed.add_field(name="Modalidad", value=offer["offer_kind"], inline=True)
        embed.add_field(name="Propuesta", value=_proposal_text(offer), inline=False)
        embed.add_field(name="Estado", value=offer["status"], inline=True)
        embed.add_field(name="Condiciones", value=offer["message"], inline=False)

        view = None
        if offer["status"] == "PENDIENTE":
            decision_id = _decision_user_id(offer)
            if interaction.user.id == decision_id:
                view = NegotiationDecisionView(offer["id"])
                embed.add_field(
                    name="Tu turno",
                    value="Podés **Aceptar**, **Contraofertar** o **Rechazar**.",
                    inline=False,
                )
            else:
                waiting_club = _club_for_user(offer, decision_id) or "el otro club"
                embed.add_field(
                    name="⏳ Esperando respuesta",
                    value=f"Ahora debe responder **{waiting_club}**.",
                    inline=False,
                )

        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)


class NegotiationOffersView(discord.ui.View):
    def __init__(self, offers):
        super().__init__(timeout=300)
        if offers:
            self.add_item(NegotiationOffersSelect(offers))


async def _open_offer_picker(interaction, publication):
    if not APP.mercado_abierto():
        await interaction.response.send_message(
            "🔒 El mercado está cerrado. Las ofertas todavía no están habilitadas.", ephemeral=True
        )
        return
    buyer_club = APP.club_de(interaction.user.id)
    if not buyer_club:
        await interaction.response.send_message("⚠️ Primero elegí tu club.", ephemeral=True)
        return
    if interaction.user.id == publication["owner_id"] or buyer_club.casefold() == publication["club"].casefold():
        await interaction.response.send_message("⚠️ No podés ofertar por tu propio jugador.", ephemeral=True)
        return

    picker = RosterPickerView(
        actor_id=interaction.user.id,
        club=buyer_club,
        mode="offer",
        publication_id=publication["id"],
    )
    await interaction.response.send_message(embed=picker.embed(), view=picker, ephemeral=True)


async def _transferibles_callback(select_self, interaction: discord.Interaction):
    publication = APP.publicacion_por_id(int(select_self.values[0]))
    if not publication:
        await interaction.response.send_message("Publicación no disponible.", ephemeral=True)
        return
    await _open_offer_picker(interaction, publication)


async def _global_offer_callback(button_self, interaction: discord.Interaction):
    publication = APP.publicacion_por_id(button_self.publication_id)
    if not publication:
        await interaction.response.send_message("⚠️ Ese jugador ya no está publicado.", ephemeral=True)
        return
    await _open_offer_picker(interaction, publication)


def apply_negotiation_picker_patch(main_module):
    global APP, FINAL_OFFER_MODAL
    APP = main_module
    if getattr(main_module, "_ajap_negotiation_picker_patch", False):
        return

    ensure_schema()
    FINAL_OFFER_MODAL = main_module.OfertaModal

    # Transferibles: replace free typing with the roster picker.
    main_module.TransferiblesSelect.callback = _transferibles_callback

    # Global search has its own offer button class, so patch that callback too.
    global_search.OfferFromSearchButton.callback = _global_offer_callback

    # Mis ofertas becomes a real two-way negotiation history/decision screen.
    main_module.OfertasSelect = NegotiationOffersSelect
    main_module.OfertasView = NegotiationOffersView
    main_module.OfertaDecisionView = NegotiationDecisionView
    flexible.FlexibleOfertaDecisionView = NegotiationDecisionView

    main_module.RosterPickerView = RosterPickerView
    main_module.CounterOfferModal = CounterOfferModal
    main_module._ajap_negotiation_picker_patch = True
    print("AJAP negociación avanzada activa: selector de plantel + contraofertas con cambio de jugador")
