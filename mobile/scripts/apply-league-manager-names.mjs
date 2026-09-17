// OTA-safe: show the real assigned Discord manager between club name and qualification.
// The league endpoint does not always include manager_name, so the table also uses
// the same /clubs/profiles assignment source that powers the Staff "Equipos y DTs" view.
import fs from 'node:fs';

const uiPath = new URL('../src/BotParityAppV2.tsx', import.meta.url);
const apiPath = new URL('../src/api.ts', import.meta.url);
let ui = fs.readFileSync(uiPath, 'utf8');
let api = fs.readFileSync(apiPath, 'utf8');
const marker = '// AJPA_LEAGUE_MANAGER_NAMES_V2';

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
if (!ui.includes('const [clubProfiles, setClubProfiles]')) {
  throw new Error('AJPA Liga DT: falta el estado real de perfiles de clubes');
}
if (!ui.includes('fetchClubProfiles')) {
  throw new Error('AJPA Liga DT: falta fetchClubProfiles');
}

// Keep the assignment source fresh on app load/refresh. This is deliberately
// non-blocking: if profiles are temporarily unavailable, Liga still opens and can
// fall back to manager_name from the league response.
const loadAnchor = `      const snap = await fetchSnapshot();\n      setSnapshot(snap);`;
const profileLoad = `${loadAnchor}\n      try {\n        setClubProfiles(await fetchClubProfiles());\n      } catch {\n        // Keep the last known assignments if the public club-profile feed is unavailable.\n      }`;
if (!ui.includes('setClubProfiles(await fetchClubProfiles())')) {
  if (!ui.includes(loadAnchor)) {
    throw new Error('AJPA Liga DT: no encontré loadAll/fetchSnapshot');
  }
  ui = ui.replace(loadAnchor, profileLoad);
}

// Resolve the DT by club name from the real club-profile assignment feed. The
// case-insensitive trim avoids false "Sin asignar" values caused by casing/spaces.
const standingsMapAnchor = `{leagueData.standings.map((row, index) => {`;
if (!ui.includes(standingsMapAnchor)) {
  throw new Error('AJPA Liga DT: no encontré el map de la tabla real');
}
if (!ui.includes('const assignedManagerName = clubProfiles.find')) {
  ui = ui.replace(
    standingsMapAnchor,
    `${standingsMapAnchor}\n                const rowManagerKey = row.team.trim().toLocaleLowerCase('es');\n                const assignedManagerName = clubProfiles.find((club) => {\n                  const clubManagerKey = club.club.trim().toLocaleLowerCase('es');\n                  if (clubManagerKey === rowManagerKey) return true;\n                  const betisAliases = ['betis', 'real betis'];\n                  return betisAliases.includes(clubManagerKey) && betisAliases.includes(rowManagerKey);\n                })?.manager?.name || row.manager_name || '';`,
  );
}

const teamAnchor = '<Text numberOfLines={1} style={s.leagueTeamName}>{row.team}</Text>';
if (!ui.includes(teamAnchor)) {
  throw new Error('AJPA Liga DT: no encontré el nombre del equipo en la tabla');
}
const managerLine = `${teamAnchor}\n                        <Text numberOfLines={1} style={s.leagueManagerName}>\n                          {assignedManagerName ? 'DT: ' + assignedManagerName : 'DT: Sin asignar'}\n                        </Text>`;
ui = ui.replace(teamAnchor, managerLine);

const styleAnchor = "  leagueTeamName: { color: C.white, fontSize: 11, fontWeight: '900' },\n";
if (!ui.includes(styleAnchor)) {
  throw new Error('AJPA Liga DT: no encontré leagueTeamName en los estilos');
}
if (!ui.includes('leagueManagerName:')) {
  ui = ui.replace(
    styleAnchor,
    styleAnchor + "  leagueManagerName: { color: '#a7b7c5', fontSize: 8, lineHeight: 10, fontWeight: '700', marginTop: 1 },\n",
  );
}

for (const required of [
  'assignedManagerName',
  'clubProfiles.find',
  'setClubProfiles(await fetchClubProfiles())',
  's.leagueManagerName',
  's.leagueZoneInline',
]) {
  if (!ui.includes(required)) throw new Error(`AJPA Liga DT: falta ${required}`);
}

fs.writeFileSync(uiPath, ui + '\n' + marker + '\n');
console.log('AJPA Liga: nombres de DT sincronizados con las asignaciones reales de clubes.');
