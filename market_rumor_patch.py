"""Rumores de prensa para cada oferta creada en AJAP Transfer Market.

Cada oferta valida mantiene sus avisos privados/operativos habituales y, ademas,
genera una tarjeta breve en el canal publico del mercado. El rumor solo revela
el club interesado y el jugador: no expone monto, condiciones ni jugadores
ofrecidos.

Esta capa es deliberadamente defensiva: primero usa el canal configurado en la
DB del guild y, si por cualquier motivo esa configuracion no puede resolverse,
busca un canal llamado #resumen-mercado en el mismo servidor. Asi un fallo de
orden de parches o de configuracion nunca vuelve invisible una oferta valida.
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
            f"👀 **{buyer}** esta detras de **{player}**.\n\n"
            "Fuentes del mercado indican que el club ya habria realizado "
            "movimientos para intentar incorporarlo."
        ),
        color=discord.Color.gold(),
    )

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
        text="AJAP Transfer Market • Rumor de prensa • Operacion no confirmada"
    )
    return embed


def _normalized_channel_name(name: str) -> str:
    return "".join(ch for ch in str(name or "").casefold() if ch.isalnum())


async def _resolve_summary_channel(guild):
    """Resolve configured channel first; fall back to the canonical channel name."""
    if guild is None:
        return None, "NO_GUILD"

    if public_summary.APP is not None:
        try:
            configured = await public_summary._resolve_public_channel(guild)
            if configured is not None:
                return configured, "CONFIGURED"
        except Exception as exc:
            print(f"WARNING AJAP: no pude resolver canal publico configurado: {exc}")

    accepted = {
        "resumenmercado",
        "resumendemercado",
        "mercadoresumen",
    }
    me = getattr(guild, "me", None)
    for channel in getattr(guild, "text_channels", []):
        if _normalized_channel_name(getattr(channel, "name", "")) not in accepted:
            continue
        if me is not None:
            try:
                perms = channel.permissions_for(me)
                if not perms.view_channel or not perms.send_messages:
                    continue
            except Exception:
                pass
        return channel, "NAME_FALLBACK"

    return None, "NOT_FOUND"


async def publish_offer_rumor(interaction, offer):
    guild = getattr(interaction, "guild", None)
    if guild is None:
        print(f"WARNING AJAP: rumor oferta #{offer['id']} sin guild")
        return False

    offer_id = int(offer["id"])

    # Dedupe only when the public-summary runtime is already initialized.
    if public_summary.APP is not None:
        try:
            if public_summary._was_announced(guild.id, "OFFER_RUMOR", offer_id):
                print(f"AJAP rumor oferta #{offer_id}: YA_PUBLICADO")
                return True
        except Exception as exc:
            # Do not block the actual Discord send because the audit table failed.
            print(f"WARNING AJAP: dedupe rumor oferta #{offer_id} fallo: {exc}")

    channel, source = await _resolve_summary_channel(guild)
    if channel is None:
        configured_id = None
        if public_summary.APP is not None:
            try:
                configured_id = public_summary.get_public_channel_id(guild.id)
            except Exception:
                pass
        names = ", ".join(
            f"#{getattr(ch, 'name', '?')}" for ch in getattr(guild, "text_channels", [])
        )
        print(
            f"WARNING AJAP: rumor oferta #{offer_id} SIN_DESTINO "
            f"guild={guild.id} configured_id={configured_id} canales=[{names}]"
        )
        return False

    try:
        msg = await channel.send(
            embed=_rumor_embed(offer),
            allowed_mentions=discord.AllowedMentions.none(),
        )

        if public_summary.APP is not None:
            try:
                public_summary._remember_announcement(
                    guild.id,
                    "OFFER_RUMOR",
                    offer_id,
                    channel.id,
                    msg.id,
                )
            except Exception as exc:
                print(
                    f"WARNING AJAP: rumor oferta #{offer_id} enviado pero no auditado: {exc}"
                )

        print(
            f"AJAP rumor oferta #{offer_id}: SENT guild={guild.id} "
            f"channel={channel.id} source={source}"
        )
        return True
    except (discord.Forbidden, discord.HTTPException) as exc:
        print(
            f"WARNING AJAP: rumor oferta #{offer_id} SEND_FAILED "
            f"channel={getattr(channel, 'id', None)} source={source}: {exc}"
        )
        return False


def _install_offer_rumor_hook():
    current = offer_notifications._send_public_notice
    if getattr(current, "_ajap_market_rumor_hook", False):
        return False

    async def notice_and_rumor(interaction, offer):
        result = await current(interaction, offer)
        try:
            rumor_ok = await publish_offer_rumor(interaction, offer)
            print(
                f"AJAP rumor hook oferta #{offer['id']}: "
                f"{'OK' if rumor_ok else 'FAILED'}"
            )
        except Exception as exc:
            # Un fallo del feed publico nunca debe invalidar una oferta real.
            print(f"WARNING AJAP: rumor de oferta #{offer['id']} fallo: {exc}")
        return result

    notice_and_rumor._ajap_market_rumor_hook = True
    offer_notifications._send_public_notice = notice_and_rumor
    return True


installed = _install_offer_rumor_hook()
print(
    "AJAP rumores de mercado activos: cada oferta genera rumor publico "
    f"({'OK' if installed else 'YA INSTALADO'})"
)
