"""Automatically finish legacy approved free-agent signings.

Before the final free-agent approval fix, Staff approval left JUGADOR LIBRE
operations in APROBADA and required a second "Cargado en PES" click. Those stale
rows must not leave the market report saying the move happened while the official
roster still shows the player as Jugador Libre.

This patch installs after guild isolation and reconciles only the current guild
DB. It never changes normal transfers/loans/swaps: only APROBADA operations whose
seller/type identifies Jugador Libre are eligible. The destination max-32 rule is
revalidated before moving the player.
"""

from __future__ import annotations

import asyncio

import galatasaray_roster_patch as galatasaray


_ORIGINAL_GALATASARAY_APPLY = galatasaray.apply_galatasaray_json
_WARNED = set()


def _tables(conn):
    return {
        str(row["name"])
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }


def _columns(conn, table):
    return {
        str(row["name"])
        for row in conn.execute(f"PRAGMA table_info({table})").fetchall()
    }


def _stale_rows(conn):
    transfer_cols = _columns(conn, "transfers")
    if "status" not in transfer_cols or "seller" not in transfer_cols:
        return []

    free_agent_match = "LOWER(TRIM(COALESCE(seller,'')))='jugador libre'"
    if "operation_type" in transfer_cols:
        free_agent_match = (
            "(" + free_agent_match + " OR "
            "UPPER(TRIM(COALESCE(operation_type,'')))='JUGADOR LIBRE')"
        )

    return conn.execute(
        f"""
        SELECT *
        FROM transfers
        WHERE UPPER(TRIM(COALESCE(status,'')))='APROBADA'
          AND {free_agent_match}
        ORDER BY id ASC
        """
    ).fetchall()


def _player_for_transfer(conn, row, transfer_cols):
    if "player_id" in transfer_cols and row["player_id"]:
        player = conn.execute(
            "SELECT * FROM roster_players WHERE id=? LIMIT 1",
            (int(row["player_id"]),),
        ).fetchone()
        if player:
            return player
    return conn.execute(
        "SELECT * FROM roster_players WHERE name=? COLLATE NOCASE LIMIT 1",
        (row["player"],),
    ).fetchone()


def _manager_ids(conn, buyer):
    if "clubs" not in _tables(conn):
        return []
    try:
        rows = conn.execute(
            "SELECT user_id FROM clubs WHERE name=? COLLATE NOCASE",
            (buyer,),
        ).fetchall()
    except Exception:
        return []
    return [int(row["user_id"]) for row in rows if row["user_id"]]


def _insert_history_if_needed(conn, row, player, transfer_cols, buyer):
    if "player_history" not in _tables(conn):
        return
    history_cols = _columns(conn, "player_history")
    required = {"player_id", "player", "from_club", "to_club", "transfer_id", "event_type"}
    if not required.issubset(history_cols):
        return

    exists = conn.execute(
        "SELECT 1 FROM player_history WHERE transfer_id=? LIMIT 1",
        (int(row["id"]),),
    ).fetchone()
    if exists:
        return

    columns = ["player_id", "player", "from_club", "to_club", "transfer_id"]
    values = [
        int(player["id"]),
        row["player"],
        "Jugador Libre",
        buyer,
        int(row["id"]),
    ]
    if "season_id" in history_cols:
        columns.append("season_id")
        values.append(row["season_id"] if "season_id" in transfer_cols else None)
    columns.append("event_type")
    values.append("JUGADOR LIBRE")

    marks = ", ".join("?" for _ in columns)
    conn.execute(
        f"INSERT INTO player_history ({', '.join(columns)}) VALUES ({marks})",
        tuple(values),
    )


def _mark_applied(conn, row, transfer_cols):
    updates = ["status='APLICADA'"]
    params = []

    if "applied_by" in transfer_cols and "approved_by" in transfer_cols:
        updates.append("applied_by=COALESCE(applied_by, approved_by)")
    if "applied_at" in transfer_cols:
        updates.append("applied_at=COALESCE(applied_at, CURRENT_TIMESTAMP)")
    if "pes_loaded_by" in transfer_cols:
        if "approved_by" in transfer_cols:
            updates.append("pes_loaded_by=COALESCE(pes_loaded_by, approved_by)")
        else:
            updates.append("pes_loaded_by=COALESCE(pes_loaded_by, 0)")
    if "pes_loaded_at" in transfer_cols:
        updates.append("pes_loaded_at=COALESCE(pes_loaded_at, CURRENT_TIMESTAMP)")

    params.append(int(row["id"]))
    conn.execute(
        f"UPDATE transfers SET {', '.join(updates)} WHERE id=?",
        tuple(params),
    )


def _warn_once(guild_id, transfer_id, message):
    key = (int(guild_id), int(transfer_id), str(message))
    if key in _WARNED:
        return
    _WARNED.add(key)
    print(
        "WARNING AJAP agente libre legacy: "
        f"guild={guild_id} transfer={transfer_id} • {message}"
    )


