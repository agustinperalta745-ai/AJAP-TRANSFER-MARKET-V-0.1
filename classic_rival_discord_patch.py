"""Discord UI for the shared AJPA classic-rival system.

Uses the exact same SQLite tables/rules as AJPA Mobile, so a proposal accepted
in Discord is immediately visible in the app and vice versa.
"""

from __future__ import annotations

import discord

import mobile_classic_rival_api_patch as classic
import mobile_write_api

APP = None
BOT = None


def _session(user_id: int) -> dict:
    return {"user_id": int(user_id), "is_staff": False}


def _manager_name(guild: discord.Guild | None, user_id: int | None) -> str:
    if not user_id:
        return "Sin DT asignado"
    if guild:
        member = guild.get_member(int(user_id))
        if member:
            return str(member.name or member.display_name or "DT asignado")
    return "DT asignado"


def _state(conn, user_id: int):
    classic.ensure_schema(conn)
    club = mobile_write_api._require_club(conn, _session(user_id))
    current = classic.classic_public_payload(conn, club)
    incoming = conn.execute(
        """
        SELECT * FROM classic_rival_requests
        WHERE target_club=? COLLATE NOCASE AND status='PENDING'
        ORDER BY id DESC
        """,
        (club,),
    ).fetchall()
    outgoing = conn.execute(
        """
        SELECT * FROM classic_rival_requests
        WHERE requester_club=? COLLATE NOCASE AND status='PENDING'
        ORDER BY id DESC LIMIT 1
        """,
        (club,),
    ).fetchone()
    return club, current, incoming, outgoing


def _embed(guild: discord.Guild | None, user_id: int) -> discord.Embed:
    with APP.db() as conn:
        club, current, incoming, outgoing = _state(conn, user_id)

    embed = discord.Embed(
        title=f"🔥 Clásico rival · {club}",
        description=(
            "Elegí el club que considerás tu clásico. El DT rival debe aceptar la propuesta.\n\n"
            "⚠️ Una vez confirmado, el clásico queda **fijo** y solo puede liberarse cuando uno de los dos tenga **11 o más victorias de diferencia** en el historial entre ambos."
        ),
    )

    if current:
        rival = current["opponent"]
        manager = current["opponent_manager"]
        history = current["history"]
        manager_name = _manager_name(guild, int(manager["user_id"]) if manager.get("user_id") else None)
        embed.add_field(
            name="🔥 Clásico confirmado",
            value=f"**{rival}** · DT: **{manager_name}**",
            inline=False,
        )
        embed.add_field(
            name="📊 Historial entre ambos",
            value=(
                f"{club}: **{history['wins']}** victorias\n"
                f"Empates: **{history['draws']}**\n"
                f"{rival}: **{history['losses']}** victorias\n"
                f"Partidos: **{history['played']}** · Goles: **{history['goals_for']}-{history['goals_against']}**"
            ),
            inline=False,
        )
        if history["release_allowed"]:
            embed.add_field(name="🔓 Liberación", value="Ya se superó la diferencia de 10 victorias. Se puede liberar este clásico.", inline=False)
        else:
            diff = abs(int(history["win_difference"]))
            embed.add_field(name="🔒 Clásico fijo", value=f"Diferencia actual: **{diff}** victoria(s). Se libera recién con 11 o más.", inline=False)
    else:
        embed.add_field(name="Estado", value="Todavía no tenés un clásico rival confirmado.", inline=False)

    if outgoing:
        embed.add_field(
            name="📤 Propuesta enviada",
            value=f"Esperando respuesta de **{outgoing['target_club']}**.",
            inline=False,
        )
    if incoming:
        clubs = "\n".join(f"• **{row['requester_club']}**" for row in incoming[:10])
        embed.add_field(name="📥 Propuestas recibidas", value=clubs, inline=False)

    embed.set_footer(text="AJPA · Clásicos compartidos entre Discord y la app")
    return embed


async def _dm(user_id: int, content: str) -> None:
    try:
        user = BOT.get_user(int(user_id)) or await BOT.fetch_user(int(user_id))
        await user.send(content)
    except (discord.Forbidden, discord.HTTPException, discord.NotFound):
        pass


