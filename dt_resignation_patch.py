"""DT resignation flow for AJAP Transfer Market.

Adds a red resignation button to the market menu. A resignation frees the team
without touching its roster, alerts staff, publishes the usual free-team notice,
and posts a public notice in the market channel.
"""

import discord

APP = None


def _channel_from_config(guild, *names):
    """Best-effort lookup for configured channels or common channel names."""
    for attr in names:
        value = getattr(APP, attr, None)
        try:
            channel_id = int(value) if value is not None else None
        except (TypeError, ValueError):
            channel_id = None
        if channel_id:
            channel = guild.get_channel(channel_id)
            if channel:
                return channel

    lowered = {str(name).casefold().replace("_", "-") for name in names}
    for channel in getattr(guild, "text_channels", []):
        cname = channel.name.casefold()
        if any(key in cname for key in lowered):
            return channel
    return None


async def _send_staff_notice(interaction, club):
    guild = interaction.guild
    if guild is None:
        return

    channel = _channel_from_config(
        guild,
        "STAFF_REVIEW_CHANNEL_ID",
        "STAFF_CHANNEL_ID",
        "staff",
        "administracion",
    )
    if not channel:
        return

    embed = discord.Embed(
        title="📋 Renuncia de DT",
        description=(
            f"{interaction.user.mention} renunció al cargo de DT de **{club}**.\n\n"
            "El equipo quedó libre y disponible para una nueva asignación."
        ),
    )
    try:
        await channel.send(embed=embed)
    except Exception as exc:
        print(f"AJAP renuncia: no se pudo avisar al staff: {exc}")


async def _send_market_notice(interaction, club):
    guild = interaction.guild
    if guild is None:
        return

    channel = _channel_from_config(
        guild,
        "MARKET_CHANNEL_ID",
        "MERCADO_CHANNEL_ID",
        "mercado-de-pases",
        "mercado",
    )
    if not channel:
        return

    embed = discord.Embed(
        title="🚪 Renuncia de DT",
        description=(
            f"{interaction.user.mention} renunció al cargo de DT de **{club}**.\n\n"
            "El equipo quedó libre."
        ),
    )
    try:
        await channel.send(embed=embed)
    except Exception as exc:
        print(f"AJAP renuncia: no se pudo publicar en mercado: {exc}")


async def _send_free_team_announcement(interaction, club):
    """Reuse the vacancy/free-team announcement when the installed patch exposes it."""
    candidates = [
        "announce_free_team",
        "anunciar_equipo_libre",
        "send_free_team_announcement",
        "publicar_equipo_libre",
    ]
    for name in candidates:
        func = getattr(APP, name, None)
        if not callable(func):
            continue
        for args in (
            (interaction.guild, club),
            (interaction, club),
            (club, interaction.guild),
            (club,),
        ):
            try:
                result = func(*args)
                if hasattr(result, "__await__"):
                    await result
                return
            except TypeError:
                continue
            except Exception as exc:
                print(f"AJAP renuncia: anuncio de equipo libre falló vía {name}: {exc}")
                return

    # Fallback: publish a standard vacancy notice in the best available public channel.
    guild = interaction.guild
    if guild is None:
        return
    channel = _channel_from_config(
        guild,
        "FREE_TEAM_CHANNEL_ID",
        "VACANCY_CHANNEL_ID",
        "MARKET_CHANNEL_ID",
        "MERCADO_CHANNEL_ID",
        "equipos-libres",
        "mercado-de-pases",
        "mercado",
    )
    if channel:
        embed = discord.Embed(
            title="🟢 EQUIPO LIBRE",
            description=(
                f"**{club}** quedó libre y ya puede ser elegido por un nuevo DT.\n\n"
                "Abrí `/mercado` para consultar los equipos disponibles."
            ),
        )
        try:
            await channel.send(embed=embed)
        except Exception as exc:
            print(f"AJAP renuncia: fallback de equipo libre falló: {exc}")


def _unlink_user(user_id, actor_id=None):
    """Use the current assignment layer and preserve the club roster."""
    try:
        import team_assignment as teams
        current = teams.club_de(user_id)
        if not current:
            return None
        try:
            return teams.unlink_team(user_id, actor_id)
        except TypeError:
            return teams.unlink_team(user_id)
    except Exception:
        pass

    # Fallback for installations exposing assignment helpers on the app module.
    current = APP.club_de(user_id) if hasattr(APP, "club_de") else None
    if not current:
        return None
    unlink = getattr(APP, "unlink_team", None)
    if callable(unlink):
        try:
            return unlink(user_id, actor_id)
        except TypeError:
            return unlink(user_id)
    return None


class ConfirmResignationView(discord.ui.View):
    def __init__(self, club):
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

        club = current
        removed = _unlink_user(interaction.user.id, interaction.user.id)
        if not removed:
            await interaction.response.edit_message(
                content="⚠️ No se pudo liberar el equipo.",
                embed=None,
                view=None,
            )
            return

        await interaction.response.edit_message(
            embed=discord.Embed(
                title="✅ Renuncia confirmada",
                description=(
                    f"Renunciaste al cargo de DT de **{club}**.\n\n"
                    "La plantilla quedó intacta y el equipo ya está disponible para otro DT."
                ),
            ),
            view=None,
        )

        await _send_staff_notice(interaction, club)
        await _send_free_team_announcement(interaction, club)
        await _send_market_notice(interaction, club)

    @discord.ui.button(
        label="Cancelar",
        emoji="✖️",
        style=discord.ButtonStyle.secondary,
    )
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content="Renuncia cancelada.", embed=None, view=None)


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

        embed = discord.Embed(
            title="⚠️ Confirmar renuncia",
            description=(
                f"¿Seguro que querés renunciar como DT de **{club}**?\n\n"
                "El equipo quedará libre inmediatamente. La plantilla no se borra."
            ),
        )
        await interaction.response.send_message(
            embed=embed,
            view=ConfirmResignationView(club),
            ephemeral=True,
        )


def build_resignation_market_view(base_view):
    class ResignationMarketView(base_view):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            if not any(isinstance(item, ResignButton) for item in self.children):
                try:
                    self.add_item(ResignButton())
                except ValueError:
                    # If row 4 is already full, let Discord auto-place the button.
                    button = ResignButton()
                    button.row = None
                    self.add_item(button)

    ResignationMarketView.__name__ = "MercadoView"
    return ResignationMarketView


def apply_dt_resignation_patch(main_module):
    global APP
    APP = main_module
    main_module.MercadoView = build_resignation_market_view(main_module.MercadoView)
    main_module.ConfirmResignationView = ConfirmResignationView
    print("AJAP DT resignation button enabled.")
