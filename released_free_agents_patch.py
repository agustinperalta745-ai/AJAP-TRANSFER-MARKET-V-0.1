"""Released players become $0 free-agent listings in Transferibles.

A confirmed release keeps the player in roster_players as ``Jugador Libre`` and
creates a public $0 listing. Signing that listing is not a normal negotiation:
the interested manager reserves the free agent for $0 and AJAP creates a
PENDIENTE_ADMIN operation. Staff still approves and applies it in PES before the
official roster changes.

The reservation is atomic (BEGIN IMMEDIATE), so two clubs cannot sign the same
free agent at the same time. Transferibles also self-heals listings for previously
released players that are still free and have no pending operation.
"""

from __future__ import annotations

import discord

import negotiation_picker_patch as negotiation
import player_release_patch as releases
import split_transferibles_patch as transferibles
import squad_limits_patch as squad_limits
import staff_review_channel_patch as staff_review


APP = None
BOT = None
FREE_AGENT_CLUB = releases.FREE_AGENT_CLUB
FREE_AGENT_TYPE = "JUGADOR LIBRE"
FREE_AGENT_PRICE = "$0"
PENDING_STATUSES = ("PENDIENTE_ADMIN", "APROBADA")


def _has(row, key):
    return row is not None and key in row.keys()


def _table_exists(conn, table):
    return bool(
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
            (table,),
        ).fetchone()
    )


def _ensure_publication_schema(conn):
    if not _table_exists(conn, "publications"):
        return False
    APP.add_column_if_missing(
        conn, "publications", "operation_type", "TEXT NOT NULL DEFAULT 'TRANSFERENCIA'"
    )
    APP.add_column_if_missing(conn, "publications", "season_id", "INTEGER")
    return True


def _active_season_id(conn):
    if not _table_exists(conn, "seasons"):
        return None
    row = conn.execute(
        "SELECT id FROM seasons WHERE active=1 ORDER BY id DESC LIMIT 1"
    ).fetchone()
    return int(row["id"]) if row else None


def _pending_operation(conn, player_id, player_name):
    if not _table_exists(conn, "transfers"):
        return None
    marks = ",".join("?" for _ in PENDING_STATUSES)
    return conn.execute(
        f"""
        SELECT id FROM transfers
        WHERE (player_id=? OR (player_id IS NULL AND player=? COLLATE NOCASE))
          AND status IN ({marks})
        ORDER BY id DESC LIMIT 1
        """,
        (int(player_id), str(player_name), *PENDING_STATUSES),
    ).fetchone()


def _latest_release(conn, player_id):
    if not _table_exists(conn, "player_releases"):
        return None
    return conn.execute(
        """
        SELECT * FROM player_releases
        WHERE player_id=?
        ORDER BY id DESC LIMIT 1
        """,
        (int(player_id),),
    ).fetchone()


def _is_free_agent_publication(publication):
    if not publication:
        return False
    op_type = (
        str(publication["operation_type"] or "").strip().upper()
        if _has(publication, "operation_type")
        else ""
    )
    club = str(publication["club"] or "").strip().casefold()
    price = APP.price_number(str(publication["price"] or "")) if APP else None
    return (
        op_type == FREE_AGENT_TYPE
        or (club == FREE_AGENT_CLUB.casefold() and price == 0)
    )


def _listing_detail(last_club):
    return (
        "🆓 Agente libre por liberación • "
        f"Último club: {last_club or '—'} • Fichaje inmediato por $0"
    )


