"""Persistent public/staff market-close channel delivery for AJAP.

Admins configure the destination by running /canal_movimientos in the desired
text channel. Every future market close posts a visible movement summary there
and attaches the full TXT report, while preserving the existing Staff DMs.
"""

import io

import discord
import market_close_report_patch as reports

APP = None


def ensure_schema():
    with APP.db() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS market_report_channels (
                guild_id INTEGER PRIMARY KEY,
                channel_id INTEGER NOT NULL,
                configured_by INTEGER,
                configured_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )


def set_report_channel(guild_id: int, channel_id: int, user_id: int):
    with APP.db() as conn:
        conn.execute(
            """
            INSERT INTO market_report_channels
            (guild_id, channel_id, configured_by, configured_at, updated_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            ON CONFLICT(guild_id) DO UPDATE SET
                channel_id = excluded.channel_id,
                configured_by = excluded.configured_by,
                updated_at = CURRENT_TIMESTAMP
            """,
            (guild_id, channel_id, user_id),
        )


def get_report_channel_id(guild_id: int):
    with APP.db() as conn:
        row = conn.execute(
            "SELECT channel_id FROM market_report_channels WHERE guild_id = ?",
            (guild_id,),
        ).fetchone()
    return int(row["channel_id"]) if row else None


def fmt_status(status: str) -> str:
    return {
        "PENDIENTE_ADMIN": "🟡 Pendiente admin",
        "APROBADA": "🟢 Aprobada",
        "APLICADA": "✅ Aplicada",
        "RECHAZADA_ADMIN": "⛔ Rechazada admin",
    }.get(status or "", status or "—")


def movement_lines(rows):
    lines = []
    for row in rows:
        op_type = row["operation_type"] or "TRANSFERENCIA"
        amount = row["amount"] or "$0"
        line = (
            f"**#{row['id']} • {row['player']}**\n"
            f"⬅️ {row['seller']}\n"
            f"➡️ {row['buyer']}\n"
            f"🔄 {op_type} • 💰 {amount} • {fmt_status(row['status'])}"
        )
        lines.append(line)
    return lines


def chunk_lines(lines, max_chars=3600):
    chunks = []
    current = []
    size = 0
    for line in lines:
        addition = len(line) + 2
        if current and size + addition > max_chars:
            chunks.append("\n\n".join(current))
            current = []
            size = 0
        current.append(line)
        size += addition
    if current:
        chunks.append("\n\n".join(current))
    return chunks


async def resolve_channel(interaction: discord.Interaction):
    if not interaction.guild:
        return None
    channel_id = get_report_channel_id(interaction.guild.id)
    if not channel_id:
        return None
    channel = interaction.guild.get_channel(channel_id)
    if channel is None:
        try:
            channel = await APP.bot.fetch_channel(channel_id)
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            return None
    return channel if hasattr(channel, "send") else None


async def post_close_report(interaction, text, filename):
    channel = await resolve_channel(interaction)
    if channel is None:
        return False

    cycle = reports.latest_closed_cycle(APP)
    if not cycle:
        return False
    rows = reports.cycle_rows(APP, cycle)
    with APP.db() as conn:
        season = (
            conn.execute("SELECT name FROM seasons WHERE id = ?", (cycle["season_id"],)).fetchone()
            if cycle["season_id"]
            else None
        )
    season_name = season["name"] if season else "Sin temporada"

    summary = discord.Embed(
        title="🔒 MERCADO CERRADO • MOVIMIENTOS",
        description=(
            f"**{season_name}** • Ventana **#{cycle['id']}**\n"
            f"📋 Movimientos registrados: **{len(rows)}**\n\n"
            "Debajo queda el detalle de todos los movimientos de esta ventana. "
            "El TXT adjunto sirve como checklist completo para Staff/PES."
        ),
    )

    try:
        await channel.send(
            embed=summary,
            file=discord.File(io.BytesIO(text.encode("utf-8-sig")), filename=filename),
        )
        lines = movement_lines(rows)
        if not lines:
            await channel.send("📭 No hubo movimientos registrados en esta ventana de mercado.")
        else:
            chunks = chunk_lines(lines)
            for index, chunk in enumerate(chunks, 1):
                title = "📑 Detalle de movimientos"
                if len(chunks) > 1:
                    title += f" • {index}/{len(chunks)}"
                await channel.send(embed=discord.Embed(title=title, description=chunk))
        return True
    except (discord.Forbidden, discord.HTTPException) as exc:
        print(f"WARNING AJAP: no se pudo publicar cierre en canal configurado: {exc}")
        return False


def apply_market_channel_report_patch(main_module, bot):
    global APP
    APP = main_module
    if getattr(main_module, "_ajap_market_channel_report_patch", False):
        return

    ensure_schema()

    base_deliver = reports.deliver

    async def deliver_with_channel(runtime, interaction, text, filename):
        delivered, detected, failures = await base_deliver(runtime, interaction, text, filename)
        channel_ok = await post_close_report(interaction, text, filename)
        print(
            "AJAP cierre de mercado: "
            f"Staff DM {delivered}/{detected} • canal={'OK' if channel_ok else 'NO CONFIGURADO/FAILED'}"
        )
        return delivered, detected, failures

    reports.deliver = deliver_with_channel

    if bot.tree.get_command("canal_movimientos") is None:
        @bot.tree.command(
            name="canal_movimientos",
            description="Usa este canal para recibir todos los movimientos al cerrar el mercado",
        )
        async def canal_movimientos(interaction: discord.Interaction):
            if not APP.es_admin(interaction):
                await interaction.response.send_message("⛔ Solo administradores.", ephemeral=True)
                return
            if not interaction.guild or not interaction.channel:
                await interaction.response.send_message(
                    "⚠️ Este comando debe usarse dentro de un canal del servidor.",
                    ephemeral=True,
                )
                return
            if not isinstance(interaction.channel, discord.TextChannel):
                await interaction.response.send_message(
                    "⚠️ Elegí un canal de texto normal para los reportes del mercado.",
                    ephemeral=True,
                )
                return

            set_report_channel(interaction.guild.id, interaction.channel.id, interaction.user.id)
            await interaction.response.send_message(
                f"✅ **Canal de movimientos configurado:** {interaction.channel.mention}\n"
                "A partir del próximo cierre, el bot publicará acá todos los movimientos del mercado y adjuntará el TXT completo.",
                ephemeral=True,
            )

    main_module.market_report_channel_id = get_report_channel_id
    main_module._ajap_market_channel_report_patch = True
    print("Canal persistente de movimientos activo: /canal_movimientos + publicación automática al cierre")
