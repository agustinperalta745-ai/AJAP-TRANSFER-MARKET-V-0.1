"""Evidence-safe Liga result workflow for AJAP.

Rules:
- A clearly detected full-time screenshot can be loaded automatically.
- A halftime/partial screenshot is stored as evidence only and NEVER changes standings.
- If vision cannot prove whether a score is final or partial, the uploader must choose.
- If a later screenshot exists for a match with a saved partial, AJAP asks whether the
  new image is the TOTAL result or a restarted second segment that must be added.
- If there is no final screenshot, the DT may report the final score manually, but the
  opposing DT must confirm it. Rejection goes to Staff review.
- Only one official result for the same pair is accepted automatically; conflicts are
  blocked instead of silently double-counting standings.
"""

from __future__ import annotations

import base64
import json
import re
import urllib.error
import urllib.request

import discord

import guild_isolation_patch as guild_isolation
import league_automation_patch as league
import league_validation_admin_review_patch as strict


APP = None
BOT = None


# ---------------------------------------------------------------------------
# Vision: deliberately conservative about final vs partial.
# ---------------------------------------------------------------------------
def evidence_vision_sync(images):
    api_key = league.os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("Falta OPENAI_API_KEY")

    prompt = """Sos el lector automático de capturas de una liga de PES 6.
Analizá TODAS las imágenes del mismo mensaje como evidencia del mismo partido/envío.
Devolvé SOLAMENTE un objeto JSON válido, sin markdown, con este formato:
{"kind":"result|scorers|both|unknown","match_state":"final|partial|unknown","home_team":"","away_team":"","home_goals":null,"away_goals":null,"scorers":[{"player":"","team":"","goals":1}],"confidence":0.0,"notes":""}

Reglas estrictas:
- result: se ve claramente un marcador y los dos equipos.
- scorers: se ven claramente nombres de jugadores y cuántos goles hicieron.
- both: hay evidencia clara de ambos.
- unknown: no hay suficiente información.
- match_state=final SOLO si la imagen contiene evidencia visual clara de que el partido terminó: pantalla post-partido/resultado final, texto de fin, menú posterior al partido u otra señal inequívoca.
- match_state=partial si se ve entretiempo, primer tiempo, pausa dentro del partido, reloj de primera mitad u otra evidencia clara de que el encuentro todavía no terminó.
- match_state=unknown si se puede leer un marcador pero NO hay evidencia suficiente para saber si es final o parcial.
- NUNCA deduzcas que un marcador es final solo porque parece razonable o porque se ve un score.
- No inventes. Si una parte no se puede leer, omitila o usá unknown.
- confidence es de 0 a 1 y representa la confianza de la extracción completa.
- En scorers, si un jugador aparece varias veces en las capturas de este mensaje, consolidalo en una sola entrada con su total de goles.
- Los nombres de equipos válidos son exactamente: """ + ", ".join(league.TEAMS)

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
            "max_output_tokens": 1400,
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        league.API_URL,
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=75) as res:
            payload = json.loads(res.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:500]
        raise RuntimeError(f"OpenAI API HTTP {exc.code}: {detail}") from exc

    text = league.response_text(payload)
    if not text:
        raise RuntimeError("La API no devolvió texto")
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.I | re.S)
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < start:
        raise RuntimeError("La respuesta de visión no contiene JSON")
    return json.loads(text[start : end + 1])


