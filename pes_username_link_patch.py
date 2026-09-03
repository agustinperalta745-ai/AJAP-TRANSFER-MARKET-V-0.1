"""AJAP: link Discord managers to their exact PES 6 username.

The PES username is the primary identity signal for result screenshots:
if vision can associate a registered username with one side of the result,
that side is assigned to the manager's *current* AJAP club. Team-name OCR is
kept only as fallback, so unlicensed PES team names do not override a verified
username link.
"""

from __future__ import annotations

import base64
import contextvars
import json
import re
import unicodedata
import urllib.error
import urllib.request

import discord

import guild_isolation_patch as guild_isolation
import league_automation_patch as league
import league_result_feedback_patch as feedback


APP = None
BOT = None

_RESULT_GUILD_ID = contextvars.ContextVar("ajap_pes_result_guild_id", default=None)


def _username_display(value) -> str:
    value = unicodedata.normalize("NFKC", str(value or ""))
    return re.sub(r"\s+", " ", value).strip()


def _username_key(value) -> str:
    value = _username_display(value)
    # PES result/lobby UI often renders a colon immediately after the username.
    # Ignore that visual separator for matching, but preserve the user's saved text.
    if value.endswith(":"):
        value = value[:-1].rstrip()
    return value.casefold()


def _ensure_schema(runtime, guild_id: int):
    conn = league.db(runtime, int(guild_id))
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS pes_username_links (
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                pes_username TEXT NOT NULL,
                username_key TEXT NOT NULL,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (guild_id, user_id),
                UNIQUE (guild_id, username_key)
            )
            """
        )
        conn.commit()
    finally:
        conn.close()


def _club_for_user(runtime, guild_id: int, user_id: int):
    conn = league.db(runtime, int(guild_id))
    try:
        row = conn.execute(
            "SELECT name FROM clubs WHERE user_id=? LIMIT 1",
            (int(user_id),),
        ).fetchone()
    except Exception:
        row = None
    finally:
        conn.close()
    if not row:
        return None
    club = league.canonical_team(row["name"]) or str(row["name"] or "").strip()
    return club if club in league.TEAMS else None


def _link_for_user(runtime, guild_id: int, user_id: int):
    _ensure_schema(runtime, guild_id)
    conn = league.db(runtime, int(guild_id))
    try:
        return conn.execute(
            """
            SELECT guild_id, user_id, pes_username, username_key, updated_at
            FROM pes_username_links
            WHERE guild_id=? AND user_id=?
            LIMIT 1
            """,
            (int(guild_id), int(user_id)),
        ).fetchone()
    finally:
        conn.close()


def _active_links(runtime, guild_id: int):
    """Return exact PES-name mappings resolved against current club ownership."""
    _ensure_schema(runtime, guild_id)
    conn = league.db(runtime, int(guild_id))
    try:
        rows = conn.execute(
            """
            SELECT l.user_id, l.pes_username, l.username_key, c.name AS club
            FROM pes_username_links l
            JOIN clubs c ON c.user_id = l.user_id
            WHERE l.guild_id=?
            ORDER BY l.updated_at DESC
            """,
            (int(guild_id),),
        ).fetchall()
    except Exception:
        rows = []
    finally:
        conn.close()

    out = {}
    for row in rows:
        club = league.canonical_team(row["club"]) or str(row["club"] or "").strip()
        if club not in league.TEAMS:
            continue
        key = _username_key(row["pes_username"])
        if not key:
            continue
        out[key] = {
            "user_id": int(row["user_id"]),
            "pes_username": str(row["pes_username"]),
            "club": club,
        }
    return out


def _save_link(runtime, guild_id: int, user_id: int, raw_username: str):
    username = _username_display(raw_username)
    key = _username_key(username)
    if not username:
        raise ValueError("El nombre de usuario PES no puede quedar vacío.")
    if len(username) > 40:
        raise ValueError("El nombre de usuario PES es demasiado largo.")
    if "\n" in username or "\r" in username:
        raise ValueError("El nombre de usuario PES debe ir en una sola línea.")

    _ensure_schema(runtime, guild_id)
    conn = league.db(runtime, int(guild_id))
    try:
        conn.execute("BEGIN IMMEDIATE")
        duplicate = conn.execute(
            """
            SELECT user_id, pes_username
            FROM pes_username_links
            WHERE guild_id=? AND username_key=? AND user_id<>?
            LIMIT 1
            """,
            (int(guild_id), key, int(user_id)),
        ).fetchone()
        if duplicate:
            conn.rollback()
            raise ValueError(
                f'El usuario PES "{duplicate["pes_username"]}" ya está enlazado a otro DT.'
            )
        conn.execute(
            """
            INSERT INTO pes_username_links
                (guild_id, user_id, pes_username, username_key, updated_at)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(guild_id, user_id) DO UPDATE SET
                pes_username=excluded.pes_username,
                username_key=excluded.username_key,
                updated_at=CURRENT_TIMESTAMP
            """,
            (int(guild_id), int(user_id), username, key),
        )
        conn.commit()
    except Exception:
        if conn.in_transaction:
            conn.rollback()
        raise
    finally:
        conn.close()
    return username


def _mapping_prompt(runtime, guild_id: int | None) -> str:
    if guild_id is None:
        return "No hay un servidor AJAP asociado a este análisis."
    links = _active_links(runtime, guild_id)
    if not links:
        return "Todavía no hay nombres de usuario PES enlazados en este servidor."
    lines = [
        f'- {json.dumps(item["pes_username"], ensure_ascii=False)} => {item["club"]}'
        for item in links.values()
    ]
    return "Nombres de usuario PES enlazados (coincidencia exacta):\n" + "\n".join(lines)


def pes_vision_sync(images):
    """Read the normal PES evidence plus side-specific registered usernames."""
    api_key = league.os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("Falta OPENAI_API_KEY")

    guild_id = _RESULT_GUILD_ID.get()
    mapping = _mapping_prompt(APP, guild_id)
    prompt = """Sos el lector automático de capturas de una liga de PES 6.
