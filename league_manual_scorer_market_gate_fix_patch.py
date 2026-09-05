"""Keep Liga scorer/result management outside the market-only channel gate.

Liga components are allowed outside #mercado when their custom_id starts with
``ajap:league:``. Some scorer modals and the newer match-management views create
buttons/selects without an explicit custom_id, so discord.py generates random ids
and the market gate can reject MARCADOR / AGREGAR GOLEADOR / EDITAR / CERRAR and
the following selectors as if they were transfer-market interactions.

This patch keeps the existing scorer modal fix and gives every transient child
created by both Liga match-manager modules an ``ajap:league:`` custom_id.
No result/scorer validation or persistence logic is changed.
"""
from __future__ import annotations

import discord

import market_usage_channel_patch as market_gate
import league_manual_scorer_entry_patch as entry
import league_manual_scorer_button_timeout_fix_patch as fast

PREFIX = "ajap:league:manual-scorer:"
MODAL_ID = PREFIX + "modal"
UNIFIED_MODULE = "league_unified_match_manager_patch"
UNIFIED_PREFIX = "ajap:league:match-manager:"
SCORER_EDITOR_MODULE = "league_scorer_editor_v2_patch"
SCORER_EDITOR_PREFIX = "ajap:league:scorer-editor:"

# Defensive explicit exemptions in addition to the generic ajap:league: prefix.
for prefix in (PREFIX, UNIFIED_PREFIX, SCORER_EDITOR_PREFIX):
    if prefix not in market_gate.EXEMPT_COMPONENT_PREFIXES:
        market_gate.EXEMPT_COMPONENT_PREFIXES = (
            *market_gate.EXEMPT_COMPONENT_PREFIXES,
            prefix,
        )


def _stable_modal_id(modal_cls, marker: str):
    original_init = modal_cls.__init__
    if getattr(original_init, marker, False):
        return

    def wrapped_init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        self.custom_id = MODAL_ID

    setattr(wrapped_init, marker, True)
    modal_cls.__init__ = wrapped_init


_stable_modal_id(entry.ManualScorerModal, "_ajap_market_gate_modal_fix")
_stable_modal_id(fast.FastManualScorerModal, "_ajap_market_gate_modal_fix")


def _liga_view_prefix(view) -> str | None:
    module = getattr(view.__class__, "__module__", "")
    if module == UNIFIED_MODULE:
        return UNIFIED_PREFIX
    if module == SCORER_EDITOR_MODULE:
        return SCORER_EDITOR_PREFIX
    return None


def _tag_child(view, child, index: int):
    """Give transient Liga manager buttons/selects a Liga id before dispatch."""
    prefix = _liga_view_prefix(view)
    if prefix is None or not hasattr(child, "custom_id"):
        return
    current = str(getattr(child, "custom_id", "") or "")
    if current.startswith("ajap:league:"):
        return
    try:
        child.custom_id = (
            f"{prefix}{view.__class__.__name__.lower()}:{int(index)}"
        )[:100]
    except Exception as exc:
        print(
            "WARNING AJAP Liga: no pude etiquetar componente del gestor de partido "
            f"{view.__class__.__name__}: {type(exc).__name__}: {exc}"
        )


# Decorator buttons (MARCADOR / AGREGAR GOLEADOR / EDITAR / CERRAR, etc.) are
# created inside discord.ui.View.__init__, so tag them immediately after the base
# init returns.
_original_view_init = discord.ui.View.__init__
if not getattr(_original_view_init, "_ajap_unified_market_gate_fix", False):

    def _view_init(self, *args, **kwargs):
        _original_view_init(self, *args, **kwargs)
        if _liga_view_prefix(self) is not None:
            for index, child in enumerate(list(getattr(self, "children", []))):
                _tag_child(self, child, index)

    _view_init._ajap_unified_market_gate_fix = True
    discord.ui.View.__init__ = _view_init


# Team/player/goal selectors and pagination buttons are added after super().__init__,
# therefore also tag every later add_item belonging specifically to these Liga
# manager modules.
_original_add_item = discord.ui.View.add_item
if not getattr(_original_add_item, "_ajap_unified_market_gate_fix", False):

    def _add_item(self, item):
        if _liga_view_prefix(self) is not None:
            _tag_child(self, item, len(getattr(self, "children", [])))
        return _original_add_item(self, item)

    _add_item._ajap_unified_market_gate_fix = True
    discord.ui.View.add_item = _add_item


print(
    "AJAP Liga: goleadores + editores de partido exentos del canal exclusivo de Mercado"
)