# ---------------------------------------------------------------------------
# Persistent state.
# ---------------------------------------------------------------------------
def _ensure_schema(runtime, guild_id: int):
    conn = league.db(runtime, int(guild_id))
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS league_result_evidence (
                source_message_id INTEGER PRIMARY KEY,
                guild_id INTEGER NOT NULL,
                source_channel_id INTEGER NOT NULL,
                author_id INTEGER NOT NULL,
                prompt_message_id INTEGER UNIQUE,
                confirmation_message_id INTEGER UNIQUE,
                home_team TEXT NOT NULL,
                away_team TEXT NOT NULL,
                home_goals INTEGER NOT NULL,
                away_goals INTEGER NOT NULL,
                confidence REAL NOT NULL DEFAULT 0,
                match_state TEXT NOT NULL DEFAULT 'unknown',
                payload_json TEXT,
                image_hashes_json TEXT,
                status TEXT NOT NULL DEFAULT 'ESPERANDO_TIPO',
                parent_partial_message_id INTEGER,
                manual_home_goals INTEGER,
                manual_away_goals INTEGER,
                rival_user_id INTEGER,
                resolved_by INTEGER,
                resolved_at DATETIME,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.commit()
    finally:
        conn.close()


def _row(runtime, guild_id: int, *, source_message_id=None, prompt_message_id=None, confirmation_message_id=None):
    _ensure_schema(runtime, guild_id)
    clauses, params = [], []
    if source_message_id is not None:
        clauses.append("source_message_id = ?")
        params.append(int(source_message_id))
    if prompt_message_id is not None:
        clauses.append("prompt_message_id = ?")
        params.append(int(prompt_message_id))
    if confirmation_message_id is not None:
        clauses.append("confirmation_message_id = ?")
        params.append(int(confirmation_message_id))
    if not clauses:
        return None
    conn = league.db(runtime, int(guild_id))
    try:
        return conn.execute(
            "SELECT * FROM league_result_evidence WHERE " + " AND ".join(clauses) + " LIMIT 1",
            tuple(params),
        ).fetchone()
    finally:
        conn.close()


def _stage(runtime, message, score, payload, hashes, status: str, parent_partial_message_id=None):
    home, away, hg, ag = score
    _ensure_schema(runtime, message.guild.id)
    conn = league.db(runtime, message.guild.id)
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            """
            INSERT INTO league_result_evidence
                (source_message_id, guild_id, source_channel_id, author_id,
                 home_team, away_team, home_goals, away_goals, confidence,
                 match_state, payload_json, image_hashes_json, status,
                 parent_partial_message_id, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(source_message_id) DO UPDATE SET
                home_team=excluded.home_team,
                away_team=excluded.away_team,
                home_goals=excluded.home_goals,
                away_goals=excluded.away_goals,
                confidence=excluded.confidence,
                match_state=excluded.match_state,
                payload_json=excluded.payload_json,
                image_hashes_json=excluded.image_hashes_json,
                status=excluded.status,
                parent_partial_message_id=excluded.parent_partial_message_id,
                updated_at=CURRENT_TIMESTAMP
            """,
            (
                int(message.id), int(message.guild.id), int(message.channel.id), int(message.author.id),
                home, away, int(hg), int(ag), float(payload.get("confidence") or 0.0),
                str(payload.get("match_state") or "unknown").casefold(),
                json.dumps(payload, ensure_ascii=False), json.dumps(list(hashes or [])),
                status, int(parent_partial_message_id) if parent_partial_message_id else None,
            ),
        )
        # Once AJAP has staged the image, reposting the exact same evidence must
        # not create a second result workflow.
        for digest in hashes or []:
            conn.execute(
                "INSERT OR IGNORE INTO league_image_hashes (image_hash, source_message_id) VALUES (?, ?)",
                (str(digest), int(message.id)),
            )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _set_prompt(runtime, guild_id: int, source_message_id: int, prompt_message_id: int):
    conn = league.db(runtime, int(guild_id))
    try:
        conn.execute(
            "UPDATE league_result_evidence SET prompt_message_id=?, updated_at=CURRENT_TIMESTAMP WHERE source_message_id=?",
            (int(prompt_message_id), int(source_message_id)),
        )
        conn.commit()
    finally:
        conn.close()


def _update_status(runtime, guild_id: int, source_message_id: int, status: str, *, resolved_by=None):
    conn = league.db(runtime, int(guild_id))
    try:
        conn.execute(
            """
            UPDATE league_result_evidence
            SET status=?, resolved_by=COALESCE(?, resolved_by),
                resolved_at=CASE WHEN ? IS NULL THEN resolved_at ELSE CURRENT_TIMESTAMP END,
                updated_at=CURRENT_TIMESTAMP
            WHERE source_message_id=?
            """,
            (status, int(resolved_by) if resolved_by is not None else None,
             int(resolved_by) if resolved_by is not None else None, int(source_message_id)),
        )
        conn.commit()
    finally:
        conn.close()


def _club_for_user(runtime, guild_id: int, user_id: int):
    conn = league.db(runtime, int(guild_id))
    try:
        row = conn.execute("SELECT name FROM clubs WHERE user_id=? LIMIT 1", (int(user_id),)).fetchone()
    except Exception:
        row = None
    finally:
        conn.close()
    return league.canonical_team(row["name"]) if row else None


def _manager_for_club(runtime, guild_id: int, club: str):
    conn = league.db(runtime, int(guild_id))
    try:
        row = conn.execute(
            "SELECT user_id FROM clubs WHERE name=? COLLATE NOCASE LIMIT 1", (club,)
        ).fetchone()
    except Exception:
        row = None
    finally:
        conn.close()
    return int(row["user_id"]) if row else None


def _member_is_admin(member) -> bool:
    try:
        return bool(member.guild_permissions.administrator)
    except Exception:
        return False


def _uploader_is_party(runtime, message, home: str, away: str) -> bool:
    if _member_is_admin(message.author):
        return True
    club = _club_for_user(runtime, message.guild.id, message.author.id)
    return club in {home, away}


def _same_pair(a_home, a_away, b_home, b_away):
    return {str(a_home).casefold(), str(a_away).casefold()} == {
        str(b_home).casefold(), str(b_away).casefold()
    }


def _pending_partial(runtime, guild_id: int, home: str, away: str, exclude_source=None):
    _ensure_schema(runtime, guild_id)
    conn = league.db(runtime, int(guild_id))
    try:
        rows = conn.execute(
            """
            SELECT * FROM league_result_evidence
            WHERE status='PARCIAL'
            ORDER BY created_at DESC
            """
        ).fetchall()
        for row in rows:
            if exclude_source and int(row["source_message_id"]) == int(exclude_source):
                continue
            if _same_pair(row["home_team"], row["away_team"], home, away):
                return row
        return None
    finally:
        conn.close()


