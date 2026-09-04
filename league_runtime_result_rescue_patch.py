"""Final runtime rescue for AJAP PES6 result screenshots.

This patch fixes the worst possible failure mode: a readable screenshot reaching
Staff only as a generic "technical error".

Runtime policy:
1. Run the current local/multisignal OCR first.
2. If local OCR raises OR does not produce a confident official score, and a REAL
   OPENAI_API_KEY exists, automatically run the pre-local OpenAI result pipeline.
   This fallback is reliability-critical and no longer depends on the optional
   AJAP_VISION_ALLOW_PAID_FALLBACK flag.
3. Never throw an OCR exception into the evidence handler when both readers fail;
   return a diagnostic low-confidence payload instead.
4. Replace the evidence handler with the same safe competition workflow but, if
   a non-reader technical exception happens, put the concrete exception class and
   message in the Staff review card so the next failure is immediately actionable.
5. An exact replay of an already-official score is a harmless duplicate, never a
   conflict. Only a different score for the same pair is sent to Staff.
"""

from __future__ import annotations

import os

import league_automation_patch as league
import league_local_ocr_patch as local
import league_result_evidence_patch as evidence
import league_validation_admin_review_patch as strict

try:
    import pes_username_link_patch as pes_links
except Exception:  # pragma: no cover - defensive import during unusual startup
    pes_links = None


_LOCAL_ANALYZE = local.analyze_local_first
_PAID_ANALYZE = getattr(local, "_BASE_ANALYZE", None)


def _float(value, default=0.0):
    try:
        return float(value)
    except (TypeError, ValueError):
        return float(default)


def _score_confident(payload):
    return bool(
        isinstance(payload, dict)
        and league.parsed_score(payload)
        and _float(payload.get("result_confidence", payload.get("confidence")), 0.0)
        >= league.MIN_CONF
    )


def _real_openai_key():
    value = str(os.getenv("OPENAI_API_KEY") or "").strip()
    sentinel = str(getattr(local, "LOCAL_SENTINEL", "") or "").strip()
    if not value or (sentinel and value == sentinel):
        return None
    return value


def _same_official_score(row, duplicate) -> bool:
    """Compare the detected score with an existing match in either orientation."""
    if not row or not duplicate:
        return False
    home = str(row["home_team"] or "").casefold()
    away = str(row["away_team"] or "").casefold()
    hg = int(row["home_goals"])
    ag = int(row["away_goals"])

    d_home = str(duplicate["home_team"] or "").casefold()
    d_away = str(duplicate["away_team"] or "").casefold()
    d_hg = int(duplicate["home_goals"])
    d_ag = int(duplicate["away_goals"])

    if home == d_home and away == d_away:
        return hg == d_hg and ag == d_ag
    if home == d_away and away == d_home:
        return hg == d_ag and ag == d_hg
    return False


async def analyze_with_runtime_rescue(images):
    local_payload = None
    local_error = None

    try:
        local_payload = await _LOCAL_ANALYZE(images)
    except Exception as exc:
        local_error = exc
        print(
            "WARNING AJAP runtime rescue local reader: "
            f"{type(exc).__name__}: {exc}"
        )

    if _score_confident(local_payload):
        return local_payload

    paid_error = None
    if _real_openai_key() and callable(_PAID_ANALYZE):
        try:
            paid_payload = await _PAID_ANALYZE(images)
            if isinstance(paid_payload, dict):
                # Keep PES username -> current club authority when the paid reader
                # returns side-specific usernames.
                if pes_links is not None:
                    try:
                        guild_id = pes_links._RESULT_GUILD_ID.get()
                        paid_payload = pes_links._resolve_payload_with_links(
                            pes_links.APP, guild_id, paid_payload
                        )
                    except Exception as exc:
                        print(
                            "WARNING AJAP runtime rescue PES-link merge: "
                            f"{type(exc).__name__}: {exc}"
                        )
                notes = str(paid_payload.get("notes") or "").strip()
                paid_payload["notes"] = (
                    notes + (" | " if notes else "") + "AJAP automatic OpenAI rescue"
                )[:1000]
                return paid_payload
        except Exception as exc:
            paid_error = exc
            print(
                "WARNING AJAP runtime rescue OpenAI reader: "
                f"{type(exc).__name__}: {exc}"
            )

    if isinstance(local_payload, dict):
        return local_payload

    details = []
    if local_error is not None:
        details.append(f"local={type(local_error).__name__}: {local_error}")
    if paid_error is not None:
        details.append(f"openai={type(paid_error).__name__}: {paid_error}")
    if not _real_openai_key():
        details.append("openai=fallback unavailable (no real API key)")

    return {
        "kind": "unknown",
        "match_state": "unknown",
        "home_team": "",
        "away_team": "",
        "home_goals": None,
        "away_goals": None,
        "scorers": [],
        "confidence": 0.0,
        "result_confidence": 0.0,
        "scorers_confidence": 0.0,
        "notes": ("AJAP reader rescue failed | " + " | ".join(details))[:1000],
    }


