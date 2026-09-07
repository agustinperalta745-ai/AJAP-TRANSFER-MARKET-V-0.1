"""Radio Pasillo wording for classics resolved by the authoritative GES sync."""

import discord
import classic_result_radio_patch as classics


def _embed_for(match):
    home = discord.utils.escape_markdown(str(match["home_team"]))
    away = discord.utils.escape_markdown(str(match["away_team"]))
    hg = int(match["home_goals"])
    ag = int(match["away_goals"])
    outcome, chicana = classics._chicana(match)
    embed = discord.Embed(
        title="🔥 YA PASÓ EL CLÁSICO",
        description=(
            f"⚔️ **{home} {hg}–{ag} {away}**\n\n"
            f"{outcome}\n\n"
            f"🎙️ **Radio Pasillo:**\n{chicana}"
        ),
        color=discord.Color.red(),
    )
    embed.set_footer(text="📻 Radio Pasillo • Resultado oficial desde GES")
    return embed


def _text_for(match):
    home = discord.utils.escape_markdown(str(match["home_team"]))
    away = discord.utils.escape_markdown(str(match["away_team"]))
    hg = int(match["home_goals"])
    ag = int(match["away_goals"])
    outcome, chicana = classics._chicana(match)
    return (
        "🔥 **YA PASÓ EL CLÁSICO**\n\n"
        f"⚔️ **{home} {hg}–{ag} {away}**\n\n"
        f"{outcome}\n\n"
        f"🎙️ **Radio Pasillo:**\n{chicana}"
    )


classics._embed_for = _embed_for
classics._text_for = _text_for
print("AJPA Radio Pasillo: clásicos finalizados usan copy GES 'Ya pasó el clásico'")
