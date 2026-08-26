"""Puente entre clausulazos y las tarjetas Staff/PES.

Un clausulazo se aprueba desde su propia vista Staff, no desde OperacionAdminView.
Este parche envuelve ese botón para que, al crearse la transferencia APROBADA,
aparezca inmediatamente la tarjeta amarilla en /canal_movimientos.
"""

import discord

import clausulazo_patch as clauses


def apply_clausulazo_report_bridge(runtime):
    view_cls = clauses.ClauseDecisionView
    if getattr(view_cls, "_ajap_pes_report_bridge", False):
        return

    original_init = view_cls.__init__

    def reporting_init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        request_id = int(getattr(self, "request_id", 0) or 0)
        if not request_id:
            return

        for child in self.children:
            if not isinstance(child, discord.ui.Button) or child.label != "Aprobar clausulazo":
                continue
            original_callback = child.callback

            async def approve_with_report(interaction, _original=original_callback, _request_id=request_id):
                await _original(interaction)
                request = clauses.request_by_id(_request_id)
                if not request or not request["transfer_id"]:
                    return
                transfer = runtime.operacion_por_id(int(request["transfer_id"]))
                if not transfer or (transfer["status"] or "").upper() != "APROBADA":
                    return
                publisher = getattr(runtime, "publish_or_refresh_operation_report", None)
                if publisher is None:
                    return
                try:
                    await publisher(interaction, int(transfer["id"]))
                except Exception as exc:
                    print(
                        f"WARNING AJAP: tarjeta Staff/PES de clausulazo #{transfer['id']} falló: {exc}"
                    )

            child.callback = approve_with_report

    view_cls.__init__ = reporting_init
    view_cls._ajap_pes_report_bridge = True
    print("AJAP clausulazos integrados al checklist Staff/PES")
