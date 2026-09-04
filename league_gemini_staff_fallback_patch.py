"""Final AJPA fallback policy for Gemini result intake.

Players usually photograph the PES result/scorer screens once and then leave the
match, so an uncertain Gemini read must NOT tell them to recreate/re-send evidence.

Policy:
- clear partial/halftime -> tell the player to send the final screen later;
- clear final + complete roster-resolved scorers -> automatic official load;
- anything unclear in a final capture (teams, score, uploader identity, scorers)
  -> preserve the original evidence and send it to Staff review;
- automatic persistence errors before the match is official -> Staff review;
- once official, keep the existing app/standings/GES success path.

The existing Staff parity pipeline is intentionally reused. A Staff-resolved card
finalizes through evidence._persist_official, refreshes the league/app data, sends
the result to the configured GES/results-to-load channel, and keeps the manual
"Agregar goleador" fallback when a scorer still cannot be recovered safely.
"""
from __future__ import annotations

import discord

import league_automation_patch as league
import league_result_evidence_patch as evidence
import league_result_intake_pause_patch as gemini
import league_validation_admin_review_patch as strict
import league_ges_result_queue_patch as ges


async def _safe_reply(message, text: str):
    try:
        await message.reply(
            text,
            mention_author=False,
            allowed_mentions=discord.AllowedMentions.none(),
        )
    except Exception:
        pass


def _fallback_payload(payload=None, *, note: str = ""):
    if isinstance(payload, dict):
        out = dict(payload)
    else:
        out = {
            "kind": "unknown",
            "match_state": "unknown",
            "home_team": "",
            "away_team": "",
            "home_goals": -1,
            "away_goals": -1,
            "scorers": [],
            "confidence": 0.0,
        }
    out["source_kind"] = "gemini"
    if note:
        old = str(out.get("notes") or "").strip()
        out["notes"] = f"{old} | {note}".strip(" |")
    return out


async def _send_staff_review(message, reason: str, hashes=None, payload=None):
    """Send one non-duplicated Staff card and keep Gemini's useful payload."""
    saved = _fallback_payload(payload, note=reason)
    try:
        # league_manual_review_parity_patch expands this function with payload=.
        # Keep a compatibility fallback in case startup order ever changes.
        try:
            return await strict._send_admin_review(
                message,
                reason,
                hashes,
                payload=saved,
            )
        except TypeError as exc:
            if "payload" not in str(exc):
                raise
            return await strict._send_admin_review(message, reason, hashes)
    except Exception as exc:
        print(
            f"WARNING AJPA GEMINI STAFF FALLBACK source={getattr(message, 'id', '?')}: "
            f"{type(exc).__name__}: {exc}"
        )
        await _safe_reply(
            message,
            "⚠️ El resultado necesita revisión de Staff, pero no pude crear la tarjeta automática. "
            "Avisale a un administrador y conservá esta captura en el canal.",
        )
        return False


def _scorer_totals(home: str, away: str, scorers):
    totals = {home: 0, away: 0}
    for item in scorers or []:
        club = item.get("team")
        if club not in totals:
            continue
        try:
            totals[club] += int(item.get("goals", 0))
        except (TypeError, ValueError):
            continue
    return totals


def _missing_scorer_reason(home: str, away: str, hg: int, ag: int, scorers):
    totals = _scorer_totals(home, away, scorers)
    missing = []
    for team, expected in ((home, int(hg)), (away, int(ag))):
        diff = expected - int(totals.get(team, 0))
        if diff > 0:
            missing.append(f"{team}: faltan {diff}")
        elif diff < 0:
            missing.append(f"{team}: hay {-diff} de más")
    if not missing:
        return None
    return (
        f"Gemini leyó el resultado {home} {hg}-{ag} {away}, pero no pudo cerrar "
        f"todos los goleadores contra las plantillas ({'; '.join(missing)}). "
        "Se envía a Staff porque el jugador puede haber salido del partido y no debe "
        "depender de sacar otra captura."
    )


