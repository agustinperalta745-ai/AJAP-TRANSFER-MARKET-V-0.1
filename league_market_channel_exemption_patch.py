"""Keep AJAP Liga interactions outside the market-only channel gate.

The market gate intentionally restricts market commands/components to the configured
#mercado channel. Liga result workflows live in #Resultados and Staff/PES instead,
so every Liga component/modal and Liga-only Staff command must bypass that gate.

This patch:
- exempts all custom_ids under ``ajap:league:``;
- exempts /liga_diagnostico and /rehabilitar_captura_prueba from the market channel restriction;
- gives the two Liga modals stable ``ajap:league:`` custom_ids so their submits
  are also exempt, not only the buttons that open them.
"""

import market_usage_channel_patch as market_gate
import league_result_evidence_patch as evidence
import league_validation_admin_review_patch as strict


# The market gate reads these globals at dispatch time, so extending them here is
# enough even if the gate itself was installed earlier in the startup chain.
if "ajap:league:" not in market_gate.EXEMPT_COMPONENT_PREFIXES:
    market_gate.EXEMPT_COMPONENT_PREFIXES = (
        *market_gate.EXEMPT_COMPONENT_PREFIXES,
        "ajap:league:",
    )

market_gate.EXEMPT_COMMANDS.update(
    {
        "liga_diagnostico",
        "rehabilitar_captura_prueba",
    }
)


def _give_modal_custom_id(modal_cls, custom_id: str, marker: str):
    original_init = modal_cls.__init__
    if getattr(original_init, marker, False):
        return

    def wrapped_init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        self.custom_id = custom_id

    setattr(wrapped_init, marker, True)
    modal_cls.__init__ = wrapped_init


_give_modal_custom_id(
    evidence.ManualFinalModal,
    "ajap:league:evidence:manual-final",
    "_ajap_league_market_exempt",
)
_give_modal_custom_id(
    strict.LeagueManualScoreModal,
    "ajap:league:manual-result:score",
    "_ajap_league_market_exempt",
)

print("AJAP Liga fuera del gate de Mercado: botones + modales + diagnostico + rehabilitar captura")
