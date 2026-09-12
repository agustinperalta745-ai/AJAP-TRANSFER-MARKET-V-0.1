// OTA-safe qualification zones for the real Liga standings table.
import fs from 'node:fs';

const path = new URL('../src/BotParityAppV2.tsx', import.meta.url);
let ui = fs.readFileSync(path, 'utf8');
const marker = '// league-qualification-zones applied';
if (ui.includes(marker)) process.exit(0);

if (!ui.includes('// league-real-table applied')) {
  throw new Error('AJPA Liga zones: aplicar primero league-real-table');
}

// Read the same qualification suggestion used by the new cup manager. This keeps
// the table correct from season 2 onward when the reigning Europa champion may
// qualify for Champions from outside the Top 15.
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

const headerFrom = `<Text style={[s.leagueHeaderText, s.leagueColPoints]}>PTS</Text>`;
const headerTo = `${headerFrom}\n                <Text style={[s.leagueHeaderText, s.leagueColZone]}>ZONA</Text>`;
if (!ui.includes(headerFrom)) throw new Error('AJPA Liga zones: no encontré encabezado PTS');
ui = ui.replace(headerFrom, headerTo);

const pointsFrom = `<Text style={[s.leaguePoints, s.leagueColPoints, { color: teamCardTheme(row.team).border }]}>{row.pts}</Text>`;
const pointsTo = `${pointsFrom}\n                  {(() => {\n                    const key = row.team.trim().toLocaleLowerCase('es');\n                    const suggestedChampions = cupQualification?.champions ?? [];\n                    const suggestedEuropa = cupQualification?.europa ?? [];\n                    const inChampions = suggestedChampions.length\n                      ? suggestedChampions.some(team => team.trim().toLocaleLowerCase('es') === key)\n                      : index <= 15;\n                    const inEuropa = suggestedEuropa.length\n                      ? suggestedEuropa.some(team => team.trim().toLocaleLowerCase('es') === key)\n                      : index >= 16 && index <= 23;\n                    const label = inChampions\n                      ? (index === 0 ? 'CAMPEÓN + CHAMPIONS' : 'CHAMPIONS LEAGUE')\n                      : inEuropa ? 'EUROPA LEAGUE' : '—';\n                    const color = inChampions ? (index === 0 ? '#f2c94c' : '#66a7ff') : inEuropa ? '#e2a45c' : '#718596';\n                    return (\n                      <Text numberOfLines={1} style={[s.leagueZoneText, s.leagueColZone, { color }]}>\n                        {label}\n                      </Text>\n                    );\n                  })()}`;
if (!ui.includes(pointsFrom)) throw new Error('AJPA Liga zones: no encontré celda de puntos');
ui = ui.replace(pointsFrom, pointsTo);

const widthFrom = `leagueTable: { width: 524 },`;
const widthTo = `leagueTable: { width: 650 },`;
if (!ui.includes(widthFrom)) throw new Error('AJPA Liga zones: no encontré ancho de tabla');
ui = ui.replace(widthFrom, widthTo);

const styleAnchor = `  leaguePoints: { fontSize: 12, fontWeight: '900', textAlign: 'center' },\n`;
const zoneStyles = `  leagueZoneText: { fontSize: 8.2, fontWeight: '900', textAlign: 'center', paddingHorizontal: 4 },\n  leagueColZone: { width: 126 },\n`;
if (!ui.includes(styleAnchor)) throw new Error('AJPA Liga zones: no encontré estilos de tabla');
ui = ui.replace(styleAnchor, styleAnchor + zoneStyles);

for (const required of [
  '>ZONA</Text>',
  "'CAMPEÓN + CHAMPIONS'",
  "'CHAMPIONS LEAGUE'",
  "'EUROPA LEAGUE'",
  'leagueColZone: { width: 126 }',
  "apiRequest<any>('/api/v1/cups')",
]) {
  if (!ui.includes(required)) throw new Error(`AJPA Liga zones: falta ${required}`);
}

fs.writeFileSync(path, ui + '\n' + marker + '\n');
console.log('AJPA Liga: zonas sincronizadas con Champions League + Europa League y regla del campeón de Europa.');
