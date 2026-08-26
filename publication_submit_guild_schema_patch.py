"""Reliable publication submits on guild-isolated SQLite databases.

Discord modal submits have a short acknowledgement window. Older guild DB files
may also need schema migrations before an INSERT can succeed. Doing migrations
and the whole legacy callback chain before responding can make Discord show the
generic "Something went wrong" even when the bot is still working.

This patch acknowledges the modal immediately, migrates the CURRENT guild DB,
then performs the publication write directly and answers through a follow-up.
That also avoids depending on an inherited/stacked on_submit callback chain.
"""

from __future__ import annotations

import traceback

import discord

import guild_isolation_patch as guild_isolation
import publication_announce_patch as announcements
import publication_loan_options_patch as publication_types


def _fmt_money(runtime, value):
    if value is None:
        return "Sin definir"
    try:
        return runtime.money(str(int(value)))
    except (TypeError, ValueError):
        return str(value)


async def _reply(interaction: discord.Interaction, message=None, *, embed=None):
    """Every submit is deferred first, so all user feedback goes through followup."""
    await interaction.followup.send(message, embed=embed, ephemeral=True)


async def _report_submit_error(interaction: discord.Interaction, player_name: str, exc: Exception):
    print(
        f"ERROR AJPA publicando {player_name}: {type(exc).__name__}: {exc}\n"
        + traceback.format_exc()
    )
    try:
        await _reply(
            interaction,
            "⚠️ No pude completar la publicación. El error quedó registrado en Railway para revisión.",
        )
    except Exception as response_exc:
        print(f"ERROR AJPA informando fallo de publicación: {response_exc}")


