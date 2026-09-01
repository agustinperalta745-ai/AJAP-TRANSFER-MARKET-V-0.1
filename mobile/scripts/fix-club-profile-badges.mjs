import fs from 'node:fs';

const uiPath = 'src/BotParityAppV2.tsx';
let ui = fs.readFileSync(uiPath, 'utf8');

// La pantalla Perfiles de equipo se genera en un paso previo. Ese generador
// todavía dejaba el emoji genérico 🛡️; acá lo sustituimos por ClubBadge sin
// tocar las tarjetas, textos, fondos ni la lógica de navegación.
if (!ui.includes("import { ClubBadge } from './teamBadges';") && !ui.includes("import { ClubBadge, ClubMatchup } from './teamBadges';")) {
  const anchor = "import { BG_PERFIL } from './bg_perfil';";
  if (!ui.includes(anchor)) throw new Error('Profile badges: no encontré import BG_PERFIL');
  ui = ui.replace(anchor, `${anchor}\nimport { ClubBadge } from './teamBadges';`);
}

const listOld = `            <View style={s.heroIconWrap}><Text style={s.heroIcon}>🛡️</Text></View>\n            <View style={s.flex}>\n              <Text style={s.playerName}>{club.club}</Text>`;
const listNew = `            <View style={s.heroIconWrap}><ClubBadge club={club.club} size={74} /></View>\n            <View style={s.flex}>\n              <Text style={s.playerName}>{club.club}</Text>`;
if (ui.includes(listOld)) ui = ui.replace(listOld, listNew);

const profileOld = `      <View style={s.heroClubCard}>\n        <View style={s.heroIconWrap}><Text style={s.heroIcon}>🛡️</Text></View>\n        <View style={s.flex}>\n          <Text style={s.heroClubName}>{selectedClubProfile.club}</Text>`;
const profileNew = `      <View style={s.heroClubCard}>\n        <View style={s.heroIconWrap}><ClubBadge club={selectedClubProfile.club} size={78} /></View>\n        <View style={s.flex}>\n          <Text style={s.heroClubName}>{selectedClubProfile.club}</Text>`;
if (ui.includes(profileOld)) ui = ui.replace(profileOld, profileNew);

if (!ui.includes('<ClubBadge club={club.club} size={74} />')) {
  throw new Error('Profile badges: la lista de clubes no quedó conectada a los escudos reales');
}
if (!ui.includes('<ClubBadge club={selectedClubProfile.club} size={78} />')) {
  throw new Error('Profile badges: el perfil individual no quedó conectado al escudo real');
}

fs.writeFileSync(uiPath, ui);
console.log('Perfiles de equipo: escudos reales restaurados.');
