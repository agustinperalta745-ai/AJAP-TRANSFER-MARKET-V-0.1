"""Paid player releases for AJAP Transfer Market.

Rule agreed for AJAP:
- a DT may release one of the club's own players only while the market is open;
- release cost is exactly 20% of the player's current AJAP market value;
- the club must have enough cash to pay the charge;
- active loans and already-accepted operations block the release;
- once confirmed, the player becomes ``Jugador Libre`` and any ordinary active
  publication/pending offer for him is cancelled;
- the charge is written to club_finances + treasury_transactions and the move is
  written to player_history/player_releases for audit.

The UI lives inside MI CLUB and always shows the exact value/cost before the DT
can confirm. Rosters with more than 25 players are paginated.
"""

from __future__ import annotations

import math

import discord

import guild_isolation_patch as guild_isolation
import my_club_menu_patch as my_club
import roster_catalog_autosync_patch as catalog


RELEASE_PERCENT = 20
FREE_AGENT_CLUB = "Jugador Libre"
ACTIVE_LOAN_STATUSES = ("ACTIVE", "OPTION_PENDING", "RETURN_PENDING", "REVIEW_REQUIRED")
PENDING_TRANSFER_STATUSES = ("PENDIENTE_ADMIN", "APROBADA")


_ORIGINAL_SYNC_CATALOG = catalog._sync_loaded_teams_into_catalog


def _app():
    return my_club.APP


def _fmt_money(value: int) -> str:
    return f"${int(value):,}".replace(",", ".")


def _table_exists(conn, table: str) -> bool:
    return bool(
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
            (table,),
        ).fetchone()
    )


