"""Parity fix for Staff manual Liga results.

When automatic vision cannot validate a result (for example because PES shows a
licensed/generic club name), Staff can correct the teams/score manually. That
manual path must still behave like every other official result:

- preserve/re-read the original vision payload instead of throwing it away;
- make a scorer-only pass over the original screenshots;
- store only roster-resolved scorers belonging to the two corrected clubs;
- finalize through the evidence pipeline so the GES result queue is triggered;
- refresh standings/scorers and keep the original message audit trail.
"""

from __future__ import annotations

import asyncio
import base64
import json
import mimetypes
import os
import re
import sqlite3
import urllib.error
import urllib.request

import discord

import league_automation_patch as league
import league_result_evidence_patch as evidence
import league_validation_admin_review_patch as strict


_ORIGINAL_ENSURE_SCHEMA = strict._ensure_schema
_ORIGINAL_SEND_ADMIN_REVIEW = strict._send_admin_review


def _ensure_payload_schema(runtime, guild_id: int):
    _ORIGINAL_ENSURE_SCHEMA(runtime, guild_id)
    conn = league.db(runtime, int(guild_id))
    try:
        columns = {
            str(row["name"])
            for row in conn.execute("PRAGMA table_info(league_manual_reviews)").fetchall()
        }
        if "payload_json" not in columns:
            try:
                conn.execute("ALTER TABLE league_manual_reviews ADD COLUMN payload_json TEXT")
                conn.commit()
            except sqlite3.OperationalError as exc:
                # Another interaction/startup may have migrated it first.
                if "duplicate column" not in str(exc).casefold():
                    raise
    finally:
        conn.close()


def _save_review(runtime, message, reason: str, hashes, payload=None):
    _ensure_payload_schema(runtime, message.guild.id)
    hashes_json = json.dumps(list(hashes), ensure_ascii=False) if hashes is not None else None
    payload_json = (
        json.dumps(payload, ensure_ascii=False)
        if isinstance(payload, dict)
        else None
    )
    conn = league.db(runtime, message.guild.id)
    try:
        conn.execute(
            """
            INSERT INTO league_manual_reviews
                (source_message_id, guild_id, source_channel_id, source_author_id,
                 reason, image_hashes_json, payload_json, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'PENDIENTE')
            ON CONFLICT(source_message_id) DO UPDATE SET
                reason = excluded.reason,
                image_hashes_json = COALESCE(
                    excluded.image_hashes_json,
                    league_manual_reviews.image_hashes_json
                ),
                payload_json = COALESCE(
                    excluded.payload_json,
                    league_manual_reviews.payload_json
                )
            """,
            (
                int(message.id),
                int(message.guild.id),
                int(message.channel.id),
                int(message.author.id),
                str(reason)[:1000],
                hashes_json,
                payload_json,
            ),
        )
        conn.commit()
    finally:
        conn.close()


async def _read_source_images(message):
    images = []
    for attachment in message.attachments[: league.MAX_IMAGES]:
        mime = (
            attachment.content_type
            or mimetypes.guess_type(attachment.filename)[0]
            or ""
        ).split(";")[0]
        if not mime.startswith("image/"):
            continue
        if attachment.size and attachment.size > league.MAX_BYTES:
            continue
        try:
            data = await attachment.read()
        except Exception:
            continue
        if data:
            images.append((data, mime))
    return images


async def _recover_full_payload(message):
    if not os.getenv("OPENAI_API_KEY"):
        return None
    images = await _read_source_images(message)
    if not images:
        return None
    try:
        payload = await league.analyze(images)
        return payload if isinstance(payload, dict) else None
    except Exception as exc:
        print(
            "AJAP Liga revisión: no se pudo conservar payload de visión "
            f"mensaje={message.id}: {type(exc).__name__}: {exc}"
        )
        return None


async def _send_admin_review(message, reason: str, hashes=None, payload=None):
    """Save the useful vision payload before delegating to the existing Staff card."""
    runtime = strict._runtime()
    if payload is None:
        payload = await _recover_full_payload(message)

    # Save first. The original sender calls strict._save_review again, but our
    # UPSERT preserves payload_json when that second call has no payload.
    _save_review(runtime, message, reason, hashes, payload)
    return await _ORIGINAL_SEND_ADMIN_REVIEW(message, reason, hashes)


