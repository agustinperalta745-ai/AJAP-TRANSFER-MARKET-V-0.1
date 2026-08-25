import os
import itertools

import discord
from discord.ext import commands

TOKEN = os.getenv("DISCORD_TOKEN")

if not TOKEN:
    raise RuntimeError("Falta la variable de entorno DISCORD_TOKEN")

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

# Datos temporales de la demo. Se mantienen mientras el proceso del bot siga activo.
PUBLICACIONES = []
OFERTAS = []
TRANSFERENCIAS = []
CLUBES = {}
PUBLICACION_IDS = itertools.count(1)
OFERTA_IDS = itertools.count(1)
TRANSFERENCIA_IDS = itertools.count(1)


def money(value: str) -> str:
    cleaned = value.strip().replace("$", "").replace(".", "").replace(",", "")
    if cleaned.isdigit():
        return f"${int(cleaned):,}".replace(",", ".")
    return value.strip()


def club_de(user_id: int):
    return CLUBES.get(user_id)


def transferibles_embed() -> discord.Embed:
    embed = discord.Embed(
        title="📋 Jugadores transferibles",
        description="Publicaciones activas del AJAP Transfer Market.",
    )

    if not PUBLICACIONES:
        embed.description = "Todavía no hay jugadores publicados."
        return embed

    for pub in PUBLICACIONES[:20]:
        embed.add_field(
            name=f"#{pub['id']} • {pub['jugador']} • {pub['posicion']}",
            value=(
                f"🏟️ **Club:** {pub['club']}\n"
                f"💵 **Precio:** {pub['precio']}\n"
                f"📝 **Detalle:** {pub['detalle']}\n"
                f"👤 Responsable: <@{pub['owner_id']}>"
            ),
            inline=False,
        )

    embed.set_footer(text="Seleccioná un jugador abajo para enviar una oferta")
    return embed


class RegistrarClubModal(discord.ui.Modal, title="Registrar mi club"):
    nombre = discord.ui.TextInput(
        label="Nombre del club",
        placeholder="Ej: Boca Juniors",
        max_length=60,
    )

    async def on_submit(self, interaction: discord.Interaction):
        nombre = self.nombre.value.strip()
        CLUBES[interaction.user.id] = nombre
        embed = discord.Embed(
            title="✅ Club registrado",
            description=f"Tu cuenta de Discord quedó vinculada a **{nombre}**.",
        )
        embed.set_footer(text="Las publicaciones usarán este club automáticamente")
        await interaction.response.send_message(embed=embed, ephemeral=True)


class PublicarJugadorModal(discord.ui.Modal, title="Publicar jugador"):
    jugador = discord.ui.TextInput(
        label="Nombre del jugador",
        placeholder="Ej: Juan Román Riquelme",
        max_length=60,
    )
    posicion = discord.ui.TextInput(
        label="Posición",
        placeholder="Ej: MP, DC, MC, CT...",
        max_length=20,
    )
    precio = discord.ui.TextInput(
        label="Precio pedido",
        placeholder="Ej: 2500000",
        max_length=30,
    )
    detalle = discord.ui.TextInput(
        label="Observación",
        placeholder="Ej: Venta definitiva / negociable",
        required=False,
        max_length=100,
    )

    async def on_submit(self, interaction: discord.Interaction):
        club = club_de(interaction.user.id)
        if not club:
            await interaction.response.send_message(
                "⚠️ Primero tenés que registrar tu club con `/club`.",
                ephemeral=True,
            )
            return

        pub = {
            "id": next(PUBLICACION_IDS),
            "jugador": self.jugador.value.strip(),
            "posicion": self.posicion.value.strip().upper(),
            "club": club,
            "precio": money(self.precio.value),
            "detalle": self.detalle.value.strip() or "Sin observaciones",
            "owner_id": interaction.user.id,
        }
        PUBLICACIONES.append(pub)

        embed = discord.Embed(
            title="✅ Jugador publicado",
            description=f"**{pub['jugador']}** ya aparece en Transferibles.",
        )
        embed.add_field(name="Posición", value=pub["posicion"], inline=True)
        embed.add_field(name="Club", value=pub["club"], inline=True)
        embed.add_field(name="Precio", value=pub["precio"], inline=True)
        embed.add_field(name="Detalle", value=pub["detalle"], inline=False)
        embed.set_footer(text=f"Publicación #{pub['id']}")
        await interaction.response.send_message(embed=embed, ephemeral=True)


