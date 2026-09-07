"""Recover the current GES config when an older/mobile DB split left it unconfigured.

This is intentionally conservative: it only auto-seeds the active competition when
there is no saved GES config at all in the league DB and the built-in/current boot
URLs are present. Once one competition has been configured, future competitions
still require their own explicit URLs and never inherit an older season by accident.
"""

from __future__ import annotations

import league_ges_manual_sync_patch as ges
import season_ges_authority_patch as seasonal


def apply_ges_config_recovery(runtime, bot) -> None:
    base_sync = ges.sync_from_ges
    if getattr(base_sync, "_ajpa_ges_config_recovery", False):
        return

    async def sync_with_config_recovery(
        runtime_arg,
        bot_arg,
        guild_id: int,
        staff_user_id: int | None = None,
    ) -> dict:
        try:
            return await base_sync(runtime_arg, bot_arg, int(guild_id), staff_user_id)
        except RuntimeError as exc:
            message = str(exc)
            if "Primero guardá los tres enlaces GES de" not in message:
                raise

            conn = ges.league.db(runtime_arg, int(guild_id))
            try:
                cfg = seasonal._current_config_payload(conn)
                if cfg.get("configured"):
                    raise

                ges_url = str(cfg.get("ges_url") or "").strip()
                results_url = str(cfg.get("results_url") or "").strip()
                scorers_url = str(cfg.get("scorers_url") or "").strip()

                # _current_config_payload exposes boot URLs only when this DB has
                # zero historical GES configs. Therefore this cannot leak a prior
                # competition's URLs into a new season/cup.
                if not (ges_url and results_url and scorers_url):
                    raise

                repaired = seasonal._save_current_config(
                    conn,
                    {
                        "ges_url": ges_url,
                        "results_url": results_url,
                        "scorers_url": scorers_url,
                        "league_id": str(cfg.get("league_id") or ""),
                    },
                    int(staff_user_id or 0),
                )
                print(
                    "AJPA GES recovery: configuración activa reconstruida "
                    f"para {repaired.get('competition_label')} "
                    f"(liga={repaired.get('league_id')})"
                )
            finally:
                conn.close()

            # Retry the exact same final sync chain (including result cards and
            # downstream refreshes) after repairing the persisted config.
            return await base_sync(runtime_arg, bot_arg, int(guild_id), staff_user_id)

    sync_with_config_recovery._ajpa_ges_config_recovery = True
    sync_with_config_recovery._ajpa_ges_config_recovery_base = base_sync
    ges.sync_from_ges = sync_with_config_recovery
    print("AJPA GES recovery enabled: sync can repair missing initial config once")
