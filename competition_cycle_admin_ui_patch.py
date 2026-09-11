"""Surface the official AJPA cycle inside Administración without coupling it to the market."""

import discord

# This module is imported by bot.py before run_bot. Loading the startup wrapper
# here guarantees that run_bot receives the final manual-GES guild setup.
import ges_manual_sync_startup_patch  # noqa: F401
import competition_cycle as cycle
import staff_admin_organized_patch as staff


# The competition lifecycle and the transfer market are independent systems.
# competition_cycle.advance() still calls its legacy _market() hook while moving
# between historical phase names (market_1/market_2). Neutralize ONLY that hook
# here so changing an AJPA stage can never open/close the real market_state.
# Staff's normal ABRIR/CERRAR MERCADO buttons remain the sole authority.
def _ignore_cycle_market_change(conn, opened, user_id):
    return None


cycle._market = _ignore_cycle_market_change


# Keep the lifecycle wording explicit: "Mercado 1/2" is a competition stage,
# not an instruction to mutate the manually-controlled transfer market.
def _manual_market_action(phase, n):
    if phase == cycle.PRESEASON:
        return {
            "key": "start_season",
            "label": f"INICIAR TEMPORADA {n}",
            "description": "Archiva la pretemporada y crea la temporada oficial en cero.",
        }
    if phase == cycle.SEASON:
        return {
            "key": "season_market1",
            "label": "AVANZAR A ETAPA MERCADO 1",
            "description": "Archiva la temporada y avanza de etapa. El mercado se abre o cierra manualmente desde Administración.",
        }
    if phase == cycle.MARKET_1:
        return {
            "key": "market1_cup",
            "label": "FINALIZAR ETAPA MERCADO 1 + INICIAR COPA",
            "description": "Finaliza esta etapa e inicia una Copa nueva. No modifica el estado del mercado.",
        }
    if phase == cycle.CUP:
        return {
            "key": "cup_market2",
            "label": "FINALIZAR COPA + AVANZAR A ETAPA MERCADO 2",
            "description": "Archiva la Copa y avanza de etapa. El mercado conserva su estado manual.",
        }
    if phase == cycle.MARKET_2:
        return {
            "key": "market2_season",
            "label": f"FINALIZAR ETAPA MERCADO 2 + INICIAR TEMPORADA {n+1}",
            "description": "Finaliza esta etapa e inicia la siguiente temporada sin abrir ni cerrar el mercado.",
        }
    raise cycle.CycleError(f"Etapa inválida: {phase}")


cycle._action = _manual_market_action


class ManageCycleButton(discord.ui.Button):
    def __init__(self, row=0):
        super().__init__(
            label="GESTIONAR ETAPA",
            emoji="🗓️",
            style=discord.ButtonStyle.primary,
            row=row,
            custom_id="ajpa_admin_manage_cycle",
        )

    async def callback(self, interaction: discord.Interaction):
        if not staff.APP or not staff.APP.es_admin(interaction):
            await interaction.response.send_message("⛔ Solo administradores.", ephemeral=True)
            return
        payload = cycle.runtime_state(staff.APP)
        await interaction.response.send_message(
            embed=cycle.cycle_embed(payload),
            view=cycle.CycleView(staff.APP, staff.BOT, payload),
            ephemeral=True,
        )


def _patch_view(view, remove_needles, *, add_cycle=True):
    if getattr(view, "_ajpa_cycle_admin_ui", False):
        return
    original_init = view.__init__

    def init(self):
        original_init(self)
        for item in list(self.children):
            label = str(getattr(item, "label", "") or "").strip().casefold()
            if any(needle in label for needle in remove_needles):
                self.remove_item(item)
        if add_cycle and not any(
            str(getattr(item, "custom_id", "") or "") == "ajpa_admin_manage_cycle"
            for item in self.children
        ):
            self.add_item(ManageCycleButton(row=0))

    view.__init__ = init
    view._ajpa_cycle_admin_ui = True


def apply_patch():
    # The cycle replaces only the old season-stage control. The MarketView is
    # intentionally left untouched so ABRIR/CERRAR MERCADO stays available and
    # independent at all times.
    _patch_view(staff.ManagementView, ("cambiar temporada",))

    original_embed = staff.admin_home_embed

    def admin_home_embed():
        embed = original_embed()
        try:
            payload = cycle.runtime_state(staff.APP)
            for index, field in enumerate(embed.fields):
                if "temporada" in str(field.name).casefold():
                    embed.set_field_at(
                        index,
                        name="🗓️ Etapa AJPA",
                        value=payload["phase_label"],
                        inline=True,
                    )
                    break
        except Exception:
            pass
        return embed

    staff.admin_home_embed = admin_home_embed

    original_section_embed = staff.section_embed

    def section_embed(title, description, tools):
        items = []
        for item in list(tools):
            text = str(item)
            low = text.casefold()
            if "cambiar temporada" in low:
                text = "🗓️ Gestionar etapa AJPA"
            elif "abrir o cerrar" in low:
                text = "🟢/🔒 Abrir o cerrar mercado manualmente"
            items.append(text)
        return original_section_embed(title, description, items)

    staff.section_embed = section_embed
    print("AJPA Administración: etapa independiente + mercado manual")


apply_patch()

# Install the Radio Pasillo bridge before run_bot builds the persistent market
# runtime. It reacts only to real manual market_state transitions.
import radio_market_status_patch  # noqa: E402,F401
# Materialize the exact transparent artworks supplied by Staff.
import radio_market_status_assets_patch  # noqa: E402,F401

# Keep the countdown layer after the cycle UI wrapper. Market controls remain
# owned by the normal Staff market panel and are never derived from the stage.
import season_countdown_patch  # noqa: E402,F401
