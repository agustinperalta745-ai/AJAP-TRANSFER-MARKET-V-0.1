"""Keep new result intake responsive by disabling the historical OCR sweep on startup.

The old pending-review recovery listener can scan up to 250 historical screenshots
on every bot restart. Each screenshot invokes local OCR, so during deploy/restart it
can consume CPU for minutes and make a brand-new result look like it is stuck.

Historical recovery remains available explicitly through the audit/review tools;
it must not compete with live result uploads.
"""
from __future__ import annotations

import league_pending_review_reprocess_patch as pending


def _disabled_install(runtime, bot):
    # Mark the bot so any repeated wrapper call is also a no-op.
    try:
        bot._ajap_pending_review_reprocess_listener = True
    except Exception:
        pass
    print("AJAP Liga: barrido OCR histórico al iniciar DESACTIVADO; prioridad a resultados nuevos")


# The Bot.run wrapper in league_pending_review_reprocess_patch resolves this global
# function at runtime, so replacing it here (before run_bot starts Discord) prevents
# the expensive on_ready sweep from being installed at all.
pending.install_pending_review_reprocess = _disabled_install
