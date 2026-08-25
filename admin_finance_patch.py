"""Admin balance adjustment controls for AJAP Transfer Market.

Adds two buttons to the Administration panel so admins can grant or remove
money from a club without typing slash commands. Every adjustment is audited.
"""

import discord

APP = None


def fmt_money(value: int) -> str:
    return f"${int(value):,}".replace(",", ".")


def ensure_schema(runtime):
    with runtime.db() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS club_finances (
                club TEXT PRIMARY KEY COLLATE NOCASE,
                balance INTEGER NOT NULL DEFAULT 0,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS finance_adjustments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                club TEXT NOT NULL,
                delta INTEGER NOT NULL,
                balance_before INTEGER NOT NULL,
                balance_after INTEGER NOT NULL,
                admin_id INTEGER NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            );
            """
        )


def roster_clubs(runtime):
    with runtime.db() as conn:
        rows = conn.execute(
            "SELECT DISTINCT club FROM roster_players ORDER BY club COLLATE NOCASE"
        ).fetchall()
    return [row["club"] for row in rows if row["club"]]


def adjust_balance(runtime, club: str, amount: int, mode: str, admin_id: int):
    if amount <= 0:
        return False, "El monto debe ser mayor a cero."

    conn = runtime.db()
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(
            "INSERT OR IGNORE INTO club_finances (club, balance) VALUES (?, 0)",
            (club,),
        )
        row = conn.execute(
            "SELECT balance FROM club_finances WHERE club = ? COLLATE NOCASE",
            (club,),
        ).fetchone()
        before = int(row["balance"]) if row else 0

        if mode == "REMOVE":
            if amount > before:
                conn.rollback()
                return False, (
                    f"Saldo insuficiente. **{club}** tiene **{fmt_money(before)}** "
                    f"y querés quitar **{fmt_money(amount)}**."
                )
            delta = -amount
        else:
            delta = amount

        after = before + delta
        conn.execute(
            """
            UPDATE club_finances
            SET balance = ?, updated_at = CURRENT_TIMESTAMP
            WHERE club = ? COLLATE NOCASE
            """,
            (after, club),
        )
        conn.execute(
            """
            INSERT INTO finance_adjustments
            (club, delta, balance_before, balance_after, admin_id)
            VALUES (?, ?, ?, ?, ?)
            """,
            (club, delta, before, after, int(admin_id)),
        )
        conn.commit()
        return True, (before, after, delta)
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


class MoneyAmountModal(discord.ui.Modal):
    def __init__(self, runtime, club: str, mode: str):
        action = "Dar dinero" if mode == "ADD" else "Quitar dinero"
        super().__init__(title=f"{action} • {club[:28]}")
        self.runtime = runtime
        self.club = club
        self.mode = mode
        self.amount = discord.ui.TextInput(
            label="Monto",
            placeholder="Ej: 25000000",
            max_length=20,
        )
        self.add_item(self.amount)

    async def on_submit(self, interaction: discord.Interaction):
        if not self.runtime.es_admin(interaction):
            await interaction.response.send_message("⛔ Solo administradores.", ephemeral=True)
            return

        raw = self.amount.value.strip().replace("$", "").replace(".", "").replace(",", "")
        if not raw.isdigit() or int(raw) <= 0:
            await interaction.response.send_message(
                "⚠️ Escribí un monto válido mayor a cero.",
                ephemeral=True,
            )
            return

        amount = int(raw)
        ok, result = adjust_balance(
            self.runtime,
            self.club,
            amount,
            self.mode,
            interaction.user.id,
        )
        if not ok:
            await interaction.response.send_message(f"⛔ {result}", ephemeral=True)
            return

        before, after, delta = result
        action = "agregó" if delta > 0 else "quitó"
        sign = "+" if delta > 0 else "−"
        embed = discord.Embed(
            title="💰 Saldo actualizado",
            description=f"Se {action} dinero a **{self.club}**.",
        )
        embed.add_field(name="Ajuste", value=f"{sign}{fmt_money(abs(delta))}", inline=True)
        embed.add_field(name="Saldo anterior", value=fmt_money(before), inline=True)
        embed.add_field(name="Saldo nuevo", value=fmt_money(after), inline=True)
        embed.set_footer(text=f"Ajuste realizado por {interaction.user.display_name}")
        await interaction.response.send_message(embed=embed, ephemeral=True)


class ClubMoneySelect(discord.ui.Select):
    def __init__(self, runtime, mode: str):
        self.runtime = runtime
        self.mode = mode
        clubs = roster_clubs(runtime)
        options = []
        for club in clubs[:25]:
            with runtime.db() as conn:
                row = conn.execute(
                    "SELECT balance FROM club_finances WHERE club = ? COLLATE NOCASE",
                    (club,),
                ).fetchone()
            balance = int(row["balance"]) if row else 0
            options.append(
                discord.SelectOption(
                    label=club[:100],
                    description=f"Saldo actual: {fmt_money(balance)}"[:100],
                    value=club,
                )
            )
        super().__init__(
            placeholder="Elegí el equipo",
            min_values=1,
            max_values=1,
            options=options,
        )

    async def callback(self, interaction: discord.Interaction):
        if not self.runtime.es_admin(interaction):
            await interaction.response.send_message("⛔ Solo administradores.", ephemeral=True)
            return
        await interaction.response.send_modal(
            MoneyAmountModal(self.runtime, self.values[0], self.mode)
        )


class ClubMoneyView(discord.ui.View):
    def __init__(self, runtime, mode: str):
        super().__init__(timeout=180)
        clubs = roster_clubs(runtime)
        if clubs:
            self.add_item(ClubMoneySelect(runtime, mode))


def patch_admin_view(runtime):
    base = runtime.AdminView

    class FinanceAdminView(base):
        def __init__(self):
            super().__init__()

            give = discord.ui.Button(
                label="Dar dinero",
                emoji="➕",
                style=discord.ButtonStyle.success,
                row=3,
            )
            give.callback = self._give_money
            self.add_item(give)

            take = discord.ui.Button(
                label="Quitar dinero",
                emoji="➖",
                style=discord.ButtonStyle.danger,
                row=3,
            )
            take.callback = self._take_money
            self.add_item(take)

        async def _give_money(self, interaction: discord.Interaction):
            if not runtime.es_admin(interaction):
                await interaction.response.send_message("⛔ Solo administradores.", ephemeral=True)
                return
            await interaction.response.send_message(
                embed=discord.Embed(
                    title="➕ Dar dinero",
                    description="Elegí el equipo al que querés acreditarle dinero.",
                ),
                view=ClubMoneyView(runtime, "ADD"),
                ephemeral=True,
            )

        async def _take_money(self, interaction: discord.Interaction):
            if not runtime.es_admin(interaction):
                await interaction.response.send_message("⛔ Solo administradores.", ephemeral=True)
                return
            await interaction.response.send_message(
                embed=discord.Embed(
                    title="➖ Quitar dinero",
                    description="Elegí el equipo al que querés descontarle dinero.",
                ),
                view=ClubMoneyView(runtime, "REMOVE"),
                ephemeral=True,
            )

    FinanceAdminView.__name__ = "AdminView"
    runtime.AdminView = FinanceAdminView


def apply_admin_finance_patch(runtime):
    global APP
    if getattr(runtime, "_ajap_admin_finance_patch", False):
        return
    APP = runtime
    ensure_schema(runtime)
    patch_admin_view(runtime)
    runtime._ajap_admin_finance_patch = True
    print("AJAP admin finance activo: dar/quitar dinero con auditoría")