def _ensure_listing_in_connection(conn, player, release_row=None):
    """Ensure exactly one active $0 publication for a released free agent."""
    if not player or str(player["club"] or "").casefold() != FREE_AGENT_CLUB.casefold():
        return None
    if not _ensure_publication_schema(conn):
        return None
    if _pending_operation(conn, int(player["id"]), player["name"]):
        conn.execute(
            "UPDATE publications SET active=0 WHERE player=? COLLATE NOCASE AND active=1",
            (player["name"],),
        )
        return None

    release_row = release_row or _latest_release(conn, int(player["id"]))
    if not release_row:
        # Only players that actually went through AJAP's release flow are
        # auto-published. This avoids treating arbitrary admin placeholders as releases.
        return None

    season_id = _active_season_id(conn)
    if season_id is None and _has(release_row, "season_id"):
        season_id = release_row["season_id"]
    last_club = release_row["from_club"] if _has(release_row, "from_club") else None
    detail = _listing_detail(last_club)

    existing = conn.execute(
        """
        SELECT * FROM publications
        WHERE player=? COLLATE NOCASE
          AND active=1
          AND UPPER(COALESCE(operation_type,''))=?
        ORDER BY id DESC LIMIT 1
        """,
        (player["name"], FREE_AGENT_TYPE),
    ).fetchone()

    if existing:
        conn.execute(
            """
            UPDATE publications
            SET position=?, club=?, price=?, detail=?, owner_id=0,
                operation_type=?, season_id=?
            WHERE id=?
            """,
            (
                player["position"],
                FREE_AGENT_CLUB,
                FREE_AGENT_PRICE,
                detail,
                FREE_AGENT_TYPE,
                season_id,
                int(existing["id"]),
            ),
        )
        conn.execute(
            "UPDATE publications SET active=0 WHERE player=? COLLATE NOCASE AND active=1 AND id<>?",
            (player["name"], int(existing["id"])),
        )
        return int(existing["id"])

    # A release invalidates any previous owner listing. The free-agent listing
    # becomes the only active publication for this player.
    conn.execute(
        "UPDATE publications SET active=0 WHERE player=? COLLATE NOCASE AND active=1",
        (player["name"],),
    )
    cur = conn.execute(
        """
        INSERT INTO publications
        (player, position, club, price, detail, owner_id, active, operation_type, season_id)
        VALUES (?, ?, ?, ?, ?, 0, 1, ?, ?)
        """,
        (
            player["name"],
            player["position"],
            FREE_AGENT_CLUB,
            FREE_AGENT_PRICE,
            detail,
            FREE_AGENT_TYPE,
            season_id,
        ),
    )
    return int(cur.lastrowid)


def sync_released_free_agents():
    """Backfill/repair $0 listings for released players that are still free."""
    if APP is None:
        return 0
    releases._ensure_schema(APP)
    changed = 0
    with APP.db() as conn:
        if not _ensure_publication_schema(conn):
            return 0
        rows = conn.execute(
            """
            SELECT rp.*
            FROM roster_players rp
            WHERE rp.club=? COLLATE NOCASE
              AND EXISTS (
                  SELECT 1 FROM player_releases pr WHERE pr.player_id=rp.id
              )
            ORDER BY rp.id ASC
            """,
            (FREE_AGENT_CLUB,),
        ).fetchall()

        for player in rows:
            before = conn.execute(
                """
                SELECT id, price, club, operation_type
                FROM publications
                WHERE player=? COLLATE NOCASE AND active=1
                ORDER BY id DESC LIMIT 1
                """,
                (player["name"],),
            ).fetchone()
            pub_id = _ensure_listing_in_connection(conn, player)
            after = conn.execute(
                """
                SELECT id, price, club, operation_type
                FROM publications
                WHERE player=? COLLATE NOCASE AND active=1
                ORDER BY id DESC LIMIT 1
                """,
                (player["name"],),
            ).fetchone()
            if pub_id and (
                before is None
                or after is None
                or int(before["id"]) != int(after["id"])
                or str(before["price"]) != FREE_AGENT_PRICE
                or str(before["club"]).casefold() != FREE_AGENT_CLUB.casefold()
                or str(before["operation_type"]).upper() != FREE_AGENT_TYPE
            ):
                changed += 1
    return changed


