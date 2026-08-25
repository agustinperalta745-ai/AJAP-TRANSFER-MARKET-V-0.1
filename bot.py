import os

import discord
from discord import app_commands
from discord.ext import commands

TOKEN = os.getenv("DISCORD_TOKEN")

if not TOKEN:
    raise RuntimeError("Falta la variable de entorno DISCORD_TOKEN")

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)


@bot.event
async def on_ready():
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


@bot.tree.command(name="mercado", description="Muestra el estado inicial del mercado de pases")
async def mercado(interaction: discord.Interaction):
    embed = discord.Embed(
        title="⚽ AJAP Transfer Market v0.1",
        description="El mercado de pases está funcionando.",
    )
    embed.add_field(name="Estado", value="🟢 Online", inline=True)
    embed.add_field(name="Versión", value="0.1", inline=True)
    embed.set_footer(text="Prototipo inicial")

    await interaction.response.send_message(embed=embed)


bot.run(TOKEN)
