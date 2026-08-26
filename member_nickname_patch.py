"""Discord nickname sync for AJAP club assignments.

Members are shown as ``Nombre | Equipo`` after choosing a club, including
admins/staff so the feature can be tested in admin-only test servers. The
original server nickname is stored so an admin unlink can restore it.
"""

import discord

import team_assignment as teams


MAX_NICKNAME_LENGTH = 32
SEPARATOR = " | "


def _ensure_schema():
    with teams.db() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS discord_nickname_state (
                guild_id INTEGER NOT NULL,
                user_id INTEGER NOT NULL,
                original_nick TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (guild_id, user_id)
            )
            """
        )


def _stored_original_nick(guild_id: int, user_id: int):
    _ensure_schema()
    with teams.db() as conn:
        return conn.execute(
            """
            SELECT original_nick
            FROM discord_nickname_state
            WHERE guild_id = ? AND user_id = ?
            """,
            (int(guild_id), int(user_id)),
        ).fetchone()


def _remember_original_nick(member: discord.Member, team: str):
    _ensure_schema()
    original = member.nick

    # If this feature is being enabled for a member who already has the AJAP
    # suffix, store the clean part instead of saving the generated nickname.
    if original:
        suffix = f"{SEPARATOR}{team}"
        if original.casefold().endswith(suffix.casefold()):
            cleaned = original[: -len(suffix)].rstrip()
            original = cleaned or None

    with teams.db() as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO discord_nickname_state
                (guild_id, user_id, original_nick)
            VALUES (?, ?, ?)
            """,
            (int(member.guild.id), int(member.id), original),
        )


def _forget_original_nick(guild_id: int, user_id: int):
    _ensure_schema()
    with teams.db() as conn:
        conn.execute(
            """
            DELETE FROM discord_nickname_state
            WHERE guild_id = ? AND user_id = ?
            """,
            (int(guild_id), int(user_id)),
        )


def _nickname_for(member: discord.Member, team: str) -> str:
    team = str(team).strip()
    base = (member.nick or member.display_name or member.name).strip()

    # Do not stack the suffix if the user opens /mercado repeatedly.
    current_suffix = f"{SEPARATOR}{team}"
    if base.casefold().endswith(current_suffix.casefold()):
        base = base[: -len(current_suffix)].rstrip()

    # Keep the club readable and trim the user's visible name first. Discord
    # nicknames have a hard 32-character limit.
    max_team = MAX_NICKNAME_LENGTH - len(SEPARATOR) - 1
    if len(team) > max_team:
        team = team[:max_team].rstrip()

    max_base = MAX_NICKNAME_LENGTH - len(SEPARATOR) - len(team)
    fallback = (member.name or "Jugador").strip()
    base = (base or fallback)[:max_base].rstrip()
    if not base:
        base = fallback[:max_base] or "J"

    return f"{base}{SEPARATOR}{team}"[:MAX_NICKNAME_LENGTH]


async def _apply_club_nickname(interaction: discord.Interaction, team: str) -> bool:
    if not interaction.guild or not isinstance(interaction.user, discord.Member):
        return True

    member = interaction.user
    _remember_original_nick(member, team)
    desired = _nickname_for(member, team)
    if member.nick == desired:
        return True

    try:
        await member.edit(nick=desired, reason=f"AJAP: club asignado - {team}")
        return True
    except (discord.Forbidden, discord.HTTPException) as exc:
        print(
            f"WARNING AJAP: no se pudo cambiar apodo de {member.id} "
            f"en guild {member.guild.id}: {exc}"
        )
        return False


async def _restore_member_nickname(guild: discord.Guild, user_id: int) -> bool:
    row = _stored_original_nick(guild.id, user_id)
    if row is None:
        return True

    member = guild.get_member(int(user_id))
    if member is None:
        try:
            member = await guild.fetch_member(int(user_id))
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            member = None

    if member is None:
        return False

    try:
        await member.edit(
            nick=row["original_nick"],
            reason="AJAP: club desvinculado",
        )
    except (discord.Forbidden, discord.HTTPException) as exc:
        print(
            f"WARNING AJAP: no se pudo restaurar apodo de {user_id} "
            f"en guild {guild.id}: {exc}"
        )
        return False

    _forget_original_nick(guild.id, user_id)
    return True


def _patch_team_select():
    original = teams.TeamSelect.callback
    if getattr(original, "_ajap_nickname_wrapped", False):
        return

    async def callback(self, interaction: discord.Interaction):
        await original(self, interaction)
        team = teams.club_de(interaction.user.id)
        if not team:
            return

        changed = await _apply_club_nickname(interaction, team)
        if not changed:
            try:
                await interaction.followup.send(
                    "⚠️ Tu equipo quedó asignado, pero no pude actualizar tu apodo. "
                    "El bot necesita **Administrar apodos** y tener su rol por encima del tuyo.",
                    ephemeral=True,
                )
            except discord.HTTPException:
                pass

    callback._ajap_nickname_wrapped = True
    teams.TeamSelect.callback = callback


def _patch_unlink_view():
    original_init = teams.ConfirmUnlinkView.__init__
    if getattr(original_init, "_ajap_nickname_wrapped", False):
        return

    def __init__(self, user_id, team):
        original_init(self, user_id, team)
        for item in self.children:
            if getattr(item, "label", None) != "Desvincular equipo":
                continue
            original_callback = item.callback

            async def callback(interaction, _original=original_callback, _view=self):
                had_team = teams.club_de(_view.user_id)
                await _original(interaction)
                if (
                    had_team
                    and interaction.guild
                    and teams.club_de(_view.user_id) is None
                ):
                    await _restore_member_nickname(interaction.guild, _view.user_id)

            item.callback = callback
            break

    __init__._ajap_nickname_wrapped = True
    teams.ConfirmUnlinkView.__init__ = __init__


def _patch_market_command():
    original = teams.mercado_command
    if getattr(original, "_ajap_nickname_wrapped", False):
        return

    async def mercado_command(interaction: discord.Interaction):
        team = teams.club_de(interaction.user.id)
        if team:
            await _apply_club_nickname(interaction, team)
        await original(interaction)

    mercado_command._ajap_nickname_wrapped = True
    teams.mercado_command = mercado_command


def apply_member_nickname_patch():
    """Patch assignment UI before run_bot registers Discord commands/views."""
    _patch_team_select()
    _patch_unlink_view()
    _patch_market_command()
    print("AJAP: apodos automáticos Nombre | Equipo activos para jugadores y admins")


apply_member_nickname_patch()
