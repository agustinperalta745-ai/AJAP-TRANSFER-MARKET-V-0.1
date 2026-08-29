from __future__ import annotations

import asyncio
import io

import discord
from PIL import Image, ImageDraw, ImageFont

import guild_isolation_patch as guild_isolation
import league_automation_patch as league
import league_result_evidence_patch as evidence
import market_usage_channel_patch as market_usage
import team_badge_selector_patch as badges

APP = None
BOT = None
COMMAND = "canal_resultados_ges"
PREFIX = "ajap:league:ges:"
market_usage.EXEMPT_COMMANDS.add(COMMAND)
if PREFIX not in market_usage.EXEMPT_COMPONENT_PREFIXES:
    market_usage.EXEMPT_COMPONENT_PREFIXES += (PREFIX,)

ALIASES = {
    "París Saint-Germain (PSG)": "Paris Saint-Germain",
    "Atlético de Madrid": "Atletico de Madrid",
    "Real Zaragoza": "Zaragoza",
}


def _conn(runtime, guild_id):
    conn = league.db(runtime, int(guild_id))
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS league_ges_config (
            guild_id INTEGER PRIMARY KEY,
            results_channel_id INTEGER NOT NULL,
            configured_by INTEGER,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS league_ges_result_queue (
            source_message_id INTEGER PRIMARY KEY,
            guild_id INTEGER NOT NULL,
            source_channel_id INTEGER NOT NULL,
            ges_channel_id INTEGER,
            ges_message_id INTEGER UNIQUE,
            home_team TEXT NOT NULL,
            away_team TEXT NOT NULL,
            home_goals INTEGER NOT NULL,
            away_goals INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'PENDIENTE',
            status_by INTEGER,
            status_at DATETIME,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );
        CREATE INDEX IF NOT EXISTS idx_league_ges_message
        ON league_ges_result_queue(guild_id, ges_message_id);
    """)
    conn.commit()
    return conn


def _get_channel_id(runtime, guild_id):
    conn = _conn(runtime, guild_id)
    try:
        row = conn.execute(
            "SELECT results_channel_id FROM league_ges_config WHERE guild_id=?",
            (int(guild_id),),
        ).fetchone()
        return int(row["results_channel_id"]) if row else None
    finally:
        conn.close()


def _save_channel(runtime, guild_id, channel_id, user_id):
    conn = _conn(runtime, guild_id)
    try:
        conn.execute("""
            INSERT INTO league_ges_config(guild_id,results_channel_id,configured_by,updated_at)
            VALUES(?,?,?,CURRENT_TIMESTAMP)
            ON CONFLICT(guild_id) DO UPDATE SET
                results_channel_id=excluded.results_channel_id,
                configured_by=excluded.configured_by,
                updated_at=CURRENT_TIMESTAMP
        """, (int(guild_id), int(channel_id), int(user_id)))
        conn.commit()
    finally:
        conn.close()


def _find(runtime, guild_id, *, source=None, message=None):
    conn = _conn(runtime, guild_id)
    try:
        if source is not None:
            return conn.execute(
                "SELECT * FROM league_ges_result_queue WHERE guild_id=? AND source_message_id=? LIMIT 1",
                (int(guild_id), int(source)),
            ).fetchone()
        return conn.execute(
            "SELECT * FROM league_ges_result_queue WHERE guild_id=? AND ges_message_id=? LIMIT 1",
            (int(guild_id), int(message)),
        ).fetchone()
    finally:
        conn.close()


def _reserve(runtime, guild_id, row, home, away, hg, ag, channel_id):
    conn = _conn(runtime, guild_id)
    try:
        conn.execute("BEGIN IMMEDIATE")
        if conn.execute(
            "SELECT 1 FROM league_ges_result_queue WHERE source_message_id=?",
            (int(row["source_message_id"]),),
        ).fetchone():
            conn.rollback()
            return False
        conn.execute("""
            INSERT INTO league_ges_result_queue(
                source_message_id,guild_id,source_channel_id,ges_channel_id,
                home_team,away_team,home_goals,away_goals
            ) VALUES(?,?,?,?,?,?,?,?)
        """, (
            int(row["source_message_id"]), int(guild_id), int(row["source_channel_id"]),
            int(channel_id), str(home), str(away), int(hg), int(ag),
        ))
        conn.commit()
        return True
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _attach(runtime, guild_id, source, channel_id, message_id):
    conn = _conn(runtime, guild_id)
    try:
        conn.execute("""
            UPDATE league_ges_result_queue
            SET ges_channel_id=?,ges_message_id=?,updated_at=CURRENT_TIMESTAMP
            WHERE source_message_id=?
        """, (int(channel_id), int(message_id), int(source)))
        conn.commit()
    finally:
        conn.close()


def _drop_failed(runtime, guild_id, source):
    conn = _conn(runtime, guild_id)
    try:
        conn.execute(
            "DELETE FROM league_ges_result_queue WHERE source_message_id=? AND ges_message_id IS NULL",
            (int(source),),
        )
        conn.commit()
    finally:
        conn.close()


def _status(runtime, guild_id, message_id, status, user_id):
    conn = _conn(runtime, guild_id)
    try:
        conn.execute("BEGIN IMMEDIATE")
        target = str(status).upper()
        if target == "EN_REVISION":
            cur = conn.execute("""
                UPDATE league_ges_result_queue
                SET status=?,status_by=?,status_at=CURRENT_TIMESTAMP,updated_at=CURRENT_TIMESTAMP
                WHERE guild_id=? AND ges_message_id=? AND status='PENDIENTE'
            """, (target, int(user_id), int(guild_id), int(message_id)))
        elif target == "CARGADO_GES":
            cur = conn.execute("""
                UPDATE league_ges_result_queue
                SET status=?,status_by=?,status_at=CURRENT_TIMESTAMP,updated_at=CURRENT_TIMESTAMP
                WHERE guild_id=? AND ges_message_id=? AND status IN ('PENDIENTE','EN_REVISION')
            """, (target, int(user_id), int(guild_id), int(message_id)))
        else:
            conn.rollback()
            return False
        changed = cur.rowcount > 0
        conn.commit()
        return changed
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _badge(guild, team):
    try:
        return badges._manual_badge_emoji(guild, ALIASES.get(str(team), str(team)))
    except Exception:
        return None


def _label(status):
    return {
        "EN_REVISION": "🟡 En revisión",
        "CARGADO_GES": "🟢 Cargado en GES",
    }.get(str(status or "").upper(), "🔴 Pendiente de carga")


def _embed(guild, row, actor=None):
    status = str(row["status"] or "PENDIENTE").upper()
    color = discord.Color.green() if status == "CARGADO_GES" else discord.Color.gold() if status == "EN_REVISION" else discord.Color.red()
    home, away = str(row["home_team"]), str(row["away_team"])
    home_icon, away_icon = _badge(guild, home), _badge(guild, away)
    embed = discord.Embed(
        title="📋 RESULTADO CERRADO • GES LIGA",
        description=(
            f"{home_icon or '🛡️'} **{home}**\n"
            f"## **{int(row['home_goals'])}  —  {int(row['away_goals'])}**\n"
            f"{away_icon or '🛡️'} **{away}**"
        ),
        color=color,
    )
    embed.add_field(name="Estado GES", value=_label(status), inline=True)
    if actor:
        embed.add_field(name="Última acción", value=f"<@{int(actor)}>", inline=True)
    embed.add_field(
        name="Origen",
        value=f"[Ver resultado](https://discord.com/channels/{guild.id}/{row['source_channel_id']}/{row['source_message_id']})",
        inline=False,
    )
    embed.set_footer(text="AJPA • GES Liga • Solo Staff cambia el estado")
    return embed


def _font(size, bold=False):
    """Return a real scalable font on Railway instead of Pillow's tiny bitmap fallback."""
    regular = (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/dejavu/DejaVuSans.ttf",
        "DejaVuSans.ttf",
    )
    bold_names = (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf",
        "DejaVuSans-Bold.ttf",
    )
    for name in (bold_names if bold else regular):
        try:
            return ImageFont.truetype(name, int(size))
        except Exception:
            pass
    try:
        return ImageFont.load_default(size=int(size))
    except TypeError:
        return ImageFont.load_default()


async def _card(guild, home, away, hg, ag):
    canvas = Image.new("RGB", (1000, 340), (24, 27, 33))
    draw = ImageDraw.Draw(canvas)
    draw.rounded_rectangle((28, 28, 342, 312), 30, fill=(35, 38, 45))
    draw.rounded_rectangle((658, 28, 972, 312), 30, fill=(35, 38, 45))
    draw.rounded_rectangle((370, 62, 630, 278), 34, fill=(18, 20, 25))

    async def icon(team):
        emoji = _badge(guild, team)
        if emoji is None:
            return None
        try:
            image = Image.open(io.BytesIO(await emoji.read())).convert("RGBA")
            image.thumbnail((118, 118))
            return image
        except Exception:
            return None

    home_img, away_img = await asyncio.gather(icon(home), icon(away))
    for image, cx in ((home_img, 185), (away_img, 815)):
        if image:
            canvas.paste(image, (int(cx-image.width/2), 76), image)

    def center(text, cx, y, font):
        box = draw.textbbox((0, 0), text, font=font)
        draw.text((cx-(box[2]-box[0])/2, y), text, font=font, fill=(244, 246, 248))

    def short(name):
        return name if len(name) <= 22 else name[:21] + "…"

    center(short(home), 185, 224, _font(28, True))
    center(short(away), 815, 224, _font(28, True))
    center(f"{int(hg)}  —  {int(ag)}", 500, 108, _font(92, True))
    center("RESULTADO FINAL", 500, 228, _font(18))
    out = io.BytesIO()
    canvas.save(out, "PNG", optimize=True)
    out.seek(0)
    return out


async def _send(runtime, guild_id, row, home, away, hg, ag):
    channel_id = _get_channel_id(runtime, guild_id)
    if not channel_id or BOT is None:
        return
    guild = BOT.get_guild(int(guild_id))
    if guild is None:
        return
    channel = guild.get_channel(int(channel_id))
    if not isinstance(channel, discord.TextChannel):
        return
    if not _reserve(runtime, guild_id, row, home, away, hg, ag, channel.id):
        return
    queue = _find(runtime, guild_id, source=row["source_message_id"])
    embed = _embed(guild, queue)
    try:
        image = await _card(guild, home, away, hg, ag)
        embed.set_image(url="attachment://ges_resultado.png")
        sent = await channel.send(
            embed=embed,
            file=discord.File(image, filename="ges_resultado.png"),
            view=GesView(),
            allowed_mentions=discord.AllowedMentions.none(),
        )
    except Exception:
        _drop_failed(runtime, guild_id, row["source_message_id"])
        raise
    _attach(runtime, guild_id, row["source_message_id"], channel.id, sent.id)


def _schedule(runtime, guild_id, row, **kwargs):
    home = str(kwargs.get("home") or row["home_team"])
    away = str(kwargs.get("away") or row["away_team"])
    hg = int(row["home_goals"] if kwargs.get("hg") is None else kwargs["hg"])
    ag = int(row["away_goals"] if kwargs.get("ag") is None else kwargs["ag"])
    asyncio.get_running_loop().create_task(_send(runtime, guild_id, row, home, away, hg, ag))


class GesView(discord.ui.View):
    def __init__(self, status="PENDIENTE"):
        super().__init__(timeout=None)
        status = str(status).upper()
        self.review.disabled = status in {"EN_REVISION", "CARGADO_GES"}
        self.loaded.disabled = status == "CARGADO_GES"

    async def change(self, interaction, status):
        if not interaction.guild_id or interaction.message is None:
            return
        try:
            allowed = APP.es_admin(interaction)
        except Exception:
            allowed = isinstance(interaction.user, discord.Member) and interaction.user.guild_permissions.administrator
        if not allowed:
            await interaction.response.send_message("⛔ Solo administradores.", ephemeral=True)
            return

        # Acknowledge Discord immediately so the button never shows
        # "La aplicación no ha respondido a tiempo" while DB/message work runs.
        await interaction.response.defer()

        try:
            row = _find(APP, interaction.guild_id, message=interaction.message.id)
            if not row:
                await interaction.followup.send("⚠️ Resultado GES no encontrado.", ephemeral=True)
                return

            changed = _status(APP, interaction.guild_id, interaction.message.id, status, interaction.user.id)
            row = _find(APP, interaction.guild_id, message=interaction.message.id)
            current = str(row["status"] or "PENDIENTE").upper()

            embed = _embed(interaction.guild, row, interaction.user.id if changed else row["status_by"])
            if interaction.message.attachments:
                embed.set_image(url="attachment://ges_resultado.png")
            await interaction.message.edit(embed=embed, view=GesView(current))

            if not changed:
                if current == "CARGADO_GES":
                    await interaction.followup.send("ℹ️ Ya figura como cargado en GES.", ephemeral=True)
                elif current == "EN_REVISION" and str(status).upper() == "EN_REVISION":
                    await interaction.followup.send("ℹ️ Este resultado ya está en revisión.", ephemeral=True)
        except Exception as exc:
            print(f"WARNING AJPA GES BUTTON: {type(exc).__name__}: {exc}")
            try:
                await interaction.followup.send(
                    "⚠️ No pude actualizar el estado. Probá de nuevo en unos segundos.",
                    ephemeral=True,
                )
            except Exception:
                pass

    @discord.ui.button(label="En revisión", emoji="🔍", style=discord.ButtonStyle.primary, custom_id="ajap:league:ges:review")
    async def review(self, interaction, button):
        await self.change(interaction, "EN_REVISION")

    @discord.ui.button(label="Cargado en GES", emoji="✅", style=discord.ButtonStyle.success, custom_id="ajap:league:ges:loaded")
    async def loaded(self, interaction, button):
        await self.change(interaction, "CARGADO_GES")


def _wrap():
    base = evidence._persist_official
    if getattr(base, "_ajap_ges_wrapped", False):
        return
    def wrapped(runtime, guild_id, row, *args, **kwargs):
        result = base(runtime, guild_id, row, *args, **kwargs)
        if bool(result[0]) and str(result[1]) == "CARGADO":
            try:
                _schedule(runtime, guild_id, row, **kwargs)
            except Exception as exc:
                print(f"WARNING AJPA GES: {type(exc).__name__}: {exc}")
        return result
    wrapped._ajap_ges_wrapped = True
    evidence._persist_official = wrapped


async def _configure(runtime, interaction):
    if interaction.guild is None or not runtime.es_admin(interaction):
        await interaction.response.send_message("⛔ Solo administradores dentro de un servidor.", ephemeral=True)
        return

    canal = interaction.channel
    if not isinstance(canal, discord.TextChannel):
        await interaction.response.send_message(
            "⚠️ Ejecutá este comando dentro del canal de texto que querés usar para los resultados de GES.",
            ephemeral=True,
        )
        return

    me = interaction.guild.me
    perms = canal.permissions_for(me) if me else None
    if perms and not (perms.view_channel and perms.send_messages and perms.embed_links and perms.attach_files):
        await interaction.response.send_message(
            f"⚠️ Necesito Ver canal, Enviar mensajes, Insertar enlaces y Adjuntar archivos en {canal.mention}.",
            ephemeral=True,
        )
        return
    _save_channel(runtime, interaction.guild.id, canal.id, interaction.user.id)
    await interaction.response.send_message(
        f"✅ Este canal quedó vinculado para resultados GES: {canal.mention}. Los resultados oficiales se enviarán acá con **En revisión** / **Cargado en GES**.",
        ephemeral=True,
    )


def _install(runtime, bot):
    global APP, BOT
    APP, BOT = runtime, bot
    if getattr(runtime, "_ajap_ges_result_queue", False):
        return
    _conn(runtime, guild_isolation.LEGACY_GUILD_ID).close()
    _wrap()
    old = bot.tree.get_command(COMMAND)
    if old:
        bot.tree.remove_command(COMMAND)

    @bot.tree.command(name=COMMAND, description="Vincula este canal como destino de resultados GES")
    async def canal_resultados_ges(interaction: discord.Interaction):
        await _configure(runtime, interaction)

    # Persistent view: timeout=None + fixed custom_ids makes existing buttons
    # keep working after hours, restarts and Railway deploys.
    bot.add_view(GesView())
    runtime._ajap_ges_result_queue = True
    print("AJPA GES activo: botones persistentes + estados En revisión/Cargado en GES")


_ORIGINAL = guild_isolation.apply_guild_isolation_patch

def _apply(runtime, bot):
    _ORIGINAL(runtime, bot)
    _install(runtime, bot)

if not getattr(guild_isolation.apply_guild_isolation_patch, "_ajap_ges_wrapper", False):
    _apply._ajap_ges_wrapper = True
    guild_isolation.apply_guild_isolation_patch = _apply
