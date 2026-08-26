"""Ajustes finales para el panel Staff/PES.

El canal Staff puede ser distinto del canal general de mercado, así que sus
botones deben quedar fuera del bloqueo de /canal_mercado. También registra de
forma persistente el botón Cargado en PES del panel Staff.
"""

import discord

import market_usage_channel_patch as usage_gate
import staff_review_channel_patch as staff_review


ALLOWED_CUSTOM_ID_PREFIXES = (
    "ajap:staff-operation:",
    "ajap:staff-clause:",
    "ajap:pes-loaded",
)


class PersistentStaffLoadedView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        button = discord.ui.Button(
            label="Cargado en PES",
            emoji="🎮",
            style=discord.ButtonStyle.primary,
            custom_id="ajap:staff-operation:loaded",
        )
        button.callback = self._loaded
        self.add_item(button)

    async def _loaded(self, interaction: discord.Interaction):
        # Reutiliza exactamente la validación y la lógica del panel Staff.
        proxy = staff_review.StaffOperationView()
        await proxy._loaded(interaction)


def _allow_staff_components_outside_market_channel():
    original = usage_gate._configured_wrong_channel
    if getattr(original, "_ajap_staff_exempt", False):
        return False

    def staff_aware_gate(interaction):
        data = getattr(interaction, "data", None) or {}
        custom_id = data.get("custom_id") if isinstance(data, dict) else None
        if custom_id and any(str(custom_id).startswith(prefix) for prefix in ALLOWED_CUSTOM_ID_PREFIXES):
            return None
        return original(interaction)

    staff_aware_gate._ajap_staff_exempt = True
    usage_gate._configured_wrong_channel = staff_aware_gate
    return True


def apply_staff_review_runtime_fix(runtime, bot):
    if getattr(runtime, "_ajap_staff_review_runtime_fix", False):
        return

    gate_ok = _allow_staff_components_outside_market_channel()
    persistent = 0
    try:
        bot.add_view(PersistentStaffLoadedView())
        persistent = 1
    except ValueError:
        pass

    runtime._ajap_staff_review_runtime_fix = True
    print(
        "AJAP Staff/PES runtime fix activo: botones permitidos en canal Staff "
        f"| gate={'OK' if gate_ok else 'YA'} | Cargado persistente={persistent}"
    )
