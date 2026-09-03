"""Safe automatic recovery of old Liga review screenshots.

Important rules:
- NEVER resend a failed retry to Staff; the existing review card is enough.
- NEVER duplicate a match that Staff already loaded manually under another source.
- Analyze the original Discord images silently with the newest multisignal reader.
- Only persist when teams + score are valid, the screen is clearly final, and the
  uploader belongs to the match.
- Recover scorer rows from the same payload when they are genuinely identified.
"""

from __future__ import annotations

import asyncio
import hashlib
import mimetypes

import discord

import league_automation_patch as league
import league_multisignal_result_patch as multisignal
import league_result_evidence_patch as evidence
import league_validation_admin_review_patch as strict


_DONE_GUILDS = set()


def _pending_rows(runtime, guild_id: int):
    evidence._ensure_schema(runtime, guild_id)
    strict._ensure_schema(runtime, guild_id)
    conn = league.db(runtime, guild_id)
    try:
        return conn.execute(
            """
            SELECT r.source_message_id, r.source_channel_id,
                   r.staff_channel_id, r.staff_message_id, r.reason
            FROM league_manual_reviews r
            LEFT JOIN league_matches m
              ON m.source_message_id = r.source_message_id
            WHERE UPPER(COALESCE(r.status, 'PENDIENTE'))='PENDIENTE'
              AND m.source_message_id IS NULL
            ORDER BY r.created_at ASC
            LIMIT 250
            """
        ).fetchall()
    finally:
        conn.close()


async def _fetch_text_channel(bot, guild, channel_id: int):
    channel = guild.get_channel(int(channel_id)) if guild else None
    if channel is not None:
        return channel
    try:
        return await bot.fetch_channel(int(channel_id))
    except Exception:
        return None


async def _read_images(message):
    images, hashes = [], []
    for att in message.attachments[: league.MAX_IMAGES]:
        mime = (att.content_type or mimetypes.guess_type(att.filename)[0] or "").split(";")[0]
        if not mime.startswith("image/"):
            continue
        if att.size and att.size > league.MAX_BYTES:
            continue
        try:
            data = await att.read()
        except Exception:
            continue
        if not data:
            continue
        images.append((data, mime))
        hashes.append(hashlib.sha256(data).hexdigest())
    return images, hashes


def _same_official_pair(runtime, guild_id: int, score):
    home, away, hg, ag = score
    conn = league.db(runtime, guild_id)
    try:
        rows = conn.execute(
            """
            SELECT * FROM league_matches
            WHERE (home_team=? AND away_team=?) OR (home_team=? AND away_team=?)
            ORDER BY id DESC
            """,
            (home, away, away, home),
        ).fetchall()
    finally:
        conn.close()

    exact = None
    conflict = None
    for row in rows:
        if row["home_team"] == home and row["away_team"] == away:
            same_score = int(row["home_goals"]) == int(hg) and int(row["away_goals"]) == int(ag)
        else:
            same_score = int(row["home_goals"]) == int(ag) and int(row["away_goals"]) == int(hg)
        if same_score:
            exact = row
            break
        conflict = conflict or row
    return exact, conflict


def _mark_review(runtime, guild_id: int, source_id: int, status: str, score=None):
    conn = league.db(runtime, guild_id)
    try:
        if score:
            home, away, hg, ag = score
            conn.execute(
                """
                UPDATE league_manual_reviews
                SET status=?, resolved_at=CURRENT_TIMESTAMP,
                    home_team=?, away_team=?, home_goals=?, away_goals=?
                WHERE source_message_id=?
                """,
                (status, home, away, int(hg), int(ag), int(source_id)),
            )
        else:
            conn.execute(
                "UPDATE league_manual_reviews SET status=?, resolved_at=CURRENT_TIMESTAMP WHERE source_message_id=?",
                (status, int(source_id)),
            )
        conn.commit()
    finally:
        conn.close()


async def _close_staff_card(bot, guild, row, text=None):
    if not row["staff_channel_id"] or not row["staff_message_id"]:
        return
    channel = await _fetch_text_channel(bot, guild, int(row["staff_channel_id"]))
    if channel is None or not hasattr(channel, "fetch_message"):
        return
    try:
        message = await channel.fetch_message(int(row["staff_message_id"]))
    except Exception:
        return
    try:
        if text:
            embed = discord.Embed(
                title="✅ REVISIÓN CERRADA AUTOMÁTICAMENTE",
                description=text,
                color=discord.Color.green(),
            )
            await message.edit(embed=embed, view=None)
        else:
            await message.edit(view=None)
    except Exception:
        pass


async def _mark_source_ok(source):
    try:
        await source.add_reaction("✅")
    except Exception:
        pass