def _ensure_schema(app):
    with app.db() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS player_releases (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                player_id INTEGER NOT NULL,
                player TEXT NOT NULL,
                from_club TEXT NOT NULL COLLATE NOCASE,
                market_value INTEGER NOT NULL,
                release_percent INTEGER NOT NULL,
                release_cost INTEGER NOT NULL,
                balance_before INTEGER NOT NULL,
                balance_after INTEGER NOT NULL,
                released_by INTEGER NOT NULL,
                season_id INTEGER,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS club_finances (
                club TEXT PRIMARY KEY COLLATE NOCASE,
                balance INTEGER NOT NULL DEFAULT 0,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS treasury_transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                club TEXT NOT NULL COLLATE NOCASE,
                season_id INTEGER,
                direction TEXT NOT NULL,
                category TEXT NOT NULL,
                amount INTEGER NOT NULL,
                player_id INTEGER,
                player TEXT,
                counterparty TEXT,
                reference_type TEXT,
                reference_id INTEGER,
                description TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(club, direction, category, reference_type, reference_id, season_id)
            );
            """
        )


def _market_value(player) -> int:
    app = _app()
    if not player or not app:
        return 0

    resolver = getattr(app, "player_market_value", None)
    if resolver:
        try:
            value = int(resolver(player) or 0)
            if value > 0:
                return value
        except (TypeError, ValueError):
            pass

    if "min_sale_value" in player.keys() and player["min_sale_value"] is not None:
        try:
            value = int(player["min_sale_value"] or 0)
            if value > 0:
                return value
        except (TypeError, ValueError):
            pass

    try:
        import economy_values_patch as economy
        rating = player["rating"] if "rating" in player.keys() else None
        return int(economy.market_value_for_rating(rating) or 0)
    except Exception:
        return 0


def release_cost(player) -> int:
    value = _market_value(player)
    return int(round(value * RELEASE_PERCENT / 100)) if value > 0 else 0


def _balance(club: str) -> int:
    app = _app()
    if not app or not club:
        return 0
    _ensure_schema(app)
    with app.db() as conn:
        row = conn.execute(
            "SELECT balance FROM club_finances WHERE club=? COLLATE NOCASE",
            (club,),
        ).fetchone()
    return int(row["balance"] if row else 0)


def _season_id(conn):
    if not _table_exists(conn, "seasons"):
        return None
    row = conn.execute(
        "SELECT id FROM seasons WHERE active=1 ORDER BY id DESC LIMIT 1"
    ).fetchone()
    return int(row["id"]) if row else None


def _player_blocker(conn, player_id: int):
    if _table_exists(conn, "loans"):
        marks = ",".join("?" for _ in ACTIVE_LOAN_STATUSES)
        row = conn.execute(
            f"SELECT 1 FROM loans WHERE player_id=? AND status IN ({marks}) LIMIT 1",
            (int(player_id), *ACTIVE_LOAN_STATUSES),
        ).fetchone()
        if row:
            return "El jugador tiene un préstamo/retorno activo y no puede ser liberado."

    if _table_exists(conn, "transfers"):
        marks = ",".join("?" for _ in PENDING_TRANSFER_STATUSES)
        row = conn.execute(
            f"SELECT 1 FROM transfers WHERE player_id=? AND status IN ({marks}) LIMIT 1",
            (int(player_id), *PENDING_TRANSFER_STATUSES),
        ).fetchone()
        if row:
            return "El jugador ya tiene una operación aceptada pendiente de Staff/PES."
    return None


def _preview(player, club: str):
    app = _app()
    value = _market_value(player)
    cost = release_cost(player)
    balance = _balance(club)
    blocker = None
    if app:
        with app.db() as conn:
            blocker = _player_blocker(conn, int(player["id"]))

    if value <= 0:
        blocker = blocker or "No se pudo determinar el valor de mercado del jugador."
    if balance < cost:
        blocker = blocker or (
            f"Saldo insuficiente: el club tiene {_fmt_money(balance)} y necesita {_fmt_money(cost)}."
        )
    return value, cost, balance, blocker


def release_intro_embed(club: str):
    embed = discord.Embed(
        title=f"🚪 LIBERAR JUGADOR • {club.upper()}",
        description=(
            "Elegí al jugador que querés dejar libre. Antes de confirmar vas a ver el costo exacto.\n\n"
            f"💸 **Costo fijo: {RELEASE_PERCENT}% del valor de mercado**\n"
            "🔒 Solo se puede liberar con el mercado abierto."
        ),
    )
    embed.set_footer(text="La liberación queda registrada en Historial y Tesorería")
    return embed


def release_confirm_embed(player, club: str):
    value, cost, balance, blocker = _preview(player, club)
    after = balance - cost
    embed = discord.Embed(
        title="⚠️ CONFIRMAR LIBERACIÓN",
        description=(
            f"Vas a liberar a **{player['name']}** de **{club}**.\n"
            f"El jugador pasará a **🆓 {FREE_AGENT_CLUB}**."
        ),
    )
    embed.add_field(name="⭐ OVR", value=str(player["rating"] if "rating" in player.keys() and player["rating"] is not None else "—"), inline=True)
    embed.add_field(name="💰 Valor de mercado", value=_fmt_money(value), inline=True)
    embed.add_field(name=f"📉 Penalización ({RELEASE_PERCENT}%)", value=_fmt_money(cost), inline=True)
    embed.add_field(name="💼 Saldo actual", value=_fmt_money(balance), inline=True)
    embed.add_field(name="💼 Saldo después", value=_fmt_money(max(after, 0)), inline=True)
    if blocker:
        embed.add_field(name="⛔ No se puede confirmar", value=blocker, inline=False)
    else:
        embed.add_field(
            name="🚨 Acción definitiva",
            value="Al confirmar se descuenta el dinero y el jugador sale inmediatamente de tu plantilla.",
            inline=False,
        )
    return embed, blocker


def _club_players(club: str):
    app = _app()
    if not app or not club:
        return []
    players = list(app.jugadores_de_club(club, 100))
    players.sort(
        key=lambda p: (
            -(int(p["rating"]) if "rating" in p.keys() and p["rating"] is not None else -1),
            str(p["name"]).casefold(),
        )
    )
    return players


class ReleasePlayerSelect(discord.ui.Select):
    def __init__(self, club: str, roster_callback, page=0):
        self.club = club
        self.roster_callback = roster_callback
        self.page = max(0, int(page))
        players = _club_players(club)
        start = self.page * 25
        visible = players[start:start + 25]
        options = []
        for player in visible:
            value = _market_value(player)
            ovr = player["rating"] if "rating" in player.keys() and player["rating"] is not None else "—"
            options.append(
                discord.SelectOption(
                    label=str(player["name"])[:100],
                    value=str(player["id"]),
                    description=f"OVR {ovr} • Valor {_fmt_money(value)} • Liberar {_fmt_money(release_cost(player))}"[:100],
                )
            )
        super().__init__(
            placeholder="Elegí un jugador para calcular la liberación",
            min_values=1,
            max_values=1,
            options=options,
            row=0,
        )

    async def callback(self, interaction: discord.Interaction):
        app = _app()
        if not app.mercado_abierto():
            await interaction.response.send_message(
                "🔒 Solo podés liberar jugadores mientras el mercado está abierto.",
                ephemeral=True,
            )
            return
        player = app.jugador_por_id(int(self.values[0]))
        current_club = app.club_de(interaction.user.id)
        if not player or not current_club or str(player["club"]).casefold() != str(current_club).casefold():
            await interaction.response.send_message(
                "⚠️ Ese jugador ya no pertenece a tu club.", ephemeral=True
            )
            return
        embed, blocker = release_confirm_embed(player, current_club)
        await interaction.response.edit_message(
            content=None,
            embed=embed,
            view=ReleaseConfirmView(player["id"], current_club, self.roster_callback, blocked=bool(blocker)),
        )


class ReleasePageButton(discord.ui.Button):
    def __init__(self, club, roster_callback, target_page, *, label, emoji, disabled=False):
        self.club = club
        self.roster_callback = roster_callback
        self.target_page = target_page
        super().__init__(
            label=label,
            emoji=emoji,
            style=discord.ButtonStyle.secondary,
            row=1,
            disabled=disabled,
        )

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.edit_message(
            embed=release_intro_embed(self.club),
            view=ReleaseListView(self.club, self.roster_callback, self.target_page),
        )


class ReleaseBackToClubButton(discord.ui.Button):
    def __init__(self, roster_callback, row=2):
        self.roster_callback = roster_callback
        super().__init__(
            label="Volver a MI CLUB",
            emoji="⬅️",
            style=discord.ButtonStyle.secondary,
            row=row,
        )

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.edit_message(
            content=None,
            embed=my_club.my_club_embed(interaction.user.id),
            view=my_club.MyClubSectionView(self.roster_callback),
        )


class ReleaseListView(discord.ui.View):
    def __init__(self, club: str, roster_callback, page=0):
        super().__init__(timeout=300)
        players = _club_players(club)
        pages = max(1, math.ceil(len(players) / 25))
        page = max(0, min(int(page), pages - 1))
        if players:
            self.add_item(ReleasePlayerSelect(club, roster_callback, page))
        if pages > 1:
            self.add_item(ReleasePageButton(club, roster_callback, page - 1, label="Anterior", emoji="⬅️", disabled=page <= 0))
            self.add_item(ReleasePageButton(club, roster_callback, page + 1, label="Siguiente", emoji="➡️", disabled=page >= pages - 1))
        self.add_item(ReleaseBackToClubButton(roster_callback, row=2))


class ConfirmReleaseButton(discord.ui.Button):
    def __init__(self, player_id: int, club: str, roster_callback, blocked=False):
        self.player_id = int(player_id)
        self.club = club
        self.roster_callback = roster_callback
        super().__init__(
            label="CONFIRMAR LIBERACIÓN",
            emoji="🚪",
            style=discord.ButtonStyle.danger,
            row=0,
            disabled=blocked,
        )

    async def callback(self, interaction: discord.Interaction):
        app = _app()
        if not app or not app.mercado_abierto():
            await interaction.response.send_message(
                "🔒 El mercado está cerrado. La liberación fue cancelada.", ephemeral=True
            )
            return

        assigned_club = app.club_de(interaction.user.id)
        if not assigned_club or assigned_club.casefold() != self.club.casefold():
            await interaction.response.send_message(
                "⚠️ Tu asignación de club cambió. Volvé a abrir MI CLUB.", ephemeral=True
            )
            return

        _ensure_schema(app)
        conn = app.db()
        try:
            conn.execute("BEGIN IMMEDIATE")
            state = conn.execute("SELECT is_open FROM market_state WHERE id=1").fetchone()
            if not state or not bool(state["is_open"]):
                conn.rollback()
                await interaction.response.send_message(
                    "🔒 El mercado acaba de cerrarse. No se realizó ningún cambio.", ephemeral=True
                )
                return

            player = conn.execute(
                "SELECT * FROM roster_players WHERE id=? LIMIT 1",
                (self.player_id,),
            ).fetchone()
            if not player or str(player["club"]).casefold() != self.club.casefold():
                conn.rollback()
                await interaction.response.send_message(
                    "⚠️ Ese jugador ya no pertenece a tu club.", ephemeral=True
                )
                return

            blocker = _player_blocker(conn, self.player_id)
            if blocker:
                conn.rollback()
                await interaction.response.send_message(f"⛔ {blocker}", ephemeral=True)
                return

            value = _market_value(player)
            cost = int(round(value * RELEASE_PERCENT / 100)) if value > 0 else 0
            if value <= 0 or cost <= 0:
                conn.rollback()
                await interaction.response.send_message(
                    "⛔ No se pudo calcular un valor válido para la liberación.", ephemeral=True
                )
                return

            conn.execute(
                "INSERT OR IGNORE INTO club_finances (club, balance) VALUES (?, 0)",
                (self.club,),
            )
            finance = conn.execute(
                "SELECT balance FROM club_finances WHERE club=? COLLATE NOCASE",
                (self.club,),
            ).fetchone()
            before = int(finance["balance"] if finance else 0)
            if before < cost:
                conn.rollback()
                await interaction.response.send_message(
                    f"⛔ Saldo insuficiente. Necesitás {_fmt_money(cost)} y tenés {_fmt_money(before)}.",
                    ephemeral=True,
                )
                return
            after = before - cost
            season_id = _season_id(conn)

            conn.execute(
                "UPDATE club_finances SET balance=?, updated_at=CURRENT_TIMESTAMP WHERE club=? COLLATE NOCASE",
                (after, self.club),
            )
            conn.execute(
                "UPDATE roster_players SET club=?, updated_at=CURRENT_TIMESTAMP WHERE id=?",
                (FREE_AGENT_CLUB, self.player_id),
            )
            if _table_exists(conn, "publications"):
                conn.execute(
                    "UPDATE publications SET active=0 WHERE player=? COLLATE NOCASE AND active=1",
                    (player["name"],),
                )
            if _table_exists(conn, "offers"):
                conn.execute(
                    "UPDATE offers SET status='CANCELADA' WHERE player=? COLLATE NOCASE AND status='PENDIENTE'",
                    (player["name"],),
                )

            cur = conn.execute(
                """
                INSERT INTO player_releases
                (player_id, player, from_club, market_value, release_percent, release_cost,
                 balance_before, balance_after, released_by, season_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    self.player_id, player["name"], self.club, value, RELEASE_PERCENT,
                    cost, before, after, int(interaction.user.id), season_id,
                ),
            )
            release_id = int(cur.lastrowid)

            conn.execute(
                """
                INSERT OR IGNORE INTO treasury_transactions
                (club, season_id, direction, category, amount, player_id, player,
                 counterparty, reference_type, reference_id, description)
                VALUES (?, ?, 'EGRESO', 'LIBERACIÓN', ?, ?, ?, ?, 'PLAYER_RELEASE', ?, ?)
                """,
                (
                    self.club, season_id, cost, self.player_id, player["name"],
                    FREE_AGENT_CLUB, release_id,
                    f"Liberación de {player['name']} • {RELEASE_PERCENT}% del valor de mercado",
                ),
            )

            if _table_exists(conn, "player_history"):
                conn.execute(
                    """
                    INSERT INTO player_history
                    (player_id, player, from_club, to_club, transfer_id, season_id, event_type)
                    VALUES (?, ?, ?, ?, NULL, ?, 'LIBERACIÓN')
                    """,
                    (self.player_id, player["name"], self.club, FREE_AGENT_CLUB, season_id),
                )

            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

        success = discord.Embed(
            title="✅ JUGADOR LIBERADO",
            description=f"**{player['name']}** dejó **{self.club}** y ahora es **🆓 {FREE_AGENT_CLUB}**.",
        )
        success.add_field(name="💰 Valor", value=_fmt_money(value), inline=True)
        success.add_field(name=f"📉 Costo ({RELEASE_PERCENT}%)", value=_fmt_money(cost), inline=True)
        success.add_field(name="💼 Nuevo saldo", value=_fmt_money(after), inline=True)
        success.set_footer(text="Movimiento registrado en Tesorería e Historial")
        await interaction.response.edit_message(
            content=None,
            embed=success,
            view=ReleaseBackOnlyView(self.roster_callback),
        )

        try:
            await interaction.channel.send(
                f"🆓 **JUGADOR LIBERADO**\n\n"
                f"**{self.club}** liberó a **{player['name']}**.\n"
                f"💰 Valor de mercado: **{_fmt_money(value)}**\n"
                f"📉 Penalización ({RELEASE_PERCENT}%): **{_fmt_money(cost)}**\n"
                f"➡️ Nuevo estado: **{FREE_AGENT_CLUB}**"
            )
        except Exception:
            pass


