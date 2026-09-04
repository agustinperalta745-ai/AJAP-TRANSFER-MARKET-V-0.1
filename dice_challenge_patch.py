"""Public consensual dice challenge for AJPA Discord.

`/dado jugador:@usuario` creates a public challenge. Both participants must
accept before the bot rolls a d6 for each one. Highest number wins; ties are
rerolled automatically until there is a winner.

This feature is intentionally stateless: it does not touch the AJPA database,
economy, standings, matches, or player statistics.
"""

from __future__ import annotations

import secrets

import discord
from discord import app_commands

import guild_isolation_patch as guild_isolation


_TIMEOUT_SECONDS = 180


def _roll_die() -> int:
    """Return an unbiased integer from 1 through 6 using OS-backed randomness."""
    return secrets.randbelow(6) + 1


def _roll_until_winner() -> list[tuple[int, int]]:
    """Roll both dice until the values differ, preserving every public round."""
    rounds: list[tuple[int, int]] = []
    while True:
        challenger_roll = _roll_die()
        opponent_roll = _roll_die()
        rounds.append((challenger_roll, opponent_roll))
        if challenger_roll != opponent_roll:
            return rounds


def _disable_view(view: discord.ui.View) -> None:
    for item in view.children:
        if hasattr(item, "disabled"):
            item.disabled = True


