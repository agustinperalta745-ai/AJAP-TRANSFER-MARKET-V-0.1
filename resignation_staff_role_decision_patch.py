"""Staff decides whether a resigned manager keeps the DT/access roles.

Flow:
- A voluntary resignation immediately frees the club, role-of-club and nickname.
- DT is NOT removed automatically. The user keeps access while Staff decides.
- Staff receives one persistent card with Mantener rol / Quitar rol.
- Mantener rol keeps DT + MERCADO so the user can move to another club.
- Quitar rol removes DT + MERCADO, which removes normal access to #mercado.
- A stale card can never strip DT from somebody who already took another club.
"""

from __future__ import annotations

import discord

import dt_resignation_patch as resign
import guild_isolation_patch as guild_isolation
import market_access_role_patch as market_access
import resignation_consistency_patch as consistent


APP = None
BOT = None


def _ensure_schema():
    with APP.db() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS resignation_role_decisions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                staff_message_id INTEGER NOT NULL UNIQUE,
                staff_channel_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                club TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'PENDIENTE',
                resolved_by INTEGER,
                resolved_at DATETIME,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )


def _decision_for_message(message_id: int):
    _ensure_schema()
    with APP.db() as conn:
        return conn.execute(
            """
            SELECT * FROM resignation_role_decisions
            WHERE staff_message_id = ?
            LIMIT 1
            """,
            (int(message_id),),
        ).fetchone()