def _json_object(text: str):
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", str(text or "").strip(), flags=re.I | re.S)
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < start:
        raise RuntimeError("La respuesta de goleadores no contiene JSON")
    return json.loads(text[start : end + 1])


def _scorer_vision_sync(images, home: str, away: str):
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return {"scorers": [], "confidence": 0.0}

    prompt = f"""Sos un lector de capturas de PES 6 para AJPA.
Staff ya corrigió y confirmó que el partido oficial es {home} vs {away}.

Tu única tarea es leer GOLEADORES de TODAS las imágenes adjuntas.
No rechaces la lectura si el juego muestra otro nombre, abreviatura, escudo o
nombre genérico/licenciado para alguno de los equipos. Eso ya fue corregido por Staff.

Devolvé SOLAMENTE JSON válido:
{{"scorers":[{{"player":"","side":"home|away|unknown","team_text":"","goals":1}}],"confidence":0.0}}

Reglas:
- Incluí solo nombres de jugadores que realmente sean visibles como autores de goles.
- Si un jugador aparece varias veces, consolidalo con su total de goles.
- side=home si corresponde al equipo de la izquierda/local ({home});
  side=away si corresponde al equipo de la derecha/visitante ({away});
  unknown si la captura no permite saberlo.
- team_text conserva el texto del equipo visible si existe, aunque sea un nombre genérico.
- No inventes goleadores ni completes nombres que no se leen.
- Si no hay goleadores visibles, devolvé scorers=[].
- confidence va de 0 a 1 y mide solo la confianza de esta lectura de goleadores.
"""

    content = [{"type": "input_text", "text": prompt}]
    for data, mime in images:
        content.append(
            {
                "type": "input_image",
                "image_url": f"data:{mime};base64,{base64.b64encode(data).decode('ascii')}",
                "detail": "high",
            }
        )

    body = json.dumps(
        {
            "model": league.MODEL,
            "input": [{"role": "user", "content": content}],
            "max_output_tokens": 900,
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        league.API_URL,
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=75) as response:
            response_payload = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:400]
        raise RuntimeError(f"OpenAI scorers HTTP {exc.code}: {detail}") from exc

    text = league.response_text(response_payload)
    if not text:
        raise RuntimeError("La API no devolvió goleadores")
    return _json_object(text)


async def _scorer_scan(images, home: str, away: str):
    if not images or not os.getenv("OPENAI_API_KEY"):
        return {"scorers": [], "confidence": 0.0}
    try:
        return await asyncio.to_thread(_scorer_vision_sync, images, home, away)
    except Exception as exc:
        print(f"AJAP Liga: lectura manual de goleadores falló: {type(exc).__name__}: {exc}")
        return {"scorers": [], "confidence": 0.0}


def _roster_index(runtime, guild_id: int):
    result = {}
    for row in league.roster(runtime, guild_id):
        name = str(row["name"] or "").strip()
        club = league.canonical_team(row["club"])
        if name:
            result[league.norm(name)] = (name, club)
    return result


def _merge_candidate(target, name, club, goals, confidence):
    key = (league.norm(name), str(club or "").casefold())
    previous = target.get(key)
    item = {
        "player": name,
        "team": club,
        "goals": int(goals),
        "confidence": float(confidence or 0.0),
    }
    if previous is None or int(item["goals"]) > int(previous["goals"]):
        target[key] = item
    elif previous is not None:
        previous["confidence"] = max(
            float(previous.get("confidence") or 0.0),
            float(item.get("confidence") or 0.0),
        )


def _saved_scorer_candidates(runtime, guild_id: int, payload, home: str, away: str):
    if not isinstance(payload, dict) or not payload.get("scorers"):
        return []
    forced = dict(payload)
    forced["kind"] = "both"
    pair = {home, away}
    out = []
    for name, club, goals in league.parsed_scorers(runtime, guild_id, forced):
        if club in pair:
            out.append(
                {
                    "player": name,
                    "team": club,
                    "goals": int(goals),
                    "confidence": float(payload.get("confidence") or 0.0),
                }
            )
    return out


