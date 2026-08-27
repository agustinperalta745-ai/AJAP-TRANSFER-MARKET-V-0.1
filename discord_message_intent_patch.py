"""Enable Discord Message Content intent before AJAP constructs the bot.

Discord hides message attachments/content from normal guild messages when the
privileged Message Content intent is not requested at gateway identify time.
AJAP's Liga result reader needs those attachments, so this patch must execute
before core_bot.py calls discord.Intents.default() and creates commands.Bot.
"""

import discord


_ORIGINAL_DEFAULT = discord.Intents.default


def _default_with_message_content(cls, *args, **kwargs):
    intents = _ORIGINAL_DEFAULT(*args, **kwargs)
    intents.guild_messages = True
    intents.dm_messages = True
    intents.message_content = True
    return intents


if not getattr(discord.Intents.default, "_ajap_message_content_enabled", False):
    _default_with_message_content._ajap_message_content_enabled = True
    discord.Intents.default = classmethod(_default_with_message_content)
    print("AJAP Discord intent listo: MESSAGE CONTENT habilitado antes de crear el bot")
