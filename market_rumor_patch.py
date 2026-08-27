"""Rumores de prensa para cada oferta creada en AJAP Transfer Market.

Cada oferta valida mantiene sus avisos privados/operativos habituales y, ademas,
genera una tarjeta breve en el canal publico del mercado. El rumor solo revela
el club interesado y el jugador: no expone monto, condiciones ni jugadores
ofrecidos.

Esta capa es deliberadamente defensiva: primero usa el canal configurado en la
DB del guild y, si por cualquier motivo esa configuracion no puede resolverse,
busca un canal llamado #resumen-mercado en el mismo servidor. Si Discord permite
mensajes pero no embeds, publica una version de texto para que el movimiento no
quede invisible. Al reconectar el bot tambien recupera ofertas pendientes que
hayan quedado sin rumor por una version anterior.
"""

from __future__ import annotations

from types import SimpleNamespace

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


def _rumor_text(offer):
    buyer = str(offer["from_club"] or "Club interesado")
    player = str(offer["player"] or "Jugador")
    seller = str(offer["to_club"] or "").strip()
    current = f"\n🏟️ Club actual: **{seller}**" if seller else ""
    return (
        "🗞️ **RUMOR DE MERCADO**\n"
        f"👀 **{buyer}** esta detras de **{player}**.\n"
        "Fuentes del mercado indican que el club ya habria realizado movimientos "
        f"para intentar incorporarlo.{current}\n"
        f"🔎 Club interesado: **{buyer}**"
    )


def _normalized_channel_name(name: str) -> str:
    return "".join(ch for ch in str(name or "").casefold() if ch.isalnum())


async def _resolve_summary_channel(guild):
    if guild is None:
        return None, "NO_GUILD"

    if public_summary.APP is not None:
        try:
            configured = await public_summary._resolve_public_channel(guild)
            if configured is not None:
                return configured, "CONFIGURED"
        except Exception as exc:
            print(f"WARNING AJAP: no pude resolver canal publico configurado: {exc}")

    accepted = {"resumenmercado", "resumendemercado", "mercadoresumen"}
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


async def _send_rumor_message(channel, offer):
    try:
        msg = await channel.send(
            embed=_rumor_embed(offer),
            allowed_mentions=discord.AllowedMentions.none(),
        )
        return msg, "EMBED"
    except (discord.Forbidden, discord.HTTPException) as embed_exc:
        print(
            f"WARNING AJAP: embed rumor oferta #{offer['id']} fallo en "
            f"channel={getattr(channel, 'id', None)}: {embed_exc}; intento texto"
        )
        try:
            msg = await channel.send(
                content=_rumor_text(offer),
                allowed_mentions=discord.AllowedMentions.none(),
            )
            return msg, "TEXT_FALLBACK"
        except (discord.Forbidden, discord.HTTPException) as text_exc:
            print(
                f"WARNING AJAP: texto rumor oferta #{offer['id']} tambien fallo en "
                f"channel={getattr(channel, 'id', None)}: {text_exc}"
            )
            return None, "SEND_FAILED"


async def publish_offer_rumor(interaction, offer):
    guild = getattr(interaction, "guild", None)
    if guild is None:
        print(f"WARNING AJAP: rumor oferta #{offer['id']} sin guild")
        return False

    offer_id = int(offer["id"])

    if public_summary.APP is not None:
        try:
            if public_summary._was_announced(guild.id, "OFFER_RUMOR", offer_id):
                print(f"AJAP rumor oferta #{offer_id}: YA_PUBLICADO")
                return True
        except Exception as exc:
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

    msg, mode = await _send_rumor_message(channel, offer)
    if msg is None:
        return False

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
        f"channel={channel.id} source={source} mode={mode}"
    )
    return True


async def _backfill_pending_rumors():
    """On every ready/reconnect, publish pending offers missing from the public feed."""
    app = public_summary.APP
    if app is None or getattr(app, "bot", None) is None:
        print("WARNING AJAP: backfill rumores omitido; runtime publico aun no listo")
        return

    total = 0
    for guild in list(getattr(app.bot, "guilds", [])):
        conn = None
        try:
            conn = public_summary._conn_for_guild(guild.id)
            rows = conn.execute(
                "SELECT * FROM offers WHERE status = 'PENDIENTE' ORDER BY id"
            ).fetchall()
        except Exception as exc:
            print(f"WARNING AJAP: backfill rumores guild={guild.id} fallo lectura: {exc}")
            rows = []
        finally:
            if conn is not None:
                conn.close()

        interaction = SimpleNamespace(guild=guild)
        for offer in rows:
            try:
                already = public_summary._was_announced(
                    guild.id, "OFFER_RUMOR", int(offer["id"])
                )
                if already:
                    continue
                if await publish_offer_rumor(interaction, offer):
                    total += 1
            except Exception as exc:
                print(
                    f"WARNING AJAP: backfill rumor oferta #{offer['id']} "
                    f"guild={guild.id} fallo: {exc}"
                )

    print(f"AJAP backfill rumores: {total} oferta(s) pendiente(s) recuperadas")


def install_pending_offer_backfill(bot):
    if getattr(bot, "_ajap_market_rumor_backfill", False):
        return False
    bot.add_listener(_backfill_pending_rumors, "on_ready")
    bot._ajap_market_rumor_backfill = True
    return True


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