class CancelReleaseButton(discord.ui.Button):
    def __init__(self, club, roster_callback):
        self.club = club
        self.roster_callback = roster_callback
        super().__init__(
            label="Cancelar",
            emoji="↩️",
            style=discord.ButtonStyle.secondary,
            row=0,
        )

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.edit_message(
            embed=release_intro_embed(self.club),
            view=ReleaseListView(self.club, self.roster_callback),
        )


class ReleaseConfirmView(discord.ui.View):
    def __init__(self, player_id, club, roster_callback, blocked=False):
        super().__init__(timeout=300)
        self.add_item(ConfirmReleaseButton(player_id, club, roster_callback, blocked=blocked))
        self.add_item(CancelReleaseButton(club, roster_callback))


class ReleaseBackOnlyView(discord.ui.View):
    def __init__(self, roster_callback):
        super().__init__(timeout=300)
        self.add_item(ReleaseBackToClubButton(roster_callback, row=0))


class ReleaseHubButton(discord.ui.Button):
    def __init__(self, roster_callback, row=2):
        self.roster_callback = roster_callback
        super().__init__(
            label="LIBERAR JUGADOR",
            emoji="🚪",
            style=discord.ButtonStyle.danger,
            row=row,
            custom_id="ajap_my_club_release_player",
        )

    async def callback(self, interaction: discord.Interaction):
        app = _app()
        if not app.mercado_abierto():
            await interaction.response.send_message(
                "🔒 Solo podés liberar jugadores cuando el mercado está abierto.",
                ephemeral=True,
            )
            return
        club = app.club_de(interaction.user.id)
        if not club:
            await interaction.response.send_message(
                "⚠️ No tenés un club asignado.", ephemeral=True
            )
            return
        players = _club_players(club)
        if not players:
            await interaction.response.send_message(
                "⚠️ Tu club no tiene jugadores para liberar.", ephemeral=True
            )
            return
        await interaction.response.edit_message(
            content=None,
            embed=release_intro_embed(club),
            view=ReleaseListView(club, self.roster_callback),
        )


