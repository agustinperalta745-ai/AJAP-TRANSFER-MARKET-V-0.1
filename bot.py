import os
import sqlite3
from pathlib import Path

import discord
from discord import app_commands
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

            CREATE TABLE IF NOT EXISTS roster_players (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL COLLATE NOCASE UNIQUE,
                position TEXT NOT NULL,
                club TEXT NOT NULL,
                added_by INTEGER,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
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

            CREATE TABLE IF NOT EXISTS market_state (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                is_open INTEGER NOT NULL DEFAULT 0,
                updated_by INTEGER,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );

            INSERT OR IGNORE INTO market_state (id, is_open) VALUES (1, 0);
            """
        )


def money(value: str) -> str:
    cleaned = value.strip().replace("$", "").replace(".", "").replace(",", "")
    if cleaned.isdigit():
        return f"${int(cleaned):,}".replace(",", ".")
    return value.strip()


def price_number(value: str):
    cleaned = value.strip().replace("$", "").replace(".", "").replace(",", "")
    return int(cleaned) if cleaned.isdigit() else None


def club_de(user_id: int):
    with db() as conn:
        row = conn.execute("SELECT name FROM clubs WHERE user_id = ?", (user_id,)).fetchone()
    return row["name"] if row else None


def es_admin(interaction: discord.Interaction) -> bool:
    return bool(
        interaction.guild
        and isinstance(interaction.user, discord.Member)
        and interaction.user.guild_permissions.administrator
    )


def mercado_abierto() -> bool:
    with db() as conn:
        row = conn.execute("SELECT is_open FROM market_state WHERE id = 1").fetchone()
    return bool(row and row["is_open"])


def cambiar_estado_mercado(abierto: bool, admin_id: int):
    with db() as conn:
        conn.execute(
            """
            UPDATE market_state
            SET is_open = ?, updated_by = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = 1
            """,
            (1 if abierto else 0, admin_id),
        )


def jugador_por_nombre(nombre: str):
    with db() as conn:
        return conn.execute(
            "SELECT * FROM roster_players WHERE name = ? COLLATE NOCASE",
            (nombre.strip(),),
        ).fetchone()


def jugadores_de_club(club: str, limit=50):
    with db() as conn:
        return conn.execute(
            """
            SELECT * FROM roster_players
            WHERE club = ? COLLATE NOCASE
            ORDER BY position, name
            LIMIT ?
            """,
            (club.strip(), limit),
        ).fetchall()


def publicacion_activa_del_jugador(nombre: str):
    with db() as conn:
        return conn.execute(
            """
            SELECT * FROM publications
            WHERE player = ? COLLATE NOCASE AND active = 1
            ORDER BY id DESC LIMIT 1
            """,
            (nombre.strip(),),
        ).fetchone()


def publicaciones_activas(limit=25):
    with db() as conn:
        return conn.execute(
            "SELECT * FROM publications WHERE active = 1 ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()


def buscar_publicaciones(nombre="", posicion="", club="", precio_max="", limit=25):
    nombre = nombre.strip().lower()
    posicion = posicion.strip().lower()
    club = club.strip().lower()
    maximo = price_number(precio_max) if precio_max.strip() else None

    with db() as conn:
        rows = conn.execute(
            "SELECT * FROM publications WHERE active = 1 ORDER BY id DESC LIMIT 200"
        ).fetchall()

    resultados = []
    for pub in rows:
        if nombre and nombre not in pub["player"].lower():
            continue
        if posicion and posicion not in pub["position"].lower():
            continue
        if club and club not in pub["club"].lower():
            continue
        if maximo is not None:
            precio_pub = price_number(pub["price"])
            if precio_pub is None or precio_pub > maximo:
                continue
        resultados.append(pub)
        if len(resultados) >= limit:
            break
    return resultados


def publicacion_por_id(pub_id: int):
    with db() as conn:
        return conn.execute(
            "SELECT * FROM publications WHERE id = ? AND active = 1", (pub_id,)
        ).fetchone()


def oferta_por_id(oferta_id: int):
    with db() as conn:
        return conn.execute("SELECT * FROM offers WHERE id = ?", (oferta_id,)).fetchone()


def publicaciones_embed(publicaciones, titulo="📋 Jugadores transferibles", descripcion=None):
    embed = discord.Embed(
        title=titulo,
        description=descripcion or "Publicaciones activas del AJAP Transfer Market.",
    )
    if not publicaciones:
        embed.description = "No encontramos jugadores que coincidan con esos filtros."
        return embed

    for pub in publicaciones[:20]:
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

    if mercado_abierto():
        embed.set_footer(text="Mercado abierto • Seleccioná un jugador abajo para enviar una oferta")
    else:
        embed.set_footer(text="Mercado cerrado • Podés consultar jugadores, pero todavía no ofertar")
    return embed


def transferibles_embed():
    publicaciones = publicaciones_activas(20)
    if not publicaciones:
        embed = discord.Embed(title="📋 Jugadores transferibles")
        embed.description = "Todavía no hay jugadores publicados."
        return embed
    return publicaciones_embed(publicaciones)


class RegistrarClubModal(discord.ui.Modal, title="Registrar mi club"):
    nombre = discord.ui.TextInput(label="Nombre del club", placeholder="Ej: Boca Juniors", max_length=60)

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
    jugador = discord.ui.TextInput(label="Nombre del jugador", placeholder="Ej: Lionel Messi", max_length=60)
    posicion = discord.ui.TextInput(label="Posición", placeholder="Ej: ED, DC, MP, MC...", max_length=20)
    precio = discord.ui.TextInput(label="Precio pedido", placeholder="Ej: 2500000", max_length=30)
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

        jugador_escrito = self.jugador.value.strip()
        ficha = jugador_por_nombre(jugador_escrito)
        if not ficha:
            await interaction.response.send_message(
                "⛔ Ese futbolista no está cargado en ningún plantel oficial. Pedile a un administrador que lo cargue primero.",
                ephemeral=True,
            )
            return

        if ficha["club"].casefold() != club.casefold():
            await interaction.response.send_message(
                f"⛔ **{ficha['name']}** pertenece a **{ficha['club']}**. Solo el club propietario puede publicarlo.",
                ephemeral=True,
            )
            return

        if publicacion_activa_del_jugador(ficha["name"]):
            await interaction.response.send_message(
                f"⚠️ **{ficha['name']}** ya tiene una publicación activa.", ephemeral=True
            )
            return

        posicion = self.posicion.value.strip().upper() or ficha["position"]
        precio = money(self.precio.value)
        detalle = self.detalle.value.strip() or "Sin observaciones"

        with db() as conn:
            cur = conn.execute(
                """
                INSERT INTO publications (player, position, club, price, detail, owner_id)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (ficha["name"], posicion, club, precio, detalle, interaction.user.id),
            )
            pub_id = cur.lastrowid

        embed = discord.Embed(
            title="✅ Jugador publicado",
            description=f"**{ficha['name']}** ya aparece en Transferibles.",
        )
        embed.add_field(name="Posición", value=posicion, inline=True)
        embed.add_field(name="Club", value=club, inline=True)
        embed.add_field(name="Precio", value=precio, inline=True)
        embed.add_field(name="Detalle", value=detalle, inline=False)
        embed.set_footer(text=f"Publicación #{pub_id} • Propiedad verificada por plantel")
        await interaction.response.send_message(embed=embed, ephemeral=True)


