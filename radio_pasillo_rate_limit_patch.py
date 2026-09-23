"""Compatibilidad para la antigua capa global de Radio Pasillo.

Los recordatorios/promociones periódicos ya controlan su propia cadencia de
90 minutos en radio_pasillo_feature_ads_patch. Los eventos operativos reales
(clausulazos, publicaciones de jugadores, GES, clásicos, cierres, etc.) NO deben
quedar bloqueados detrás de ese temporizador: tienen que publicarse en el
momento en que ocurre la acción.

Este módulo conserva el mismo punto de entrada para no romper run_bot.py ni los
wrappers de aislamiento por servidor, pero deliberadamente no reemplaza
Messageable.send ni aplica esperas globales.
"""

from __future__ import annotations

import guild_isolation_patch as guild_isolation


def apply_radio_pasillo_rate_limit_patch(runtime, bot) -> None:
    if getattr(bot, "_ajap_radio_pasillo_rate_limit_patch", False):
        return

    bot._ajap_radio_pasillo_rate_limit_patch = True
    print(
        "AJPA Radio Pasillo: eventos operativos inmediatos; "
        "recordatorios periódicos mantienen su cadencia propia de 90 minutos"
    )


_BASE_APPLY_GUILD_ISOLATION = guild_isolation.apply_guild_isolation_patch


def _apply_guild_isolation_then_radio_rate_limit(runtime, bot):
    _BASE_APPLY_GUILD_ISOLATION(runtime, bot)
    apply_radio_pasillo_rate_limit_patch(runtime, bot)


if not getattr(
    guild_isolation.apply_guild_isolation_patch,
    "_ajap_radio_pasillo_rate_limit_wrapped",
    False,
):
    _apply_guild_isolation_then_radio_rate_limit._ajap_radio_pasillo_rate_limit_wrapped = True
    guild_isolation.apply_guild_isolation_patch = _apply_guild_isolation_then_radio_rate_limit
