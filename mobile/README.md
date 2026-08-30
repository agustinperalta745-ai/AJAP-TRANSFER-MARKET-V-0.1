# AJPA Transfer Market Mobile

App móvil del mercado AJPA, construida sin duplicar la lógica deportiva/económica del bot.

## Arquitectura

`App móvil <-> API read-only <-> misma SQLite <-> bot de Discord`

La primera integración con datos reales es deliberadamente de solo lectura. `mobile_read_api.py` abre SQLite con `mode=ro` + `PRAGMA query_only=ON`, por lo que esta etapa no puede cambiar saldos, planteles, ofertas ni movimientos.

## Datos reales disponibles

- Estado ABIERTO/CERRADO del mercado y temporada activa.
- Catálogo de equipos oficiales activos.
- Presupuesto y cantidad de jugadores por club.
- Planteles con ID AJPA, posición, OVR y valor.
- Publicaciones activas de Transferibles.
- Agentes libres publicados por $0.

Endpoints:

- `GET /health`
- `GET /api/v1/status`
- `GET /api/v1/clubs`
- `GET /api/v1/clubs/{club}/roster`
- `GET /api/v1/market`
- `GET /api/v1/free-agents`
- `GET /api/v1/snapshot`

Los métodos de escritura (`POST`, `PUT`, `PATCH`, `DELETE`) responden `405` en esta fase.

## Arranque del backend móvil

El arranque normal `python bot.py` queda intacto. Para servir Discord + API desde el mismo servicio/volumen:

```bash
python bot_mobile.py
```

`bot_mobile.py` habilita la API y reutiliza después el arranque normal del bot. En Railway, la API escucha el `PORT` asignado por la plataforma.

Variables relevantes:

```env
AJPA_MOBILE_API_ENABLED=1
AJPA_MOBILE_GUILD_ID=<guild de la liga>
```

Si `AJPA_MOBILE_GUILD_ID` no está definido, se usa `DISCORD_GUILD_ID`.

## App Android

La app usa `EXPO_PUBLIC_API_URL` para localizar el backend:

```env
EXPO_PUBLIC_API_URL=https://tu-dominio-publico
```

La interfaz read-only tiene Inicio, Equipos/Planteles, Mercado y Agentes Libres. Hasta incorporar login de Discord no intenta adivinar qué club pertenece al usuario.

## Próximas etapas

1. Publicar la API read-only en Railway y validar contra la base real.
2. Añadir login de Discord y resolver usuario -> club.
3. Recién después habilitar escrituras: publicar, ofertar, responder ofertas, liberar, préstamos, intercambios y herramientas Staff.
