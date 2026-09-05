"""Permanent Staff controls for AJPA league results.

Every official result gets a persistent Staff control card with:
- CORREGIR RESULTADO: edit teams/score on the same match row (never duplicate it)
- CARGAR / CORREGIR GOLEADOR: upsert or remove scorer attribution

Pending review cards keep their existing persistent CARGAR RESULTADO button.
All views use timeout=None and stable ajap:league:* custom_ids, so Discord can
route them after bot restarts as long as the original message still exists.
"""
from __future__ import annotations

import asyncio
import sqlite3

import discord

import guild_isolation_patch as guild_isolation
import league_automation_patch as league
import league_validation_admin_review_patch as strict
import league_manual_scorer_entry_patch as entry
import league_scorer_pending_patch as pending

APP = None
BOT = None
_BASE_HANDLE = None
_BASE_MANUAL_SUBMIT = strict.LeagueManualScoreModal.on_submit
_BASE_PENDING_ENSURE = pending._ensure_card


def _runtime():
    return APP or strict._runtime()


def _tables(conn):
    return {
        str(row[0])
        for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    }


def _match(runtime, guild_id: int, source_id: int):
    conn = league.db(runtime, int(guild_id))
    try:
        return conn.execute(
            "SELECT * FROM league_matches WHERE source_message_id=? LIMIT 1",
            (int(source_id),),
        ).fetchone()
    finally:
        conn.close()


def _review_by_staff(runtime, guild_id: int, staff_message_id: int):
    return strict._review_for_staff_message(runtime, int(guild_id), int(staff_message_id))


def _ensure_resolved_review(runtime, message, match):
    strict._ensure_schema(runtime, int(message.guild.id))
    conn = league.db(runtime, int(message.guild.id))
    try:
        conn.execute(
            """
            INSERT INTO league_manual_reviews
                (source_message_id,guild_id,source_channel_id,source_author_id,
                 reason,status,home_team,away_team,home_goals,away_goals,resolved_at)
            VALUES (?,?,?,?,?,'RESUELTO',?,?,?,?,CURRENT_TIMESTAMP)
            ON CONFLICT(source_message_id) DO UPDATE SET
                status='RESUELTO',
                home_team=excluded.home_team,
                away_team=excluded.away_team,
                home_goals=excluded.home_goals,
                away_goals=excluded.away_goals,
                resolved_at=COALESCE(league_manual_reviews.resolved_at,CURRENT_TIMESTAMP)
            """,
            (
                int(message.id), int(message.guild.id), int(message.channel.id),
                int(message.author.id), "Resultado oficial: controles permanentes de Staff.",
                str(match['home_team']), str(match['away_team']),
                int(match['home_goals']), int(match['away_goals']),
            ),
        )
        conn.commit()
        return conn.execute(
            "SELECT * FROM league_manual_reviews WHERE source_message_id=? LIMIT 1",
            (int(message.id),),
        ).fetchone()
    finally:
        conn.close()


def _scorer_text(runtime, guild_id: int, source_id: int):
    return entry._scorers_text(runtime, int(guild_id), int(source_id))


def _control_embed(runtime, guild_id: int, review, image_url: str | None = None):
    match = _match(runtime, guild_id, int(review['source_message_id']))
    if not match:
        return discord.Embed(
            title="⚠️ RESULTADO NO ENCONTRADO",
            description="El partido ya no existe en la base de Liga.",
            color=discord.Color.red(),
        )
    embed = discord.Embed(
        title="🛠️ CONTROL DE RESULTADO",
        description=(
            f"**{match['home_team']} {int(match['home_goals'])}–"
            f"{int(match['away_goals'])} {match['away_team']}**\n\n"
            "Estos controles son permanentes para Staff."
        ),
        color=discord.Color.blue(),
    )
    embed.add_field(
        name="Goleadores",
        value=_scorer_text(runtime, guild_id, int(match['source_message_id']))[:1024],
        inline=False,
    )
    embed.set_footer(text="Corregir modifica el mismo partido y recalcula Liga; no crea duplicados")
    if image_url:
        embed.set_image(url=image_url)
    return embed


