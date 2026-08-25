import os
import sqlite3
from pathlib import Path

import discord
from discord.ext import commands

TOKEN = os.getenv("DISCORD_TOKEN")
DB_PATH = os.getenv("DB_PATH", "ajap_market.db")

if not TOKEN:
    raise RuntimeError("Falta la variable de entorno DISCORD_TOKEN")

Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)


def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with db() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS clubs (
                user_id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS publications (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                player TEXT NOT NULL,
                position TEXT NOT NULL,
                club TEXT NOT NULL,
                price TEXT NOT NULL,
                detail TEXT NOT NULL,
                owner_id INTEGER NOT NULL,
                active INTEGER NOT NULL DEFAULT 1,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS offers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                publication_id INTEGER NOT NULL,
                player TEXT NOT NULL,
                amount TEXT NOT NULL,
                message TEXT NOT NULL,
                from_id INTEGER NOT NULL,
                from_club TEXT NOT NULL,
                to_id INTEGER NOT NULL,
                to_club TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'PENDIENTE',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS transfers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                player TEXT NOT NULL,
                seller TEXT NOT NULL,
                buyer TEXT NOT NULL,
                amount TEXT NOT NULL,
                offer_id INTEGER NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );
            """
        )


def money(value: str) -> str:
    cleaned = value.strip().replace("$", "").replace(".", "").replace(",", "")
    if cleaned.isdigit():
        return f"${int(cleaned):,}".replace(",", ".")
    return value.strip()


def club_de(user_id: int):
    with db() as conn:
        row = conn.execute("SELECT name FROM clubs WHERE user_id = ?", (user_id,)).fetchone()
    return row["name"] if row else None


def publicaciones_activas(limit=25):
    with db() as conn:
        return conn.execute(
            "SELECT * FROM publications WHERE active = 1 ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()


def publicacion_por_id(pub_id: int):
    with db() as conn:
        return conn.execute(
            "SELECT * FROM publications WHERE id = ? AND active = 1", (pub_id,)
        ).fetchone()


def oferta_por_id(oferta_id: int):
    with db() as conn:
        return conn.execute("SELECT * FROM offers WHERE id = ?", (oferta_id,)).fetchone()


def transferibles_embed() -> discord.Embed:
    publicaciones = publicaciones_activas(20)
    embed = discord.Embed(
        title="📋 Jugadores transferibles",
        description="Publicaciones activas del AJAP Transfer Market.",
    )

    if not publicaciones:
        embed.description = "Todavía no hay jugadores publicados."
        return embed

    for pub in publicaciones:
        embed.add_field(
            name=f"#{pub['id']} • {pub['player']} • {pub['position']}",
            value=(
                f"🏟️ **Club:** {pub['club']}\n"
                f"💵 **Precio:** {pub['price']}\n"
                f"📝 **Detalle:** {pub['detail']}\n"
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
        with db() as conn:
            conn.execute(
                """
                INSERT INTO clubs (user_id, name) VALUES (?, ?)
                ON CONFLICT(user_id) DO UPDATE SET name = excluded.name
                """,
                (interaction.user.id, nombre),
            )

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
                "⚠️ Primero tenés que registrar tu club con `/club`.", ephemeral=True
            )
            return

        jugador = self.jugador.value.strip()
        posicion = self.posicion.value.strip().upper()
        precio = money(self.precio.value)
        detalle = self.detalle.value.strip() or "Sin observaciones"

        with db() as conn:
            cur = conn.execute(
                """
                INSERT INTO publications (player, position, club, price, detail, owner_id)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (jugador, posicion, club, precio, detalle, interaction.user.id),
            )
            pub_id = cur.lastrowid

        embed = discord.Embed(
            title="✅ Jugador publicado",
            description=f"**{jugador}** ya aparece en Transferibles.",
        )
        embed.add_field(name="Posición", value=posicion, inline=True)
        embed.add_field(name="Club", value=club, inline=True)
        embed.add_field(name="Precio", value=precio, inline=True)
        embed.add_field(name="Detalle", value=detalle, inline=False)
        embed.set_footer(text=f"Publicación #{pub_id}")
        await interaction.response.send_message(embed=embed, ephemeral=True)


