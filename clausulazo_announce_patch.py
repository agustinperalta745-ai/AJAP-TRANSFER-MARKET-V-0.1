"""Avisos automáticos para clausulazos aprobados.

- DM al dueño del club que pierde al jugador.
- Anuncio público en un canal visible por toda la liga.

El canal público se resuelve en este orden:
1) CLAUSULAZO_CHANNEL_ID (si está configurado),
2) un canal con nombre de mercado/fichajes,
3) el canal del sistema,
4) el primer canal de texto visible por @everyone donde el bot pueda escribir.
"""

import inspect

import clausulazo_patch as clauses


def _money(value):
    return clauses.fmt_money(value)


def _public_message(req):
    return (
        "📻 **RADIO PASILLO**\n\n"
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


async def _announce_channel(guild):
    """Usa el mismo destino oficial de Radio Pasillo que el resto de AJPA."""
    if guild is None:
        return None
    import radio_pasillo_feature_ads_patch as radio

    resolved = radio._resolve_radio_channel(guild)
    if inspect.isawaitable(resolved):
        resolved = await resolved
    return resolved


async def announce_public(guild, req):
    channel = await _announce_channel(guild)
    if channel is None:
        print(
            "WARNING AJAP: clausulazo aprobado sin canal Radio Pasillo disponible "
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
        buyer_delivered = False
        try:
            buyer_delivered = await original_notify_buyer(guild, req, approved)
        except Exception as exc:
            print(
                "WARNING AJAP: fallo DM comprador de clausulazo "
                f"#{req['id']}: {type(exc).__name__}: {exc}"
            )

        if approved:
            try:
                await announce_public(guild, req)
            except Exception as exc:
                print(
                    "WARNING AJAP: fallo inesperado publicando clausulazo "
                    f"#{req['id']}: {type(exc).__name__}: {exc}"
                )
        return buyer_delivered

    clauses.notify_seller = notify_seller
    clauses.notify_buyer = notify_buyer_and_announce
    clauses._announce_patch_active = True

    print("AJAP clausulazo avisos activos: DM vendedor + anuncio público")