def _install_my_club_button():
    BaseView = my_club.MyClubSectionView
    if getattr(BaseView, "_ajap_player_release", False):
        return

    class ReleaseMyClubSectionView(BaseView):
        def __init__(self, roster_callback):
            super().__init__(roster_callback)
            self.add_item(ReleaseHubButton(roster_callback, row=2))

    ReleaseMyClubSectionView.__name__ = "MyClubSectionView"
    ReleaseMyClubSectionView._ajap_player_release = True
    my_club.MyClubSectionView = ReleaseMyClubSectionView


def _sync_catalog_without_free_agents():
    _ORIGINAL_SYNC_CATALOG()
    app = getattr(catalog.builder, "APP", None)
    if app is None:
        return
    try:
        with app.db() as conn:
            if _table_exists(conn, "league_teams"):
                conn.execute(
                    "DELETE FROM league_teams WHERE name IN (?, ?) COLLATE NOCASE",
                    (FREE_AGENT_CLUB, "Libre"),
                )
            # Never create a fake $10M club for the free-agent pool.
            if _table_exists(conn, "club_finances"):
                conn.execute(
                    "DELETE FROM club_finances WHERE club IN (?, ?) COLLATE NOCASE",
                    (FREE_AGENT_CLUB, "Libre"),
                )
    except Exception:
        pass


def apply_player_release_patch(runtime, bot):
    if getattr(runtime, "_ajap_player_release_patch", False):
        return
    _ensure_schema(runtime)
    runtime.release_cost = release_cost
    runtime._ajap_player_release_patch = True
    print(f"AJAP liberaciones activas: mercado abierto + costo fijo {RELEASE_PERCENT}%")


# Install the final MI CLUB button immediately. The runtime APP is bound later
# by my_club_menu_patch when guild isolation is applied.
_install_my_club_button()

# Keep the free-agent pool out of the selectable-team autosync catalog.
catalog._sync_loaded_teams_into_catalog = _sync_catalog_without_free_agents

# Bind schema/runtime after the normal per-guild setup finishes.
_original_apply_guild_isolation_patch = guild_isolation.apply_guild_isolation_patch


def _apply_guild_isolation_then_releases(runtime, bot):
    _original_apply_guild_isolation_patch(runtime, bot)
    apply_player_release_patch(runtime, bot)


if not getattr(guild_isolation.apply_guild_isolation_patch, "_ajap_release_wrapped", False):
    _apply_guild_isolation_then_releases._ajap_release_wrapped = True
    guild_isolation.apply_guild_isolation_patch = _apply_guild_isolation_then_releases
