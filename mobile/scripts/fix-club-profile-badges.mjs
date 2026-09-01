import fs from 'node:fs';

// Los escudos vuelven a cargarse desde sus fuentes originales remotas en
// teamBadges.tsx. Este paso NO modifica, normaliza ni recompone imágenes.
// Sólo conecta ClubBadge con la pantalla de perfiles generada previamente.
const uiPath = 'src/BotParityAppV2.tsx';
let ui = fs.readFileSync(uiPath, 'utf8');

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
  throw new Error('Profile badges: la lista de clubes no quedó conectada a ClubBadge');
}
if (!ui.includes('<ClubBadge club={selectedClubProfile.club} size={78} />')) {
  throw new Error('Profile badges: el perfil individual no quedó conectada a ClubBadge');
}

fs.writeFileSync(uiPath, ui);
console.log('Perfiles de equipo: escudos conectados sin recomprimir ninguna imagen.');
