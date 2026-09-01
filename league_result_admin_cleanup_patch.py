"""Herramienta Staff para retirar resultados de prueba de la Liga.

`/eliminar_resultado_liga [equipo]` muestra partidos oficiales ya persistidos,
permite elegir uno y exige una segunda confirmación antes de borrarlo. Elimina
solo el partido seleccionado y los goleadores/evidencias vinculados a su mensaje;
después recalcula las publicaciones de Liga.
"""

from __future__ import annotations

import discord
from discord import app_commands

import guild_isolation_patch as guild_isolation
import league_automation_patch as league
import league_result_evidence_patch as evidence
import league_validation_admin_review_patch as strict


APP = None
BOT = None


def _runtime():
    return APP


def _matches(runtime, guild_id: int, team: str | None = None):
    conn = league.db(runtime, int(guild_id))
    try:
        if team:
            return conn.execute(
                """
                SELECT * FROM league_matches
                WHERE home_team=? OR away_team=?
                ORDER BY created_at DESC, id DESC
                LIMIT 25
                """,
                (team, team),
            ).fetchall()
        return conn.execute(
            """
            SELECT * FROM league_matches
            ORDER BY created_at DESC, id DESC
            LIMIT 25
            """
        ).fetchall()
    finally:
        conn.close()


def _match(runtime, guild_id: int, source_message_id: int):
    conn = league.db(runtime, int(guild_id))
    try:
        return conn.execute(
            "SELECT * FROM league_matches WHERE source_message_id=? LIMIT 1",
            (int(source_message_id),),
        ).fetchone()
    finally:
        conn.close()


def _score(row):
    return (
        f"{row['home_team']} {int(row['home_goals'])}–"
        f"{int(row['away_goals'])} {row['away_team']}"
    )


def _delete_match(runtime, guild_id: int, source_message_id: int):
    evidence._ensure_schema(runtime, int(guild_id))
    strict._ensure_schema(runtime, int(guild_id))
    conn = league.db(runtime, int(guild_id))
    try:
        row = conn.execute(
            "SELECT * FROM league_matches WHERE source_message_id=? LIMIT 1",
            (int(source_message_id),),
        ).fetchone()
        if not row:
            return None

        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            "DELETE FROM league_goal_events WHERE source_message_id=?",
            (int(source_message_id),),
        )
        conn.execute(
            "DELETE FROM league_image_hashes WHERE source_message_id=?",
            (int(source_message_id),),
        )
        conn.execute(
            "UPDATE league_result_evidence SET parent_partial_message_id=NULL "
            "WHERE parent_partial_message_id=?",
            (int(source_message_id),),
        )
        conn.execute(
            "DELETE FROM league_result_evidence WHERE source_message_id=?",
            (int(source_message_id),),
        )
        conn.execute(
            "DELETE FROM league_manual_reviews WHERE source_message_id=?",
            (int(source_message_id),),
        )
        conn.execute(
            "DELETE FROM league_matches WHERE source_message_id=?",
            (int(source_message_id),),
        )
        conn.commit()
        return row
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


async def _remove_success_reaction(guild: discord.Guild, row):
    if BOT is None or BOT.user is None:
        return
    try:
        channel = guild.get_channel(int(row["source_channel_id"]))
        if channel is None:
            channel = await BOT.fetch_channel(int(row["source_channel_id"]))
        if not hasattr(channel, "fetch_message"):
            return
        message = await channel.fetch_message(int(row["source_message_id"]))
        try:
            await message.remove_reaction("✅", BOT.user)
        except Exception:
            pass
    except Exception:
        pass


class ConfirmDeleteResultView(discord.ui.View):
    def __init__(self, source_message_id: int):
        super().__init__(timeout=180)
        self.source_message_id = int(source_message_id)

    @discord.ui.button(label="ELIMINAR RESULTADO", emoji="🗑️", style=discord.ButtonStyle.danger)
    async def delete(self, interaction: discord.Interaction, button: discord.ui.Button):
        runtime = _runtime()
        if not interaction.guild_id or not runtime or not runtime.es_admin(interaction):
            await interaction.response.send_message("⛔ Solo administradores.", ephemeral=True)
            return

        row = _delete_match(runtime, interaction.guild_id, self.source_message_id)
        if not row:
            await interaction.response.edit_message(
                content="ℹ️ Ese partido ya no existe en la Liga.", embed=None, view=None
            )
            return

        try:
            if BOT is not None:
                await league.refresh(runtime, BOT, interaction.guild_id)
        except Exception as exc:
            print(f"AJAP Liga: resultado eliminado pero refresh falló: {exc}")

        if interaction.guild:
            await _remove_success_reaction(interaction.guild, row)

        await interaction.response.edit_message(
            content=(
                "✅ Resultado retirado de la Liga y tabla recalculada.\n"
                f"~~{_score(row)}~~\n"
                "También se eliminaron sus goleadores y evidencias vinculadas."
            ),
            embed=None,
            view=None,
        )

    @discord.ui.button(label="CANCELAR", emoji="↩️", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content="Operación cancelada.", embed=None, view=None)