def _existing_official_pair(runtime, guild_id: int, home: str, away: str, exclude_source=None):
    conn = league.db(runtime, int(guild_id))
    try:
        rows = conn.execute(
            "SELECT * FROM league_matches WHERE (home_team=? AND away_team=?) OR (home_team=? AND away_team=?)",
            (home, away, away, home),
        ).fetchall()
        for row in rows:
            if exclude_source is None or int(row["source_message_id"]) != int(exclude_source):
                return row
        return None
    finally:
        conn.close()


def _score_text(row, *, hg=None, ag=None, home=None, away=None):
    home = home or row["home_team"]
    away = away or row["away_team"]
    hg = int(row["home_goals"] if hg is None else hg)
    ag = int(row["away_goals"] if ag is None else ag)
    return f"**{home} {hg}–{ag} {away}**"


def _combined_score(partial, current):
    ph, pa = partial["home_team"], partial["away_team"]
    if str(current["home_team"]).casefold() == str(ph).casefold():
        return ph, pa, int(partial["home_goals"]) + int(current["home_goals"]), int(partial["away_goals"]) + int(current["away_goals"])
    return ph, pa, int(partial["home_goals"]) + int(current["away_goals"]), int(partial["away_goals"]) + int(current["home_goals"])


def _persist_official(runtime, guild_id: int, row, *, home=None, away=None, hg=None, ag=None, include_scorers=True, status="FINAL_CARGADO", resolver_id=None):
    home = home or row["home_team"]
    away = away or row["away_team"]
    hg = int(row["home_goals"] if hg is None else hg)
    ag = int(row["away_goals"] if ag is None else ag)

    duplicate = _existing_official_pair(runtime, guild_id, home, away, exclude_source=row["source_message_id"])
    if duplicate:
        return False, "DUPLICADO", duplicate, 0

    conn = league.db(runtime, int(guild_id))
    scorers_count = 0
    try:
        conn.execute("BEGIN IMMEDIATE")
        existing = conn.execute(
            "SELECT * FROM league_matches WHERE source_message_id=? LIMIT 1",
            (int(row["source_message_id"]),),
        ).fetchone()
        if existing:
            conn.rollback()
            return True, "YA_CARGADO", existing, 0

        conn.execute(
            """
            INSERT INTO league_matches
                (source_message_id, source_channel_id, author_id,
                 home_team, away_team, home_goals, away_goals, confidence)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                int(row["source_message_id"]), int(row["source_channel_id"]), int(row["author_id"]),
                home, away, hg, ag, float(row["confidence"] or 0.0),
            ),
        )

        if include_scorers:
            try:
                payload = json.loads(row["payload_json"] or "{}")
            except Exception:
                payload = {}
            for name, club, goals in league.parsed_scorers(runtime, guild_id, payload):
                conn.execute(
                    """
                    INSERT INTO league_goal_events
                        (source_message_id, player, team, goals, confidence)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (int(row["source_message_id"]), name, club, int(goals), float(row["confidence"] or 0.0)),
                )
                scorers_count += 1

        conn.execute(
            """
            UPDATE league_result_evidence
            SET status=?, resolved_by=COALESCE(?, resolved_by), resolved_at=CURRENT_TIMESTAMP,
                manual_home_goals=CASE WHEN ? THEN ? ELSE manual_home_goals END,
                manual_away_goals=CASE WHEN ? THEN ? ELSE manual_away_goals END,
                updated_at=CURRENT_TIMESTAMP
            WHERE source_message_id=?
            """,
            (
                status, int(resolver_id) if resolver_id is not None else None,
                1 if hg != int(row["home_goals"]) else 0, hg,
                1 if ag != int(row["away_goals"]) else 0, ag,
                int(row["source_message_id"]),
            ),
        )
        league.standings(conn)
        conn.commit()
        return True, "CARGADO", None, scorers_count
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


async def _fetch_source(guild, row):
    channel = guild.get_channel(int(row["source_channel_id"]))
    if channel is None:
        try:
            channel = await guild.fetch_channel(int(row["source_channel_id"]))
        except Exception:
            return None
    try:
        return await channel.fetch_message(int(row["source_message_id"]))
    except Exception:
        return None


async def _mark_official(guild, row, text: str):
    source = await _fetch_source(guild, row)
    if source is None:
        return
    try:
        await source.add_reaction("✅")
    except Exception:
        pass
    try:
        await source.reply(text, mention_author=False)
    except Exception:
        pass


async def _send_conflict_review(guild, row, reason: str):
    source = await _fetch_source(guild, row)
    if source is not None:
        try:
            hashes = json.loads(row["image_hashes_json"] or "[]")
        except Exception:
            hashes = []
        await strict._send_admin_review(source, reason, hashes)


