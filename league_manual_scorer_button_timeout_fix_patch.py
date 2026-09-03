"""Make the Staff manual-scorer interaction acknowledge Discord immediately.

The old `Agregar goleador` button queried SQLite before opening its modal, and the
modal submit refreshed league messages before acknowledging the interaction.  A
slow DB/message operation could therefore cross Discord's interaction deadline
and show "La aplicación no ha respondido a tiempo" even though the feature was
otherwise valid.

This patch keeps the same persistent custom_id used by existing cards, so old
buttons start working after deploy without recreating the result cards.
"""

from __future__ import annotations

import discord

import guild_isolation_patch as guild_isolation
import league_automation_patch as league
import league_manual_scorer_entry_patch as entry
import league_validation_admin_review_patch as strict


APP = None
BOT = None


class FastManualScorerModal(discord.ui.Modal, title="Agregar goleador"):
    player = discord.ui.TextInput(
        label="Jugador",
        placeholder="Ej: Diego Milito",
        required=True,
        max_length=100,
    )
    team = discord.ui.TextInput(
        label="Equipo",
        placeholder="Uno de los dos equipos del partido",
        required=True,
        max_length=80,
    )
    goals = discord.ui.TextInput(
        label="Goles de este jugador (total)",
        placeholder="Ej: 2",
        required=True,
        max_length=2,
    )

    def __init__(self, staff_message_id: int):
        super().__init__()
        self.staff_message_id = int(staff_message_id)

    async def on_submit(self, interaction: discord.Interaction):
        # Acknowledge FIRST. Everything below may touch SQLite and Discord.
        await interaction.response.defer(ephemeral=True, thinking=True)

        runtime = APP or entry.APP or strict._runtime()
        if not interaction.guild_id or runtime is None:
            await interaction.followup.send(
                "⚠️ No pude acceder al contexto de este servidor.", ephemeral=True
            )
            return
        if not runtime.es_admin(interaction):
            await interaction.followup.send("⛔ Solo administradores.", ephemeral=True)
            return

        review = entry._review(runtime, interaction.guild_id, self.staff_message_id)
        if not review or str(review["status"] or "").upper() != "RESUELTO":
            await interaction.followup.send(
                "⚠️ Este resultado manual no está disponible para cargar goleadores.",
                ephemeral=True,
            )
            return

        club = entry._resolve_match_club(review, self.team.value)
        if not club:
            await interaction.followup.send(
                f"⚠️ El equipo debe ser **{review['home_team']}** o **{review['away_team']}**.",
                ephemeral=True,
            )
            return

        player = entry._resolve_roster_player(
            runtime, interaction.guild_id, club, self.player.value
        )
        if not player:
            await interaction.followup.send(
                f"⚠️ No encontré **{self.player.value}** en la plantilla registrada de **{club}**.",
                ephemeral=True,
            )
            return

        try:
            goals = int(str(self.goals.value).strip())
        except ValueError:
            await interaction.followup.send(
                "⚠️ Los goles deben ser un número entero.", ephemeral=True
            )
            return

        ok, error = entry._upsert_manual_scorer(
            runtime, interaction.guild_id, review, player, club, goals
        )
        if not ok:
            await interaction.followup.send(f"⚠️ {error}", ephemeral=True)
            return

        bot = BOT or entry.BOT or strict.BOT or interaction.client
        try:
            await league.refresh(runtime, bot, interaction.guild_id)
        except Exception as exc:
            print(f"AJAP Liga: goleador manual guardado pero refresh falló: {exc}")

        try:
            await entry._refresh_staff_card(interaction, review)
        except Exception as exc:
            print(f"AJAP Liga: no se pudo refrescar tarjeta tras goleador manual: {exc}")

        await interaction.followup.send(
            f"✅ Goleador guardado: **{player} — {club} • ⚽ {goals}**.",
            ephemeral=True,
        )


class FastManualScorerView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Agregar goleador",
        emoji="⚽",
        style=discord.ButtonStyle.primary,
        custom_id=entry.PREFIX + "add",
    )
    async def add(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Do NOT touch the DB here. Opening the modal is the interaction response
        # and must happen inside Discord's short component deadline.
        if not interaction.guild_id or interaction.message is None:
            await interaction.response.send_message(
                "⚠️ No pude identificar esta tarjeta.", ephemeral=True
            )
            return
        await interaction.response.send_modal(
            FastManualScorerModal(interaction.message.id)
        )


def _install(runtime, bot):
    global APP, BOT
    APP, BOT = runtime, bot
    if getattr(runtime, "_ajap_manual_scorer_timeout_fix", False):
        return

    # Same custom_id as the historical cards. Registering this last replaces the
    # dispatch target for those existing persistent buttons after every restart.
    try:
        bot.add_view(FastManualScorerView())
    except Exception as exc:
        print(f"AJAP Liga: no se pudo registrar fix de botón goleador: {exc}")

    runtime._ajap_manual_scorer_timeout_fix = True
    print("AJAP Liga: botón Agregar goleador con ACK inmediato activo")


_ORIGINAL_APPLY = guild_isolation.apply_guild_isolation_patch


def _apply(runtime, bot):
    _ORIGINAL_APPLY(runtime, bot)
    _install(runtime, bot)


if not getattr(
    guild_isolation.apply_guild_isolation_patch,
    "_ajap_manual_scorer_timeout_fix_wrapper",
    False,
):
    _apply._ajap_manual_scorer_timeout_fix_wrapper = True
    guild_isolation.apply_guild_isolation_patch = _apply