class OfertaModal(discord.ui.Modal):
    def __init__(self, publicacion: dict):
        super().__init__(title=f"Oferta por {publicacion['jugador'][:30]}")
        self.publicacion = publicacion

        self.monto = discord.ui.TextInput(
            label="Monto de la oferta",
            placeholder="Ej: 2000000",
            max_length=30,
        )
        self.mensaje = discord.ui.TextInput(
            label="Mensaje / condiciones",
            placeholder="Ej: Pago inmediato / negociable",
            required=False,
            max_length=150,
        )
        self.add_item(self.monto)
        self.add_item(self.mensaje)

    async def on_submit(self, interaction: discord.Interaction):
        if interaction.user.id == self.publicacion["owner_id"]:
            await interaction.response.send_message(
                "⚠️ No podés ofertar por una publicación propia.", ephemeral=True
            )
            return

        comprador_club = club_de(interaction.user.id)
        if not comprador_club:
            await interaction.response.send_message(
                "⚠️ Primero registrá tu club con `/club` para poder ofertar.",
                ephemeral=True,
            )
            return

        if self.publicacion not in PUBLICACIONES:
            await interaction.response.send_message(
                "⚠️ Esa publicación ya no está disponible.", ephemeral=True
            )
            return

        oferta = {
            "id": next(OFERTA_IDS),
            "publicacion_id": self.publicacion["id"],
            "jugador": self.publicacion["jugador"],
            "monto": money(self.monto.value),
            "mensaje": self.mensaje.value.strip() or "Sin condiciones adicionales",
            "from_id": interaction.user.id,
            "from_club": comprador_club,
            "to_id": self.publicacion["owner_id"],
            "to_club": self.publicacion["club"],
            "estado": "PENDIENTE",
        }
        OFERTAS.append(oferta)

        embed = discord.Embed(
            title="💰 Oferta enviada",
            description=f"Tu oferta por **{oferta['jugador']}** fue registrada.",
        )
        embed.add_field(name="Club comprador", value=comprador_club, inline=True)
        embed.add_field(name="Monto", value=oferta["monto"], inline=True)
        embed.add_field(name="Estado", value="🟡 PENDIENTE", inline=True)
        embed.add_field(name="Condiciones", value=oferta["mensaje"], inline=False)
        embed.set_footer(text=f"Oferta #{oferta['id']}")
        await interaction.response.send_message(embed=embed, ephemeral=True)


class TransferiblesSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(
                label=pub["jugador"][:100],
                description=f"{pub['posicion']} • {pub['club']} • {pub['precio']}"[:100],
                value=str(pub["id"]),
            )
            for pub in PUBLICACIONES[:25]
        ]
        super().__init__(
            placeholder="Elegí un jugador para ofertar",
            min_values=1,
            max_values=1,
            options=options,
        )

    async def callback(self, interaction: discord.Interaction):
        pub_id = int(self.values[0])
        pub = next((p for p in PUBLICACIONES if p["id"] == pub_id), None)
        if not pub:
            await interaction.response.send_message(
                "La publicación ya no está disponible.", ephemeral=True
            )
            return
        await interaction.response.send_modal(OfertaModal(pub))


class TransferiblesView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=180)
        if PUBLICACIONES:
            self.add_item(TransferiblesSelect())


class OfertaDecisionView(discord.ui.View):
    def __init__(self, oferta: dict):
        super().__init__(timeout=180)
        self.oferta = oferta

    @discord.ui.button(label="Aceptar", emoji="✅", style=discord.ButtonStyle.success)
    async def aceptar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.oferta["to_id"]:
            await interaction.response.send_message("No podés gestionar esta oferta.", ephemeral=True)
            return
        if self.oferta["estado"] != "PENDIENTE":
            await interaction.response.send_message("Esta oferta ya fue resuelta.", ephemeral=True)
            return

        pub = next(
            (p for p in PUBLICACIONES if p["id"] == self.oferta["publicacion_id"]),
            None,
        )
        if not pub:
            self.oferta["estado"] = "CANCELADA"
            await interaction.response.send_message(
                "La publicación ya no está disponible.", ephemeral=True
            )
            return

        self.oferta["estado"] = "ACEPTADA"
        PUBLICACIONES.remove(pub)

        for otra in OFERTAS:
            if (
                otra["publicacion_id"] == self.oferta["publicacion_id"]
                and otra["id"] != self.oferta["id"]
                and otra["estado"] == "PENDIENTE"
            ):
                otra["estado"] = "RECHAZADA"

        transferencia = {
            "id": next(TRANSFERENCIA_IDS),
            "jugador": self.oferta["jugador"],
            "vendedor": self.oferta["to_club"],
            "comprador": self.oferta["from_club"],
            "monto": self.oferta["monto"],
            "oferta_id": self.oferta["id"],
        }
        TRANSFERENCIAS.append(transferencia)

        embed = discord.Embed(
            title="🤝 Transferencia acordada",
            description=f"La oferta por **{transferencia['jugador']}** fue aceptada.",
        )
        embed.add_field(name="Sale de", value=transferencia["vendedor"], inline=True)
        embed.add_field(name="Llega a", value=transferencia["comprador"], inline=True)
        embed.add_field(name="Monto", value=transferencia["monto"], inline=True)
        embed.set_footer(text=f"Transferencia #{transferencia['id']} • Oferta #{self.oferta['id']}")
        await interaction.response.edit_message(embed=embed, view=None)

    @discord.ui.button(label="Rechazar", emoji="❌", style=discord.ButtonStyle.danger)
    async def rechazar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.oferta["to_id"]:
            await interaction.response.send_message("No podés gestionar esta oferta.", ephemeral=True)
            return
        if self.oferta["estado"] != "PENDIENTE":
            await interaction.response.send_message("Esta oferta ya fue resuelta.", ephemeral=True)
            return

        self.oferta["estado"] = "RECHAZADA"
        embed = discord.Embed(
            title="❌ Oferta rechazada",
            description=f"Rechazaste la oferta por **{self.oferta['jugador']}**.",
        )
        embed.add_field(name="Monto", value=self.oferta["monto"], inline=True)
        embed.set_footer(text=f"Oferta #{self.oferta['id']}")
        await interaction.response.edit_message(embed=embed, view=None)


