"""Confirma resultados de Liga únicamente después de persistirlos.

No usa reacciones de "procesando" ni de error. El único ✅ significa que el
mensaje ya fue guardado en la DB de Liga y, si contiene resultado, que ese
partido ya participa del cálculo que ve el menú 🏆 LIGA.
"""

from __future__ import annotations

import os

import league_automation_patch as league


def _stored_state(runtime, message_id: int, guild_id: int):
    """Verificación posterior al commit: devuelve (partido, goleadores)."""
    conn = league.db(runtime, int(guild_id))
    try:
        match = conn.execute(
            "SELECT 1 FROM league_matches WHERE source_message_id = ? LIMIT 1",
            (int(message_id),),
        ).fetchone()
        scorers = conn.execute(
            "SELECT 1 FROM league_goal_events WHERE source_message_id = ? LIMIT 1",
            (int(message_id),),
        ).fetchone()
        # Forzar la misma lectura/cálculo que usa el menú. Si esto falla, no se
        # confirma el resultado aunque el INSERT haya ocurrido.
        if match:
            league.standings(conn)
        return bool(match), bool(scorers)
    finally:
        conn.close()


async def confirmed_handle(runtime, bot, message):
    if not message.guild or message.author.bot or not message.attachments:
        return

    conn = league.db(runtime, message.guild.id)
    try:
        cfg = conn.execute(
            "SELECT * FROM league_config WHERE guild_id = ?",
            (message.guild.id,),
        ).fetchone()
    finally:
        conn.close()

    if (
        not cfg
        or not cfg["intake_channel_id"]
        or message.channel.id != int(cfg["intake_channel_id"])
    ):
        return

    if not os.getenv("OPENAI_API_KEY"):
        await message.reply(
            "⚠️ El lector automático todavía no tiene configurada `OPENAI_API_KEY`.",
            mention_author=False,
        )
        return

    # Si ESTE mismo mensaje ya fue persistido antes (por ejemplo tras reinicio),
    # el ✅ sí es válido: la base confirma que ya forma parte de Liga.
    stored_match, stored_scorers = _stored_state(
        runtime, message.id, message.guild.id
    )
    if stored_match or stored_scorers:
        try:
            await message.add_reaction("✅")
        except Exception:
            pass
        return

    images, hashes = await league.new_images(runtime, message)
    if not images:
        # No marcar como cargado: puede ser una imagen duplicada de otro mensaje,
        # pero este mensaje no tiene una carga propia confirmada.
        await message.reply(
            "ℹ️ Esta captura ya fue procesada anteriormente o no contiene una imagen válida.",
            mention_author=False,
        )
        return

    try:
        payload = await league.analyze(images)
        try:
            confidence = float(payload.get("confidence") or 0.0)
        except (TypeError, ValueError):
            confidence = 0.0

        if confidence < league.MIN_CONF:
            await message.reply(
                "⚠️ No pude leer esta captura con suficiente seguridad. No cargué nada; mandá una foto más clara.",
                mention_author=False,
            )
            return

        score_ok, scorers_ok, scorers_count = league.store(
            runtime, message, payload, hashes
        )
        if not score_ok and not scorers_ok:
            await message.reply(
                "⚠️ No encontré un resultado o goleadores válidos. No se modificó la Liga.",
                mention_author=False,
            )
            return

        # Segunda lectura DESPUÉS del commit. El ✅ solo se coloca si los datos
        # que acabamos de cargar realmente existen y el cálculo de tabla responde.
        persisted_match, persisted_scorers = _stored_state(
            runtime, message.id, message.guild.id
        )
        if score_ok and not persisted_match:
            raise RuntimeError("El resultado no quedó persistido después del commit")
        if scorers_ok and not persisted_scorers:
            raise RuntimeError("Los goleadores no quedaron persistidos después del commit")

        # Recién acá se confirma visualmente el mensaje original.
        await message.add_reaction("✅")

        bits = []
        if score_ok:
            score = league.parsed_score(payload)
            bits.append(
                f"resultado **{score[0]} {score[2]}–{score[3]} {score[1]}**"
            )
        if scorers_ok:
            bits.append(f"**{scorers_count} goleador(es)**")
        await message.reply(
            "✅ Cargado y reflejado en Liga: " + " + ".join(bits) + ".",
            mention_author=False,
        )
    except Exception as exc:
        print(f"AJAP League confirmación error mensaje={message.id}: {exc}")
        await message.reply(
            "❌ No pude confirmar la carga. El mensaje no recibió ✅ porque el resultado no quedó verificado en Liga.",
            mention_author=False,
        )


# apply_league_automation_patch crea un listener que resuelve `handle` desde el
# módulo en tiempo de ejecución, así que reemplazarlo acá afecta el listener final
# sin registrar uno duplicado.
league.handle = confirmed_handle
print("AJAP Liga: ✅ solo después de persistencia y cálculo verificados")
