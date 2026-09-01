"""Evita que Discord venza la confirmación al retirar un resultado de Liga."""

import discord

import league_automation_patch as league
import league_result_admin_cleanup_patch as cleanup


class SafeConfirmDeleteResultView(discord.ui.View):
    def __init__(self, source_message_id: int):
        super().__init__(timeout=180)
        self.source_message_id = int(source_message_id)

    @discord.ui.button(label="ELIMINAR RESULTADO", emoji="🗑️", style=discord.ButtonStyle.danger)
    async def delete(self, interaction: discord.Interaction, button: discord.ui.Button):
        runtime = cleanup._runtime()
        if not interaction.guild_id or not runtime or not runtime.es_admin(interaction):
            await interaction.response.send_message("⛔ Solo administradores.", ephemeral=True)
            return

        # Confirmar el clic antes de tocar DB/publicaciones/red de Discord.
        await interaction.response.defer()

        row = cleanup._delete_match(runtime, interaction.guild_id, self.source_message_id)
        if not row:
            await interaction.edit_original_response(
                content="ℹ️ Ese partido ya no existe en la Liga.", embed=None, view=None
            )
            return

        try:
            if cleanup.BOT is not None:
                await league.refresh(runtime, cleanup.BOT, interaction.guild_id)
        except Exception as exc:
            print(f"AJAP Liga: resultado eliminado pero refresh falló: {exc}")

        await interaction.edit_original_response(
            content=(
                "✅ Resultado retirado de la Liga y tabla recalculada.\n"
                f"~~{cleanup._score(row)}~~\n"
                "También se eliminaron sus goleadores y evidencias vinculadas."
            ),
            embed=None,
            view=None,
        )

        if interaction.guild:
            await cleanup._remove_success_reaction(interaction.guild, row)

    @discord.ui.button(label="CANCELAR", emoji="↩️", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content="Operación cancelada.", embed=None, view=None)


# MatchDeleteSelect resuelve este nombre global al ejecutarse, así que reemplazar
# la clase acá mejora el callback sin duplicar el selector/comando principal.
cleanup.ConfirmDeleteResultView = SafeConfirmDeleteResultView