def _store_decision_message(message, user_id: int, club: str):
    _ensure_schema()
    with APP.db() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO resignation_role_decisions
            (staff_message_id, staff_channel_id, user_id, club, status,
             resolved_by, resolved_at, created_at)
            VALUES (?, ?, ?, ?, 'PENDIENTE', NULL, NULL, CURRENT_TIMESTAMP)
            """,
            (int(message.id), int(message.channel.id), int(user_id), str(club)),
        )


def _resolve_decision(message_id: int, status: str, admin_id: int):
    _ensure_schema()
    with APP.db() as conn:
        row = conn.execute(
            "SELECT status FROM resignation_role_decisions WHERE staff_message_id = ?",
            (int(message_id),),
        ).fetchone()
        if not row or (row["status"] or "").upper() != "PENDIENTE":
            return False
        conn.execute(
            """
            UPDATE resignation_role_decisions
            SET status = ?, resolved_by = ?, resolved_at = CURRENT_TIMESTAMP
            WHERE staff_message_id = ?
            """,
            (str(status).upper(), int(admin_id), int(message_id)),
        )
    return True


def _current_club(user_id: int):
    try:
        return APP.club_de(int(user_id))
    except Exception:
        return None


def _market_channel_label(guild: discord.Guild):
    try:
        with guild_isolation.guild_context(guild.id):
            channel_id = market_access.market_usage.get_market_channel_id(guild.id)
        if channel_id:
            return f"<#{int(channel_id)}>"
    except Exception:
        pass
    return "#Mercado-de-pases"


def _question_embed(guild: discord.Guild, user_id: int, club: str):
    market_label = _market_channel_label(guild)
    embed = discord.Embed(
        title="🚪 DT abandonó el cargo",
        description=(
            f"<@{int(user_id)}> abandonó el cargo de DT de **{club}**.\n\n"
            "¿Desea que mantenga el rol **DT**?\n\n"
            f"⚠️ **Quitar el rol DT impedirá al usuario acceder o permanecer en {market_label}.**"
        ),
        color=discord.Color.orange(),
    )
    embed.add_field(name="🏟️ Club liberado", value=club, inline=True)
    embed.add_field(name="👤 DT saliente", value=f"<@{int(user_id)}>", inline=True)
    embed.set_footer(text="El club ya quedó libre • Staff debe decidir el acceso del usuario")
    return embed


def _resolved_embed(row, status: str, admin_id: int, *, note: str | None = None):
    kept = str(status).upper() in {"MANTENIDO", "MANTENIDO_NUEVO_CLUB"}
    embed = discord.Embed(
        title="✅ Decisión de rol DT registrada",
        description=(
            f"<@{int(row['user_id'])}> abandonó **{row['club']}**.\n\n"
            + (
                "🟢 **Se mantuvo el rol DT y el acceso al mercado.**"
                if kept
                else "🔴 **Se quitó el rol DT y el acceso al mercado.**"
            )
        ),
        color=discord.Color.green() if kept else discord.Color.red(),
    )
    if note:
        embed.add_field(name="ℹ️ Nota", value=note, inline=False)
    embed.set_footer(text=f"Decisión tomada por {admin_id}")
    return embed


async def _staff_channel(guild: discord.Guild):
    try:
        return await resign.vacancies._staff_report_channel(guild)
    except Exception:
        return None


async def _send_staff_question(interaction: discord.Interaction, club: str):
    channel = await _staff_channel(interaction.guild)
    if channel is None:
        return False
    try:
        message = await channel.send(
            embed=_question_embed(interaction.guild, interaction.user.id, club),
            view=ResignationRoleDecisionView(),
        )
        _store_decision_message(message, interaction.user.id, club)
        return True
    except (discord.Forbidden, discord.HTTPException) as exc:
        print(
            "WARNING AJAP renuncia rol Staff: no pude publicar decisión "
            f"guild={interaction.guild.id} user={interaction.user.id} error={type(exc).__name__}: {exc}"
        )
        return False
    except Exception as exc:
        print(
            "WARNING AJAP renuncia rol Staff: no pude registrar tarjeta "
            f"guild={interaction.guild.id} user={interaction.user.id} error={type(exc).__name__}: {exc}"
        )
        return False


async def _remove_market_access(guild: discord.Guild, user_id: int):
    member = await market_access._member(guild, int(user_id))
    if member is None:
        return False

    role = market_access._configured_role(guild)
    if role is not None and role in member.roles:
        me = guild.me
        if me is None or not me.guild_permissions.manage_roles or role >= me.top_role:
            return False
        try:
            await member.remove_roles(
                role,
                reason="AJAP: Staff quitó acceso al mercado tras renuncia",
            )
        except (discord.Forbidden, discord.HTTPException):
            return False

    # Remove only the exact individual emergency allow created by an older
    # market hotfix; custom/manual overwrites remain untouched.
    try:
        with guild_isolation.guild_context(guild.id):
            channel_id = market_access.market_usage.get_market_channel_id(guild.id)
        channel = (
            await market_access.market_usage._resolve_text_channel(guild, int(channel_id))
            if channel_id
            else None
        )
        if channel is not None:
            overwrite = channel.overwrites_for(member)
            if market_access._looks_like_old_bot_member_overwrite(overwrite):
                await channel.set_permissions(
                    member,
                    overwrite=None,
                    reason="AJAP: quitar acceso individual antiguo tras renuncia",
                )
    except (discord.Forbidden, discord.HTTPException, Exception):
        # The role is the canonical gate. A cleanup failure here must not fake a
        # failure after the canonical role was already removed.
        pass
    return True


async def _handle_staff_decision(interaction: discord.Interaction, *, keep: bool):
    if APP is None or not APP.es_admin(interaction):
        await interaction.response.send_message("⛔ Solo administradores.", ephemeral=True)
        return
    if interaction.message is None:
        await interaction.response.send_message("⚠️ No pude identificar la renuncia.", ephemeral=True)
        return

    row = _decision_for_message(interaction.message.id)
    if not row:
        await interaction.response.send_message("⚠️ No encontré esta decisión en la base.", ephemeral=True)
        return
    if (row["status"] or "").upper() != "PENDIENTE":
        await interaction.response.send_message("⚠️ Esta decisión ya fue resuelta.", ephemeral=True)
        return

    user_id = int(row["user_id"])
    current = _current_club(user_id)

    # Never let an old resignation card strip the role of somebody who has since
    # become DT of a new club.
    if current:
        await resign.dt_roles._grant_dt(
            interaction.guild,
            user_id,
            reason=f"AJAP: DT activo de {current}; conservar rol ante tarjeta vieja",
        )
        await market_access.grant_market_access(
            interaction.guild,
            user_id,
            reason=f"AJAP: DT activo de {current}; conservar acceso",
        )
        _resolve_decision(interaction.message.id, "MANTENIDO_NUEVO_CLUB", interaction.user.id)
        await interaction.response.edit_message(
            embed=_resolved_embed(
                row,
                "MANTENIDO_NUEVO_CLUB",
                interaction.user.id,
                note=f"El usuario ya está a cargo de **{current}**, por lo que el rol no puede quitarse desde esta renuncia anterior.",
            ),
            view=None,
        )
        return

    if keep:
        ok, result, _ = await resign.dt_roles._grant_dt(
            interaction.guild,
            user_id,
            reason=f"AJAP: Staff mantuvo DT tras renuncia a {row['club']}",
        )
        access_ok = await market_access.grant_market_access(
            interaction.guild,
            user_id,
            reason="AJAP: Staff mantuvo acceso tras renuncia",
        )
        if not ok or not access_ok:
            await interaction.response.send_message(
                f"⚠️ No pude mantener completamente el rol/acceso. {result if not ok else ''}",
                ephemeral=True,
            )
            return

        _resolve_decision(interaction.message.id, "MANTENIDO", interaction.user.id)
        await interaction.response.edit_message(
            embed=_resolved_embed(row, "MANTENIDO", interaction.user.id),
            view=None,
        )
        return

    # Removing DT is transactional from Staff's perspective: if the independent
    # MERCADO role cannot also be removed, restore DT and leave the card pending.
    ok, result, removed_dt = await resign.dt_roles._remove_dt(
        interaction.guild,
        user_id,
        reason=f"AJAP: Staff quitó DT tras renuncia a {row['club']}",
        require_config=False,
    )
    if not ok:
        await interaction.response.send_message(str(result), ephemeral=True)
        return

    access_ok = await _remove_market_access(interaction.guild, user_id)
    if not access_ok:
        if removed_dt:
            try:
                await resign.dt_roles._grant_dt(
                    interaction.guild,
                    user_id,
                    reason="AJAP: rollback porque no se pudo quitar acceso MERCADO",
                )
            except Exception:
                pass
        await interaction.response.send_message(
            "⚠️ No pude quitar el acceso al mercado; no cerré la decisión.",
            ephemeral=True,
        )
        return

    _resolve_decision(interaction.message.id, "QUITADO", interaction.user.id)
    await interaction.response.edit_message(
        embed=_resolved_embed(row, "QUITADO", interaction.user.id),
        view=None,
    )


class ResignationRoleDecisionView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Mantener rol",
        emoji="✅",
        style=discord.ButtonStyle.success,
        custom_id="ajap:resign-role:keep",
    )
    async def keep_role(self, interaction: discord.Interaction, button: discord.ui.Button):
        await _handle_staff_decision(interaction, keep=True)

    @discord.ui.button(
        label="Quitar rol",
        emoji="🚫",
        style=discord.ButtonStyle.danger,
        custom_id="ajap:resign-role:remove",
    )
    async def remove_role(self, interaction: discord.Interaction, button: discord.ui.Button):
        await _handle_staff_decision(interaction, keep=False)


def _confirm_embed_pending_role(club: str):
    return discord.Embed(
        title="⚠️ Confirmar renuncia",
        description=(
            f"¿Seguro que querés renunciar como DT de **{club}**?\n\n"
            "Esta acción liberará el equipo inmediatamente y anunciará la vacante. "
            "**Tu rol DT no se quitará automáticamente:** Staff decidirá si lo mantenés o si se elimina.\n\n"
            "La plantilla y la economía del club no se borran."
        ),
        color=discord.Color.red(),
    )


async def _confirm_resignation_deferred(self, interaction: discord.Interaction, button: discord.ui.Button):
    token = resign._guild_context(interaction)
    try:
        await interaction.response.edit_message(
            content=None,
            embed=consistent._processing_embed(self.club),
            view=None,
        )

        async with consistent._lock_for(interaction):
            current = resign.APP.club_de(interaction.user.id)
            if not current or current.casefold() != self.club.casefold():
                await consistent._edit_after_ack(
                    interaction,
                    content=None,
                    embed=consistent._choice_embed(already=True),
                    view=consistent._choice_view(interaction),
                )
                return

            try:
                club = resign._resign_assignment(interaction.user.id, current)
            except Exception as exc:
                print(f"ERROR AJAP renuncia con decisión Staff: no se pudo liberar {current}: {exc}")
                await consistent._edit_after_ack(
                    interaction,
                    content="⚠️ No se pudo completar la renuncia. El club sigue asignado.",
                    embed=None,
                    view=resign.ConfirmResignationView(current),
                )
                return

            if not club:
                await consistent._edit_after_ack(
                    interaction,
                    content=None,
                    embed=consistent._choice_embed(already=True),
                    view=consistent._choice_view(interaction),
                )
                return

            # Keep DT + market access until Staff explicitly decides otherwise.
            role_ok, role_result, _ = await resign.dt_roles._grant_dt(
                interaction.guild,
                interaction.user.id,
                reason=f"AJAP: conservar DT pendiente de decisión Staff tras renuncia a {club}",
            )
            access_ok = await market_access.grant_market_access(
                interaction.guild,
                interaction.user.id,
                reason="AJAP: conservar acceso pendiente de decisión Staff",
            )

            nickname_ok = True
            try:
                nickname_ok = await resign.nicknames._restore_member_nickname(
                    interaction.guild,
                    interaction.user.id,
                )
            except Exception as exc:
                nickname_ok = False
                print(f"WARNING AJAP renuncia con decisión Staff: apodo: {exc}")

            await consistent._edit_after_ack(
                interaction,
                content=None,
                embed=consistent._choice_embed(club=club),
                view=consistent._choice_view(interaction),
            )

            vacancy_ok = False
            try:
                vacancy_ok = await resign.vacancies._publish_vacancy(interaction.guild, club)
            except Exception as exc:
                print(f"WARNING AJAP renuncia con decisión Staff: vacante: {exc}")

            staff_ok = await _send_staff_question(interaction, club)
            market_ok = await resign._market_notice(interaction, club)

            failures = []
            if not staff_ok:
                failures.append("pregunta de rol a Staff")
            if not vacancy_ok:
                failures.append("anuncio de equipo libre")
            if not market_ok:
                failures.append("aviso en mercado")
            if not nickname_ok:
                failures.append("restauración del apodo")
            if not role_ok:
                failures.append(f"mantener DT ({role_result})")
            if not access_ok:
                failures.append("mantener acceso al mercado")

            if failures:
                try:
                    await interaction.followup.send(
                        "⚠️ La renuncia quedó registrada, pero falló: **"
                        + ", ".join(failures)
                        + "**.",
                        ephemeral=True,
                    )
                except discord.HTTPException:
                    pass
    finally:
        resign._reset_guild_context(token)


class DeferredRoleConfirmResignationView(discord.ui.View):
    def __init__(self, club: str):
        super().__init__(timeout=90)
        self.club = club

    @discord.ui.button(
        label="Sí, renunciar",
        emoji="🚪",
        style=discord.ButtonStyle.danger,
    )
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        await _confirm_resignation_deferred(self, interaction, button)

    @discord.ui.button(
        label="Cancelar",
        emoji="✖️",
        style=discord.ButtonStyle.secondary,
    )
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await consistent.cancel_resignation(self, interaction, button)


# The existing resignation button callback resolves both of these globals at click
# time, so replacing them here is enough to change the final flow.
consistent._confirm_embed = _confirm_embed_pending_role
resign.ConfirmResignationView = DeferredRoleConfirmResignationView


def apply_resignation_staff_role_decision_patch(runtime, bot):
    global APP, BOT
    APP = runtime
    BOT = bot
    if getattr(runtime, "_ajap_resignation_staff_role_decision_patch", False):
        return

    _ensure_schema()
    try:
        bot.add_view(ResignationRoleDecisionView())
    except ValueError:
        pass

    runtime._ajap_resignation_staff_role_decision_patch = True
    print(
        "AJAP renuncia Staff activa: club se libera + DT queda pendiente + "
        "Mantener rol/Quitar rol controla también acceso MERCADO"
    )


_prior_apply_guild_isolation = guild_isolation.apply_guild_isolation_patch


def _apply_guild_isolation_then_resignation_staff(runtime, bot):
    _prior_apply_guild_isolation(runtime, bot)
    apply_resignation_staff_role_decision_patch(runtime, bot)


if not getattr(
    guild_isolation.apply_guild_isolation_patch,
    "_ajap_resignation_staff_role_decision_wrapped",
    False,
):
    _apply_guild_isolation_then_resignation_staff._ajap_resignation_staff_role_decision_wrapped = True
    guild_isolation.apply_guild_isolation_patch = _apply_guild_isolation_then_resignation_staff