def apply_publication_submit_guild_schema_patch(runtime, bot):
    if getattr(runtime, "_ajpa_publication_submit_guild_schema_patch", False):
        return

    FixedModal = publication_types.FixedTypePublicationModal
    LoanModal = publication_types.LoanPublicationModal

    def ensure_current_guild_schema():
        # runtime.init_db resolves runtime.db dynamically. After guild isolation,
        # this migrates the SQLite file belonging to the interaction's guild.
        runtime.init_db()
        publication_types.ensure_schema()

    def validate_player(user_id: int, player_name: str):
        club = runtime.club_de(user_id)
        ficha = runtime.jugador_por_nombre(player_name)
        if not club or not ficha or str(ficha["club"]).casefold() != str(club).casefold():
            return None, None, "⛔ Ese jugador ya no pertenece a tu plantel."
        if runtime.publicacion_activa_del_jugador(ficha["name"]):
            return None, None, f"⚠️ **{ficha['name']}** ya tiene una publicación activa."
        if runtime.operacion_abierta_del_jugador(ficha["name"]):
            return (
                None,
                None,
                f"⚠️ **{ficha['name']}** ya tiene una operación aceptada pendiente de administración.",
            )
        return club, ficha, None

    def insert_publication(*, ficha, club, owner_id, operation_type, raw_price, detail,
                           loan_seasons=None, purchase_option_enabled=None,
                           purchase_option_value=None):
        season = runtime.temporada_activa()
        price = runtime.money(str(int(raw_price)))
        with runtime.db() as conn:
            cur = conn.execute(
                """
                INSERT INTO publications
                    (player, position, club, price, detail, owner_id,
                     operation_type, season_id, loan_seasons,
                     purchase_option_enabled, purchase_option_value)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    ficha["name"],
                    ficha["position"],
                    club,
                    price,
                    detail,
                    int(owner_id),
                    operation_type,
                    season["id"] if season else None,
                    loan_seasons,
                    purchase_option_enabled,
                    purchase_option_value,
                ),
            )
            pub_id = int(cur.lastrowid)
        return pub_id, price

    def success_embed(ficha, operation_type, price, detail, pub_id):
        embed = discord.Embed(
            title="✅ Jugador publicado",
            description=f"**{ficha['name']}** ya aparece en Transferibles.",
        )
        if "rating" in ficha.keys() and ficha["rating"] is not None:
            embed.add_field(name="⭐ OVR", value=str(ficha["rating"]), inline=True)
        minimum = ficha["min_sale_value"] if "min_sale_value" in ficha.keys() else None
        if minimum is not None:
            embed.add_field(name="📉 Mín. venta", value=_fmt_money(runtime, minimum), inline=True)
        embed.add_field(name="🔁 Tipo", value=operation_type, inline=True)
        embed.add_field(name="💰 Precio", value=price, inline=True)
        embed.add_field(name="📝 Detalle", value=detail, inline=False)
        embed.set_footer(text=f"Publicación #{pub_id} • AJPA Transfer Market")
        return embed

    async def announce(interaction, pub_id):
        publication = runtime.publicacion_por_id(pub_id)
        if not publication:
            return
        try:
            await announcements._send_public_announcement(interaction, publication)
        except Exception as exc:
            # The publication itself is already valid/persisted. Notification
            # failures must never turn a successful listing into a failed submit.
            print(f"WARNING AJPA anuncio publicación #{pub_id}: {type(exc).__name__}: {exc}")

    async def fixed_submit(self, interaction: discord.Interaction):
        # ACK first: this is the key difference from the old path.
        try:
            await interaction.response.defer(ephemeral=True, thinking=True)
        except Exception:
            # If Discord already considers it acknowledged, continue and use followup.
            pass

        try:
            ensure_current_guild_schema()
            club, ficha, error = validate_player(interaction.user.id, self.jugador)
            if error:
                await _reply(interaction, error)
                return

            operation_type = runtime.normalizar_tipo(self.tipo.value)
            raw_price = runtime.price_number(self.precio.value)
            minimum = ficha["min_sale_value"] if "min_sale_value" in ficha.keys() else None

            if raw_price is None:
                await _reply(interaction, "⚠️ El precio debe ser un número.")
                return
            if operation_type == "TRANSFERENCIA" and minimum and raw_price < int(minimum):
                await _reply(
                    interaction,
                    f"⛔ **{ficha['name']}** tiene un mínimo de venta de **{_fmt_money(runtime, minimum)}**.",
                )
                return

            detail = self.detalle.value.strip() or "Sin observaciones"
            pub_id, price = insert_publication(
                ficha=ficha,
                club=club,
                owner_id=interaction.user.id,
                operation_type=operation_type,
                raw_price=raw_price,
                detail=detail,
            )
            await _reply(
                interaction,
                embed=success_embed(ficha, operation_type, price, detail, pub_id),
            )
            await announce(interaction, pub_id)
        except Exception as exc:
            await _report_submit_error(interaction, getattr(self, "jugador", "jugador"), exc)

    async def loan_submit(self, interaction: discord.Interaction):
        try:
            await interaction.response.defer(ephemeral=True, thinking=True)
        except Exception:
            pass

        try:
            ensure_current_guild_schema()
            club, ficha, error = validate_player(interaction.user.id, self.jugador)
            if error:
                await _reply(interaction, error)
                return

            raw_duration = self.loan_duration.value.strip()
            if not raw_duration.isdigit() or int(raw_duration) <= 0:
                await _reply(
                    interaction,
                    "⚠️ La **cantidad de temporadas es obligatoria** y debe ser un número mayor a 0.",
                )
                return
            seasons = int(raw_duration)

            has_option = publication_types._yes_no(self.purchase_option.value)
            if has_option is None:
                await _reply(
                    interaction,
                    "⚠️ En **Opción de compra** escribí solamente **Sí** o **No**.",
                )
                return

            raw_purchase = self.purchase_value.value.strip()
            purchase_value = None
            if has_option:
                if not raw_purchase:
                    await _reply(
                        interaction,
                        "⚠️ Marcaste **Sí** en opción de compra, así que el **valor es obligatorio**.",
                    )
                    return
                purchase_number = runtime.price_number(raw_purchase)
                if purchase_number is None or purchase_number <= 0:
                    await _reply(
                        interaction,
                        "⚠️ El valor de la opción de compra debe ser un número mayor a 0.",
                    )
                    return
                purchase_value = runtime.money(str(purchase_number))
            elif raw_purchase:
                await _reply(
                    interaction,
                    "⚠️ Si elegiste **No** en opción de compra, dejá vacío el valor de compra.",
                )
                return

            raw_price = runtime.price_number(self.precio.value)
            if raw_price is None or raw_price < 0:
                await _reply(interaction, "⚠️ El cargo del préstamo debe ser un número igual o mayor a 0.")
                return

            option_text = purchase_value if has_option else "Sin opción de compra"
            note = self.note.value.strip()
            detail = (
                f"Préstamo por {seasons} temporada{'s' if seasons != 1 else ''} • "
                f"Opción de compra: {option_text}"
            )
            if note:
                detail += f" • {note}"

            pub_id, price = insert_publication(
                ficha=ficha,
                club=club,
                owner_id=interaction.user.id,
                operation_type="PRÉSTAMO",
                raw_price=raw_price,
                detail=detail,
                loan_seasons=seasons,
                purchase_option_enabled=1 if has_option else 0,
                purchase_option_value=purchase_value,
            )
            await _reply(
                interaction,
                embed=success_embed(ficha, "PRÉSTAMO", price, detail, pub_id),
            )
            await announce(interaction, pub_id)
        except Exception as exc:
            await _report_submit_error(interaction, getattr(self, "jugador", "jugador"), exc)

    FixedModal.on_submit = fixed_submit
    LoanModal.on_submit = loan_submit

    runtime._ajpa_publication_submit_guild_schema_patch = True
    print("AJPA publicación: ACK inmediato + escritura directa per-guild activa")


_original_apply_guild_isolation_patch = guild_isolation.apply_guild_isolation_patch


def _apply_guild_isolation_then_publication_schema(runtime, bot):
    _original_apply_guild_isolation_patch(runtime, bot)
    apply_publication_submit_guild_schema_patch(runtime, bot)


if not getattr(
    guild_isolation.apply_guild_isolation_patch,
    "_ajpa_publication_submit_schema_wrapped_v2",
    False,
):
    _apply_guild_isolation_then_publication_schema._ajpa_publication_submit_schema_wrapped_v2 = True
    guild_isolation.apply_guild_isolation_patch = _apply_guild_isolation_then_publication_schema
