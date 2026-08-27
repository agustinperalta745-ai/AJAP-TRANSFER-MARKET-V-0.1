"""Final hardening for Discord modal submits.

Some discord.py 2.x releases changed private Modal internals. AJAP has several
wrappers around guild isolation and channel gating, so a private signature
mismatch can fail BEFORE Modal.on_submit runs and Discord only shows the generic
"Algo ha fallado" banner.

This module is imported last. It replaces only Modal._scheduled_task with a
version-tolerant implementation that:
- restores the current guild context,
- refreshes submitted TextInput values across supported discord.py signatures,
- runs interaction checks and on_submit,
- forwards real exceptions to Modal.on_error instead of dying before the modal
  callback can acknowledge Discord.
"""

from __future__ import annotations

import traceback

import discord

import guild_isolation_patch as guild_isolation


_ORIGINAL_APPLY_GUILD_ISOLATION = guild_isolation.apply_guild_isolation_patch


def _refresh_modal(modal, interaction, components, extra):
    refresh = getattr(modal, "_refresh", None)
    if refresh is None:
        return

    resolved = extra[0] if extra else {}

    # discord.py 2.6+: _refresh(interaction, components, resolved)
    try:
        refresh(interaction, components, resolved)
        return
    except TypeError:
        pass

    # Intermediate/older variants.
    try:
        refresh(interaction, components)
        return
    except TypeError:
        pass

    # discord.py 2.4/2.5 style fallback.
    refresh(components)


async def _safe_modal_error(modal, interaction, error):
    print(
        f"ERROR AJAP modal {modal.__class__.__name__}: {type(error).__name__}: {error}\n"
        + "".join(traceback.format_exception(type(error), error, error.__traceback__))
    )
    try:
        await modal.on_error(interaction, error)
    except Exception as nested:
        print(
            f"ERROR AJAP modal on_error {modal.__class__.__name__}: "
            f"{type(nested).__name__}: {nested}"
        )
        try:
            if not interaction.response.is_done():
                await interaction.response.send_message(
                    "⚠️ No pude procesar este formulario. Volvé a intentarlo en unos segundos.",
                    ephemeral=True,
                )
            else:
                await interaction.followup.send(
                    "⚠️ No pude procesar este formulario. Volvé a intentarlo en unos segundos.",
                    ephemeral=True,
                )
        except Exception:
            pass


def _install_final_modal_scheduler():
    current = discord.ui.Modal._scheduled_task
    if getattr(current, "_ajap_final_modal_hardening", False):
        return

    async def hardened_modal_task(self, interaction, components, *extra):
        try:
            guild_id = guild_isolation._interaction_guild_id(interaction)
            token = guild_isolation._CURRENT_GUILD_ID.set(guild_id)
        except Exception as exc:
            await _safe_modal_error(self, interaction, exc)
            return

        try:
            try:
                refresh_timeout = getattr(self, "_refresh_timeout", None)
                if callable(refresh_timeout):
                    refresh_timeout()

                _refresh_modal(self, interaction, components, extra)

                check = getattr(self, "interaction_check", None)
                if callable(check):
                    allowed = await check(interaction)
                    if not allowed:
                        return

                await self.on_submit(interaction)
            except Exception as exc:
                await _safe_modal_error(self, interaction, exc)
            else:
                try:
                    self.stop()
                except Exception:
                    pass
        finally:
            guild_isolation._CURRENT_GUILD_ID.reset(token)

    hardened_modal_task._ajap_guild_context = True
    hardened_modal_task._ajap_final_modal_hardening = True
    discord.ui.Modal._scheduled_task = hardened_modal_task
    print("AJAP modal hardening FINAL activo: submit multi-version + contexto guild")


def _apply_guild_isolation_then_harden_modals(runtime, bot):
    _ORIGINAL_APPLY_GUILD_ISOLATION(runtime, bot)
    _install_final_modal_scheduler()


if not getattr(
    guild_isolation.apply_guild_isolation_patch,
    "_ajap_final_modal_hardening_wrapper",
    False,
):
    _apply_guild_isolation_then_harden_modals._ajap_final_modal_hardening_wrapper = True
    guild_isolation.apply_guild_isolation_patch = _apply_guild_isolation_then_harden_modals

# Última regla de entrada al mercado: una invocación NUEVA de /mercado hecha
# por Staff siempre vuelve al dashboard Staff aunque el admin haya quedado
# afiliado a un club durante una prueba de Perfil Usuario.
import staff_market_entry_guard_patch  # noqa: F401,E402
