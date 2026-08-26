"""DT resignation flow for AJAP Transfer Market.

Adds a red resignation button to the market menu. A resignation:
- removes the DT role safely;
- frees only the Discord <-> club assignment (never the roster);
- records RENUNCIA_DT in assignment history;
- restores the manager's original nickname;
- alerts Staff/PES;
- reuses the existing rich free-team vacancy announcement;
- posts a public resignation notice in the configured market channel.
"""

from __future__ import annotations

import discord

import dt_role_patch as dt_roles
import free_team_vacancy_patch as vacancies
import guild_isolation_patch as guild_isolation
import market_usage_channel_patch as market_channels
import member_nickname_patch as nicknames
import team_assignment as teams

APP = None
BOT = None


async def _resolve_channel(guild, channel_id):
    if guild is None or not channel_id:
        return None
    channel = guild.get_channel(int(channel_id))
    if channel is None and BOT is not None:
        try:
            channel = await BOT.fetch_channel(int(channel_id))
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            channel = None
    return channel if channel is not None and hasattr(channel, "send") else None


async def _staff_notice(interaction: discord.Interaction, club: str) -> bool:
    """Shared Staff/PES channel first; admin DMs are a fallback."""
    guild = interaction.guild
    if guild is None:
        return False

    embed = discord.Embed(
        title="🚪 Renuncia de DT",
        description=(
            f"{interaction.user.mention} renunció al cargo de DT de **{club}**.\n\n"
            "✅ El equipo quedó libre.\n"
            "✅ La plantilla y el estado económico del club se conservaron."
        ),
        color=discord.Color.orange(),
    )
    embed.add_field(name="👤 DT saliente", value=interaction.user.mention, inline=True)
    embed.add_field(name="🏟️ Club", value=club, inline=True)
    embed.set_footer(text=f"Usuario: {interaction.user} • ID {interaction.user.id}")

    delivered = False
    try:
        channel = await vacancies._staff_report_channel(guild)
    except Exception:
        channel = None

    if channel is not None:
        try:
            await channel.send(embed=embed)
            delivered = True
        except (discord.Forbidden, discord.HTTPException):
            pass

    if delivered:
        return True

    recipients = {}
    owner = getattr(guild, "owner", None)
    if owner is not None and not owner.bot:
        recipients[owner.id] = owner
    for member in getattr(guild, "members", []):
        try:
            if not member.bot and member.guild_permissions.administrator:
                recipients[member.id] = member
        except AttributeError:
            continue

    for member in recipients.values():
        try:
            await member.send(embed=embed)
            delivered = True
        except (discord.Forbidden, discord.HTTPException):
            pass
    return delivered


async def _market_notice(interaction: discord.Interaction, club: str) -> bool:
    """Post in the configured market channel; the click channel is a safe fallback."""
    guild = interaction.guild
    if guild is None:
        return False

    channel = None
    try:
        channel_id = market_channels.get_market_channel_id(guild.id)
        channel = await _resolve_channel(guild, channel_id)
    except Exception:
        channel = None

    if channel is None and interaction.channel is not None and hasattr(interaction.channel, "send"):
        channel = interaction.channel
    if channel is None:
        return False

    embed = discord.Embed(
        title="🚪 RENUNCIA DE DT",
        description=(
            f"{interaction.user.mention} renunció al cargo de DT de **{club}**.\n\n"
            "El club quedó oficialmente **sin DT**."
        ),
        color=discord.Color.red(),
    )
    try:
        await channel.send(embed=embed)
        return True
    except (discord.Forbidden, discord.HTTPException):
        return False


def _resign_assignment(user_id: int, expected_club: str):
    """Atomically free the club and audit the action as a real resignation."""
    conn = teams.db()
    try:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT name FROM clubs WHERE user_id = ? LIMIT 1",
            (int(user_id),),
        ).fetchone()
        if not row or str(row["name"]).casefold() != str(expected_club).casefold():
            conn.rollback()
            return None

        club = str(row["name"])
        conn.execute("DELETE FROM clubs WHERE user_id = ?", (int(user_id),))
        conn.execute(
            """
            INSERT INTO club_assignment_history (user_id, club, action, actor_id)
            VALUES (?, ?, 'RENUNCIA_DT', ?)
            """,
            (int(user_id), club, int(user_id)),
        )
        conn.commit()
        return club
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