def _free_agent_embed(publication):
    player = APP.jugador_por_nombre(publication["player"]) if publication else None
    embed = discord.Embed(
        title="🆓 AGENTE LIBRE • FICHAJE $0",
        description=(
            f"**{publication['player']}** está libre y puede ser fichado **sin costo**.\n\n"
            "Al confirmar, el jugador queda reservado para tu club y desaparece de "
            "Transferibles. Staff debe aprobar/cargar el movimiento en PES antes de "
            "que pase al plantel oficial."
        ),
    )
    if player:
        embed.add_field(name="📍 Posición", value=str(player["position"] or "—"), inline=True)
        rating = player["rating"] if _has(player, "rating") else None
        embed.add_field(name="⭐ OVR", value=str(rating if rating is not None else "—"), inline=True)

        with APP.db() as conn:
            release_row = _latest_release(conn, int(player["id"]))
        if release_row:
            embed.add_field(
                name="⬅️ Último club",
                value=str(release_row["from_club"] or "—"),
                inline=True,
            )
            market_value = release_row["market_value"] if _has(release_row, "market_value") else None
            if market_value is not None:
                embed.add_field(
                    name="💰 Valor de mercado",
                    value=f"${int(market_value):,}".replace(",", "."),
                    inline=True,
                )
    embed.add_field(name="🏷️ Precio de fichaje", value="**$0**", inline=True)
    embed.set_footer(text="AJAP Transfer Market • primero en confirmar y validar la operación")
    return embed


def _reserve_free_agent(publication_id, user_id):
    """Atomically reserve a free agent and create the Staff/PES operation."""
    buyer_club = APP.club_de(int(user_id))
    if not buyer_club:
        return False, "⚠️ Primero elegí tu club.", None

    conn = APP.db()
    try:
        conn.execute("BEGIN IMMEDIATE")

        state = conn.execute(
            "SELECT is_open FROM market_state WHERE id=1"
        ).fetchone()
        if not state or not bool(state["is_open"]):
            conn.rollback()
            return False, "🔒 El mercado está cerrado.", None

        publication = conn.execute(
            "SELECT * FROM publications WHERE id=? AND active=1 LIMIT 1",
            (int(publication_id),),
        ).fetchone()
        if not publication or not _is_free_agent_publication(publication):
            conn.rollback()
            return False, "⚠️ Este agente libre ya no está disponible.", None

        player = conn.execute(
            "SELECT * FROM roster_players WHERE name=? COLLATE NOCASE LIMIT 1",
            (publication["player"],),
        ).fetchone()
        if not player or str(player["club"] or "").casefold() != FREE_AGENT_CLUB.casefold():
            if publication:
                conn.execute(
                    "UPDATE publications SET active=0 WHERE id=?",
                    (int(publication["id"]),),
                )
                conn.commit()
            else:
                conn.rollback()
            return False, "⚠️ El jugador ya no figura como agente libre.", None

        pending = _pending_operation(conn, int(player["id"]), player["name"])
        if pending:
            conn.execute(
                "UPDATE publications SET active=0 WHERE id=?",
                (int(publication["id"]),),
            )
            conn.commit()
            return False, "⚠️ Otro club ya reservó a este jugador.", None

        ok, reason = squad_limits.validate_free_agent(conn, buyer_club)
        if not ok:
            conn.rollback()
            return False, reason, None

        # Re-check/deactivate inside the same write transaction. Exactly one
        # concurrent claimant can change active=1 to active=0.
        cur = conn.execute(
            "UPDATE publications SET active=0 WHERE id=? AND active=1",
            (int(publication["id"]),),
        )
        if cur.rowcount != 1:
            conn.rollback()
            return False, "⚠️ Otro club se adelantó y fichó a este jugador.", None

        if _table_exists(conn, "offers"):
            conn.execute(
                """
                UPDATE offers SET status='CANCELADA'
                WHERE player=? COLLATE NOCASE AND status='PENDIENTE'
                """,
                (player["name"],),
            )

        release_row = _latest_release(conn, int(player["id"]))
        last_club = (
            str(release_row["from_club"])
            if release_row and _has(release_row, "from_club") and release_row["from_club"]
            else "—"
        )
        season_id = (
            publication["season_id"]
            if _has(publication, "season_id") and publication["season_id"] is not None
            else _active_season_id(conn)
        )
        notes = (
            f"Fichaje gratuito de agente libre • Precio $0 • Último club: {last_club}"
        )

        cur = conn.execute(
            """
            INSERT INTO transfers
            (player, seller, buyer, amount, offer_id, player_id, operation_type,
             season_id, status, notes)
            VALUES (?, ?, ?, '$0', 0, ?, ?, ?, 'PENDIENTE_ADMIN', ?)
            """,
            (
                player["name"],
                FREE_AGENT_CLUB,
                buyer_club,
                int(player["id"]),
                FREE_AGENT_TYPE,
                season_id,
                notes,
            ),
        )
        transfer_id = int(cur.lastrowid)
        conn.commit()
        return True, None, {
            "transfer_id": transfer_id,
            "player": player["name"],
            "buyer": buyer_club,
            "last_club": last_club,
        }
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


