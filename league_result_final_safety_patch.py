"""Last safety bridge for AJAP result recovery/testing.

- Never let /rehabilitar_captura_prueba delete an already official match.
- Force every normal/retry result read through the local Railway OCR only.
- OpenAI is never called from the league-result reader, even if an API key exists
  or an old paid-fallback environment flag is still configured.
"""

from __future__ import annotations

import league_automation_patch as league
import league_capture_rehab_patch as rehab
import league_local_ocr_patch as local
import league_multisignal_result_patch as multisignal
import league_runtime_result_rescue_patch as rescue
import pes_username_link_patch as pes_links


# Hard runtime guarantee: the result reader is local-only.  Older modules keep
# references to paid readers for backwards compatibility, but this final bridge
# makes those paths unreachable for result screenshots.
local.ALLOW_PAID_FALLBACK = False
rescue._PAID_ANALYZE = None


_BASE_CLEAR_SOURCE = rehab._clear_source


def _safe_clear_source(runtime, guild_id: int, source_message_id: int, hashes):
    """Keep official DB rows immutable during a reader test/retry."""
    conn = league.db(runtime, int(guild_id))
    try:
        official = conn.execute(
            "SELECT 1 FROM league_matches WHERE source_message_id=? LIMIT 1",
            (int(source_message_id),),
        ).fetchone()
        if not official:
            return _BASE_CLEAR_SOURCE(runtime, guild_id, source_message_id, hashes)

        evidence_row = conn.execute(
            "SELECT prompt_message_id FROM league_result_evidence WHERE source_message_id=? LIMIT 1",
            (int(source_message_id),),
        ).fetchone()
        review_row = conn.execute(
            "SELECT staff_message_id FROM league_manual_reviews WHERE source_message_id=? LIMIT 1",
            (int(source_message_id),),
        ).fetchone()

        # Close any stale manual-review state, but never delete the official
        # match, goal events, hashes or standings contribution.
        conn.execute(
            """
            UPDATE league_manual_reviews
            SET status='RESUELTO_YA_CARGADO', resolved_at=CURRENT_TIMESTAMP
            WHERE source_message_id=? AND UPPER(COALESCE(status,'PENDIENTE'))='PENDIENTE'
            """,
            (int(source_message_id),),
        )
        conn.commit()
        return {
            "removed_match": False,
            "removed_scorers": 0,
            "old_prompt_id": int(evidence_row["prompt_message_id"])
            if evidence_row and evidence_row["prompt_message_id"]
            else None,
            "old_staff_message_id": int(review_row["staff_message_id"])
            if review_row and review_row["staff_message_id"]
            else None,
        }
    finally:
        conn.close()


rehab._clear_source = _safe_clear_source


async def _analyze_local_only(images):
    """Run the local OCR and never enter any OpenAI/paid fallback path."""
    try:
        payload = await local.analyze_local_first(images)
        if isinstance(payload, dict):
            return payload
    except Exception as exc:
        print(
            "WARNING AJAP local-only result reader: "
            f"{type(exc).__name__}: {exc}"
        )
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
            "notes": (
                "AJAP local-only reader failed | "
                f"local={type(exc).__name__}: {exc}"
            )[:1000],
        }

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
        "notes": "AJAP local-only reader returned no payload",
    }


# reliable_evidence_handle resolves this name dynamically from the rescue module,
# so replacing it also removes OpenAI from ordinary new uploads, not only retries.
rescue.analyze_with_runtime_rescue = _analyze_local_only


async def _analyze_message_local_only(runtime, message, images):
    guild_id = getattr(getattr(message, "guild", None), "id", None)
    author = getattr(message, "author", None)
    author_id = getattr(author, "id", None)
    display = getattr(author, "display_name", "") or getattr(author, "name", "") or ""

    guild_token = pes_links._RESULT_GUILD_ID.set(
        int(guild_id) if guild_id is not None else None
    )
    author_token = multisignal._AUTHOR_ID.set(
        int(author_id) if author_id is not None else None
    )
    display_token = multisignal._AUTHOR_DISPLAY.set(str(display))
    try:
        return await _analyze_local_only(images)
    finally:
        multisignal._AUTHOR_DISPLAY.reset(display_token)
        multisignal._AUTHOR_ID.reset(author_token)
        pes_links._RESULT_GUILD_ID.reset(guild_token)


# Pending-review recovery resolves this attribute dynamically as well.
multisignal.analyze_message = _analyze_message_local_only

# Reassert the final analyzer after every earlier reader patch has loaded.
league.analyze = _analyze_local_only
pes_links.analyze_with_pes_links = _analyze_local_only

# Install the deterministic PES6 region reader last. It only replaces the local
# payload function used by the analyzer above; persistence/duplicate/season logic
# remains unchanged. Tesseract then replaces only the OCR mechanics of that
# structured reader, keeping all AJAP validation rules intact.
import league_pes6_structured_reader_patch  # noqa: F401,E402
import league_pes6_score_geometry_patch  # noqa: F401,E402
import league_tesseract_runtime_patch  # noqa: F401,E402
# PES6 Result screens that show the second-period row (2nd/2do) are final.
# This also recognises the English "Result / Exit match series / Match details" UI.
import league_pes6_second_period_final_patch  # noqa: F401,E402
# If the official result is loaded but OCR misses one or more player names, Staff
# gets an explicit persistent card showing exactly how many goals remain to assign.
import league_scorer_pending_patch  # noqa: F401,E402
# Staff can audit the entire historical Results channel oldest-to-newest without
# changing official matches, and bulk-complete missing scorer attribution from
# cards that already include the original screenshot.
import league_historical_audit_patch  # noqa: F401,E402

print(
    "AJAP Liga: seguridad final LOCAL-ONLY activa "
    "(rehab no borra oficiales + Tesseract PES6 + 2nd=final + auditoría histórica + pendientes de goleadores + cero OpenAI)"
)