# ---------------------------------------------------------------------------
# Embeds + persistent views.
# ---------------------------------------------------------------------------
def _partial_embed(row):
    embed = discord.Embed(
        title="🟡 RESULTADO PARCIAL GUARDADO",
        description=(
            f"Detecté {_score_text(row)}.\n\n"
            "Este marcador **NO modificó la tabla**. Si después tienen una captura final, mandala normalmente al canal. "
            "Si el partido terminó y no tienen captura final, usá el botón de abajo."
        ),
        color=discord.Color.gold(),
    )
    embed.set_footer(text="Parcial = evidencia pendiente • no suma PJ ni puntos")
    return embed


def _unknown_embed(row):
    embed = discord.Embed(
        title="🧐 ¿ESTE MARCADOR ES FINAL O PARCIAL?",
        description=(
            f"Pude leer {_score_text(row)}, pero la imagen no demuestra con suficiente seguridad si el partido terminó.\n\n"
            "Elegí una opción. Hasta entonces **la tabla no cambia**."
        ),
        color=discord.Color.gold(),
    )
    return embed


def _resume_embed(partial, current):
    home, away, total_h, total_a = _combined_score(partial, current)
    return discord.Embed(
        title="🔄 HAY UN PARCIAL PENDIENTE DE ESTE PARTIDO",
        description=(
            f"Parcial guardado: {_score_text(partial)}\n"
            f"Nueva captura: {_score_text(current)}\n\n"
            "Decime qué representa la nueva captura:\n"
            "• **RESULTADO TOTAL**: el marcador nuevo ya incluye todo el partido.\n"
            f"• **SEGUNDO TRAMO**: el juego se reinició desde 0–0 y AJAP debe sumar ambos → **{home} {total_h}–{total_a} {away}**.\n\n"
            "Hasta elegir, la tabla no cambia."
        ),
        color=discord.Color.gold(),
    )


def _manual_pending_embed(row):
    return discord.Embed(
        title="⏳ RESULTADO SIN CAPTURA • ESPERANDO RIVAL",
        description=(
            f"Se informó como resultado final **{row['home_team']} {row['manual_home_goals']}–{row['manual_away_goals']} {row['away_team']}**.\n\n"
            "Todavía **no modifica la tabla**. Falta la confirmación del DT rival."
        ),
        color=discord.Color.gold(),
    )


class EvidenceChoiceView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="RESULTADO FINAL", emoji="🏁", style=discord.ButtonStyle.success, custom_id="ajap:league:evidence:final")
    async def final(self, interaction: discord.Interaction, button: discord.ui.Button):
        await _classify_final(interaction)

    @discord.ui.button(label="PARCIAL / 1ER TIEMPO", emoji="1️⃣", style=discord.ButtonStyle.secondary, custom_id="ajap:league:evidence:partial")
    async def partial(self, interaction: discord.Interaction, button: discord.ui.Button):
        await _classify_partial(interaction)


class PartialActionsView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="NO TENGO CAPTURA FINAL", emoji="📝", style=discord.ButtonStyle.primary, custom_id="ajap:league:evidence:no-final-photo")
    async def no_photo(self, interaction: discord.Interaction, button: discord.ui.Button):
        await _open_manual_final(interaction)


class ResumeDecisionView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="RESULTADO TOTAL", emoji="🏁", style=discord.ButtonStyle.success, custom_id="ajap:league:evidence:resume-total")
    async def total(self, interaction: discord.Interaction, button: discord.ui.Button):
        await _resolve_resume_total(interaction)

    @discord.ui.button(label="SEGUNDO TRAMO • SUMAR", emoji="➕", style=discord.ButtonStyle.primary, custom_id="ajap:league:evidence:resume-add")
    async def add(self, interaction: discord.Interaction, button: discord.ui.Button):
        await _resolve_resume_add(interaction)


class RivalConfirmationView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="CONFIRMAR RESULTADO", emoji="✅", style=discord.ButtonStyle.success, custom_id="ajap:league:evidence:rival-confirm")
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        await _rival_confirm(interaction)

    @discord.ui.button(label="RECHAZAR", emoji="❌", style=discord.ButtonStyle.danger, custom_id="ajap:league:evidence:rival-reject")
    async def reject(self, interaction: discord.Interaction, button: discord.ui.Button):
        await _rival_reject(interaction)


