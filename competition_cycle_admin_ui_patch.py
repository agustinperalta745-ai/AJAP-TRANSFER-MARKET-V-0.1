"""Surface the official AJPA cycle inside Administración -> Gestión."""

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


def apply_patch():
    view = staff.ManagementView
    if getattr(view, "_ajpa_cycle_admin_ui", False):
        return
    original_init = view.__init__

    def init(self):
        original_init(self)
        for item in list(self.children):
            label = str(getattr(item, "label", "") or "").strip().casefold()
            if "cambiar temporada" in label:
                self.remove_item(item)
        # Keep Assignments on row 0 and make the official lifecycle the second
        # primary management action. Export/configuration remain below.
        self.add_item(ManageCycleButton(row=0))

    view.__init__ = init
    view._ajpa_cycle_admin_ui = True

    original_embed = staff.admin_home_embed
    def admin_home_embed():
        embed = original_embed()
        try:
            payload = cycle.runtime_state(staff.APP)
            for index, field in enumerate(embed.fields):
                if "temporada" in str(field.name).casefold():
                    embed.set_field_at(index, name="🗓️ Etapa AJPA", value=payload["phase_label"], inline=True)
                    break
        except Exception:
            pass
        return embed
    staff.admin_home_embed = admin_home_embed
    print("AJPA Administración: Cambiar temporada -> Gestionar etapa")


apply_patch()
