"""Publication flow with explicit operation type and loan terms.

When a manager selects a player to publish, choose the operation type first.
Loan publications use a dedicated modal where duration is mandatory, purchase
option is explicit (yes/no), and a value is mandatory only when the option is yes.
"""

import discord

import lyon_test_seed as lyon
import publish_ovr_patch as publish


APP = None


class _FixedValue:
    def __init__(self, value=""):
        self.value = value


def ensure_schema():
    with APP.db() as conn:
        APP.add_column_if_missing(conn, "publications", "loan_seasons", "INTEGER")
        APP.add_column_if_missing(conn, "publications", "purchase_option_enabled", "INTEGER")
        APP.add_column_if_missing(conn, "publications", "purchase_option_value", "TEXT")


def _last_publication_id(player, owner_id):
    with APP.db() as conn:
        row = conn.execute(
            """
            SELECT COALESCE(MAX(id), 0) AS last_id
            FROM publications
            WHERE player = ? COLLATE NOCASE AND owner_id = ?
            """,
            (player, int(owner_id)),
        ).fetchone()
    return int(row["last_id"] if row else 0)


def _new_publication(player, owner_id, after_id):
    with APP.db() as conn:
        return conn.execute(
            """
            SELECT * FROM publications
            WHERE player = ? COLLATE NOCASE
              AND owner_id = ?
              AND id > ?
            ORDER BY id DESC LIMIT 1
            """,
            (player, int(owner_id), int(after_id)),
        ).fetchone()


def _yes_no(value):
    raw = (value or "").strip().casefold()
    if raw in {"si", "sí", "s", "yes", "y"}:
        return True
    if raw in {"no", "n"}:
        return False
    return None


def _validate_player(interaction, player_id, club):
    current = APP.club_de(interaction.user.id)
    if not current or current.casefold() != club.casefold():
        return None, "⛔ Este plantel ya no está vinculado a tu cuenta."

    ficha = APP.jugador_por_id(int(player_id))
    if not ficha or ficha["club"].casefold() != club.casefold():
        return None, "⚠️ Ese jugador ya no está disponible en tu plantel."
    if APP.publicacion_activa_del_jugador(ficha["name"]):
        return None, f"⚠️ **{ficha['name']}** ya tiene una publicación activa."
    if APP.operacion_abierta_del_jugador(ficha["name"]):
        return None, f"⚠️ **{ficha['name']}** ya tiene una operación pendiente."
    return ficha, None


class FixedTypePublicationModal(lyon.RatedPublicarJugadorModal):
    def __init__(self, ficha, operation_type, title_label):
        super().__init__(ficha)
        old_type = self.tipo
        self.remove_item(old_type)
        self.tipo = _FixedValue(operation_type)
        self.title = f"{title_label} • {ficha['name'][:25]}"


class LoanPublicationModal(lyon.RatedPublicarJugadorModal):
    def __init__(self, ficha):
        super().__init__(ficha)

        old_type = self.tipo
        old_price = self.precio
        old_detail = self.detalle
        self.remove_item(old_type)
        self.remove_item(old_price)
        self.remove_item(old_detail)

        self.tipo = _FixedValue("Préstamo")
        self.detalle = _FixedValue("")
        self.title = f"Préstamo • {ficha['name'][:26]}"

        self.precio = discord.ui.TextInput(
            label="Cargo / precio del préstamo",
            placeholder="0 si no pedís dinero • Ej: 5000000",
            default="0",
            required=True,
            max_length=30,
        )
        self.loan_duration = discord.ui.TextInput(
            label="Duración (temporadas)",
            placeholder="Ej: 1",
            required=True,
            max_length=2,
        )
        self.purchase_option = discord.ui.TextInput(
            label="¿Opción de compra? Sí / No",
            placeholder="Escribí Sí o No",
            required=True,
            max_length=3,
        )
        self.purchase_value = discord.ui.TextInput(
            label="Valor opción de compra",
            placeholder="Obligatorio si pusiste Sí • Ej: 30000000",
            required=False,
            max_length=30,
        )
        self.note = discord.ui.TextInput(
            label="Observación (opcional)",
            placeholder="Ej: Negociable",
            required=False,
            max_length=100,
        )

        self.add_item(self.precio)
        self.add_item(self.loan_duration)
        self.add_item(self.purchase_option)
        self.add_item(self.purchase_value)
        self.add_item(self.note)

    async def on_submit(self, interaction: discord.Interaction):
        raw_duration = self.loan_duration.value.strip()
        if not raw_duration.isdigit() or int(raw_duration) <= 0:
            await interaction.response.send_message(
                "⚠️ La **cantidad de temporadas es obligatoria** y debe ser un número mayor a 0.",
                ephemeral=True,
            )
            return
        seasons = int(raw_duration)

        has_option = _yes_no(self.purchase_option.value)
        if has_option is None:
            await interaction.response.send_message(
                "⚠️ En **Opción de compra** escribí solamente **Sí** o **No**.",
                ephemeral=True,
            )
            return

        raw_purchase = self.purchase_value.value.strip()
        purchase_value = None
        if has_option:
            if not raw_purchase:
                await interaction.response.send_message(
                    "⚠️ Marcaste **Sí** en opción de compra, así que el **valor es obligatorio**.",
                    ephemeral=True,
                )
                return
            purchase_number = APP.price_number(raw_purchase)
            if purchase_number is None or purchase_number <= 0:
                await interaction.response.send_message(
                    "⚠️ El valor de la opción de compra debe ser un número mayor a 0.",
                    ephemeral=True,
                )
                return
            purchase_value = APP.money(str(purchase_number))
        elif raw_purchase:
            await interaction.response.send_message(
                "⚠️ Si elegiste **No** en opción de compra, dejá vacío el valor de compra.",
                ephemeral=True,
            )
            return

        option_text = purchase_value if has_option else "Sin opción de compra"
        note = self.note.value.strip()
        terms = (
            f"Préstamo por {seasons} temporada{'s' if seasons != 1 else ''} • "
            f"Opción de compra: {option_text}"
        )
        if note:
            terms += f" • {note}"
        self.detalle = _FixedValue(terms)

        previous_id = _last_publication_id(self.jugador, interaction.user.id)
        await super().on_submit(interaction)

        publication = _new_publication(self.jugador, interaction.user.id, previous_id)
        if not publication:
            return

        with APP.db() as conn:
            conn.execute(
                """
                UPDATE publications
                SET operation_type = 'PRÉSTAMO',
                    loan_seasons = ?,
                    purchase_option_enabled = ?,
                    purchase_option_value = ?
                WHERE id = ?
                """,
                (seasons, 1 if has_option else 0, purchase_value, publication["id"]),
            )


