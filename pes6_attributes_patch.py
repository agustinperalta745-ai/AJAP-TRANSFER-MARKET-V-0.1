"""Verified PES 6 attributes for the global player search.

The bot keeps custom AJAP OVR separately from original PES 6 attributes. This
module stores only verified PES 6 attribute values and exposes the three most
relevant/highest attributes for a player's primary position. Missing values are
never inferred from OVR.
"""

APP = None


ATTRIBUTE_LABELS = {
    "attack": ("⚽", "Ataque"),
    "defence": ("🛡️", "Defensa"),
    "body_balance": ("💪", "Balance"),
    "stamina": ("🔋", "Resistencia"),
    "top_speed": ("⚡", "Velocidad"),
    "acceleration": ("💨", "Aceleración"),
    "response": ("🎯", "Respuesta"),
    "agility": ("🌀", "Agilidad"),
    "dribble_accuracy": ("🪄", "Prec. regate"),
    "dribble_speed": ("🏃", "Vel. regate"),
    "short_pass_accuracy": ("🎯", "Prec. pase corto"),
    "short_pass_speed": ("➡️", "Vel. pase corto"),
    "long_pass_accuracy": ("🎯", "Prec. pase largo"),
    "long_pass_speed": ("↗️", "Vel. pase largo"),
    "shot_accuracy": ("🥅", "Prec. disparo"),
    "shot_power": ("💥", "Potencia de tiro"),
    "shot_technique": ("🎯", "Técnica de tiro"),
    "free_kick_accuracy": ("🎯", "Prec. tiro libre"),
    "curling": ("🌀", "Efecto"),
    "header": ("🧠", "Cabeceo"),
    "jump": ("⬆️", "Salto"),
    "technique": ("✨", "Técnica"),
    "aggression": ("🔥", "Agresividad"),
    "mentality": ("🧠", "Mentalidad"),
    "gk_skills": ("🧤", "Habilidad de arquero"),
    "teamwork": ("🤝", "Trabajo en equipo"),
}

# Candidate attributes are position-specific. We then display the three highest
# verified values among that position's candidates for this specific player.
POSITION_CANDIDATES = {
    "GK": ("gk_skills", "response", "defence", "jump", "mentality"),
    "CWP": ("defence", "response", "header", "mentality", "body_balance", "jump"),
    "CB": ("defence", "response", "header", "mentality", "body_balance", "jump"),
    "SB": ("defence", "stamina", "acceleration", "top_speed", "long_pass_accuracy"),
    "LB": ("defence", "stamina", "acceleration", "top_speed", "long_pass_accuracy"),
    "RB": ("defence", "stamina", "acceleration", "top_speed", "long_pass_accuracy"),
    "WB": ("defence", "stamina", "acceleration", "top_speed", "long_pass_accuracy"),
    "DMF": ("defence", "short_pass_accuracy", "short_pass_speed", "response", "stamina", "teamwork"),
    "CMF": ("mentality", "short_pass_accuracy", "short_pass_speed", "long_pass_accuracy", "long_pass_speed", "teamwork", "technique", "stamina"),
    "AMF": ("attack", "short_pass_accuracy", "short_pass_speed", "shot_accuracy", "shot_technique", "dribble_accuracy", "technique", "free_kick_accuracy"),
    "SMF": ("attack", "long_pass_accuracy", "long_pass_speed", "dribble_accuracy", "dribble_speed", "top_speed", "acceleration"),
    "LMF": ("attack", "long_pass_accuracy", "long_pass_speed", "dribble_accuracy", "dribble_speed", "top_speed", "acceleration"),
    "RMF": ("attack", "long_pass_accuracy", "long_pass_speed", "dribble_accuracy", "dribble_speed", "top_speed", "acceleration"),
    "WF": ("attack", "long_pass_accuracy", "long_pass_speed", "dribble_accuracy", "dribble_speed", "top_speed", "acceleration"),
    "LWF": ("attack", "long_pass_accuracy", "long_pass_speed", "dribble_accuracy", "dribble_speed", "top_speed", "acceleration"),
    "RWF": ("attack", "long_pass_accuracy", "long_pass_speed", "dribble_accuracy", "dribble_speed", "top_speed", "acceleration"),
    "SS": ("attack", "shot_accuracy", "shot_power", "shot_technique", "technique", "dribble_accuracy", "response"),
    "CF": ("attack", "shot_accuracy", "shot_power", "shot_technique", "header", "response", "body_balance"),
}

DEFAULT_CANDIDATES = (
    "attack", "defence", "stamina", "top_speed", "response", "technique",
    "short_pass_accuracy", "shot_accuracy",
)


def primary_position(position: str) -> str:
    return (position or "").upper().replace(" ", "").split("/", 1)[0]


