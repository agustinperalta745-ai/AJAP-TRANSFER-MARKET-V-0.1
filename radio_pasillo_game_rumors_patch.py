"""Radio Pasillo: rumores inmersivos del universo AJPA.

Los rumores usan únicamente clubes con DT enlazado y jugadores que realmente
figuran en sus planteles AJPA. Se presentan como rumores de periodismo deportivo
(dentro del juego), sin atribuir delitos, consumo de sustancias, vida sexual,
salud u otras conductas personales graves a futbolistas reales.

Se integra sobre el selector existente de Radio Pasillo; no crea otro loop ni
modifica el intervalo de dos horas.
"""

from __future__ import annotations

import random
from contextlib import closing

import radio_pasillo_feature_ads_patch as radio
import radio_pasillo_sports_column_patch as sports


RUMOR_KEY_PREFIX = "rumor|"
RUMOR_CHANCE = 0.24

_POSITIVE_RUMORS = (
    (
        "ganando_lugar",
        "👀 **{player} empieza a ganar terreno en {team}**\n"
        "En los pasillos del club comentan que **{player}** viene dejando buenas sensaciones y podría "
        "tener más protagonismo en los próximos partidos. Por ahora, el DT no confirma nada.",
    ),
    (
        "titularidad",
        "📋 **¿Se viene una oportunidad para {player}?**\n"
        "Radio Pasillo recoge versiones de que **{player}** estaría siendo considerado seriamente para "
        "ganarse un lugar entre los titulares de **{team}**.",
    ),
    (
        "otra_posicion",
        "🧠 **Movimiento táctico en {team}**\n"
        "Se comenta que el cuerpo técnico estaría probando a **{player}** en un rol diferente. "
        "La idea sería encontrar una nueva forma de aprovecharlo dentro del equipo.",
    ),
    (
        "elogios_internos",
        "👏 **Buenas referencias para {player}**\n"
        "Desde el entorno futbolístico de **{team}** llegan comentarios positivos sobre **{player}**. "
        "Su nombre estaría creciendo en la consideración del DT.",
    ),
    (
        "seguimiento",
        "🔎 **Un nombre que empieza a llamar la atención**\n"
        "El nombre de **{player}**, actualmente en **{team}**, habría empezado a aparecer en conversaciones "
        "de otros clubes de AJPA. De momento no existe ninguna oferta confirmada.",
    ),
    (
        "proyecto",
        "🌟 **{team} podría apostar más por {player}**\n"
        "Hay quienes aseguran que **{player}** está bien considerado dentro del proyecto del club y que "
        "podría recibir mayor responsabilidad si mantiene su lugar en la consideración del DT.",
    ),
)

_NEGATIVE_RUMORS = (
    (
        "banco",
        "🪑 **¿Pierde terreno {player}?**\n"
        "En **{team}** circula la versión de que **{player}** podría arrancar más partidos desde el banco "
        "si el DT decide mover piezas. Nada está confirmado todavía.",
    ),
    (
        "continuidad",
        "❓ **Dudas alrededor de {player}**\n"
        "Radio Pasillo señala que la continuidad de **{player}** como pieza importante de **{team}** no estaría "
        "tan asegurada como semanas atrás. El próximo tramo puede ser clave.",
    ),
    (
        "competencia",
        "⚔️ **Competencia interna en {team}**\n"
        "**{player}** tendría que pelear más fuerte por su lugar: dentro del plantel habría varios nombres "
        "disputando el mismo espacio en la consideración del DT.",
    ),
    (
        "mercado",
        "💼 **{player}, un nombre a seguir en el mercado**\n"
        "En los pasillos de **{team}** no descartan escuchar propuestas por **{player}** si aparece una oferta "
        "que convenza al club. Por ahora, sigue formando parte del plantel.",
    ),
    (
        "menos_minutos",
        "⏱️ **Podrían cambiar los minutos de {player}**\n"
        "Se rumorea que **{player}** podría perder protagonismo en **{team}** si el cuerpo técnico cambia la "
        "estructura del equipo para los próximos encuentros.",
    ),
    (
        "examen",
        "🔬 **{player}, bajo examen futbolístico**\n"
        "El próximo tramo sería importante para **{player}** en **{team}**. En el entorno del equipo creen que "
        "su lugar dentro de la rotación podría depender de cómo responda cuando le toque participar.",
    ),
)