async def staff_fallback_result_handle(runtime, bot, message):
    if not getattr(message, "guild", None):
        return
    if getattr(getattr(message, "author", None), "bot", False):
        return

    intake = gemini._configured_intake(runtime, message.guild.id)
    if not intake or int(getattr(getattr(message, "channel", None), "id", 0) or 0) != int(intake):
        return

    attachments = list(getattr(message, "attachments", None) or [])
    if not any(gemini._is_image(att) for att in attachments):
        return

    await gemini._react(message, "🔎")

    try:
        images, hashes = await gemini._read_images(message)
    except Exception as exc:
        print(f"WARNING AJPA GEMINI IMAGE READ: {type(exc).__name__}: {exc}")
        await _send_staff_review(
            message,
            "No se pudieron recuperar correctamente las imágenes adjuntas para Gemini.",
            None,
            _fallback_payload(note=str(exc)),
        )
        return

    if not images:
        await _send_staff_review(
            message,
            "La publicación contiene una imagen, pero el lector no pudo abrirla como evidencia válida.",
            hashes,
            _fallback_payload(),
        )
        return

    try:
        payload = await gemini._analyze(images)
    except Exception as exc:
        print(f"WARNING AJPA GEMINI RESULT: {type(exc).__name__}: {exc}")
        await _send_staff_review(
            message,
            f"Gemini no pudo procesar la captura: {type(exc).__name__}: {str(exc)[:350]}",
            hashes,
            _fallback_payload(note=str(exc)),
        )
        return

    try:
        confidence = float(payload.get("confidence") or 0.0)
    except (TypeError, ValueError):
        confidence = 0.0
    state = str(payload.get("match_state") or "unknown").casefold()
    score = gemini._score(payload)

    # A genuinely partial screen is not an error: the final result does not exist
    # yet, so there is nothing for Staff to resolve at this point.
    if state == "partial":
        await _safe_reply(
            message,
            "🟡 Detecté que esta captura es de **primer tiempo/resultado parcial**. "
            "No cargué puntos. Cuando termine, mandá la captura final.",
        )
        return

    if not score or state != "final" or confidence < gemini.MIN_CONF:
        reason = (
            "Gemini no pudo confirmar con suficiente seguridad los dos equipos y el "
            f"marcador FINAL (estado={state}, confianza={confidence:.0%})."
        )
        notes = str(payload.get("notes") or "").strip()
        if notes:
            reason += f" Diagnóstico Gemini: {notes[:350]}"
        await _send_staff_review(message, reason, hashes, payload)
        return

    home, away, hg, ag = score
    if not gemini._soft_reporter_check(runtime, message, home, away):
        await _send_staff_review(
            message,
            (
                f"Gemini leyó {home} {hg}-{ag} {away}, pero el club vinculado al autor "
                "no coincide con ninguno de los dos equipos. Staff debe validar la identidad "
                "antes de cargar el partido."
            ),
            hashes,
            payload,
        )
        return

    scorers = gemini._clean_scorers(runtime, message.guild.id, payload, score)
    scorer_issue = _missing_scorer_reason(home, away, hg, ag, scorers)
    if scorer_issue:
        await _send_staff_review(message, scorer_issue, hashes, payload)
        return

    clean_payload = dict(payload)
    clean_payload.update(
        {
            "kind": "both" if scorers else "result",
            "match_state": "final",
            "home_team": home,
            "away_team": away,
            "home_goals": hg,
            "away_goals": ag,
            "scorers": scorers,
            "source_kind": "gemini",
            "confidence": confidence,
        }
    )

    try:
        evidence._stage(
            runtime,
            message,
            score,
            clean_payload,
            hashes,
            "GEMINI_VALIDADO",
        )
        row = evidence._row(
            runtime,
            message.guild.id,
            source_message_id=message.id,
        )
        if row is None:
            raise RuntimeError("No se pudo recuperar el resultado validado")

        ok, result_state, duplicate, scorer_count = evidence._persist_official(
            runtime,
            message.guild.id,
            row,
            include_scorers=True,
            status="FINAL_CARGADO",
        )

        if not ok and result_state == "DUPLICADO":
            await _safe_reply(
                message,
                "ℹ️ El cruce ya tiene un resultado oficial cargado. "
                "No dupliqué el partido ni los puntos.",
            )
            return
        if not ok:
            raise RuntimeError(f"No se pudo persistir resultado: {result_state}")
    except Exception as exc:
        print(f"WARNING AJPA GEMINI PERSIST: {type(exc).__name__}: {exc}")
        await _send_staff_review(
            message,
            (
                f"Gemini leyó {home} {hg}-{ag} {away} y sus goleadores, pero falló "
                f"la persistencia automática antes de confirmar el partido: "
                f"{type(exc).__name__}: {str(exc)[:300]}"
            ),
            hashes,
            clean_payload,
        )
        return

    # From here the match is already official. Do not create a manual review that
    # could tempt Staff to duplicate it; refresh and GES failures are reported as
    # operational warnings instead.
    try:
        await league.refresh(runtime, bot, message.guild.id)
    except Exception as exc:
        print(f"WARNING AJPA GEMINI REFRESH: {type(exc).__name__}: {exc}")

    ges_sent = False
    try:
        await ges._send(runtime, message.guild.id, row, home, away, hg, ag)
        queued = ges._find(runtime, message.guild.id, source=message.id)
        ges_sent = bool(queued and queued["ges_message_id"])
    except Exception as ges_exc:
        print(f"WARNING AJPA GEMINI GES: {type(ges_exc).__name__}: {ges_exc}")

    await gemini._react(message, "✅")
    scorer_text = gemini._format_scorers(home, away, hg, ag, scorers)
    ges_line = (
        "📋 **Resultados para cargar:** enviado al canal configurado."
        if ges_sent
        else "⚠️ **Resultados para cargar:** el partido quedó oficial, pero no pude confirmar la publicación de la tarjeta GES."
    )
    await _safe_reply(
        message,
        (
            "✅ **RESULTADO CARGADO AUTOMÁTICAMENTE**\n"
            f"## {home} {hg} - {ag} {away}\n"
            f"{scorer_text}\n\n"
            "📲 **App actualizada:** resultado + puntos/tabla + goleadores.\n"
            f"{ges_line}"
        ),
    )


# Replace the Gemini handler itself. Its existing on_ready hook calls
# gemini._install_handlers(), which reads this global every reconnect, so the
# Staff fallback policy remains authoritative after Railway restarts.
gemini.gemini_result_handle = staff_fallback_result_handle
gemini._install_handlers()

print(
    "AJPA Liga: Gemini fallback a Staff ACTIVO | parciales esperan final | "
    "finales incompletos nunca piden recrear captura"
)