def _image_from_message(message):
    try:
        if message and message.embeds and message.embeds[0].image.url:
            return str(message.embeds[0].image.url)
    except Exception:
        pass
    return None


async def _edit_control_card(interaction, review):
    runtime = _runtime()
    if runtime is None or interaction.message is None or not interaction.guild_id:
        return
    image_url = _image_from_message(interaction.message)
    await interaction.message.edit(
        embed=_control_embed(runtime, interaction.guild_id, review, image_url),
        view=ResultAdminView(),
    )


async def _refresh_everything(runtime, bot, guild_id: int):
    await league.refresh(runtime, bot, int(guild_id))
    try:
        import league_ges_scorer_details_patch as ges
        ges.APP = runtime
        ges.BOT = bot
        await ges._refresh_active_ges_cards()
    except Exception as exc:
        print(f"AJAP result controls: GES refresh omitido: {type(exc).__name__}: {exc}")


class CorrectResultModal(discord.ui.Modal, title="Corregir resultado"):
    def __init__(self, staff_message_id: int, match):
        super().__init__(custom_id="ajap:league:correct-result:modal")
        self.staff_message_id = int(staff_message_id)
        self.home_team = discord.ui.TextInput(
            label="Equipo local", required=True, max_length=80,
            default=str(match['home_team']),
        )
        self.home_goals = discord.ui.TextInput(
            label="Goles local", required=True, max_length=2,
            default=str(int(match['home_goals'])),
        )
        self.away_team = discord.ui.TextInput(
            label="Equipo visitante", required=True, max_length=80,
            default=str(match['away_team']),
        )
        self.away_goals = discord.ui.TextInput(
            label="Goles visitante", required=True, max_length=2,
            default=str(int(match['away_goals'])),
        )
        for item in (self.home_team, self.home_goals, self.away_team, self.away_goals):
            self.add_item(item)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)
        runtime = _runtime()
        if runtime is None or not interaction.guild_id or not runtime.es_admin(interaction):
            await interaction.followup.send("⛔ Solo administradores.", ephemeral=True)
            return
        review = _review_by_staff(runtime, interaction.guild_id, self.staff_message_id)
        if not review:
            await interaction.followup.send("⚠️ No pude identificar este resultado.", ephemeral=True)
            return
        old = _match(runtime, interaction.guild_id, int(review['source_message_id']))
        if not old:
            await interaction.followup.send("⚠️ El partido ya no existe en Liga.", ephemeral=True)
            return

        home = strict._official_team(self.home_team.value)
        away = strict._official_team(self.away_team.value)
        if not home or not away or home == away:
            await interaction.followup.send(
                "⚠️ Elegí dos equipos oficiales distintos.", ephemeral=True
            )
            return
        try:
            hg, ag = int(str(self.home_goals.value).strip()), int(str(self.away_goals.value).strip())
        except ValueError:
            await interaction.followup.send("⚠️ Los goles deben ser números enteros.", ephemeral=True)
            return
        if not (0 <= hg <= 99 and 0 <= ag <= 99):
            await interaction.followup.send("⚠️ Marcador fuera de rango.", ephemeral=True)
            return

        source = int(review['source_message_id'])
        old_home, old_away = str(old['home_team']), str(old['away_team'])
        teams_changed = (
            old_home.casefold() != str(home).casefold()
            or old_away.casefold() != str(away).casefold()
        )
        conn = league.db(runtime, interaction.guild_id)
        try:
            conn.execute("BEGIN IMMEDIATE")
            conn.execute(
                """
                UPDATE league_matches
                SET home_team=?, away_team=?, home_goals=?, away_goals=?, confidence=1.0
                WHERE source_message_id=?
                """,
                (home, away, int(hg), int(ag), source),
            )

            if teams_changed:
                conn.execute("DELETE FROM league_goal_events WHERE source_message_id=?", (source,))
            else:
                # Keep valid scorer data. If the corrected score is lower than
                # the already attributed total for a team, clear only that team.
                rows = conn.execute(
                    """
                    SELECT team, SUM(goals) AS n
                    FROM league_goal_events WHERE source_message_id=?
                    GROUP BY team COLLATE NOCASE
                    """,
                    (source,),
                ).fetchall()
                limits = {str(home).casefold(): int(hg), str(away).casefold(): int(ag)}
                for row in rows:
                    team = str(row['team'] or '')
                    limit = limits.get(team.casefold())
                    if limit is None or int(row['n'] or 0) > limit:
                        conn.execute(
                            "DELETE FROM league_goal_events WHERE source_message_id=? AND COALESCE(team,'') COLLATE NOCASE=?",
                            (source, team),
                        )

            if 'league_ges_result_queue' in _tables(conn):
                try:
                    conn.execute(
                        """
                        UPDATE league_ges_result_queue
                        SET home_team=?, away_team=?, home_goals=?, away_goals=?, updated_at=CURRENT_TIMESTAMP
                        WHERE source_message_id=?
                        """,
                        (home, away, int(hg), int(ag), source),
                    )
                except sqlite3.OperationalError:
                    # Older queue schemas may not contain team columns.
                    conn.execute(
                        """
                        UPDATE league_ges_result_queue
                        SET home_goals=?, away_goals=?, updated_at=CURRENT_TIMESTAMP
                        WHERE source_message_id=?
                        """,
                        (int(hg), int(ag), source),
                    )

            conn.execute(
                """
                UPDATE league_manual_reviews
                SET status='RESUELTO', resolved_by=?, resolved_at=CURRENT_TIMESTAMP,
                    home_team=?, away_team=?, home_goals=?, away_goals=?
                WHERE source_message_id=?
                """,
                (int(interaction.user.id), home, away, int(hg), int(ag), source),
            )
            league.standings(conn)
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

        bot = BOT or interaction.client
        try:
            await _refresh_everything(runtime, bot, interaction.guild_id)
        except Exception as exc:
            print(f"AJAP result controls: refresh tras corrección falló: {exc}")

        review = _review_by_staff(runtime, interaction.guild_id, self.staff_message_id)
        try:
            channel = interaction.guild.get_channel(int(review['staff_channel_id'] or 0))
            if channel is None and review['staff_channel_id']:
                channel = await interaction.guild.fetch_channel(int(review['staff_channel_id']))
            msg = await channel.fetch_message(int(review['staff_message_id'])) if channel else None
            if msg:
                image_url = _image_from_message(msg)
                await msg.edit(
                    embed=_control_embed(runtime, interaction.guild_id, review, image_url),
                    view=ResultAdminView(),
                )
        except Exception as exc:
            print(f"AJAP result controls: no pude refrescar tarjeta: {exc}")

        await interaction.followup.send(
            f"✅ Resultado corregido: **{home} {hg}–{ag} {away}**. "
            "Liga, app y cola de resultados fueron recalculadas.",
            ephemeral=True,
        )


