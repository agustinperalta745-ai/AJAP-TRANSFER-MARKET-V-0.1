"""Final nickname hook for the current AJAP vacancy-assignment flow.

The live flow assigns clubs when Staff accepts a free-team request. This patch
runs after the DT-role layer, then changes the APPLICANT nickname to
``Nombre | Equipo``. It deliberately targets the accepted applicant instead of
the admin who presses the Accept button.
"""

from __future__ import annotations

import discord

import dt_role_patch as dt_roles
import free_team_admin_decision_patch as decisions
import member_nickname_patch as nicknames
import team_assignment as teams


APP = None
BOT = None


async def _member(guild: discord.Guild | None, user_id: int):
    if guild is None:
        return None
    member = guild.get_member(int(user_id))
    if member is None:
        try:
            member = await guild.fetch_member(int(user_id))
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            return None
    return member


async def _apply_nickname(guild: discord.Guild | None, user_id: int, team: str):
    member = await _member(guild, user_id)
    if member is None:
        return False, "No pude encontrar al usuario dentro del servidor."

    nicknames._remember_original_nick(member, team)
    desired = nicknames._nickname_for(member, team)
    if member.nick == desired:
        return True, desired

    try:
        await member.edit(
            nick=desired,
            reason=f"AJAP: vacante aceptada - {team}",
        )
        return True, desired
    except discord.Forbidden:
        return False, (
            "Discord bloqueó el cambio de apodo. El bot necesita **Administrar apodos** "
            "y su rol debe estar por encima del rol del usuario."
        )
    except discord.HTTPException as exc:
        return False, f"Discord no pudo actualizar el apodo: {exc}"


def _install_accept_nickname_hook():
    BaseView = decisions.VacancyAdminDecisionView
    if getattr(BaseView, "_ajap_vacancy_nickname", False):
        return

    class NicknameVacancyAdminDecisionView(BaseView):
        async def _accept(self, interaction: discord.Interaction):
            request = None
            if interaction.message is not None:
                request = decisions._request_for_message(interaction.message.id)

            await super()._accept(interaction)

            if not request:
                return

            fresh = decisions._request_by_id(int(request["id"]))
            if not fresh or (fresh["status"] or "").upper() != "ACEPTADA":
                return

            user_id = int(fresh["user_id"])
            club = str(fresh["club"])
            assigned = teams.club_de(user_id)
            if not assigned or assigned.casefold() != club.casefold():
                return

            ok, result = await _apply_nickname(interaction.guild, user_id, club)
            if ok:
                print(
                    f"AJAP nickname sync OK: guild={getattr(interaction.guild, 'id', None)} "
                    f"user={user_id} nick={result!r}"
                )
                return

            print(
                f"WARNING AJAP nickname sync failed: guild={getattr(interaction.guild, 'id', None)} "
                f"user={user_id} club={club}: {result}"
            )
            try:
                await interaction.followup.send(
                    f"⚠️ El club quedó asignado, pero no pude cambiar el apodo de <@{user_id}>.\n{result}",
                    ephemeral=True,
                )
            except discord.HTTPException:
                pass

    NicknameVacancyAdminDecisionView.__name__ = "VacancyAdminDecisionView"
    NicknameVacancyAdminDecisionView._ajap_vacancy_nickname = True
    decisions.VacancyAdminDecisionView = NicknameVacancyAdminDecisionView
    APP.VacancyAdminDecisionView = NicknameVacancyAdminDecisionView

    # Same persistent custom_ids as the previous Staff decision view. Registering
    # this final view makes the accepted-vacancy handler use the nickname-aware
    # subclass for both old and new Staff messages.
    try:
        BOT.add_view(NicknameVacancyAdminDecisionView())
    except ValueError:
        pass


def apply_vacancy_nickname_patch(runtime, bot):
    global APP, BOT
    APP = runtime
    BOT = bot

    if getattr(runtime, "_ajap_vacancy_nickname_patch", False):
        return

    _install_accept_nickname_hook()
    runtime._ajap_vacancy_nickname_patch = True
    print("AJAP: vacante aceptada => apodo Nombre | Equipo activo")


# guild_isolation_patch imports apply_dt_role_patch late in startup. Wrap that
# function now so this nickname layer is installed immediately AFTER the final
# DT-role acceptance handler exists.
_original_apply_dt_role_patch = dt_roles.apply_dt_role_patch


def _apply_dt_role_then_nickname(runtime, bot):
    _original_apply_dt_role_patch(runtime, bot)
    apply_vacancy_nickname_patch(runtime, bot)


if not getattr(dt_roles.apply_dt_role_patch, "_ajap_vacancy_nickname_wrapped", False):
    _apply_dt_role_then_nickname._ajap_vacancy_nickname_wrapped = True
    dt_roles.apply_dt_role_patch = _apply_dt_role_then_nickname
