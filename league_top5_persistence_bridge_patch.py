"""Bridge definitivo para Radio Pasillo Top 5.

El primer parche comparaba la tabla alrededor del listener de mensajes. Eso cubre
los resultados finales que se persisten durante el mismo mensaje, pero no los
resultados que pasan a ser oficiales DESPUÉS mediante un botón (final/parcial,
reanudación, confirmación rival) o mediante la tarjeta de revisión manual de
Staff.

Esta capa se carga al final y observa las funciones que realmente persisten esos
resultados. Guarda el mismo evento Top 5 y dispara la misma publicación, sin
cambiar resultados, standings ni reglas de validación.
"""

from __future__ import annotations

import asyncio

import league_automation_patch as league
import league_result_evidence_patch as evidence
import league_result_feedback_patch as feedback
import league_top5_overtake_radio_patch as top5
import league_validation_admin_review_patch as strict


_PUBLISH_LOCKS: dict[tuple[int, int], asyncio.Lock] = {}
_BASE_PUBLISH_EVENT = top5._publish_event
_BASE_EVIDENCE_PERSIST = evidence._persist_official
_BASE_LEAGUE_STORE = league.store
_BASE_MANUAL_SUBMIT = strict.LeagueManualScoreModal.on_submit


def _bot():
    return getattr(evidence, "BOT", None) or getattr(feedback, "BOT", None)


def _guild(bot, guild_id: int):
    if bot is None:
        return None
    try:
        return bot.get_guild(int(guild_id))
    except Exception:
        return None


async def _publish_event_locked(runtime, bot, guild, source_message_id: int) -> bool:
    """Serializa por resultado para que dos capas nunca publiquen dos veces."""
    key = (int(guild.id), int(source_message_id))
    lock = _PUBLISH_LOCKS.get(key)
    if lock is None:
        lock = asyncio.Lock()
        _PUBLISH_LOCKS[key] = lock
    try:
        async with lock:
            return await _BASE_PUBLISH_EVENT(runtime, bot, guild, int(source_message_id))
    finally:
        # No hace falta conservar locks de eventos que ya terminaron.
        current = _PUBLISH_LOCKS.get(key)
        if current is lock and not lock.locked():
            _PUBLISH_LOCKS.pop(key, None)


# El wrapper original de Top 5 y los reintentos pasan también por el candado.
top5._publish_event = _publish_event_locked


def _queue_if_overtake(runtime, guild_id: int, source_message_id: int, before) -> None:
    if before is None:
        return
    try:
        after = top5._top5(runtime, int(guild_id))
        moves = top5._detect_overtakes(before, after)
        if not moves:
            return
        top5._store_event(
            runtime,
            int(guild_id),
            int(source_message_id),
            before,
            after,
            moves,
        )

        bot = _bot()
        guild = _guild(bot, int(guild_id))
        if bot is None or guild is None:
            # El evento queda pending y el on_ready de Top 5 lo reintentará.
            return
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return
        loop.create_task(
            top5._publish_event(runtime, bot, guild, int(source_message_id)),
            name=f"ajap-top5-radio-{int(source_message_id)}",
        )
    except Exception as exc:
        # Radio Pasillo jamás puede romper la persistencia oficial del partido.
        print(
            f"AJAP Top5 bridge falló guild={guild_id} mensaje={source_message_id}: {exc}"
        )


def _persist_official_with_top5(runtime, guild_id: int, row, *args, **kwargs):
    source_id = int(row["source_message_id"])
    existed_before = top5._source_exists(runtime, int(guild_id), source_id)
    before = None
    if not existed_before:
        try:
            before = top5._top5(runtime, int(guild_id))
        except Exception as exc:
            print(
                f"AJAP Top5 bridge snapshot evidencia falló guild={guild_id} "
                f"mensaje={source_id}: {exc}"
            )

    result = _BASE_EVIDENCE_PERSIST(runtime, guild_id, row, *args, **kwargs)

    try:
        ok = bool(result[0]) if isinstance(result, tuple) and result else False
        is_new = (
            ok
            and not existed_before
            and top5._source_exists(runtime, int(guild_id), source_id)
        )
        if is_new:
            _queue_if_overtake(runtime, int(guild_id), source_id, before)
    except Exception as exc:
        print(
            f"AJAP Top5 bridge post-evidencia falló guild={guild_id} "
            f"mensaje={source_id}: {exc}"
        )
    return result


evidence._persist_official = _persist_official_with_top5


def _store_with_top5(runtime, message, payload, hashes):
    """Respaldo para cualquier flujo legado que todavía use league.store()."""
    guild = getattr(message, "guild", None)
    source_id = int(getattr(message, "id", 0) or 0)
    existed_before = bool(
        guild is not None
        and source_id
        and top5._source_exists(runtime, int(guild.id), source_id)
    )
    before = None
    if guild is not None and source_id and not existed_before:
        try:
            before = top5._top5(runtime, int(guild.id))
        except Exception:
            before = None

    result = _BASE_LEAGUE_STORE(runtime, message, payload, hashes)

    try:
        score_ok = bool(result[0]) if isinstance(result, tuple) and result else False
        if (
            score_ok
            and guild is not None
            and source_id
            and not existed_before
            and top5._source_exists(runtime, int(guild.id), source_id)
        ):
            _queue_if_overtake(runtime, int(guild.id), source_id, before)
    except Exception as exc:
        print(
            f"AJAP Top5 bridge post-store falló guild={getattr(guild, 'id', None)} "
            f"mensaje={source_id}: {exc}"
        )
    return result


league.store = _store_with_top5


async def _manual_submit_with_top5(self, interaction):
    """Cubre CARGAR RESULTADO de la tarjeta de revisión Staff/PES."""
    runtime = strict._runtime()
    guild_id = int(interaction.guild_id) if interaction.guild_id else 0
    review = None
    source_id = 0
    before = None
    existed_before = False

    if runtime is not None and guild_id:
        try:
            review = strict._review_for_staff_message(
                runtime, guild_id, int(self.staff_message_id)
            )
            if review:
                source_id = int(review["source_message_id"])
                existed_before = top5._source_exists(runtime, guild_id, source_id)
                if not existed_before:
                    before = top5._top5(runtime, guild_id)
        except Exception as exc:
            print(
                f"AJAP Top5 bridge snapshot Staff falló guild={guild_id} "
                f"mensaje={source_id}: {exc}"
            )

    result = await _BASE_MANUAL_SUBMIT(self, interaction)

    if runtime is not None and guild_id and source_id and not existed_before:
        try:
            if top5._source_exists(runtime, guild_id, source_id):
                _queue_if_overtake(runtime, guild_id, source_id, before)
        except Exception as exc:
            print(
                f"AJAP Top5 bridge post-Staff falló guild={guild_id} "
                f"mensaje={source_id}: {exc}"
            )
    return result


strict.LeagueManualScoreModal.on_submit = _manual_submit_with_top5

print(
    "AJAP Top5 bridge activo: final automático + botones de evidencia + "
    "confirmación rival + revisión Staff"
)
