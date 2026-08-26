"""Organized Staff administrator menu for AJAP Transfer Market.

Keeps the Staff dashboard information intact, but replaces the crowded admin
button wall with four clear sections:
- Mercado y operaciones
- Planteles
- Economía
- Gestión

All existing callbacks are reused, so current validations/auditing remain in
place. The only new read-only tool is a compact club budget overview.
"""

from __future__ import annotations

import discord

import guild_isolation_patch as guild_isolation
import staff_dashboard_patch as staff


APP = None
BOT = None


def _norm(value):
    return str(value or "").strip().casefold()


def _source_buttons():
    """Build the final AdminView and expose its already-patched callbacks."""
    source = APP.AdminView()
    return [
        item for item in source.children
        if isinstance(item, discord.ui.Button)
        and not _norm(getattr(item, "label", "")).startswith("volver")
    ]


def _find_button(buttons, *needles):
    for item in buttons:
        label = _norm(getattr(item, "label", ""))
        if all(_norm(needle) in label for needle in needles):
            return item
    return None


class ProxyAdminButton(discord.ui.Button):
    def __init__(
        self,
        source_button,
        *,
        label=None,
        emoji=None,
        style=None,
        row=0,
        custom_id=None,
    ):
        super().__init__(
            label=label or source_button.label,
            emoji=emoji if emoji is not None else source_button.emoji,
            style=style or source_button.style,
            disabled=bool(source_button.disabled),
            row=row,
            custom_id=custom_id,
        )
        self._target = source_button.callback

    async def callback(self, interaction: discord.Interaction):
        if not APP.es_admin(interaction):
            await interaction.response.send_message("⛔ Solo administradores.", ephemeral=True)
            return
        await self._target(interaction)


class BackAdminHomeButton(discord.ui.Button):
    def __init__(self, row=3):
        super().__init__(
            label="VOLVER",
            emoji="⬅️",
            style=discord.ButtonStyle.secondary,
            row=row,
            custom_id=f"ajap_staff_admin_section_back_{row}",
        )

    async def callback(self, interaction: discord.Interaction):
        if not APP.es_admin(interaction):
            await interaction.response.send_message("⛔ Solo administradores.", ephemeral=True)
            return
        await interaction.response.edit_message(
            content=None,
            embeds=[organized_admin_embed()],
            view=OrganizedAdminHomeView(),
        )


def organized_admin_embed():
    season = APP.temporada_activa()
    embed = discord.Embed(
        title="⚙️ PERFIL ADMINISTRADOR",
        description="Elegí una sección para administrar el mercado.",
    )
    embed.add_field(
        name="🔁 Mercado",
        value="🟢 ABIERTO" if APP.mercado_abierto() else "🔒 CERRADO",
        inline=True,
    )
    embed.add_field(
        name="🗓️ Temporada",
        value=season["name"] if season else "Sin temporada",
        inline=True,
    )
    embed.add_field(
        name="🧭 Secciones",
        value=(
            "🔁 Mercado y operaciones\n"
            "👥 Planteles\n"
            "💰 Economía\n"
            "⚙️ Gestión"
        ),
        inline=False,
    )
    embed.set_footer(text="AJAP Transfer Market • Panel Staff")
    return embed


def _section_embed(title, description, lines):
    embed = discord.Embed(title=title, description=description)
    embed.add_field(name="Herramientas", value="\n".join(lines), inline=False)
    embed.set_footer(text="⬅️ Volver regresa al Perfil Administrador")
    return embed


class MarketOperationsView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=300)
        buttons = _source_buttons()

        if APP.mercado_abierto():
            toggle = _find_button(buttons, "cerrar mercado")
            if toggle:
                self.add_item(
                    ProxyAdminButton(
                        toggle,
                        label="CERRAR MERCADO",
                        emoji="🔒",
                        style=discord.ButtonStyle.danger,
                        row=0,
                        custom_id="ajap_staff_admin_market_close",
                    )
                )
        else:
            toggle = _find_button(buttons, "abrir mercado")
            if toggle:
                self.add_item(
                    ProxyAdminButton(
                        toggle,
                        label="ABRIR MERCADO",
                        emoji="🟢",
                        style=discord.ButtonStyle.success,
                        row=0,
                        custom_id="ajap_staff_admin_market_open",
                    )
                )

        pending = _find_button(buttons, "operaciones pendientes")
        if pending:
            self.add_item(
                ProxyAdminButton(
                    pending,
                    label="OPERACIONES PENDIENTES",
                    emoji="🛠️",
                    style=discord.ButtonStyle.primary,
                    row=0,
                    custom_id="ajap_staff_admin_pending_ops",
                )
            )

        clauses = _find_button(buttons, "clausulazos")
        if clauses:
            self.add_item(
                ProxyAdminButton(
                    clauses,
                    label="CLAUSULAZOS",
                    emoji="💥",
                    style=discord.ButtonStyle.danger,
                    row=1,
                    custom_id="ajap_staff_admin_clauses",
                )
            )

        self.add_item(staff.UndoPassButton(row=1))
        self.add_item(BackAdminHomeButton(row=2))


