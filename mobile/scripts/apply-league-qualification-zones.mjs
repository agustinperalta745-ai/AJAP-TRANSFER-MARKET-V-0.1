// OTA-safe qualification zones for the real Liga standings table.
import fs from 'node:fs';

const path = new URL('../src/BotParityAppV2.tsx', import.meta.url);
let ui = fs.readFileSync(path, 'utf8');
const marker = '// league-qualification-zones applied';
if (ui.includes(marker)) process.exit(0);

if (!ui.includes('// league-real-table applied')) {
  throw new Error('AJPA Liga zones: aplicar primero league-real-table');
}

const headerFrom = `<Text style={[s.leagueHeaderText, s.leagueColPoints]}>PTS</Text>`;
const headerTo = `${headerFrom}\n                <Text style={[s.leagueHeaderText, s.leagueColZone]}>ZONA</Text>`;
if (!ui.includes(headerFrom)) throw new Error('AJPA Liga zones: no encontré encabezado PTS');
ui = ui.replace(headerFrom, headerTo);

const pointsFrom = `<Text style={[s.leaguePoints, s.leagueColPoints, { color: teamCardTheme(row.team).border }]}>{row.pts}</Text>`;
const pointsTo = `${pointsFrom}\n                  <Text\n                    numberOfLines={1}\n                    style={[\n                      s.leagueZoneText,\n                      s.leagueColZone,\n                      { color: index === 0 ? '#f2c94c' : index <= 10 ? '#66a7ff' : index <= 23 ? '#72d9c7' : '#718596' },\n                    ]}\n                  >\n                    {index === 0 ? 'CAMPEÓN + COPA 1' : index <= 10 ? 'COPA 1' : index <= 23 ? 'COPA 2' : '—'}\n                  </Text>`;
if (!ui.includes(pointsFrom)) throw new Error('AJPA Liga zones: no encontré celda de puntos');
ui = ui.replace(pointsFrom, pointsTo);

const widthFrom = `leagueTable: { width: 524 },`;
const widthTo = `leagueTable: { width: 640 },`;
if (!ui.includes(widthFrom)) throw new Error('AJPA Liga zones: no encontré ancho de tabla');
ui = ui.replace(widthFrom, widthTo);

const styleAnchor = `  leaguePoints: { fontSize: 12, fontWeight: '900', textAlign: 'center' },\n`;
const zoneStyles = `  leagueZoneText: { fontSize: 8.5, fontWeight: '900', textAlign: 'center', paddingHorizontal: 4 },\n  leagueColZone: { width: 116 },\n`;
if (!ui.includes(styleAnchor)) throw new Error('AJPA Liga zones: no encontré estilos de tabla');
ui = ui.replace(styleAnchor, styleAnchor + zoneStyles);

for (const required of [
  '>ZONA</Text>',
  "'CAMPEÓN + COPA 1'",
  "'COPA 1'",
  "'COPA 2'",
  'leagueColZone: { width: 116 }',
]) {
  if (!ui.includes(required)) throw new Error(`AJPA Liga zones: falta ${required}`);
}

fs.writeFileSync(path, ui + '\n' + marker + '\n');
console.log('AJPA Liga: zonas aplicadas — 1 Campeón + Copa 1; 2-11 Copa 1; 12-24 Copa 2.');
