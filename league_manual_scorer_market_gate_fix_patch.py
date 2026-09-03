"""Allow Liga manual-scorer modals to submit from the Staff/Results workflow.

The market channel gate already exempts all ``ajap:league:`` component ids, so the
persistent ``Agregar goleador`` button itself is allowed outside #mercado. The
modal classes, however, were created without an explicit custom_id; discord.py
therefore generated a random id that did not start with ``ajap:league:`` and the
market gate rejected the modal submit as if it were a market interaction.

Give both the current fast modal and the legacy modal a stable Liga custom_id.
This changes no scorer validation/persistence logic; it only keeps the submit out
of the market-only channel restriction.
"""
from __future__ import annotations

import market_usage_channel_patch as market_gate
import league_manual_scorer_entry_patch as entry
import league_manual_scorer_button_timeout_fix_patch as fast

PREFIX = "ajap:league:manual-scorer:"
MODAL_ID = PREFIX + "modal"

# Defensive explicit exemption in addition to the generic ajap:league: prefix.
if PREFIX not in market_gate.EXEMPT_COMPONENT_PREFIXES:
    market_gate.EXEMPT_COMPONENT_PREFIXES = (
        *market_gate.EXEMPT_COMPONENT_PREFIXES,
        PREFIX,
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

print("AJAP Liga: modal Agregar goleador exento del canal exclusivo de Mercado")
