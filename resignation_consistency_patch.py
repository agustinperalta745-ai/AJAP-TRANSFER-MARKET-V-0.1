"""Make DT resignation a single-message, timeout-safe and self-healing flow.

Why this exists:
- The old resignation button used send_message(), so the manager panel stayed
  alive behind a second ephemeral confirmation. After a successful resignation
  that stale panel still showed the old club and its buttons could be clicked.
- Confirmation performed Discord role/nickname I/O before acknowledging the
  component interaction. A slow Discord request could exceed the interaction
  response window even though SQLite had already been updated.

This final UI guard keeps resignation on the SAME ephemeral message, acknowledges
confirmation immediately, serializes duplicate/stale clicks per user+guild and,
after success, turns the message straight into the team selector. Old resignation
panels also repair themselves if clicked after the assignment is already gone.
"""

from __future__ import annotations

import asyncio

import discord

import dt_resignation_patch as resign
import team_assignment as teams


_LOCKS = {}


def _lock_for(interaction: discord.Interaction):
    guild_id = resign.guild_isolation._interaction_guild_id(interaction)
    key = (int(guild_id), int(interaction.user.id))
    lock = _LOCKS.get(key)
    if lock is None:
        lock = asyncio.Lock()
        _LOCKS[key] = lock
    return lock


def _choice_view(interaction: discord.Interaction):
    """Normal users get the team selector; Staff user-mode also keeps Back to Staff."""
    try:
        if resign.APP is not None and resign.APP.es_admin(interaction):
            import staff_profile_gate_patch as profiles

            builder = getattr(profiles, "_team_choice_view", None)
            if callable(builder):
                return builder()
    except Exception:
        pass
    return teams.TeamChoiceView()


def _choice_embed(*, club=None, already=False):
    base = teams.welcome_embed()
    original = str(getattr(base, "description", "") or "").strip()

    if already:
        base.title = "✅ Ya no tenés un club asignado"
        prefix = (
            "Ese panel había quedado abierto con información vieja. "
            "La asignación real ya estaba eliminada."
        )
    else:
        base.title = "✅ Renuncia confirmada"
        prefix = (
            f"Renunciaste al cargo de DT de **{club}**.\n"
            "El equipo quedó libre y su plantilla/economía permanecen intactas."
        )

    base.description = prefix + (f"\n\n{original}" if original else "")
    return base


def _confirm_embed(club: str):
    return discord.Embed(
        title="⚠️ Confirmar renuncia",
        description=(
            f"¿Seguro que querés renunciar como DT de **{club}**?\n\n"
            "Esta acción liberará el equipo inmediatamente, quitará tu rol DT "
            "y anunciará la vacante. **La plantilla no se borra.**"
        ),
        color=discord.Color.red(),
    )


def _processing_embed(club: str):
    return discord.Embed(
        title="⏳ Procesando renuncia",
        description=(
            f"Estamos liberando **{club}** y actualizando tu perfil.\n"
            "No hace falta volver a tocar el botón."
        ),
        color=discord.Color.orange(),
    )


async def _edit_after_ack(interaction: discord.Interaction, *, content=None, embed=None, view=None):
    """Edit the component's message after it has already been acknowledged."""
    await interaction.edit_original_response(content=content, embed=embed, view=view)


async def _safe_restore_role(interaction: discord.Interaction, current: str, removed_role: bool):
    if not removed_role:
        return
    try:
        await resign.dt_roles._grant_dt(
            interaction.guild,
            interaction.user.id,
            reason=f"AJAP: rollback de rol DT por error al renunciar a {current}",
        )
    except Exception:
        pass


async def resign_button_callback(self, interaction: discord.Interaction):
    token = resign._guild_context(interaction)
    try:
        club = resign.APP.club_de(interaction.user.id)
        if not club:
            # Self-heal any old manager panel instead of stacking another
            # "No tenés equipo" ephemeral message below it.
            await interaction.response.edit_message(
                content=None,
                embed=_choice_embed(already=True),
                view=_choice_view(interaction),
            )
            return

        # Replace the manager panel itself. No stale club panel remains behind.
        await interaction.response.edit_message(
            content=None,
            embed=_confirm_embed(club),
            view=resign.ConfirmResignationView(club),
        )
    finally:
        resign._reset_guild_context(token)


