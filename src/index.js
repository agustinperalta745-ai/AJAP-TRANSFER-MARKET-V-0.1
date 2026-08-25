import 'dotenv/config';
import { Client, GatewayIntentBits, REST, Routes, SlashCommandBuilder, EmbedBuilder } from 'discord.js';

const token = process.env.DISCORD_TOKEN;
const clientId = process.env.DISCORD_CLIENT_ID;
const guildId = process.env.DISCORD_GUILD_ID;

if (!token || !clientId || !guildId) {
  console.error('Faltan variables de entorno. Revisá DISCORD_TOKEN, DISCORD_CLIENT_ID y DISCORD_GUILD_ID.');
  process.exit(1);
}

const commands = [
  new SlashCommandBuilder()
    .setName('ping')
    .setDescription('Comprueba si AJAP Transfer Market está online.'),
  new SlashCommandBuilder()
    .setName('mercado')
    .setDescription('Muestra el estado del mercado de transferencias.'),
].map(command => command.toJSON());

const rest = new REST({ version: '10' }).setToken(token);

async function registerCommands() {
  await rest.put(Routes.applicationGuildCommands(clientId, guildId), { body: commands });
  console.log('Comandos slash registrados correctamente.');
}

const client = new Client({
  intents: [GatewayIntentBits.Guilds],
});

client.once('ready', readyClient => {
  console.log(`AJAP Transfer Market conectado como ${readyClient.user.tag}`);
});

client.on('interactionCreate', async interaction => {
  if (!interaction.isChatInputCommand()) return;

  if (interaction.commandName === 'ping') {
    await interaction.reply(`🏓 Pong — ${client.ws.ping} ms`);
    return;
  }

  if (interaction.commandName === 'mercado') {
    const embed = new EmbedBuilder()
      .setTitle('⚽ AJAP Transfer Market v0.1')
      .setDescription('El mercado de transferencias está operativo.')
      .addFields(
        { name: 'Estado', value: '🟢 Online', inline: true },
        { name: 'Versión', value: '0.1', inline: true },
        { name: 'Próximamente', value: 'Publicar jugadores, ofertas, fichajes y administración del mercado.' },
      )
      .setFooter({ text: 'AJAP Transfer Market' })
      .setTimestamp();

    await interaction.reply({ embeds: [embed] });
  }
});

async function start() {
  try {
    await registerCommands();
    await client.login(token);
  } catch (error) {
    console.error('No se pudo iniciar el bot:', error);
    process.exit(1);
  }
}

start();