class CorrectScorerModal(discord.ui.Modal, title="Cargar / corregir goleador"):
    player = discord.ui.TextInput(
        label="Jugador", placeholder="Ej: Huntelaar", required=True, max_length=100,
    )
    team = discord.ui.TextInput(
        label="Equipo", placeholder="Uno de los dos equipos", required=True, max_length=80,
    )
    goals = discord.ui.TextInput(
        label="Goles (0 = borrar este goleador)", placeholder="Ej: 2", required=True, max_length=2,
    )

    def __init__(self, staff_message_id: int):
        super().__init__(custom_id="ajap:league:correct-scorer:modal")
        self.staff_message_id = int(staff_message_id)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True, thinking=True)
        runtime = _runtime()
        if runtime is None or not interaction.guild_id or not runtime.es_admin(interaction):
            await interaction.followup.send("⛔ Solo administradores.", ephemeral=True)
            return
        review = _review_by_staff(runtime, interaction.guild_id, self.staff_message_id)
        if not review or str(review['status'] or '').upper() != 'RESUELTO':
            await interaction.followup.send("⚠️ No pude identificar un resultado oficial para esta tarjeta.", ephemeral=True)
            return
        club = entry._resolve_match_club(review, self.team.value)
        if not club:
            await interaction.followup.send(
                f"⚠️ El equipo debe ser **{review['home_team']}** o **{review['away_team']}**.",
                ephemeral=True,
            )
            return
        player = entry._resolve_roster_player(runtime, interaction.guild_id, club, self.player.value)
        if not player:
            await interaction.followup.send(
                f"⚠️ No encontré **{self.player.value}** en la plantilla de **{club}**.",
                ephemeral=True,
            )
            return
        try:
            goals = int(str(self.goals.value).strip())
        except ValueError:
            await interaction.followup.send("⚠️ Los goles deben ser un número entero.", ephemeral=True)
            return

        if goals == 0:
            conn = league.db(runtime, interaction.guild_id)
            try:
                conn.execute(
                    """
                    DELETE FROM league_goal_events
                    WHERE source_message_id=? AND team=? COLLATE NOCASE
                      AND lower(trim(player))=lower(trim(?))
                    """,
                    (int(review['source_message_id']), club, player),
                )
                conn.commit()
            finally:
                conn.close()
            text = f"🗑️ Goleador eliminado: **{player} — {club}**."
        else:
            ok, error = entry._upsert_manual_scorer(
                runtime, interaction.guild_id, review, player, club, goals
            )
            if not ok:
                await interaction.followup.send(f"⚠️ {error}", ephemeral=True)
                return
            text = f"✅ Goleador guardado: **{player} — {club} • ⚽ {goals}**."

        bot = BOT or interaction.client
        try:
            await _refresh_everything(runtime, bot, interaction.guild_id)
        except Exception as exc:
            print(f"AJAP result controls: refresh tras goleador falló: {exc}")
        review = _review_by_staff(runtime, interaction.guild_id, self.staff_message_id)
        try:
            channel = interaction.guild.get_channel(int(review['staff_channel_id'] or 0))
            if channel is None and review['staff_channel_id']:
                channel = await interaction.guild.fetch_channel(int(review['staff_channel_id']))
            msg = await channel.fetch_message(int(review['staff_message_id'])) if channel else None
            if msg:
                image_url = _image_from_message(msg)
                await msg.edit(
                    embed=_control_embed(runtime, interaction.guild_id, review, image_url),
                    view=ResultAdminView(),
                )
        except Exception as exc:
            print(f"AJAP result controls: no pude refrescar tarjeta tras goleador: {exc}")
        await interaction.followup.send(text, ephemeral=True)