_NEUTRAL_RUMORS = (
    (
        "sorpresa",
        "🎲 **¿Sorpresa preparada en {team}?**\n"
        "Algunas voces aseguran que **{player}** podría aparecer en una función inesperada en el próximo "
        "partido. El DT guarda silencio y alimenta el misterio.",
    ),
    (
        "charlas",
        "🗣️ **El nombre de {player} aparece en las charlas de {team}**\n"
        "Sin decisiones oficiales, **{player}** estaría siendo uno de los nombres evaluados por el cuerpo "
        "técnico a la hora de preparar los próximos encuentros.",
    ),
    (
        "mercado_mira",
        "📡 **Radar de mercado sobre {player}**\n"
        "No hay propuesta formal, pero el nombre de **{player}** comienza a sonar en conversaciones informales "
        "del mercado AJPA. **{team}** por ahora no mueve ficha.",
    ),
)


def _rumor_key(team: str, player: str, slug: str) -> str:
    return (
        f"{RUMOR_KEY_PREFIX}{sports._team_key(team)}|"
        f"{sports._norm(player)}|{slug}"
    )


def _rumor_candidates(guild_id: int, last_key: str | None):
    try:
        with closing(radio._conn_for_guild(guild_id)) as conn:
            linked = sports._linked_clubs(conn)
            if not linked:
                return []

            pool = []
            for club in linked:
                team = sports._canonical_team(club)
                roster = sports._team_roster(conn, team)
                if not roster:
                    continue
                for player in roster:
                    if str(player or "").strip():
                        pool.append((team, str(player).strip()))
    except Exception:
        return []

    if not pool:
        return []

    templates = list(_POSITIVE_RUMORS + _NEGATIVE_RUMORS + _NEUTRAL_RUMORS)
    random.shuffle(pool)
    random.shuffle(templates)

    candidates = []
    # Limitar combinaciones para no construir cientos de textos en cada ciclo.
    for team, player in pool[:12]:
        for slug, template in templates[:8]:
            key = _rumor_key(team, player, slug)
            if key == last_key:
                continue
            candidates.append((key, template.format(player=player, team=team)))

    if last_key and str(last_key).startswith(RUMOR_KEY_PREFIX):
        parts = str(last_key).split("|")
        previous_team = parts[1] if len(parts) > 1 else ""
        previous_player = parts[2] if len(parts) > 2 else ""
        preferred = [
            item
            for item in candidates
            if len(item[0].split("|")) > 2
            and (
                item[0].split("|")[1] != previous_team
                or item[0].split("|")[2] != previous_player
            )
        ]
        if preferred:
            candidates = preferred

    return candidates


_BASE_SELECT_MESSAGE = sports._select_message


def _select_message_with_rumors(guild_id: int, last_key: str | None):
    rumors = _rumor_candidates(guild_id, last_key)
    base = _BASE_SELECT_MESSAGE(guild_id, last_key)

    if rumors and (base is None or random.random() < RUMOR_CHANCE):
        return random.choice(rumors)
    return base or (random.choice(rumors) if rumors else None)


sports._select_message = _select_message_with_rumors

# El sender ya consulta sports._select_message en cada ejecución. Cambiamos solo
# el encabezado para distinguir claramente que se trata de la sección de rumores,
# sin añadir otra publicación ni tocar el temporizador.
_BASE_SEND_DUE = sports._send_due_with_sports

async def _send_due_with_rumor_header(guild) -> bool:
    # El sender original arma su propio encabezado. Para mantener el cambio
    # mínimo, dejamos que el contenido siga el formato de columna deportiva; la
    # primera línea de cada rumor ya tiene estilo propio y el texto usa lenguaje
    # de rumor ("se comenta", "circula la versión", etc.).
    return await _BASE_SEND_DUE(guild)


print("AJAP Radio Pasillo: rumores futbolísticos inmersivos activos")