class OfertasSelect(discord.ui.Select):
    def __init__(self, ofertas):
        options = [
            discord.SelectOption(
                label=f"#{o['id']} • {o['jugador']}"[:100],
                description=f"{o['from_club']} ofrece {o['monto']}"[:100],
                value=str(o["id"]),
            )
            for o in ofertas[:25]
        ]
        super().__init__(
            placeholder="Elegí una oferta recibida para gestionarla",
            min_values=1,
            max_values=1,
            options=options,
        )

    async def callback(self, interaction: discord.Interaction):
        oferta_id = int(self.values[0])
        oferta = next((o for o in OFERTAS if o["id"] == oferta_id), None)
        if not oferta or oferta["to_id"] != interaction.user.id:
            await interaction.response.send_message("Oferta no disponible.", ephemeral=True)
            return

        embed = discord.Embed(
            title=f"💰 Oferta #{oferta['id']}",
            description=f"Oferta recibida por **{oferta['jugador']}**.",
        )
        embed.add_field(name="Club comprador", value=oferta["from_club"], inline=True)
        embed.add_field(name="Monto", value=oferta["monto"], inline=True)
        embed.add_field(name="Estado", value=oferta["estado"], inline=True)
        embed.add_field(name="Condiciones", value=oferta["mensaje"], inline=False)
        await interaction.response.send_message(
            embed=embed,
            view=OfertaDecisionView(oferta) if oferta["estado"] == "PENDIENTE" else None,
            ephemeral=True,
        )


class OfertasView(discord.ui.View):
    def __init__(self, ofertas_recibidas):
        super().__init__(timeout=180)
        if ofertas_recibidas:
            self.add_item(OfertasSelect(ofertas_recibidas))