class ConfirmResignationView(discord.ui.View):
    def __init__(self, club: str):
        super().__init__(timeout=90)
        self.club = club

    @discord.ui.button(
        label="Sí, renunciar",
        emoji="🚪",
        style=discord.ButtonStyle.danger,
    )
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        current = APP.club_de(interaction.user.id)
        if not current or current.casefold() != self.club.casefold():
            await interaction.response.edit_message(
                content="⚠️ Ya no estás asignado a ese equipo.",
                embed=None,
                view=None,
            )
            return

        # Remove market-access role first. If Discord blocks it, do not leave a
        # manager unassigned while still retaining DT access.
        ok, role_result, removed_role = await dt_roles._remove_dt(
            interaction.guild,
            interaction.user.id,
            reason=f"AJAP: renuncia voluntaria de {current}",
            require_config=False,
        )
        if not ok:
            await interaction.response.edit_message(
                content=str(role_result),
                embed=None,
                view=None,
            )
            return

        try:
            club = _resign_assignment(interaction.user.id, current)
        except Exception as exc:
            if removed_role:
                try:
                    await dt_roles._grant_dt(
                        interaction.guild,
                        interaction.user.id,
                        reason="AJAP: rollback de rol DT por error al procesar renuncia",
                    )
                except Exception:
                    pass
            print(f"ERROR AJAP renuncia: no se pudo liberar {current}: {exc}")
            await interaction.response.edit_message(
                content="⚠️ No se pudo completar la renuncia. El club sigue asignado.",
                embed=None,
                view=None,
            )
            return

        if not club:
            if removed_role:
                try:
                    await dt_roles._grant_dt(
                        interaction.guild,
                        interaction.user.id,
                        reason="AJAP: rollback de rol DT por asignación ya modificada",
                    )
                except Exception:
                    pass
            await interaction.response.edit_message(
                content="⚠️ La asignación cambió antes de confirmar. No se procesó la renuncia.",
                embed=None,
                view=None,
            )
            return

        nickname_ok = True
        if interaction.guild is not None:
            try:
                nickname_ok = await nicknames._restore_member_nickname(
                    interaction.guild,
                    interaction.user.id,
                )
            except Exception as exc:
                nickname_ok = False
                print(f"WARNING AJAP renuncia: no se pudo restaurar apodo: {exc}")

        await interaction.response.edit_message(
            embed=discord.Embed(
                title="✅ Renuncia confirmada",
                description=(
                    f"Renunciaste al cargo de DT de **{club}**.\n\n"
                    "El equipo quedó libre y su plantilla permanece intacta."
                ),
                color=discord.Color.red(),
            ),
            view=None,
        )

        # Reuse exactly the vacancy system already used for admin unlinking.
        vacancy_ok = False
        try:
            vacancy_ok = await vacancies._publish_vacancy(interaction.guild, club)
        except Exception as exc:
            print(f"WARNING AJAP renuncia: anuncio de vacante falló: {exc}")

        staff_ok = await _staff_notice(interaction, club)
        market_ok = await _market_notice(interaction, club)

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

    @discord.ui.button(
        label="Cancelar",
        emoji="✖️",
        style=discord.ButtonStyle.secondary,
    )
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(
            content="Renuncia cancelada.", embed=None, view=None
        )


class ResignButton(discord.ui.Button):
    def __init__(self):
        super().__init__(
            label="Renunciar como DT",
            emoji="🚪",
            style=discord.ButtonStyle.danger,
            row=4,
        )

    async def callback(self, interaction: discord.Interaction):
        club = APP.club_de(interaction.user.id)
        if not club:
            await interaction.response.send_message(
                "⚠️ No tenés un equipo asignado.", ephemeral=True
            )
            return

        await interaction.response.send_message(
            embed=discord.Embed(
                title="⚠️ Confirmar renuncia",
                description=(
                    f"¿Seguro que querés renunciar como DT de **{club}**?\n\n"
                    "Esta acción liberará el equipo inmediatamente, quitará tu rol DT "
                    "y anunciará la vacante. **La plantilla no se borra.**"
                ),
                color=discord.Color.red(),
            ),
            view=ConfirmResignationView(club),
            ephemeral=True,
        )


def build_resignation_market_view(base_view):
    class ResignationMarketView(base_view):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            if any(isinstance(item, ResignButton) for item in self.children):
                return
            try:
                self.add_item(ResignButton())
            except ValueError:
                button = ResignButton()
                button.row = None
                self.add_item(button)

    ResignationMarketView.__name__ = "MercadoView"
    return ResignationMarketView


def apply_dt_resignation_patch(runtime, bot):
    global APP, BOT
    APP = runtime
    BOT = bot

    if getattr(runtime, "_ajap_dt_resignation_patch", False):
        return

    runtime.MercadoView = build_resignation_market_view(runtime.MercadoView)
    runtime.ConfirmResignationView = ConfirmResignationView
    runtime._ajap_dt_resignation_patch = True
    print(
        "AJAP renuncia DT activa: botón rojo + rol/apodo + Staff + vacante + anuncio mercado"
    )


# bot.py imports this module before run_bot imports apply_guild_isolation_patch.
# Wrap that final startup layer so vacancies, DT role and guild DB isolation are
# already installed before we attach the resignation workflow.
_original_apply_guild_isolation_patch = guild_isolation.apply_guild_isolation_patch


def _apply_guild_isolation_then_resignation(runtime, bot):
    _original_apply_guild_isolation_patch(runtime, bot)
    apply_dt_resignation_patch(runtime, bot)


if not getattr(
    guild_isolation.apply_guild_isolation_patch,
    "_ajap_dt_resignation_wrapped",
    False,
):
    _apply_guild_isolation_then_resignation._ajap_dt_resignation_wrapped = True
    guild_isolation.apply_guild_isolation_patch = _apply_guild_isolation_then_resignation
