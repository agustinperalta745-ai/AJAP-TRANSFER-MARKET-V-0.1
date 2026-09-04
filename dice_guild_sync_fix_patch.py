"""Reliable immediate Discord guild registration for /dado.

The original dice feature is global and also tries to reuse the same Command
object for every guild. Discord clients can temporarily lose the suggestion
after a restart if that guild sync races another startup sync. This final layer
creates a fresh guild-scoped command per server after ready, waits briefly for
other startup handlers to finish, syncs, and verifies that Discord returned
/dado in the synced command list.
"""

from __future__ import annotations

import asyncio

from discord import app_commands

import dice_challenge_patch as dice


_DESCRIPTION = "Retá a otro jugador a decidir algo con un dado del 1 al 6"


def _install_reliable_sync(runtime, bot) -> None:
    if getattr(bot, "_ajpa_dice_reliable_guild_sync", False):
        return

    async def _sync_dice_last_on_ready():
        # Other on_ready handlers can also sync commands. Run last so /dado is
        # the final guild command state Discord receives for this startup.
        await asyncio.sleep(3)

        for guild in list(getattr(bot, "guilds", [])):
            try:
                bot.tree.remove_command("dado", guild=guild)
                guild_command = app_commands.Command(
                    name="dado",
                    description=_DESCRIPTION,
                    callback=dice.dice_command,
                )
                bot.tree.add_command(guild_command, guild=guild, override=True)
                synced = await bot.tree.sync(guild=guild)
                names = {getattr(command, "name", None) for command in synced}
                if "dado" not in names:
                    raise RuntimeError(
                        f"Discord no devolvió /dado al sincronizar guild {guild.id}: {sorted(str(n) for n in names)}"
                    )
                print(
                    "AJPA Discord: /dado confirmado por Discord en guild "
                    f"{guild.id} ({len(synced)} comando(s) guild)"
                )
            except Exception as exc:
                print(
                    "AJPA Discord: sync final de /dado falló en guild "
                    f"{getattr(guild, 'id', None)}: {type(exc).__name__}: {exc}"
                )

    bot.add_listener(_sync_dice_last_on_ready, "on_ready")
    bot._ajpa_dice_reliable_guild_sync = True
    print("AJPA Discord: sync final confiable de /dado instalado")


_base_apply_dice_challenge_patch = dice.apply_dice_challenge_patch


def _apply_dice_with_reliable_sync(runtime, bot) -> None:
    _base_apply_dice_challenge_patch(runtime, bot)
    _install_reliable_sync(runtime, bot)


if not getattr(
    dice.apply_dice_challenge_patch,
    "_ajpa_reliable_guild_sync_wrapped",
    False,
):
    _apply_dice_with_reliable_sync._ajpa_reliable_guild_sync_wrapped = True
    dice.apply_dice_challenge_patch = _apply_dice_with_reliable_sync