class PublicationTypeView(discord.ui.View):
    def __init__(self, player_id, club, owner_id):
        super().__init__(timeout=300)
        self.player_id = int(player_id)
        self.club = club
        self.owner_id = int(owner_id)

    async def _ficha(self, interaction):
        if int(interaction.user.id) != self.owner_id:
            await interaction.response.send_message(
                "⛔ Esta selección pertenece a otro usuario.", ephemeral=True
            )
            return None
        ficha, error = _validate_player(interaction, self.player_id, self.club)
        if error:
            await interaction.response.send_message(error, ephemeral=True)
            return None
        return ficha

    @discord.ui.button(label="Transferencia", emoji="💰", style=discord.ButtonStyle.success, row=0)
    async def transfer(self, interaction: discord.Interaction, button: discord.ui.Button):
        ficha = await self._ficha(interaction)
        if ficha:
            await interaction.response.send_modal(
                FixedTypePublicationModal(ficha, "Transferencia", "Transferencia")
            )

    @discord.ui.button(label="Préstamo", emoji="🔄", style=discord.ButtonStyle.primary, row=0)
    async def loan(self, interaction: discord.Interaction, button: discord.ui.Button):
        ficha = await self._ficha(interaction)
        if ficha:
            await interaction.response.send_modal(LoanPublicationModal(ficha))

    @discord.ui.button(label="Intercambio", emoji="🔁", style=discord.ButtonStyle.secondary, row=0)
    async def swap(self, interaction: discord.Interaction, button: discord.ui.Button):
        ficha = await self._ficha(interaction)
        if ficha:
            await interaction.response.send_modal(
                FixedTypePublicationModal(ficha, "Intercambio", "Intercambio")
            )

    @discord.ui.button(label="Volver", emoji="⬅️", style=discord.ButtonStyle.secondary, row=1)
    async def back(self, interaction: discord.Interaction, button: discord.ui.Button):
        if int(interaction.user.id) != self.owner_id:
            await interaction.response.send_message("⛔ Esta selección no es tuya.", ephemeral=True)
            return
        await interaction.response.edit_message(
            embed=publish.publish_ranges_embed(self.club),
            view=publish.PublishOVRView(self.club),
        )


def _type_embed(ficha, club):
    embed = discord.Embed(
        title=f"📤 Publicar {ficha['name']}",
        description="Elegí el **tipo de operación** para esta publicación.",
    )
    if "rating" in ficha.keys() and ficha["rating"] is not None:
        embed.add_field(name="⭐ OVR", value=str(ficha["rating"]), inline=True)
    embed.add_field(name="🏟️ Club", value=club, inline=True)
    embed.add_field(
        name="🔄 Préstamo",
        value="Pedirá duración, opción de compra Sí/No y valor cuando corresponda.",
        inline=False,
    )
    return embed


async def _choose_publication_type(select_self, interaction: discord.Interaction):
    ficha = APP.jugador_por_id(int(select_self.values[0]))
    club = getattr(select_self, "club", None)
    if not club or not ficha:
        await interaction.response.send_message("⚠️ Jugador no disponible.", ephemeral=True)
        return

    validated, error = _validate_player(interaction, ficha["id"], club)
    if error:
        await interaction.response.send_message(error, ephemeral=True)
        return

    await interaction.response.edit_message(
        embed=_type_embed(validated, club),
        view=PublicationTypeView(validated["id"], club, interaction.user.id),
    )


def apply_publication_loan_options_patch(runtime):
    global APP
    APP = runtime
    if getattr(runtime, "_ajap_publication_loan_options_patch", False):
        return

    ensure_schema()
    publish.PublishPlayerSelect.callback = _choose_publication_type
    runtime.LoanPublicationModal = LoanPublicationModal
    runtime.PublicationTypeView = PublicationTypeView
    runtime._ajap_publication_loan_options_patch = True
    print("AJAP publicación por tipo activa: préstamo pide temporadas + opción Sí/No + valor")