class ManualFinalModal(discord.ui.Modal):
    def __init__(self, prompt_message_id: int, home: str, away: str):
        super().__init__(title="Resultado final sin captura")
        self.prompt_message_id = int(prompt_message_id)
        self.home = home
        self.away = away
        self.home_goals_input = discord.ui.TextInput(label=f"Goles {home}"[:45], placeholder="Ej: 2", max_length=2)
        self.away_goals_input = discord.ui.TextInput(label=f"Goles {away}"[:45], placeholder="Ej: 1", max_length=2)
        self.add_item(self.home_goals_input)
        self.add_item(self.away_goals_input)

    async def on_submit(self, interaction: discord.Interaction):
        runtime = APP
        if not interaction.guild_id:
            return
        row = _row(runtime, interaction.guild_id, prompt_message_id=self.prompt_message_id)
        if not row or str(row["status"]) != "PARCIAL":
            await interaction.response.send_message("ℹ️ Este parcial ya cambió de estado.", ephemeral=True)
            return
        if int(row["author_id"]) != int(interaction.user.id) and not runtime.es_admin(interaction):
            await interaction.response.send_message("⛔ Solo quien envió el resultado o Staff puede completar este dato.", ephemeral=True)
            return
        try:
            hg = int(str(self.home_goals_input.value).strip())
            ag = int(str(self.away_goals_input.value).strip())
        except ValueError:
            await interaction.response.send_message("⚠️ Los goles deben ser números enteros.", ephemeral=True)
            return
        if not (0 <= hg <= 99 and 0 <= ag <= 99):
            await interaction.response.send_message("⚠️ Marcador fuera de rango.", ephemeral=True)
            return

        reporter_club = _club_for_user(runtime, interaction.guild_id, row["author_id"])
        if reporter_club not in {row["home_team"], row["away_team"]}:
            await interaction.response.send_message(
                "⛔ Para informar un final sin captura tenés que ser el DT de uno de los dos equipos. Staff puede resolverlo desde revisión manual.",
                ephemeral=True,
            )
            return
        rival_club = row["away_team"] if reporter_club == row["home_team"] else row["home_team"]
        rival_id = _manager_for_club(runtime, interaction.guild_id, rival_club)
        if not rival_id:
            await interaction.response.send_message(
                "⚠️ El rival no tiene un DT asignado para confirmar. Mandé el caso a revisión de Staff.",
                ephemeral=True,
            )
            await _send_conflict_review(interaction.guild, row, "Resultado final informado sin captura, pero el club rival no tiene DT asignado para confirmarlo.")
            return

        conn = league.db(runtime, interaction.guild_id)
        try:
            conn.execute(
                """
                UPDATE league_result_evidence
                SET status='MANUAL_PENDIENTE', manual_home_goals=?, manual_away_goals=?,
                    rival_user_id=?, updated_at=CURRENT_TIMESTAMP
                WHERE source_message_id=?
                """,
                (hg, ag, int(rival_id), int(row["source_message_id"])),
            )
            conn.commit()
        finally:
            conn.close()

        channel = interaction.guild.get_channel(int(row["source_channel_id"]))
        if channel is None:
            channel = await interaction.guild.fetch_channel(int(row["source_channel_id"]))
        embed = discord.Embed(
            title="⚠️ CONFIRMAR RESULTADO SIN CAPTURA FINAL",
            description=(
                f"<@{row['author_id']}> informa que el resultado final fue **{row['home_team']} {hg}–{ag} {row['away_team']}**.\n\n"
                f"<@{rival_id}>: confirmá si ese marcador es correcto. **Hasta que confirmes, la tabla no cambia.**"
            ),
            color=discord.Color.gold(),
        )
        confirmation = await channel.send(content=f"<@{rival_id}>", embed=embed, view=RivalConfirmationView())
        conn = league.db(runtime, interaction.guild_id)
        try:
            conn.execute(
                "UPDATE league_result_evidence SET confirmation_message_id=? WHERE source_message_id=?",
                (int(confirmation.id), int(row["source_message_id"])),
            )
            conn.commit()
        finally:
            conn.close()

        try:
            prompt = await channel.fetch_message(int(row["prompt_message_id"]))
            refreshed = _row(runtime, interaction.guild_id, source_message_id=row["source_message_id"])
            await prompt.edit(embed=_manual_pending_embed(refreshed), view=None)
        except Exception:
            pass
        await interaction.response.send_message("✅ Resultado enviado al DT rival para confirmación.", ephemeral=True)


async def _require_prompt_owner(interaction):
    row = _row(APP, interaction.guild_id, prompt_message_id=interaction.message.id)
    if not row:
        await interaction.response.send_message("⚠️ No pude encontrar este envío.", ephemeral=True)
        return None
    if int(row["author_id"]) != int(interaction.user.id) and not APP.es_admin(interaction):
        await interaction.response.send_message("⛔ Solo quien envió la captura puede clasificarla.", ephemeral=True)
        return None
    return row