def _scan_scorer_candidates(runtime, guild_id: int, scan, home: str, away: str):
    if not isinstance(scan, dict):
        return []
    roster = _roster_index(runtime, guild_id)
    pair = {home, away}
    confidence = float(scan.get("confidence") or 0.0)
    out = []

    for item in scan.get("scorers") or []:
        if not isinstance(item, dict):
            continue
        raw_name = str(item.get("player") or "").strip()
        if not raw_name:
            continue
        try:
            goals = int(item.get("goals", 1))
        except (TypeError, ValueError):
            continue
        if goals < 1 or goals > 30:
            continue

        side = str(item.get("side") or "unknown").casefold()
        side_team = home if side == "home" else away if side == "away" else None
        raw_team = side_team or item.get("team_text")
        resolved_name, resolved_club = league.canonical_player(
            runtime, guild_id, raw_name, raw_team
        )

        # Only accept a player that resolves back to the registered roster. This
        # prevents a scorer-only pass from inventing an unregistered name.
        roster_row = roster.get(league.norm(resolved_name))
        if not roster_row:
            continue
        canonical_name, roster_club = roster_row
        club = roster_club if roster_club in pair else resolved_club
        if club not in pair:
            continue
        out.append(
            {
                "player": canonical_name,
                "team": club,
                "goals": goals,
                "confidence": confidence,
            }
        )
    return out


def _validate_scorer_totals(candidates, home: str, away: str, hg: int, ag: int):
    limits = {home: int(hg), away: int(ag)}
    totals = {home: 0, away: 0}
    for item in candidates:
        if item["team"] in totals:
            totals[item["team"]] += int(item["goals"])

    invalid_teams = {
        club for club, total in totals.items() if total > int(limits.get(club, 0))
    }
    if invalid_teams:
        print(
            "AJAP Liga: goleadores descartados por exceder marcador manual: "
            + ", ".join(sorted(invalid_teams))
        )
    return [item for item in candidates if item["team"] not in invalid_teams]


async def _recover_scorers(runtime, guild, review, home, away, hg, ag):
    try:
        saved_payload = json.loads(review["payload_json"] or "{}")
    except Exception:
        saved_payload = {}

    source = None
    try:
        channel = guild.get_channel(int(review["source_channel_id"]))
        if channel is None:
            channel = await guild.fetch_channel(int(review["source_channel_id"]))
        source = await channel.fetch_message(int(review["source_message_id"]))
    except Exception as exc:
        print(f"AJAP Liga: no se pudo recuperar captura original para goleadores: {exc}")

    images = await _read_source_images(source) if source is not None else []
    scan = await _scorer_scan(images, home, away) if images else {"scorers": [], "confidence": 0.0}

    merged = {}
    for item in _saved_scorer_candidates(
        runtime, guild.id, saved_payload, home, away
    ):
        _merge_candidate(
            merged,
            item["player"],
            item["team"],
            item["goals"],
            item["confidence"],
        )
    for item in _scan_scorer_candidates(runtime, guild.id, scan, home, away):
        _merge_candidate(
            merged,
            item["player"],
            item["team"],
            item["goals"],
            item["confidence"],
        )

    return _validate_scorer_totals(
        list(merged.values()), home, away, int(hg), int(ag)
    )