Analizá TODAS las imágenes del mismo mensaje como evidencia del mismo partido/envío.
Devolvé SOLAMENTE un objeto JSON válido, sin markdown, con este formato:
{"kind":"result|scorers|both|unknown","match_state":"final|partial|unknown","home_team":"","away_team":"","home_goals":null,"away_goals":null,"home_pes_username":"","away_pes_username":"","pes_usernames":[{"username":"","side":"home|away|unknown"}],"scorers":[{"player":"","team":"","goals":1}],"confidence":0.0,"notes":""}

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
- Leé también el NOMBRE DE USUARIO de PES que aparece en zonas como "Jugador", perfil online, barra inferior o panel del jugador.
- Copiá el username tal como se ve. Un ":" pegado al final puede ser solo un separador visual de PES.
- Solo llená home_pes_username o away_pes_username cuando la posición/layout de la pantalla permita asociar ese username con ese lado del marcador. Si se ve el nombre pero no podés probar el lado, usá side="unknown" en pes_usernames y NO adivines.
- Si un username visible coincide con uno de los nombres enlazados de abajo y podés asociarlo a un lado, ESE ENLACE TIENE PRIORIDAD sobre el nombre/escudo del equipo mostrado por PES. Para ese lado, home_team/away_team debe ser el club AJAP enlazado.
- Esto es especialmente importante porque PES 6 puede mostrar nombres de clubes sin licencia o distintos del club AJAP usado por el DT.
- IMPORTANTE PES 6: si aparece "Middlebrook", ese equipo es BOLTON WANDERERS.
- Mantené la orientación exacta del marcador: no inviertas goles al reemplazar un equipo por el club enlazado.
- Los nombres de equipos AJAP válidos son exactamente: """ + ", ".join(league.TEAMS) + "\n\n" + mapping

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
            "max_output_tokens": 1600,
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
            response = json.loads(res.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:500]
        raise RuntimeError(f"OpenAI API HTTP {exc.code}: {detail}") from exc

    text = league.response_text(response)
    if not text:
        raise RuntimeError("La API no devolvió texto")
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.I | re.S)
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < start:
        raise RuntimeError("La respuesta de visión no contiene JSON")
    payload = json.loads(text[start : end + 1])

    # Keep the older explicit PES alias as a defensive fallback.
    for field in ("home_team", "away_team"):
        if league.norm(payload.get(field)) == "middlebrook":
            payload[field] = "Bolton Wanderers"
    return payload


def _resolve_payload_with_links(runtime, guild_id: int | None, payload):
    if not isinstance(payload, dict) or guild_id is None:
        return payload
    links = _active_links(runtime, guild_id)
    if not links:
        return payload

    # Support both the dedicated side fields and the array form returned by vision.
    side_names = {
        "home": payload.get("home_pes_username"),
        "away": payload.get("away_pes_username"),
    }
    for item in payload.get("pes_usernames") or []:
        if not isinstance(item, dict):
            continue
        side = str(item.get("side") or "").casefold()
        if side in side_names and not side_names[side]:
            side_names[side] = item.get("username")

    applied = []
    applied_keys = set()
    for side, raw_username in side_names.items():
        key = _username_key(raw_username)
        match = links.get(key)
        if not match:
            continue
        team_field = f"{side}_team"
        username_field = f"{side}_pes_username"
        payload[username_field] = match["pes_username"]
        payload[team_field] = match["club"]
        applied_keys.add(key)
        applied.append(
            {
                "side": side,
                "pes_username": match["pes_username"],
                "user_id": match["user_id"],
                "club": match["club"],
            }
        )

    # If vision recognizes a registered username but genuinely cannot associate it
    # with a scoreboard side, never fall back to a guessed team name. Force the
    # existing evidence workflow into Staff review instead of risking bad stats.
    ambiguous = []
    for item in payload.get("pes_usernames") or []:
        if not isinstance(item, dict):
            continue
        if str(item.get("side") or "").casefold() not in {"", "unknown"}:
            continue
        key = _username_key(item.get("username"))
        match = links.get(key)
        if match and key not in applied_keys:
            ambiguous.append(match["pes_username"])
    if ambiguous:
        payload["pes_link_ambiguous"] = sorted(set(ambiguous))
        try:
            payload["confidence"] = min(float(payload.get("confidence") or 0.0), 0.0)
        except (TypeError, ValueError):
            payload["confidence"] = 0.0

    if applied:
        payload["pes_link_applied"] = applied
        notes = str(payload.get("notes") or "").strip()
        audit = "; ".join(
            f'{item["side"]}={item["pes_username"]}->{item["club"]}'
            for item in applied
        )
        payload["notes"] = (notes + (" | " if notes else "") + "AJAP PES link: " + audit)[:1000]
    return payload


class PesUsernameModal(discord.ui.Modal):
    def __init__(self, current_username: str | None = None):
        super().__init__(title="Enlazar usuario de PES")
        self.username_input = discord.ui.TextInput(
            label="Nombre de usuario PES",
            placeholder="Escribilo exactamente como aparece en PES 6",
            default=current_username or None,
            required=True,
            max_length=40,
        )
        self.add_item(self.username_input)

    async def on_submit(self, interaction: discord.Interaction):
        if not interaction.guild_id:
            await interaction.response.send_message(
                "⚠️ Este enlace solo se puede guardar dentro del servidor.",
                ephemeral=True,
            )
            return

        club = _club_for_user(APP, interaction.guild_id, interaction.user.id)
        if not club:
            await interaction.response.send_message(
                "⛔ Primero tenés que tener un club asignado para enlazar tu usuario de PES.",
                ephemeral=True,
            )
            return

        try:
            username = _save_link(
                APP,
                interaction.guild_id,
                interaction.user.id,
                str(self.username_input.value),
            )
        except ValueError as exc:
            await interaction.response.send_message(f"⚠️ {exc}", ephemeral=True)
            return
        except Exception as exc:
            print(f"AJAP usuario PES: error guardando enlace: {type(exc).__name__}: {exc}")
            await interaction.response.send_message(
                "❌ No pude guardar el enlace. No se modificó nada.",
                ephemeral=True,
            )
            return

        await interaction.response.send_message(
            (
                f'✅ Usuario PES **{discord.utils.escape_markdown(username)}** enlazado a **{club}**.\n'
                "Desde ahora, cuando una captura permita reconocer ese usuario en un lado del marcador, "
                "**el enlace de usuario tendrá prioridad sobre el nombre del equipo que muestre PES**."
            ),
            ephemeral=True,
        )


class PesUsernameButton(discord.ui.Button):
    def __init__(self):
        super().__init__(
            label="ENLAZAR USUARIO PES",
            emoji="🎮",
            style=discord.ButtonStyle.secondary,
            row=3,
            custom_id="ajap_manager_pes_username",
        )

    async def callback(self, interaction: discord.Interaction):
        if not interaction.guild_id:
            await interaction.response.send_message(
                "⚠️ Esta opción solo funciona dentro del servidor.",
                ephemeral=True,
            )
            return
        club = _club_for_user(APP, interaction.guild_id, interaction.user.id)
        if not club:
            await interaction.response.send_message(
                "⛔ Primero tenés que tener un club asignado.",
                ephemeral=True,
            )
            return
        current = _link_for_user(APP, interaction.guild_id, interaction.user.id)
        await interaction.response.send_modal(
            PesUsernameModal(current["pes_username"] if current else None)
        )


def _wrap_market_view(runtime):
    base_view = runtime.MercadoView
    if getattr(base_view, "_ajap_pes_username_link_view", False):
        return

    class PesLinkedMarketView(base_view):
        _ajap_pes_username_link_view = True

        def __init__(self):
            super().__init__()
            if not any(
                getattr(item, "custom_id", None) == "ajap_manager_pes_username"
                for item in self.children
            ):
                self.add_item(PesUsernameButton())

    PesLinkedMarketView.__name__ = getattr(base_view, "__name__", "MercadoView")
    runtime.MercadoView = PesLinkedMarketView


def _install(runtime, bot):
    global APP, BOT
    APP, BOT = runtime, bot
    if getattr(runtime, "_ajap_pes_username_link_patch", False):
        return

    _ensure_schema(runtime, guild_isolation.LEGACY_GUILD_ID)
    _wrap_market_view(runtime)

    original_analyze = league.analyze

    async def analyze_with_pes_links(images):
        payload = await original_analyze(images)
        return _resolve_payload_with_links(APP, _RESULT_GUILD_ID.get(), payload)

    league.vision_sync = pes_vision_sync
    league.analyze = analyze_with_pes_links

    # league_result_feedback_patch owns the final on_message handler and its
    # Bot.run guard re-installs that handler immediately before Discord connects.
    # Wrap the feedback function itself so the guild context survives that guard.
    original_feedback = feedback._feedback_handle
    if not getattr(original_feedback, "_ajap_pes_username_context", False):
        async def feedback_with_pes_context(runtime_arg, bot_arg, message):
            guild_id = getattr(getattr(message, "guild", None), "id", None)
            token = _RESULT_GUILD_ID.set(int(guild_id) if guild_id is not None else None)
            try:
                if guild_id is not None:
                    _ensure_schema(runtime_arg, int(guild_id))
                return await original_feedback(runtime_arg, bot_arg, message)
            finally:
                _RESULT_GUILD_ID.reset(token)

        feedback_with_pes_context.__name__ = "_feedback_handle"
        feedback_with_pes_context._ajap_pes_username_context = True
        feedback._feedback_handle = feedback_with_pes_context
        league.handle = feedback_with_pes_context
    else:
        league.handle = original_feedback

    runtime.pes_username_for_user = lambda guild_id, user_id: (
        (row := _link_for_user(runtime, guild_id, user_id))
        and row["pes_username"]
    )
    runtime._ajap_pes_username_link_patch = True
    print("AJAP usuario PES activo: enlace por DT + prioridad de username en capturas")


_ORIGINAL_APPLY = guild_isolation.apply_guild_isolation_patch


def _apply(runtime, bot):
    _ORIGINAL_APPLY(runtime, bot)
    _install(runtime, bot)


if not getattr(
    guild_isolation.apply_guild_isolation_patch,
    "_ajap_pes_username_link_wrapper",
    False,
):
    _apply._ajap_pes_username_link_wrapper = True
    guild_isolation.apply_guild_isolation_patch = _apply