def _reconcile_connection(runtime, conn, guild_id):
    tables = _tables(conn)
    if "transfers" not in tables or "roster_players" not in tables:
        return []
    if conn.in_transaction:
        return []

    preview = _stale_rows(conn)
    if not preview:
        return []

    import squad_limits_patch as squad_limits

    transfer_cols = _columns(conn, "transfers")
    notifications = []
    conn.execute("BEGIN IMMEDIATE")
    try:
        # Re-read under the write lock so two simultaneous interactions cannot
        # apply or notify the same legacy operation twice.
        rows = _stale_rows(conn)
        for row in rows:
            transfer_id = int(row["id"])
            buyer = str(row["buyer"] or "").strip()
            if not buyer:
                _warn_once(guild_id, transfer_id, "sin club de destino")
                continue

            player = _player_for_transfer(conn, row, transfer_cols)
            if not player:
                _warn_once(
                    guild_id,
                    transfer_id,
                    f"no se encontró el jugador {row['player']}",
                )
                continue

            current_club = str(player["club"] or "").strip()
            already_in_buyer = current_club.casefold() == buyer.casefold()
            still_free = current_club.casefold() == "jugador libre"
            if not already_in_buyer and not still_free:
                _warn_once(
                    guild_id,
                    transfer_id,
                    f"{row['player']} figura en {current_club}, no en Jugador Libre",
                )
                continue

            if still_free:
                ok, reason = squad_limits.validate_free_agent(conn, buyer)
                if not ok:
                    _warn_once(guild_id, transfer_id, reason or "destino sin cupo")
                    continue
                conn.execute(
                    "UPDATE roster_players SET club=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                    (buyer, int(player["id"])),
                )

            _mark_applied(conn, row, transfer_cols)
            _insert_history_if_needed(conn, row, player, transfer_cols, buyer)
            for user_id in _manager_ids(conn, buyer):
                notifications.append((user_id, str(row["player"]), buyer))

            print(
                "AJAP agente libre legacy reconciliado: "
                f"guild={guild_id} • {row['player']} -> {buyer} • transfer={transfer_id}"
            )

        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return notifications


async def _send_dm(runtime, user_id, player, buyer):
    bot = getattr(runtime, "bot", None)
    if bot is None:
        return
    try:
        user = bot.get_user(int(user_id))
        if user is None:
            user = await bot.fetch_user(int(user_id))
        await user.send(
            "✅ **FICHAJE APROBADO POR STAFF**\n\n"
            f"El Staff aprobó el fichaje de **{player}**.\n"
            f"➡️ **Nuevo club:** {buyer}\n"
            "💰 **Costo:** $0\n\n"
            "📋 El jugador ya fue incorporado al plantel oficial de tu club."
        )
    except Exception as exc:
        print(
            "WARNING AJAP: no se pudo enviar DM de reconciliación de agente libre "
            f"a user_id={user_id}: {exc}"
        )


def _schedule_notifications(runtime, notifications):
    if not notifications:
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return

    seen = set()
    for user_id, player, buyer in notifications:
        key = (int(user_id), player.casefold(), buyer.casefold())
        if key in seen:
            continue
        seen.add(key)
        loop.create_task(_send_dm(runtime, user_id, player, buyer))


def _install_reconciler(runtime):
    current_db = runtime.db
    if getattr(current_db, "_ajap_free_agent_legacy_reconcile", False):
        return False

    def reconciled_db(_fallback=current_db):
        conn = _fallback()
        try:
            guild_id = int(runtime.current_guild_id())
        except Exception:
            return conn
        if guild_id <= 0:
            return conn

        try:
            notifications = _reconcile_connection(runtime, conn, guild_id)
        except Exception as exc:
            try:
                conn.rollback()
            except Exception:
                pass
            print(
                "WARNING AJAP: reconciliación automática de agentes libres falló "
                f"guild={guild_id}: {exc}"
            )
            return conn

        _schedule_notifications(runtime, notifications)
        return conn

    reconciled_db._ajap_free_agent_legacy_reconcile = True
    runtime.db = reconciled_db
    print(
        "AJAP agentes libres legacy: APROBADA -> APLICADA se reconcilia "
        "automáticamente por servidor"
    )
    return True


def _apply_galatasaray_then_reconcile(runtime, *args, **kwargs):
    result = _ORIGINAL_GALATASARAY_APPLY(runtime, *args, **kwargs)
    _install_reconciler(runtime)
    return result


if not getattr(
    galatasaray.apply_galatasaray_json,
    "_ajap_free_agent_legacy_reconcile_wrapped",
    False,
):
    _apply_galatasaray_then_reconcile._ajap_free_agent_legacy_reconcile_wrapped = True
    galatasaray.apply_galatasaray_json = _apply_galatasaray_then_reconcile