class ClassicTargetSelect(discord.ui.Select):
    def __init__(self, owner_id: int):
        self.owner_id = int(owner_id)
        with APP.db() as conn:
            club, current, _incoming, outgoing = _state(conn, owner_id)
            active = set()
            for row in conn.execute("SELECT club_a, club_b FROM classic_rivals WHERE active=1").fetchall():
                active.add(str(row["club_a"]).casefold())
                active.add(str(row["club_b"]).casefold())
            rows = conn.execute(
                "SELECT name FROM league_teams WHERE active=1 ORDER BY name COLLATE NOCASE"
            ).fetchall()
            options = []
            for row in rows:
                candidate = str(row["name"])
                if candidate.casefold() == club.casefold():
                    continue
                owner = classic._owner_id(conn, candidate)
                if owner is None:
                    desc = "Sin DT asignado"
                elif candidate.casefold() in active:
                    desc = "Ya tiene clásico rival"
                else:
                    desc = "Disponible"
                options.append(discord.SelectOption(label=candidate[:100], value=candidate, description=desc[:100]))

        super().__init__(
            placeholder="Elegir clásico rival",
            min_values=1,
            max_values=1,
            options=options[:25] or [discord.SelectOption(label="Sin equipos disponibles", value="__none__")],
            disabled=bool(current or outgoing or not options),
            row=0,
        )

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("⛔ Este menú no te pertenece.", ephemeral=True)
            return
        if self.values[0] == "__none__":
            await interaction.response.send_message("⚠️ No hay equipos disponibles.", ephemeral=True)
            return
        target = self.values[0]
        try:
            with APP.db() as conn:
                conn.execute("BEGIN IMMEDIATE")
                result, notification = classic._request_classic(conn, _session(interaction.user.id), {"target_club": target})
                conn.commit()
            if notification:
                await _dm(
                    notification[0],
                    f"🔥 **{result['requester_club']} considera que sos su clásico rival.**\n\n"
                    f"⚠️ Si aceptás, **{result['requester_club']}** será el clásico rival fijo de **{result['target_club']}**. "
                    "Solo podrá liberarse si uno de los dos llega a tener **11 o más victorias de diferencia** en el historial entre ambos.\n\n"
                    "Para responder entrá al servidor y usá **/clasico** o **Mercado → Clásico rival**.",
                )
            await interaction.response.edit_message(embed=_embed(interaction.guild, interaction.user.id), view=ClassicHubView(interaction.user.id))
        except mobile_write_api.ApiFailure as exc:
            await interaction.response.send_message(f"⚠️ {exc.message}", ephemeral=True)


class IncomingSelect(discord.ui.Select):
    def __init__(self, owner_id: int, rows):
        self.owner_id = int(owner_id)
        super().__init__(
            placeholder="Responder propuesta de clásico",
            min_values=1,
            max_values=1,
            options=[
                discord.SelectOption(label=str(row["requester_club"])[:100], value=str(row["id"]), description="Aceptar o rechazar")
                for row in rows[:25]
            ],
            row=1,
        )

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("⛔ Este menú no te pertenece.", ephemeral=True)
            return
        request_id = int(self.values[0])
        with APP.db() as conn:
            row = conn.execute("SELECT requester_club FROM classic_rival_requests WHERE id=?", (request_id,)).fetchone()
        if not row:
            await interaction.response.send_message("⚠️ Esa propuesta ya no existe.", ephemeral=True)
            return
        await interaction.response.send_message(
            embed=discord.Embed(
                title="🔥 Propuesta de clásico",
                description=(
                    f"**{row['requester_club']} considera que sos su clásico rival.**\n\n"
                    "Si aceptás, ambos clubes quedarán vinculados como clásico fijo hasta que haya 11 o más victorias de diferencia."
                ),
            ),
            view=ClassicResponseView(self.owner_id, request_id),
            ephemeral=True,
        )