class FreeAgentSignView(discord.ui.View):
    def __init__(self, publication_id, actor_id):
        super().__init__(timeout=300)
        self.publication_id = int(publication_id)
        self.actor_id = int(actor_id)

    @discord.ui.button(
        label="FICHAR POR $0",
        emoji="🆓",
        style=discord.ButtonStyle.success,
        row=0,
    )
    async def sign(self, interaction: discord.Interaction, button: discord.ui.Button):
        if int(interaction.user.id) != self.actor_id:
            await interaction.response.send_message(
                "⛔ Este fichaje fue abierto por otro usuario.", ephemeral=True
            )
            return

        ok, error, result = _reserve_free_agent(
            self.publication_id, interaction.user.id
        )
        if not ok:
            await interaction.response.send_message(error, ephemeral=True)
            return

        embed = discord.Embed(
            title="🆓 FICHAJE DE AGENTE LIBRE RESERVADO",
            description=(
                f"**{result['player']}** quedó reservado para **{result['buyer']}** por **$0**.\n\n"
                "Ya desapareció de Transferibles para evitar un segundo fichaje. "
                "El jugador sigue temporalmente como **Jugador Libre** hasta que Staff "
                "apruebe y cargue el movimiento en PES."
            ),
        )
        embed.add_field(name="⬅️ Estado actual", value=FREE_AGENT_CLUB, inline=True)
        embed.add_field(name="➡️ Destino", value=result["buyer"], inline=True)
        embed.add_field(name="💰 Monto", value="**$0**", inline=True)
        embed.add_field(name="Estado", value="🟡 PENDIENTE_ADMIN", inline=False)
        embed.set_footer(text=f"Operación #{result['transfer_id']} • AJAP Transfer Market")
        await interaction.response.edit_message(embed=embed, view=None)

        try:
            await staff_review.publish_or_refresh_operation(
                interaction, result["transfer_id"]
            )
        except Exception as exc:
            print(
                f"WARNING AJAP: tarjeta Staff de agente libre "
                f"#{result['transfer_id']} no publicada: {exc}"
            )