class DiceChallengeView(discord.ui.View):
    def __init__(self, challenger: discord.Member, opponent: discord.Member):
        super().__init__(timeout=_TIMEOUT_SECONDS)
        self.challenger = challenger
        self.opponent = opponent
        self.accepted: set[int] = set()
        self.message: discord.Message | None = None
        self.resolved = False

    @property
    def participant_ids(self) -> set[int]:
        return {int(self.challenger.id), int(self.opponent.id)}

    def _status(self, member: discord.Member) -> str:
        return "✅ Aceptó" if int(member.id) in self.accepted else "⏳ Falta aceptar"

    def challenge_embed(self) -> discord.Embed:
        embed = discord.Embed(
            title="🎲 Reto de dados",
            description=(
                f"{self.challenger.mention} retó a {self.opponent.mention}.\n\n"
                "Para que la tirada sea válida, **los dos jugadores deben aceptar**. "
                "Después AJPA tira un dado del **1 al 6** para cada uno y el número más alto gana."
            ),
        )
        embed.add_field(
            name=self.challenger.display_name[:256],
            value=self._status(self.challenger),
            inline=True,
        )
        embed.add_field(
            name=self.opponent.display_name[:256],
            value=self._status(self.opponent),
            inline=True,
        )
        embed.set_footer(text="Si hay empate, AJPA vuelve a tirar automáticamente.")
        return embed

    def result_embed(self, rounds: list[tuple[int, int]]) -> discord.Embed:
        final_challenger, final_opponent = rounds[-1]
        winner = self.challenger if final_challenger > final_opponent else self.opponent

        lines: list[str] = []
        for index, (challenger_roll, opponent_roll) in enumerate(rounds, start=1):
            suffix = " → empate, se repite" if challenger_roll == opponent_roll else ""
            lines.append(
                f"**Tirada {index}:** {self.challenger.mention} **{challenger_roll}** "
                f"— **{opponent_roll}** {self.opponent.mention}{suffix}"
            )

        embed = discord.Embed(
            title="🎲 Resultado del reto",
            description="\n".join(lines),
        )
        embed.add_field(
            name="🏆 Ganador",
            value=f"{winner.mention} gana el reto de dados.",
            inline=False,
        )
        if len(rounds) > 1:
            embed.set_footer(text=f"Hubo {len(rounds) - 1} empate(s); se repitió hasta desempatar.")
        else:
            embed.set_footer(text="Resultado generado por AJPA después de la aceptación de ambos jugadores.")
        return embed

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if int(interaction.user.id) not in self.participant_ids:
            await interaction.response.send_message(
                "⛔ Solo los dos jugadores del reto pueden usar estos botones.",
                ephemeral=True,
            )
            return False
        return True

    @discord.ui.button(label="Aceptar", emoji="✅", style=discord.ButtonStyle.success)
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        user_id = int(interaction.user.id)
        if user_id in self.accepted:
            await interaction.response.send_message("✅ Ya aceptaste este reto.", ephemeral=True)
            return

        self.accepted.add(user_id)
        if self.accepted != self.participant_ids:
            await interaction.response.edit_message(embed=self.challenge_embed(), view=self)
            return

        rounds = _roll_until_winner()
        self.resolved = True
        _disable_view(self)
        await interaction.response.edit_message(
            content=None,
            embed=self.result_embed(rounds),
            view=self,
        )
        self.stop()

    @discord.ui.button(label="Rechazar", emoji="✖️", style=discord.ButtonStyle.danger)
    async def reject(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.resolved = True
        _disable_view(self)
        embed = discord.Embed(
            title="❌ Reto rechazado",
            description=f"{interaction.user.mention} rechazó el reto de dados. No se realizó ninguna tirada.",
        )
        await interaction.response.edit_message(content=None, embed=embed, view=self)
        self.stop()

    async def on_timeout(self) -> None:
        if self.resolved:
            return
        self.resolved = True
        _disable_view(self)
        if self.message is None:
            return
        embed = discord.Embed(
            title="⌛ Reto vencido",
            description=(
                f"El reto entre {self.challenger.mention} y {self.opponent.mention} venció porque "
                "no fue aceptado por ambos a tiempo. No se realizó ninguna tirada."
            ),
        )
        try:
            await self.message.edit(content=None, embed=embed, view=self)
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            pass


@app_commands.describe(jugador="Jugador al que querés retar")
async def dice_command(interaction: discord.Interaction, jugador: discord.Member):
    if interaction.guild is None:
        await interaction.response.send_message(
            "Usá `/dado` dentro del servidor de AJPA.",
            ephemeral=True,
        )
        return

    if int(jugador.id) == int(interaction.user.id):
        await interaction.response.send_message(
            "⚠️ Tenés que retar a otro jugador.",
            ephemeral=True,
        )
        return

    if jugador.bot:
        await interaction.response.send_message(
            "⚠️ El reto de dados es entre jugadores, no contra bots.",
            ephemeral=True,
        )
        return

    challenger = interaction.user
    if not isinstance(challenger, discord.Member):
        await interaction.response.send_message(
            "⚠️ No pude identificar tu usuario dentro del servidor.",
            ephemeral=True,
        )
        return

    view = DiceChallengeView(challenger, jugador)
    await interaction.response.send_message(
        content=f"{jugador.mention} · {challenger.mention} te desafió a un reto de dados.",
        embed=view.challenge_embed(),
        view=view,
        allowed_mentions=discord.AllowedMentions(
            users=[challenger, jugador],
            roles=False,
            everyone=False,
            replied_user=False,
        ),
    )
    try:
        view.message = await interaction.original_response()
    except (discord.NotFound, discord.HTTPException):
        view.message = None


def apply_dice_challenge_patch(runtime, bot) -> None:
    """Register the public `/dado` command before Discord connects."""
    if getattr(bot, "_ajpa_dice_challenge_patch", False):
        return

    if bot.tree.get_command("dado") is None:
        bot.tree.command(
            name="dado",
            description="Retá a otro jugador a decidir algo con un dado del 1 al 6",
        )(dice_command)

    bot._ajpa_dice_challenge_patch = True
    print("AJPA Discord: /dado consensuado activo")


# bot.py imports this module before run_bot. Wrap the final guild-isolation
# installer so /dado is registered on the same runtime bot before it connects.
_base_apply_guild_isolation_patch = guild_isolation.apply_guild_isolation_patch


def _apply_guild_isolation_then_dice(runtime, bot):
    _base_apply_guild_isolation_patch(runtime, bot)
    apply_dice_challenge_patch(runtime, bot)


if not getattr(
    guild_isolation.apply_guild_isolation_patch,
    "_ajpa_dice_challenge_wrapped",
    False,
):
    _apply_guild_isolation_then_dice._ajpa_dice_challenge_wrapped = True
    guild_isolation.apply_guild_isolation_patch = _apply_guild_isolation_then_dice
