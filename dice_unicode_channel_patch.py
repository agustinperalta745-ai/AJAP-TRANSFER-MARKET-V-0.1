"""Make /dado channel matching robust to Discord stylized Unicode names."""

from __future__ import annotations

import unicodedata

import dice_challenge_patch as dice


_SMALL_CAPS = str.maketrans({
    "ᴀ": "a",
    "ʙ": "b",
    "ᴄ": "c",
    "ᴅ": "d",
    "ᴇ": "e",
    "ꜰ": "f",
    "ɢ": "g",
    "ʜ": "h",
    "ɪ": "i",
    "ᴊ": "j",
    "ᴋ": "k",
    "ʟ": "l",
    "ᴍ": "m",
    "ɴ": "n",
    "ᴏ": "o",
    "ᴘ": "p",
    "ʀ": "r",
    "ꜱ": "s",
    "ᴛ": "t",
    "ᴜ": "u",
    "ᴠ": "v",
    "ᴡ": "w",
    "ʏ": "y",
    "ᴢ": "z",
})


def _plain_channel_name(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or "")).casefold()
    text = text.translate(_SMALL_CAPS)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return "".join(ch for ch in text if ch.isalnum())


def _channel_is_allowed(interaction) -> bool:
    channel = getattr(interaction, "channel", None)
    candidates = [channel, getattr(channel, "parent", None)]
    for candidate in candidates:
        normalized = _plain_channel_name(getattr(candidate, "name", ""))
        if "general" in normalized:
            return True
        if "buscar" in normalized and "rival" in normalized:
            return True
    return False


dice._channel_is_allowed = _channel_is_allowed
print("AJPA Discord: /dado reconoce nombres Unicode de General/Buscar Rival")
