"""Módulo Liga AJAP: resultados y goleadores automáticos desde capturas."""

import asyncio
import base64
import difflib
import hashlib
import json
import mimetypes
import os
import re
import sqlite3
import unicodedata
import urllib.error
import urllib.request
from pathlib import Path

import discord

MODEL = os.getenv("OPENAI_VISION_MODEL", "gpt-5.4-mini")
MIN_CONF = float(os.getenv("AJAP_LEAGUE_VISION_CONFIDENCE", "0.80"))
API_URL = "https://api.openai.com/v1/responses"
MAX_IMAGES = 6
MAX_BYTES = 12 * 1024 * 1024

TEAMS = [
    "Tottenham Hotspur",
    "Newcastle United",
    "Aston Villa",
    "Everton",
    "West Ham United",
    "Manchester City",
    "Bolton Wanderers",
    "Middlesbrough",
    "Fulham",
    "Lazio",
    "Fiorentina",
    "Torino",
    "Villarreal",
    "Sevilla",
    "Real Betis",
    "Atlético de Madrid",
    "Real Zaragoza",
    "Celta de Vigo",
    "Olympique de Lyon",
    "Olympique de Marsella",
    "París Saint-Germain (PSG)",
    "Ajax",
    "Porto",
    "Benfica",
]

ALIASES = {
    "psg": "París Saint-Germain (PSG)",
    "paris saint germain": "París Saint-Germain (PSG)",
    "paris": "París Saint-Germain (PSG)",
    "lyon": "Olympique de Lyon",
    "olympique lyon": "Olympique de Lyon",
    "marseille": "Olympique de Marsella",
    "marsella": "Olympique de Marsella",
    "olympique marseille": "Olympique de Marsella",
    "newcastle": "Newcastle United",
    "tottenham": "Tottenham Hotspur",
    "spurs": "Tottenham Hotspur",
    "man city": "Manchester City",
    "manchester city": "Manchester City",
    "atletico": "Atlético de Madrid",
    "atletico madrid": "Atlético de Madrid",
    "zaragoza": "Real Zaragoza",
    "betis": "Real Betis",
    "west ham": "West Ham United",
    "middlesboro": "Middlesbrough",
    "middlesborough": "Middlesbrough",
}


def norm(value):
    value = unicodedata.normalize("NFKD", str(value or ""))
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = value.casefold().replace("&", " and ")
    return re.sub(r"[^a-z0-9]+", " ", value).strip()


