"""Protección doble de clausulazos por ventana de mercado.

Regla AJAP:
- Un jugador que ya sufrió un clausulazo aprobado no puede volver a ser clausulado
  hasta la próxima ventana.
- El club que ya perdió un jugador por clausulazo aprobado queda protegido completo
  hasta la próxima ventana.
- Mientras haya un clausulazo pendiente contra un club, no se permite abrir otro
  contra ese mismo club; si se rechaza, el club vuelve a quedar disponible.
"""

import clausulazo_patch as clausulas


def _club_clause_state(runtime, cycle_id: int, seller_club: str, exclude_request_id=None):
    """Devuelve el último clausulazo pendiente/aprobado sufrido por un club en la ventana."""
    params = [cycle_id, seller_club]
    exclude_sql = ""
    if exclude_request_id is not None:
        exclude_sql = " AND id != ?"
        params.append(exclude_request_id)

    with runtime.db() as conn:
        return conn.execute(
            f"""
            SELECT id, player, seller_club, buyer_club, status
            FROM clause_requests
            WHERE cycle_id = ?
              AND seller_club = ? COLLATE NOCASE
              AND status IN ('PENDIENTE_STAFF', 'APROBADO')
              {exclude_sql}
            ORDER BY CASE status WHEN 'APROBADO' THEN 0 ELSE 1 END, id DESC
            LIMIT 1
            """,
            tuple(params),
        ).fetchone()


def apply_clausulazo_club_protection_patch(runtime):
    base_create = clausulas.create_clause_request
    base_approve = clausulas.approve_request
    base_home_embed = clausulas.home_embed

    def protected_create_clause_request(interaction, ficha):
        # Dejá que la implementación original resuelva mercado cerrado/equipo propio/etc.
        cycle = clausulas.active_cycle()
        if cycle and ficha:
            target_club = (ficha["club"] or "").strip()
            if target_club:
                club_lock = _club_clause_state(runtime, cycle["id"], target_club)
                if club_lock:
                    if club_lock["status"] == "APROBADO":
                        return (
                            False,
                            f"🛡️ **{target_club} está protegido durante este mercado.** "
                            f"Ya sufrió un clausulazo con **{club_lock['player']}**. "
                            "No se le puede clausular ningún otro jugador hasta la próxima ventana.",
                        )
                    return (
                        False,
                        f"⏳ Ya hay un clausulazo pendiente contra **{target_club}** "
                        f"por **{club_lock['player']}**. Hasta que Staff lo resuelva no se puede iniciar otro contra ese club.",
                    )

        # La función original conserva además la protección individual del jugador
        # y hace el descuento recién después de todas las validaciones.
        return base_create(interaction, ficha)

    def protected_approve_request(req, staff_id):
        # Segunda barrera: si dos pedidos contra el mismo club quedaron pendientes
        # antes de este parche, solo el primero aprobado puede prosperar.
        fresh = clausulas.request_by_id(req["id"])
        if fresh and fresh["status"] == "PENDIENTE_STAFF":
            club_lock = _club_clause_state(
                runtime,
                fresh["cycle_id"],
                fresh["seller_club"],
                exclude_request_id=fresh["id"],
            )
            if club_lock and club_lock["status"] == "APROBADO":
                clausulas.reject_request(
                    fresh,
                    staff_id,
                    f"{fresh['seller_club']} ya sufrió un clausulazo en este mercado",
                )
                return (
                    False,
                    f"🛡️ **{fresh['seller_club']}** ya quedó protegido tras el clausulazo de "
                    f"**{club_lock['player']}**. Esta solicitud fue rechazada y el dinero fue devuelto.",
                )
        return base_approve(req, staff_id)

    def protected_home_embed(user_id):
        embed = base_home_embed(user_id)
        for index, field in enumerate(embed.fields):
            if field.name == "🔁 Por jugador":
                embed.set_field_at(
                    index,
                    name="🛡️ Límite por mercado",
                    value="Un jugador solo puede sufrir 1 clausulazo y un club solo puede perder 1 jugador por clausulazo.",
                    inline=False,
                )
            elif field.name == "🔒 Protección":
                embed.set_field_at(
                    index,
                    name="🔒 Protección doble",
                    value=(
                        "Después de un clausulazo aprobado quedan protegidos hasta la próxima ventana: "
                        "**el jugador transferido y todo el club vendedor**."
                    ),
                    inline=False,
                )
        return embed

    clausulas.create_clause_request = protected_create_clause_request
    clausulas.approve_request = protected_approve_request
    clausulas.home_embed = protected_home_embed

    print("AJAP protección doble activa: jugador + club vendedor por ventana de mercado")
