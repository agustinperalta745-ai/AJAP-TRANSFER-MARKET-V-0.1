import discord


def apply_clausulazo_safety_patch(runtime):
    base_view = runtime.OperacionAdminView

    class ClausulazoSafeOperacionAdminView(base_view):
        def __init__(self, operacion_id: int):
            super().__init__(operacion_id)
            op = runtime.operacion_por_id(operacion_id)
            if not op or (op["operation_type"] or "").strip().upper() != "CLAUSULAZO":
                return

            # Una vez que Staff aprobó el clausulazo, la decisión deportiva es firme.
            # Desde este punto solo queda aplicar el cambio físicamente en PES.
            for item in self.children:
                label = getattr(item, "label", None)
                if label in {"Aprobar", "Rechazar admin"}:
                    item.disabled = True

    ClausulazoSafeOperacionAdminView.__name__ = "OperacionAdminView"
    runtime.OperacionAdminView = ClausulazoSafeOperacionAdminView
    print("AJAP clausulazo safety activo: aprobación firme; solo queda Aplicado en PES")
