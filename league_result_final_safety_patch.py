"""Last safety bridge for AJAP result recovery/testing.

- Never let /rehabilitar_captura_prueba delete an already official match.
- Make the silent historical pending-review recovery use the runtime rescue reader
  (local OCR first, OpenAI fallback when available) with the same guild/author
  identity context as a normal Discord upload.
"""

from __future__ import annotations

import league_automation_patch as league
import league_capture_rehab_patch as rehab
import league_multisignal_result_patch as multisignal
import league_runtime_result_rescue_patch as rescue
import pes_username_link_patch as pes_links


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


async def _analyze_message_with_runtime_rescue(runtime, message, images):
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
        return await rescue.analyze_with_runtime_rescue(images)
    finally:
        multisignal._AUTHOR_DISPLAY.reset(display_token)
        multisignal._AUTHOR_ID.reset(author_token)
        pes_links._RESULT_GUILD_ID.reset(guild_token)


# league_pending_review_reprocess_patch calls this module attribute dynamically,
# so replacing it here upgrades old pending reviews without rewriting that module.
multisignal.analyze_message = _analyze_message_with_runtime_rescue

# Reassert the final analyzer after every earlier reader patch has loaded.
league.analyze = rescue.analyze_with_runtime_rescue
pes_links.analyze_with_pes_links = rescue.analyze_with_runtime_rescue

print(
    "AJAP Liga: seguridad final activa (rehab no borra oficiales + pendientes usan runtime rescue)"
)
