"""Persistent club budget support for AJAP Transfer Market.

For the current Lyon pilot, apply the initial $100,000,000 balance once and a
separate one-time +$100,000,000 test bonus requested afterwards. Both actions
are recorded in SQLite so normal bot/Railway restarts never repeat them.
"""

LYON = "Olympique de Lyon"
LYON_TEST_BUDGET = 100_000_000
SEED_KEY = "lyon_budget_100m_v1"
LYON_BONUS = 100_000_000
BONUS_SEED_KEY = "lyon_budget_bonus_100m_v2"


def fmt_money(value: int) -> str:
    return f"${int(value):,}".replace(",", ".")


def ensure_budget_schema(app):
    with app.db() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS club_finances (
                club TEXT PRIMARY KEY COLLATE NOCASE,
                balance INTEGER NOT NULL DEFAULT 0,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS seed_state (
                key TEXT PRIMARY KEY,
                applied_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );
            """
        )


def seed_lyon_budget_once(app):
    """Set Lyon to exactly $100M once, then preserve all future balance changes."""
    with app.db() as conn:
        seeded = conn.execute(
            "SELECT 1 FROM seed_state WHERE key = ?",
            (SEED_KEY,),
        ).fetchone()
        if seeded:
            return False

        conn.execute(
            """
            INSERT INTO club_finances (club, balance, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(club) DO UPDATE SET
                balance = excluded.balance,
                updated_at = CURRENT_TIMESTAMP
            """,
            (LYON, LYON_TEST_BUDGET),
        )
        conn.execute("INSERT INTO seed_state (key) VALUES (?)", (SEED_KEY,))
        return True


def add_lyon_bonus_once(app):
    """Add +$100M to Lyon once without resetting its current balance."""
    with app.db() as conn:
        applied = conn.execute(
            "SELECT 1 FROM seed_state WHERE key = ?",
            (BONUS_SEED_KEY,),
        ).fetchone()
        if applied:
            return False

        conn.execute(
            "INSERT OR IGNORE INTO club_finances (club, balance) VALUES (?, 0)",
            (LYON,),
        )
        conn.execute(
            """
            UPDATE club_finances
            SET balance = balance + ?, updated_at = CURRENT_TIMESTAMP
            WHERE club = ? COLLATE NOCASE
            """,
            (LYON_BONUS, LYON),
        )
        conn.execute("INSERT INTO seed_state (key) VALUES (?)", (BONUS_SEED_KEY,))
        return True


def club_balance(app, club: str):
    if not club:
        return None
    with app.db() as conn:
        row = conn.execute(
            "SELECT balance FROM club_finances WHERE club = ? COLLATE NOCASE",
            (club.strip(),),
        ).fetchone()
    return int(row["balance"]) if row else None


def apply_budget_patch(app):
    if getattr(app, "_ajap_budget_patch", False):
        return False

    ensure_budget_schema(app)
    initial_seeded = seed_lyon_budget_once(app)
    bonus_seeded = add_lyon_bonus_once(app)

    app.club_balance = lambda club: club_balance(app, club)
    app.fmt_budget = fmt_money

    old_panel_embed = app.panel_embed

    def panel_embed_with_budget(user_id: int):
        embed = old_panel_embed(user_id)
        club = app.club_de(user_id)
        balance = club_balance(app, club)
        if club and balance is not None:
            embed.add_field(
                name="💰 Presupuesto",
                value=fmt_money(balance),
                inline=True,
            )
        return embed

    app.panel_embed = panel_embed_with_budget
    app._ajap_budget_patch = True
    return bool(initial_seeded or bonus_seeded)
