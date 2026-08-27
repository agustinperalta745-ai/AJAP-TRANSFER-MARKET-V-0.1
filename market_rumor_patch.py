"""Rumores de prensa para cada oferta creada en AJAP Transfer Market.

Cada oferta válida mantiene sus avisos privados/operativos habituales y, además,
genera una tarjeta breve en /canal_resumen_mercado. El rumor solo revela el club
interesado y el jugador: no expone monto, condiciones ni jugadores ofrecidos.
"""

from __future__ import annotations

import discord

import offer_notifications_patch as offer_notifications
import public_market_summary_patch as public_summary


def _rumor_embed(offer):
    buyer = str(offer["from_club"] or "Club interesado")
    player = str(offer["player"] or "Jugador")
    seller = str(offer["to_club"] or "").strip()

    embed = discord.Embed(
        title="🗞️ RUMOR DE MERCADO",
        description=(
            f"👀 **{buyer}** está detrás de **{player}**.\n\n"
            "Fuentes del mercado indican que el club ya habría realizado "
            "movimientos para intentar incorporarlo."
        ),
        color=discord.Color.gold(),
    )

    # Si el runtime del resumen ya está listo, mostramos la ficha corta con OVR/posición.
    try:
        if public_summary.APP is not None:
            embed.add_field(
                name="⚽ Jugador seguido",
                value=public_summary._player_line(player),
                inline=False,
            )
    except Exception:
        pass

    if seller:
        embed.add_field(name="🏟️ Club actual", value=seller, inline=True)
    embed.add_field(name="🔎 Club interesado", value=buyer, inline=True)
    embed.set_footer(
        text="AJAP Transfer Market • Rumor de prensa • Operación no confirmada"
    )
    return embed


async def publish_offer_rumor(interaction, offer):
    guild = getattr(interaction, "guild", None)
    if guild is None or public_summary.APP is None:
        return False

    offer_id = int(offer["id"])
    if public_summary._was_announced(guild.id, "OFFER_RUMOR", offer_id):
        return True

    channel = await public_summary._resolve_public_channel(guild)
    if channel is None:
        return False

    try:
        msg = await channel.send(
            embed=_rumor_embed(offer),
            allowed_mentions=discord.AllowedMentions.none(),
        )
        public_summary._remember_announcement(
            guild.id,
            "OFFER_RUMOR",
            offer_id,
            channel.id,
            msg.id,
        )
        return True
    except (discord.Forbidden, discord.HTTPException) as exc:
        print(f"WARNING AJAP: rumor de oferta #{offer_id} no publicado: {exc}")
        return False


def _install_offer_rumor_hook():
    current = offer_notifications._send_public_notice
    if getattr(current, "_ajap_market_rumor_hook", False):
        return False

    async def notice_and_rumor(interaction, offer):
        result = await current(interaction, offer)
        try:
            await publish_offer_rumor(interaction, offer)
        except Exception as exc:
            # Un fallo del feed público nunca debe invalidar una oferta real.
            print(f"WARNING AJAP: rumor de oferta #{offer['id']} falló: {exc}")
        return result

    notice_and_rumor._ajap_market_rumor_hook = True
    offer_notifications._send_public_notice = notice_and_rumor
    return True


installed = _install_offer_rumor_hook()
print(
    "AJAP rumores de mercado activos: cada oferta genera rumor público "
    f"({'OK' if installed else 'YA INSTALADO'})"
)
