"""Avisos automáticos para clausulazos aprobados.

- DM al dueño del club que pierde al jugador.
- Anuncio público en un canal visible por toda la liga.

El canal público se resuelve en este orden:
1) CLAUSULAZO_CHANNEL_ID (si está configurado),
2) un canal con nombre de mercado/fichajes,
3) el canal del sistema,
4) el primer canal de texto visible por @everyone donde el bot pueda escribir.
"""

import os

import clausulazo_patch as clauses


PREFERRED_CHANNEL_NAMES = (
    "mercado-de-pases",
    "mercado",
    "fichajes",
    "transferencias",
    "transfer-market",
    "mercado-ajap",
    "anuncios-mercado",
    "anuncios",
)


def _money(value):
    return clauses.fmt_money(value)


def _public_message(req):
    return (
        "🚨 **¡CLAUSULAZO!** 🚨\n\n"
        f"💥 **{req['buyer_club']}** ejecutó la cláusula de rescisión de **{req['player']}**.\n\n"
        f"⬅️ **Club anterior:** {req['seller_club']}\n"
        f"➡️ **Nuevo club:** {req['buyer_club']}\n\n"
        f"💰 **Cláusula:** {_money(req['amount'])}\n\n"
        "✅ Operación aprobada por el Comité."
    )


def _seller_message(req):
    return (
        "🚨 **¡CLAUSULAZO!** 🚨\n\n"
        f"**{req['buyer_club']}** ejecutó la cláusula de rescisión de **{req['player']}**.\n\n"
        f"✅ El Comité aprobó la operación y **{req['player']} se marcha de tu club**.\n\n"
        f"💰 **Ingreso:** +{_money(req['amount'])}"
    )


async def _member_from_id(guild, user_id):
    if not guild or not user_id:
        return None
    member = guild.get_member(int(user_id))
    if member is not None:
        return member
    try:
        return await guild.fetch_member(int(user_id))
    except Exception:
        return None


def _channel_is_public_and_writable(guild, channel):
    if not guild or channel is None or not hasattr(channel, "send"):
        return False
    try:
        everyone = channel.permissions_for(guild.default_role)
        if not everyone.view_channel:
            return False
        me = guild.me
        if me is not None:
            mine = channel.permissions_for(me)
            if not mine.view_channel or not mine.send_messages:
                return False
    except Exception:
        return False
    return True


def _announce_channel(guild):
    if not guild:
        return None

    configured = (os.getenv("CLAUSULAZO_CHANNEL_ID") or "").strip()
    if configured.isdigit():
        channel = guild.get_channel(int(configured))
        if _channel_is_public_and_writable(guild, channel):
            return channel

    channels = list(getattr(guild, "text_channels", []) or [])
    by_name = {(channel.name or "").strip().casefold(): channel for channel in channels}

    for wanted in PREFERRED_CHANNEL_NAMES:
        channel = by_name.get(wanted.casefold())
        if _channel_is_public_and_writable(guild, channel):
            return channel

    for channel in channels:
        name = (channel.name or "").strip().casefold()
        if any(word in name for word in ("mercado", "fichaje", "transfer")):
            if _channel_is_public_and_writable(guild, channel):
                return channel

    system_channel = getattr(guild, "system_channel", None)
    if _channel_is_public_and_writable(guild, system_channel):
        return system_channel

    for channel in channels:
        if _channel_is_public_and_writable(guild, channel):
            return channel

    return None


async def announce_public(guild, req):
    channel = _announce_channel(guild)
    if channel is None:
        print(
            "WARNING AJAP: clausulazo aprobado sin canal público disponible "
            f"(request #{req['id']})"
        )
        return False
    try:
        await channel.send(_public_message(req))
        print(
            "AJAP clausulazo anunciado: "
            f"#{req['id']} {req['player']} {req['seller_club']} -> {req['buyer_club']} "
            f"en #{getattr(channel, 'name', channel.id)}"
        )
        return True
    except Exception as exc:
        print(f"WARNING AJAP: no se pudo anunciar clausulazo #{req['id']}: {exc}")
        return False


async def notify_seller(guild, req):
    member = await _member_from_id(guild, req["seller_user_id"])
    if member is None:
        print(
            "WARNING AJAP: no se encontró al dueño del club vendedor para DM "
            f"(clausulazo #{req['id']}, {req['seller_club']})"
        )
        return False
    try:
        await member.send(_seller_message(req))
        return True
    except Exception as exc:
        print(
            "WARNING AJAP: no se pudo entregar DM de clausulazo "
            f"#{req['id']} a {req['seller_club']}: {exc}"
        )
        return False


def apply_clausulazo_announce_patch(runtime):
    """Reemplaza los avisos del módulo de clausulazos sin tocar su lógica financiera."""
    if getattr(clauses, "_announce_patch_active", False):
        return

    original_notify_buyer = clauses.notify_buyer

    async def notify_buyer_and_announce(guild, req, approved):
        # El anuncio público no depende de que el comprador tenga los DMs abiertos.
        buyer_delivered = await original_notify_buyer(guild, req, approved)
        if approved:
            await announce_public(guild, req)
        return buyer_delivered

    clauses.notify_seller = notify_seller
    clauses.notify_buyer = notify_buyer_and_announce
    clauses._announce_patch_active = True

    print("AJAP clausulazo avisos activos: DM vendedor + anuncio público")
