"""Resumen público y automático de movimientos del AJAP Transfer Market.

El canal se configura por servidor ejecutando /canal_resumen_mercado dentro del
canal de solo lectura para los DTs. A partir de ahí se publican únicamente
operaciones oficiales: transferencias, préstamos, intercambios y compras de
opción. Los clausulazos conservan su formato especial y se redirigen al mismo
canal cuando está configurado.

Este parche se monta después del aislamiento por guild para que la configuración
y el control de duplicados queden guardados en la SQLite correcta de cada liga.
"""

from __future__ import annotations

import discord

import guild_isolation_patch


APP = None


def _conn_for_guild(guild_id: int):
    if APP is None:
        raise RuntimeError("AJAP runtime todavía no inicializado")
    if hasattr(APP, "db_for_guild"):
        return APP.db_for_guild(int(guild_id))
    if hasattr(APP, "guild_context"):
        with APP.guild_context(int(guild_id)):
            return APP.db()
    return APP.db()


def _ensure_schema(conn):
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS public_market_channels (
            guild_id INTEGER PRIMARY KEY,
            channel_id INTEGER NOT NULL,
            configured_by INTEGER,
            configured_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS public_market_announcements (
            kind TEXT NOT NULL,
            reference_id INTEGER NOT NULL,
            channel_id INTEGER NOT NULL,
            message_id INTEGER NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (kind, reference_id)
        );
        """
    )
    conn.commit()


def get_public_channel_id(guild_id: int):
    conn = _conn_for_guild(int(guild_id))
    try:
        _ensure_schema(conn)
        row = conn.execute(
            "SELECT channel_id FROM public_market_channels WHERE guild_id = ? LIMIT 1",
            (int(guild_id),),
        ).fetchone()
        return int(row["channel_id"]) if row else None
    finally:
        conn.close()


def set_public_channel(guild_id: int, channel_id: int, user_id: int):
    conn = _conn_for_guild(int(guild_id))
    try:
        _ensure_schema(conn)
        conn.execute(
            """
            INSERT INTO public_market_channels
                (guild_id, channel_id, configured_by, configured_at, updated_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            ON CONFLICT(guild_id) DO UPDATE SET
                channel_id=excluded.channel_id,
                configured_by=excluded.configured_by,
                updated_at=CURRENT_TIMESTAMP
            """,
            (int(guild_id), int(channel_id), int(user_id)),
        )
        conn.commit()
    finally:
        conn.close()


def _was_announced(guild_id: int, kind: str, reference_id: int) -> bool:
    conn = _conn_for_guild(int(guild_id))
    try:
        _ensure_schema(conn)
        row = conn.execute(
            """
            SELECT 1 FROM public_market_announcements
            WHERE kind = ? AND reference_id = ?
            LIMIT 1
            """,
            (str(kind), int(reference_id)),
        ).fetchone()
        return row is not None
    finally:
        conn.close()


def _remember_announcement(
    guild_id: int,
    kind: str,
    reference_id: int,
    channel_id: int,
    message_id: int,
):
    conn = _conn_for_guild(int(guild_id))
    try:
        _ensure_schema(conn)
        conn.execute(
            """
            INSERT OR IGNORE INTO public_market_announcements
                (kind, reference_id, channel_id, message_id)
            VALUES (?, ?, ?, ?)
            """,
            (str(kind), int(reference_id), int(channel_id), int(message_id)),
        )
        conn.commit()
    finally:
        conn.close()


def _has(row, key: str) -> bool:
    return row is not None and key in row.keys()


async def _resolve_public_channel(guild):
    if guild is None:
        return None
    channel_id = get_public_channel_id(guild.id)
    if not channel_id:
        return None
    channel = guild.get_channel(int(channel_id))
    if channel is None:
        try:
            channel = await APP.bot.fetch_channel(int(channel_id))
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            return None
    return channel if hasattr(channel, "send") else None


def _player_line(name: str) -> str:
    try:
        from lyon_test_seed import player_rating

        player = APP.jugador_por_nombre(name)
        if not player:
            return f"**{name}**"
        position = str(player["position"] or "").strip()
        rating = player_rating(player)
        details = []
        if position:
            details.append(position)
        if rating:
            details.append(f"OVR {rating}")
        suffix = f" • {' • '.join(details)}" if details else ""
        return f"**{name}**{suffix}"
    except Exception:
        return f"**{name}**"


def _money_text(value) -> str:
    raw = str(value or "").strip()
    if not raw:
        return "—"
    try:
        return APP.money(raw)
    except Exception:
        return raw


def _public_operation_embed(transfer_id: int):
    import market_channel_report_patch as market_reports

    canonical = market_reports._canonical_id(int(transfer_id))
    if canonical is None:
        return None, None
    rows = market_reports._deal_rows(canonical)
    details = market_reports._deal_details(canonical)
    if not rows or not details:
        return canonical, None

    statuses = {(row["status"] or "").upper() for row in rows}
    if not statuses or not statuses.issubset({"APROBADA", "APLICADA"}):
        return canonical, None

    op_type = str(market_reports._operation_type(details, rows) or "TRANSFERENCIA").upper()
    if "CLAUSUL" in op_type:
        # Los clausulazos mantienen el formato público especial ya existente.
        return canonical, None

    if len(rows) > 1 or "INTERCAMBIO" in op_type:
        title = "🔁 INTERCAMBIO CONFIRMADO"
        color = discord.Color.blurple()
    elif "PRÉSTAMO" in op_type or "PRESTAMO" in op_type or "CESI" in op_type:
        title = "🤝 PRÉSTAMO CONFIRMADO"
        color = discord.Color.blue()
    elif "LIBRE" in op_type:
        title = "🆓 FICHAJE CONFIRMADO"
        color = discord.Color.green()
    else:
        title = "✅ TRANSFERENCIA CONFIRMADA"
        color = discord.Color.green()

    embed = discord.Embed(title=title, color=color)

    if len(rows) == 1:
        row = rows[0]
        embed.description = _player_line(row["player"])
        embed.add_field(name="⬅️ Club anterior", value=row["seller"] or "—", inline=True)
        embed.add_field(name="➡️ Nuevo club", value=row["buyer"] or "—", inline=True)
    else:
        movement_lines = [
            f"• {_player_line(row['player'])}\n  {row['seller'] or '—'} ➜ **{row['buyer'] or '—'}**"
            for row in rows
        ]
        embed.add_field(
            name="⚽ Jugadores involucrados",
            value="\n".join(movement_lines),
            inline=False,
        )

    amount = details["amount"] if _has(details, "amount") else None
    amount_text = _money_text(amount)
    if "PRÉSTAMO" in op_type or "PRESTAMO" in op_type or "CESI" in op_type:
        if amount_text not in {"—", "$0", "0"}:
            embed.add_field(name="💰 Canon", value=f"{amount_text} por temporada", inline=True)
        seasons = details["loan_seasons"] if _has(details, "loan_seasons") else None
        if seasons:
            seasons = int(seasons)
            embed.add_field(
                name="⏳ Duración",
                value=f"{seasons} temporada{'s' if seasons != 1 else ''}",
                inline=True,
            )
        purchase = details["purchase_option_value"] if _has(details, "purchase_option_value") else None
        embed.add_field(
            name="🛒 Opción de compra",
            value=_money_text(purchase) if purchase else "Sin opción",
            inline=True,
        )
    elif amount_text not in {"—", "$0", "0"}:
        label = "💰 Dinero adicional" if len(rows) > 1 else "💰 Monto"
        embed.add_field(name=label, value=amount_text, inline=True)

    embed.set_footer(text="AJAP Transfer Market • Resumen oficial del mercado")
    return canonical, embed


async def publish_public_operation(interaction, transfer_id: int):
    if interaction.guild is None:
        return False

    canonical, embed = _public_operation_embed(int(transfer_id))
    if canonical is None or embed is None:
        return False
    if _was_announced(interaction.guild.id, "TRANSFER", canonical):
        return True

    channel = await _resolve_public_channel(interaction.guild)
    if channel is None:
        return False

    try:
        msg = await channel.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
        _remember_announcement(
            interaction.guild.id,
            "TRANSFER",
            canonical,
            channel.id,
            msg.id,
        )
        return True
    except (discord.Forbidden, discord.HTTPException) as exc:
        print(f"WARNING AJAP: resumen público operación #{canonical} falló: {exc}")
        return False


def _install_market_operation_hook(runtime):
    import market_channel_report_patch as market_reports

    current = market_reports.publish_or_refresh_operation
    if getattr(current, "_ajap_public_market_feed", False):
        runtime.publish_or_refresh_operation_report = current
        return False

    async def publish_with_public_summary(interaction, transfer_id: int):
        result = await current(interaction, transfer_id)
        try:
            await publish_public_operation(interaction, transfer_id)
        except Exception as exc:
            # Un fallo del canal público nunca debe romper una transferencia oficial.
            print(f"WARNING AJAP: anuncio público operación #{transfer_id} falló: {exc}")
        return result

    publish_with_public_summary._ajap_public_market_feed = True
    market_reports.publish_or_refresh_operation = publish_with_public_summary
    runtime.publish_or_refresh_operation_report = publish_with_public_summary
    return True


def _install_clausulazo_channel_bridge():
    import clausulazo_announce_patch as clause_announcements

    current = clause_announcements._announce_channel
    if getattr(current, "_ajap_public_market_channel", False):
        return False

    def configured_summary_or_original(guild):
        if guild is not None:
            try:
                channel_id = get_public_channel_id(guild.id)
                if channel_id:
                    channel = guild.get_channel(int(channel_id))
                    if channel is not None and hasattr(channel, "send"):
                        return channel
            except Exception as exc:
                print(f"WARNING AJAP: no pude resolver canal público de clausulazo: {exc}")
        return current(guild)

    configured_summary_or_original._ajap_public_market_channel = True
    clause_announcements._announce_channel = configured_summary_or_original
    return True


def _loan_purchase_embed(loan, payment):
    amount = None
    if payment and _has(payment, "amount"):
        amount = payment["amount"]
    if amount is None and _has(loan, "purchase_option_value"):
        amount = loan["purchase_option_value"]

    embed = discord.Embed(
        title="🛒 OPCIÓN DE COMPRA EJECUTADA",
        description=(
            f"**{loan['borrower_club']}** compró definitivamente a "
            f"{_player_line(loan['player'])}."
        ),
        color=discord.Color.green(),
    )
    embed.add_field(name="⬅️ Club propietario", value=loan["owner_club"], inline=True)
    embed.add_field(name="➡️ Nuevo propietario", value=loan["borrower_club"], inline=True)
    embed.add_field(name="💰 Importe", value=_money_text(amount), inline=True)
    embed.set_footer(text="AJAP Transfer Market • Resumen oficial del mercado")
    return embed


async def publish_public_loan_purchase(interaction, loan_id: int):
    if interaction.guild is None or _was_announced(interaction.guild.id, "LOAN_PURCHASE", loan_id):
        return False

    with APP.db() as conn:
        loan = conn.execute("SELECT * FROM loans WHERE id = ? LIMIT 1", (int(loan_id),)).fetchone()
        payment = conn.execute(
            """
            SELECT * FROM loan_option_payments
            WHERE loan_id = ? ORDER BY id DESC LIMIT 1
            """,
            (int(loan_id),),
        ).fetchone()

    if not loan or (loan["status"] or "").upper() != "PURCHASED":
        return False

    channel = await _resolve_public_channel(interaction.guild)
    if channel is None:
        return False

    try:
        msg = await channel.send(
            embed=_loan_purchase_embed(loan, payment),
            allowed_mentions=discord.AllowedMentions.none(),
        )
        _remember_announcement(
            interaction.guild.id,
            "LOAN_PURCHASE",
            int(loan_id),
            channel.id,
            msg.id,
        )
        return True
    except (discord.Forbidden, discord.HTTPException) as exc:
        print(f"WARNING AJAP: anuncio público compra préstamo #{loan_id} falló: {exc}")
        return False


def _install_loan_purchase_hook():
    import loan_lifecycle_patch as loans

    view_cls = loans.LoanOptionDecisionView
    if getattr(view_cls, "_ajap_public_purchase_feed", False):
        return False

    original_init = view_cls.__init__

    def public_feed_init(self, *args, **kwargs):
        original_init(self, *args, **kwargs)
        loan_id = int(getattr(self, "loan_id", 0) or 0)
        if not loan_id:
            return

        for child in self.children:
            if not isinstance(child, discord.ui.Button) or child.label != "Ejecutar compra":
                continue
            original_callback = child.callback

            async def buy_and_publish(interaction, _original=original_callback, _loan_id=loan_id):
                try:
                    await _original(interaction)
                finally:
                    try:
                        fresh = loans.loan_by_id(_loan_id)
                        if fresh and (fresh["status"] or "").upper() == "PURCHASED":
                            await publish_public_loan_purchase(interaction, _loan_id)
                    except Exception as exc:
                        print(
                            f"WARNING AJAP: anuncio público compra préstamo #{_loan_id} falló: {exc}"
                        )

            child.callback = buy_and_publish
            break

    view_cls.__init__ = public_feed_init
    view_cls._ajap_public_purchase_feed = True
    return True


def apply_public_market_summary_patch(runtime, bot):
    global APP
    APP = runtime
    if getattr(runtime, "_ajap_public_market_summary_patch", False):
        return

    hooked_ops = _install_market_operation_hook(runtime)
    hooked_clauses = _install_clausulazo_channel_bridge()
    hooked_purchases = _install_loan_purchase_hook()

    if bot.tree.get_command("canal_resumen_mercado") is None:
        @bot.tree.command(
            name="canal_resumen_mercado",
            description="Usa este canal como resumen público automático del mercado",
        )
        async def canal_resumen_mercado(interaction: discord.Interaction):
            if not APP.es_admin(interaction):
                await interaction.response.send_message("⛔ Solo administradores.", ephemeral=True)
                return
            if not interaction.guild or not isinstance(interaction.channel, discord.TextChannel):
                await interaction.response.send_message(
                    "⚠️ Usá este comando dentro del canal de texto que querés usar como resumen.",
                    ephemeral=True,
                )
                return

            me = interaction.guild.me
            if me is not None:
                perms = interaction.channel.permissions_for(me)
                if not perms.view_channel or not perms.send_messages:
                    await interaction.response.send_message(
                        "⚠️ El bot necesita **Ver canal** y **Enviar mensajes** en este canal.",
                        ephemeral=True,
                    )
                    return

            set_public_channel(
                interaction.guild.id,
                interaction.channel.id,
                interaction.user.id,
            )
            await interaction.response.send_message(
                f"✅ **Resumen público del mercado:** {interaction.channel.mention}\n"
                "Voy a anunciar acá transferencias, préstamos, intercambios, clausulazos "
                "y opciones de compra confirmadas.",
                ephemeral=True,
            )

    runtime.public_market_channel_id = get_public_channel_id
    runtime.publish_public_market_operation = publish_public_operation
    runtime._ajap_public_market_summary_patch = True
    print(
        "AJAP resumen público activo: /canal_resumen_mercado + transferencias/préstamos/"
        f"intercambios/clausulazos/compras | op-hook={'OK' if hooked_ops else 'YA'} "
        f"| clausulazo={'OK' if hooked_clauses else 'YA'} "
        f"| compra={'OK' if hooked_purchases else 'YA'}"
    )


# bot.py importa este módulo antes de run_bot. Envolvemos guild isolation para
# aplicar el resumen recién cuando runtime.db_for_guild ya existe. bot.py luego
# monta Liga encima de este wrapper, de modo que ambos parches se conservan.
if not getattr(guild_isolation_patch, "_ajap_public_market_summary_wrapper", False):
    _ORIGINAL_APPLY_GUILD_ISOLATION = guild_isolation_patch.apply_guild_isolation_patch

    def _apply_guild_isolation_and_public_summary(runtime, bot):
        _ORIGINAL_APPLY_GUILD_ISOLATION(runtime, bot)
        apply_public_market_summary_patch(runtime, bot)

    guild_isolation_patch.apply_guild_isolation_patch = _apply_guild_isolation_and_public_summary
    guild_isolation_patch._ajap_public_market_summary_wrapper = True
