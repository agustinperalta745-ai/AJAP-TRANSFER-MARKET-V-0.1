"""AJPA startup fixes for Staff result evidence and one verified scorer repair.

Python's site module imports usercustomize after sitecustomize. We install a
one-shot import hook and patch league_validation_admin_review_patch as soon as
it is loaded by bot.py.
"""
from __future__ import annotations

import builtins
import sys

_ORIGINAL_IMPORT = builtins.__import__
_PATCHED = False
_FIX_KEY = "verified_atletico_fulham_2_4_20260904_scorers_v1"


def _canonical(strict, value):
    try:
        return strict.league.canonical_team(value)
    except Exception:
        return str(value or "").strip()


async def _apply_verified_atletico_fulham_scorers(strict, runtime, bot, guild):
    """Repair only the verified Atlético 2-4 Fulham match from 04/09/2026.

    Scorer screen shows Fernando Torres at 64' and 87'. Fulham's scorer list has
    Boa Morte plus M. Brown; with a 2-4 final, that is Boa Morte x1 and M. Brown
    x3. The patch is date/score/team bounded and marks itself once applied.
    """
    conn = strict.league.db(runtime, int(guild.id))
    source_id = None
    review_row = None
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS ajap_runtime_fixes (
                fix_key TEXT PRIMARY KEY,
                applied_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        already = conn.execute(
            "SELECT 1 FROM ajap_runtime_fixes WHERE fix_key=? LIMIT 1",
            (_FIX_KEY,),
        ).fetchone()
        if already:
            return False

        rows = conn.execute(
            """
            SELECT * FROM league_matches
            WHERE home_goals=2 AND away_goals=4
              AND substr(COALESCE(created_at,''),1,10)='2026-09-04'
            ORDER BY created_at DESC, id DESC
            LIMIT 30
            """
        ).fetchall()
        target = None
        atl = _canonical(strict, "Atletico de Madrid")
        fulham = _canonical(strict, "Fulham")
        for row in rows:
            if _canonical(strict, row["home_team"]) == atl and _canonical(strict, row["away_team"]) == fulham:
                target = row
                break
        if target is None:
            return False

        source_id = int(target["source_message_id"])
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            "DELETE FROM league_goal_events WHERE source_message_id=?",
            (source_id,),
        )
        scorers = [
            ("Fernando Torres", atl, 2),
            ("Boa Morte", fulham, 1),
            ("M. Brown", fulham, 3),
        ]
        for player, team, goals in scorers:
            conn.execute(
                """
                INSERT INTO league_goal_events
                    (source_message_id, player, team, goals, confidence)
                VALUES (?, ?, ?, ?, 1.0)
                """,
                (source_id, player, team, int(goals)),
            )
        conn.execute(
            "INSERT OR REPLACE INTO ajap_runtime_fixes (fix_key, applied_at) VALUES (?, CURRENT_TIMESTAMP)",
            (_FIX_KEY,),
        )
        try:
            review_row = conn.execute(
                "SELECT * FROM league_manual_reviews WHERE source_message_id=? LIMIT 1",
                (source_id,),
            ).fetchone()
        except Exception:
            review_row = None
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    try:
        await strict.league.refresh(runtime, bot, int(guild.id))
    except Exception as exc:
        print(f"AJAP verified scorer repair: refresh falló: {type(exc).__name__}: {exc}")

    # Refresh the existing Staff scorer card too, so it stops showing pending
    # goals immediately after the DB correction.
    if review_row and review_row["staff_channel_id"] and review_row["staff_message_id"]:
        try:
            pending = sys.modules.get("league_scorer_pending_patch")
            if pending is not None:
                channel = guild.get_channel(int(review_row["staff_channel_id"]))
                if channel is None:
                    channel = await guild.fetch_channel(int(review_row["staff_channel_id"]))
                staff_message = await channel.fetch_message(int(review_row["staff_message_id"]))
                embed, mh, ma = pending._embed(runtime, guild.id, review_row)
                await staff_message.edit(embed=embed, view=None if not (mh or ma) else staff_message.components)
        except Exception as exc:
            print(f"AJAP verified scorer repair: no se pudo refrescar tarjeta Staff: {type(exc).__name__}: {exc}")

    print(
        "AJAP Liga: goleadores verificados corregidos | "
        f"guild={guild.id} source={source_id} | Fernando Torres x2, Boa Morte x1, M. Brown x3"
    )
    return True


def _install_verified_fix(strict):
    guild_isolation = strict.guild_isolation
    previous_apply = guild_isolation.apply_guild_isolation_patch
    if getattr(previous_apply, "_ajap_verified_atl_fulham_fix", False):
        return

    def apply_then_install(runtime, bot):
        previous_apply(runtime, bot)
        if getattr(bot, "_ajap_verified_atl_fulham_listener", False):
            return

        async def on_ready():
            for guild in list(bot.guilds):
                try:
                    await _apply_verified_atletico_fulham_scorers(
                        strict, runtime, bot, guild
                    )
                except Exception as exc:
                    print(
                        "AJAP verified scorer repair falló "
                        f"guild={getattr(guild, 'id', '?')}: {type(exc).__name__}: {exc}"
                    )

        bot.add_listener(on_ready, "on_ready")
        bot._ajap_verified_atl_fulham_listener = True

    apply_then_install._ajap_verified_atl_fulham_fix = True
    guild_isolation.apply_guild_isolation_patch = apply_then_install


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
        # screenshot directly below it; normally image #2 is the PES scorer list.
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
    _install_verified_fix(strict)
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
