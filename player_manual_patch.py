"""Manual de jugador integrado para AJPA Transfer Market.

Comportamiento:
- La primera vez que un usuario normal abre /mercado, ve el manual antes del selector/panel.
- El manual se presenta en 4 páginas cortas y fáciles de leer.
- Recién al finalizar y tocar "ENTENDIDO • IR AL MERCADO" queda marcado como leído.
- Después, /mercado abre normalmente.
- El panel principal conserva un botón "MANUAL BOT" para volver a consultarlo cuando quiera.
- Staff no recibe el manual automáticamente, aunque puede abrirlo desde el botón si aparece en modo usuario.

El estado de lectura se guarda por servidor en SQLite. Cambiar MANUAL_VERSION permite
forzar una nueva lectura en el futuro sin borrar datos.
"""

from __future__ import annotations

import discord

import guild_isolation_patch as guild_isolation


APP = None
BOT = None
ORIGINAL_MERCADO_CALLBACK = None
MANUAL_VERSION = 1
LAST_PAGE = 3


def _guild_context(interaction: discord.Interaction):
    return guild_isolation._CURRENT_GUILD_ID.set(
        guild_isolation._interaction_guild_id(interaction)
    )


def _reset_guild_context(token):
    guild_isolation._CURRENT_GUILD_ID.reset(token)