class ClassicResponseView(discord.ui.View):
    def __init__(self, owner_id: int, request_id: int):
        super().__init__(timeout=300)
        self.owner_id = int(owner_id)
        self.request_id = int(request_id)

    async def _answer(self, interaction: discord.Interaction, decision: str):
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("⛔ Esta propuesta no te pertenece.", ephemeral=True)
            return
        try:
            with APP.db() as conn:
                conn.execute("BEGIN IMMEDIATE")
                result, notification = classic._respond_classic(
                    conn,
                    _session(interaction.user.id),
                    {"request_id": self.request_id, "decision": decision},
                )
                conn.commit()
            if notification:
                await _dm(notification[0], notification[1] + "\n\nTambién podés verlo desde **/clasico** y AJPA Mobile.")
            if decision == "ACCEPT":
                text = f"🔥 **{result['requester_club']} vs {result['target_club']}** ya es un clásico oficial de AJPA."
            else:
                text = f"❌ Rechazaste la propuesta de **{result['requester_club']}**."
            await interaction.response.edit_message(content=text, embed=None, view=None)
        except mobile_write_api.ApiFailure as exc:
            await interaction.response.send_message(f"⚠️ {exc.message}", ephemeral=True)

    @discord.ui.button(label="Aceptar clásico", emoji="🔥", style=discord.ButtonStyle.success)
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._answer(interaction, "ACCEPT")

    @discord.ui.button(label="Rechazar", emoji="✖️", style=discord.ButtonStyle.danger)
    async def reject(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._answer(interaction, "REJECT")


class ClassicHubView(discord.ui.View):
    def __init__(self, owner_id: int):
        super().__init__(timeout=300)
        self.owner_id = int(owner_id)
        with APP.db() as conn:
            _club, current, incoming, outgoing = _state(conn, owner_id)
        self.add_item(ClassicTargetSelect(owner_id))
        if incoming:
            self.add_item(IncomingSelect(owner_id, incoming))
        if outgoing:
            cancel = discord.ui.Button(label="Cancelar propuesta", emoji="↩️", style=discord.ButtonStyle.secondary, row=2)
            cancel.callback = self._cancel
            self.add_item(cancel)
        if current and current["history"]["release_allowed"]:
            release = discord.ui.Button(label="Liberar clásico", emoji="🔓", style=discord.ButtonStyle.danger, row=2)
            release.callback = self._release
            self.add_item(release)
        refresh = discord.ui.Button(label="Actualizar", emoji="🔄", style=discord.ButtonStyle.secondary, row=3)
        refresh.callback = self._refresh
        self.add_item(refresh)

    async def _refresh(self, interaction: discord.Interaction):
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("⛔ Este menú no te pertenece.", ephemeral=True)
            return
        await interaction.response.edit_message(embed=_embed(interaction.guild, interaction.user.id), view=ClassicHubView(interaction.user.id))

    async def _cancel(self, interaction: discord.Interaction):
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("⛔ Este menú no te pertenece.", ephemeral=True)
            return
        try:
            with APP.db() as conn:
                _club, _current, _incoming, outgoing = _state(conn, interaction.user.id)
                if not outgoing:
                    raise mobile_write_api.ApiFailure("No tenés una propuesta pendiente.")
                conn.execute("BEGIN IMMEDIATE")
                classic._cancel_request(conn, _session(interaction.user.id), {"request_id": int(outgoing["id"])})
                conn.commit()
            await interaction.response.edit_message(embed=_embed(interaction.guild, interaction.user.id), view=ClassicHubView(interaction.user.id))
        except mobile_write_api.ApiFailure as exc:
            await interaction.response.send_message(f"⚠️ {exc.message}", ephemeral=True)

    async def _release(self, interaction: discord.Interaction):
        if interaction.user.id != self.owner_id:
            await interaction.response.send_message("⛔ Este menú no te pertenece.", ephemeral=True)
            return
        try:
            with APP.db() as conn:
                conn.execute("BEGIN IMMEDIATE")
                result = classic._release_classic(conn, _session(interaction.user.id), {})
                conn.commit()
            await interaction.response.edit_message(
                content=f"🔓 Se liberó el clásico **{result['club']} vs {result['opponent']}**.",
                embed=None,
                view=None,
            )
        except mobile_write_api.ApiFailure as exc:
            await interaction.response.send_message(f"⚠️ {exc.message}", ephemeral=True)


async def classic_command(interaction: discord.Interaction):
    if not interaction.guild:
        await interaction.response.send_message("Usá este menú dentro del servidor de AJPA.", ephemeral=True)
        return
    try:
        with APP.db() as conn:
            _state(conn, interaction.user.id)
        await interaction.response.send_message(
            embed=_embed(interaction.guild, interaction.user.id),
            view=ClassicHubView(interaction.user.id),
            ephemeral=True,
        )
    except mobile_write_api.ApiFailure as exc:
        await interaction.response.send_message(f"⚠️ {exc.message}", ephemeral=True)


def _patch_market_view():
    old = APP.MercadoView

    class ClassicMercadoView(old):
        def __init__(self):
            super().__init__()
            if any(getattr(item, "custom_id", None) == "mercado_clasico" for item in self.children):
                return
            button = discord.ui.Button(
                label="Clásico rival",
                emoji="🔥",
                style=discord.ButtonStyle.secondary,
                custom_id="mercado_clasico",
                row=3,
            )
            button.callback = self._classic
            self.add_item(button)

        async def _classic(self, interaction: discord.Interaction):
            await classic_command(interaction)

    ClassicMercadoView.__name__ = "MercadoView"
    APP.MercadoView = ClassicMercadoView


def apply_classic_rival_discord_patch(runtime, bot) -> None:
    global APP, BOT
    if getattr(bot, "_ajpa_classic_rival_discord_patch", False):
        return
    APP = runtime
    BOT = bot
    with APP.db() as conn:
        classic.ensure_schema(conn)
        conn.commit()
    _patch_market_view()
    if bot.tree.get_command("clasico") is None:
        bot.tree.command(name="clasico", description="Elegí, respondé o consultá tu clásico rival")(classic_command)
    bot._ajpa_classic_rival_discord_patch = True
    print("AJPA Discord: sistema de clásico rival activo y compartido con Mobile")
