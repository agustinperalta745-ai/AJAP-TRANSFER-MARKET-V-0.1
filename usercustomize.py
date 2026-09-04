"""AJPA: Staff review keeps every screenshot from a result message.

Python's site module imports usercustomize after sitecustomize.  We install a
one-shot import hook and patch league_validation_admin_review_patch as soon as
it is loaded by bot.py. No league data is modified here.
"""
from __future__ import annotations

import builtins
import sys

_ORIGINAL_IMPORT = builtins.__import__
_PATCHED = False


def _patch(strict):
    global _PATCHED
    if _PATCHED or getattr(strict, "_ajap_staff_all_images_patch", False):
        return

    original = strict._send_admin_review

    async def wrapped(message, reason: str, hashes=None):
        runtime = strict._runtime()
        had_staff_message = False

        if runtime is not None and getattr(message, "guild", None) is not None:
            try:
                strict._ensure_schema(runtime, message.guild.id)
                conn = strict.league.db(runtime, message.guild.id)
                try:
                    row = conn.execute(
                        "SELECT staff_message_id FROM league_manual_reviews WHERE source_message_id=?",
                        (int(message.id),),
                    ).fetchone()
                    had_staff_message = bool(row and row["staff_message_id"])
                finally:
                    conn.close()
            except Exception:
                had_staff_message = False

        ok = await original(message, reason, hashes)
        if not ok or had_staff_message:
            return ok

        images = [
            attachment
            for attachment in list(getattr(message, "attachments", None) or [])
            if str(getattr(attachment, "content_type", "") or "").startswith("image/")
        ]
        if len(images) <= 1:
            return ok

        channel = strict._staff_channel(message.guild)
        if channel is None:
            return ok

        # The main Staff card already shows image #1. Mirror every additional
        # screenshot directly below it; in normal AJPA result posts this is the
        # PES scorer screen belonging to the same match.
        for index, attachment in enumerate(images[1:], start=2):
            try:
                embed = strict.discord.Embed(
                    title="📸 GOLEADORES / EVIDENCIA DEL MISMO RESULTADO",
                    description=(
                        f"Captura {index}. Revisala antes de completar el partido; "
                        "el bot la tomó del mismo mensaje original."
                    ),
                    color=strict.discord.Color.blurple(),
                )
                embed.set_image(url=attachment.url)
                embed.add_field(
                    name="Mensaje original",
                    value=f"[Abrir resultado]({message.jump_url})",
                    inline=False,
                )
                await channel.send(embed=embed)
            except Exception as exc:
                print(
                    "AJAP Liga: fallo copiando foto adicional a Staff "
                    f"message={getattr(message, 'id', '?')}: {type(exc).__name__}: {exc}"
                )

        return ok

    wrapped._ajap_staff_all_images = True
    strict._send_admin_review = wrapped
    strict._ajap_staff_all_images_patch = True
    _PATCHED = True
    print("AJAP Liga: revisión Staff conserva resultado + fotos de goleadores")


def _import(name, globals=None, locals=None, fromlist=(), level=0):
    module = _ORIGINAL_IMPORT(name, globals, locals, fromlist, level)
    try:
        strict = sys.modules.get("league_validation_admin_review_patch")
        if strict is not None and not _PATCHED:
            _patch(strict)
            builtins.__import__ = _ORIGINAL_IMPORT
    except Exception as exc:
        print(
            "AJAP startup: no se pudo instalar copia de evidencias Staff: "
            f"{type(exc).__name__}: {exc}"
        )
    return module


builtins.__import__ = _import
