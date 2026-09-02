"""Auto-configure the Discord match-search bridge to the league rival channel.

This is a production fallback for guilds that have not yet saved a channel via
/canal_partidos.  It discovers the existing BUSCAR-RIVAL-LIGA text channel,
persists its ID in the bridge table, and then lets the normal bridge publish and
update the same cards there.  A later explicit /canal_partidos selection still
overrides this fallback because discovery only runs when no channel is saved.
"""

from __future__ import annotations

import unicodedata
from contextlib import closing

import match_search_discord_bridge_patch as bridge


def _norm(value: str) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return "".join(ch.lower() for ch in text if ch.isalnum())


def _find_match_channel(guild):
    channels = list(getattr(guild, "text_channels", []) or [])
    if not channels:
        return None

    # Preferred production channel shown in AJPA: ⚔️ | BUSCAR-RIVAL-LIGA.
    for channel in channels:
        if _norm(getattr(channel, "name", "")) == "buscarrivalliga":
            return channel

    # Tolerate Discord name decoration/emoji changes without matching unrelated
    # channels such as mercado/resultados.
    for channel in channels:
        name = _norm(getattr(channel, "name", ""))
        if "buscar" in name and "rival" in name and "liga" in name:
            return channel
    return None


_original_sync_guild = bridge.sync_guild


async def _sync_guild_with_auto_channel(guild):
    if bridge.APP is not None and bridge.BOT is not None and guild is not None:
        try:
            with closing(bridge._conn_for_guild(guild.id)) as conn:
                bridge._ensure_schema(conn)
                configured = bridge._channel_id(conn, guild.id)
                if not configured:
                    channel = _find_match_channel(guild)
                    if channel is not None:
                        configured_by = int(getattr(getattr(bridge.BOT, "user", None), "id", 0) or 0)
                        bridge._set_channel(
                            conn,
                            int(guild.id),
                            int(channel.id),
                            configured_by,
                        )
                        print(
                            "AJPA Buscar Partido: canal auto-configurado "
                            f"guild={guild.id} channel={channel.id} name={channel.name}"
                        )
        except Exception as exc:
            # Auto-discovery must never block the normal bridge worker.
            print(
                f"AJPA Buscar Partido auto-channel error guild={getattr(guild, 'id', '?')}: "
                f"{type(exc).__name__}: {exc}"
            )

    await _original_sync_guild(guild)


if not getattr(bridge.sync_guild, "_ajpa_auto_match_channel", False):
    _sync_guild_with_auto_channel._ajpa_auto_match_channel = True
    bridge.sync_guild = _sync_guild_with_auto_channel
