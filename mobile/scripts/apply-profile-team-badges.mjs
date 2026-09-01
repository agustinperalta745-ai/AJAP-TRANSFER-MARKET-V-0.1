import fs from 'node:fs';

const uiPath = new URL('../src/BotParityAppV2.tsx', import.meta.url);
let ui = fs.readFileSync(uiPath, 'utf8');

const listShield = `<View style={s.heroIconWrap}><Text style={s.heroIcon}>🛡️</Text></View>\n            <View style={s.flex}>\n              <Text style={s.playerName}>{club.club}</Text>`;
const listBadge = `<View style={s.heroIconWrap}><ClubBadge club={club.club} size={62} /></View>\n            <View style={s.flex}>\n              <Text style={s.playerName}>{club.club}</Text>`;

const profileShield = `<View style={s.heroIconWrap}><Text style={s.heroIcon}>🛡️</Text></View>\n        <View style={s.flex}>\n          <Text style={s.heroClubName}>{selectedClubProfile.club}</Text>`;
const profileBadge = `<View style={s.heroIconWrap}><ClubBadge club={selectedClubProfile.club} size={62} /></View>\n        <View style={s.flex}>\n          <Text style={s.heroClubName}>{selectedClubProfile.club}</Text>`;

if (ui.includes(listShield)) {
  ui = ui.replace(listShield, listBadge);
}
if (ui.includes(profileShield)) {
  ui = ui.replace(profileShield, profileBadge);
}

if (!ui.includes(listBadge)) {
  throw new Error('AJPA profile badges patch: no se pudo aplicar el escudo real en la lista de equipos');
}
if (!ui.includes(profileBadge)) {
  throw new Error('AJPA profile badges patch: no se pudo aplicar el escudo real en el perfil público');
}
if (!ui.includes(`import { ClubBadge`)) {
  throw new Error('AJPA profile badges patch: ClubBadge no está importado; revisar orden de transforms');
}

fs.writeFileSync(uiPath, ui);
console.log('AJPA profile badges: lista de equipos + perfil público usan escudos reales.');