async def _classify_final(interaction):
    row = await _require_prompt_owner(interaction)
    if not row:
        return
    if str(row["status"]) not in {"ESPERANDO_TIPO", "PARCIAL"}:
        await interaction.response.send_message("ℹ️ Este envío ya fue resuelto.", ephemeral=True)
        return

    pending = _pending_partial(APP, interaction.guild_id, row["home_team"], row["away_team"], exclude_source=row["source_message_id"])
    if pending:
        _update_status(APP, interaction.guild_id, row["source_message_id"], "REANUDACION_PENDIENTE")
        conn = league.db(APP, interaction.guild_id)
        try:
            conn.execute(
                "UPDATE league_result_evidence SET parent_partial_message_id=? WHERE source_message_id=?",
                (int(pending["source_message_id"]), int(row["source_message_id"])),
            )
            conn.commit()
        finally:
            conn.close()
        current = _row(APP, interaction.guild_id, source_message_id=row["source_message_id"])
        await interaction.response.edit_message(embed=_resume_embed(pending, current), view=ResumeDecisionView())
        return

    ok, state, duplicate, scorers = _persist_official(APP, interaction.guild_id, row, resolver_id=interaction.user.id)
    if not ok and state == "DUPLICADO":
        await interaction.response.edit_message(
            embed=discord.Embed(title="⚠️ ESTE CRUCE YA TIENE RESULTADO OFICIAL", description=f"Ya existe **{duplicate['home_team']} {duplicate['home_goals']}–{duplicate['away_goals']} {duplicate['away_team']}**. No cargué otro resultado.", color=discord.Color.gold()),
            view=None,
        )
        await _send_conflict_review(interaction.guild, row, "Se intentó cargar un segundo resultado para un cruce que ya tiene resultado oficial.")
        return
    await interaction.response.edit_message(
        embed=discord.Embed(title="✅ RESULTADO FINAL CARGADO", description=_score_text(row) + "\n\nYa participa del cálculo de 🏆 LIGA.", color=discord.Color.green()),
        view=None,
    )
    extra = f" + {scorers} goleador(es)" if scorers else ""
    await _mark_official(interaction.guild, row, f"✅ Resultado final confirmado: {_score_text(row)}{extra}.")


async def _classify_partial(interaction):
    row = await _require_prompt_owner(interaction)
    if not row:
        return
    if str(row["status"]) not in {"ESPERANDO_TIPO", "PARCIAL"}:
        await interaction.response.send_message("ℹ️ Este envío ya fue resuelto.", ephemeral=True)
        return
    _update_status(APP, interaction.guild_id, row["source_message_id"], "PARCIAL", resolved_by=interaction.user.id)
    current = _row(APP, interaction.guild_id, source_message_id=row["source_message_id"])
    await interaction.response.edit_message(embed=_partial_embed(current), view=PartialActionsView())


async def _open_manual_final(interaction):
    row = await _require_prompt_owner(interaction)
    if not row:
        return
    if str(row["status"]) != "PARCIAL":
        await interaction.response.send_message("ℹ️ Este parcial ya fue resuelto o reemplazado.", ephemeral=True)
        return
    await interaction.response.send_modal(ManualFinalModal(interaction.message.id, row["home_team"], row["away_team"]))


async def _resolve_resume_total(interaction):
    row = await _require_prompt_owner(interaction)
    if not row:
        return
    if str(row["status"]) != "REANUDACION_PENDIENTE":
        await interaction.response.send_message("ℹ️ Este caso ya fue resuelto.", ephemeral=True)
        return
    parent = _row(APP, interaction.guild_id, source_message_id=row["parent_partial_message_id"])
    ok, state, duplicate, scorers = _persist_official(APP, interaction.guild_id, row, resolver_id=interaction.user.id)
    if not ok:
        await interaction.response.edit_message(embed=discord.Embed(title="⚠️ NO SE CARGÓ", description="Este cruce ya tiene otro resultado oficial. El caso fue enviado a Staff.", color=discord.Color.gold()), view=None)
        await _send_conflict_review(interaction.guild, row, "Conflicto al resolver una reanudación: el cruce ya tenía resultado oficial.")
        return
    if parent:
        _update_status(APP, interaction.guild_id, parent["source_message_id"], "CERRADO_POR_TOTAL", resolved_by=interaction.user.id)
        source = await _fetch_source(interaction.guild, parent)
        if source:
            try:
                await source.reply(f"ℹ️ Parcial cerrado: se tomó como oficial la captura final {_score_text(row)}.", mention_author=False)
            except Exception:
                pass
    await interaction.response.edit_message(embed=discord.Embed(title="✅ RESULTADO TOTAL CARGADO", description=_score_text(row) + "\n\nEl parcial anterior no se sumó.", color=discord.Color.green()), view=None)
    await _mark_official(interaction.guild, row, f"✅ Resultado final confirmado: {_score_text(row)}.")