async def confirm_resignation(self, interaction: discord.Interaction, button: discord.ui.Button):
    token = resign._guild_context(interaction)
    try:
        # ACK NOW, before any Discord API / SQLite work. This removes the buttons
        # immediately, prevents repeat taps and guarantees the interaction cannot
        # expire while role/nickname operations are running.
        await interaction.response.edit_message(
            content=None,
            embed=_processing_embed(self.club),
            view=None,
        )

        async with _lock_for(interaction):
            current = resign.APP.club_de(interaction.user.id)
            if not current or current.casefold() != self.club.casefold():
                await _edit_after_ack(
                    interaction,
                    content=None,
                    embed=_choice_embed(already=True),
                    view=_choice_view(interaction),
                )
                return

            ok, role_result, removed_role = await resign.dt_roles._remove_dt(
                interaction.guild,
                interaction.user.id,
                reason=f"AJAP: renuncia voluntaria de {current}",
                require_config=False,
            )
            if not ok:
                await _edit_after_ack(
                    interaction,
                    content=str(role_result),
                    embed=None,
                    view=resign.ConfirmResignationView(current),
                )
                return

            try:
                club = resign._resign_assignment(interaction.user.id, current)
            except Exception as exc:
                await _safe_restore_role(interaction, current, removed_role)
                print(f"ERROR AJAP renuncia consistente: no se pudo liberar {current}: {exc}")
                await _edit_after_ack(
                    interaction,
                    content="⚠️ No se pudo completar la renuncia. El club sigue asignado.",
                    embed=None,
                    view=resign.ConfirmResignationView(current),
                )
                return

            if not club:
                await _safe_restore_role(interaction, current, removed_role)
                # Another stale/duplicate click already completed the operation.
                await _edit_after_ack(
                    interaction,
                    content=None,
                    embed=_choice_embed(already=True),
                    view=_choice_view(interaction),
                )
                return

            nickname_ok = True
            if interaction.guild is not None:
                try:
                    nickname_ok = await resign.nicknames._restore_member_nickname(
                        interaction.guild,
                        interaction.user.id,
                    )
                except Exception as exc:
                    nickname_ok = False
                    print(f"WARNING AJAP renuncia consistente: no se pudo restaurar apodo: {exc}")

            # The same original panel becomes the post-resignation selector.
            # The DB has already committed, so the freed team appears available.
            await _edit_after_ack(
                interaction,
                content=None,
                embed=_choice_embed(club=club),
                view=_choice_view(interaction),
            )

            vacancy_ok = False
            try:
                vacancy_ok = await resign.vacancies._publish_vacancy(interaction.guild, club)
            except Exception as exc:
                print(f"WARNING AJAP renuncia consistente: anuncio de vacante falló: {exc}")

            staff_ok = await resign._staff_notice(interaction, club)
            market_ok = await resign._market_notice(interaction, club)

            failures = []
            if not staff_ok:
                failures.append("aviso Staff/PES")
            if not vacancy_ok:
                failures.append("anuncio de equipo libre")
            if not market_ok:
                failures.append("aviso en mercado")
            if not nickname_ok:
                failures.append("restauración del apodo")

            if failures:
                try:
                    await interaction.followup.send(
                        "⚠️ La renuncia quedó registrada, pero falló: **"
                        + ", ".join(failures)
                        + "**. Revisá la configuración/permisos de Discord.",
                        ephemeral=True,
                    )
                except discord.HTTPException:
                    pass
    finally:
        resign._reset_guild_context(token)


async def cancel_resignation(self, interaction: discord.Interaction, button: discord.ui.Button):
    token = resign._guild_context(interaction)
    try:
        club = resign.APP.club_de(interaction.user.id)
        if not club:
            await interaction.response.edit_message(
                content=None,
                embed=_choice_embed(already=True),
                view=_choice_view(interaction),
            )
            return

        panel = getattr(resign.APP, "panel_embed", None)
        view_for = getattr(resign.APP, "manager_market_view_for", None)
        if callable(panel) and callable(view_for):
            await interaction.response.edit_message(
                content=None,
                embeds=[panel(interaction.user.id)],
                view=view_for(interaction),
            )
            return

        await interaction.response.edit_message(
            content="Renuncia cancelada.",
            embed=None,
            view=resign.APP.MercadoView(),
        )
    finally:
        resign._reset_guild_context(token)


# Monkey-patch the final classes. Manager-menu construction resolves the bound
# resignation callback from ResignButton instances after imports, so this is
# picked up by the final manager UI without rebuilding older patch layers.
resign.ResignButton.callback = resign_button_callback
resign.ConfirmResignationView.confirm = confirm_resignation
resign.ConfirmResignationView.cancel = cancel_resignation

print(
    "AJAP renuncia consistente activa: un solo mensaje + ACK inmediato + "
    "anti doble clic + panel viejo autorreparable"
)
