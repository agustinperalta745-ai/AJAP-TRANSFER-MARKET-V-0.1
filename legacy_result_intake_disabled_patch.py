"""Permanently disable AJPA's legacy Discord result recognizer.

The Results channel can keep existing as a normal channel, but screenshots,
attachments and result text posted there no longer trigger OCR, parsing,
validation queues, database writes or acknowledgements. Official competitive
data now enters AJPA only through the Staff-only manual GES synchronization.
"""

from __future__ import annotations

import asyncio

import league_automation_patch as league


async def _disabled_handle(*args, **kwargs):
    return None


async def _disabled_analyze(*args, **kwargs):
    return {"kind": "unknown", "confidence": 0.0, "notes": "Discord result intake disabled; use GES sync"}


def _disabled_vision(*args, **kwargs):
    return {"kind": "unknown", "confidence": 0.0, "notes": "Discord result intake disabled; use GES sync"}


def _is_legacy_message_listener(callback) -> bool:
    module = str(getattr(callback, "__module__", "") or "")
    name = str(getattr(callback, "__name__", "") or "")
    if module == "league_automation_patch" and name == "message_listener":
        return True
    # Several historical bridges register their own message listener rather than
    # replacing league.handle. Keep the list intentionally result-intake-only.
    return module in {
        "league_ocrspace_result_bridge_patch",
        "league_result_intake_pause_patch",
        "league_result_feedback_patch",
        "league_pending_review_reprocess_patch",
    } and ("message" in name or "result" in name or "feedback" in name)


def _is_legacy_reprocess_listener(callback) -> bool:
    module = str(getattr(callback, "__module__", "") or "")
    name = str(getattr(callback, "__name__", "") or "")
    return module in {
        "league_pending_review_reprocess_patch",
        "league_authoritative_audit_reconcile_patch",
        "league_capture_rehab_patch",
    } and name == "ready_listener"


def _purge(bot) -> tuple[int, int]:
    removed_messages = 0
    removed_reprocess = 0
    for callback in list(getattr(bot, "extra_events", {}).get("on_message", [])):
        if _is_legacy_message_listener(callback):
            try:
                bot.remove_listener(callback, "on_message")
                removed_messages += 1
            except Exception:
                pass
    for callback in list(getattr(bot, "extra_events", {}).get("on_ready", [])):
        if _is_legacy_reprocess_listener(callback):
            try:
                bot.remove_listener(callback, "on_ready")
                removed_reprocess += 1
            except Exception:
                pass
    return removed_messages, removed_reprocess


def _neutralize_functions() -> None:
    # Even if another historical wrapper kept a direct reference to the module,
    # expensive OCR/vision entrypoints become inert and cannot write a result.
    league.handle = _disabled_handle
    league.analyze = _disabled_analyze
    league.vision_sync = _disabled_vision

    for module_name in (
        "league_ocrspace_result_bridge_patch",
        "league_result_intake_pause_patch",
        "league_result_feedback_patch",
        "league_runtime_result_rescue_patch",
        "league_pending_review_reprocess_patch",
    ):
        try:
            module = __import__(module_name)
        except Exception:
            continue
        for attr in ("handle", "_feedback_handle", "analyze", "vision_sync"):
            if hasattr(module, attr):
                setattr(module, attr, _disabled_handle if "handle" in attr else _disabled_analyze)


def disable_legacy_result_intake(runtime, bot) -> None:
    _neutralize_functions()
    removed_messages, removed_reprocess = _purge(bot)

    if not getattr(runtime, "_ajpa_legacy_result_intake_disabled", False):
        async def enforce_on_ready():
            # Yield once so any older ready hook gets a chance to reinstall its
            # listener, then remove it again. No polling/task is created.
            await asyncio.sleep(0)
            _neutralize_functions()
            removed, reprocess = _purge(bot)
            if removed or reprocess:
                print(
                    "AJPA legacy result intake stayed disabled after ready: "
                    f"message_listeners={removed} reprocessors={reprocess}"
                )

        bot.add_listener(enforce_on_ready, "on_ready")
        runtime._ajpa_legacy_result_intake_disabled = True

    print(
        "AJPA Discord result recognizer DISABLED permanently • "
        f"message_listeners_removed={removed_messages} • "
        f"reprocessors_removed={removed_reprocess} • official source=manual GES"
    )
