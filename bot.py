import csv
import io
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


# -----------------------------
# Base de datos y migraciones
# -----------------------------

def db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def table_columns(conn, table):
    return {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def add_column_if_missing(conn, table, column, definition):
    if column not in table_columns(conn, table):
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")


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

            CREATE TABLE IF NOT EXISTS seasons (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                active INTEGER NOT NULL DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS player_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                player_id INTEGER,
                player TEXT NOT NULL,
                from_club TEXT,
                to_club TEXT NOT NULL,
                transfer_id INTEGER,
                season_id INTEGER,
                event_type TEXT NOT NULL DEFAULT 'TRANSFERENCIA',
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );

            INSERT OR IGNORE INTO market_state (id, is_open) VALUES (1, 0);
            INSERT OR IGNORE INTO seasons (name, active) VALUES ('Temporada 1', 1);
            """
        )

        add_column_if_missing(conn, "publications", "operation_type", "TEXT NOT NULL DEFAULT 'TRANSFERENCIA'")
        add_column_if_missing(conn, "publications", "season_id", "INTEGER")

        add_column_if_missing(conn, "offers", "operation_type", "TEXT NOT NULL DEFAULT 'TRANSFERENCIA'")
        add_column_if_missing(conn, "offers", "season_id", "INTEGER")

        add_column_if_missing(conn, "transfers", "player_id", "INTEGER")
        add_column_if_missing(conn, "transfers", "operation_type", "TEXT NOT NULL DEFAULT 'TRANSFERENCIA'")
        add_column_if_missing(conn, "transfers", "season_id", "INTEGER")
        add_column_if_missing(conn, "transfers", "status", "TEXT NOT NULL DEFAULT 'APLICADA'")
        add_column_if_missing(conn, "transfers", "approved_by", "INTEGER")
        add_column_if_missing(conn, "transfers", "approved_at", "DATETIME")
        add_column_if_missing(conn, "transfers", "applied_by", "INTEGER")
        add_column_if_missing(conn, "transfers", "applied_at", "DATETIME")
        add_column_if_missing(conn, "transfers", "rejected_by", "INTEGER")
        add_column_if_missing(conn, "transfers", "rejected_at", "DATETIME")
        add_column_if_missing(conn, "transfers", "notes", "TEXT")

        conn.execute(
            "UPDATE transfers SET status = 'APLICADA' WHERE status IS NULL OR TRIM(status) = ''"
        )

        season = conn.execute("SELECT id FROM seasons WHERE active = 1 ORDER BY id DESC LIMIT 1").fetchone()
        if not season:
            conn.execute("UPDATE seasons SET active = 0")
            conn.execute("INSERT OR IGNORE INTO seasons (name, active) VALUES ('Temporada 1', 1)")
            season = conn.execute("SELECT id FROM seasons WHERE active = 1 ORDER BY id DESC LIMIT 1").fetchone()

        sid = season["id"]
        conn.execute("UPDATE publications SET season_id = ? WHERE season_id IS NULL", (sid,))
        conn.execute("UPDATE offers SET season_id = ? WHERE season_id IS NULL", (sid,))
        conn.execute("UPDATE transfers SET season_id = ? WHERE season_id IS NULL", (sid,))


def money(value: str) -> str:
    cleaned = value.strip().replace("$", "").replace(".", "").replace(",", "")
    if cleaned.isdigit():
        return f"${int(cleaned):,}".replace(",", ".")
    return value.strip()


def price_number(value: str):
    cleaned = value.strip().replace("$", "").replace(".", "").replace(",", "")
    return int(cleaned) if cleaned.isdigit() else None


def normalizar_tipo(value: str) -> str:
    raw = (value or "").strip().upper()
    aliases = {
        "VENTA": "TRANSFERENCIA",
        "TRANSFERENCIA DEFINITIVA": "TRANSFERENCIA",
        "DEFINITIVA": "TRANSFERENCIA",
        "PRESTAMO": "PRÉSTAMO",
        "PRESTAMO / CESION": "PRÉSTAMO",
        "CESION": "PRÉSTAMO",
        "CESIÓN": "PRÉSTAMO",
        "INTERCAMBIO": "INTERCAMBIO",
        "LIBRE": "JUGADOR LIBRE",
        "JUGADOR LIBRE": "JUGADOR LIBRE",
    }
    return aliases.get(raw, raw or "TRANSFERENCIA")[:40]


def player_code(player_id: int) -> str:
    return f"AJAP-{player_id:06d}"


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


def temporada_activa():
    with db() as conn:
        return conn.execute(
            "SELECT * FROM seasons WHERE active = 1 ORDER BY id DESC LIMIT 1"
        ).fetchone()


def cambiar_temporada(nombre: str):
    nombre = nombre.strip()
    with db() as conn:
        conn.execute("UPDATE seasons SET active = 0")
        conn.execute("INSERT OR IGNORE INTO seasons (name, active) VALUES (?, 0)", (nombre,))
        conn.execute("UPDATE seasons SET active = 1 WHERE name = ?", (nombre,))
        return conn.execute("SELECT * FROM seasons WHERE name = ?", (nombre,)).fetchone()


def jugador_por_nombre(nombre: str):
    with db() as conn:
        return conn.execute(
            "SELECT * FROM roster_players WHERE name = ? COLLATE NOCASE",
            (nombre.strip(),),
        ).fetchone()


def jugador_por_id(player_id: int):
    with db() as conn:
        return conn.execute("SELECT * FROM roster_players WHERE id = ?", (player_id,)).fetchone()


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


def operacion_abierta_del_jugador(nombre: str):
    with db() as conn:
        return conn.execute(
            """
            SELECT * FROM transfers
            WHERE player = ? COLLATE NOCASE
              AND status IN ('PENDIENTE_ADMIN', 'APROBADA')
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
            "SELECT * FROM publications WHERE id = ? AND active = 1",
            (pub_id,),
        ).fetchone()