class MercadoView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Buscar jugadores",
        emoji="🔎",
        style=discord.ButtonStyle.primary,
        custom_id="mercado_buscar",
    )
    async def buscar_jugadores(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await interaction.response.send_message(
            embed=transferibles_embed(), view=TransferiblesView(), ephemeral=True
        )

    @discord.ui.button(
        label="Publicar jugador",
        emoji="📤",
        style=discord.ButtonStyle.success,
        custom_id="mercado_publicar",
    )
    async def publicar_jugador(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        if not club_de(interaction.user.id):
            await interaction.response.send_message(
                "⚠️ Primero registrá tu club usando `/club`.", ephemeral=True
            )
            return
        await interaction.response.send_modal(PublicarJugadorModal())

    @discord.ui.button(
        label="Transferibles",
        emoji="📋",
        style=discord.ButtonStyle.secondary,
        custom_id="mercado_transferibles",
    )
    async def transferibles(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await interaction.response.send_message(
            embed=transferibles_embed(), view=TransferiblesView(), ephemeral=True
        )

    @discord.ui.button(
        label="Mis ofertas",
        emoji="💰",
        style=discord.ButtonStyle.danger,
        custom_id="mercado_ofertas",
    )
    async def ofertas(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        propias = [
            oferta
            for oferta in OFERTAS
            if oferta["from_id"] == interaction.user.id
            or oferta["to_id"] == interaction.user.id
        ]
        recibidas_pendientes = [
            oferta
            for oferta in OFERTAS
            if oferta["to_id"] == interaction.user.id and oferta["estado"] == "PENDIENTE"
        ]

        embed = discord.Embed(
            title="💰 Mis ofertas",
            description="Ofertas enviadas y recibidas en esta sesión.",
        )
        if not propias:
            embed.description = "Todavía no tenés ofertas enviadas ni recibidas."
        else:
            for oferta in propias[-15:]:
                tipo = "📤 Enviada" if oferta["from_id"] == interaction.user.id else "📥 Recibida"
                contraparte = oferta["to_id"] if tipo.startswith("📤") else oferta["from_id"]
                estado_emoji = {
                    "PENDIENTE": "🟡",
                    "ACEPTADA": "🟢",
                    "RECHAZADA": "🔴",
                    "CANCELADA": "⚫",
                }.get(oferta["estado"], "⚪")
                embed.add_field(
                    name=f"{tipo} • #{oferta['id']} • {oferta['jugador']}",
                    value=(
                        f"💵 **{oferta['monto']}**\n"
                        f"🏟️ {oferta['from_club']} → {oferta['to_club']}\n"
                        f"👤 <@{contraparte}>\n"
                        f"📝 {oferta['mensaje']}\n"
                        f"{estado_emoji} {oferta['estado']}"
                    ),
                    inline=False,
                )

        await interaction.response.send_message(
            embed=embed,
            view=OfertasView(recibidas_pendientes),
            ephemeral=True,
        )


@bot.event
async def on_ready():
    bot.add_view(MercadoView())

    try:
        synced = await bot.tree.sync()
        print(f"Comandos sincronizados: {len(synced)}")
    except Exception as exc:
        print(f"Error sincronizando comandos: {exc}")

    print(f"Bot conectado como {bot.user} (ID: {bot.user.id})")


@bot.tree.command(name="ping", description="Comprueba si AJAP Transfer Market está online")
async def ping(interaction: discord.Interaction):
    latency_ms = round(bot.latency * 1000)
    await interaction.response.send_message(
        f"🏓 AJAP Transfer Market v0.1 está online. Ping: {latency_ms} ms"
    )


@bot.tree.command(name="club", description="Registra o cambia el club vinculado a tu Discord")
async def club(interaction: discord.Interaction):
    actual = club_de(interaction.user.id)
    if actual:
        embed = discord.Embed(
            title="🏟️ Mi club",
            description=f"Actualmente estás vinculado a **{actual}**.",
        )
        view = discord.ui.View(timeout=120)
        boton = discord.ui.Button(label="Cambiar club", emoji="✏️", style=discord.ButtonStyle.primary)

        async def cambiar(i: discord.Interaction):
            if i.user.id != interaction.user.id:
                await i.response.send_message("Este botón no es para vos.", ephemeral=True)
                return
            await i.response.send_modal(RegistrarClubModal())

        boton.callback = cambiar
        view.add_item(boton)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
    else:
        await interaction.response.send_modal(RegistrarClubModal())


@bot.tree.command(name="transferencias", description="Muestra las transferencias cerradas en esta sesión")
async def transferencias(interaction: discord.Interaction):
    embed = discord.Embed(
        title="🤝 Transferencias cerradas",
        description="Historial de operaciones acordadas en esta sesión.",
    )
    if not TRANSFERENCIAS:
        embed.description = "Todavía no se cerró ninguna transferencia."
    else:
        for t in TRANSFERENCIAS[-15:]:
            embed.add_field(
                name=f"#{t['id']} • {t['jugador']}",
                value=f"🏟️ {t['vendedor']} → {t['comprador']}\n💵 **{t['monto']}**",
                inline=False,
            )
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="mercado", description="Abre AJAP Transfer Market")
async def mercado(interaction: discord.Interaction):
    club = club_de(interaction.user.id)
    embed = discord.Embed(
        title="⚽ AJAP TRANSFER MARKET v0.1",
        description=(
            "**Centro de operaciones del mercado de fichajes**\n\n"
            "Desde este panel los clubes pueden publicar jugadores, consultar transferibles "
            "y enviar ofertas dentro de Discord.\n\n"
            "Seleccioná una opción para continuar."
        ),
    )
    embed.add_field(name="🟢 Mercado", value="ABIERTO", inline=True)
    embed.add_field(name="⚙️ Sistema", value="Beta v0.1", inline=True)
    embed.add_field(name="🏟️ Tu club", value=club or "Sin registrar — usá /club", inline=False)
    embed.add_field(name="🤝 Negociaciones", value="Habilitadas", inline=False)
    embed.set_footer(text="AJAP Transfer Market • PES 6")

    await interaction.response.send_message(embed=embed, view=MercadoView())


bot.run(TOKEN)
