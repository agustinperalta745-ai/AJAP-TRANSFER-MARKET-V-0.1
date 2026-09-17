// OTA-safe qualification labels for the real Liga standings table.
// The label is derived only from the CURRENT table position:
// 1st-16th Champions League, 17th-24th Europa League.
import fs from 'node:fs';

const path = new URL('../src/BotParityAppV2.tsx', import.meta.url);
let ui = fs.readFileSync(path, 'utf8');
const marker = '// league-qualification-zones applied';
if (ui.includes(marker)) process.exit(0);

if (!ui.includes('// league-real-table applied')) {
  throw new Error('AJPA Liga zones: aplicar primero league-real-table');
}
if (!ui.includes('s.leagueZoneInline')) {
  throw new Error('AJPA Liga zones: falta la zona inline de la tabla');
}

const zoneFrom = `                const zoneColor = index === 0 ? '#f2c94c' : index <= 10 ? '#66a7ff' : index <= 23 ? '#72d9c7' : '#718596';
                const zoneLabel = index === 0 ? 'Campeón + Copa 1' : index <= 10 ? 'Copa 1' : index <= 23 ? 'Copa 2' : '';`;

const zoneTo = `                const inChampions = index <= 15;
                const inEuropa = index >= 16 && index <= 23;
                const zoneColor = inChampions
                  ? (index === 0 ? '#f2c94c' : '#66a7ff')
                  : inEuropa ? '#e2a45c' : '#718596';
                const zoneLabel = inChampions
                  ? (index === 0 ? 'Campeón + Champions League' : 'Champions League')
                  : inEuropa ? 'Europa League' : '';`;

if (!ui.includes(zoneFrom)) {
  throw new Error('AJPA Liga zones: no encontré las etiquetas inline Copa 1/Copa 2');
}
ui = ui.replace(zoneFrom, zoneTo);

for (const required of [
  "'Champions League'",
  "'Europa League'",
  "'Campeón + Champions League'",
  'const inChampions = index <= 15',
  'const inEuropa = index >= 16 && index <= 23',
  's.leagueZoneInline',
  's.leagueZoneDot',
]) {
  if (!ui.includes(required)) throw new Error(`AJPA Liga zones: falta ${required}`);
}
if (ui.includes("'Copa 1'") || ui.includes("'Copa 2'")) {
  throw new Error('AJPA Liga zones: quedaron etiquetas genéricas de Copa 1/Copa 2');
}

fs.writeFileSync(path, ui + '\n' + marker + '\n');
console.log('AJPA Liga: clasificación por posición real — 1-16 Champions League, 17-24 Europa League.');
