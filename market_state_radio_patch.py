"""Publica en Radio Pasillo los carteles reales al abrir/cerrar el mercado.

La publicación queda enganchada a los botones reales del panel Staff y sólo se
hace cuando el estado del mercado cambia de verdad. La persistencia del mercado
ocurre antes; un fallo de Discord al publicar la imagen nunca revierte ni rompe
la apertura/cierre.
"""

from __future__ import annotations

import base64
import io
from pathlib import Path

import discord

import radio_pasillo_feature_ads_patch as radio_pasillo
import staff_admin_organized_patch as staff_admin


_OPEN_ID = "ajap_admin_open_market"
_CLOSE_ID = "ajap_admin_close_market"
_ASSET_OPEN = Path(__file__).with_name("mercado_abierto.webp.b64")
_ASSET_CLOSED = Path(__file__).with_name("mercado_cerrado.webp.b64")

_APPLIED = False
_ORIGINAL_PROXY_CALLBACK = None


def _market_is_open(runtime: object) -> bool:
    return bool(runtime.mercado_abierto())


def _load_artwork(is_open: bool) -> bytes:
    path = _ASSET_OPEN if is_open else _ASSET_CLOSED
    encoded = path.read_text(encoding="ascii").strip()
    return base64.b64decode(encoded, validate=True)


async def _publish_radio_pasillo(interaction: discord.Interaction, is_open: bool) -> None:
    guild = interaction.guild
    if guild is None:
        return

    state = "ABIERTO" if is_open else "CERRADO"
    filename = "mercado_de_pases_abierto.webp" if is_open else "mercado_de_pases_cerrado.webp"

    try:
        channel = await radio_pasillo._resolve_radio_channel(guild)
        artwork = _load_artwork(is_open)
        await channel.send(
            file=discord.File(io.BytesIO(artwork), filename=filename),
            allowed_mentions=discord.AllowedMentions.none(),
        )
        print(f"AJAP Radio Pasillo: cartel de mercado {state} publicado en {guild.name}.")
    except Exception as exc:
        # El cambio de estado ya fue confirmado/persistido. La publicación es un
        # efecto secundario y jamás debe hacer fallar la acción administrativa.
        print(
            f"WARNING AJAP Radio Pasillo: mercado {state} confirmado pero no se pudo "
            f"publicar el cartel en guild={getattr(guild, 'id', '?')}: {exc!r}"
        )


def apply_market_state_radio_patch(runtime: object, bot: discord.Client | None = None) -> None:
    """Conecta Radio Pasillo a los botones Staff Abrir/Cerrar mercado."""
    del bot  # la firma se mantiene homogénea con el resto de parches del proyecto

    global _APPLIED, _ORIGINAL_PROXY_CALLBACK
    if _APPLIED:
        return

    proxy_cls = getattr(staff_admin, "ProxyAdminButton", None)
    if proxy_cls is None:
        raise RuntimeError("ProxyAdminButton no disponible para conectar Radio Pasillo al mercado")

    original_callback = proxy_cls.callback
    _ORIGINAL_PROXY_CALLBACK = original_callback

    async def callback(self, interaction: discord.Interaction) -> None:
        custom_id = str(getattr(self, "custom_id", "") or "")
        is_market_button = custom_id in {_OPEN_ID, _CLOSE_ID}

        before = None
        if is_market_button:
            try:
                before = _market_is_open(runtime)
            except Exception as exc:
                print(f"WARNING AJAP Radio Pasillo: no se pudo leer estado previo del mercado: {exc!r}")

        # Ejecuta primero la acción REAL del bot. Ahí se validan permisos, cambia
        # el estado, se persiste SQLite y se ejecutan los demás efectos existentes.
        await original_callback(self, interaction)

        if not is_market_button or before is None:
            return

        try:
            after = _market_is_open(runtime)
        except Exception as exc:
            print(f"WARNING AJAP Radio Pasillo: no se pudo leer estado final del mercado: {exc!r}")
            return

        desired = custom_id == _OPEN_ID
        # Sólo publicación por transición real: cerrado->abierto o abierto->cerrado.
        # Repetir el mismo botón sin cambio no genera spam.
        if before != after and after == desired:
            await _publish_radio_pasillo(interaction, after)

    proxy_cls.callback = callback
    _APPLIED = True
    print("AJAP Radio Pasillo: carteles automáticos de apertura/cierre de mercado activos.")