def schema(conn):
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS league_config (
            guild_id INTEGER PRIMARY KEY,
            intake_channel_id INTEGER,
            table_channel_id INTEGER,
            standings_message_id INTEGER,
            scorers_message_id INTEGER,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS league_matches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_message_id INTEGER NOT NULL UNIQUE,
            source_channel_id INTEGER NOT NULL,
            author_id INTEGER NOT NULL,
            home_team TEXT NOT NULL,
            away_team TEXT NOT NULL,
            home_goals INTEGER NOT NULL,
            away_goals INTEGER NOT NULL,
            confidence REAL NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS league_goal_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source_message_id INTEGER NOT NULL,
            player TEXT NOT NULL,
            team TEXT,
            goals INTEGER NOT NULL DEFAULT 1,
            confidence REAL NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS league_image_hashes (
            image_hash TEXT PRIMARY KEY,
            source_message_id INTEGER NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        """
    )
    conn.commit()


def db(runtime, guild_id, must_exist=False):
    if hasattr(runtime, "guild_db_path"):
        path = Path(runtime.guild_db_path(int(guild_id)))
    else:
        path = Path(runtime.DB_PATH)
    if must_exist and not path.exists():
        return None
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    schema(conn)
    return conn


def admin(interaction):
    return bool(
        interaction.guild
        and isinstance(interaction.user, discord.Member)
        and interaction.user.guild_permissions.administrator
    )


def canonical_team(raw):
    key = norm(raw)
    if not key:
        return None
    if key in ALIASES:
        return ALIASES[key]
    exact = {norm(name): name for name in TEAMS}
    if key in exact:
        return exact[key]
    hit = difflib.get_close_matches(key, exact.keys(), n=1, cutoff=0.72)
    return exact[hit[0]] if hit else None


def roster(runtime, guild_id):
    conn = db(runtime, guild_id)
    try:
        return conn.execute("SELECT name, club FROM roster_players").fetchall()
    except sqlite3.OperationalError:
        return []
    finally:
        conn.close()


def canonical_player(runtime, guild_id, raw, raw_team=None):
    raw = str(raw or "").strip()
    if not raw:
        return None, canonical_team(raw_team)
    rows = roster(runtime, guild_id)
    key = norm(raw)
    exact = {norm(row["name"]): row for row in rows}
    row = exact.get(key)
    if row:
        return row["name"], canonical_team(row["club"]) or canonical_team(raw_team)
    hit = difflib.get_close_matches(key, exact.keys(), n=1, cutoff=0.82)
    if hit:
        row = exact[hit[0]]
        return row["name"], canonical_team(row["club"]) or canonical_team(raw_team)
    return raw[:100], canonical_team(raw_team)


def standings(conn):
    table = {
        t: {"team": t, "pj": 0, "pg": 0, "pe": 0, "pp": 0, "gf": 0, "gc": 0, "pts": 0}
        for t in TEAMS
    }
    for row in conn.execute("SELECT home_team,away_team,home_goals,away_goals FROM league_matches"):
        h = table.get(row["home_team"])
        a = table.get(row["away_team"])
        if not h or not a:
            continue
        hg, ag = int(row["home_goals"]), int(row["away_goals"])
        h["pj"] += 1
        a["pj"] += 1
        h["gf"] += hg
        h["gc"] += ag
        a["gf"] += ag
        a["gc"] += hg
        if hg > ag:
            h["pg"] += 1
            a["pp"] += 1
            h["pts"] += 3
        elif ag > hg:
            a["pg"] += 1
            h["pp"] += 1
            a["pts"] += 3
        else:
            h["pe"] += 1
            a["pe"] += 1
            h["pts"] += 1
            a["pts"] += 1
    rows = list(table.values())
    rows.sort(
        key=lambda x: (
            -x["pts"],
            -(x["gf"] - x["gc"]),
            -x["gf"],
            -x["pg"],
            norm(x["team"]),
        )
    )
    return rows[:24]


def standings_embed(conn):
    rows = standings(conn)
    lines = [f"**P{i}** — {row['team']}" for i, row in enumerate(rows, 1)]
    embed = discord.Embed(
        title="🏆 Tabla de posiciones",
        description="\n".join(lines) or "Todavía no hay equipos.",
    )
    embed.set_footer(text="Se actualiza automáticamente con las capturas de resultados")
    return embed


def scorers_embed(conn):
    rows = conn.execute(
        """
        SELECT player, team, SUM(goals) AS goals
        FROM league_goal_events
        GROUP BY player COLLATE NOCASE, COALESCE(team, '') COLLATE NOCASE
        ORDER BY goals DESC, player COLLATE NOCASE ASC
        LIMIT 30
        """
    ).fetchall()
    if rows:
        lines = []
        for i, row in enumerate(rows, 1):
            club = f" — {row['team']}" if row["team"] else ""
            lines.append(f"**{i}. {row['player']}**{club} • ⚽ {row['goals']}")
        desc = "\n".join(lines)
    else:
        desc = "Todavía no hay goles registrados."
    embed = discord.Embed(title="⚽ Tabla de goleadores", description=desc)
    embed.set_footer(text="Se actualiza automáticamente con las capturas de goles")
    return embed


async def refresh(runtime, bot, guild_id):
    conn = db(runtime, guild_id)
    try:
        cfg = conn.execute("SELECT * FROM league_config WHERE guild_id = ?", (guild_id,)).fetchone()
        if not cfg or not cfg["table_channel_id"]:
            return
        channel = bot.get_channel(int(cfg["table_channel_id"]))
        if channel is None:
            try:
                channel = await bot.fetch_channel(int(cfg["table_channel_id"]))
            except Exception:
                return

        async def upsert(message_id, embed):
            if message_id:
                try:
                    msg = await channel.fetch_message(int(message_id))
                    await msg.edit(embed=embed)
                    return msg.id
                except Exception:
                    pass
            msg = await channel.send(embed=embed)
            return msg.id

        standings_id = await upsert(cfg["standings_message_id"], standings_embed(conn))
        scorers_id = await upsert(cfg["scorers_message_id"], scorers_embed(conn))
        conn.execute(
            """
            UPDATE league_config
            SET standings_message_id = ?, scorers_message_id = ?, updated_at = CURRENT_TIMESTAMP
            WHERE guild_id = ?
            """,
            (standings_id, scorers_id, guild_id),
        )
        conn.commit()
    finally:
        conn.close()


def response_text(payload):
    if isinstance(payload.get("output_text"), str) and payload["output_text"].strip():
        return payload["output_text"].strip()
    parts = []
    for item in payload.get("output", []):
        for content in item.get("content", []) if isinstance(item, dict) else []:
            text = content.get("text") if isinstance(content, dict) else None
            if isinstance(text, str):
                parts.append(text)
    return "\n".join(parts).strip()


def vision_sync(images):
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("Falta OPENAI_API_KEY")
    prompt = """Sos el lector automático de capturas de una liga de PES 6.
Analizá TODAS las imágenes del mismo mensaje como evidencia del mismo partido/envío.
Devolvé SOLAMENTE un objeto JSON válido, sin markdown, con este formato:
{"kind":"result|scorers|both|unknown","home_team":"","away_team":"","home_goals":null,"away_goals":null,"scorers":[{"player":"","team":"","goals":1}],"confidence":0.0,"notes":""}

Reglas:
- result: se ve claramente el marcador final y los dos equipos.
- scorers: se ven claramente nombres de jugadores y cuántos goles hicieron.
- both: hay evidencia clara de ambos.
- unknown: no hay suficiente información.
- No inventes. Si una parte no se puede leer, omitila o usá unknown.
- confidence es de 0 a 1 y debe representar la confianza de la extracción completa.
- En scorers, si un jugador aparece varias veces en las capturas de este mensaje, consolidalo en una sola entrada con su total de goles.
- Los nombres de equipos válidos son exactamente: """ + ", ".join(TEAMS)
    content = [{"type": "input_text", "text": prompt}]
    for data, mime in images:
        b64 = base64.b64encode(data).decode("ascii")
        content.append(
            {
                "type": "input_image",
                "image_url": f"data:{mime};base64,{b64}",
                "detail": "high",
            }
        )
    body = json.dumps(
        {
            "model": MODEL,
            "input": [{"role": "user", "content": content}],
            "max_output_tokens": 1200,
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        API_URL,
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
    text = response_text(payload)
    if not text:
        raise RuntimeError("La API no devolvió texto")
    text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text.strip(), flags=re.I | re.S)
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end < start:
        raise RuntimeError("La respuesta de visión no contiene JSON")
    return json.loads(text[start : end + 1])


async def analyze(images):
    return await asyncio.to_thread(vision_sync, images)


async def new_images(runtime, message):
    conn = db(runtime, message.guild.id)
    try:
        known = {row["image_hash"] for row in conn.execute("SELECT image_hash FROM league_image_hashes")}
    finally:
        conn.close()
    output, hashes = [], []
    for att in message.attachments[:MAX_IMAGES]:
        mime = (att.content_type or mimetypes.guess_type(att.filename)[0] or "").split(";")[0]
        if not mime.startswith("image/"):
            continue
        if att.size and att.size > MAX_BYTES:
            continue
        data = await att.read()
        digest = hashlib.sha256(data).hexdigest()
        if digest in known or digest in hashes:
            continue
        output.append((data, mime))
        hashes.append(digest)
    return output, hashes


def parsed_score(payload):
    kind = str(payload.get("kind") or "").casefold()
    if kind not in {"result", "both"}:
        return None
    home, away = canonical_team(payload.get("home_team")), canonical_team(payload.get("away_team"))
    if not home or not away or home == away:
        return None
    try:
        hg, ag = int(payload.get("home_goals")), int(payload.get("away_goals"))
    except (TypeError, ValueError):
        return None
    if hg < 0 or ag < 0 or hg > 99 or ag > 99:
        return None
    return home, away, hg, ag


def parsed_scorers(runtime, guild_id, payload):
    kind = str(payload.get("kind") or "").casefold()
    if kind not in {"scorers", "both"}:
        return []
    out = []
    for item in payload.get("scorers") or []:
        if not isinstance(item, dict):
            continue
        name, club = canonical_player(runtime, guild_id, item.get("player"), item.get("team"))
        try:
            goals = int(item.get("goals", 1))
        except (TypeError, ValueError):
            continue
        if name and 1 <= goals <= 30:
            out.append((name, club, goals))
    return out


def store(runtime, message, payload, hashes):
    confidence = float(payload.get("confidence") or 0.0)
    score = parsed_score(payload)
    scorers = parsed_scorers(runtime, message.guild.id, payload)
    if not score and not scorers:
        return False, False, 0
    conn = db(runtime, message.guild.id)
    try:
        already = conn.execute(
            "SELECT 1 FROM league_matches WHERE source_message_id = ? LIMIT 1",
            (message.id,),
        ).fetchone() or conn.execute(
            "SELECT 1 FROM league_goal_events WHERE source_message_id = ? LIMIT 1",
            (message.id,),
        ).fetchone()
        if already:
            return False, False, 0
        if score:
            home, away, hg, ag = score
            conn.execute(
                """
                INSERT INTO league_matches
                (source_message_id,source_channel_id,author_id,home_team,away_team,home_goals,away_goals,confidence)
                VALUES (?,?,?,?,?,?,?,?)
                """,
                (message.id, message.channel.id, message.author.id, home, away, hg, ag, confidence),
            )
        for name, club, goals in scorers:
            conn.execute(
                """
                INSERT INTO league_goal_events
                (source_message_id,player,team,goals,confidence)
                VALUES (?,?,?,?,?)
                """,
                (message.id, name, club, goals, confidence),
            )
        for digest in hashes:
            conn.execute(
                "INSERT OR IGNORE INTO league_image_hashes (image_hash,source_message_id) VALUES (?,?)",
                (digest, message.id),
            )
        conn.commit()
        return bool(score), bool(scorers), len(scorers)
    finally:
        conn.close()


async def remove_hourglass(message):
    try:
        await message.remove_reaction("⏳", message.guild.me)
    except Exception:
        pass


async def handle(runtime, bot, message):
    if not message.guild or message.author.bot or not message.attachments:
        return
    conn = db(runtime, message.guild.id)
    try:
        cfg = conn.execute(
            "SELECT * FROM league_config WHERE guild_id = ?", (message.guild.id,)
        ).fetchone()
    finally:
        conn.close()
    if not cfg or not cfg["intake_channel_id"] or message.channel.id != int(cfg["intake_channel_id"]):
        return
    if not os.getenv("OPENAI_API_KEY"):
        await message.reply("⚠️ El lector automático todavía no tiene configurada `OPENAI_API_KEY`.", mention_author=False)
        return
    images, hashes = await new_images(runtime, message)
    if not images:
        try:
            await message.add_reaction("♻️")
        except Exception:
            pass
        return
    try:
        await message.add_reaction("⏳")
    except Exception:
        pass
    try:
        payload = await analyze(images)
        try:
            confidence = float(payload.get("confidence") or 0.0)
        except (TypeError, ValueError):
            confidence = 0.0
        if confidence < MIN_CONF:
            await remove_hourglass(message)
            await message.add_reaction("⚠️")
            await message.reply(
                "⚠️ No pude leer esta captura con suficiente seguridad. No cargué nada; mandá una foto más clara.",
                mention_author=False,
            )
            return
        score_ok, scorers_ok, scorers_count = store(runtime, message, payload, hashes)
        await remove_hourglass(message)
        if not score_ok and not scorers_ok:
            await message.add_reaction("⚠️")
            await message.reply(
                "⚠️ No encontré un resultado o goleadores válidos. No se modificaron las tablas.",
                mention_author=False,
            )
            return
        await refresh(runtime, bot, message.guild.id)
        await message.add_reaction("✅")
        bits = []
        if score_ok:
            s = parsed_score(payload)
            bits.append(f"resultado **{s[0]} {s[2]}–{s[3]} {s[1]}**")
        if scorers_ok:
            bits.append(f"**{scorers_count} goleador(es)**")
        await message.reply("✅ Cargado automáticamente: " + " + ".join(bits) + ".", mention_author=False)
    except Exception as exc:
        await remove_hourglass(message)
        try:
            await message.add_reaction("❌")
        except Exception:
            pass
        print(f"AJAP League error mensaje={message.id}: {exc}")
        await message.reply(
            "❌ No pude procesar estas imágenes. No se modificaron las tablas.",
            mention_author=False,
        )


def apply_league_automation_patch(runtime, bot):
    if getattr(runtime, "_ajap_league_automation_patch", False):
        return

    # Necesario para que discord.py entregue adjuntos de mensajes normales de forma fiable.
    bot.intents.message_content = True
    with runtime.db() as conn:
        schema(conn)

    @bot.tree.command(name="liga_configurar", description="Configura los canales automáticos de la liga")
    async def liga_configurar(
        interaction: discord.Interaction,
        canal_resultados: discord.TextChannel,
        canal_tablas: discord.TextChannel,
    ):
        if not admin(interaction):
            await interaction.response.send_message("⛔ Solo administradores.", ephemeral=True)
            return
        # Fuerza la creación/clonado de la DB de este guild bajo el contexto de interacción.
        with runtime.db() as guild_conn:
            schema(guild_conn)
        conn = db(runtime, interaction.guild_id)
        try:
            conn.execute(
                """
                INSERT INTO league_config (guild_id,intake_channel_id,table_channel_id,standings_message_id,scorers_message_id,updated_at)
                VALUES (?,?,?,NULL,NULL,CURRENT_TIMESTAMP)
                ON CONFLICT(guild_id) DO UPDATE SET
                    intake_channel_id=excluded.intake_channel_id,
                    table_channel_id=excluded.table_channel_id,
                    standings_message_id=NULL,
                    scorers_message_id=NULL,
                    updated_at=CURRENT_TIMESTAMP
                """,
                (interaction.guild_id, canal_resultados.id, canal_tablas.id),
            )
            conn.commit()
        finally:
            conn.close()
        await interaction.response.send_message(
            f"✅ Liga configurada. Fotos: {canal_resultados.mention} • Tablas: {canal_tablas.mention}",
            ephemeral=True,
        )
        await refresh(runtime, bot, interaction.guild_id)

    @bot.tree.command(name="liga_tablas", description="Muestra las tablas actuales de posiciones y goleadores")
    async def liga_tablas(interaction: discord.Interaction):
        with runtime.db() as guild_conn:
            schema(guild_conn)
        conn = db(runtime, interaction.guild_id)
        try:
            await interaction.response.send_message(
                embeds=[standings_embed(conn), scorers_embed(conn)], ephemeral=True
            )
        finally:
            conn.close()

    @bot.tree.command(name="liga_estado", description="Muestra la configuración y estado del módulo Liga")
    async def liga_estado(interaction: discord.Interaction):
        if not admin(interaction):
            await interaction.response.send_message("⛔ Solo administradores.", ephemeral=True)
            return
        with runtime.db() as guild_conn:
            schema(guild_conn)
        conn = db(runtime, interaction.guild_id)
        try:
            cfg = conn.execute("SELECT * FROM league_config WHERE guild_id = ?", (interaction.guild_id,)).fetchone()
            matches = conn.execute("SELECT COUNT(*) AS n FROM league_matches").fetchone()["n"]
            goals = conn.execute("SELECT COALESCE(SUM(goals),0) AS n FROM league_goal_events").fetchone()["n"]
        finally:
            conn.close()
        intake = f"<#{cfg['intake_channel_id']}>" if cfg and cfg["intake_channel_id"] else "Sin configurar"
        tables = f"<#{cfg['table_channel_id']}>" if cfg and cfg["table_channel_id"] else "Sin configurar"
        api = "✅ configurada" if os.getenv("OPENAI_API_KEY") else "❌ falta OPENAI_API_KEY"
        embed = discord.Embed(
            title="📊 Estado Liga AJAP",
            description=(
                f"📸 Canal de fotos: {intake}\n"
                f"🏆 Canal de tablas: {tables}\n"
                f"🤖 Visión: {api}\n"
                f"⚽ Partidos cargados: **{matches}**\n"
                f"🥅 Goles acumulados: **{goals}**\n"
                f"🎯 Confianza mínima: **{MIN_CONF:.0%}**"
            ),
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @bot.tree.command(name="liga_anular_ultimo", description="Anula el último envío cargado automáticamente")
    async def liga_anular_ultimo(interaction: discord.Interaction):
        if not admin(interaction):
            await interaction.response.send_message("⛔ Solo administradores.", ephemeral=True)
            return
        with runtime.db() as guild_conn:
            schema(guild_conn)
        conn = db(runtime, interaction.guild_id)
        try:
            row = conn.execute(
                """
                SELECT source_message_id, MAX(created_at) AS created_at
                FROM (
                    SELECT source_message_id, created_at FROM league_matches
                    UNION ALL
                    SELECT source_message_id, created_at FROM league_goal_events
                )
                GROUP BY source_message_id
                ORDER BY created_at DESC, source_message_id DESC
                LIMIT 1
                """
            ).fetchone()
            if not row:
                await interaction.response.send_message("ℹ️ No hay cargas para anular.", ephemeral=True)
                return
            source_id = int(row["source_message_id"])
            conn.execute("DELETE FROM league_matches WHERE source_message_id = ?", (source_id,))
            conn.execute("DELETE FROM league_goal_events WHERE source_message_id = ?", (source_id,))
            conn.execute("DELETE FROM league_image_hashes WHERE source_message_id = ?", (source_id,))
            conn.commit()
        finally:
            conn.close()
        await interaction.response.send_message(
            f"↩️ Se anuló la última carga automática (mensaje `{source_id}`).",
            ephemeral=True,
        )
        await refresh(runtime, bot, interaction.guild_id)

    async def message_listener(message):
        await handle(runtime, bot, message)

    async def ready_listener():
        for guild in bot.guilds:
            conn = db(runtime, guild.id, must_exist=True)
            if conn is None:
                continue
            try:
                cfg = conn.execute("SELECT * FROM league_config WHERE guild_id = ?", (guild.id,)).fetchone()
            finally:
                conn.close()
            if cfg and cfg["table_channel_id"]:
                try:
                    await refresh(runtime, bot, guild.id)
                except Exception as exc:
                    print(f"AJAP League refresh inicial guild={guild.id}: {exc}")

    bot.add_listener(message_listener, "on_message")
    bot.add_listener(ready_listener, "on_ready")
    runtime._ajap_league_automation_patch = True
    print(f"AJAP League activo: P1-P24 + goleadores automáticos ({MODEL}, conf>={MIN_CONF:.2f})")
