# AJAP Transfer Market v0.1

Bot de Discord para gestionar el mercado de fichajes de una liga de PES 6 y convertir los acuerdos del mercado en una cola administrativa segura para editar el juego.

## Flujo principal

1. Los clubes pueden publicar jugadores durante la temporada.
2. Las ofertas solo se pueden enviar y resolver cuando un administrador abre el mercado.
3. Cuando el dueño acepta una oferta, se crea una operación `PENDIENTE_ADMIN` y el jugador todavía no cambia de club.
4. Un administrador revisa y aprueba la operación.
5. Después de realizar el cambio en PES 6, el administrador marca `Aplicado en PES`.
6. Recién entonces se actualiza el plantel oficial del bot y se registra el movimiento en el historial.

## Datos administrativos

- Cada jugador tiene un ID estable con formato `AJAP-000001`.
- Las operaciones guardan temporada, tipo, club origen, club destino, monto, estado y responsables administrativos.
- Estados principales: `PENDIENTE_ADMIN`, `APROBADA`, `APLICADA`, `RECHAZADA_ADMIN`.
- Tipos admitidos como referencia: transferencia, préstamo, intercambio y jugador libre.
- Las operaciones pendientes bloquean una segunda negociación del mismo jugador.

## Comandos

- `/mercado`: panel principal.
- `/operaciones_pendientes`: cola administrativa para aprobar o aplicar cambios en PES.
- `/historial_jugador jugador:<nombre>`: historial de movimientos aplicados.
- `/exportar_mercado`: genera un CSV de la temporada activa para usar como checklist al editar PES.

La mayor parte de la gestión cotidiana también está disponible mediante botones dentro de `/mercado`.

## Persistencia

La base usa SQLite. En Railway, `DB_PATH` debe apuntar al volumen persistente para que clubes, planteles, publicaciones, ofertas, operaciones, temporadas e historial sobrevivan reinicios y deploys.

## Variables de entorno

- `DISCORD_TOKEN`: token privado del bot.
- `DB_PATH`: ruta de la base SQLite persistente, configurada en Railway.

Nunca subas el archivo `.env` ni el token al repositorio.

## Ejecutar

```bash
pip install -r requirements.txt
python bot.py
```

Requiere Python y `discord.py` 2.4 o superior.