class OfertaModal(discord.ui.Modal):
    def __init__(self, publicacion):
        super().__init__(title=f"Oferta por {publicacion['player'][:30]}")
        self.publicacion_id = publicacion["id"]

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
        pub = publicacion_por_id(self.publicacion_id)
        if not pub:
            await interaction.response.send_message(
                "⚠️ Esa publicación ya no está disponible.", ephemeral=True
            )
            return

        if interaction.user.id == pub["owner_id"]:
            await interaction.response.send_message(
                "⚠️ No podés ofertar por una publicación propia.", ephemeral=True
            )
            return

        comprador_club = club_de(interaction.user.id)
        if not comprador_club:
            await interaction.response.send_message(
                "⚠️ Primero registrá tu club con `/club` para poder ofertar.", ephemeral=True
            )
            return

        monto = money(self.monto.value)
        mensaje = self.mensaje.value.strip() or "Sin condiciones adicionales"
        with db() as conn:
            cur = conn.execute(
                """
                INSERT INTO offers
                (publication_id, player, amount, message, from_id, from_club, to_id, to_club)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    pub["id"], pub["player"], monto, mensaje,
                    interaction.user.id, comprador_club, pub["owner_id"], pub["club"]
                ),
            )
            oferta_id = cur.lastrowid

        embed = discord.Embed(
            title="💰 Oferta enviada",
            description=f"Tu oferta por **{pub['player']}** fue registrada.",
        )
        embed.add_field(name="Club comprador", value=comprador_club, inline=True)
        embed.add_field(name="Monto", value=monto, inline=True)
        embed.add_field(name="Estado", value="🟡 PENDIENTE", inline=True)
        embed.add_field(name="Condiciones", value=mensaje, inline=False)
        embed.set_footer(text=f"Oferta #{oferta_id}")
        await interaction.response.send_message(embed=embed, ephemeral=True)


class TransferiblesSelect(discord.ui.Select):
    def __init__(self, publicaciones):
        options = [
            discord.SelectOption(
                label=pub["player"][:100],
                description=f"{pub['position']} • {pub['club']} • {pub['price']}"[:100],
                value=str(pub["id"]),
            )
            for pub in publicaciones[:25]
        ]
        super().__init__(
            placeholder="Elegí un jugador para ofertar",
            min_values=1,
            max_values=1,
            options=options,
        )

    async def callback(self, interaction: discord.Interaction):
        pub = publicacion_por_id(int(self.values[0]))
        if not pub:
            await interaction.response.send_message(
                "La publicación ya no está disponible.", ephemeral=True
            )
            return
        await interaction.response.send_modal(OfertaModal(pub))


class TransferiblesView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=180)
        publicaciones = publicaciones_activas(25)
        if publicaciones:
            self.add_item(TransferiblesSelect(publicaciones))


class OfertaDecisionView(discord.ui.View):
    def __init__(self, oferta_id: int):
        super().__init__(timeout=180)
        self.oferta_id = oferta_id

    @discord.ui.button(label="Aceptar", emoji="✅", style=discord.ButtonStyle.success)
    async def aceptar(self, interaction: discord.Interaction, button: discord.ui.Button):
        oferta = oferta_por_id(self.oferta_id)
        if not oferta or interaction.user.id != oferta["to_id"]:
            await interaction.response.send_message("No podés gestionar esta oferta.", ephemeral=True)
            return
        if oferta["status"] != "PENDIENTE":
            await interaction.response.send_message("Esta oferta ya fue resuelta.", ephemeral=True)
            return

        pub = publicacion_por_id(oferta["publication_id"])
        if not pub:
            with db() as conn:
                conn.execute("UPDATE offers SET status = 'CANCELADA' WHERE id = ?", (oferta["id"],))
            await interaction.response.send_message("La publicación ya no está disponible.", ephemeral=True)
            return

        with db() as conn:
            conn.execute("UPDATE offers SET status = 'ACEPTADA' WHERE id = ?", (oferta["id"],))
            conn.execute("UPDATE publications SET active = 0 WHERE id = ?", (pub["id"],))
            conn.execute(
                """
                UPDATE offers SET status = 'RECHAZADA'
                WHERE publication_id = ? AND id != ? AND status = 'PENDIENTE'
                """,
                (pub["id"], oferta["id"]),
            )
            cur = conn.execute(
                """
                INSERT INTO transfers (player, seller, buyer, amount, offer_id)
                VALUES (?, ?, ?, ?, ?)
                """,
                (oferta["player"], oferta["to_club"], oferta["from_club"], oferta["amount"], oferta["id"]),
            )
            transferencia_id = cur.lastrowid

        embed = discord.Embed(
            title="🤝 Transferencia acordada",
            description=f"La oferta por **{oferta['player']}** fue aceptada.",
        )
        embed.add_field(name="Sale de", value=oferta["to_club"], inline=True)
        embed.add_field(name="Llega a", value=oferta["from_club"], inline=True)
        embed.add_field(name="Monto", value=oferta["amount"], inline=True)
        embed.set_footer(text=f"Transferencia #{transferencia_id} • Oferta #{oferta['id']}")
        await interaction.response.edit_message(embed=embed, view=None)

    @discord.ui.button(label="Rechazar", emoji="❌", style=discord.ButtonStyle.danger)
    async def rechazar(self, interaction: discord.Interaction, button: discord.ui.Button):
        oferta = oferta_por_id(self.oferta_id)
        if not oferta or interaction.user.id != oferta["to_id"]:
            await interaction.response.send_message("No podés gestionar esta oferta.", ephemeral=True)
            return
        if oferta["status"] != "PENDIENTE":
            await interaction.response.send_message("Esta oferta ya fue resuelta.", ephemeral=True)
            return

        with db() as conn:
            conn.execute("UPDATE offers SET status = 'RECHAZADA' WHERE id = ?", (oferta["id"],))

        embed = discord.Embed(
            title="❌ Oferta rechazada",
            description=f"Rechazaste la oferta por **{oferta['player']}**.",
        )
        embed.add_field(name="Monto", value=oferta["amount"], inline=True)
        embed.set_footer(text=f"Oferta #{oferta['id']}")
        await interaction.response.edit_message(embed=embed, view=None)


class OfertasSelect(discord.ui.Select):
    def __init__(self, ofertas):
        options = [
            discord.SelectOption(
                label=f"#{o['id']} • {o['player']}"[:100],
                description=f"{o['from_club']} ofrece {o['amount']}"[:100],
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
        oferta = oferta_por_id(int(self.values[0]))
        if not oferta or oferta["to_id"] != interaction.user.id:
            await interaction.response.send_message("Oferta no disponible.", ephemeral=True)
            return

        embed = discord.Embed(
            title=f"💰 Oferta #{oferta['id']}",
            description=f"Oferta recibida por **{oferta['player']}**.",
        )
        embed.add_field(name="Club comprador", value=oferta["from_club"], inline=True)
        embed.add_field(name="Monto", value=oferta["amount"], inline=True)
        embed.add_field(name="Estado", value=oferta["status"], inline=True)
        embed.add_field(name="Condiciones", value=oferta["message"], inline=False)
        await interaction.response.send_message(
            embed=embed,
            view=OfertaDecisionView(oferta["id"]) if oferta["status"] == "PENDIENTE" else None,
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

    @discord.ui.button(label="Buscar jugadores", emoji="🔎", style=discord.ButtonStyle.primary, custom_id="mercado_buscar")
    async def buscar_jugadores(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(embed=transferibles_embed(), view=TransferiblesView(), ephemeral=True)

    @discord.ui.button(label="Publicar jugador", emoji="📤", style=discord.ButtonStyle.success, custom_id="mercado_publicar")
    async def publicar_jugador(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not club_de(interaction.user.id):
            await interaction.response.send_message("⚠️ Primero registrá tu club usando `/club`.", ephemeral=True)
            return
        await interaction.response.send_modal(PublicarJugadorModal())

    @discord.ui.button(label="Transferibles", emoji="📋", style=discord.ButtonStyle.secondary, custom_id="mercado_transferibles")
    async def transferibles(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(embed=transferibles_embed(), view=TransferiblesView(), ephemeral=True)

    @discord.ui.button(label="Mis ofertas", emoji="💰", style=discord.ButtonStyle.danger, custom_id="mercado_ofertas")
    async def ofertas(self, interaction: discord.Interaction, button: discord.ui.Button):
        with db() as conn:
            propias = conn.execute(
                """
                SELECT * FROM offers
                WHERE from_id = ? OR to_id = ?
                ORDER BY id DESC LIMIT 15
                """,
                (interaction.user.id, interaction.user.id),
            ).fetchall()
            recibidas_pendientes = conn.execute(
                """
                SELECT * FROM offers
                WHERE to_id = ? AND status = 'PENDIENTE'
                ORDER BY id DESC LIMIT 25
                """,
                (interaction.user.id,),
            ).fetchall()

        embed = discord.Embed(title="💰 Mis ofertas", description="Ofertas enviadas y recibidas.")
        if not propias:
            embed.description = "Todavía no tenés ofertas enviadas ni recibidas."
        else:
            for oferta in propias:
                enviada = oferta["from_id"] == interaction.user.id
                tipo = "📤 Enviada" if enviada else "📥 Recibida"
                contraparte = oferta["to_id"] if enviada else oferta["from_id"]
                icono = {"PENDIENTE": "🟡", "ACEPTADA": "🟢", "RECHAZADA": "🔴", "CANCELADA": "⚫"}.get(oferta["status"], "⚪")
                embed.add_field(
                    name=f"{tipo} • #{oferta['id']} • {oferta['player']}",
                    value=(
                        f"💵 **{oferta['amount']}**\n"
                        f"👤 <@{contraparte}>\n"
                        f"📝 {oferta['message']}\n"
                        f"{icono} {oferta['status']}"
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
    print(f"Base de datos: {DB_PATH}")


@bot.tree.command(name="ping", description="Comprueba si AJAP Transfer Market está online")
async def ping(interaction: discord.Interaction):
    latency_ms = round(bot.latency * 1000)
    await interaction.response.send_message(f"🏓 AJAP Transfer Market v0.1 está online. Ping: {latency_ms} ms")


@bot.tree.command(name="club", description="Registra o actualiza el club vinculado a tu cuenta")
async def club(interaction: discord.Interaction):
    await interaction.response.send_modal(RegistrarClubModal())


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
    embed.add_field(name="🏟️ Tu club", value=club or "No registrado", inline=False)
    embed.add_field(name="🤝 Negociaciones", value="Habilitadas", inline=False)
    embed.set_footer(text="AJAP Transfer Market • PES 6")
    await interaction.response.send_message(embed=embed, view=MercadoView())


@bot.tree.command(name="transferencias", description="Muestra las últimas transferencias confirmadas")
async def transferencias(interaction: discord.Interaction):
    with db() as conn:
        rows = conn.execute("SELECT * FROM transfers ORDER BY id DESC LIMIT 15").fetchall()

    embed = discord.Embed(title="🤝 Transferencias confirmadas")
    if not rows:
        embed.description = "Todavía no hay transferencias confirmadas."
    else:
        for t in rows:
            embed.add_field(
                name=f"#{t['id']} • {t['player']}",
                value=f"{t['seller']} ➜ **{t['buyer']}**\n💵 {t['amount']}",
                inline=False,
            )
    await interaction.response.send_message(embed=embed)


init_db()
bot.run(TOKEN)
