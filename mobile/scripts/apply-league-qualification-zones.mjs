// OTA-safe qualification labels for the real Liga standings table.
// Keeps the approved inline layout: team -> DT -> qualification.
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

// Use the same qualification suggestion as the cup manager. This keeps the table
// synchronized with the actual Champions/Europa rules instead of hard-coded names.
if (!ui.includes('apiRequest,')) {
  const importAnchor = '  acceptOffer,\n';
  if (!ui.includes(importAnchor)) throw new Error('AJPA Liga zones: no encontré import API');
  ui = ui.replace(importAnchor, `  apiRequest,\n${importAnchor}`);
}

const stateAnchor = `  const [refreshing, setRefreshing] = useState(false);\n`;
const qualificationState = `  const [cupQualification, setCupQualification] = useState<{ champions: string[]; europa: string[]; season_number: number } | null>(null);\n`;
if (!ui.includes(qualificationState)) {
  if (!ui.includes(stateAnchor)) throw new Error('AJPA Liga zones: no encontré estado principal');
  ui = ui.replace(stateAnchor, stateAnchor + qualificationState);
}

const loadAnchor = `      const snap = await fetchSnapshot();\n      setSnapshot(snap);\n`;
const qualificationLoad = `${loadAnchor}      try {\n        const cups = await apiRequest<any>('/api/v1/cups');\n        const suggestion = cups?.qualification_suggestion;\n        setCupQualification({\n          champions: Array.isArray(suggestion?.champions) ? suggestion.champions : [],\n          europa: Array.isArray(suggestion?.europa) ? suggestion.europa : [],\n          season_number: Number(cups?.rules?.season_number || 1),\n        });\n      } catch {\n        setCupQualification(null);\n      }\n`;
if (!ui.includes("apiRequest<any>('/api/v1/cups')")) {
  if (!ui.includes(loadAnchor)) throw new Error('AJPA Liga zones: no encontré carga principal');
  ui = ui.replace(loadAnchor, qualificationLoad);
}

const zoneFrom = `                const zoneColor = index === 0 ? '#f2c94c' : index <= 10 ? '#66a7ff' : index <= 23 ? '#72d9c7' : '#718596';\n                const zoneLabel = index === 0 ? 'Campeón + Copa 1' : index <= 10 ? 'Copa 1' : index <= 23 ? 'Copa 2' : '';`;
const zoneTo = `                const key = row.team.trim().toLocaleLowerCase('es');\n                const suggestedChampions = cupQualification?.champions ?? [];\n                const suggestedEuropa = cupQualification?.europa ?? [];\n                const inChampions = suggestedChampions.length\n                  ? suggestedChampions.some(team => team.trim().toLocaleLowerCase('es') === key)\n                  : index <= 15;\n                const inEuropa = suggestedEuropa.length\n                  ? suggestedEuropa.some(team => team.trim().toLocaleLowerCase('es') === key)\n                  : index >= 16 && index <= 23;\n                const zoneColor = inChampions\n                  ? (index === 0 ? '#f2c94c' : '#66a7ff')\n                  : inEuropa ? '#e2a45c' : '#718596';\n                const zoneLabel = inChampions\n                  ? (index === 0 ? 'Campeón + Champions League' : 'Champions League')\n                  : inEuropa ? 'Europa League' : '';`;

if (!ui.includes(zoneFrom)) {
  throw new Error('AJPA Liga zones: no encontré las etiquetas inline Copa 1/Copa 2');
}
ui = ui.replace(zoneFrom, zoneTo);

for (const required of [
  "'Champions League'",
  "'Europa League'",
  "'Campeón + Champions League'",
  's.leagueZoneInline',
  's.leagueZoneDot',
  "apiRequest<any>('/api/v1/cups')",
]) {
  if (!ui.includes(required)) throw new Error(`AJPA Liga zones: falta ${required}`);
}
if (ui.includes("'Copa 1'") || ui.includes("'Copa 2'")) {
  throw new Error('AJPA Liga zones: quedaron etiquetas genéricas de Copa 1/Copa 2');
}

fs.writeFileSync(path, ui + '\n' + marker + '\n');
console.log('AJPA Liga: equipo -> DT -> Champions League/Europa League, sincronizado con la clasificación real.');
