"""Keep live AJAP result intake responsive while rescuing the newest failed upload.

The old recovery listener could OCR up to 250 historical pending screenshots on
startup. That competed with new uploads and made Discord look frozen.

New rule:
- on startup, retry ONLY the newest pending result once;
- never sweep the historical backlog automatically;
- audits/manual review remain responsible for older pending captures.
"""
from __future__ import annotations

import league_automation_patch as league
import league_pending_review_reprocess_patch as pending


_ORIGINAL_INSTALL = pending.install_pending_review_reprocess


def _latest_pending_row(runtime, guild_id: int):
    pending.evidence._ensure_schema(runtime, guild_id)
    pending.strict._ensure_schema(runtime, guild_id)
    conn = league.db(runtime, guild_id)
    try:
        return conn.execute(
            """
            SELECT r.source_message_id, r.source_channel_id,
                   r.staff_channel_id, r.staff_message_id, r.reason
            FROM league_manual_reviews r
            LEFT JOIN league_matches m
              ON m.source_message_id = r.source_message_id
            WHERE UPPER(COALESCE(r.status, 'PENDIENTE'))='PENDIENTE'
              AND m.source_message_id IS NULL
            ORDER BY datetime(r.created_at) DESC, r.source_message_id DESC
            LIMIT 1
            """
        ).fetchall()
    finally:
        conn.close()


def _install_latest_only(runtime, bot):
    # pending._retry_guild resolves _pending_rows dynamically, so constraining
    # this selector to one row preserves all existing duplicate/persistence
    # safety while removing the expensive 250-image startup sweep.
    pending._pending_rows = _latest_pending_row
    _ORIGINAL_INSTALL(runtime, bot)
    print(
        "AJAP Liga: recuperación al iniciar limitada a la ÚLTIMA captura pendiente "
        "(1 solo reintento; sin barrido histórico)"
    )


pending.install_pending_review_reprocess = _install_latest_only
