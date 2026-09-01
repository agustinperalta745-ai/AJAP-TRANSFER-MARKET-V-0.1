"""Final AJPA brand guard for every Discord-facing bot response.

Several historical patches still contain the old AJAP typo in embed footers or
messages. Rewriting every legacy module is fragile because older views can be
reintroduced by later wrappers. This late runtime guard normalizes Discord
output at the transport boundary so users always see the canonical AJPA name.
"""

from __future__ import annotations

import re

import discord


_BRAND_RE = re.compile(r"\bAJAP\b", re.IGNORECASE)


def _brand_text(value):
    if not isinstance(value, str):
        return value
    return _BRAND_RE.sub("AJPA", value)


def _normalize_embed(embed):
    if embed is None or not isinstance(embed, discord.Embed):
        return embed

    if embed.title:
        embed.title = _brand_text(embed.title)
    if embed.description:
        embed.description = _brand_text(embed.description)

    for index, field in enumerate(list(embed.fields)):
        name = _brand_text(field.name)
        value = _brand_text(field.value)
        if name != field.name or value != field.value:
            embed.set_field_at(index, name=name, value=value, inline=field.inline)

    footer = embed.footer
    footer_text = getattr(footer, "text", None)
    if footer_text:
        icon_url = getattr(footer, "icon_url", None)
        kwargs = {"text": _brand_text(footer_text)}
        if icon_url:
            kwargs["icon_url"] = str(icon_url)
        embed.set_footer(**kwargs)

    author = embed.author
    author_name = getattr(author, "name", None)
    if author_name:
        kwargs = {"name": _brand_text(author_name)}
        author_url = getattr(author, "url", None)
        author_icon = getattr(author, "icon_url", None)
        if author_url:
            kwargs["url"] = str(author_url)
        if author_icon:
            kwargs["icon_url"] = str(author_icon)
        embed.set_author(**kwargs)

    return embed


def _normalize_view(view):
    if view is None:
        return view
    for item in getattr(view, "children", ()):
        try:
            if isinstance(getattr(item, "label", None), str):
                item.label = _brand_text(item.label)
            if isinstance(getattr(item, "placeholder", None), str):
                item.placeholder = _brand_text(item.placeholder)
            for option in getattr(item, "options", ()):
                if isinstance(getattr(option, "label", None), str):
                    option.label = _brand_text(option.label)
                if isinstance(getattr(option, "description", None), str):
                    option.description = _brand_text(option.description)
        except Exception:
            # Branding must never break a working Discord interaction.
            continue
    return view


def _normalize_call(args, kwargs):
    args = list(args)
    if args and isinstance(args[0], str):
        args[0] = _brand_text(args[0])

    if isinstance(kwargs.get("content"), str):
        kwargs["content"] = _brand_text(kwargs["content"])

    if kwargs.get("embed") is not None:
        kwargs["embed"] = _normalize_embed(kwargs["embed"])
    if kwargs.get("embeds") is not None:
        kwargs["embeds"] = [_normalize_embed(embed) for embed in kwargs["embeds"]]
    if kwargs.get("view") is not None:
        kwargs["view"] = _normalize_view(kwargs["view"])

    return tuple(args), kwargs


def _wrap_async_method(owner, method_name):
    original = getattr(owner, method_name, None)
    if original is None or getattr(original, "_ajpa_brand_guard", False):
        return

    async def wrapped(self, *args, **kwargs):
        args, kwargs = _normalize_call(args, kwargs)
        return await original(self, *args, **kwargs)

    wrapped._ajpa_brand_guard = True
    wrapped.__name__ = getattr(original, "__name__", method_name)
    wrapped.__doc__ = getattr(original, "__doc__", None)
    setattr(owner, method_name, wrapped)


def apply_brand_identity_guard() -> None:
    # Interactions, normal channel/DM sends, webhook followups and message edits.
    targets = (
        (discord.InteractionResponse, "send_message"),
        (discord.InteractionResponse, "edit_message"),
        (discord.abc.Messageable, "send"),
        (discord.Webhook, "send"),
        (discord.Message, "reply"),
        (discord.Message, "edit"),
        (discord.InteractionMessage, "edit"),
    )
    for owner, method_name in targets:
        _wrap_async_method(owner, method_name)

    print("AJPA brand guard activo: salida Discord normalizada a AJPA")


apply_brand_identity_guard()
