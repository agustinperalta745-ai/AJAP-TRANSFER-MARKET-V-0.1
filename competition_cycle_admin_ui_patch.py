"""Surface the official AJPA cycle inside Administración and avoid raw phase toggles."""

import discord

import competition_cycle as cycle
import staff_admin_organized_patch as staff


class ManageCycleButton(discord.ui.Button):
    def __init__(self, row=0):
        super().__init__(
            label="GESTIONAR ETAPA",
            emoji="🗓️",
            style=discord.ButtonStyle.primary,
            row=row,
            custom_id="ajpa_admin_manage_cycle",
        )

    async def callback(self, interaction: discord.Interaction):
        if not staff.APP or not staff.APP.es_admin(interaction):
            await interaction.response.send_message("⛔ Solo administradores.", ephemeral=True)
            return
        payload = cycle.runtime_state(staff.APP)
        await interaction.response.send_message(
            embed=cycle.cycle_embed(payload),
            view=cycle.CycleView(staff.APP, staff.BOT, payload),
            ephemeral=True,
        )


def _patch_view(view, remove_needles, *, add_cycle=True):
    if getattr(view, "_ajpa_cycle_admin_ui", False):
        return
    original_init = view.__init__

    def init(self):
        original_init(self)
        for item in list(self.children):
            label = str(getattr(item, "label", "") or "").strip().casefold()
            if any(needle in label for needle in remove_needles):
                self.remove_item(item)
        if add_cycle and not any(
            str(getattr(item, "custom_id", "") or "") == "ajpa_admin_manage_cycle"
            for item in self.children
        ):
            self.add_item(ManageCycleButton(row=0))

    view.__init__ = init
    view._ajpa_cycle_admin_ui = True


def apply_patch():
    # Season and market open/close are one state machine. Removing the legacy
    # direct toggles prevents combinations such as "Temporada activa + Mercado abierto".
    _patch_view(staff.ManagementView, ("cambiar temporada",))
    _patch_view(staff.MarketView, ("abrir mercado", "cerrar mercado"))

    original_embed = staff.admin_home_embed

    def admin_home_embed():
        embed = original_embed()
        try:
            payload = cycle.runtime_state(staff.APP)
            for index, field in enumerate(embed.fields):
                if "temporada" in str(field.name).casefold():
                    embed.set_field_at(
                        index,
                        name="🗓️ Etapa AJPA",
                        value=payload["phase_label"],
                        inline=True,
                    )
                    break
        except Exception:
            pass
        return embed

    staff.admin_home_embed = admin_home_embed

    original_section_embed = staff.section_embed

    def section_embed(title, description, tools):
        items = []
        for item in list(tools):
            text = str(item)
            low = text.casefold()
            if "cambiar temporada" in low:
                text = "🗓️ Gestionar etapa AJPA"
            elif "abrir o cerrar" in low:
                text = "🗓️ Apertura/cierre según etapa AJPA"
            items.append(text)
        return original_section_embed(title, description, items)

    staff.section_embed = section_embed
    print("AJPA Administración: temporada/mercado controlados por Gestionar etapa")


apply_patch()