def _ensure_schema():
    with APP.db() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS player_manual_state (
                user_id INTEGER PRIMARY KEY,
                manual_version INTEGER NOT NULL DEFAULT 0,
                seen_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.commit()


def _manual_seen(user_id: int) -> bool:
    _ensure_schema()
    with APP.db() as conn:
        row = conn.execute(
            "SELECT manual_version FROM player_manual_state WHERE user_id = ? LIMIT 1",
            (int(user_id),),
        ).fetchone()
    return bool(row and int(row["manual_version"] or 0) >= MANUAL_VERSION)


def _mark_seen(user_id: int):
    _ensure_schema()
    with APP.db() as conn:
        conn.execute(
            """
            INSERT INTO player_manual_state (user_id, manual_version, seen_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(user_id) DO UPDATE SET
                manual_version = excluded.manual_version,
                seen_at = CURRENT_TIMESTAMP
            """,
            (int(user_id), MANUAL_VERSION),
        )
        conn.commit()


def _page_footer(embed: discord.Embed, page: int):
    embed.set_footer(text=f"AJPA Transfer Market • Manual del Bot • {page + 1}/4")
    return embed


def manual_embed(page: int) -> discord.Embed:
    page = max(0, min(int(page), LAST_PAGE))

    if page == 0:
        embed = discord.Embed(
            title="📖 MANUAL DEL BOT • BIENVENIDO A AJPA",
            description=(
                "Antes de empezar, te mostramos rápidamente cómo manejar tu club.\n\n"
                "El acceso principal es **`/mercado`**. Desde ahí vas a gestionar tu equipo, "
                "negociaciones, economía y Liga."
            ),
            color=discord.Color.blurple(),
        )
        embed.add_field(
            name="🚀 Tu primera entrada",
            value=(
                "Si todavía no tenés club, después de este manual vas a elegir uno de los equipos disponibles.\n\n"
                "Al asignarte un club, el bot registra tu cargo de DT, te da el rol correspondiente y sincroniza "
                "tu apodo como **Nombre | Club**."
            ),
            inline=False,
        )
        embed.add_field(
            name="🏟️ Panel principal",
            value=(
                "**MI CLUB** • **MERCADO** • **OFERTAS** • **BUSCAR** • **HISTORIAL** • **LIGA**\n"
                "También vas a poder renunciar al club cuando corresponda."
            ),
            inline=False,
        )
        return _page_footer(embed, page)

    if page == 1:
        embed = discord.Embed(
            title="🏟️ MI CLUB Y MERCADO",
            description="Todo lo relacionado con tu plantel y las operaciones de mercado está organizado desde el panel.",
            color=discord.Color.blurple(),
        )
        embed.add_field(
            name="🏟️ MI CLUB",
            value=(
                "👥 **Plantilla:** jugadores, OVR y estadísticas PES 6.\n"
                "💰 **Economía:** presupuesto disponible.\n"
                "💼 **Tesorería:** ingresos, egresos y movimientos reales.\n"
                "📊 **Valor del club:** valor total/promedio de la plantilla.\n"
                "ℹ️ **Información:** resumen general de tu equipo."
            ),
            inline=False,
        )
        embed.add_field(
            name="🔁 MERCADO",
            value=(
                "📤 **Publicar:** poner jugadores de tu club en el mercado.\n"
                "📋 **Transferibles:** ver jugadores publicados por otros equipos.\n"
                "🔎 **Buscar:** localizar jugadores de cualquier plantel.\n"
                "💥 **Clausulazo:** ejecutar una cláusula cuando cumplís las condiciones del sistema."
            ),
            inline=False,
        )
        embed.add_field(
            name="🆓 Liberar jugador",
            value=(
                "Podés liberar un jugador propio **solo con el mercado abierto**. "
                "El costo es el **20% de su valor de mercado** y el bot muestra el importe exacto antes de confirmar."
            ),
            inline=False,
        )
        return _page_footer(embed, page)

    if page == 2:
        embed = discord.Embed(
            title="🤝 OFERTAS, NEGOCIACIONES Y PRÉSTAMOS",
            description="Las negociaciones se gestionan desde el mismo bot y quedan registradas.",
            color=discord.Color.blurple(),
        )
        embed.add_field(
            name="📩 Ofertas",
            value=(
                "Podés ofertar con **solo dinero**, **jugador/es** o una combinación de **dinero + jugador**.\n\n"
                "Si recibís una oferta, podés **aceptar**, **rechazar** o **contraofertar** según el estado de la negociación."
            ),
            inline=False,
        )
        embed.add_field(
            name="🔄 Préstamos",
            value=(
                "Se define la cantidad de temporadas, el canon y, si corresponde, una opción de compra.\n"
                "El canon puede ser menor, pero no superar el **tope del 10% del valor del jugador por temporada**."
            ),
            inline=False,
        )
        embed.add_field(
            name="📜 Historial",
            value="Desde **HISTORIAL** podés consultar operaciones y movimientos realizados por tu club.",
            inline=False,
        )
        return _page_footer(embed, page)

    embed = discord.Embed(
        title="🏆 LIGA, RESULTADOS Y SOPORTE",
        description="La Liga y los resultados también se gestionan desde AJPA.",
        color=discord.Color.blurple(),
    )
    embed.add_field(
        name="🏆 LIGA",
        value=(
            "Desde **LIGA** podés consultar la tabla de posiciones y la tabla de goleadores.\n\n"
            "Los resultados se envían como captura en el canal oficial configurado."
        ),
        inline=False,
    )
    embed.add_field(
        name="📸 ¿Qué hace el bot con una captura?",
        value=(
            "✅ **Final claro:** lo registra y actualiza la Liga.\n"
            "🟡 **Parcial / 1er tiempo:** lo guarda como evidencia y **no modifica la tabla**.\n"
            "🧐 **Duda:** te pregunta si el marcador es final o parcial.\n"
            "📝 **Sin captura final:** puede informarse manualmente y debe confirmarlo el DT rival.\n"
            "⚠️ **Conflicto o lectura dudosa:** pasa a revisión de Staff.\n\n"
            "Una reacción **✅** en la captura significa que el resultado quedó oficialmente guardado."
        ),
        inline=False,
    )
    embed.add_field(
        name="🛠️ BUGS O MAL FUNCIONAMIENTO",
        value=(
            "Si detectás un **bug, comportamiento extraño, dato incorrecto o cualquier mal funcionamiento**, "
            "agradecemos que te comuniques con el **Staff**.\n\n"
            "Reportalo apenas lo detectes y, si es posible, adjuntá una captura explicando qué estabas haciendo. "
            "Así podemos atenderlo **de forma inmediata** y evitar que afecte a otros jugadores u operaciones."
        ),
        inline=False,
    )
    embed.add_field(
        name="💚 Gracias",
        value="Gracias por ayudar a mejorar **AJPA Transfer Market**.",
        inline=False,
    )
    return _page_footer(embed, page)


async def _team_selector(interaction: discord.Interaction):
    import team_assignment as teams

    try:
        embed = teams.welcome_embed(guild=interaction.guild)
    except TypeError:
        embed = teams.welcome_embed()
    try:
        view = teams.TeamChoiceView(guild=interaction.guild)
    except TypeError:
        view = teams.TeamChoiceView()

    await interaction.response.edit_message(
        content=None,
        embeds=[embed],
        view=view,
    )


async def _return_to_market(interaction: discord.Interaction, *, mark_seen: bool = False):
    token = _guild_context(interaction)
    try:
        if mark_seen:
            _mark_seen(interaction.user.id)

        if not APP.es_admin(interaction) and not APP.club_de(interaction.user.id):
            await _team_selector(interaction)
            return

        panel = APP.panel_embed(interaction.user.id)
        view_builder = getattr(APP, "manager_market_view_for", None) or getattr(APP, "market_view_for", None)
        view = view_builder(interaction) if callable(view_builder) else APP.MercadoView()
        await interaction.response.edit_message(
            content=None,
            embeds=[panel],
            view=view,
        )
    finally:
        _reset_guild_context(token)


class ManualNavButton(discord.ui.Button):
    def __init__(self, *, label: str, emoji: str, target_page: int, first_time: bool, row: int = 0):
        super().__init__(
            label=label,
            emoji=emoji,
            style=discord.ButtonStyle.secondary,
            row=row,
        )
        self.target_page = int(target_page)
        self.first_time = bool(first_time)

    async def callback(self, interaction: discord.Interaction):
        token = _guild_context(interaction)
        try:
            await interaction.response.edit_message(
                content=None,
                embeds=[manual_embed(self.target_page)],
                view=ManualView(self.target_page, first_time=self.first_time),
            )
        finally:
            _reset_guild_context(token)


class ManualReturnButton(discord.ui.Button):
    def __init__(self, *, first_time: bool, row: int = 1):
        super().__init__(
            label="ENTENDIDO • IR AL MERCADO" if first_time else "VOLVER AL MERCADO",
            emoji="✅" if first_time else "⬅️",
            style=discord.ButtonStyle.success if first_time else discord.ButtonStyle.primary,
            row=row,
        )
        self.first_time = bool(first_time)

    async def callback(self, interaction: discord.Interaction):
        await _return_to_market(interaction, mark_seen=self.first_time)


class ManualView(discord.ui.View):
    def __init__(self, page: int = 0, *, first_time: bool = False):
        super().__init__(timeout=300)
        page = max(0, min(int(page), LAST_PAGE))

        if page > 0:
            self.add_item(
                ManualNavButton(
                    label="ANTERIOR",
                    emoji="⬅️",
                    target_page=page - 1,
                    first_time=first_time,
                    row=0,
                )
            )
        if page < LAST_PAGE:
            self.add_item(
                ManualNavButton(
                    label="SIGUIENTE",
                    emoji="➡️",
                    target_page=page + 1,
                    first_time=first_time,
                    row=0,
                )
            )

        if first_time:
            if page == LAST_PAGE:
                self.add_item(ManualReturnButton(first_time=True, row=1))
        else:
            self.add_item(ManualReturnButton(first_time=False, row=1))


class ManualBotButton(discord.ui.Button):
    def __init__(self, row: int = 3):
        super().__init__(
            label="MANUAL BOT",
            emoji="📖",
            style=discord.ButtonStyle.secondary,
            row=row,
            custom_id="ajpa_player_manual_bot",
        )

    async def callback(self, interaction: discord.Interaction):
        token = _guild_context(interaction)
        try:
            await interaction.response.edit_message(
                content=None,
                embeds=[manual_embed(0)],
                view=ManualView(0, first_time=False),
            )
        finally:
            _reset_guild_context(token)


def _install_manual_button(runtime):
    BaseView = runtime.MercadoView
    if getattr(BaseView, "_ajpa_player_manual_button", False):
        return

    class ManualMarketView(BaseView):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            if not any(
                getattr(item, "custom_id", None) == "ajpa_player_manual_bot"
                for item in self.children
            ):
                self.add_item(ManualBotButton(row=3))

    ManualMarketView.__name__ = "MercadoView"
    ManualMarketView._ajpa_player_manual_button = True
    runtime.MercadoView = ManualMarketView


def apply_player_manual_patch(runtime, bot):
    global APP, BOT, ORIGINAL_MERCADO_CALLBACK
    APP = runtime
    BOT = bot
    if getattr(runtime, "_ajpa_player_manual_patch", False):
        return

    current_command = bot.tree.get_command("mercado")
    ORIGINAL_MERCADO_CALLBACK = getattr(current_command, "callback", None)
    if not callable(ORIGINAL_MERCADO_CALLBACK):
        raise RuntimeError("AJPA manual: no se encontró el callback final de /mercado")

    _install_manual_button(runtime)

    async def mercado_with_manual(interaction: discord.Interaction):
        token = _guild_context(interaction)
        try:
            if not APP.es_admin(interaction) and not _manual_seen(interaction.user.id):
                await interaction.response.send_message(
                    embed=manual_embed(0),
                    view=ManualView(0, first_time=True),
                    ephemeral=True,
                )
                return
            await ORIGINAL_MERCADO_CALLBACK(interaction)
        finally:
            _reset_guild_context(token)

    bot.tree.remove_command("mercado")
    bot.tree.command(
        name="mercado",
        description="Abre el panel principal de AJPA Transfer Market",
    )(mercado_with_manual)

    runtime.manual_bot_embed = manual_embed
    runtime.ManualBotView = ManualView
    runtime._ajpa_player_manual_patch = True
    print(
        "AJPA manual de jugador activo: primera entrada obligatoria + 4 páginas + botón MANUAL BOT"
    )


_original_apply_guild_isolation_patch = guild_isolation.apply_guild_isolation_patch


def _apply_guild_isolation_then_player_manual(runtime, bot):
    _original_apply_guild_isolation_patch(runtime, bot)
    apply_player_manual_patch(runtime, bot)


if not getattr(
    guild_isolation.apply_guild_isolation_patch,
    "_ajpa_player_manual_wrapped",
    False,
):
    _apply_guild_isolation_then_player_manual._ajpa_player_manual_wrapped = True
    guild_isolation.apply_guild_isolation_patch = _apply_guild_isolation_then_player_manual