class RostersView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=300)
        buttons = _source_buttons()
        specs = [
            (("agregar jugador",), "AGREGAR JUGADOR", "➕", discord.ButtonStyle.primary, 0, "add"),
            (("mover manual",), "MOVER JUGADOR", "🔁", discord.ButtonStyle.primary, 0, "move"),
            (("quitar jugador",), "QUITAR JUGADOR", "🗑️", discord.ButtonStyle.danger, 1, "remove"),
            (("ver plantel",), "VER PLANTEL", "📋", discord.ButtonStyle.secondary, 1, "view"),
        ]
        for needles, label, emoji, style, row, key in specs:
            source = _find_button(buttons, *needles)
            if source:
                self.add_item(
                    ProxyAdminButton(
                        source,
                        label=label,
                        emoji=emoji,
                        style=style,
                        row=row,
                        custom_id=f"ajap_staff_admin_roster_{key}",
                    )
                )
        self.add_item(BackAdminHomeButton(row=2))


class BudgetOverviewButton(discord.ui.Button):
    def __init__(self, row=1):
        super().__init__(
            label="VER PRESUPUESTOS",
            emoji="📊",
            style=discord.ButtonStyle.secondary,
            row=row,
            custom_id="ajap_staff_admin_budget_overview",
        )

    async def callback(self, interaction: discord.Interaction):
        if not APP.es_admin(interaction):
            await interaction.response.send_message("⛔ Solo administradores.", ephemeral=True)
            return

        with APP.db() as conn:
            rows = conn.execute(
                "SELECT club, balance FROM club_finances ORDER BY club COLLATE NOCASE"
            ).fetchall()

        embed = discord.Embed(
            title="📊 PRESUPUESTOS DE CLUBES",
            description="Saldo actual registrado en el mercado.",
        )
        if not rows:
            embed.description = "Todavía no hay presupuestos registrados."
        else:
            lines = [f"🏟️ **{row['club']}** — {staff._fmt_money(row['balance'])}" for row in rows]
            chunks = []
            current = []
            current_len = 0
            for line in lines:
                if current and current_len + len(line) + 1 > 950:
                    chunks.append(current)
                    current = []
                    current_len = 0
                current.append(line)
                current_len += len(line) + 1
            if current:
                chunks.append(current)
            for index, chunk in enumerate(chunks[:4], start=1):
                embed.add_field(
                    name="Clubes" if index == 1 else f"Clubes • {index}",
                    value="\n".join(chunk),
                    inline=False,
                )
        await interaction.response.edit_message(embed=embed, view=EconomyView())


class EconomyView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=300)
        buttons = _source_buttons()

        give = _find_button(buttons, "dar dinero")
        if give:
            self.add_item(
                ProxyAdminButton(
                    give,
                    label="DAR DINERO",
                    emoji="➕",
                    style=discord.ButtonStyle.success,
                    row=0,
                    custom_id="ajap_staff_admin_money_add",
                )
            )

        take = _find_button(buttons, "quitar dinero")
        if take:
            self.add_item(
                ProxyAdminButton(
                    take,
                    label="QUITAR DINERO",
                    emoji="➖",
                    style=discord.ButtonStyle.danger,
                    row=0,
                    custom_id="ajap_staff_admin_money_remove",
                )
            )

        self.add_item(BudgetOverviewButton(row=1))
        self.add_item(BackAdminHomeButton(row=2))


class AssignmentsToolButton(discord.ui.Button):
    def __init__(self, row=0):
        super().__init__(
            label="ASIGNACIONES",
            emoji="👥",
            style=discord.ButtonStyle.secondary,
            row=row,
            custom_id="ajap_staff_admin_assignments",
        )

    async def callback(self, interaction: discord.Interaction):
        if not APP.es_admin(interaction):
            await interaction.response.send_message("⛔ Solo administradores.", ephemeral=True)
            return

        # El menú manager guarda los callbacks originales dentro del botón
        # ADMINISTRACIÓN. También contemplamos versiones antiguas que todavía
        # expongan mercado_asignaciones como botón directo.
        source = APP.MercadoView()
        for item in source.children:
            if getattr(item, "custom_id", None) == "mercado_asignaciones":
                await item.callback(interaction)
                return
            callbacks = getattr(item, "callbacks", None)
            if callbacks and callbacks.get("mercado_asignaciones"):
                await callbacks["mercado_asignaciones"](interaction)
                return

        await interaction.response.send_message(
            "⚠️ No encontré la herramienta de asignaciones en esta versión.",
            ephemeral=True,
        )


