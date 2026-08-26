"""Split AJAP transfer listings into other clubs vs the current manager's own.

The Transferibles screen becomes owner-aware: users browse other clubs without
seeing their own listings mixed in, while a separate section keeps their active
publications available for management/removal.
"""

import math

import discord

import navigation_patch as navigation
import negotiation_picker_patch as negotiation
import publication_management_patch as management


APP = None
PAGE_SIZE = 25
PREVIEW_SIZE = 8


def _active_publications(limit=500):
    with APP.db() as conn:
        return conn.execute(
            "SELECT * FROM publications WHERE active = 1 ORDER BY id DESC LIMIT ?",
            (int(limit),),
        ).fetchall()


def _split(publications, owner_id):
    owner_id = int(owner_id)
    own = [pub for pub in publications if int(pub["owner_id"]) == owner_id]
    others = [pub for pub in publications if int(pub["owner_id"]) != owner_id]
    return others, own


def _page(rows, page):
    pages = max(1, math.ceil(len(rows) / PAGE_SIZE))
    page = max(0, min(int(page), pages - 1))
    start = page * PAGE_SIZE
    return rows[start : start + PAGE_SIZE], page, pages


def _line(pub, own=False):
    ficha = APP.jugador_por_nombre(pub["player"])
    ovr = None
    if ficha and "rating" in ficha.keys() and ficha["rating"] is not None:
        ovr = ficha["rating"]
    parts = [f"**{pub['player']}**"]
    if ovr is not None:
        parts.append(f"⭐ {ovr}")
    if not own:
        parts.append(str(pub["club"]))
    parts.append(str(pub["price"]))
    return " • ".join(parts)


def _preview(rows, own=False):
    if not rows:
        return "_No hay jugadores en esta sección._"
    lines = [_line(pub, own=own) for pub in rows[:PREVIEW_SIZE]]
    if len(rows) > PREVIEW_SIZE:
        lines.append(f"… y **{len(rows) - PREVIEW_SIZE}** más.")
    return "\n".join(lines)


class SectionTransferiblesSelect(discord.ui.Select):
    def __init__(self, publications, *, placeholder, row):
        options = []
        for pub in publications[:PAGE_SIZE]:
            ficha = APP.jugador_por_nombre(pub["player"])
            ovr = None
            if ficha and "rating" in ficha.keys() and ficha["rating"] is not None:
                ovr = ficha["rating"]
            desc_parts = [str(pub["position"]), str(pub["club"]), str(pub["price"])]
            if ovr is not None:
                desc_parts.insert(1, f"OVR {ovr}")
            options.append(
                discord.SelectOption(
                    label=str(pub["player"])[:100],
                    description=" • ".join(desc_parts)[:100],
                    value=str(pub["id"]),
                )
            )
        super().__init__(
            placeholder=placeholder,
            min_values=1,
            max_values=1,
            options=options,
            row=row,
        )

    async def callback(self, interaction: discord.Interaction):
        publication = APP.publicacion_por_id(int(self.values[0]))
        if not publication:
            await interaction.response.send_message(
                "⚠️ Esa publicación ya no está disponible.", ephemeral=True
            )
            return

        if int(publication["owner_id"]) == int(interaction.user.id):
            await interaction.response.send_message(
                embed=management._owner_embed(publication),
                view=management.OwnerPublicationView(
                    publication["id"], publication["owner_id"]
                ),
                ephemeral=True,
            )
            return

        await negotiation._open_offer_picker(interaction, publication)


