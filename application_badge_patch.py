"""Use an application-owned emoji for Manchester City in Discord components.

Guild custom emojis can be rejected by Discord inside select options when the
component is built from a different guild/cache context. Application emojis are
owned by the bot application itself and are valid anywhere the app can render a
component, so they are the stable choice for AJAP's team selector.
"""

from __future__ import annotations

import base64
import os
from pathlib import Path

import aiohttp
import discord

import json_team_selection_patch as json_selector
import team_badge_selector_patch as selector


CITY = "Manchester City"
APP_EMOJI_NAME = "mancity"
ASSET_PATH = Path(__file__).resolve().parent / "assets" / "teams" / "manchester_city_emoji.png"
BOT = None
_APP_EMOJI_ID: int | None = None
_PROVISIONING = False


def _partial_city_emoji():
    if not _APP_EMOJI_ID:
        return None
    return discord.PartialEmoji(name=APP_EMOJI_NAME, id=int(_APP_EMOJI_ID), animated=False)


async def _discord_json(method: str, url: str, *, payload=None):
    token = (os.getenv("DISCORD_TOKEN") or "").strip()
    if not token and BOT is not None:
        token = str(getattr(getattr(BOT, "http", None), "token", "") or "").strip()
    if not token:
        raise RuntimeError("DISCORD_TOKEN no disponible para administrar emoji de aplicación")

    headers = {"Authorization": f"Bot {token}"}
    async with aiohttp.ClientSession(headers=headers) as session:
        async with session.request(method, url, json=payload) as response:
            text = await response.text()
            if response.status < 200 or response.status >= 300:
                raise RuntimeError(f"Discord HTTP {response.status}: {text[:500]}")
            if not text:
                return {}
            return await response.json()


async def _ensure_application_emoji():
    global _APP_EMOJI_ID, _PROVISIONING
    if BOT is None or BOT.user is None or _APP_EMOJI_ID or _PROVISIONING:
        return

    _PROVISIONING = True
    try:
        app_id = int(BOT.user.id)
        base_url = f"https://discord.com/api/v10/applications/{app_id}/emojis"
        listing = await _discord_json("GET", base_url)
        items = listing.get("items", []) if isinstance(listing, dict) else []

        for item in items:
            if str(item.get("name") or "").casefold() == APP_EMOJI_NAME.casefold():
                _APP_EMOJI_ID = int(item["id"])
                print(
                    f"AJAP app emoji OK: :{APP_EMOJI_NAME}: id={_APP_EMOJI_ID}"
                )
                return

        if not ASSET_PATH.is_file():
            raise RuntimeError(f"No existe el asset {ASSET_PATH.name}")

        raw = ASSET_PATH.read_bytes()
        image = "data:image/png;base64," + base64.b64encode(raw).decode("ascii")
        created = await _discord_json(
            "POST",
            base_url,
            payload={"name": APP_EMOJI_NAME, "image": image},
        )
        _APP_EMOJI_ID = int(created["id"])
        print(
            f"AJAP app emoji creado: :{APP_EMOJI_NAME}: id={_APP_EMOJI_ID}"
        )
    except Exception as exc:
        print(
            "WARNING AJAP app emoji Manchester City: "
            f"{type(exc).__name__}: {exc}"
        )
    finally:
        _PROVISIONING = False


async def _on_ready_application_badge():
    await _ensure_application_emoji()


# Selector: only City gets a custom image for now. Every other club keeps the
# safe Unicode country flag, so one invalid custom emoji can never break /mercado.
def _safe_selector_emoji(club: str, country: str):
    if str(club).casefold() == CITY.casefold():
        emoji = _partial_city_emoji()
        if emoji is not None:
            return emoji
    return json_selector._country_emoji(country)


# Embed reliability layer resolves this dynamically. Returning the app emoji here
# also lets City thumbnails use Discord's own CDN instead of a raw external URL.
def _safe_find_badge_emoji(guild, club: str):
    if str(club).casefold() == CITY.casefold():
        return _partial_city_emoji()
    return None


async def _no_guild_badge_provisioning(guild):
    # Guild emojis are no longer needed for component rendering.
    return 0


def apply_application_badge_patch(bot):
    global BOT
    BOT = bot
    if getattr(bot, "_ajap_application_badge_patch", False):
        return

    selector._selector_emoji = _safe_selector_emoji
    selector._find_badge_emoji = _safe_find_badge_emoji
    selector._ensure_guild_badges = _no_guild_badge_provisioning
    bot.add_listener(_on_ready_application_badge, "on_ready")
    bot._ajap_application_badge_patch = True
    print(
        "AJAP escudo City definitivo: application emoji para selector + flags seguras para el resto"
    )


# team_badge_selector_patch receives BOT only when its guild-isolation wrapper is
# finally applied. Wrap that installer so this layer is installed immediately
# afterwards and before Discord connects.
_original_apply_team_badge_selector_patch = selector.apply_team_badge_selector_patch


def _apply_selector_then_application_badge(runtime, bot):
    _original_apply_team_badge_selector_patch(runtime, bot)
    apply_application_badge_patch(bot)


if not getattr(
    selector.apply_team_badge_selector_patch,
    "_ajap_application_badge_wrapped",
    False,
):
    _apply_selector_then_application_badge._ajap_application_badge_wrapped = True
    selector.apply_team_badge_selector_patch = _apply_selector_then_application_badge
