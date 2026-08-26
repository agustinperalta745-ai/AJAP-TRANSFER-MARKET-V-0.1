"""Free-team vacancy announcements for AJAP Transfer Market.

When an administrator unlinks a manager from a club:
- the club is automatically advertised in the configured #equipos-libres channel;
- the card shows roster, remaining budget and whether the club still has its
  clausulazo available in the current market;
- users can request the vacancy from a persistent button;
- administrators receive a notification of the request.

The clausulazo entitlement is also carried by the club, so changing manager does
not reset a clausulazo already used by that club in the same market window.
"""

from __future__ import annotations

import re

import discord

import team_assignment as teams
import clausulazo_patch as clauses

APP = None
BOT = None


def _fmt_money(value) -> str:
    try:
        return f"${int(value):,}".replace(",", ".")
    except (TypeError, ValueError):
        return "$0"


def _ensure_schema():
    with APP.db() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS free_team_config (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                channel_id INTEGER
            );

            CREATE TABLE IF NOT EXISTS free_team_requests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                club TEXT NOT NULL COLLATE NOCASE,
                user_id INTEGER NOT NULL,
                username TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'PENDIENTE',
                requested_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                resolved_by INTEGER,
                resolved_at DATETIME
            );

            CREATE INDEX IF NOT EXISTS idx_free_team_requests_club_status
                ON free_team_requests (club, status);
            CREATE INDEX IF NOT EXISTS idx_free_team_requests_user_status
                ON free_team_requests (user_id, status);
            """
        )


def _set_channel_id(channel_id: int):
    _ensure_schema()
    with APP.db() as conn:
        conn.execute(
            """
            INSERT INTO free_team_config (id, channel_id)
            VALUES (1, ?)
            ON CONFLICT(id) DO UPDATE SET channel_id = excluded.channel_id
            """,
            (int(channel_id),),
        )


def _get_channel_id():
    _ensure_schema()
    with APP.db() as conn:
        row = conn.execute(
            "SELECT channel_id FROM free_team_config WHERE id = 1"
        ).fetchone()
    return int(row["channel_id"]) if row and row["channel_id"] else None


def _normalize_channel_name(name: str) -> str:
    raw = (name or "").strip().casefold()
    raw = re.sub(r"[_\s]+", "-", raw)
    raw = re.sub(r"-+", "-", raw)
    return raw.strip("-")


async def _resolve_free_teams_channel(guild):
    if guild is None:
        return None

    configured = _get_channel_id()
    if configured:
        channel = guild.get_channel(configured)
        if channel is None:
            try:
                channel = await BOT.fetch_channel(configured)
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                channel = None
        if channel is not None and hasattr(channel, "send"):
            return channel

    # Zero-config fallback for the channel name the league is already using.
    preferred = {
        "equipos-libres",
        "equipo-libre",
        "vacantes",
        "dt-vacantes",
    }
    for channel in getattr(guild, "text_channels", []):
        if _normalize_channel_name(channel.name) in preferred:
            return channel

    for channel in getattr(guild, "text_channels", []):
        norm = _normalize_channel_name(channel.name)
        if "equipo" in norm and "libre" in norm:
            return channel

    return None


def _club_is_free(club: str) -> bool:
    with APP.db() as conn:
        row = conn.execute(
            "SELECT user_id FROM clubs WHERE name = ? COLLATE NOCASE LIMIT 1",
            (club,),
        ).fetchone()
    return row is None


def _player_rating(player):
    if player is None or "rating" not in player.keys() or player["rating"] is None:
        return -1
    try:
        return int(player["rating"])
    except (TypeError, ValueError):
        return -1


def _roster_text(club: str) -> str:
    players = list(APP.jugadores_de_club(club, 100))
    players.sort(key=lambda p: (-_player_rating(p), str(p["name"]).casefold()))
    if not players:
        return "_No hay jugadores cargados._"

    lines = []
    used = 0
    for index, player in enumerate(players):
        rating = _player_rating(player)
        ovr = str(rating) if rating >= 0 else "—"
        line = f"• **{player['name']}** — {player['position']} • OVR {ovr}"
        # Discord embed fields are limited to 1024 chars.
        if used + len(line) + 1 > 940:
            remaining = len(players) - index
            lines.append(f"… y **{remaining}** jugador(es) más.")
            break
        lines.append(line)
        used += len(line) + 1
    return "\n".join(lines)


def _club_clause_state(club: str):
    cycle = clauses.active_cycle()
    if not cycle:
        return None
    with APP.db() as conn:
        return conn.execute(
            """
            SELECT *
            FROM clause_requests
            WHERE cycle_id = ?
              AND buyer_club = ? COLLATE NOCASE
              AND status IN ('PENDIENTE_STAFF', 'APROBADO')
            ORDER BY CASE status WHEN 'APROBADO' THEN 0 ELSE 1 END, id DESC
            LIMIT 1
            """,
            (int(cycle["id"]), club),
        ).fetchone()


def _clause_availability(club: str) -> str:
    cycle = clauses.active_cycle()
    if not cycle:
        return "✅ Disponible para el próximo mercado"

    state = _club_clause_state(club)
    if not state:
        return "✅ Disponible"
    if (state["status"] or "").upper() == "APROBADO":
        return f"❌ No disponible • ya utilizado por **{state['player']}**"
    return f"⏳ No disponible • clausulazo pendiente por **{state['player']}**"


def vacancy_embed(club: str):
    balance = clauses.club_balance(club)
    embed = discord.Embed(
        title=f"📣 {club} está buscando DT!",
        description=(
            "El club quedó **sin entrenador** y está disponible para recibir solicitudes."
        ),
        color=discord.Color.blue(),
    )
    embed.add_field(name="🏟️ Plantilla", value=_roster_text(club), inline=False)
    embed.add_field(
        name="💰 Dinero disponible",
        value=f"**{_fmt_money(balance)}**",
        inline=True,
    )
    embed.add_field(
        name="💥 Clausulazo",
        value=_clause_availability(club),
        inline=True,
    )
    embed.set_footer(
        text="Si querés hacerte cargo del club, usá el botón Solicitar vacante."
    )
    return embed


def _request_exists(club: str, user_id: int) -> bool:
    _ensure_schema()
    with APP.db() as conn:
        row = conn.execute(
            """
            SELECT id FROM free_team_requests
            WHERE club = ? COLLATE NOCASE
              AND user_id = ?
              AND status = 'PENDIENTE'
            ORDER BY id DESC LIMIT 1
            """,
            (club, int(user_id)),
        ).fetchone()
    return bool(row)


def _create_request(club: str, user) -> int:
    _ensure_schema()
    with APP.db() as conn:
        cur = conn.execute(
            """
            INSERT INTO free_team_requests (club, user_id, username)
            VALUES (?, ?, ?)
            """,
            (club, int(user.id), str(user)),
        )
        return int(cur.lastrowid)


def _admin_request_embed(request_id: int, club: str, user):
    embed = discord.Embed(
        title="📥 Nueva solicitud de vacante",
        description=(
            f"{user.mention} quiere hacerse cargo de **{club}**."
        ),
        color=discord.Color.gold(),
    )
    embed.add_field(name="👤 Usuario", value=f"{user} • `{user.id}`", inline=False)
    embed.add_field(name="🏟️ Club solicitado", value=club, inline=True)
    embed.add_field(
        name="💰 Dinero del club",
        value=_fmt_money(clauses.club_balance(club)),
        inline=True,
    )
    embed.add_field(name="💥 Clausulazo", value=_clause_availability(club), inline=False)
    embed.set_footer(text=f"Solicitud de vacante #{request_id} • Revisar antes de asignar el club")
    return embed


async def _staff_report_channel(guild):
    try:
        import market_channel_report_patch as market_reports

        channel_id = market_reports.get_report_channel_id(guild.id)
        if not channel_id:
            return None
        channel = guild.get_channel(int(channel_id))
        if channel is None:
            try:
                channel = await BOT.fetch_channel(int(channel_id))
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                return None
        return channel if hasattr(channel, "send") else None
    except Exception:
        return None


async def _notify_admins(guild, request_id: int, club: str, user) -> int:
    if guild is None:
        return 0

    embed = _admin_request_embed(request_id, club, user)
    delivered = 0

    # Also post in the configured Staff/PES channel when it exists.
    staff_channel = await _staff_report_channel(guild)
    if staff_channel is not None:
        try:
            await staff_channel.send(embed=embed)
            delivered += 1
        except (discord.Forbidden, discord.HTTPException):
            pass

    # DM the server owner and cached administrators. Intents.default() does not
    # guarantee a complete member cache, so the staff-channel copy above is the
    # reliable shared notification path.
    recipients = {}
    owner = getattr(guild, "owner", None)
    if owner is not None and not owner.bot:
        recipients[owner.id] = owner

    for member in getattr(guild, "members", []):
        try:
            if not member.bot and member.guild_permissions.administrator:
                recipients[member.id] = member
        except AttributeError:
            continue

    for member in recipients.values():
        try:
            await member.send(embed=embed)
            delivered += 1
        except (discord.Forbidden, discord.HTTPException):
            pass

    return delivered


class FreeTeamVacancyView(discord.ui.View):
    def __init__(self, club: str):
        super().__init__(timeout=None)
        self.club = club

        button = discord.ui.Button(
            label="Solicitar vacante",
            emoji="📩",
            style=discord.ButtonStyle.success,
            custom_id=f"ajap:free-team:apply:{club}"[:100],
        )
        button.callback = self._apply
        self.add_item(button)

    async def _apply(self, interaction: discord.Interaction):
        if not _club_is_free(self.club):
            await interaction.response.send_message(
                f"⚠️ **{self.club}** ya fue asignado a otro DT.",
                ephemeral=True,
            )
            return

        current = APP.club_de(interaction.user.id)
        if current:
            await interaction.response.send_message(
                f"⚠️ Ya estás a cargo de **{current}**. Primero un administrador debe desvincularte.",
                ephemeral=True,
            )
            return

        if _request_exists(self.club, interaction.user.id):
            await interaction.response.send_message(
                f"⏳ Ya tenés una solicitud pendiente por **{self.club}**.",
                ephemeral=True,
            )
            return

        request_id = _create_request(self.club, interaction.user)
        delivered = await _notify_admins(
            interaction.guild, request_id, self.club, interaction.user
        )

        await interaction.response.send_message(
            (
                f"✅ Solicitud enviada para **{self.club}**.\n"
                "Los administradores fueron avisados."
                if delivered
                else
                f"✅ Solicitud registrada para **{self.club}**.\n"
                "No pude entregar la alerta por Discord; un administrador podrá verla en la base."
            ),
            ephemeral=True,
        )


async def _publish_vacancy(guild, club: str):
    channel = await _resolve_free_teams_channel(guild)
    if channel is None:
        return False

    try:
        await channel.send(
            embed=vacancy_embed(club),
            view=FreeTeamVacancyView(club),
        )
        return True
    except (discord.Forbidden, discord.HTTPException) as exc:
        print(f"WARNING AJAP: no se pudo publicar vacante de {club}: {exc}")
        return False


def _install_unlink_alert():
    if getattr(teams, "_ajap_free_team_unlink_alert", False):
        return

    class AlertingConfirmUnlinkView(discord.ui.View):
        def __init__(self, user_id, team):
            super().__init__(timeout=120)
            self.user_id = int(user_id)
            self.team = team

        @discord.ui.button(
            label="Desvincular equipo",
            emoji="↩️",
            style=discord.ButtonStyle.danger,
        )
        async def confirm(
            self, interaction: discord.Interaction, button: discord.ui.Button
        ):
            if not APP.es_admin(interaction):
                await interaction.response.send_message("⛔ Solo admins.", ephemeral=True)
                return

            current = teams.club_de(self.user_id)
            if not current or current.casefold() != self.team.casefold():
                await interaction.response.send_message(
                    "⚠️ Esa asignación ya cambió.", ephemeral=True
                )
                return

            removed = teams.unlink_team(self.user_id, interaction.user.id)
            if not removed:
                await interaction.response.send_message(
                    "⚠️ Esa asignación ya no existe.", ephemeral=True
                )
                return

            embed = discord.Embed(
                title="↩️ Asignación revertida",
                description=(
                    f"<@{self.user_id}> ya no tiene **{removed}**.\n\n"
                    f"✅ La plantilla de **{removed}** quedó intacta."
                ),
            )
            await interaction.response.edit_message(embed=embed, view=None)

            published = await _publish_vacancy(interaction.guild, removed)
            if not published:
                try:
                    await interaction.followup.send(
                        (
                            "⚠️ El equipo fue desvinculado, pero no encontré el canal de **equipos libres**.\n"
                            "Ejecutá `/canal_equipos_libres` dentro del canal correcto para dejarlo configurado."
                        ),
                        ephemeral=True,
                    )
                except discord.HTTPException:
                    pass

        @discord.ui.button(
            label="Cancelar",
            emoji="✖️",
            style=discord.ButtonStyle.secondary,
        )
        async def cancel(
            self, interaction: discord.Interaction, button: discord.ui.Button
        ):
            if not APP.es_admin(interaction):
                await interaction.response.send_message("⛔ Solo admins.", ephemeral=True)
                return
            await interaction.response.edit_message(
                content="Cancelado.", embed=None, view=None
            )

    teams.ConfirmUnlinkView = AlertingConfirmUnlinkView
    teams._ajap_free_team_unlink_alert = True


def _install_club_clause_entitlement():
    """A club cannot regain a clausulazo just because its manager changes."""
    if getattr(clauses, "_ajap_club_buyer_clause_lock", False):
        return

    original_create = clauses.create_clause_request
    original_approve = clauses.approve_request

    def create_clause_request(interaction, ficha):
        buyer_club = APP.club_de(interaction.user.id)
        cycle = clauses.active_cycle()
        if buyer_club and cycle:
            state = _club_clause_state(buyer_club)
            if state:
                if (state["status"] or "").upper() == "APROBADO":
                    return (
                        False,
                        f"🛡️ **{buyer_club} ya utilizó su clausulazo de este mercado** "
                        f"por **{state['player']}**. Cambiar de DT no reinicia el cupo del club.",
                    )
                return (
                    False,
                    f"⏳ **{buyer_club} ya tiene un clausulazo pendiente** "
                    f"por **{state['player']}**. Debe resolverse antes de intentar otro.",
                )
        return original_create(interaction, ficha)

    def approve_request(req, staff_id):
        fresh = clauses.request_by_id(req["id"])
        if fresh and (fresh["status"] or "").upper() == "PENDIENTE_STAFF":
            with APP.db() as conn:
                other = conn.execute(
                    """
                    SELECT *
                    FROM clause_requests
                    WHERE cycle_id = ?
                      AND buyer_club = ? COLLATE NOCASE
                      AND status = 'APROBADO'
                      AND id != ?
                    ORDER BY id DESC LIMIT 1
                    """,
                    (
                        int(fresh["cycle_id"]),
                        fresh["buyer_club"],
                        int(fresh["id"]),
                    ),
                ).fetchone()
            if other:
                clauses.reject_request(
                    fresh,
                    staff_id,
                    "El club ya utilizó su clausulazo en este mercado",
                )
                return (
                    False,
                    f"🛡️ **{fresh['buyer_club']}** ya utilizó su clausulazo por "
                    f"**{other['player']}**. La solicitud fue rechazada y el dinero devuelto.",
                )
        return original_approve(req, staff_id)

    clauses.create_clause_request = create_clause_request
    clauses.approve_request = approve_request
    clauses._ajap_club_buyer_clause_lock = True


def _register_commands():
    if BOT.tree.get_command("canal_equipos_libres") is None:

        @BOT.tree.command(
            name="canal_equipos_libres",
            description="Configura este canal para publicar automáticamente equipos sin DT",
        )
        async def canal_equipos_libres(interaction: discord.Interaction):
            if not APP.es_admin(interaction):
                await interaction.response.send_message(
                    "⛔ Solo administradores.", ephemeral=True
                )
                return
            if interaction.channel is None or not hasattr(interaction.channel, "send"):
                await interaction.response.send_message(
                    "⚠️ Ejecutá este comando dentro de un canal de texto.",
                    ephemeral=True,
                )
                return
            _set_channel_id(interaction.channel.id)
            await interaction.response.send_message(
                (
                    f"✅ {interaction.channel.mention} quedó configurado como **canal de equipos libres**.\n"
                    "A partir de ahora, cada desvinculación publicará automáticamente la vacante acá."
                ),
                ephemeral=True,
            )


def _register_persistent_views():
    # One persistent view per official club. The interaction guild context selects
    # the correct per-server SQLite database at click time.
    clubs = []
    for name, _country in teams.OFFICIAL_TEAMS:
        if name.casefold() not in {club.casefold() for club in clubs}:
            clubs.append(name)

    for club in clubs:
        try:
            BOT.add_view(FreeTeamVacancyView(club))
        except ValueError:
            pass


def apply_free_team_vacancy_patch(runtime, bot):
    global APP, BOT
    APP = runtime
    BOT = bot

    if getattr(runtime, "_ajap_free_team_vacancy_patch", False):
        return

    _install_unlink_alert()
    _install_club_clause_entitlement()
    _register_commands()
    _register_persistent_views()

    runtime.FreeTeamVacancyView = FreeTeamVacancyView
    runtime.free_team_vacancy_embed = vacancy_embed
    runtime._ajap_free_team_vacancy_patch = True

    print(
        "AJAP vacantes de DT activas: alerta automática + plantilla + saldo + "
        "clausulazo por club + botón Solicitar vacante"
    )
