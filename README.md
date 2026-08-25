# AJPA Transfer Market v0.1

Bot de Discord para gestionar el mercado de fichajes de una liga de PES 6.

## Estado actual

- Conexión segura a Discord mediante `DISCORD_TOKEN`.
- Registro de comandos slash en un servidor de pruebas.
- `/ping` para comprobar que el bot está online.
- `/mercado` para mostrar el estado del mercado.

## Variables de entorno

Usá `.env.example` como referencia y configurá estas variables únicamente en tu entorno local o en el hosting:

- `DISCORD_TOKEN`: token privado del bot.
- `DISCORD_CLIENT_ID`: Application ID de Discord Developer Portal.
- `DISCORD_GUILD_ID`: ID del servidor de Discord donde se probará el bot.

Nunca subas el archivo `.env` ni el token al repositorio.

## Ejecutar

```bash
npm install
npm start
```

Requiere Node.js 20 o superior.