def _store_scorers(runtime, guild_id: int, source_message_id: int, scorers):
    if not scorers:
        return 0
    conn = league.db(runtime, int(guild_id))
    try:
        existing = conn.execute(
            "SELECT COUNT(*) AS n FROM league_goal_events WHERE source_message_id=?",
            (int(source_message_id),),
        ).fetchone()
        if existing and int(existing["n"] or 0) > 0:
            return int(existing["n"] or 0)

        conn.execute("BEGIN IMMEDIATE")
        count = 0
        for item in scorers:
            conn.execute(
                """
                INSERT INTO league_goal_events
                    (source_message_id, player, team, goals, confidence)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    int(source_message_id),
                    str(item["player"]),
                    str(item["team"]),
                    int(item["goals"]),
                    max(0.0, min(1.0, float(item.get("confidence") or 0.0))),
                ),
            )
            count += 1
        conn.commit()
        return count
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


async def _edit_staff_review_message(interaction, review, embed):
    try:
        channel = interaction.guild.get_channel(int(review["staff_channel_id"] or 0))
        if channel is None and review["staff_channel_id"]:
            channel = await interaction.guild.fetch_channel(int(review["staff_channel_id"]))
        if channel is None:
            return
        message = await channel.fetch_message(int(review["staff_message_id"]))
        await message.edit(embed=embed, view=None)
    except Exception as exc:
        print(f"AJAP Liga: no se pudo actualizar tarjeta Staff resuelta: {exc}")


async def _manual_submit(self, interaction: discord.Interaction):
    runtime = strict._runtime()
    if not interaction.guild_id or not runtime.es_admin(interaction):
        await interaction.response.send_message("⛔ Solo administradores.", ephemeral=True)
        return

    # Scorer recovery can call vision, so acknowledge the modal immediately.
    await interaction.response.defer(ephemeral=True, thinking=True)

    review = strict._review_for_staff_message(
        runtime, interaction.guild_id, self.staff_message_id
    )
    if not review:
        await interaction.followup.send(
            "⚠️ No pude identificar esta revisión.", ephemeral=True
        )
        return
    if str(review["status"] or "").upper() != "PENDIENTE":
        await interaction.followup.send(
            "ℹ️ Este resultado ya fue resuelto.", ephemeral=True
        )
        return

    home = strict._official_team(self.home_team.value)
    away = strict._official_team(self.away_team.value)
    if not home or not away:
        await interaction.followup.send(
            "⛔ Los dos equipos deben pertenecer a la lista oficial de la Liga.",
            ephemeral=True,
        )
        return
    if home == away:
        await interaction.followup.send(
            "⛔ No podés cargar el mismo equipo contra sí mismo.", ephemeral=True
        )
        return
    try:
        hg = int(self.home_goals.value.strip())
        ag = int(self.away_goals.value.strip())
    except ValueError:
        await interaction.followup.send(
            "⚠️ Los goles deben ser números enteros.", ephemeral=True
        )
        return
    if hg < 0 or ag < 0 or hg > 99 or ag > 99:
        await interaction.followup.send("⚠️ Marcador fuera de rango.", ephemeral=True)
        return

    if strict._stored_match(
        runtime, interaction.guild_id, int(review["source_message_id"])
    ):
        await interaction.followup.send(
            "ℹ️ Ese mensaje ya tiene un partido cargado.", ephemeral=True
        )
        return

    # Read scorers before marking image hashes as consumed.
    scorers = await _recover_scorers(
        runtime, interaction.guild, review, home, away, hg, ag
    )

    try:
        saved_payload = json.loads(review["payload_json"] or "{}")
    except Exception:
        saved_payload = {}

    manual_row = {
        "source_message_id": int(review["source_message_id"]),
        "source_channel_id": int(review["source_channel_id"]),
        "author_id": int(review["source_author_id"] or interaction.user.id),
        "home_team": home,
        "away_team": away,
        "home_goals": int(hg),
        "away_goals": int(ag),
        "confidence": 1.0,
        "payload_json": json.dumps(saved_payload, ensure_ascii=False),
    }

    # Critical parity: use the same official finalizer that the automatic result
    # pipeline uses. league_ges_result_queue_patch wraps this function, therefore
    # a Staff-corrected result also enters #resultados-para-cargar.
    ok, state, duplicate, _ = evidence._persist_official(
        runtime,
        interaction.guild_id,
        manual_row,
        home=home,
        away=away,
        hg=hg,
        ag=ag,
        include_scorers=False,
        status="MANUAL_STAFF",
        resolver_id=interaction.user.id,
    )
    if not ok:
        text = (
            f"Ya existe **{duplicate['home_team']} {duplicate['home_goals']}–"
            f"{duplicate['away_goals']} {duplicate['away_team']}** para este cruce."
            if duplicate
            else "El resultado no pudo cargarse."
        )
        await interaction.followup.send(f"⚠️ {text}", ephemeral=True)
        return

    scorers_count = _store_scorers(
        runtime, interaction.guild_id, int(review["source_message_id"]), scorers
    )

    conn = league.db(runtime, interaction.guild_id)
    try:
        conn.execute("BEGIN IMMEDIATE")
        try:
            hashes = json.loads(review["image_hashes_json"] or "[]")
        except Exception:
            hashes = []
        for digest in hashes:
            conn.execute(
                "INSERT OR IGNORE INTO league_image_hashes (image_hash, source_message_id) VALUES (?, ?)",
                (str(digest), int(review["source_message_id"])),
            )
        conn.execute(
            """
            UPDATE league_manual_reviews
            SET status='RESUELTO', resolved_by=?, resolved_at=CURRENT_TIMESTAMP,
                home_team=?, away_team=?, home_goals=?, away_goals=?
            WHERE source_message_id=?
            """,
            (
                int(interaction.user.id),
                home,
                away,
                int(hg),
                int(ag),
                int(review["source_message_id"]),
            ),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    bot = strict.BOT or evidence.BOT or interaction.client
    try:
        await league.refresh(runtime, bot, interaction.guild_id)
    except Exception as exc:
        print(f"AJAP Liga: resultado manual cargado pero refresh falló: {exc}")

    # Explicitly schedule as a fallback too. If the evidence finalizer was already
    # wrapped by GES, its primary-key reservation makes this second schedule a no-op.
    ges_configured = False
    try:
        import league_ges_result_queue_patch as ges

        ges.APP = runtime
        if ges.BOT is None:
            ges.BOT = bot
        ges_configured = bool(ges._get_channel_id(runtime, interaction.guild_id))
        if ges_configured:
            ges._schedule(
                runtime,
                interaction.guild_id,
                manual_row,
                home=home,
                away=away,
                hg=hg,
                ag=ag,
            )
    except Exception as exc:
        print(f"AJAP Liga: no se pudo reforzar envío GES manual: {exc}")

    resolved = discord.Embed(
        title="✅ RESULTADO CARGADO MANUALMENTE",
        description=f"**{home} {hg}–{ag} {away}**",
        color=discord.Color.green(),
    )
    resolved.add_field(
        name="Cargado por", value=interaction.user.mention, inline=True
    )
    resolved.add_field(
        name="Estado", value="Ya participa del cálculo de 🏆 LIGA", inline=True
    )
    resolved.add_field(
        name="Goleadores",
        value=(
            f"⚽ {scorers_count} registro(s) detectado(s) desde la captura"
            if scorers_count
            else "⚠️ No se pudieron identificar goleadores seguros en la captura"
        ),
        inline=False,
    )
    resolved.add_field(
        name="GES Liga",
        value=(
            "📋 Enviado a resultados para cargar"
            if ges_configured
            else "ℹ️ No hay canal GES configurado"
        ),
        inline=False,
    )
    await _edit_staff_review_message(interaction, review, resolved)

    try:
        source_channel = interaction.guild.get_channel(int(review["source_channel_id"]))
        if source_channel is None:
            source_channel = await interaction.guild.fetch_channel(
                int(review["source_channel_id"])
            )
        source_message = await source_channel.fetch_message(
            int(review["source_message_id"])
        )
        await source_message.add_reaction("✅")
        extra = (
            f" + **{scorers_count} registro(s) de goleador**"
            if scorers_count
            else ""
        )
        await source_message.reply(
            f"✅ Resultado cargado manualmente por Staff: "
            f"**{home} {hg}–{ag} {away}**{extra}.",
            mention_author=False,
        )
    except Exception as exc:
        print(
            "AJAP Liga: resultado manual guardado pero no se pudo marcar "
            f"mensaje original: {exc}"
        )

    await interaction.followup.send(
        (
            f"✅ {home} {hg}–{ag} {away} cargado. "
            + (
                f"Detecté {scorers_count} registro(s) de goleador. "
                if scorers_count
                else "No encontré goleadores suficientemente seguros. "
            )
            + (
                "También quedó enviado a resultados para cargar."
                if ges_configured
                else "No hay canal GES configurado."
            )
        ),
        ephemeral=True,
    )


# Install monkeypatches before guild_isolation's wrapped installers run.
strict._ensure_schema = _ensure_payload_schema
strict._save_review = _save_review
strict._send_admin_review = _send_admin_review
strict.LeagueManualScoreModal.on_submit = _manual_submit

print(
    "AJAP Liga manual parity activo: payload preservado + goleadores + cola GES"
)