async def _open_free_agent_or_offer(interaction, publication):
    if not _is_free_agent_publication(publication):
        await _ORIGINAL_OPEN_OFFER_PICKER(interaction, publication)
        return

    if not APP.mercado_abierto():
        await interaction.response.send_message(
            "🔒 El mercado está cerrado. Los fichajes todavía no están habilitados.",
            ephemeral=True,
        )
        return

    buyer_club = APP.club_de(interaction.user.id)
    if not buyer_club:
        await interaction.response.send_message(
            "⚠️ Primero elegí tu club.", ephemeral=True
        )
        return

    # Cheap early validation for UX. The definitive validation runs atomically
    # again when the manager presses FICHAR POR $0.
    with APP.db() as conn:
        ok, reason = squad_limits.validate_free_agent(conn, buyer_club)
    if not ok:
        await interaction.response.send_message(reason, ephemeral=True)
        return

    fresh = APP.publicacion_por_id(int(publication["id"]))
    if not fresh or not _is_free_agent_publication(fresh):
        await interaction.response.send_message(
            "⚠️ Este agente libre ya no está disponible.", ephemeral=True
        )
        return

    await interaction.response.send_message(
        embed=_free_agent_embed(fresh),
        view=FreeAgentSignView(fresh["id"], interaction.user.id),
        ephemeral=True,
    )


def _install_release_listing_hook():
    cls = releases.ConfirmReleaseButton
    if getattr(cls, "_ajap_free_agent_listing_hook", False):
        return

    original = cls.callback

    async def release_and_list(self, interaction):
        await original(self, interaction)

        # Only a successful release leaves this player in Jugador Libre.
        try:
            player = APP.jugador_por_id(int(self.player_id))
            if not player or str(player["club"] or "").casefold() != FREE_AGENT_CLUB.casefold():
                return
            with APP.db() as conn:
                _ensure_listing_in_connection(conn, player)
        except Exception as exc:
            print(
                f"WARNING AJAP: no se pudo publicar agente libre "
                f"player_id={getattr(self, 'player_id', '?')}: {exc}"
            )

    cls.callback = release_and_list
    cls._ajap_free_agent_listing_hook = True


def _install_transferibles_sync():
    if getattr(transferibles, "_ajap_free_agent_sync", False):
        return

    original = transferibles._active_publications

    def active_with_free_agents(limit=500):
        try:
            sync_released_free_agents()
        except Exception as exc:
            print(f"WARNING AJAP: sync de agentes libres falló: {exc}")
        return original(limit)

    transferibles._active_publications = active_with_free_agents
    transferibles._ajap_free_agent_sync = True


_ORIGINAL_OPEN_OFFER_PICKER = negotiation._open_offer_picker


def apply_released_free_agents_patch(runtime, bot=None):
    global APP, BOT, _ORIGINAL_OPEN_OFFER_PICKER
    APP = runtime
    BOT = bot or getattr(runtime, "bot", None)
    if getattr(runtime, "_ajap_released_free_agents_patch", False):
        return

    # negotiation.apply_negotiation_picker_patch already ran by this point, so
    # this is the final offer entry point used by Transferibles and global search.
    _ORIGINAL_OPEN_OFFER_PICKER = negotiation._open_offer_picker
    negotiation._open_offer_picker = _open_free_agent_or_offer

    _install_release_listing_hook()
    _install_transferibles_sync()

    runtime.FreeAgentSignView = FreeAgentSignView
    runtime.sync_released_free_agents = sync_released_free_agents
    runtime._ajap_released_free_agents_patch = True
    print(
        "AJAP agentes libres activos: liberados -> Transferibles $0 • "
        "fichaje directo atómico • límite 32 • Staff/PES"
    )


# release_button_visual_patch imports this module before run_bot. Wrap the
# Transferibles installer so the free-agent layer receives the final runtime
# without adding another startup dependency to run_bot.py.
_ORIGINAL_APPLY_SPLIT_TRANSFERIBLES = transferibles.apply_split_transferibles_patch


def _apply_split_transferibles_then_free_agents(runtime):
    _ORIGINAL_APPLY_SPLIT_TRANSFERIBLES(runtime)
    apply_released_free_agents_patch(runtime, getattr(runtime, "bot", None))


if not getattr(
    transferibles.apply_split_transferibles_patch,
    "_ajap_released_free_agents_wrapped",
    False,
):
    _apply_split_transferibles_then_free_agents._ajap_released_free_agents_wrapped = True
    transferibles.apply_split_transferibles_patch = _apply_split_transferibles_then_free_agents
