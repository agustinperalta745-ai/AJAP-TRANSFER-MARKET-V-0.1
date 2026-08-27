"""Reglas duras de resultados + revisión manual Staff para Liga AJAP.

- Solo se cargan partidos entre dos equipos oficiales de league.TEAMS.
- Una captura ilegible/inválida nunca recibe ✅ y genera revisión en canal Staff/PES.
- Staff puede cargar el marcador desde la tarjeta mediante un modal persistente.
- El ✅ del mensaje original aparece solo tras persistir el partido y recalcular standings.
- La tabla muestra posiciones, pero ordena internamente por puntos (3/1/0) y DG.
"""

from __future__ import annotations

import json
import os

import discord

import guild_isolation_patch as guild_isolation
import league_automation_patch as league
import market_channel_report_patch as market_reports

APP = None
BOT = None


def _runtime():
    return APP or market_reports.APP


def _ensure_schema(runtime, guild_id: int):
    conn = league.db(runtime, int(guild_id))
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS league_manual_reviews (
                source_message_id INTEGER PRIMARY KEY,
                guild_id INTEGER NOT NULL,
                source_channel_id INTEGER NOT NULL,
                source_author_id INTEGER,
                staff_channel_id INTEGER,
                staff_message_id INTEGER UNIQUE,
                reason TEXT NOT NULL,
                image_hashes_json TEXT,
                status TEXT NOT NULL DEFAULT 'PENDIENTE',
                resolved_by INTEGER,
                resolved_at DATETIME,
                home_team TEXT,
                away_team TEXT,
                home_goals INTEGER,
                away_goals INTEGER,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.commit()
    finally:
        conn.close()


def _official_team(raw):
    """Devuelve un equipo SOLO si pertenece al listado oficial de la Liga."""
    team = league.canonical_team(raw)
    return team if team in league.TEAMS else None


def _validated_score(payload):
    kind = str(payload.get("kind") or "").casefold()
    if kind not in {"result", "both"}:
        return None, "La imagen no devolvió un marcador final identificable."

    home = _official_team(payload.get("home_team"))
    away = _official_team(payload.get("away_team"))
    if not home or not away:
        return None, (
            "Uno o ambos equipos detectados no pertenecen a la lista oficial de participantes de la Liga."
        )
    if home == away:
        return None, "El resultado detectó el mismo equipo en ambos lados."

    try:
        hg = int(payload.get("home_goals"))
        ag = int(payload.get("away_goals"))
    except (TypeError, ValueError):
        return None, "No se pudo leer un marcador numérico válido."

    if hg < 0 or ag < 0 or hg > 99 or ag > 99:
        return None, "El marcador detectado está fuera de rango."
    return (home, away, hg, ag), None


def _stored_match(runtime, guild_id: int, source_message_id: int):
    conn = league.db(runtime, int(guild_id))
    try:
        row = conn.execute(
            "SELECT * FROM league_matches WHERE source_message_id = ? LIMIT 1",
            (int(source_message_id),),
        ).fetchone()
        if row:
            # Misma operación de cálculo usada al mostrar LIGA.
            league.standings(conn)
        return row
    finally:
        conn.close()


def _review_for_staff_message(runtime, guild_id: int, staff_message_id: int):
    _ensure_schema(runtime, guild_id)
    conn = league.db(runtime, int(guild_id))
    try:
        return conn.execute(
            "SELECT * FROM league_manual_reviews WHERE staff_message_id = ? LIMIT 1",
            (int(staff_message_id),),
        ).fetchone()
    finally:
        conn.close()


def _save_review(runtime, message, reason: str, hashes):
    _ensure_schema(runtime, message.guild.id)
    conn = league.db(runtime, message.guild.id)
    try:
        conn.execute(
            """
            INSERT INTO league_manual_reviews
                (source_message_id, guild_id, source_channel_id, source_author_id,
                 reason, image_hashes_json, status)
            VALUES (?, ?, ?, ?, ?, ?, 'PENDIENTE')
            ON CONFLICT(source_message_id) DO UPDATE SET
                reason = excluded.reason,
                image_hashes_json = COALESCE(excluded.image_hashes_json, league_manual_reviews.image_hashes_json)
            """,
            (
                int(message.id),
                int(message.guild.id),
                int(message.channel.id),
                int(message.author.id),
                str(reason)[:1000],
                json.dumps(list(hashes or [])),
            ),
        )
        conn.commit()
    finally:
        conn.close()


def _store_staff_message(runtime, guild_id: int, source_message_id: int, channel_id: int, message_id: int):
    conn = league.db(runtime, int(guild_id))
    try:
        conn.execute(
            """
            UPDATE league_manual_reviews
            SET staff_channel_id = ?, staff_message_id = ?
            WHERE source_message_id = ?
            """,
            (int(channel_id), int(message_id), int(source_message_id)),
        )
        conn.commit()
    finally:
        conn.close()


def _staff_channel(guild: discord.Guild):
    runtime = _runtime()
    try:
        channel_id = market_reports.get_report_channel_id(guild.id)
    except Exception:
        channel_id = None
    if not channel_id:
        return None
    return guild.get_channel(int(channel_id))


def _review_embed(message, reason: str):
    embed = discord.Embed(
        title="⚠️ RESULTADO PENDIENTE DE CARGA",
        description=(
            "El bot **no pudo validar automáticamente este resultado** y no modificó la Liga.\n\n"
            "Un administrador puede cargarlo manualmente desde esta tarjeta."
        ),
        color=discord.Color.gold(),
    )
    embed.add_field(name="Motivo", value=str(reason)[:1024], inline=False)
    embed.add_field(name="Enviado por", value=message.author.mention, inline=True)
    embed.add_field(name="Canal", value=message.channel.mention, inline=True)
    embed.add_field(name="Mensaje original", value=f"[Abrir resultado]({message.jump_url})", inline=False)
    first_image = next(
        (a for a in message.attachments if str(a.content_type or "").startswith("image/")),
        None,
    )
    if first_image:
        embed.set_image(url=first_image.url)
    embed.set_footer(text="Solo se aceptan cruces entre equipos oficiales de la Liga")
    return embed


async def _send_admin_review(message, reason: str, hashes=None):
    runtime = _runtime()
    _save_review(runtime, message, reason, hashes)

    # Si la revisión ya tiene tarjeta Staff, no duplicarla.
    conn = league.db(runtime, message.guild.id)
    try:
        existing = conn.execute(
            "SELECT staff_message_id FROM league_manual_reviews WHERE source_message_id = ?",
            (int(message.id),),
        ).fetchone()
    finally:
        conn.close()
    if existing and existing["staff_message_id"]:
        return True

    channel = _staff_channel(message.guild)
    if channel is None:
        await message.reply(
            "⚠️ El resultado necesita revisión manual, pero todavía no hay un canal Staff/PES configurado. "
            "Un administrador debe configurar `/canal_movimientos`.",
            mention_author=False,
        )
        return False

    try:
        staff_msg = await channel.send(
            embed=_review_embed(message, reason),
            view=LeagueManualReviewView(),
        )
        _store_staff_message(runtime, message.guild.id, message.id, channel.id, staff_msg.id)
        await message.reply(
            "⚠️ No pude validar este resultado automáticamente. Fue enviado a **revisión administrativa**.",
            mention_author=False,
        )
        return True
    except (discord.Forbidden, discord.HTTPException) as exc:
        print(f"AJAP Liga: no se pudo crear revisión Staff para {message.id}: {exc}")
        return False


class LeagueManualScoreModal(discord.ui.Modal, title="Cargar resultado de Liga"):
    home_team = discord.ui.TextInput(
        label="Equipo local",
        placeholder="Ej: Lazio",
        required=True,
        max_length=80,
    )
    home_goals = discord.ui.TextInput(
        label="Goles local",
        placeholder="Ej: 2",
        required=True,
        max_length=2,
    )
    away_team = discord.ui.TextInput(
        label="Equipo visitante",
        placeholder="Ej: Sevilla",
        required=True,
        max_length=80,
    )
    away_goals = discord.ui.TextInput(
        label="Goles visitante",
        placeholder="Ej: 1",
        required=True,
        max_length=2,
    )

    def __init__(self, staff_message_id: int):
        super().__init__()
        self.staff_message_id = int(staff_message_id)

    async def on_submit(self, interaction: discord.Interaction):
        runtime = _runtime()
        if not interaction.guild_id or not runtime.es_admin(interaction):
            await interaction.response.send_message("⛔ Solo administradores.", ephemeral=True)
            return

        review = _review_for_staff_message(runtime, interaction.guild_id, self.staff_message_id)
        if not review:
            await interaction.response.send_message("⚠️ No pude identificar esta revisión.", ephemeral=True)
            return
        if str(review["status"] or "").upper() != "PENDIENTE":
            await interaction.response.send_message("ℹ️ Este resultado ya fue resuelto.", ephemeral=True)
            return

        home = _official_team(self.home_team.value)
        away = _official_team(self.away_team.value)
        if not home or not away:
            await interaction.response.send_message(
                "⛔ Los dos equipos deben pertenecer a la **lista oficial de equipos que disputan la Liga**.",
                ephemeral=True,
            )
            return
        if home == away:
            await interaction.response.send_message("⛔ No podés cargar el mismo equipo contra sí mismo.", ephemeral=True)
            return
        try:
            hg = int(self.home_goals.value.strip())
            ag = int(self.away_goals.value.strip())
        except ValueError:
            await interaction.response.send_message("⚠️ Los goles deben ser números enteros.", ephemeral=True)
            return
        if hg < 0 or ag < 0 or hg > 99 or ag > 99:
            await interaction.response.send_message("⚠️ Marcador fuera de rango.", ephemeral=True)
            return

        # Bloqueo de duplicado por mensaje de origen.
        if _stored_match(runtime, interaction.guild_id, int(review["source_message_id"])):
            await interaction.response.send_message("ℹ️ Ese mensaje ya tiene un partido cargado.", ephemeral=True)
            return

        conn = league.db(runtime, interaction.guild_id)
        try:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                """
                INSERT INTO league_matches
                    (source_message_id, source_channel_id, author_id,
                     home_team, away_team, home_goals, away_goals, confidence)
                VALUES (?, ?, ?, ?, ?, ?, ?, 1.0)
                """,
                (
                    int(review["source_message_id"]),
                    int(review["source_channel_id"]),
                    int(review["source_author_id"] or interaction.user.id),
                    home,
                    away,
                    hg,
                    ag,
                ),
            )
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
                    int(interaction.user.id), home, away, hg, ag,
                    int(review["source_message_id"]),
                ),
            )
            # Recalcular antes del commit final de confirmación visual.
            league.standings(conn)
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

        persisted = _stored_match(runtime, interaction.guild_id, int(review["source_message_id"]))
        if not persisted:
            await interaction.response.send_message(
                "❌ El resultado no pudo verificarse después de guardarlo; no se confirmó.",
                ephemeral=True,
            )
            return

        resolved = discord.Embed(
            title="✅ RESULTADO CARGADO MANUALMENTE",
            description=f"**{home} {hg}–{ag} {away}**",
            color=discord.Color.green(),
        )
        resolved.add_field(name="Cargado por", value=interaction.user.mention, inline=True)
        resolved.add_field(name="Estado", value="Ya participa del cálculo de 🏆 LIGA", inline=True)
        await interaction.response.edit_message(embed=resolved, view=None)

        # El ✅ del mensaje original sigue teniendo el mismo significado: persistido y reflejado.
        try:
            source_channel = interaction.guild.get_channel(int(review["source_channel_id"]))
            if source_channel is None:
                source_channel = await interaction.guild.fetch_channel(int(review["source_channel_id"]))
            source_message = await source_channel.fetch_message(int(review["source_message_id"]))
            await source_message.add_reaction("✅")
            await source_message.reply(
                f"✅ Resultado cargado manualmente por Staff: **{home} {hg}–{ag} {away}**.",
                mention_author=False,
            )
        except Exception as exc:
            print(f"AJAP Liga: resultado manual guardado pero no se pudo marcar mensaje original: {exc}")