class ResultAdminView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="CORREGIR RESULTADO", emoji="✏️",
        style=discord.ButtonStyle.primary,
        custom_id="ajap:league:correct-result",
    )
    async def correct_result(self, interaction: discord.Interaction, button: discord.ui.Button):
        runtime = _runtime()
        if runtime is None or not interaction.guild_id or interaction.message is None:
            return
        if not runtime.es_admin(interaction):
            await interaction.response.send_message("⛔ Solo administradores.", ephemeral=True)
            return
        review = _review_by_staff(runtime, interaction.guild_id, interaction.message.id)
        if not review:
            await interaction.response.send_message("⚠️ No pude vincular esta tarjeta con un resultado.", ephemeral=True)
            return
        match = _match(runtime, interaction.guild_id, int(review['source_message_id']))
        if not match:
            await interaction.response.send_message("⚠️ El partido ya no existe.", ephemeral=True)
            return
        await interaction.response.send_modal(CorrectResultModal(interaction.message.id, match))

    @discord.ui.button(
        label="CARGAR / CORREGIR GOLEADOR", emoji="⚽",
        style=discord.ButtonStyle.secondary,
        custom_id="ajap:league:correct-scorer",
    )
    async def correct_scorer(self, interaction: discord.Interaction, button: discord.ui.Button):
        runtime = _runtime()
        if runtime is None or not interaction.guild_id or interaction.message is None:
            return
        if not runtime.es_admin(interaction):
            await interaction.response.send_message("⛔ Solo administradores.", ephemeral=True)
            return
        review = _review_by_staff(runtime, interaction.guild_id, interaction.message.id)
        if not review or str(review['status'] or '').upper() != 'RESUELTO':
            await interaction.response.send_message("⚠️ Esta tarjeta no está vinculada a un resultado oficial.", ephemeral=True)
            return
        await interaction.response.send_modal(CorrectScorerModal(interaction.message.id))