async def reliable_evidence_handle(runtime, bot, message):
    if not message.guild or message.author.bot or not message.attachments:
        return

    evidence._ensure_schema(runtime, message.guild.id)
    conn = league.db(runtime, message.guild.id)
    try:
        cfg = conn.execute(
            "SELECT * FROM league_config WHERE guild_id=?",
            (message.guild.id,),
        ).fetchone()
        already = conn.execute(
            "SELECT * FROM league_matches WHERE source_message_id=? LIMIT 1",
            (message.id,),
        ).fetchone()
    finally:
        conn.close()

    if (
        not cfg
        or not cfg["intake_channel_id"]
        or message.channel.id != int(cfg["intake_channel_id"])
    ):
        return

    if already:
        try:
            await message.add_reaction("✅")
        except Exception:
            pass
        return

    images, hashes = await league.new_images(runtime, message)
    if not images:
        await message.reply(
            "ℹ️ Esta captura ya fue procesada anteriormente o no contiene una imagen válida.",
            mention_author=False,
        )
        return

    try:
        payload = await analyze_with_runtime_rescue(images)
        confidence = _float(payload.get("confidence"), 0.0)

        if confidence < league.MIN_CONF:
            notes = str(payload.get("notes") or "").strip()
            reason = (
                f"La captura no alcanzó la confianza mínima de lectura "
                f"({confidence:.0%} < {league.MIN_CONF:.0%})."
            )
            if notes:
                reason += f"\nDiagnóstico lector: {notes[:650]}"
            await strict._send_admin_review(message, reason, hashes)
            return

        score, error = strict._validated_score(payload)
        if not score:
            await strict._send_admin_review(message, error, hashes)
            return

        home, away, hg, ag = score
        if not evidence._uploader_is_party(runtime, message, home, away):
            await strict._send_admin_review(
                message,
                "La captura fue enviada por un usuario que no figura como DT de ninguno de los dos equipos detectados.",
                hashes,
            )
            return

        pending = evidence._pending_partial(
            runtime,
            message.guild.id,
            home,
            away,
            exclude_source=message.id,
        )
        state = str(payload.get("match_state") or "unknown").casefold()

        if pending:
            evidence._stage(
                runtime,
                message,
                score,
                payload,
                hashes,
                "REANUDACION_PENDIENTE",
                pending["source_message_id"],
            )
            current = evidence._row(
                runtime, message.guild.id, source_message_id=message.id
            )
            prompt = await message.reply(
                embed=evidence._resume_embed(pending, current),
                view=evidence.ResumeDecisionView(),
                mention_author=False,
            )
            evidence._set_prompt(runtime, message.guild.id, message.id, prompt.id)
            return

        if state == "final":
            evidence._stage(
                runtime, message, score, payload, hashes, "FINAL_DETECTADO"
            )
            row = evidence._row(
                runtime, message.guild.id, source_message_id=message.id
            )
            ok, result_state, duplicate, scorers = evidence._persist_official(
                runtime, message.guild.id, row
            )
            if not ok:
                if result_state == "DUPLICADO" and _same_official_score(row, duplicate):
                    evidence._update_status(
                        runtime,
                        message.guild.id,
                        message.id,
                        "DUPLICADO_IGNORADO",
                    )
                    try:
                        await message.add_reaction("✅")
                    except Exception:
                        pass
                    await message.reply(
                        f"ℹ️ Ese resultado ya estaba cargado: "
                        f"**{duplicate['home_team']} {duplicate['home_goals']}–"
                        f"{duplicate['away_goals']} {duplicate['away_team']}**. "
                        "No se volvió a sumar.",
                        mention_author=False,
                    )
                    return

                await message.reply(
                    f"⚠️ No cargué {evidence._score_text(row)} porque este cruce ya tiene "
                    f"un resultado oficial distinto: **{duplicate['home_team']} "
                    f"{duplicate['home_goals']}–{duplicate['away_goals']} "
                    f"{duplicate['away_team']}**. El caso pasó a Staff.",
                    mention_author=False,
                )
                await evidence._send_conflict_review(
                    message.guild,
                    row,
                    "Se detectó automáticamente un resultado diferente para un cruce ya cargado.",
                )
                return

            await message.add_reaction("✅")
            extra = f" + **{scorers} goleador(es)**" if scorers else ""
            await message.reply(
                f"✅ Captura final verificada y cargada: "
                f"{evidence._score_text(row)}{extra}.",
                mention_author=False,
            )
            return

        if state == "partial":
            evidence._stage(runtime, message, score, payload, hashes, "PARCIAL")
            row = evidence._row(
                runtime, message.guild.id, source_message_id=message.id
            )
            prompt = await message.reply(
                embed=evidence._partial_embed(row),
                view=evidence.PartialActionsView(),
                mention_author=False,
            )
            evidence._set_prompt(runtime, message.guild.id, message.id, prompt.id)
            return

        evidence._stage(runtime, message, score, payload, hashes, "ESPERANDO_TIPO")
        row = evidence._row(runtime, message.guild.id, source_message_id=message.id)
        prompt = await message.reply(
            embed=evidence._unknown_embed(row),
            view=evidence.EvidenceChoiceView(),
            mention_author=False,
        )
        evidence._set_prompt(runtime, message.guild.id, message.id, prompt.id)

    except Exception as exc:
        print(
            f"AJAP Liga evidencia runtime error mensaje={message.id}: "
            f"{type(exc).__name__}: {exc}"
        )
        detail = str(exc).strip() or "sin mensaje"
        await strict._send_admin_review(
            message,
            f"Error técnico {type(exc).__name__}: {detail[:700]}",
            hashes,
        )


# Make both the current module state and all later startup installers use the
# rescued functions.  pes_username_link_patch and league_result_evidence_patch
# reassign league.analyze/league.handle during startup, so their install targets
# are replaced as well.
league.analyze = analyze_with_runtime_rescue
evidence.evidence_handle = reliable_evidence_handle
league.handle = reliable_evidence_handle

if pes_links is not None:
    pes_links.analyze_with_pes_links = analyze_with_runtime_rescue

print(
    "AJAP Liga: RUNTIME RESCUE activo (OCR local -> OpenAI automático -> diagnóstico concreto)"
)