async def _resolve_resume_add(interaction):
    row = await _require_prompt_owner(interaction)
    if not row:
        return
    if str(row["status"]) != "REANUDACION_PENDIENTE":
        await interaction.response.send_message("ℹ️ Este caso ya fue resuelto.", ephemeral=True)
        return
    parent = _row(APP, interaction.guild_id, source_message_id=row["parent_partial_message_id"])
    if not parent:
        await interaction.response.send_message("⚠️ No encontré el parcial anterior.", ephemeral=True)
        return
    home, away, hg, ag = _combined_score(parent, row)
    ok, state, duplicate, _ = _persist_official(
        APP, interaction.guild_id, row, home=home, away=away, hg=hg, ag=ag,
        include_scorers=False, status="FINAL_COMBINADO", resolver_id=interaction.user.id,
    )
    if not ok:
        await interaction.response.edit_message(embed=discord.Embed(title="⚠️ NO SE CARGÓ", description="Este cruce ya tiene otro resultado oficial. El caso fue enviado a Staff.", color=discord.Color.gold()), view=None)
        await _send_conflict_review(interaction.guild, row, "Conflicto al sumar parcial + segundo tramo: el cruce ya tenía resultado oficial.")
        return
    _update_status(APP, interaction.guild_id, parent["source_message_id"], "CERRADO_SUMADO", resolved_by=interaction.user.id)
    await interaction.response.edit_message(
        embed=discord.Embed(title="✅ TRAMOS SUMADOS", description=f"Parcial: {_score_text(parent)}\nSegundo tramo: {_score_text(row)}\n\n**Resultado oficial: {home} {hg}–{ag} {away}**", color=discord.Color.green()),
        view=None,
    )
    await _mark_official(interaction.guild, row, f"✅ Resultado oficial tras sumar ambos tramos: **{home} {hg}–{ag} {away}**.")
    await _mark_official(interaction.guild, parent, f"✅ Este parcial fue usado junto con la reanudación. Resultado oficial: **{home} {hg}–{ag} {away}**.")


async def _rival_confirm(interaction):
    row = _row(APP, interaction.guild_id, confirmation_message_id=interaction.message.id)
    if not row:
        await interaction.response.send_message("⚠️ No pude encontrar esta confirmación.", ephemeral=True)
        return
    if str(row["status"]) != "MANUAL_PENDIENTE":
        await interaction.response.send_message("ℹ️ Este resultado ya fue resuelto.", ephemeral=True)
        return
    if int(interaction.user.id) != int(row["rival_user_id"] or 0) and not APP.es_admin(interaction):
        await interaction.response.send_message("⛔ Solo el DT rival puede confirmar este resultado.", ephemeral=True)
        return
    hg, ag = int(row["manual_home_goals"]), int(row["manual_away_goals"])
    ok, state, duplicate, _ = _persist_official(
        APP, interaction.guild_id, row, hg=hg, ag=ag, include_scorers=False,
        status="MANUAL_CONFIRMADO", resolver_id=interaction.user.id,
    )
    if not ok:
        await interaction.response.edit_message(embed=discord.Embed(title="⚠️ NO SE CARGÓ", description="Este cruce ya tiene otro resultado oficial. Staff recibió el conflicto.", color=discord.Color.gold()), view=None)
        await _send_conflict_review(interaction.guild, row, "El rival confirmó un resultado manual, pero el cruce ya tenía otro resultado oficial.")
        return
    text = f"**{row['home_team']} {hg}–{ag} {row['away_team']}**"
    await interaction.response.edit_message(embed=discord.Embed(title="✅ RESULTADO CONFIRMADO POR EL RIVAL", description=text + "\n\nYa participa del cálculo de 🏆 LIGA.", color=discord.Color.green()), view=None)
    await _mark_official(interaction.guild, row, f"✅ Resultado sin captura final confirmado por el rival: {text}.")


async def _rival_reject(interaction):
    row = _row(APP, interaction.guild_id, confirmation_message_id=interaction.message.id)
    if not row:
        await interaction.response.send_message("⚠️ No pude encontrar esta confirmación.", ephemeral=True)
        return
    if str(row["status"]) != "MANUAL_PENDIENTE":
        await interaction.response.send_message("ℹ️ Este resultado ya fue resuelto.", ephemeral=True)
        return
    if int(interaction.user.id) != int(row["rival_user_id"] or 0) and not APP.es_admin(interaction):
        await interaction.response.send_message("⛔ Solo el DT rival puede rechazar este resultado.", ephemeral=True)
        return
    _update_status(APP, interaction.guild_id, row["source_message_id"], "MANUAL_RECHAZADO", resolved_by=interaction.user.id)
    await interaction.response.edit_message(
        embed=discord.Embed(title="❌ RESULTADO RECHAZADO", description="El rival no confirmó el marcador informado. **La tabla no cambió** y el caso pasó a Staff.", color=discord.Color.red()),
        view=None,
    )
    await _send_conflict_review(interaction.guild, row, "El DT rival rechazó el resultado final informado sin captura. Staff debe resolver el marcador.")


