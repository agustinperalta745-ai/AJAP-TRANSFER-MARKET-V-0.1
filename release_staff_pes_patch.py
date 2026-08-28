"""Send player releases to the configured Staff/PES movement channel.

A release is already final in AJAP when the DT confirms it: the 20% charge is
paid and the player moves to Jugador Libre immediately. Staff still needs a
visible checklist item because the PES 6 option file must be edited afterwards.

This patch therefore creates a yellow Staff/PES card for every successful
release and gives admins a persistent ``Cargado en PES`` button. Marking it does
not move the player again; it only audits that the manual PES change was done and
turns the Staff card green.
"""

from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import discord

import guild_isolation_patch as guild_isolation
import market_channel_report_patch as reports
import player_release_patch as release


APP = None
BOT = None
LOCAL_TZ = ZoneInfo("America/Argentina/Buenos_Aires")


def _table_columns(conn, table: str):
    return {row["name"] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def _ensure_schema():
    if APP is None:
        return
    release._ensure_schema(APP)
    with APP.db() as conn:
        columns = _table_columns(conn, "player_releases")
        additions = {
            "pes_loaded_by": "INTEGER",
            "pes_loaded_at": "DATETIME",
            "pes_report_channel_id": "INTEGER",
            "pes_report_message_id": "INTEGER",
        }
        for column, definition in additions.items():
            if column not in columns:
                conn.execute(f"ALTER TABLE player_releases ADD COLUMN {column} {definition}")


def _fmt_money(value) -> str:
    try:
        return f"${int(value):,}".replace(",", ".")
    except (TypeError, ValueError):
        return str(value or "$0")


def _fmt_time(value):
    if not value:
        return "—"
    raw = str(value).strip()
    try:
        dt = datetime.strptime(raw[:19], "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        return dt.astimezone(LOCAL_TZ).strftime("%d/%m/%Y • %H:%M")
    except ValueError:
        return raw


def _row(release_id: int):
    _ensure_schema()
    with APP.db() as conn:
        return conn.execute(
            "SELECT * FROM player_releases WHERE id=? LIMIT 1",
            (int(release_id),),
        ).fetchone()


def _release_for_message(message_id: int):
    _ensure_schema()
    with APP.db() as conn:
        row = conn.execute(
            """
            SELECT id FROM player_releases
            WHERE pes_report_message_id=?
            ORDER BY id DESC LIMIT 1
            """,
            (int(message_id),),
        ).fetchone()
    return int(row["id"]) if row else None


def _max_release_id(user_id: int | None = None):
    _ensure_schema()
    with APP.db() as conn:
        if user_id is None:
            row = conn.execute("SELECT MAX(id) AS id FROM player_releases").fetchone()
        else:
            row = conn.execute(
                "SELECT MAX(id) AS id FROM player_releases WHERE released_by=?",
                (int(user_id),),
            ).fetchone()
    return int(row["id"]) if row and row["id"] is not None else 0


def _store_message(release_id: int, channel_id: int, message_id: int):
    _ensure_schema()
    with APP.db() as conn:
        conn.execute(
            """
            UPDATE player_releases
            SET pes_report_channel_id=?, pes_report_message_id=?
            WHERE id=?
            """,
            (int(channel_id), int(message_id), int(release_id)),
        )


def _mark_loaded(release_id: int, user_id: int):
    _ensure_schema()
    with APP.db() as conn:
        conn.execute(
            """
            UPDATE player_releases
            SET pes_loaded_by=?, pes_loaded_at=COALESCE(pes_loaded_at, CURRENT_TIMESTAMP)
            WHERE id=?
            """,
            (int(user_id), int(release_id)),
        )


def release_staff_embed(release_id: int):
    row = _row(release_id)
    if not row:
        return discord.Embed(
            title="⚠️ Liberación no encontrada",
            color=discord.Color.red(),
        )

    loaded = bool(row["pes_loaded_at"])
    color = discord.Color.green() if loaded else discord.Color.gold()
    title = (
        "🟢 LIBERACIÓN CARGADA EN PES"
        if loaded
        else "🟡 LIBERACIÓN PENDIENTE DE CARGAR EN PES"
    )
    embed = discord.Embed(title=f"{title} • #{row['id']}", color=color)
    embed.add_field(name="⚽ Jugador", value=f"**{row['player']}**", inline=False)
    embed.add_field(name="⬅️ Club anterior", value=row["from_club"], inline=True)
    embed.add_field(name="➡️ Nuevo estado", value=f"🆓 {release.FREE_AGENT_CLUB}", inline=True)
    embed.add_field(
        name="💰 Operación económica",
        value=(
            f"**Valor de mercado:** {_fmt_money(row['market_value'])}\n"
            f"**Costo de liberación ({row['release_percent']}%):** {_fmt_money(row['release_cost'])}\n"
            f"**Saldo antes:** {_fmt_money(row['balance_before'])}\n"
            f"**Saldo después:** {_fmt_money(row['balance_after'])}"
        ),
        inline=False,
    )
    embed.add_field(
        name="📋 Acción requerida en PES 6",
        value=(
            f"Quitar a **{row['player']}** de **{row['from_club']}** y dejarlo como jugador libre.\n"
            "La liberación **ya fue aplicada en AJAP**; no requiere aprobación administrativa."
        ),
        inline=False,
    )
    embed.add_field(
        name="🕐 Registro",
        value=(
            f"**Liberado:** {_fmt_time(row['created_at'])} (Argentina)\n"
            f"**Liberado por:** <@{int(row['released_by'])}>"
        ),
        inline=False,
    )

    if loaded:
        embed.add_field(
            name="🎮 Carga en PES",
            value=(
                f"**Cargado:** {_fmt_time(row['pes_loaded_at'])} (Argentina)\n"
                f"**Cargado por:** <@{int(row['pes_loaded_by'])}>"
            ),
            inline=False,
        )
        embed.add_field(name="Estado", value="✅ CARGADO EN PES", inline=False)
    else:
        embed.add_field(name="Estado", value="⏳ PENDIENTE DE CARGAR EN PES", inline=False)

    embed.set_footer(text="AJAP Transfer Market • checklist Staff/PES • Liberación")
    return embed


class ReleasePesLoadedView(discord.ui.View):
    def __init__(self, release_id: int | None = None):
        super().__init__(timeout=None)
        loaded = False
        if release_id is not None:
            row = _row(int(release_id))
            loaded = bool(row and row["pes_loaded_at"])

        button = discord.ui.Button(
            label="Cargado en PES",
            emoji="✅" if loaded else "🎮",
            style=discord.ButtonStyle.success if loaded else discord.ButtonStyle.primary,
            custom_id="ajap:release-pes-loaded",
            disabled=loaded,
        )
        button.callback = self._loaded
        self.add_item(button)

    async def _loaded(self, interaction: discord.Interaction):
        token = guild_isolation._CURRENT_GUILD_ID.set(
            guild_isolation._interaction_guild_id(interaction)
        )
        try:
            if not APP.es_admin(interaction):
                await interaction.response.send_message(
                    "⛔ Solo administradores pueden marcar una liberación como cargada en PES.",
                    ephemeral=True,
                )
                return

            message = getattr(interaction, "message", None)
            if message is None:
                await interaction.response.send_message(
                    "⚠️ No pude identificar esta tarjeta.", ephemeral=True
                )
                return

            release_id = _release_for_message(message.id)
            if release_id is None:
                await interaction.response.send_message(
                    "⚠️ Esta tarjeta no está vinculada a una liberación de este servidor.",
                    ephemeral=True,
                )
                return

            row = _row(release_id)
            if row and not row["pes_loaded_at"]:
                _mark_loaded(release_id, interaction.user.id)

            await interaction.response.edit_message(
                embed=release_staff_embed(release_id),
                view=ReleasePesLoadedView(release_id),
            )
        finally:
            guild_isolation._CURRENT_GUILD_ID.reset(token)


async def _report_channel(interaction: discord.Interaction):
    if not interaction.guild:
        return None
    channel_id = reports.get_report_channel_id(interaction.guild.id)
    if not channel_id:
        return None

    channel = interaction.guild.get_channel(int(channel_id))
    if channel is None and BOT is not None:
        channel = BOT.get_channel(int(channel_id))
    if channel is None and BOT is not None:
        try:
            channel = await BOT.fetch_channel(int(channel_id))
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            return None
    return channel if channel is not None and hasattr(channel, "send") else None


async def publish_release_to_staff(interaction: discord.Interaction, release_id: int):
    row = _row(release_id)
    if not row:
        return False

    channel = await _report_channel(interaction)
    if channel is None:
        try:
            await interaction.followup.send(
                "⚠️ La liberación se realizó, pero Staff no tiene un canal de movimientos disponible. "
                "Configurá `/canal_movimientos` para recibir el checklist de PES.",
                ephemeral=True,
            )
        except Exception:
            pass
        return False

    # If a report was already stored (for example because Discord retried a
    # component delivery), refresh it instead of creating a duplicate.
    if row["pes_report_message_id"]:
        try:
            message = await channel.fetch_message(int(row["pes_report_message_id"]))
            await message.edit(
                embed=release_staff_embed(release_id),
                view=ReleasePesLoadedView(release_id),
            )
            return True
        except (discord.NotFound, discord.Forbidden, discord.HTTPException, AttributeError):
            pass

    try:
        message = await channel.send(
            embed=release_staff_embed(release_id),
            view=ReleasePesLoadedView(release_id),
        )
        _store_message(release_id, channel.id, message.id)
        return True
    except (discord.Forbidden, discord.HTTPException) as exc:
        print(f"WARNING AJAP: liberación Staff/PES #{release_id} no publicada: {exc}")
        return False


_original_confirm_callback = release.ConfirmReleaseButton.callback


async def _confirm_release_with_staff_report(self, interaction: discord.Interaction):
    before = _max_release_id(interaction.user.id)
    await _original_confirm_callback(self, interaction)
    after = _max_release_id(interaction.user.id)
    if after <= before:
        return
    try:
        await publish_release_to_staff(interaction, after)
    except Exception as exc:
        print(f"WARNING AJAP: reporte Staff/PES de liberación #{after} falló: {exc}")


release.ConfirmReleaseButton.callback = _confirm_release_with_staff_report


def apply_release_staff_pes_patch(runtime, bot):
    global APP, BOT
    APP = runtime
    BOT = bot
    if getattr(runtime, "_ajap_release_staff_pes_patch", False):
        return

    _ensure_schema()
    try:
        bot.add_view(ReleasePesLoadedView())
    except Exception as exc:
        print(f"WARNING AJAP: vista persistente de liberaciones no registrada: {exc}")

    runtime.publish_release_to_staff = publish_release_to_staff
    runtime._ajap_release_staff_pes_patch = True
    print("AJAP liberaciones -> Staff/PES activo: tarjeta amarilla + Cargado en PES")


_original_apply_guild_isolation_patch = guild_isolation.apply_guild_isolation_patch


def _apply_guild_isolation_then_release_staff(runtime, bot):
    _original_apply_guild_isolation_patch(runtime, bot)
    apply_release_staff_pes_patch(runtime, bot)


if not getattr(
    guild_isolation.apply_guild_isolation_patch,
    "_ajap_release_staff_pes_wrapped",
    False,
):
    _apply_guild_isolation_then_release_staff._ajap_release_staff_pes_wrapped = True
    guild_isolation.apply_guild_isolation_patch = _apply_guild_isolation_then_release_staff