def oferta_por_id(oferta_id: int):
    with db() as conn:
        return conn.execute("SELECT * FROM offers WHERE id = ?", (oferta_id,)).fetchone()


def operacion_por_id(op_id: int):
    with db() as conn:
        return conn.execute("SELECT * FROM transfers WHERE id = ?", (op_id,)).fetchone()


def operaciones_pendientes(limit=25):
    with db() as conn:
        return conn.execute(
            """
            SELECT t.*, s.name AS season_name
            FROM transfers t
            LEFT JOIN seasons s ON s.id = t.season_id
            WHERE t.status IN ('PENDIENTE_ADMIN', 'APROBADA')
            ORDER BY t.id ASC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()


def historial_jugador(nombre: str, limit=20):
    with db() as conn:
        return conn.execute(
            """
            SELECT h.*, s.name AS season_name
            FROM player_history h
            LEFT JOIN seasons s ON s.id = h.season_id
            WHERE h.player = ? COLLATE NOCASE
            ORDER BY h.id DESC LIMIT ?
            """,
            (nombre.strip(), limit),
        ).fetchall()


# -----------------------------
# Embeds
# -----------------------------

def panel_embed(user_id: int):
    club = club_de(user_id)
    abierto = mercado_abierto()
    temporada = temporada_activa()
    pendientes = len(operaciones_pendientes(100))
    embed = discord.Embed(
        title="⚽ AJAP TRANSFER MARKET v0.1",
        description=(
            "**Centro de operaciones del mercado de fichajes**\n\n"
            "Los acuerdos quedan auditados antes de modificar el plantel oficial del juego."
        ),
    )
    embed.add_field(
        name="🟢 Mercado" if abierto else "🔒 Mercado",
        value="ABIERTO" if abierto else "CERRADO",
        inline=True,
    )
    embed.add_field(name="🏟️ Tu club", value=club or "No registrado", inline=True)
    embed.add_field(name="🗓️ Temporada", value=temporada["name"] if temporada else "Sin temporada", inline=True)
    embed.add_field(
        name="🤝 Negociaciones",
        value="Habilitadas" if abierto else "Bloqueadas hasta que un admin abra el mercado",
        inline=False,
    )
    embed.add_field(name="📤 Publicaciones", value="Disponibles durante toda la temporada", inline=True)
    embed.add_field(name="🛠️ Por procesar en admin", value=str(pendientes), inline=True)
    embed.set_footer(text="AJAP Transfer Market • PES 6")
    return embed


def plantel_embed(club: str):
    jugadores = jugadores_de_club(club)
    embed = discord.Embed(title=f"🏟️ Plantel oficial • {club}")
    if not jugadores:
        embed.description = "No hay jugadores cargados para este club."
    else:
        embed.description = "\n".join(
            f"`{player_code(j['id'])}` • **{j['position']}** • {j['name']}" for j in jugadores[:50]
        )
        embed.set_footer(text=f"{len(jugadores)} jugador(es) • IDs estables para administración")
    return embed


def publicaciones_embed(publicaciones, titulo="📋 Jugadores transferibles", descripcion=None):
    embed = discord.Embed(
        title=titulo,
        description=descripcion or "Publicaciones activas del AJAP Transfer Market.",
    )
    if not publicaciones:
        embed.description = "No encontramos jugadores que coincidan con esos filtros."
        return embed

    for pub in publicaciones[:20]:
        ficha = jugador_por_nombre(pub["player"])
        codigo = player_code(ficha["id"]) if ficha else "SIN-ID"
        embed.add_field(
            name=f"#{pub['id']} • {pub['player']} • {pub['position']}",
            value=(
                f"🆔 `{codigo}`\n"
                f"🏟️ **Club:** {pub['club']}\n"
                f"🔁 **Tipo:** {pub['operation_type']}\n"
                f"💵 **Precio:** {pub['price']}\n"
                f"📝 **Detalle:** {pub['detail']}\n"
                f"👤 Responsable: <@{pub['owner_id']}>"
            ),
            inline=False,
        )

    if mercado_abierto():
        embed.set_footer(text="Mercado abierto • Elegí un jugador para ofertar")
    else:
        embed.set_footer(text="Mercado cerrado • Podés consultar, pero todavía no ofertar")
    return embed


def transferencias_embed():
    with db() as conn:
        rows = conn.execute(
            """
            SELECT t.*, s.name AS season_name
            FROM transfers t LEFT JOIN seasons s ON s.id = t.season_id
            ORDER BY t.id DESC LIMIT 15
            """
        ).fetchall()
    embed = discord.Embed(title="🤝 Operaciones del mercado")
    if not rows:
        embed.description = "Todavía no hay operaciones registradas."
    else:
        icons = {
            "PENDIENTE_ADMIN": "🟡",
            "APROBADA": "🔵",
            "APLICADA": "🟢",
            "RECHAZADA_ADMIN": "🔴",
        }
        for t in rows:
            codigo = player_code(t["player_id"]) if t["player_id"] else "SIN-ID"
            embed.add_field(
                name=f"#{t['id']} • {t['player']} • {t['operation_type']}",
                value=(
                    f"🆔 `{codigo}`\n"
                    f"{t['seller']} ➜ **{t['buyer']}**\n"
                    f"💵 {t['amount']}\n"
                    f"{icons.get(t['status'], '⚪')} **{t['status']}**\n"
                    f"🗓️ {t['season_name'] or 'Sin temporada'}"
                ),
                inline=False,
            )
    return embed


def operaciones_pendientes_embed():
    rows = operaciones_pendientes(25)
    embed = discord.Embed(title="🛠️ Operaciones pendientes • Administración")
    if not rows:
        embed.description = "✅ No hay operaciones pendientes de aprobación o de aplicar en PES."
        return embed
    for t in rows:
        estado = "🟡 Revisar y aprobar" if t["status"] == "PENDIENTE_ADMIN" else "🎮 Aplicar en PES"
        codigo = player_code(t["player_id"]) if t["player_id"] else "SIN-ID"
        embed.add_field(
            name=f"#{t['id']} • {t['player']}",
            value=(
                f"🆔 `{codigo}` • {t['operation_type']}\n"
                f"{t['seller']} ➜ **{t['buyer']}** • {t['amount']}\n"
                f"{estado} • {t['season_name'] or 'Sin temporada'}"
            ),
            inline=False,
        )
    embed.set_footer(text="Aprobar NO mueve el plantel. Aplicar confirma que el cambio ya se hizo en el juego.")
    return embed


def historial_embed(nombre: str):
    ficha = jugador_por_nombre(nombre)
    historial = historial_jugador(nombre)
    embed = discord.Embed(title=f"📚 Historial • {ficha['name'] if ficha else nombre.strip()}")
    if ficha:
        embed.add_field(name="ID", value=f"`{player_code(ficha['id'])}`", inline=True)
        embed.add_field(name="Club actual", value=ficha["club"], inline=True)
        embed.add_field(name="Posición", value=ficha["position"], inline=True)
    if not historial:
        embed.description = "No hay movimientos aplicados registrados para este jugador."
    else:
        for h in historial:
            embed.add_field(
                name=f"{h['season_name'] or 'Sin temporada'} • {h['event_type']}",
                value=f"{h['from_club'] or '—'} ➜ **{h['to_club']}** • Operación #{h['transfer_id'] or '—'}",
                inline=False,
            )
    return embed


class RegistrarClubModal(discord.ui.Modal, title="Registrar / actualizar club"):
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
        await interaction.response.send_message(
            embed=discord.Embed(title="✅ Club registrado", description=f"Tu cuenta quedó vinculada a **{nombre}**."),
            ephemeral=True,
        )


class ClubView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=180)

    @discord.ui.button(label="Cambiar nombre del club", emoji="✏️", style=discord.ButtonStyle.secondary)
    async def cambiar(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(RegistrarClubModal())


class PublicarJugadorModal(discord.ui.Modal):
    def __init__(self, ficha):
        super().__init__(title=f"Publicar {ficha['name'][:30]}")
        self.jugador = ficha["name"]
        self.tipo = discord.ui.TextInput(
            label="Tipo de operación",
            placeholder="Transferencia / Préstamo / Intercambio",
            default="Transferencia",
            max_length=40,
        )
        self.precio = discord.ui.TextInput(label="Precio pedido", placeholder="Ej: 2500000", max_length=30)
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
        club = club_de(interaction.user.id)
        ficha = jugador_por_nombre(self.jugador)
        if not club or not ficha or ficha["club"].casefold() != club.casefold():
            await interaction.response.send_message("⛔ Ese jugador ya no pertenece a tu plantel.", ephemeral=True)
            return
        if publicacion_activa_del_jugador(ficha["name"]):
            await interaction.response.send_message(f"⚠️ **{ficha['name']}** ya tiene una publicación activa.", ephemeral=True)
            return
        if operacion_abierta_del_jugador(ficha["name"]):
            await interaction.response.send_message(
                f"⚠️ **{ficha['name']}** ya tiene una operación aceptada pendiente de administración.", ephemeral=True
            )
            return

        precio = money(self.precio.value)
        detalle = self.detalle.value.strip() or "Sin observaciones"
        tipo = normalizar_tipo(self.tipo.value)
        season = temporada_activa()
        with db() as conn:
            cur = conn.execute(
                """
                INSERT INTO publications
                (player, position, club, price, detail, owner_id, operation_type, season_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (ficha["name"], ficha["position"], club, precio, detalle, interaction.user.id, tipo, season["id"] if season else None),
            )
            pub_id = cur.lastrowid

        embed = discord.Embed(title="✅ Jugador publicado", description=f"**{ficha['name']}** ya aparece en Transferibles.")
        embed.add_field(name="ID", value=f"`{player_code(ficha['id'])}`", inline=True)
        embed.add_field(name="Tipo", value=tipo, inline=True)
        embed.add_field(name="Precio", value=precio, inline=True)
        embed.add_field(name="Detalle", value=detalle, inline=False)
        embed.set_footer(text=f"Publicación #{pub_id}")
        await interaction.response.send_message(embed=embed, ephemeral=True)


class PublicarSelect(discord.ui.Select):
    def __init__(self, jugadores):
        options = [
            discord.SelectOption(
                label=j["name"][:100],
                description=f"{player_code(j['id'])} • {j['position']} • {j['club']}"[:100],
                value=str(j["id"]),
            )
            for j in jugadores[:25]
        ]
        super().__init__(placeholder="Elegí un jugador de tu plantel", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        ficha = jugador_por_id(int(self.values[0]))
        if not ficha:
            await interaction.response.send_message("Jugador no disponible.", ephemeral=True)
            return
        await interaction.response.send_modal(PublicarJugadorModal(ficha))


class PublicarView(discord.ui.View):
    def __init__(self, jugadores):
        super().__init__(timeout=180)
        self.add_item(PublicarSelect(jugadores))


class BuscarJugadoresModal(discord.ui.Modal, title="Buscar jugadores"):
    nombre = discord.ui.TextInput(label="Nombre", required=False, max_length=60)
    posicion = discord.ui.TextInput(label="Posición", required=False, max_length=20)
    club = discord.ui.TextInput(label="Club", required=False, max_length=60)
    precio_max = discord.ui.TextInput(label="Precio máximo", required=False, max_length=30)

    async def on_submit(self, interaction: discord.Interaction):
        if self.precio_max.value.strip() and price_number(self.precio_max.value) is None:
            await interaction.response.send_message("⚠️ El precio máximo debe ser un número.", ephemeral=True)
            return
        resultados = buscar_publicaciones(
            self.nombre.value, self.posicion.value, self.club.value, self.precio_max.value, 25
        )
        await interaction.response.send_message(
            embed=publicaciones_embed(resultados, f"🔎 Resultados de búsqueda ({len(resultados)})"),
            view=TransferiblesView(resultados),
            ephemeral=True,
        )


class OfertaModal(discord.ui.Modal):
    def __init__(self, publicacion):
        super().__init__(title=f"Oferta por {publicacion['player'][:30]}")
        self.publicacion_id = publicacion["id"]
        self.monto = discord.ui.TextInput(label="Monto de la oferta", placeholder="Ej: 2000000", max_length=30)
        self.mensaje = discord.ui.TextInput(label="Mensaje / condiciones", required=False, max_length=150)
        self.add_item(self.monto)
        self.add_item(self.mensaje)

    async def on_submit(self, interaction: discord.Interaction):
        if not mercado_abierto():
            await interaction.response.send_message("🔒 El mercado está cerrado. Las ofertas todavía no están habilitadas.", ephemeral=True)
            return

        pub = publicacion_por_id(self.publicacion_id)
        if not pub:
            await interaction.response.send_message("⚠️ Esa publicación ya no está disponible.", ephemeral=True)
            return

        ficha = jugador_por_nombre(pub["player"])
        if not ficha or ficha["club"].casefold() != pub["club"].casefold():
            await interaction.response.send_message("⚠️ La propiedad del jugador cambió. La publicación ya no es válida.", ephemeral=True)
            return
        if operacion_abierta_del_jugador(pub["player"]):
            await interaction.response.send_message("⚠️ Ese jugador ya tiene un acuerdo aceptado pendiente de administración.", ephemeral=True)
            return
        if interaction.user.id == pub["owner_id"]:
            await interaction.response.send_message("⚠️ No podés ofertar por una publicación propia.", ephemeral=True)
            return

        comprador_club = club_de(interaction.user.id)
        if not comprador_club:
            await interaction.response.send_message("⚠️ Primero registrá tu club desde **Mi club**.", ephemeral=True)
            return
        if comprador_club.casefold() == pub["club"].casefold():
            await interaction.response.send_message("⚠️ El jugador ya pertenece a tu club.", ephemeral=True)
            return

        monto = money(self.monto.value)
        mensaje = self.mensaje.value.strip() or "Sin condiciones adicionales"
        with db() as conn:
            cur = conn.execute(
                """
                INSERT INTO offers
                (publication_id, player, amount, message, from_id, from_club, to_id, to_club, operation_type, season_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    pub["id"], pub["player"], monto, mensaje,
                    interaction.user.id, comprador_club, pub["owner_id"], pub["club"],
                    pub["operation_type"], pub["season_id"],
                ),
            )
            oferta_id = cur.lastrowid

        embed = discord.Embed(title="💰 Oferta enviada", description=f"Tu oferta por **{pub['player']}** fue registrada.")
        embed.add_field(name="Tipo", value=pub["operation_type"], inline=True)
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
        super().__init__(placeholder="Elegí un jugador", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        if not mercado_abierto():
            await interaction.response.send_message("🔒 El mercado está cerrado. Podés ver los jugadores, pero todavía no ofertar.", ephemeral=True)
            return
        pub = publicacion_por_id(int(self.values[0]))
        if not pub:
            await interaction.response.send_message("Publicación no disponible.", ephemeral=True)
            return
        await interaction.response.send_modal(OfertaModal(pub))


class TransferiblesView(discord.ui.View):
    def __init__(self, publicaciones=None):
        super().__init__(timeout=180)
        publicaciones = publicaciones if publicaciones is not None else publicaciones_activas(25)
        if publicaciones:
            self.add_item(TransferiblesSelect(publicaciones))


class OfertaDecisionView(discord.ui.View):
    def __init__(self, oferta_id: int):
        super().__init__(timeout=180)
        self.oferta_id = oferta_id

    @discord.ui.button(label="Aceptar", emoji="✅", style=discord.ButtonStyle.success)
    async def aceptar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not mercado_abierto():
            await interaction.response.send_message("🔒 El mercado está cerrado. La oferta queda congelada.", ephemeral=True)
            return

        oferta = oferta_por_id(self.oferta_id)
        if not oferta or interaction.user.id != oferta["to_id"]:
            await interaction.response.send_message("No podés gestionar esta oferta.", ephemeral=True)
            return
        if oferta["status"] != "PENDIENTE":
            await interaction.response.send_message("Esta oferta ya fue resuelta.", ephemeral=True)
            return
        if operacion_abierta_del_jugador(oferta["player"]):
            await interaction.response.send_message("⚠️ Ese jugador ya tiene otra operación pendiente de administración.", ephemeral=True)
            return

        pub = publicacion_por_id(oferta["publication_id"])
        ficha = jugador_por_nombre(oferta["player"])
        if not pub or not ficha or ficha["club"].casefold() != oferta["to_club"].casefold():
            with db() as conn:
                conn.execute("UPDATE offers SET status = 'CANCELADA' WHERE id = ?", (oferta["id"],))
            await interaction.response.send_message("⚠️ La publicación o propiedad cambió. La oferta fue cancelada.", ephemeral=True)
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
                INSERT INTO transfers
                (player, seller, buyer, amount, offer_id, player_id, operation_type, season_id, status, notes)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'PENDIENTE_ADMIN', ?)
                """,
                (
                    oferta["player"], oferta["to_club"], oferta["from_club"], oferta["amount"], oferta["id"],
                    ficha["id"], oferta["operation_type"], oferta["season_id"], oferta["message"],
                ),
            )
            operacion_id = cur.lastrowid

        embed = discord.Embed(
            title="🤝 Acuerdo aceptado • Falta administración",
            description=(
                f"**{oferta['player']}**: **{oferta['to_club']}** ➜ **{oferta['from_club']}**.\n\n"
                "El jugador **todavía no fue movido del plantel oficial**. Un admin debe aprobar la operación y, después de editar PES, marcarla como aplicada."
            ),
        )
        embed.add_field(name="ID jugador", value=f"`{player_code(ficha['id'])}`", inline=True)
        embed.add_field(name="Monto", value=oferta["amount"], inline=True)
        embed.add_field(name="Estado", value="🟡 PENDIENTE_ADMIN", inline=True)
        embed.set_footer(text=f"Operación #{operacion_id}")
        await interaction.response.edit_message(embed=embed, view=None)

    @discord.ui.button(label="Rechazar", emoji="❌", style=discord.ButtonStyle.danger)
    async def rechazar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not mercado_abierto():
            await interaction.response.send_message("🔒 El mercado está cerrado. La oferta queda congelada.", ephemeral=True)
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
        await interaction.response.edit_message(
            embed=discord.Embed(title="❌ Oferta rechazada", description=f"Rechazaste la oferta por **{oferta['player']}**."),
            view=None,
        )


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
        super().__init__(placeholder="Elegí una oferta recibida", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        oferta = oferta_por_id(int(self.values[0]))
        if not oferta or oferta["to_id"] != interaction.user.id:
            await interaction.response.send_message("Oferta no disponible.", ephemeral=True)
            return
        embed = discord.Embed(title=f"💰 Oferta #{oferta['id']}", description=f"Oferta recibida por **{oferta['player']}**.")
        embed.add_field(name="Club comprador", value=oferta["from_club"], inline=True)
        embed.add_field(name="Tipo", value=oferta["operation_type"], inline=True)
        embed.add_field(name="Monto", value=oferta["amount"], inline=True)
        embed.add_field(name="Estado", value=oferta["status"], inline=True)
        embed.add_field(name="Condiciones", value=oferta["message"], inline=False)
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


class AdminAgregarModal(discord.ui.Modal, title="Agregar jugador"):
    jugador = discord.ui.TextInput(label="Jugador", max_length=60)
    posicion = discord.ui.TextInput(label="Posición", max_length=20)
    club = discord.ui.TextInput(label="Club propietario", max_length=60)

    async def on_submit(self, interaction: discord.Interaction):
        if not es_admin(interaction):
            await interaction.response.send_message("⛔ Solo admins.", ephemeral=True)
            return
        existente = jugador_por_nombre(self.jugador.value)
        if existente:
            await interaction.response.send_message(
                f"⚠️ Ya existe como `{player_code(existente['id'])}` y pertenece a **{existente['club']}**.", ephemeral=True
            )
            return
        with db() as conn:
            cur = conn.execute(
                "INSERT INTO roster_players (name, position, club, added_by) VALUES (?, ?, ?, ?)",
                (self.jugador.value.strip(), self.posicion.value.strip().upper(), self.club.value.strip(), interaction.user.id),
            )
            player_id = cur.lastrowid
        await interaction.response.send_message(
            f"✅ `{player_code(player_id)}` • **{self.jugador.value.strip()}** agregado a **{self.club.value.strip()}**.", ephemeral=True
        )


class AdminMoverModal(discord.ui.Modal, title="Mover jugador manualmente"):
    jugador = discord.ui.TextInput(label="Jugador", max_length=60)
    destino = discord.ui.TextInput(label="Club destino", max_length=60)
    motivo = discord.ui.TextInput(label="Motivo", placeholder="Ej: Corrección administrativa", required=False, max_length=100)

    async def on_submit(self, interaction: discord.Interaction):
        if not es_admin(interaction):
            await interaction.response.send_message("⛔ Solo admins.", ephemeral=True)
            return
        ficha = jugador_por_nombre(self.jugador.value)
        if not ficha:
            await interaction.response.send_message("⚠️ Jugador no encontrado.", ephemeral=True)
            return
        if operacion_abierta_del_jugador(ficha["name"]):
            await interaction.response.send_message("⚠️ Ese jugador tiene una operación pendiente. Resolvela antes de moverlo manualmente.", ephemeral=True)
            return
        destino = self.destino.value.strip()
        season = temporada_activa()
        motivo = self.motivo.value.strip() or "Movimiento manual de administración"
        with db() as conn:
            conn.execute("UPDATE roster_players SET club = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?", (destino, ficha["id"]))
            conn.execute("UPDATE publications SET active = 0 WHERE player = ? COLLATE NOCASE AND active = 1", (ficha["name"],))
            conn.execute("UPDATE offers SET status = 'CANCELADA' WHERE player = ? COLLATE NOCASE AND status = 'PENDIENTE'", (ficha["name"],))
            cur = conn.execute(
                """
                INSERT INTO transfers
                (player, seller, buyer, amount, offer_id, player_id, operation_type, season_id, status,
                 approved_by, approved_at, applied_by, applied_at, notes)
                VALUES (?, ?, ?, '-', 0, ?, 'AJUSTE ADMIN', ?, 'APLICADA', ?, CURRENT_TIMESTAMP, ?, CURRENT_TIMESTAMP, ?)
                """,
                (ficha["name"], ficha["club"], destino, ficha["id"], season["id"] if season else None,
                 interaction.user.id, interaction.user.id, motivo),
            )
            op_id = cur.lastrowid
            conn.execute(
                """
                INSERT INTO player_history (player_id, player, from_club, to_club, transfer_id, season_id, event_type)
                VALUES (?, ?, ?, ?, ?, ?, 'AJUSTE ADMIN')
                """,
                (ficha["id"], ficha["name"], ficha["club"], destino, op_id, season["id"] if season else None),
            )
        await interaction.response.send_message(
            f"✅ `{player_code(ficha['id'])}` • **{ficha['name']}** movido de **{ficha['club']}** a **{destino}**. Operación #{op_id} registrada.",
            ephemeral=True,
        )


class AdminQuitarModal(discord.ui.Modal, title="Quitar jugador"):
    jugador = discord.ui.TextInput(label="Jugador", max_length=60)

    async def on_submit(self, interaction: discord.Interaction):
        if not es_admin(interaction):
            await interaction.response.send_message("⛔ Solo admins.", ephemeral=True)
            return
        ficha = jugador_por_nombre(self.jugador.value)
        if not ficha:
            await interaction.response.send_message("⚠️ Jugador no encontrado.", ephemeral=True)
            return
        if operacion_abierta_del_jugador(ficha["name"]):
            await interaction.response.send_message("⚠️ Ese jugador tiene una operación pendiente. Resolvela antes de quitarlo.", ephemeral=True)
            return
        with db() as conn:
            conn.execute("DELETE FROM roster_players WHERE id = ?", (ficha["id"],))
            conn.execute("UPDATE publications SET active = 0 WHERE player = ? COLLATE NOCASE AND active = 1", (ficha["name"],))
            conn.execute("UPDATE offers SET status = 'CANCELADA' WHERE player = ? COLLATE NOCASE AND status = 'PENDIENTE'", (ficha["name"],))
        await interaction.response.send_message(f"🗑️ **{ficha['name']}** eliminado de los planteles.", ephemeral=True)


class AdminPlantelModal(discord.ui.Modal, title="Consultar plantel"):
    club = discord.ui.TextInput(label="Club", max_length=60)

    async def on_submit(self, interaction: discord.Interaction):
        if not es_admin(interaction):
            await interaction.response.send_message("⛔ Solo admins.", ephemeral=True)
            return
        await interaction.response.send_message(embed=plantel_embed(self.club.value.strip()), ephemeral=True)


class AdminTemporadaModal(discord.ui.Modal, title="Cambiar temporada activa"):
    nombre = discord.ui.TextInput(label="Nombre", placeholder="Ej: Temporada 2", max_length=60)

    async def on_submit(self, interaction: discord.Interaction):
        if not es_admin(interaction):
            await interaction.response.send_message("⛔ Solo admins.", ephemeral=True)
            return
        season = cambiar_temporada(self.nombre.value)
        await interaction.response.send_message(f"🗓️ Temporada activa: **{season['name']}**.", ephemeral=True)


class OperacionAdminView(discord.ui.View):
    def __init__(self, operacion_id: int):
        super().__init__(timeout=180)
        self.operacion_id = operacion_id

    @discord.ui.button(label="Aprobar", emoji="✅", style=discord.ButtonStyle.success)
    async def aprobar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not es_admin(interaction):
            await interaction.response.send_message("⛔ Solo admins.", ephemeral=True)
            return
        op = operacion_por_id(self.operacion_id)
        if not op or op["status"] != "PENDIENTE_ADMIN":
            await interaction.response.send_message("⚠️ La operación ya no está pendiente de aprobación.", ephemeral=True)
            return
        ficha = jugador_por_nombre(op["player"])
        if not ficha or ficha["club"].casefold() != op["seller"].casefold():
            await interaction.response.send_message(
                "⚠️ El plantel actual no coincide con el club vendedor. Revisá el caso antes de aprobar.", ephemeral=True
            )
            return
        with db() as conn:
            conn.execute(
                "UPDATE transfers SET status = 'APROBADA', approved_by = ?, approved_at = CURRENT_TIMESTAMP WHERE id = ?",
                (interaction.user.id, op["id"]),
            )
        await interaction.response.edit_message(
            embed=discord.Embed(
                title="✅ Operación aprobada",
                description=(
                    f"Operación **#{op['id']}** aprobada.\n"
                    f"**{op['player']}** todavía figura en **{op['seller']}** hasta que ustedes hagan el cambio en PES y presionen **Aplicado en PES**."
                ),
            ),
            view=OperacionAdminView(op["id"]),
        )

    @discord.ui.button(label="Aplicado en PES", emoji="🎮", style=discord.ButtonStyle.primary)
    async def aplicar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not es_admin(interaction):
            await interaction.response.send_message("⛔ Solo admins.", ephemeral=True)
            return
        op = operacion_por_id(self.operacion_id)
        if not op or op["status"] != "APROBADA":
            await interaction.response.send_message("⚠️ Primero la operación debe estar APROBADA.", ephemeral=True)
            return
        ficha = jugador_por_nombre(op["player"])
        if not ficha:
            await interaction.response.send_message("⚠️ Jugador no encontrado en el plantel oficial.", ephemeral=True)
            return
        if ficha["club"].casefold() != op["seller"].casefold():
            await interaction.response.send_message(
                f"⚠️ El jugador figura actualmente en **{ficha['club']}**, no en **{op['seller']}**. No se aplicó nada.", ephemeral=True
            )
            return
        with db() as conn:
            conn.execute(
                "UPDATE roster_players SET club = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (op["buyer"], ficha["id"]),
            )
            conn.execute(
                "UPDATE transfers SET status = 'APLICADA', applied_by = ?, applied_at = CURRENT_TIMESTAMP WHERE id = ?",
                (interaction.user.id, op["id"]),
            )
            conn.execute(
                """
                INSERT INTO player_history (player_id, player, from_club, to_club, transfer_id, season_id, event_type)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (ficha["id"], ficha["name"], op["seller"], op["buyer"], op["id"], op["season_id"], op["operation_type"]),
            )
        await interaction.response.edit_message(
            embed=discord.Embed(
                title="🎮 Operación aplicada al juego",
                description=(
                    f"`{player_code(ficha['id'])}` • **{ficha['name']}**\n"
                    f"**{op['seller']}** ➜ **{op['buyer']}**\n\n"
                    "El plantel oficial del bot quedó actualizado y el movimiento fue agregado al historial."
                ),
            ),
            view=None,
        )

    @discord.ui.button(label="Rechazar admin", emoji="⛔", style=discord.ButtonStyle.danger)
    async def rechazar_admin(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not es_admin(interaction):
            await interaction.response.send_message("⛔ Solo admins.", ephemeral=True)
            return
        op = operacion_por_id(self.operacion_id)
        if not op or op["status"] not in ("PENDIENTE_ADMIN", "APROBADA"):
            await interaction.response.send_message("⚠️ Esa operación ya no puede rechazarse.", ephemeral=True)
            return
        with db() as conn:
            conn.execute(
                "UPDATE transfers SET status = 'RECHAZADA_ADMIN', rejected_by = ?, rejected_at = CURRENT_TIMESTAMP WHERE id = ?",
                (interaction.user.id, op["id"]),
            )
            if op["offer_id"]:
                conn.execute("UPDATE offers SET status = 'CANCELADA_ADMIN' WHERE id = ?", (op["offer_id"],))
        await interaction.response.edit_message(
            embed=discord.Embed(title="⛔ Operación rechazada por administración", description=f"Operación **#{op['id']}** cancelada. El plantel no fue modificado."),
            view=None,
        )


class OperacionesSelect(discord.ui.Select):
    def __init__(self, operaciones):
        options = [
            discord.SelectOption(
                label=f"#{o['id']} • {o['player']}"[:100],
                description=(("APROBAR • " if o["status"] == "PENDIENTE_ADMIN" else "APLICAR EN PES • ") + f"{o['seller']} > {o['buyer']}")[:100],
                value=str(o["id"]),
            )
            for o in operaciones[:25]
        ]
        super().__init__(placeholder="Elegí una operación", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        if not es_admin(interaction):
            await interaction.response.send_message("⛔ Solo admins.", ephemeral=True)
            return
        op = operacion_por_id(int(self.values[0]))
        if not op:
            await interaction.response.send_message("Operación no encontrada.", ephemeral=True)
            return
        ficha = jugador_por_nombre(op["player"])
        codigo = player_code(ficha["id"]) if ficha else "SIN-ID"
        embed = discord.Embed(title=f"🛠️ Operación #{op['id']} • {op['player']}")
        embed.add_field(name="ID jugador", value=f"`{codigo}`", inline=True)
        embed.add_field(name="Tipo", value=op["operation_type"], inline=True)
        embed.add_field(name="Estado", value=op["status"], inline=True)
        embed.add_field(name="Movimiento", value=f"{op['seller']} ➜ **{op['buyer']}**", inline=False)
        embed.add_field(name="Monto", value=op["amount"], inline=True)
        embed.add_field(name="Condiciones", value=op["notes"] or "Sin condiciones", inline=False)
        await interaction.response.send_message(embed=embed, view=OperacionAdminView(op["id"]), ephemeral=True)


class OperacionesAdminListView(discord.ui.View):
    def __init__(self, operaciones):
        super().__init__(timeout=180)
        if operaciones:
            self.add_item(OperacionesSelect(operaciones))


class AdminView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=180)

    @discord.ui.button(label="Abrir mercado", emoji="🟢", style=discord.ButtonStyle.success, row=0)
    async def abrir(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not es_admin(interaction):
            await interaction.response.send_message("⛔ Solo admins.", ephemeral=True)
            return
        cambiar_estado_mercado(True, interaction.user.id)
        await interaction.response.send_message("🟢 Mercado abierto.", ephemeral=True)

    @discord.ui.button(label="Cerrar mercado", emoji="🔒", style=discord.ButtonStyle.danger, row=0)
    async def cerrar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not es_admin(interaction):
            await interaction.response.send_message("⛔ Solo admins.", ephemeral=True)
            return
        cambiar_estado_mercado(False, interaction.user.id)
        await interaction.response.send_message("🔒 Mercado cerrado. Las ofertas quedan congeladas.", ephemeral=True)

    @discord.ui.button(label="Operaciones pendientes", emoji="🛠️", style=discord.ButtonStyle.primary, row=0)
    async def ops(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not es_admin(interaction):
            await interaction.response.send_message("⛔ Solo admins.", ephemeral=True)
            return
        ops = operaciones_pendientes(25)
        await interaction.response.send_message(
            embed=operaciones_pendientes_embed(), view=OperacionesAdminListView(ops), ephemeral=True
        )

    @discord.ui.button(label="Agregar jugador", emoji="➕", style=discord.ButtonStyle.primary, row=1)
    async def agregar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not es_admin(interaction):
            await interaction.response.send_message("⛔ Solo admins.", ephemeral=True)
            return
        await interaction.response.send_modal(AdminAgregarModal())

    @discord.ui.button(label="Mover manual", emoji="🔁", style=discord.ButtonStyle.primary, row=1)
    async def mover(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not es_admin(interaction):
            await interaction.response.send_message("⛔ Solo admins.", ephemeral=True)
            return
        await interaction.response.send_modal(AdminMoverModal())

    @discord.ui.button(label="Quitar jugador", emoji="🗑️", style=discord.ButtonStyle.secondary, row=1)
    async def quitar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not es_admin(interaction):
            await interaction.response.send_message("⛔ Solo admins.", ephemeral=True)
            return
        await interaction.response.send_modal(AdminQuitarModal())

    @discord.ui.button(label="Ver plantel", emoji="📋", style=discord.ButtonStyle.secondary, row=2)
    async def ver_plantel(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not es_admin(interaction):
            await interaction.response.send_message("⛔ Solo admins.", ephemeral=True)
            return
        await interaction.response.send_modal(AdminPlantelModal())

    @discord.ui.button(label="Cambiar temporada", emoji="🗓️", style=discord.ButtonStyle.secondary, row=2)
    async def temporada(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not es_admin(interaction):
            await interaction.response.send_message("⛔ Solo admins.", ephemeral=True)
            return
        await interaction.response.send_modal(AdminTemporadaModal())


class MercadoView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Mi club", emoji="🏟️", style=discord.ButtonStyle.primary, custom_id="mercado_mi_club", row=0)
    async def mi_club(self, interaction: discord.Interaction, button: discord.ui.Button):
        club = club_de(interaction.user.id)
        if not club:
            await interaction.response.send_modal(RegistrarClubModal())
            return
        await interaction.response.send_message(embed=plantel_embed(club), view=ClubView(), ephemeral=True)

    @discord.ui.button(label="Publicar", emoji="📤", style=discord.ButtonStyle.success, custom_id="mercado_publicar", row=0)
    async def publicar(self, interaction: discord.Interaction, button: discord.ui.Button):
        club = club_de(interaction.user.id)
        if not club:
            await interaction.response.send_modal(RegistrarClubModal())
            return
        jugadores = [
            j for j in jugadores_de_club(club, 50)
            if not publicacion_activa_del_jugador(j["name"]) and not operacion_abierta_del_jugador(j["name"])
        ]
        if not jugadores:
            await interaction.response.send_message(
                "⚠️ No tenés jugadores disponibles para publicar. Puede que el plantel esté vacío, ya estén publicados o tengan una operación pendiente.",
                ephemeral=True,
            )
            return
        await interaction.response.send_message("📤 Elegí el jugador que querés publicar:", view=PublicarView(jugadores[:25]), ephemeral=True)

    @discord.ui.button(label="Buscar", emoji="🔎", style=discord.ButtonStyle.primary, custom_id="mercado_buscar", row=0)
    async def buscar(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(BuscarJugadoresModal())

    @discord.ui.button(label="Transferibles", emoji="📋", style=discord.ButtonStyle.secondary, custom_id="mercado_transferibles", row=0)
    async def transferibles(self, interaction: discord.Interaction, button: discord.ui.Button):
        pubs = publicaciones_activas(25)
        await interaction.response.send_message(embed=publicaciones_embed(pubs), view=TransferiblesView(pubs), ephemeral=True)

    @discord.ui.button(label="Mis ofertas", emoji="💰", style=discord.ButtonStyle.danger, custom_id="mercado_ofertas", row=0)
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

        embed = discord.Embed(title="💰 Mis ofertas")
        if not propias:
            embed.description = "Todavía no tenés ofertas enviadas ni recibidas."
        else:
            for oferta in propias:
                enviada = oferta["from_id"] == interaction.user.id
                tipo = "📤 Enviada" if enviada else "📥 Recibida"
                icono = {
                    "PENDIENTE": "🟡", "ACEPTADA": "🟢", "RECHAZADA": "🔴",
                    "CANCELADA": "⚫", "CANCELADA_ADMIN": "⛔",
                }.get(oferta["status"], "⚪")
                embed.add_field(
                    name=f"{tipo} • #{oferta['id']} • {oferta['player']}",
                    value=f"🔁 {oferta['operation_type']} • 💵 **{oferta['amount']}**\n{icono} {oferta['status']}",
                    inline=False,
                )
        await interaction.response.send_message(embed=embed, view=OfertasView(pendientes), ephemeral=True)

    @discord.ui.button(label="Transferencias", emoji="🤝", style=discord.ButtonStyle.secondary, custom_id="mercado_transferencias", row=1)
    async def transferencias(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(embed=transferencias_embed(), ephemeral=True)

    @discord.ui.button(label="Administración", emoji="⚙️", style=discord.ButtonStyle.secondary, custom_id="mercado_admin", row=1)
    async def administracion(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not es_admin(interaction):
            await interaction.response.send_message("⛔ Este menú es solo para administradores.", ephemeral=True)
            return
        temporada = temporada_activa()
        embed = discord.Embed(
            title="⚙️ Administración",
            description=(
                "Gestioná el mercado, planteles y la cola de operaciones que después se aplican en PES.\n\n"
                f"🗓️ Temporada: **{temporada['name'] if temporada else 'Sin temporada'}**"
            ),
        )
        await interaction.response.send_message(embed=embed, view=AdminView(), ephemeral=True)


@bot.tree.command(name="mercado", description="Abre el panel principal de AJAP Transfer Market")
async def mercado(interaction: discord.Interaction):
    await interaction.response.send_message(embed=panel_embed(interaction.user.id), view=MercadoView())


@bot.tree.command(name="operaciones_pendientes", description="Lista operaciones por aprobar o aplicar en PES")
async def operaciones_pendientes_cmd(interaction: discord.Interaction):
    if not es_admin(interaction):
        await interaction.response.send_message("⛔ Solo administradores.", ephemeral=True)
        return
    ops = operaciones_pendientes(25)
    await interaction.response.send_message(
        embed=operaciones_pendientes_embed(), view=OperacionesAdminListView(ops), ephemeral=True
    )


@bot.tree.command(name="historial_jugador", description="Muestra el historial de movimientos de un jugador")
async def historial_jugador_cmd(interaction: discord.Interaction, jugador: str):
    await interaction.response.send_message(embed=historial_embed(jugador), ephemeral=True)


@bot.tree.command(name="exportar_mercado", description="Exporta operaciones de la temporada a CSV para editar PES")
async def exportar_mercado_cmd(interaction: discord.Interaction):
    if not es_admin(interaction):
        await interaction.response.send_message("⛔ Solo administradores.", ephemeral=True)
        return
    season = temporada_activa()
    if not season:
        await interaction.response.send_message("⚠️ No hay temporada activa.", ephemeral=True)
        return
    with db() as conn:
        rows = conn.execute(
            """
            SELECT * FROM transfers
            WHERE season_id = ?
            ORDER BY id ASC
            """,
            (season["id"],),
        ).fetchall()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "operacion_id", "temporada", "jugador_id", "jugador", "tipo", "club_origen",
        "club_destino", "monto", "estado", "aprobada_en", "aplicada_en", "notas"
    ])
    for row in rows:
        writer.writerow([
            row["id"], season["name"], player_code(row["player_id"]) if row["player_id"] else "",
            row["player"], row["operation_type"], row["seller"], row["buyer"], row["amount"],
            row["status"], row["approved_at"] or "", row["applied_at"] or "", row["notes"] or "",
        ])

    data = output.getvalue().encode("utf-8-sig")
    safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in season["name"])
    file = discord.File(io.BytesIO(data), filename=f"AJAP_mercado_{safe_name}.csv")
    await interaction.response.send_message(
        content=f"📤 Exportación de **{season['name']}** • {len(rows)} operación(es).",
        file=file,
        ephemeral=True,
    )


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
    season = temporada_activa()
    print(f"Temporada activa: {season['name'] if season else 'Ninguna'}")


init_db()
bot.run(TOKEN)
