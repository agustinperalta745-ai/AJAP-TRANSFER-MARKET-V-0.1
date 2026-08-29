"""Keep every Staff economy view limited to the current active AJAP clubs.

Legacy aliases are intentionally kept in SQLite for history/referential safety,
but they must never appear as separate clubs in budget selectors, treasury or
the budget overview. The live catalog is league_teams WHERE active = 1.
"""

from __future__ import annotations

import discord

import admin_finance_patch as admin_finance
import staff_admin_organized_patch as staff_admin
import staff_treasury_patch as staff_treasury


def _table_exists(conn, table: str) -> bool:
    return bool(
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1",
            (table,),
        ).fetchone()
    )


def _active_clubs(app):
    if not app:
        return []
    with app.db() as conn:
        if not _table_exists(conn, "league_teams"):
            return []
        rows = conn.execute(
            """
            SELECT name
            FROM league_teams
            WHERE active = 1
              AND name IS NOT NULL
              AND TRIM(name) <> ''
            ORDER BY name COLLATE NOCASE
            """
        ).fetchall()
    return [str(row["name"]).strip() for row in rows if row["name"]]


def _active_budget_rows(app):
    if not app:
        return []
    with app.db() as conn:
        if not _table_exists(conn, "league_teams"):
            return []
        rows = conn.execute(
            """
            SELECT lt.name AS club, COALESCE(cf.balance, 0) AS balance
            FROM league_teams AS lt
            LEFT JOIN club_finances AS cf
              ON cf.club = lt.name COLLATE NOCASE
            WHERE lt.active = 1
              AND lt.name IS NOT NULL
              AND TRIM(lt.name) <> ''
            ORDER BY lt.name COLLATE NOCASE
            """
        ).fetchall()
    return rows


def _admin_roster_clubs(runtime):
    """Dar/Quitar dinero: never offer historical roster aliases."""
    return _active_clubs(runtime)


_original_adjust_balance = admin_finance.adjust_balance


def _adjust_active_balance(runtime, club: str, amount: int, mode: str, admin_id: int):
    """Reject stale buttons/selects that point at an inactive legacy alias."""
    active = {name.casefold() for name in _active_clubs(runtime)}
    if str(club or "").strip().casefold() not in active:
        return False, "Ese club ya no pertenece al catálogo oficial activo. No se modificó ningún saldo."
    return _original_adjust_balance(runtime, club, amount, mode, admin_id)


def _staff_treasury_clubs():
    """Tesorería Staff: same club source as the live team catalog."""
    return _active_clubs(staff_treasury._app())


async def _budget_overview_callback(self, interaction: discord.Interaction):
    app = staff_admin.APP
    if not app or not app.es_admin(interaction):
        await interaction.response.send_message("⛔ Solo administradores.", ephemeral=True)
        return

    rows = _active_budget_rows(app)
    embed = discord.Embed(
        title="📊 PRESUPUESTOS",
        description="Saldo actual de los clubes oficiales activos.",
    )
    if not rows:
        embed.description = "Todavía no hay clubes oficiales activos con presupuesto."
    else:
        lines = [
            f"🏟️ **{row['club']}** — {staff_admin._fmt_money(row['balance'])}"
            for row in rows
        ]
        chunks = []
        current = []
        size = 0
        for line in lines:
            if current and size + len(line) + 1 > 950:
                chunks.append(current)
                current = []
                size = 0
            current.append(line)
            size += len(line) + 1
        if current:
            chunks.append(current)

        for idx, chunk in enumerate(chunks[:4], 1):
            embed.add_field(
                name="Clubes" if idx == 1 else f"Clubes • {idx}",
                value="\n".join(chunk),
                inline=False,
            )
        embed.set_footer(text=f"{len(rows)} club(es) oficial(es) activo(s)")

    await interaction.response.edit_message(embed=embed, view=staff_admin.EconomyView())


def apply_active_finance_clubs_patch():
    if getattr(admin_finance, "_ajap_active_finance_clubs_patch", False):
        return

    admin_finance.roster_clubs = _admin_roster_clubs
    admin_finance.adjust_balance = _adjust_active_balance
    staff_treasury._clubs = _staff_treasury_clubs
    staff_admin.BudgetOverviewButton.callback = _budget_overview_callback

    admin_finance._ajap_active_finance_clubs_patch = True
    print("AJAP economía filtrada a clubes oficiales activos; alias históricos ocultos")


apply_active_finance_clubs_patch()