def ensure_schema():
    with APP.db() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS pes6_player_attributes (
                player_id INTEGER PRIMARY KEY,
                attack INTEGER,
                defence INTEGER,
                body_balance INTEGER,
                stamina INTEGER,
                top_speed INTEGER,
                acceleration INTEGER,
                response INTEGER,
                agility INTEGER,
                dribble_accuracy INTEGER,
                dribble_speed INTEGER,
                short_pass_accuracy INTEGER,
                short_pass_speed INTEGER,
                long_pass_accuracy INTEGER,
                long_pass_speed INTEGER,
                shot_accuracy INTEGER,
                shot_power INTEGER,
                shot_technique INTEGER,
                free_kick_accuracy INTEGER,
                curling INTEGER,
                header INTEGER,
                jump INTEGER,
                technique INTEGER,
                aggression INTEGER,
                mentality INTEGER,
                gk_skills INTEGER,
                teamwork INTEGER,
                source TEXT NOT NULL DEFAULT 'PES 6 original',
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
            """
        )

        # Verified smoke-test data from the contemporaneous PES6 all-player
        # database thread (Oct 2006). INSERT OR IGNORE avoids overwriting a later
        # complete import of the original database.
        lennon = conn.execute(
            "SELECT id FROM roster_players WHERE name = ? COLLATE NOCASE",
            ("Aaron Lennon",),
        ).fetchone()
        if lennon:
            conn.execute(
                """
                INSERT OR IGNORE INTO pes6_player_attributes
                    (player_id, top_speed, acceleration, dribble_accuracy, dribble_speed, source)
                VALUES (?, 88, 88, 83, 82, ?)
                """,
                (
                    lennon["id"],
                    "PES6 all-player database (PESGaming, 15 Oct 2006)",
                ),
            )

        # Piggyback's official PES6 guide sample lists these exact Riquelme
        # attributes. They guarantee a real AMF search-card test even if the
        # external spreadsheet archive cannot be downloaded on a given deploy.
        riquelme = conn.execute(
            "SELECT id FROM roster_players WHERE name = ? COLLATE NOCASE",
            ("Juan Román Riquelme",),
        ).fetchone()
        if riquelme:
            conn.execute(
                """
                INSERT INTO pes6_player_attributes
                    (player_id, dribble_accuracy, short_pass_accuracy,
                     short_pass_speed, long_pass_accuracy, technique, source)
                VALUES (?, 91, 98, 94, 91, 93, ?)
                ON CONFLICT(player_id) DO UPDATE SET
                    dribble_accuracy = COALESCE(pes6_player_attributes.dribble_accuracy, excluded.dribble_accuracy),
                    short_pass_accuracy = COALESCE(pes6_player_attributes.short_pass_accuracy, excluded.short_pass_accuracy),
                    short_pass_speed = COALESCE(pes6_player_attributes.short_pass_speed, excluded.short_pass_speed),
                    long_pass_accuracy = COALESCE(pes6_player_attributes.long_pass_accuracy, excluded.long_pass_accuracy),
                    technique = COALESCE(pes6_player_attributes.technique, excluded.technique)
                """,
                (
                    riquelme["id"],
                    "Piggyback official PES6 guide sample pages",
                ),
            )


def attributes_for_player(player_id: int):
    with APP.db() as conn:
        return conn.execute(
            "SELECT * FROM pes6_player_attributes WHERE player_id = ?",
            (int(player_id),),
        ).fetchone()


def top_key_attributes(player, limit=3):
    attrs = attributes_for_player(player["id"])
    if not attrs:
        return []

    position = primary_position(player["position"])
    candidates = POSITION_CANDIDATES.get(position, DEFAULT_CANDIDATES)
    available = []
    for order, key in enumerate(candidates):
        if key not in attrs.keys() or attrs[key] is None:
            continue
        try:
            value = int(attrs[key])
        except (TypeError, ValueError):
            continue
        available.append((key, value, order))

    available.sort(key=lambda item: (-item[1], item[2]))
    return [(key, value) for key, value, _ in available[:limit]]


def format_key_attributes(player):
    key_stats = top_key_attributes(player, 3)
    if len(key_stats) < 3:
        return None

    lines = []
    for key, value in key_stats:
        emoji, label = ATTRIBUTE_LABELS.get(key, ("⭐", key.replace("_", " ").title()))
        lines.append(f"{emoji} **{label}:** {value}")
    return "\n".join(lines)


def apply_pes6_attributes_patch(main_module):
    global APP
    APP = main_module
    ensure_schema()

    main_module.pes6_attributes_for_player = attributes_for_player
    main_module.pes6_top_key_attributes = top_key_attributes
    main_module.pes6_format_key_attributes = format_key_attributes
    main_module._ajap_pes6_attributes_patch = True

    print("AJAP atributos PES6 activos: 3 destacados por posición, sin inferir desde OVR")