async def _retry_guild(runtime, bot, guild):
    guild_id = int(guild.id)
    if guild_id in _DONE_GUILDS:
        return
    _DONE_GUILDS.add(guild_id)

    try:
        rows = _pending_rows(runtime, guild_id)
    except Exception as exc:
        print(f"WARNING AJAP safe recovery scan guild={guild_id}: {exc}")
        return

    recovered = 0
    already_loaded = 0
    left_pending = 0

    for row in rows:
        channel = await _fetch_text_channel(bot, guild, int(row["source_channel_id"]))
        if channel is None or not hasattr(channel, "fetch_message"):
            left_pending += 1
            continue
        try:
            source = await channel.fetch_message(int(row["source_message_id"]))
        except Exception:
            left_pending += 1
            continue

        images, hashes = await _read_images(source)
        if not images:
            left_pending += 1
            continue

        try:
            payload = await multisignal.analyze_message(runtime, source, images)
            try:
                confidence = float(payload.get("result_confidence") or payload.get("confidence") or 0.0)
            except (TypeError, ValueError):
                confidence = 0.0
            score, _error = strict._validated_score(payload)
            state = str(payload.get("match_state") or "unknown").casefold()

            # SILENT failure: keep the old review, do not create/repost anything.
            if not score or confidence < league.MIN_CONF or state != "final":
                left_pending += 1
                continue
            if not evidence._uploader_is_party(runtime, source, score[0], score[1]):
                left_pending += 1
                continue

            exact, conflict = _same_official_pair(runtime, guild_id, score)
            if exact is not None:
                _mark_review(runtime, guild_id, int(row["source_message_id"]), "RESUELTO_YA_CARGADO", score)
                await _mark_source_ok(source)
                await _close_staff_card(
                    bot, guild, row,
                    f"Este partido ya estaba cargado en la Liga: **{exact['home_team']} {exact['home_goals']}–{exact['away_goals']} {exact['away_team']}**. No se duplicó.",
                )
                already_loaded += 1
                continue

            # Same pair with a different score needs human judgement, but it
            # already HAS a review card. Never create another one.
            if conflict is not None:
                left_pending += 1
                continue

            # Persist directly instead of calling league.handle again. Calling
            # the public handler was what recreated duplicate Staff reviews.
            evidence._stage(runtime, source, score, payload, hashes, "FINAL_DETECTADO")
            staged = evidence._row(runtime, guild_id, source_message_id=source.id)
            ok, result_state, duplicate, scorers = evidence._persist_official(
                runtime, guild_id, staged
            )
            if not ok:
                # Race/late manual load: if it now matches, close as duplicate;
                # otherwise leave the existing review untouched.
                exact_now, _ = _same_official_pair(runtime, guild_id, score)
                if exact_now is not None:
                    _mark_review(runtime, guild_id, int(row["source_message_id"]), "RESUELTO_YA_CARGADO", score)
                    await _mark_source_ok(source)
                    await _close_staff_card(bot, guild, row, "El resultado ya estaba cargado. No se duplicó.")
                    already_loaded += 1
                else:
                    left_pending += 1
                continue

            _mark_review(runtime, guild_id, int(row["source_message_id"]), "RESUELTO_AUTO", score)
            await _mark_source_ok(source)
            extra = f" • {scorers} goleador(es) recuperados" if scorers else ""
            await _close_staff_card(
                bot, guild, row,
                f"Recuperado desde la captura original: **{score[0]} {score[2]}–{score[3]} {score[1]}**{extra}.",
            )
            recovered += 1
        except Exception as exc:
            # No destructive reset, no new Staff message, no retry loop noise.
            left_pending += 1
            print(
                f"WARNING AJAP safe recovery source={row['source_message_id']}: "
                f"{type(exc).__name__}: {exc}"
            )
        await asyncio.sleep(0.20)

    if recovered or already_loaded:
        try:
            await league.refresh(runtime, bot, guild_id)
        except Exception:
            pass

    print(
        f"AJAP Liga SAFE recovery guild={guild_id}: "
        f"recuperados={recovered} ya_cargados={already_loaded} pendientes_sin_spam={left_pending}"
    )


def install_pending_review_reprocess(runtime, bot):
    if getattr(bot, "_ajap_pending_review_reprocess_listener", False):
        return

    async def _on_ready():
        for guild in list(bot.guilds):
            await _retry_guild(runtime, bot, guild)

    bot.add_listener(_on_ready, "on_ready")
    bot._ajap_pending_review_reprocess_listener = True
    print("AJAP Liga: recuperación segura de revisiones pendientes ACTIVA (sin reenvío Staff)")


try:
    import sys
    from discord.ext import commands

    _ORIGINAL_RUN = commands.Bot.run

    def _run_with_pending_review_reprocess(self, token, *args, **kwargs):
        runtime = sys.modules.get("ajap_bot_runtime")
        if runtime is not None:
            try:
                install_pending_review_reprocess(runtime, self)
            except Exception as exc:
                print(f"WARNING AJAP safe recovery listener install: {exc}")
        return _ORIGINAL_RUN(self, token, *args, **kwargs)

    if not getattr(commands.Bot.run, "_ajap_pending_review_reprocess", False):
        _run_with_pending_review_reprocess._ajap_pending_review_reprocess = True
        commands.Bot.run = _run_with_pending_review_reprocess
except Exception as exc:
    print(f"WARNING AJAP safe recovery patch import: {exc}")