class OfertaModal(discord.ui.Modal):
    def __init__(self, publicacion):
        super().__init__(title=f"Oferta por {publicacion['player'][:30]}")
        self.publicacion_id = publicacion["id"]
        self.monto = discord.ui.TextInput(label="Monto de la oferta", placeholder="Ej: 2000000", max_length=30)
        self.mensaje = discord.ui.TextInput(
            label="Mensaje / condiciones",
            placeholder="Ej: Pago inmediato / negociable",
            required=False,
            max_length=150,
        )
        self.add_item(self.monto)
        self.add_item(self.mensaje)

    async def on_submit(self, interaction: discord.Interaction):
        if not mercado_abierto():
            await interaction.response.send_message(
                "🔒 El mercado está cerrado. Podés consultar y publicar jugadores, pero las ofertas se habilitan cuando un administrador abra el mercado.",
                ephemeral=True,
            )
            return

        pub = publicacion_por_id(self.publicacion_id)
        if not pub:
            await interaction.response.send_message("⚠️ Esa publicación ya no está disponible.", ephemeral=True)
            return

        ficha = jugador_por_nombre(pub["player"])
        if not ficha or ficha["club"].casefold() != pub["club"].casefold():
            await interaction.response.send_message(
                "⚠️ La propiedad de este jugador cambió y la publicación ya no es válida.", ephemeral=True
            )
            return

        if interaction.user.id == pub["owner_id"]:
            await interaction.response.send_message("⚠️ No podés ofertar por una publicación propia.", ephemeral=True)
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

        embed = discord.Embed(title="💰 Oferta enviada", description=f"Tu oferta por **{pub['player']}** fue registrada.")
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
        super().__init__(placeholder="Elegí un jugador para ofertar", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        if not mercado_abierto():
            await interaction.response.send_message(
                "🔒 El mercado todavía está cerrado. Podés ver los transferibles, pero no enviar ofertas hasta que un administrador lo abra.",
                ephemeral=True,
            )
            return
        pub = publicacion_por_id(int(self.values[0]))
        if not pub:
            await interaction.response.send_message("La publicación ya no está disponible.", ephemeral=True)
            return
        await interaction.response.send_modal(OfertaModal(pub))


class TransferiblesView(discord.ui.View):
    def __init__(self, publicaciones=None):
        super().__init__(timeout=180)
        publicaciones = publicaciones if publicaciones is not None else publicaciones_activas(25)
        if publicaciones:
            self.add_item(TransferiblesSelect(publicaciones))


class BuscarJugadoresModal(discord.ui.Modal, title="Buscar jugadores"):
    nombre = discord.ui.TextInput(label="Nombre", placeholder="Ej: Messi (opcional)", required=False, max_length=60)
    posicion = discord.ui.TextInput(label="Posición", placeholder="Ej: ED, DC, MP... (opcional)", required=False, max_length=20)
    club = discord.ui.TextInput(label="Club", placeholder="Ej: Barcelona FC (opcional)", required=False, max_length=60)
    precio_max = discord.ui.TextInput(label="Precio máximo", placeholder="Ej: 30000000 (opcional)", required=False, max_length=30)

    async def on_submit(self, interaction: discord.Interaction):
        if self.precio_max.value.strip() and price_number(self.precio_max.value) is None:
            await interaction.response.send_message(
                "⚠️ El precio máximo debe ser un número. Ejemplo: `30000000`.", ephemeral=True
            )
            return

        resultados = buscar_publicaciones(
            self.nombre.value, self.posicion.value, self.club.value, self.precio_max.value, 25
        )
        filtros = []
        if self.nombre.value.strip():
            filtros.append(f"Nombre: **{self.nombre.value.strip()}**")
        if self.posicion.value.strip():
            filtros.append(f"Posición: **{self.posicion.value.strip().upper()}**")
        if self.club.value.strip():
            filtros.append(f"Club: **{self.club.value.strip()}**")
        if self.precio_max.value.strip():
            filtros.append(f"Máximo: **{money(self.precio_max.value)}**")

        descripcion = " • ".join(filtros) if filtros else "Todos los jugadores disponibles."
        embed = publicaciones_embed(resultados, f"🔎 Resultados de búsqueda ({len(resultados)})", descripcion)
        await interaction.response.send_message(embed=embed, view=TransferiblesView(resultados), ephemeral=True)


class OfertaDecisionView(discord.ui.View):
    def __init__(self, oferta_id: int):
        super().__init__(timeout=180)
        self.oferta_id = oferta_id

    @discord.ui.button(label="Aceptar", emoji="✅", style=discord.ButtonStyle.success)
    async def aceptar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not mercado_abierto():
            await interaction.response.send_message(
                "🔒 El mercado está cerrado. Las ofertas pendientes quedan congeladas hasta la próxima apertura.", ephemeral=True
            )
            return

        oferta = oferta_por_id(self.oferta_id)
        if not oferta or interaction.user.id != oferta["to_id"]:
            await interaction.response.send_message("No podés gestionar esta oferta.", ephemeral=True)
            return
        if oferta["status"] != "PENDIENTE":
            await interaction.response.send_message("Esta oferta ya fue resuelta.", ephemeral=True)
            return

        pub = publicacion_por_id(oferta["publication_id"])
        ficha = jugador_por_nombre(oferta["player"])
        if not pub or not ficha or ficha["club"].casefold() != oferta["to_club"].casefold():
            with db() as conn:
                conn.execute("UPDATE offers SET status = 'CANCELADA' WHERE id = ?", (oferta["id"],))
            await interaction.response.send_message(
                "⚠️ La publicación o la propiedad del jugador cambió. La oferta fue cancelada.", ephemeral=True
            )
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
            conn.execute(
                """
                UPDATE roster_players
                SET club = ?, updated_at = CURRENT_TIMESTAMP
                WHERE name = ? COLLATE NOCASE
                """,
                (oferta["from_club"], oferta["player"]),
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
            description=f"La oferta por **{oferta['player']}** fue aceptada y el plantel fue actualizado.",
        )
        embed.add_field(name="Sale de", value=oferta["to_club"], inline=True)
        embed.add_field(name="Llega a", value=oferta["from_club"], inline=True)
        embed.add_field(name="Monto", value=oferta["amount"], inline=True)
        embed.set_footer(text=f"Transferencia #{transferencia_id} • Oferta #{oferta['id']}")
        await interaction.response.edit_message(embed=embed, view=None)

    @discord.ui.button(label="Rechazar", emoji="❌", style=discord.ButtonStyle.danger)
    async def rechazar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not mercado_abierto():
            await interaction.response.send_message(
                "🔒 El mercado está cerrado. Las ofertas pendientes quedan congeladas hasta la próxima apertura.", ephemeral=True
            )
            return
        oferta = oferta_por_id(self.oferta_id)
        if not oferta or interaction.user.id != oferta["to_id"]:
            await interaction.response.send_message("No podés gestionar esta oferta.", ephemeral=True)
            return
        if oferta["status"] != "PENDIENTE":
            await interaction.response.send_message("Esta oferta ya fue resuelta.", ephemeral=True)
            return
        with db() as conn:
            conn.execute("UPDATE offers SET status = 'RECHAZADA' WHERE id = ?", (oferta["id"],))
        embed = discord.Embed(title="❌ Oferta rechazada", description=f"Rechazaste la oferta por **{oferta['player']}**.")
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
        super().__init__(placeholder="Elegí una oferta recibida para gestionarla", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        oferta = oferta_por_id(int(self.values[0]))
        if not oferta or oferta["to_id"] != interaction.user.id:
            await interaction.response.send_message("Oferta no disponible.", ephemeral=True)
            return
        embed = discord.Embed(title=f"💰 Oferta #{oferta['id']}", description=f"Oferta recibida por **{oferta['player']}**.")
        embed.add_field(name="Club comprador", value=oferta["from_club"], inline=True)
        embed.add_field(name="Monto", value=oferta["amount"], inline=True)
        embed.add_field(name="Estado", value=oferta["status"], inline=True)
        embed.add_field(name="Condiciones", value=oferta["message"], inline=False)
        if oferta["status"] == "PENDIENTE" and not mercado_abierto():
            embed.add_field(
                name="🔒 Mercado cerrado",
                value="La oferta queda congelada hasta que un administrador vuelva a abrir el mercado.",
                inline=False,
            )
        await interaction.response.send_message(
            embed=embed,
            view=OfertaDecisionView(oferta["id"]) if oferta["status"] == "PENDIENTE" else None,
            ephemeral=True,
        )


class OfertasView(discord.ui.View):
    def __init__(self, ofertas):
        super().__init__(timeout=180)
        if ofertas:
            self.add_item(OfertasSelect(ofertas))


class MercadoView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Buscar jugadores", emoji="🔎", style=discord.ButtonStyle.primary, custom_id="mercado_buscar")
    async def buscar_jugadores(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(BuscarJugadoresModal())

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
                "SELECT * FROM offers WHERE from_id = ? OR to_id = ? ORDER BY id DESC LIMIT 15",
                (interaction.user.id, interaction.user.id),
            ).fetchall()
            pendientes = conn.execute(
                "SELECT * FROM offers WHERE to_id = ? AND status = 'PENDIENTE' ORDER BY id DESC LIMIT 25",
                (interaction.user.id,),
            ).fetchall()

        estado = "🟢 Mercado abierto" if mercado_abierto() else "🔒 Mercado cerrado"
        embed = discord.Embed(title="💰 Mis ofertas", description=f"Ofertas enviadas y recibidas.\n{estado}")
        if not propias:
            embed.description = f"Todavía no tenés ofertas enviadas ni recibidas.\n{estado}"
        else:
            for oferta in propias:
                enviada = oferta["from_id"] == interaction.user.id
                tipo = "📤 Enviada" if enviada else "📥 Recibida"
                contraparte = oferta["to_id"] if enviada else oferta["from_id"]
                icono = {"PENDIENTE": "🟡", "ACEPTADA": "🟢", "RECHAZADA": "🔴", "CANCELADA": "⚫"}.get(oferta["status"], "⚪")
                embed.add_field(
                    name=f"{tipo} • #{oferta['id']} • {oferta['player']}",
                    value=f"💵 **{oferta['amount']}**\n👤 <@{contraparte}>\n📝 {oferta['message']}\n{icono} {oferta['status']}",
                    inline=False,
                )
        await interaction.response.send_message(embed=embed, view=OfertasView(pendientes), ephemeral=True)


@bot.event
async def on_ready():
    if not getattr(bot, "_persistent_view_added", False):
        bot.add_view(MercadoView())
        bot._persistent_view_added = True
    try:
        synced = await bot.tree.sync()
        print(f"Comandos sincronizados: {len(synced)}")
    except Exception as exc:
        print(f"Error sincronizando comandos: {exc}")
    print(f"Bot conectado como {bot.user} (ID: {bot.user.id})")
    print(f"Base de datos: {DB_PATH}")


@bot.tree.command(name="ping", description="Comprueba si AJAP Transfer Market está online")
async def ping(interaction: discord.Interaction):
    await interaction.response.send_message(f"🏓 AJAP Transfer Market v0.1 está online. Ping: {round(bot.latency * 1000)} ms")


@bot.tree.command(name="club", description="Registra o actualiza el club vinculado a tu cuenta")
async def club(interaction: discord.Interaction):
    await interaction.response.send_modal(RegistrarClubModal())


@bot.tree.command(name="plantel", description="Muestra el plantel oficial de un club")
@app_commands.describe(club="Nombre del club. Si lo dejás vacío muestra tu propio plantel")
async def plantel(interaction: discord.Interaction, club: str | None = None):
    nombre_club = club.strip() if club else club_de(interaction.user.id)
    if not nombre_club:
        await interaction.response.send_message(
            "⚠️ Indicá un club o registrá el tuyo primero con `/club`.", ephemeral=True
        )
        return
    jugadores = jugadores_de_club(nombre_club)
    embed = discord.Embed(title=f"🏟️ Plantel • {nombre_club}")
    if not jugadores:
        embed.description = "No hay jugadores cargados para este club."
    else:
        lineas = [f"**{j['position']}** • {j['name']}" for j in jugadores]
        embed.description = "\n".join(lineas[:50])
        embed.set_footer(text=f"{len(jugadores)} jugador(es) • Plantel oficial del bot")
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="agregar_jugador", description="Admin: agrega un futbolista a un plantel oficial")
@app_commands.describe(jugador="Nombre del futbolista", posicion="Posición", club="Club propietario")
async def agregar_jugador(interaction: discord.Interaction, jugador: str, posicion: str, club: str):
    if not es_admin(interaction):
        await interaction.response.send_message("⛔ Solo un administrador puede modificar planteles.", ephemeral=True)
        return
    jugador = jugador.strip()
    posicion = posicion.strip().upper()
    club = club.strip()
    existente = jugador_por_nombre(jugador)
    if existente:
        await interaction.response.send_message(
            f"⚠️ **{existente['name']}** ya pertenece a **{existente['club']}**. Usá `/mover_jugador` si querés cambiarlo de club.",
            ephemeral=True,
        )
        return
    with db() as conn:
        conn.execute(
            "INSERT INTO roster_players (name, position, club, added_by) VALUES (?, ?, ?, ?)",
            (jugador, posicion, club, interaction.user.id),
        )
    await interaction.response.send_message(f"✅ **{jugador}** ({posicion}) agregado al plantel de **{club}**.")


@bot.tree.command(name="mover_jugador", description="Admin: mueve un futbolista a otro club")
@app_commands.describe(jugador="Nombre del futbolista", club_destino="Nuevo club propietario")
async def mover_jugador(interaction: discord.Interaction, jugador: str, club_destino: str):
    if not es_admin(interaction):
        await interaction.response.send_message("⛔ Solo un administrador puede modificar planteles.", ephemeral=True)
        return
    ficha = jugador_por_nombre(jugador)
    if not ficha:
        await interaction.response.send_message("⚠️ Ese jugador no existe en los planteles oficiales.", ephemeral=True)
        return
    destino = club_destino.strip()
    origen = ficha["club"]
    with db() as conn:
        conn.execute(
            "UPDATE roster_players SET club = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
            (destino, ficha["id"]),
        )
        conn.execute(
            "UPDATE publications SET active = 0 WHERE player = ? COLLATE NOCASE AND active = 1",
            (ficha["name"],),
        )
        conn.execute(
            "UPDATE offers SET status = 'CANCELADA' WHERE player = ? COLLATE NOCASE AND status = 'PENDIENTE'",
            (ficha["name"],),
        )
    await interaction.response.send_message(
        f"✅ **{ficha['name']}** movido de **{origen}** a **{destino}**. Sus publicaciones/ofertas pendientes fueron cerradas."
    )


@bot.tree.command(name="quitar_jugador", description="Admin: elimina un futbolista de los planteles oficiales")
@app_commands.describe(jugador="Nombre del futbolista")
async def quitar_jugador(interaction: discord.Interaction, jugador: str):
    if not es_admin(interaction):
        await interaction.response.send_message("⛔ Solo un administrador puede modificar planteles.", ephemeral=True)
        return
    ficha = jugador_por_nombre(jugador)
    if not ficha:
        await interaction.response.send_message("⚠️ Ese jugador no existe en los planteles oficiales.", ephemeral=True)
        return
    with db() as conn:
        conn.execute("DELETE FROM roster_players WHERE id = ?", (ficha["id"],))
        conn.execute(
            "UPDATE publications SET active = 0 WHERE player = ? COLLATE NOCASE AND active = 1",
            (ficha["name"],),
        )
        conn.execute(
            "UPDATE offers SET status = 'CANCELADA' WHERE player = ? COLLATE NOCASE AND status = 'PENDIENTE'",
            (ficha["name"],),
        )
    await interaction.response.send_message(f"🗑️ **{ficha['name']}** fue eliminado del plantel de **{ficha['club']}**.")


@bot.tree.command(name="mercado", description="Abre AJAP Transfer Market")
async def mercado(interaction: discord.Interaction):
    club = club_de(interaction.user.id)
    abierto = mercado_abierto()
    embed = discord.Embed(
        title="⚽ AJAP TRANSFER MARKET v0.1",
        description=(
            "**Centro de operaciones del mercado de fichajes**\n\n"
            "Los clubes pueden publicar y consultar jugadores durante toda la temporada. "
            "Las negociaciones solo se habilitan cuando un administrador abre oficialmente el mercado.\n\n"
            "Seleccioná una opción para continuar."
        ),
    )
    embed.add_field(name="🟢 Mercado" if abierto else "🔒 Mercado", value="ABIERTO" if abierto else "CERRADO", inline=True)
    embed.add_field(name="⚙️ Sistema", value="Beta v0.1", inline=True)
    embed.add_field(name="🏟️ Tu club", value=club or "No registrado", inline=False)
    embed.add_field(name="🤝 Negociaciones", value="Habilitadas" if abierto else "Bloqueadas", inline=False)
    embed.add_field(name="📤 Publicaciones", value="Habilitadas siempre • Solo jugadores de tu plantel", inline=False)
    embed.set_footer(text="AJAP Transfer Market • PES 6")
    await interaction.response.send_message(embed=embed, view=MercadoView())


@bot.tree.command(name="abrir_mercado", description="Abre oficialmente la ventana de transferencias")
async def abrir_mercado(interaction: discord.Interaction):
    if not es_admin(interaction):
        await interaction.response.send_message("⛔ Solo un administrador del servidor puede abrir el mercado.", ephemeral=True)
        return
    if mercado_abierto():
        await interaction.response.send_message("🟢 El mercado ya está abierto.", ephemeral=True)
        return
    cambiar_estado_mercado(True, interaction.user.id)
    embed = discord.Embed(
        title="🟢 MERCADO DE TRANSFERENCIAS ABIERTO",
        description="La administración abrió oficialmente la ventana. Los clubes ya pueden **enviar, aceptar y rechazar ofertas**.",
    )
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="cerrar_mercado", description="Cierra oficialmente la ventana de transferencias")
async def cerrar_mercado(interaction: discord.Interaction):
    if not es_admin(interaction):
        await interaction.response.send_message("⛔ Solo un administrador del servidor puede cerrar el mercado.", ephemeral=True)
        return
    if not mercado_abierto():
        await interaction.response.send_message("🔒 El mercado ya está cerrado.", ephemeral=True)
        return
    cambiar_estado_mercado(False, interaction.user.id)
    embed = discord.Embed(
        title="🔒 MERCADO DE TRANSFERENCIAS CERRADO",
        description=(
            "Los clubes pueden seguir **publicando y consultando jugadores**, pero no enviar, aceptar ni rechazar ofertas. "
            "Las ofertas pendientes quedan congeladas."
        ),
    )
    await interaction.response.send_message(embed=embed)


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