class SplitTransferiblesView(discord.ui.View):
    def __init__(
        self,
        publicaciones=None,
        owner_id=None,
        other_page=0,
        own_page=0,
    ):
        super().__init__(timeout=300)
        self.owner_id = int(owner_id) if owner_id is not None else None
        self.other_page = int(other_page)
        self.own_page = int(own_page)
        self.publications = list(publicaciones) if publicaciones is not None else list(_active_publications())

        # Search results and legacy callers do not know the current user id.
        # Keep those screens functional with a single owner-aware selector.
        if self.owner_id is None:
            if self.publications:
                self.add_item(
                    SectionTransferiblesSelect(
                        self.publications[:PAGE_SIZE],
                        placeholder="Elegí un jugador transferible",
                        row=0,
                    )
                )
            self.add_item(navigation.MainMenuButton(APP, row=4))
            return

        others, own = _split(self.publications, self.owner_id)
        other_chunk, self.other_page, self.other_pages = _page(others, self.other_page)
        own_chunk, self.own_page, self.own_pages = _page(own, self.own_page)
        self.others = others
        self.own = own

        if other_chunk:
            self.add_item(
                SectionTransferiblesSelect(
                    other_chunk,
                    placeholder=(
                        f"🌍 Otros equipos • página {self.other_page + 1}/{self.other_pages}"
                        if self.other_pages > 1
                        else "🌍 Transferibles de otros equipos"
                    ),
                    row=0,
                )
            )

        if own_chunk:
            self.add_item(
                SectionTransferiblesSelect(
                    own_chunk,
                    placeholder=(
                        f"📤 Mis transferibles • página {self.own_page + 1}/{self.own_pages}"
                        if self.own_pages > 1
                        else "📤 Mis transferibles • gestionar"
                    ),
                    row=1,
                )
            )

        self._add_pagination_buttons()
        self._add_refresh_button()
        self.add_item(navigation.MainMenuButton(APP, row=4))

    def embed(self):
        embed = discord.Embed(
            title="📋 Jugadores transferibles",
            description=(
                "El mercado está separado para que tus publicaciones no se mezclen "
                "con los jugadores que podés negociar."
            ),
        )
        embed.add_field(
            name=f"🌍 Transferibles de otros equipos ({len(self.others)})",
            value=_preview(self.others, own=False),
            inline=False,
        )
        embed.add_field(
            name=f"📤 Mis transferibles ({len(self.own)})",
            value=_preview(self.own, own=True),
            inline=False,
        )
        if self.other_pages > 1:
            embed.add_field(
                name="Navegación del mercado",
                value=f"Página de otros equipos: **{self.other_page + 1}/{self.other_pages}**",
                inline=True,
            )
        if self.own_pages > 1:
            embed.add_field(
                name="Tus publicaciones",
                value=f"Página: **{self.own_page + 1}/{self.own_pages}**",
                inline=True,
            )
        embed.set_footer(
            text="Elegí arriba para ofertar • Elegí abajo para gestionar tus publicaciones"
        )
        return embed

    async def _move(self, interaction, *, other_page=None, own_page=None):
        new_view = SplitTransferiblesView(
            publicaciones=_active_publications(),
            owner_id=self.owner_id,
            other_page=self.other_page if other_page is None else other_page,
            own_page=self.own_page if own_page is None else own_page,
        )
        await interaction.response.edit_message(embed=new_view.embed(), view=new_view)

    def _add_pagination_buttons(self):
        if self.other_pages > 1:
            prev_other = discord.ui.Button(
                label="Otros ◀",
                style=discord.ButtonStyle.secondary,
                row=2,
                disabled=self.other_page <= 0,
            )
            next_other = discord.ui.Button(
                label="Otros ▶",
                style=discord.ButtonStyle.secondary,
                row=2,
                disabled=self.other_page >= self.other_pages - 1,
            )

            async def prev_other_cb(interaction):
                await self._move(interaction, other_page=self.other_page - 1)

            async def next_other_cb(interaction):
                await self._move(interaction, other_page=self.other_page + 1)

            prev_other.callback = prev_other_cb
            next_other.callback = next_other_cb
            self.add_item(prev_other)
            self.add_item(next_other)

        if self.own_pages > 1:
            prev_own = discord.ui.Button(
                label="Míos ◀",
                style=discord.ButtonStyle.secondary,
                row=2,
                disabled=self.own_page <= 0,
            )
            next_own = discord.ui.Button(
                label="Míos ▶",
                style=discord.ButtonStyle.secondary,
                row=2,
                disabled=self.own_page >= self.own_pages - 1,
            )

            async def prev_own_cb(interaction):
                await self._move(interaction, own_page=self.own_page - 1)

            async def next_own_cb(interaction):
                await self._move(interaction, own_page=self.own_page + 1)

            prev_own.callback = prev_own_cb
            next_own.callback = next_own_cb
            self.add_item(prev_own)
            self.add_item(next_own)

    def _add_refresh_button(self):
        refresh = discord.ui.Button(
            label="Actualizar",
            emoji="🔄",
            style=discord.ButtonStyle.secondary,
            row=3,
        )

        async def refresh_cb(interaction):
            await self._move(interaction)

        refresh.callback = refresh_cb
        self.add_item(refresh)


def _patch_market_view(runtime):
    base = runtime.MercadoView

    class SplitTransferiblesMercadoView(base):
        def __init__(self):
            super().__init__()
            for item in self.children:
                if getattr(item, "custom_id", None) == "mercado_transferibles":
                    item.callback = self._open_split_transferibles

        async def _open_split_transferibles(self, interaction: discord.Interaction):
            view = SplitTransferiblesView(
                publicaciones=_active_publications(),
                owner_id=interaction.user.id,
            )
            await interaction.response.send_message(
                embed=view.embed(),
                view=view,
                ephemeral=True,
            )

    SplitTransferiblesMercadoView.__name__ = "MercadoView"
    runtime.MercadoView = SplitTransferiblesMercadoView


def apply_split_transferibles_patch(runtime):
    global APP
    APP = runtime
    if getattr(runtime, "_ajap_split_transferibles_patch", False):
        return

    runtime.TransferiblesView = SplitTransferiblesView
    runtime.SplitTransferiblesView = SplitTransferiblesView
    _patch_market_view(runtime)

    runtime._ajap_split_transferibles_patch = True
    print("AJAP transferibles separados: otros equipos + mis transferibles")
