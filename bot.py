import os

import discord
from discord import app_commands
from discord.ext import commands

TOKEN = os.getenv("DISCORD_TOKEN")

if not TOKEN:
    raise RuntimeError("Falta la variable de entorno DISCORD_TOKEN")

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)


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
        embed = discord.Embed(
            title="🔎 Buscar jugadores",
            description=(
                "Acá vas a poder filtrar futbolistas disponibles en el mercado.\n\n"
                "**Próximamente:** posición, media, edad, club y valor."
            ),
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(
        label="Publicar jugador",
        emoji="📤",
        style=discord.ButtonStyle.success,
        custom_id="mercado_publicar",
    )
    async def publicar_jugador(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        embed = discord.Embed(
            title="📤 Publicar jugador",
            description=(
                "Desde acá un club podrá poner un jugador en el mercado.\n\n"
                "**Próximamente:** nombre, posición, precio pedido y tipo de operación."
            ),
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(
        label="Transferibles",
        emoji="📋",
        style=discord.ButtonStyle.secondary,
        custom_id="mercado_transferibles",
    )
    async def transferibles(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        embed = discord.Embed(
            title="📋 Jugadores transferibles",
            description=(
                "Todavía no hay jugadores publicados en esta versión de prueba.\n\n"
                "Cuando carguemos planteles y publicaciones, aparecerán acá."
            ),
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(
        label="Mis ofertas",
        emoji="💰",
        style=discord.ButtonStyle.danger,
        custom_id="mercado_ofertas",
    )
    async def ofertas(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        embed = discord.Embed(
            title="💰 Mis ofertas",
            description=(
                "Acá cada club podrá revisar las ofertas enviadas y recibidas.\n\n"
                "**Próximamente:** aceptar, rechazar o contraofertar desde Discord."
            ),
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


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


@bot.tree.command(name="mercado", description="Abre AJAP Transfer Market")
async def mercado(interaction: discord.Interaction):
    embed = discord.Embed(
        title="⚽ AJAP TRANSFER MARKET v0.1",
        description=(
            "**Centro de operaciones del mercado de fichajes**\n\n"
            "Desde este panel los clubes podrán buscar jugadores, publicar transferibles "
            "y gestionar negociaciones.\n\n"
            "Seleccioná una opción para continuar."
        ),
    )
    embed.add_field(name="🟢 Mercado", value="ABIERTO", inline=True)
    embed.add_field(name="⚙️ Sistema", value="Beta v0.1", inline=True)
    embed.add_field(name="🤝 Negociaciones", value="Habilitadas en pruebas", inline=False)
    embed.set_footer(text="AJAP Transfer Market • PES 6")

    await interaction.response.send_message(embed=embed, view=MercadoView())


bot.run(TOKEN)