class MatchDeleteSelect(discord.ui.Select):
    def __init__(self, rows):
        options = []
        for row in rows:
            label = _score(row)
            if len(label) > 100:
                label = label[:97] + "..."
            created = str(row["created_at"] or "")[:16]
            options.append(
                discord.SelectOption(
                    label=label,
                    value=str(int(row["source_message_id"])),
                    description=(f"Cargado {created}" if created else "Resultado oficial guardado")[:100],
                    emoji="🏆",
                )
            )
        super().__init__(
            placeholder="Elegí el resultado que querés retirar",
            min_values=1,
            max_values=1,
            options=options,
        )

    async def callback(self, interaction: discord.Interaction):
        runtime = _runtime()
        if not interaction.guild_id or not runtime or not runtime.es_admin(interaction):
            await interaction.response.send_message("⛔ Solo administradores.", ephemeral=True)
            return

        source_id = int(self.values[0])
        row = _match(runtime, interaction.guild_id, source_id)
        if not row:
            await interaction.response.edit_message(
                content="ℹ️ Ese partido ya no existe.", embed=None, view=None
            )
            return

        embed = discord.Embed(
            title="⚠️ CONFIRMAR ELIMINACIÓN DE RESULTADO",
            description=(
                f"Vas a retirar **{_score(row)}** de la Liga.\n\n"
                "Esto recalcula PJ/PG/PE/PP/GF/GC/puntos y elimina los goleadores "
                "asociados únicamente a este partido."
            ),
            color=discord.Color.red(),
        )
        embed.set_footer(text="Usalo para pruebas o resultados cargados por error")
        await interaction.response.edit_message(
            content=None,
            embed=embed,
            view=ConfirmDeleteResultView(source_id),
        )


class MatchDeleteView(discord.ui.View):
    def __init__(self, rows):
        super().__init__(timeout=300)
        self.add_item(MatchDeleteSelect(rows))


@app_commands.command(
    name="eliminar_resultado_liga",
    description="Retira un resultado de prueba/error y recalcula la Liga (solo Staff).",
)
@app_commands.describe(
    equipo="Opcional: escribí Betis, Everton, etc. para filtrar los partidos"
)
async def eliminar_resultado_liga(
    interaction: discord.Interaction,
    equipo: str | None = None,
):
    runtime = _runtime()
    if not interaction.guild_id or not runtime or not runtime.es_admin(interaction):
        await interaction.response.send_message("⛔ Solo administradores.", ephemeral=True)
        return

    canonical = None
    if equipo:
        canonical = league.canonical_team(equipo)
        if not canonical:
            await interaction.response.send_message(
                "⚠️ No reconocí ese equipo de la Liga.", ephemeral=True
            )
            return

    rows = _matches(runtime, interaction.guild_id, canonical)
    if not rows:
        suffix = f" de **{canonical}**" if canonical else ""
        await interaction.response.send_message(
            f"ℹ️ No hay resultados oficiales guardados{suffix}.", ephemeral=True
        )
        return

    title = f"Resultados de {canonical}" if canonical else "Últimos resultados oficiales"
    embed = discord.Embed(
        title=f"🧹 {title}",
        description=(
            "Elegí el partido cargado por error o de prueba. Antes de borrarlo vas a "
            "tener una segunda pantalla de confirmación."
        ),
        color=discord.Color.gold(),
    )
    await interaction.response.send_message(
        embed=embed,
        view=MatchDeleteView(rows),
        ephemeral=True,
    )


async def _sync_cleanup_command():
    if BOT is None or not BOT.user:
        return
    for guild in list(BOT.guilds):
        target = discord.Object(id=int(guild.id))
        try:
            BOT.tree.add_command(eliminar_resultado_liga, guild=target, override=True)
            synced = await BOT.tree.sync(guild=target)
            present = any(
                getattr(command, "name", None) == "eliminar_resultado_liga"
                for command in synced
            )
            print(
                f"AJAP Liga slash sync guild={guild.id}: "
                f"eliminar_resultado_liga={'OK' if present else 'NO_ENCONTRADO'}"
            )
        except Exception as exc:
            print(f"ERROR AJAP Liga sync eliminar_resultado_liga guild={guild.id}: {exc}")


def _install(runtime, bot):
    global APP, BOT
    APP, BOT = runtime, bot
    if getattr(runtime, "_ajap_league_result_admin_cleanup", False):
        return

    existing = bot.tree.get_command("eliminar_resultado_liga")
    if existing is not None:
        bot.tree.remove_command("eliminar_resultado_liga")
    bot.tree.add_command(eliminar_resultado_liga)

    if not getattr(bot, "_ajap_liga_cleanup_sync_listener", False):
        bot.add_listener(_sync_cleanup_command, "on_ready")
        bot._ajap_liga_cleanup_sync_listener = True

    runtime._ajap_league_result_admin_cleanup = True
    print("AJAP Liga: eliminación segura de resultados Staff activa")


_original_apply_guild_isolation_patch = guild_isolation.apply_guild_isolation_patch


def _apply_guild_isolation_then_cleanup(runtime, bot):
    _original_apply_guild_isolation_patch(runtime, bot)
    _install(runtime, bot)


if not getattr(guild_isolation.apply_guild_isolation_patch, "_ajap_liga_cleanup_wrapped", False):
    _apply_guild_isolation_then_cleanup._ajap_liga_cleanup_wrapped = True
    guild_isolation.apply_guild_isolation_patch = _apply_guild_isolation_then_cleanup
