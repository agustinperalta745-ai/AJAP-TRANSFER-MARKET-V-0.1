import discord

import market_close_report_patch as close_report

APP = None
DEFAULT_CLAUSE_PRICE = 50_000_000
STAFF_ROLE_NAMES = {"staff"}


def fmt_money(value):
    return f"${int(value):,}".replace(",", ".")


def ensure_schema():
    with APP.db() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS market_config (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                clause_price INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS club_finances (
                club TEXT PRIMARY KEY COLLATE NOCASE,
                balance INTEGER NOT NULL DEFAULT 0,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS clause_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cycle_id INTEGER NOT NULL,
                season_id INTEGER,
                player_id INTEGER NOT NULL,
                player TEXT NOT NULL,
                seller_club TEXT NOT NULL,
                seller_user_id INTEGER,
                buyer_club TEXT NOT NULL,
                buyer_user_id INTEGER NOT NULL,
                buyer_username TEXT NOT NULL,
                amount INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'PENDIENTE_STAFF',
                transfer_id INTEGER,
                requested_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                decided_by INTEGER,
                decided_at DATETIME,
                notes TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_clause_cycle_player
                ON clause_requests (cycle_id, player_id);
            CREATE INDEX IF NOT EXISTS idx_clause_status
                ON clause_requests (status);
            """
        )
        conn.execute(
            "INSERT OR IGNORE INTO market_config (id, clause_price) VALUES (1, ?)",
            (DEFAULT_CLAUSE_PRICE,),
        )
        clubs = conn.execute("SELECT DISTINCT club FROM roster_players ORDER BY club").fetchall()
        for row in clubs:
            conn.execute(
                "INSERT OR IGNORE INTO club_finances (club, balance) VALUES (?, 0)",
                (row["club"],),
            )


def active_cycle():
    with APP.db() as conn:
        return conn.execute(
            "SELECT * FROM market_cycles WHERE closed_at IS NULL ORDER BY id DESC LIMIT 1"
        ).fetchone()


def clause_price():
    with APP.db() as conn:
        row = conn.execute("SELECT clause_price FROM market_config WHERE id = 1").fetchone()
    return int(row["clause_price"]) if row else DEFAULT_CLAUSE_PRICE


def set_clause_price(value):
    with APP.db() as conn:
        conn.execute(
            "INSERT INTO market_config (id, clause_price) VALUES (1, ?) "
            "ON CONFLICT(id) DO UPDATE SET clause_price = excluded.clause_price",
            (int(value),),
        )


def club_balance(club):
    with APP.db() as conn:
        conn.execute("INSERT OR IGNORE INTO club_finances (club, balance) VALUES (?, 0)", (club,))
        row = conn.execute(
            "SELECT balance FROM club_finances WHERE club = ? COLLATE NOCASE", (club,)
        ).fetchone()
    return int(row["balance"]) if row else 0


def set_club_balance(club, amount):
    with APP.db() as conn:
        conn.execute(
            """
            INSERT INTO club_finances (club, balance, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(club) DO UPDATE SET
                balance = excluded.balance,
                updated_at = CURRENT_TIMESTAMP
            """,
            (club.strip(), int(amount)),
        )


def owner_id_for_club(club):
    with APP.db() as conn:
        row = conn.execute(
            "SELECT user_id FROM clubs WHERE name = ? COLLATE NOCASE LIMIT 1", (club,)
        ).fetchone()
    return int(row["user_id"]) if row else None


def is_staff_member(member):
    return isinstance(member, discord.Member) and any(
        (role.name or "").strip().casefold() in STAFF_ROLE_NAMES for role in member.roles
    )


def is_staff_or_admin(interaction):
    return APP.es_admin(interaction) or is_staff_member(interaction.user)


def staff_members(guild):
    found = {}
    if not guild:
        return []
    for role in guild.roles:
        if (role.name or "").strip().casefold() in STAFF_ROLE_NAMES:
            for member in role.members:
                if not member.bot:
                    found[member.id] = member
    return list(found.values())


def player_rating(row):
    if "rating" in row.keys() and row["rating"] is not None:
        return int(row["rating"])
    return None


def all_roster_clubs():
    with APP.db() as conn:
        return [
            row["club"]
            for row in conn.execute(
                "SELECT DISTINCT club FROM roster_players ORDER BY club COLLATE NOCASE"
            ).fetchall()
        ]


def players_for_club(club):
    with APP.db() as conn:
        return conn.execute(
            "SELECT * FROM roster_players WHERE club = ? COLLATE NOCASE ORDER BY name COLLATE NOCASE",
            (club,),
        ).fetchall()


def search_players(term):
    needle = f"%{term.strip()}%"
    with APP.db() as conn:
        return conn.execute(
            """
            SELECT * FROM roster_players
            WHERE name LIKE ? COLLATE NOCASE
            ORDER BY name COLLATE NOCASE
            LIMIT 50
            """,
            (needle,),
        ).fetchall()


def clause_state(player_id, cycle_id):
    with APP.db() as conn:
        return conn.execute(
            """
            SELECT * FROM clause_requests
            WHERE cycle_id = ? AND player_id = ?
              AND status IN ('PENDIENTE_STAFF', 'APROBADO')
            ORDER BY id DESC LIMIT 1
            """,
            (cycle_id, player_id),
        ).fetchone()


def pending_clauses(limit=25):
    with APP.db() as conn:
        return conn.execute(
            """
            SELECT * FROM clause_requests
            WHERE status = 'PENDIENTE_STAFF'
            ORDER BY id ASC LIMIT ?
            """,
            (limit,),
        ).fetchall()


def request_by_id(request_id):
    with APP.db() as conn:
        return conn.execute(
            "SELECT * FROM clause_requests WHERE id = ?", (request_id,)
        ).fetchone()


def home_embed(user_id):
    club = APP.club_de(user_id)
    price = clause_price()
    balance = club_balance(club) if club else 0
    embed = discord.Embed(
        title="💥 Clausulazo",
        description=(
            "Podés ejecutar la cláusula de **cualquier jugador de otro equipo**, aunque no esté publicado.\n\n"
            "La operación **no necesita aceptación del club propietario**, pero sí aprobación del **Staff**."
        ),
    )
    embed.add_field(name="💰 Cláusula universal", value=fmt_money(price), inline=True)
    embed.add_field(name="🏦 Tu saldo", value=fmt_money(balance), inline=True)
    embed.add_field(name="🔁 Por jugador", value="Máximo 1 clausulazo por mercado", inline=False)
    embed.add_field(
        name="🔒 Protección",
        value="Si un jugador ya fue clausulado en esta ventana, nadie puede volver a clausularlo hasta el próximo mercado.",
        inline=False,
    )
    embed.set_footer(text="El importe queda reservado mientras Staff revisa la solicitud")
    return embed


def request_embed(req):
    ficha = APP.jugador_por_id(req["player_id"])
    rating = player_rating(ficha) if ficha else None
    embed = discord.Embed(title=f"💥 Clausulazo #{req['id']} • {req['player']}")
    embed.add_field(name="Jugador", value=req["player"], inline=True)
    embed.add_field(name="OVR", value=str(rating) if rating is not None else "—", inline=True)
    embed.add_field(name="Monto", value=fmt_money(req["amount"]), inline=True)
    embed.add_field(name="Movimiento", value=f"{req['seller_club']} ➜ **{req['buyer_club']}**", inline=False)
    embed.add_field(name="Solicitado por", value=f"{req['buyer_username']} • <@{req['buyer_user_id']}>", inline=False)
    embed.add_field(name="Estado", value=req["status"], inline=True)
    embed.set_footer(text=f"Mercado #{req['cycle_id']} • No requiere aceptación del vendedor")
    return embed


async def notify_staff(guild, req):
    delivered = 0
    for member in staff_members(guild):
        try:
            await member.send(
                embed=discord.Embed(
                    title="💥 Nuevo clausulazo • Revisión Staff",
                    description=(
                        f"**{req['buyer_username']}** ({req['buyer_club']}) quiere ejecutar la cláusula de "
                        f"**{req['player']}** ({req['seller_club']}) por **{fmt_money(req['amount'])}**.\n\n"
                        "Revisalo con **/clausulazos_pendientes**."
                    ),
                )
            )
            delivered += 1
        except Exception:
            pass
    return delivered


async def notify_seller(guild, req):
    if not req["seller_user_id"]:
        return False
    member = guild.get_member(req["seller_user_id"]) if guild else None
    if member is None and guild:
        try:
            member = await guild.fetch_member(req["seller_user_id"])
        except Exception:
            member = None
    if not member:
        return False
    try:
        await member.send(
            embed=discord.Embed(
                title="💥 CLAUSULAZO",
                description=(
                    f"**{req['buyer_username']}**, del **{req['buyer_club']}**, ha pagado la cláusula de "
                    f"**{req['player']}** por **{fmt_money(req['amount'])}**.\n\n"
                    f"El Staff aprobó la operación y **{req['player']} se marcha de {req['seller_club']}**."
                ),
            ).add_field(
                name="💰 Compensación recibida",
                value=fmt_money(req["amount"]),
                inline=False,
            ).set_footer(text="El movimiento queda registrado para la actualización oficial de PES")
        )
        return True
    except Exception:
        return False


async def notify_buyer(guild, req, approved):
    member = guild.get_member(req["buyer_user_id"]) if guild else None
    if member is None and guild:
        try:
            member = await guild.fetch_member(req["buyer_user_id"])
        except Exception:
            member = None
    if not member:
        return False
    try:
        if approved:
            embed = discord.Embed(
                title="✅ Clausulazo aprobado",
                description=(
                    f"El Staff aprobó el clausulazo de **{req['player']}**.\n"
                    f"**{req['seller_club']} ➜ {req['buyer_club']}** por **{fmt_money(req['amount'])}**."
                ),
            )
        else:
            embed = discord.Embed(
                title="❌ Clausulazo rechazado",
                description=(
                    f"El Staff rechazó la solicitud por **{req['player']}**.\n"
                    f"Los **{fmt_money(req['amount'])}** reservados volvieron al saldo de **{req['buyer_club']}**."
                ),
            )
        await member.send(embed=embed)
        return True
    except Exception:
        return False


def create_clause_request(interaction, ficha):
    if not APP.mercado_abierto():
        return False, "🔒 El mercado está cerrado."
    cycle = active_cycle()
    if not cycle:
        return False, "⚠️ No hay una ventana de mercado activa registrada."
    buyer_club = APP.club_de(interaction.user.id)
    if not buyer_club:
        return False, "⚠️ Primero tenés que tener un equipo asignado."
    if ficha["club"].casefold() == buyer_club.casefold():
        return False, "⚠️ No podés ejecutar la cláusula de un jugador de tu propio club."
    if APP.operacion_abierta_del_jugador(ficha["name"]):
        return False, "⚠️ Ese jugador ya tiene una operación aceptada pendiente de administración."

    amount = clause_price()
    conn = APP.db()
    try:
        conn.execute("BEGIN IMMEDIATE")
        current = conn.execute(
            "SELECT * FROM roster_players WHERE id = ?", (ficha["id"],)
        ).fetchone()
        if not current or current["club"].casefold() == buyer_club.casefold():
            conn.rollback()
            return False, "⚠️ La situación del jugador cambió. Volvé a buscarlo."
        locked = conn.execute(
            """
            SELECT id, status FROM clause_requests
            WHERE cycle_id = ? AND player_id = ?
              AND status IN ('PENDIENTE_STAFF', 'APROBADO')
            LIMIT 1
            """,
            (cycle["id"], current["id"]),
        ).fetchone()
        if locked:
            conn.rollback()
            if locked["status"] == "APROBADO":
                return False, "🔒 Este jugador ya fue clausulado en este mercado. Se reactiva en el próximo."
            return False, "⏳ Ya existe un clausulazo pendiente de revisión para este jugador."

        conn.execute(
            "INSERT OR IGNORE INTO club_finances (club, balance) VALUES (?, 0)",
            (buyer_club,),
        )
        account = conn.execute(
            "SELECT balance FROM club_finances WHERE club = ? COLLATE NOCASE", (buyer_club,)
        ).fetchone()
        balance = int(account["balance"])
        if balance < amount:
            conn.rollback()
            return False, f"⛔ Saldo insuficiente. Necesitás **{fmt_money(amount)}** y tenés **{fmt_money(balance)}**."

        seller_user_id = owner_id_for_club(current["club"])
        season = APP.temporada_activa()
        conn.execute(
            "UPDATE club_finances SET balance = balance - ?, updated_at = CURRENT_TIMESTAMP WHERE club = ? COLLATE NOCASE",
            (amount, buyer_club),
        )
        cur = conn.execute(
            """
            INSERT INTO clause_requests
            (cycle_id, season_id, player_id, player, seller_club, seller_user_id,
             buyer_club, buyer_user_id, buyer_username, amount)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                cycle["id"], season["id"] if season else None, current["id"], current["name"],
                current["club"], seller_user_id, buyer_club, interaction.user.id,
                interaction.user.display_name, amount,
            ),
        )
        request_id = cur.lastrowid
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
    return True, request_by_id(request_id)


def reject_request(req, staff_id, reason="Rechazado por Staff"):
    conn = APP.db()
    try:
        conn.execute("BEGIN IMMEDIATE")
        fresh = conn.execute("SELECT * FROM clause_requests WHERE id = ?", (req["id"],)).fetchone()
        if not fresh or fresh["status"] != "PENDIENTE_STAFF":
            conn.rollback()
            return False
        conn.execute(
            "INSERT OR IGNORE INTO club_finances (club, balance) VALUES (?, 0)",
            (fresh["buyer_club"],),
        )
        conn.execute(
            "UPDATE club_finances SET balance = balance + ?, updated_at = CURRENT_TIMESTAMP WHERE club = ? COLLATE NOCASE",
            (fresh["amount"], fresh["buyer_club"]),
        )
        conn.execute(
            """
            UPDATE clause_requests
            SET status = 'RECHAZADO_STAFF', decided_by = ?, decided_at = CURRENT_TIMESTAMP, notes = ?
            WHERE id = ?
            """,
            (staff_id, reason, fresh["id"]),
        )
        conn.commit()
        return True
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def approve_request(req, staff_id):
    conn = APP.db()
    try:
        conn.execute("BEGIN IMMEDIATE")
        fresh = conn.execute("SELECT * FROM clause_requests WHERE id = ?", (req["id"],)).fetchone()
        if not fresh or fresh["status"] != "PENDIENTE_STAFF":
            conn.rollback()
            return False, "La solicitud ya fue resuelta."
        player = conn.execute(
            "SELECT * FROM roster_players WHERE id = ?", (fresh["player_id"],)
        ).fetchone()
        if not player or player["club"].casefold() != fresh["seller_club"].casefold():
            conn.rollback()
            reject_request(fresh, staff_id, "El jugador cambió de club antes de la aprobación")
            return False, "El jugador cambió de club. La solicitud fue rechazada y el dinero devuelto."
        already = conn.execute(
            """
            SELECT id FROM clause_requests
            WHERE cycle_id = ? AND player_id = ? AND status = 'APROBADO' AND id != ? LIMIT 1
            """,
            (fresh["cycle_id"], fresh["player_id"], fresh["id"]),
        ).fetchone()
        if already:
            conn.rollback()
            reject_request(fresh, staff_id, "El jugador ya recibió un clausulazo en este mercado")
            return False, "Ese jugador ya fue clausulado en esta ventana. Se devolvió el dinero."

        conn.execute(
            "INSERT OR IGNORE INTO club_finances (club, balance) VALUES (?, 0)",
            (fresh["seller_club"],),
        )
        conn.execute(
            "UPDATE club_finances SET balance = balance + ?, updated_at = CURRENT_TIMESTAMP WHERE club = ? COLLATE NOCASE",
            (fresh["amount"], fresh["seller_club"]),
        )
        conn.execute(
            "UPDATE publications SET active = 0 WHERE player = ? COLLATE NOCASE AND active = 1",
            (fresh["player"],),
        )
        conn.execute(
            "UPDATE offers SET status = 'CANCELADA' WHERE player = ? COLLATE NOCASE AND status = 'PENDIENTE'",
            (fresh["player"],),
        )
        notes = (
            f"CLAUSULAZO aprobado por Staff. Cláusula universal {fmt_money(fresh['amount'])}. "
            f"Solicitado por {fresh['buyer_username']} ({fresh['buyer_club']}). Sin negociación."
        )
        cur = conn.execute(
            """
            INSERT INTO transfers
            (player, seller, buyer, amount, offer_id, player_id, operation_type,
             season_id, status, approved_by, approved_at, notes)
            VALUES (?, ?, ?, ?, 0, ?, 'CLAUSULAZO', ?, 'APROBADA', ?, CURRENT_TIMESTAMP, ?)
            """,
            (
                fresh["player"], fresh["seller_club"], fresh["buyer_club"],
                APP.money(str(fresh["amount"])), fresh["player_id"], fresh["season_id"], staff_id, notes,
            ),
        )
        transfer_id = cur.lastrowid
        conn.execute(
            """
            UPDATE clause_requests
            SET status = 'APROBADO', transfer_id = ?, decided_by = ?, decided_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (transfer_id, staff_id, fresh["id"]),
        )
        conn.commit()
        return True, transfer_id
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


class ClauseConfirmView(discord.ui.View):
    def __init__(self, player_id):
        super().__init__(timeout=180)
        self.player_id = int(player_id)

    @discord.ui.button(label="Pagar cláusula", emoji="💥", style=discord.ButtonStyle.danger)
    async def pay(self, interaction, button):
        ficha = APP.jugador_por_id(self.player_id)
        if not ficha:
            await interaction.response.send_message("⚠️ Jugador no encontrado.", ephemeral=True)
            return
        ok, result = create_clause_request(interaction, ficha)
        if not ok:
            await interaction.response.send_message(result, ephemeral=True)
            return
        req = result
        delivered = await notify_staff(interaction.guild, req)
        embed = request_embed(req)
        embed.description = (
            f"✅ **{fmt_money(req['amount'])}** quedaron reservados.\n"
            "La operación todavía **no está aprobada** y el vendedor todavía no fue notificado."
        )
        embed.add_field(name="Staff avisado", value=str(delivered), inline=True)
        embed.add_field(name="Saldo restante", value=fmt_money(club_balance(req["buyer_club"])), inline=True)
        await interaction.response.edit_message(embed=embed, view=None)


class ClausePlayerSelect(discord.ui.Select):
    def __init__(self, players, row=0):
        cycle = active_cycle()
        options = []
        for player in players[:25]:
            state = clause_state(player["id"], cycle["id"]) if cycle else None
            rating = player_rating(player)
            status = ""
            if state:
                status = " • 🔒 Clausulado" if state["status"] == "APROBADO" else " • ⏳ Pendiente Staff"
            desc = f"{player['club']} • {player['position']}"
            if rating is not None:
                desc += f" • OVR {rating}"
            desc += status
            options.append(discord.SelectOption(label=player["name"][:100], description=desc[:100], value=str(player["id"])))
        super().__init__(placeholder="Elegí un jugador", min_values=1, max_values=1, options=options, row=row)

    async def callback(self, interaction):
        ficha = APP.jugador_por_id(int(self.values[0]))
        if not ficha:
            await interaction.response.send_message("⚠️ Jugador no encontrado.", ephemeral=True)
            return
        buyer = APP.club_de(interaction.user.id)
        if not buyer:
            await interaction.response.send_message("⚠️ Primero elegí un equipo.", ephemeral=True)
            return
        if ficha["club"].casefold() == buyer.casefold():
            await interaction.response.send_message("⚠️ Ese jugador ya es de tu club.", ephemeral=True)
            return
        cycle = active_cycle()
        if cycle:
            state = clause_state(ficha["id"], cycle["id"])
            if state:
                msg = "🔒 Este jugador ya fue clausulado en este mercado. Se reactiva en el próximo." if state["status"] == "APROBADO" else "⏳ Ya tiene un clausulazo pendiente de Staff."
                await interaction.response.send_message(msg, ephemeral=True)
                return
        rating = player_rating(ficha)
        embed = discord.Embed(title=f"💥 Ejecutar cláusula • {ficha['name']}")
        embed.add_field(name="Club actual", value=ficha["club"], inline=True)
        embed.add_field(name="Posición", value=ficha["position"], inline=True)
        embed.add_field(name="OVR", value=str(rating) if rating is not None else "—", inline=True)
        embed.add_field(name="Cláusula universal", value=fmt_money(clause_price()), inline=False)
        embed.add_field(name="Tu saldo", value=fmt_money(club_balance(buyer)), inline=True)
        embed.description = "No necesita aceptación del propietario. **Staff debe aprobarla antes de que sea efectiva.**"
        await interaction.response.send_message(embed=embed, view=ClauseConfirmView(ficha["id"]), ephemeral=True)


class ClausePlayersView(discord.ui.View):
    def __init__(self, players):
        super().__init__(timeout=300)
        groups = [players[i:i + 25] for i in range(0, min(len(players), 50), 25)]
        for i, group in enumerate(groups):
            if group:
                self.add_item(ClausePlayerSelect(group, row=i))


class ClauseSearchModal(discord.ui.Modal, title="Buscar jugador para clausulazo"):
    player = discord.ui.TextInput(label="Nombre del jugador", placeholder="Ej: Ronaldinho", max_length=60)

    async def on_submit(self, interaction):
        rows = search_players(self.player.value)
        buyer = APP.club_de(interaction.user.id)
        rows = [row for row in rows if not buyer or row["club"].casefold() != buyer.casefold()]
        if not rows:
            await interaction.response.send_message("🔎 No encontré jugadores de otros clubes con ese nombre.", ephemeral=True)
            return
        embed = discord.Embed(title=f"🔎 Clausulazo • resultados ({len(rows)})")
        embed.description = "Elegí el jugador cuya cláusula querés ejecutar."
        await interaction.response.send_message(embed=embed, view=ClausePlayersView(rows), ephemeral=True)


class ClauseTeamSelect(discord.ui.Select):
    def __init__(self, buyer_club):
        clubs = [club for club in all_roster_clubs() if club.casefold() != buyer_club.casefold()]
        options = [discord.SelectOption(label=club[:100], value=club) for club in clubs[:25]]
        super().__init__(placeholder="Ver plantilla de otro equipo", min_values=1, max_values=1, options=options)

    async def callback(self, interaction):
        rows = players_for_club(self.values[0])
        embed = discord.Embed(title=f"💥 Clausulazo • {self.values[0]}")
        embed.description = "Elegí cualquier jugador. No hace falta que esté publicado."
        await interaction.response.edit_message(embed=embed, view=ClausePlayersView(rows))


class ClauseHomeView(discord.ui.View):
    def __init__(self, buyer_club):
        super().__init__(timeout=300)
        clubs = [club for club in all_roster_clubs() if club.casefold() != buyer_club.casefold()]
        if clubs:
            self.add_item(ClauseTeamSelect(buyer_club))

    @discord.ui.button(label="Buscar jugador", emoji="🔎", style=discord.ButtonStyle.primary, row=1)
    async def search(self, interaction, button):
        await interaction.response.send_modal(ClauseSearchModal())


class ClauseDecisionView(discord.ui.View):
    def __init__(self, request_id):
        super().__init__(timeout=300)
        self.request_id = int(request_id)

    @discord.ui.button(label="Aprobar clausulazo", emoji="✅", style=discord.ButtonStyle.success)
    async def approve(self, interaction, button):
        if not is_staff_or_admin(interaction):
            await interaction.response.send_message("⛔ Solo Staff/administradores.", ephemeral=True)
            return
        req = request_by_id(self.request_id)
        if not req or req["status"] != "PENDIENTE_STAFF":
            await interaction.response.send_message("⚠️ Esta solicitud ya fue resuelta.", ephemeral=True)
            return
        ok, result = approve_request(req, interaction.user.id)
        if not ok:
            await interaction.response.send_message(f"⚠️ {result}", ephemeral=True)
            return
        fresh = request_by_id(self.request_id)
        await notify_seller(interaction.guild, fresh)
        await notify_buyer(interaction.guild, fresh, True)
        embed = request_embed(fresh)
        embed.description = (
            f"✅ Clausulazo aprobado. Se creó la operación **#{result}** como **APROBADA**.\n"
            "El jugador queda protegido contra nuevos clausulazos hasta el próximo mercado y ahora Staff debe aplicar el movimiento en PES."
        )
        await interaction.response.edit_message(embed=embed, view=None)

    @discord.ui.button(label="Rechazar", emoji="❌", style=discord.ButtonStyle.danger)
    async def reject(self, interaction, button):
        if not is_staff_or_admin(interaction):
            await interaction.response.send_message("⛔ Solo Staff/administradores.", ephemeral=True)
            return
        req = request_by_id(self.request_id)
        if not req or req["status"] != "PENDIENTE_STAFF":
            await interaction.response.send_message("⚠️ Esta solicitud ya fue resuelta.", ephemeral=True)
            return
        reject_request(req, interaction.user.id)
        fresh = request_by_id(self.request_id)
        await notify_buyer(interaction.guild, fresh, False)
        embed = request_embed(fresh)
        embed.description = "❌ Solicitud rechazada. El importe reservado fue devuelto al comprador."
        await interaction.response.edit_message(embed=embed, view=None)


class PendingClauseSelect(discord.ui.Select):
    def __init__(self, rows):
        options = [
            discord.SelectOption(
                label=f"#{row['id']} • {row['player']}"[:100],
                description=f"{row['seller_club']} → {row['buyer_club']} • {fmt_money(row['amount'])}"[:100],
                value=str(row["id"]),
            )
            for row in rows[:25]
        ]
        super().__init__(placeholder="Elegí un clausulazo pendiente", min_values=1, max_values=1, options=options)

    async def callback(self, interaction):
        if not is_staff_or_admin(interaction):
            await interaction.response.send_message("⛔ Solo Staff/administradores.", ephemeral=True)
            return
        req = request_by_id(int(self.values[0]))
        if not req:
            await interaction.response.send_message("⚠️ Solicitud no encontrada.", ephemeral=True)
            return
        await interaction.response.send_message(embed=request_embed(req), view=ClauseDecisionView(req["id"]), ephemeral=True)


class PendingClauseView(discord.ui.View):
    def __init__(self, rows):
        super().__init__(timeout=300)
        if rows:
            self.add_item(PendingClauseSelect(rows))


def pending_embed():
    rows = pending_clauses()
    embed = discord.Embed(title="💥 Clausulazos pendientes • Staff")
    if not rows:
        embed.description = "✅ No hay clausulazos pendientes de revisión."
        return embed
    for row in rows:
        embed.add_field(
            name=f"#{row['id']} • {row['player']}",
            value=f"{row['seller_club']} ➜ **{row['buyer_club']}** • {fmt_money(row['amount'])}",
            inline=False,
        )
    embed.set_footer(text="Resolver todas las solicitudes antes de cerrar el mercado")
    return embed


def patch_close_report_mode():
    original = close_report.deal_mode
    if getattr(original, "_clausulazo_aware", False):
        return

    def deal_mode(runtime, row):
        if (row["operation_type"] or "").strip().upper() == "CLAUSULAZO":
            return "CLAUSULAZO / SIN NEGOCIACIÓN"
        return original(runtime, row)

    deal_mode._clausulazo_aware = True
    close_report.deal_mode = deal_mode


def build_market_view(base_view):
    class ClausulazoMarketView(base_view):
        def __init__(self):
            super().__init__()
            button = discord.ui.Button(
                label="Clausulazo",
                emoji="💥",
                style=discord.ButtonStyle.danger,
                custom_id="mercado_clausulazo",
                row=1,
            )
            button.callback = self._clausulazo
            self.add_item(button)

        async def _clausulazo(self, interaction):
            club = APP.club_de(interaction.user.id)
            if not club:
                await interaction.response.send_message("⚠️ Primero tenés que elegir un equipo.", ephemeral=True)
                return
            if not APP.mercado_abierto():
                await interaction.response.send_message("🔒 El mercado está cerrado. No se pueden ejecutar cláusulas.", ephemeral=True)
                return
            await interaction.response.send_message(embed=home_embed(interaction.user.id), view=ClauseHomeView(club), ephemeral=True)

    ClausulazoMarketView.__name__ = "MercadoView"
    return ClausulazoMarketView


def patch_admin_view(base_view):
    class ClausulazoAdminView(base_view):
        def __init__(self):
            super().__init__()
            for item in self.children:
                if getattr(item, "label", None) == "Cerrar mercado":
                    original_close = item.callback

                    async def guarded_close(interaction, original=original_close):
                        pending = pending_clauses(100)
                        if pending:
                            await interaction.response.send_message(
                                f"⛔ Hay **{len(pending)} clausulazo(s)** pendientes de Staff. Resolvelos antes de cerrar el mercado.",
                                ephemeral=True,
                            )
                            return
                        await original(interaction)

                    item.callback = guarded_close

            button = discord.ui.Button(
                label="Clausulazos",
                emoji="💥",
                style=discord.ButtonStyle.danger,
                row=2,
            )
            button.callback = self._pending_clauses
            self.add_item(button)

        async def _pending_clauses(self, interaction):
            if not is_staff_or_admin(interaction):
                await interaction.response.send_message("⛔ Solo Staff/administradores.", ephemeral=True)
                return
            rows = pending_clauses()
            await interaction.response.send_message(embed=pending_embed(), view=PendingClauseView(rows), ephemeral=True)

    ClausulazoAdminView.__name__ = "AdminView"
    return ClausulazoAdminView


def apply_clausulazo_patch(runtime, bot):
    global APP
    APP = runtime
    ensure_schema()
    patch_close_report_mode()
    runtime.MercadoView = build_market_view(runtime.MercadoView)
    runtime.AdminView = patch_admin_view(runtime.AdminView)

    if bot.tree.get_command("clausulazos_pendientes") is None:
        @bot.tree.command(name="clausulazos_pendientes", description="Revisa clausulazos pendientes de aprobación Staff")
        async def clausulazos_pendientes(interaction: discord.Interaction):
            if not is_staff_or_admin(interaction):
                await interaction.response.send_message("⛔ Solo Staff/administradores.", ephemeral=True)
                return
            rows = pending_clauses()
            await interaction.response.send_message(embed=pending_embed(), view=PendingClauseView(rows), ephemeral=True)

    if bot.tree.get_command("configurar_clausula") is None:
        @bot.tree.command(name="configurar_clausula", description="Configura el valor universal del clausulazo")
        async def configurar_clausula(interaction: discord.Interaction, monto: int):
            if not APP.es_admin(interaction):
                await interaction.response.send_message("⛔ Solo administradores.", ephemeral=True)
                return
            if monto <= 0:
                await interaction.response.send_message("⚠️ El monto debe ser mayor a cero.", ephemeral=True)
                return
            set_clause_price(monto)
            await interaction.response.send_message(f"💥 Cláusula universal configurada en **{fmt_money(monto)}**.", ephemeral=True)

    if bot.tree.get_command("configurar_saldo") is None:
        @bot.tree.command(name="configurar_saldo", description="Configura el saldo de mercado de un club")
        async def configurar_saldo(interaction: discord.Interaction, club: str, monto: int):
            if not APP.es_admin(interaction):
                await interaction.response.send_message("⛔ Solo administradores.", ephemeral=True)
                return
            if monto < 0:
                await interaction.response.send_message("⚠️ El saldo no puede ser negativo.", ephemeral=True)
                return
            set_club_balance(club, monto)
            await interaction.response.send_message(f"🏦 Saldo de **{club.strip()}** configurado en **{fmt_money(monto)}**.", ephemeral=True)

    if bot.tree.get_command("saldo") is None:
        @bot.tree.command(name="saldo", description="Consulta el saldo de mercado de tu club")
        async def saldo(interaction: discord.Interaction):
            club = APP.club_de(interaction.user.id)
            if not club:
                await interaction.response.send_message("⚠️ Primero tenés que tener un equipo asignado.", ephemeral=True)
                return
            await interaction.response.send_message(f"🏦 **{club}** • Saldo disponible: **{fmt_money(club_balance(club))}**", ephemeral=True)

    print("AJAP clausulazo activo: universal + Staff + saldo reservado + bloqueo por ventana")
