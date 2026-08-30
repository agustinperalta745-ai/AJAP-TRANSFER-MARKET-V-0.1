# AJPA Transfer Market Mobile

Primera base de la app móvil del mercado de fichajes.

## Objetivo

La app no reemplaza ni duplica la lógica del bot. La arquitectura prevista es:

`App móvil <-> API compartida <-> base de datos <-> bot de Discord`

La API será la única puerta de entrada a las operaciones del mercado para que Discord y la app respeten las mismas reglas.

## Estado actual

La primera versión contiene una interfaz navegable con datos de demostración:

- Inicio del club.
- Presupuesto, tamaño de plantel, ofertas y estado del mercado.
- Mi plantel.
- Jugadores publicados en el mercado.
- Ofertas recibidas y enviadas.
- Base de cliente HTTP mediante `EXPO_PUBLIC_API_URL`.

Todavía no modifica datos reales ni toca la base SQLite de producción.

## Ejecutar

Requiere Node.js 22.13 o superior para Expo SDK 57.

```bash
cd mobile
npm install
npm start
```

En Android se puede abrir con el flujo de desarrollo de Expo. Para una APK instalable se configurará EAS Build en una etapa posterior.

## Próximo paso técnico

Crear una API HTTP pequeña en el backend existente para exponer inicialmente endpoints de solo lectura:

- `GET /api/me`
- `GET /api/clubs/{club_id}`
- `GET /api/clubs/{club_id}/roster`
- `GET /api/market/listings`
- `GET /api/offers`

Después de validar autenticación y permisos se habilitarán las acciones de escritura: ofertar, aceptar, rechazar, contraofertar, publicar, liberar y operaciones de staff.