class LeagueManualReviewView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)
        button = discord.ui.Button(
            label="CARGAR RESULTADO",
            emoji="📝",
            style=discord.ButtonStyle.primary,
            custom_id="ajap:league:manual-result",
        )
        button.callback = self._open_modal
        self.add_item(button)

    async def _open_modal(self, interaction: discord.Interaction):
        runtime = _runtime()
        if not runtime or not runtime.es_admin(interaction):
            await interaction.response.send_message("⛔ Solo administradores.", ephemeral=True)
            return
        await interaction.response.send_modal(LeagueManualScoreModal(interaction.message.id))


async def strict_confirmed_handle(runtime, bot, message):
    if not message.guild or message.author.bot or not message.attachments:
        return

    _ensure_schema(runtime, message.guild.id)
    conn = league.db(runtime, message.guild.id)
    try:
        cfg = conn.execute(
            "SELECT * FROM league_config WHERE guild_id = ?",
            (message.guild.id,),
        ).fetchone()
    finally:
        conn.close()

    if not cfg or not cfg["intake_channel_id"] or message.channel.id != int(cfg["intake_channel_id"]):
        return

    # Si el mismo mensaje ya está confirmado en DB, el ✅ es válido.
    if _stored_match(runtime, message.guild.id, message.id):
        try:
            await message.add_reaction("✅")
        except Exception:
            pass
        return

    if not os.getenv("OPENAI_API_KEY"):
        await _send_admin_review(message, "El lector automático no tiene OPENAI_API_KEY configurada.")
        return

    images, hashes = await league.new_images(runtime, message)
    if not images:
        await _send_admin_review(
            message,
            "La imagen no se pudo procesar o ya fue utilizada anteriormente.",
            hashes,
        )
        return

    try:
        payload = await league.analyze(images)
        try:
            confidence = float(payload.get("confidence") or 0.0)
        except (TypeError, ValueError):
            confidence = 0.0

        if confidence < league.MIN_CONF:
            await _send_admin_review(
                message,
                f"La captura no alcanzó la confianza mínima de lectura ({confidence:.0%} < {league.MIN_CONF:.0%}).",
                hashes,
            )
            return

        score, score_error = _validated_score(payload)
        if not score:
            await _send_admin_review(message, score_error, hashes)
            return

        # league.store vuelve a validar y persiste marcador + goleadores si existen.
        score_ok, scorers_ok, scorers_count = league.store(runtime, message, payload, hashes)
        if not score_ok:
            await _send_admin_review(
                message,
                "El marcador parecía válido pero no pudo persistirse automáticamente.",
                hashes,
            )
            return

        persisted = _stored_match(runtime, message.guild.id, message.id)
        if not persisted:
            await _send_admin_review(
                message,
                "El marcador no quedó verificado después del guardado automático.",
                hashes,
            )
            return

        # ÚNICA reacción de confirmación, y recién después de persistencia + standings.
        await message.add_reaction("✅")
        home, away, hg, ag = score
        extra = f" + **{scorers_count} goleador(es)**" if scorers_ok else ""
        await message.reply(
            f"✅ Cargado y reflejado en Liga: **{home} {hg}–{ag} {away}**{extra}.",
            mention_author=False,
        )
    except Exception as exc:
        print(f"AJAP Liga lectura estricta error mensaje={message.id}: {exc}")
        await _send_admin_review(
            message,
            "Ocurrió un error técnico al intentar leer o guardar la captura.",
            hashes,
        )


def _install(runtime, bot):
    global APP, BOT
    APP = runtime
    BOT = bot
    if getattr(runtime, "_ajap_league_strict_review_patch", False):
        return

    # El listener creado por league_automation resuelve league.handle en runtime.
    league.handle = strict_confirmed_handle

    # Vista persistente: el mismo botón resuelve la revisión por staff_message_id.
    try:
        bot.add_view(LeagueManualReviewView())
    except Exception as exc:
        print(f"AJAP Liga: no se pudo registrar vista persistente manual: {exc}")

    runtime._ajap_league_strict_review_patch = True
    print("AJAP Liga: validación equipos oficiales + revisión manual Staff activa")


_original_apply_guild_isolation_patch = guild_isolation.apply_guild_isolation_patch


def _apply_guild_isolation_then_strict_review(runtime, bot):
    _original_apply_guild_isolation_patch(runtime, bot)
    _install(runtime, bot)


if not getattr(
    guild_isolation.apply_guild_isolation_patch,
    "_ajap_league_strict_review_wrapped",
    False,
):
    _apply_guild_isolation_then_strict_review._ajap_league_strict_review_wrapped = True
    guild_isolation.apply_guild_isolation_patch = _apply_guild_isolation_then_strict_review
