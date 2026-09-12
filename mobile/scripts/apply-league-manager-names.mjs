// OTA-safe: show the assigned Discord manager between club name and qualification.
import fs from 'node:fs';

const uiPath = new URL('../src/BotParityAppV2.tsx', import.meta.url);
const apiPath = new URL('../src/api.ts', import.meta.url);
let ui = fs.readFileSync(uiPath, 'utf8');
let api = fs.readFileSync(apiPath, 'utf8');
const marker = '// AJPA_LEAGUE_MANAGER_NAMES_V1';

if (!api.includes('manager_name?: string | null;')) {
  const apiAnchor = `export type LeagueStanding = {\n  team: string;`;
  if (!api.includes(apiAnchor)) {
    throw new Error('AJPA Liga DT: no encontré LeagueStanding en api.ts');
  }
  api = api.replace(
    apiAnchor,
    `export type LeagueStanding = {\n  team: string;\n  manager_name?: string | null;\n  manager_user_id?: string | null;`,
  );
  fs.writeFileSync(apiPath, api);
}

if (ui.includes(marker)) {
  process.exit(0);
}
if (!ui.includes('// league-real-table applied')) {
  throw new Error('AJPA Liga DT: aplicar primero la tabla real de Liga');
}

const teamAnchor = '<Text numberOfLines={1} style={s.leagueTeamName}>{row.team}</Text>';
if (!ui.includes(teamAnchor)) {
  throw new Error('AJPA Liga DT: no encontré el nombre del equipo en la tabla');
}
const managerLine = `${teamAnchor}\n                        <Text numberOfLines={1} style={s.leagueManagerName}>\n                          {row.manager_name ? 'DT: ' + row.manager_name : 'DT: Sin asignar'}\n                        </Text>`;
ui = ui.replace(teamAnchor, managerLine);

const styleAnchor = "  leagueTeamName: { color: C.white, fontSize: 11, fontWeight: '900' },\n";
if (!ui.includes(styleAnchor)) {
  throw new Error('AJPA Liga DT: no encontré leagueTeamName en los estilos');
}
ui = ui.replace(
  styleAnchor,
  styleAnchor + "  leagueManagerName: { color: '#a7b7c5', fontSize: 8, lineHeight: 10, fontWeight: '700', marginTop: 1 },\n",
);

for (const required of [
  'row.manager_name',
  's.leagueManagerName',
  's.leagueZoneInline',
]) {
  if (!ui.includes(required)) throw new Error(`AJPA Liga DT: falta ${required}`);
}

fs.writeFileSync(uiPath, ui + '\n' + marker + '\n');
console.log('AJPA Liga: equipo → DT asignado → clasificación.');