async def _ensure_control_for_message(runtime, bot, message):
    if not message.guild or message.author.bot or not message.attachments:
        return
    match = _match(runtime, message.guild.id, message.id)
    if not match:
        return
    review = _ensure_resolved_review(runtime, message, match)
    if review['staff_message_id']:
        try:
            channel = message.guild.get_channel(int(review['staff_channel_id'] or 0))
            if channel is None and review['staff_channel_id']:
                channel = await message.guild.fetch_channel(int(review['staff_channel_id']))
            staff_msg = await channel.fetch_message(int(review['staff_message_id'])) if channel else None
            if staff_msg:
                await staff_msg.edit(view=ResultAdminView())
                return
        except Exception:
            pass

    channel = strict._staff_channel(message.guild)
    if channel is None:
        return
    image_url = None
    images = [a for a in message.attachments if str(a.content_type or '').startswith('image/')]
    if images:
        image_url = images[-1].url if len(images) > 1 else images[0].url
    staff_msg = await channel.send(
        embed=_control_embed(runtime, message.guild.id, review, image_url),
        view=ResultAdminView(),
    )
    strict._store_staff_message(runtime, message.guild.id, message.id, channel.id, staff_msg.id)


async def _handle_with_controls(runtime, bot, message):
    await _BASE_HANDLE(runtime, bot, message)
    try:
        await _ensure_control_for_message(runtime, bot, message)
    except Exception as exc:
        print(f"WARNING AJAP result control card message={getattr(message,'id','?')}: {type(exc).__name__}: {exc}")


async def _pending_with_controls(runtime, bot, message):
    await _BASE_PENDING_ENSURE(runtime, bot, message)
    try:
        review = strict._review_for_staff_message(runtime, message.guild.id, 0) if False else None
        conn = league.db(runtime, int(message.guild.id))
        try:
            row = conn.execute(
                "SELECT * FROM league_manual_reviews WHERE source_message_id=? LIMIT 1",
                (int(message.id),),
            ).fetchone()
        finally:
            conn.close()
        if row and row['staff_message_id'] and str(row['status'] or '').upper() == 'RESUELTO':
            channel = message.guild.get_channel(int(row['staff_channel_id'] or 0))
            if channel is None and row['staff_channel_id']:
                channel = await message.guild.fetch_channel(int(row['staff_channel_id']))
            staff_msg = await channel.fetch_message(int(row['staff_message_id'])) if channel else None
            if staff_msg:
                await staff_msg.edit(view=ResultAdminView())
    except Exception as exc:
        print(f"WARNING AJAP scorer card control upgrade: {type(exc).__name__}: {exc}")


