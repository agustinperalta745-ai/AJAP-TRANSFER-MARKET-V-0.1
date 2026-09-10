"""Harden the Staff -> Gestión Discord button against interaction timeouts.

The organized Staff menu historically rebuilt an old AdminView just to discover
legacy buttons. After the competition-cycle/countdown wrappers this became both
unnecessary and fragile. Build Gestión directly from the final controls and
acknowledge the component interaction before any database/view work.
"""

from __future__ import annotations

import discord

import staff_admin_organized_patch as staff
import competition_cycle_admin_ui_patch as cycle_ui
import season_countdown_patch as countdown


if not getattr(staff, "_ajap_management_timeout_fix", False):
    _ORIGINAL_SECTION_CALLBACK = staff.SectionButton.callback

    def _management_init(self):
        discord.ui.View.__init__(self, timeout=300)
        self.add_item(staff.AssignmentsButton(row=0))
        self.add_item(cycle_ui.ManageCycleButton(row=0))
        self.add_item(countdown.CountdownAdminButton(row=1))
        self.add_item(staff.ExportButton(row=1))
        self.add_item(staff.BackAdminButton(row=2))

    staff.ManagementView.__init__ = _management_init

    async def _section_callback(self, interaction: discord.Interaction):
        if str(getattr(self, "section", "") or "") != "management":
            return await _ORIGINAL_SECTION_CALLBACK(self, interaction)

        if not staff.APP or not staff.APP.es_admin(interaction):
            await interaction.response.send_message(
                "⛔ Solo administradores.",
                ephemeral=True,
            )
            return

        # Acknowledge immediately so Discord never expires the interaction while
        # the cycle/countdown controls inspect the persistent database.
        await interaction.response.defer()
        try:
            embed = staff.section_embed(
                "⚙️ GESTIÓN",
                "Configuración general del torneo y del mercado.",
                [
                    "👥 Asignaciones",
                    "🗓️ Gestionar etapa AJPA",
                    "⏳ Cierre de temporada",
                    "📤 Exportar mercado",
                ],
            )
            await interaction.edit_original_response(
                content=None,
                embeds=[embed],
                view=staff.ManagementView(),
            )
        except Exception as exc:
            print(
                "AJAP Gestión Staff error después de defer: "
                f"{type(exc).__name__}: {exc}"
            )
            try:
                await interaction.edit_original_response(
                    content=(
                        "⚠️ No se pudo abrir Gestión. "
                        "El error quedó registrado para Staff."
                    ),
                    embeds=[],
                    view=staff.BackAdminView(),
                )
            except Exception:
                pass

    staff.SectionButton.callback = _section_callback
    staff._ajap_management_timeout_fix = True
    print(
        "AJAP Staff Gestión: menú directo + respuesta temprana anti-timeout activos"
    )