# ---------------------------------------------------------------------------
# Final message handler.
# ---------------------------------------------------------------------------
async def evidence_handle(runtime, bot, message):
    if not message.guild or message.author.bot or not message.attachments:
        return

    _ensure_schema(runtime, message.guild.id)
    conn = league.db(runtime, message.guild.id)
    try:
        cfg = conn.execute("SELECT * FROM league_config WHERE guild_id=?", (message.guild.id,)).fetchone()
        already = conn.execute("SELECT * FROM league_matches WHERE source_message_id=? LIMIT 1", (message.id,)).fetchone()
    finally:
        conn.close()
    if not cfg or not cfg["intake_channel_id"] or message.channel.id != int(cfg["intake_channel_id"]):
        return
    if already:
        try:
            await message.add_reaction("✅")
        except Exception:
            pass
        return
    if not league.os.getenv("OPENAI_API_KEY"):
        await strict._send_admin_review(message, "El lector automático no tiene OPENAI_API_KEY configurada.")
        return

    images, hashes = await league.new_images(runtime, message)
    if not images:
        await message.reply("ℹ️ Esta captura ya fue procesada anteriormente o no contiene una imagen válida.", mention_author=False)
        return

    try:
        payload = await league.analyze(images)
        try:
            confidence = float(payload.get("confidence") or 0.0)
        except (TypeError, ValueError):
            confidence = 0.0
        if confidence < league.MIN_CONF:
            await strict._send_admin_review(
                message,
                f"La captura no alcanzó la confianza mínima de lectura ({confidence:.0%} < {league.MIN_CONF:.0%}).",
                hashes,
            )
            return

        score, error = strict._validated_score(payload)
        if not score:
            await strict._send_admin_review(message, error, hashes)
            return
        home, away, hg, ag = score
        if not _uploader_is_party(runtime, message, home, away):
            await strict._send_admin_review(
                message,
                "La captura fue enviada por un usuario que no figura como DT de ninguno de los dos equipos detectados.",
                hashes,
            )
            return

        pending = _pending_partial(runtime, message.guild.id, home, away, exclude_source=message.id)
        state = str(payload.get("match_state") or "unknown").casefold()

        if pending:
            _stage(runtime, message, score, payload, hashes, "REANUDACION_PENDIENTE", pending["source_message_id"])
            current = _row(runtime, message.guild.id, source_message_id=message.id)
            prompt = await message.reply(embed=_resume_embed(pending, current), view=ResumeDecisionView(), mention_author=False)
            _set_prompt(runtime, message.guild.id, message.id, prompt.id)
            return

        if state == "final":
            _stage(runtime, message, score, payload, hashes, "FINAL_DETECTADO")
            row = _row(runtime, message.guild.id, source_message_id=message.id)
            ok, result_state, duplicate, scorers = _persist_official(runtime, message.guild.id, row)
            if not ok:
                await message.reply(
                    f"⚠️ No cargué {_score_text(row)} porque este cruce ya tiene un resultado oficial: **{duplicate['home_team']} {duplicate['home_goals']}–{duplicate['away_goals']} {duplicate['away_team']}**. El caso pasó a Staff.",
                    mention_author=False,
                )
                await _send_conflict_review(message.guild, row, "Se detectó automáticamente un segundo resultado para un cruce ya cargado.")
                return
            await message.add_reaction("✅")
            extra = f" + **{scorers} goleador(es)**" if scorers else ""
            await message.reply(
                f"✅ Captura final verificada y cargada: {_score_text(row)}{extra}.",
                mention_author=False,
            )
            return

        if state == "partial":
            _stage(runtime, message, score, payload, hashes, "PARCIAL")
            row = _row(runtime, message.guild.id, source_message_id=message.id)
            prompt = await message.reply(embed=_partial_embed(row), view=PartialActionsView(), mention_author=False)
            _set_prompt(runtime, message.guild.id, message.id, prompt.id)
            return

        _stage(runtime, message, score, payload, hashes, "ESPERANDO_TIPO")
        row = _row(runtime, message.guild.id, source_message_id=message.id)
        prompt = await message.reply(embed=_unknown_embed(row), view=EvidenceChoiceView(), mention_author=False)
        _set_prompt(runtime, message.guild.id, message.id, prompt.id)
    except Exception as exc:
        print(f"AJAP Liga evidencia error mensaje={message.id}: {exc}")
        await strict._send_admin_review(message, "Ocurrió un error técnico al analizar o clasificar la captura.", hashes)


def _install(runtime, bot):
    global APP, BOT
    APP, BOT = runtime, bot
    if getattr(runtime, "_ajap_league_result_evidence_patch", False):
        return

    _ensure_schema(runtime, guild_isolation.LEGACY_GUILD_ID)
    league.vision_sync = evidence_vision_sync
    league.handle = evidence_handle

    for view in (EvidenceChoiceView(), PartialActionsView(), ResumeDecisionView(), RivalConfirmationView()):
        try:
            bot.add_view(view)
        except Exception as exc:
            print(f"AJAP Liga evidencia: no se pudo registrar vista persistente: {exc}")

    runtime._ajap_league_result_evidence_patch = True
    print("AJAP Liga evidencia segura activa: final automático + parciales + reanudación + confirmación rival")


_original_apply_guild_isolation_patch = guild_isolation.apply_guild_isolation_patch


def _apply_guild_isolation_then_evidence(runtime, bot):
    _original_apply_guild_isolation_patch(runtime, bot)
    _install(runtime, bot)


if not getattr(guild_isolation.apply_guild_isolation_patch, "_ajap_league_result_evidence_wrapped", False):
    _apply_guild_isolation_then_evidence._ajap_league_result_evidence_wrapped = True
    guild_isolation.apply_guild_isolation_patch = _apply_guild_isolation_then_evidence