async def _manual_submit_with_controls(self, interaction: discord.Interaction):
    await _BASE_MANUAL_SUBMIT(self, interaction)
    try:
        runtime = _runtime()
        if runtime is None or not interaction.guild_id:
            return
        review = _review_by_staff(runtime, interaction.guild_id, self.staff_message_id)
        if not review or str(review['status'] or '').upper() != 'RESUELTO':
            return
        channel = interaction.guild.get_channel(int(review['staff_channel_id'] or 0))
        if channel is None and review['staff_channel_id']:
            channel = await interaction.guild.fetch_channel(int(review['staff_channel_id']))
        msg = await channel.fetch_message(int(review['staff_message_id'])) if channel else None
        if msg:
            await msg.edit(
                embed=_control_embed(runtime, interaction.guild_id, review, _image_from_message(msg)),
                view=ResultAdminView(),
            )
    except Exception as exc:
        print(f"WARNING AJAP manual result control activation: {type(exc).__name__}: {exc}")


async def _reactivate_all_cards():
    await asyncio.sleep(2)
    runtime = _runtime()
    bot = BOT
    if runtime is None or bot is None:
        return
    pending_count = resolved_count = 0
    for guild in list(bot.guilds):
        conn = league.db(runtime, int(guild.id))
        try:
            try:
                rows = conn.execute(
                    """
                    SELECT * FROM league_manual_reviews
                    WHERE staff_channel_id IS NOT NULL AND staff_message_id IS NOT NULL
                    ORDER BY created_at DESC
                    """
                ).fetchall()
            except sqlite3.OperationalError:
                rows = []
        finally:
            conn.close()
        for row in rows:
            try:
                channel = guild.get_channel(int(row['staff_channel_id']))
                if channel is None:
                    channel = await guild.fetch_channel(int(row['staff_channel_id']))
                msg = await channel.fetch_message(int(row['staff_message_id']))
                if str(row['status'] or '').upper() == 'PENDIENTE':
                    await msg.edit(view=strict.LeagueManualReviewView())
                    pending_count += 1
                else:
                    if _match(runtime, guild.id, int(row['source_message_id'])):
                        await msg.edit(view=ResultAdminView())
                        resolved_count += 1
            except (discord.NotFound, discord.Forbidden):
                continue
            except Exception as exc:
                print(f"WARNING AJAP persistent control reactivate message={row['staff_message_id']}: {type(exc).__name__}: {exc}")
    print(f"AJAP Liga: botones persistentes reactivados pendientes={pending_count} resueltos={resolved_count}")


def _install(runtime, bot):
    global APP, BOT, _BASE_HANDLE
    APP, BOT = runtime, bot
    if getattr(runtime, '_ajap_persistent_result_admin_controls', False):
        return

    try:
        bot.add_view(ResultAdminView())
        bot.add_view(strict.LeagueManualReviewView())
    except Exception as exc:
        print(f"AJAP Liga: registro de controles persistentes: {exc}")

    current = league.handle
    if current is not _handle_with_controls:
        _BASE_HANDLE = current
        league.handle = _handle_with_controls

    pending._ensure_card = _pending_with_controls
    strict.LeagueManualScoreModal.on_submit = _manual_submit_with_controls

    if not getattr(bot, '_ajap_reactivate_all_result_controls', False):
        bot.add_listener(_reactivate_all_cards, 'on_ready')
        bot._ajap_reactivate_all_result_controls = True

    runtime._ajap_persistent_result_admin_controls = True
    print('AJAP Liga: controles permanentes CARGAR/CORREGIR resultado + goleadores activos')


_ORIGINAL_APPLY = guild_isolation.apply_guild_isolation_patch


def _apply(runtime, bot):
    _ORIGINAL_APPLY(runtime, bot)
    _install(runtime, bot)


if not getattr(guild_isolation.apply_guild_isolation_patch, '_ajap_persistent_result_admin_controls_wrapper', False):
    _apply._ajap_persistent_result_admin_controls_wrapper = True
    guild_isolation.apply_guild_isolation_patch = _apply
