"""Expose the same persisted PES 6 player attributes used by Discord to AJPA Mobile."""

from __future__ import annotations

import re
from http import HTTPStatus
from urllib.parse import urlparse

import mobile_read_api


STAT_GROUPS = (
    (
        "⚽ Ataque y definición",
        (
            ("attack", "Ataque"),
            ("aggression", "Agresividad"),
            ("shot_accuracy", "Precisión de tiro"),
            ("shot_power", "Potencia de tiro"),
            ("shot_technique", "Técnica de tiro"),
            ("free_kick_accuracy", "Tiros libres"),
            ("curling", "Efecto"),
            ("header", "Cabeceo"),
            ("technique", "Técnica"),
        ),
    ),
    (
        "🎯 Pase y regate",
        (
            ("dribble_accuracy", "Precisión de regate"),
            ("dribble_speed", "Velocidad de regate"),
            ("short_pass_accuracy", "Precisión pase corto"),
            ("short_pass_speed", "Velocidad pase corto"),
            ("long_pass_accuracy", "Precisión pase largo"),
            ("long_pass_speed", "Velocidad pase largo"),
        ),
    ),
    (
        "⚡ Físico y movilidad",
        (
            ("body_balance", "Equilibrio"),
            ("stamina", "Resistencia"),
            ("top_speed", "Velocidad máxima"),
            ("acceleration", "Aceleración"),
            ("response", "Respuesta"),
            ("agility", "Agilidad"),
            ("jump", "Salto"),
        ),
    ),
    (
        "🛡️ Defensa y mentalidad",
        (
            ("defence", "Defensa"),
            ("mentality", "Mentalidad"),
            ("teamwork", "Trabajo en equipo"),
            ("gk_skills", "Cualidad de arquero"),
        ),
    ),
    (
        "🦶 Otros datos PES 6",
        (
            ("injury_resistance", "Resistencia a lesiones"),
            ("weak_foot_usage", "Uso de pierna mala"),
            ("weak_foot_accuracy", "Precisión pierna mala"),
        ),
    ),
)


def _player_stats_payload(conn, player_id: int):
    tables = mobile_read_api._tables(conn)
    if "roster_players" not in tables:
        return None

    roster_cols = mobile_read_api._columns(conn, "roster_players")
    rating = "rating" if "rating" in roster_cols else "NULL AS rating"
    value = "min_sale_value" if "min_sale_value" in roster_cols else "NULL AS min_sale_value"
    player = conn.execute(
        f"""
        SELECT id, name, position, club, {rating}, {value}
        FROM roster_players
        WHERE id=?
        LIMIT 1
        """,
        (int(player_id),),
    ).fetchone()
    if not player:
        return None

    attrs = None
    if "pes6_player_attributes" in tables:
        attrs = conn.execute(
            "SELECT * FROM pes6_player_attributes WHERE player_id=? LIMIT 1",
            (int(player_id),),
        ).fetchone()

    abilities = []
    if "pes6_player_special_abilities" in tables:
        abilities = [
            str(row["ability"])
            for row in conn.execute(
                """
                SELECT ability
                FROM pes6_player_special_abilities
                WHERE player_id=?
                ORDER BY ability COLLATE NOCASE
                """,
                (int(player_id),),
            ).fetchall()
            if str(row["ability"] or "").strip()
        ]

    groups = []
    if attrs:
        attr_keys = set(attrs.keys())
        for title, definitions in STAT_GROUPS:
            items = []
            for key, label in definitions:
                if key not in attr_keys or attrs[key] is None:
                    continue
                items.append({"key": key, "label": label, "value": attrs[key]})
            if items:
                groups.append({"title": title, "items": items})

    source = None
    if attrs:
        attr_keys = set(attrs.keys())
        source = str(attrs["source"] or "").strip() if "source" in attr_keys else ""
        source = source or "PES 6 / JSON"

    return {
        "player": mobile_read_api._player_dict(player),
        "has_stats": bool(attrs),
        "groups": groups,
        "special_abilities": abilities,
        "source": source,
    }


def apply_mobile_player_stats_api_patch() -> None:
    handler = mobile_read_api.MobileReadHandler
    if getattr(handler, "_ajpa_mobile_player_stats_api_patch", False):
        return

    original_get = handler.do_GET

    def get(self):
        path = urlparse(self.path).path.rstrip("/") or "/"
        match = re.fullmatch(r"/api/v1/players/(\d+)/stats", path)
        if not match:
            return original_get(self)

        try:
            with mobile_read_api.readonly_db() as conn:
                payload = _player_stats_payload(conn, int(match.group(1)))
            if payload is None:
                self._json(
                    {"error": "player_not_found", "message": "Ese jugador ya no existe en el plantel."},
                    HTTPStatus.NOT_FOUND,
                )
                return
            self._json(payload)
        except FileNotFoundError as exc:
            self._json(
                {"error": "database_not_found", "message": str(exc)},
                HTTPStatus.SERVICE_UNAVAILABLE,
            )
        except Exception as exc:
            print(f"AJPA mobile PES6 stats error: {type(exc).__name__}: {exc}")
            self._json(
                {"error": "internal_error", "message": "No se pudieron cargar las estadísticas PES 6."},
                HTTPStatus.INTERNAL_SERVER_ERROR,
            )

    handler.do_GET = get
    handler._ajpa_mobile_player_stats_api_patch = True