class ManagementView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=300)
        buttons = _source_buttons()

        self.add_item(AssignmentsToolButton(row=0))

        season = _find_button(buttons, "cambiar temporada")
        if season:
            self.add_item(
                ProxyAdminButton(
                    season,
                    label="CAMBIAR TEMPORADA",
                    emoji="🗓️",
                    style=discord.ButtonStyle.secondary,
                    row=0,
                    custom_id="ajap_staff_admin_change_season",
                )
            )

        self.add_item(staff.ExportMarketButton(row=1))
        self.add_item(BackAdminHomeButton(row=2))


class AdminSectionButton(discord.ui.Button):
    def __init__(self, *, label, emoji, section, row):
        super().__init__(
            label=label,
            emoji=emoji,
            style=discord.ButtonStyle.secondary,
            row=row,
            custom_id=f"ajap_staff_admin_section_{section}",
        )
        self.section = section

    async def callback(self, interaction: discord.Interaction):
        if not APP.es_admin(interaction):
            await interaction.response.send_message("⛔ Solo administradores.", ephemeral=True)
            return

        if self.section == "market":
            embed = _section_embed(
                "🔁 MERCADO Y OPERACIONES",
                "Control de la ventana de pases y correcciones de movimientos.",
                [
                    "🟢/🔒 Abrir o cerrar mercado",
                    "🛠️ Revisar operaciones pendientes",
                    "💥 Gestionar clausulazos",
                    "↩️ Deshacer un pase aplicado",
                ],
            )
            view = MarketOperationsView()
        elif self.section == "rosters":
            embed = _section_embed(
                "👥 PLANTELES",
                "Herramientas para corregir las plantillas oficiales.",
                [
                    "➕ Agregar jugador",
                    "🔁 Mover jugador entre clubes",
                    "🗑️ Quitar jugador",
                    "📋 Consultar plantel",
                ],
            )
            view = RostersView()
        elif self.section == "economy":
            embed = _section_embed(
                "💰 ECONOMÍA",
                "Administración de presupuestos de los clubes.",
                [
                    "➕ Dar dinero",
                    "➖ Quitar dinero",
                    "📊 Ver presupuestos actuales",
                ],
            )
            view = EconomyView()
        else:
            embed = _section_embed(
                "⚙️ GESTIÓN",
                "Configuración general y herramientas de Staff.",
                [
                    "👥 Asignaciones de clubes",
                    "🗓️ Cambiar temporada",
                    "📤 Exportar mercado",
                ],
            )
            view = ManagementView()

        await interaction.response.edit_message(content=None, embeds=[embed], view=view)


class OrganizedAdminHomeView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=300)
        self.add_item(AdminSectionButton(label="MERCADO", emoji="🔁", section="market", row=0))
        self.add_item(AdminSectionButton(label="PLANTELES", emoji="👥", section="rosters", row=0))
        self.add_item(AdminSectionButton(label="ECONOMÍA", emoji="💰", section="economy", row=1))
        self.add_item(AdminSectionButton(label="GESTIÓN", emoji="⚙️", section="management", row=1))
        self.add_item(staff.BackToStaffButton(row=2))


def apply_staff_admin_organized_patch(runtime, bot):
    global APP, BOT
    APP = runtime
    BOT = bot
    if getattr(runtime, "_ajap_staff_admin_organized_patch", False):
        return

    # StaffHomeView and every back button resolve these globals at click time,
    # so replacing them here reorganiza la UI sin tocar el dashboard.
    staff._admin_profile_embed = organized_admin_embed
    staff._admin_profile_view = lambda: OrganizedAdminHomeView()

    runtime._ajap_staff_admin_organized_patch = True
    print("AJAP Staff admin organizado: Mercado / Planteles / Economía / Gestión")


_original_apply_guild_isolation_patch = guild_isolation.apply_guild_isolation_patch


def _apply_guild_isolation_then_staff_admin(runtime, bot):
    _original_apply_guild_isolation_patch(runtime, bot)
    apply_staff_admin_organized_patch(runtime, bot)


if not getattr(
    guild_isolation.apply_guild_isolation_patch,
    "_ajap_staff_admin_organized_wrapped",
    False,
):
    _apply_guild_isolation_then_staff_admin._ajap_staff_admin_organized_wrapped = True
    guild_isolation.apply_guild_isolation_patch = _apply_guild_isolation_then_staff_admin
