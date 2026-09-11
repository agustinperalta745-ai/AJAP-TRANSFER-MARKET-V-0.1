import fs from 'node:fs';

const apiPath = 'src/api.ts';
const appPath = 'src/BotParityAppV2.tsx';

let api = fs.readFileSync(apiPath, 'utf8');

if (!api.includes('export type LatestHonours =')) {
  const anchor = `export type LeagueData = {\n  standings: LeagueStanding[];\n  scorers: LeagueScorer[];\n};\n`;
  if (!api.includes(anchor)) throw new Error('Latest honours: LeagueData type anchor not found');
  api = api.replace(anchor, `${anchor}\nexport type HonoursManager = {\n  user_id: string | null;\n  username: string;\n};\n\nexport type LatestChampion = {\n  competition_id: number;\n  competition: string;\n  kind: string;\n  team: string;\n  manager: HonoursManager;\n};\n\nexport type LatestTopScorer = {\n  competition_id: number;\n  competition: string;\n  player: string;\n  goals: number;\n  team: string;\n  manager: HonoursManager;\n};\n\nexport type LatestHonours = {\n  season_champion: LatestChampion | null;\n  top_scorer: LatestTopScorer | null;\n  cup_champion: LatestChampion | null;\n};\n`);
}

if (!api.includes('export function fetchLatestHonours()')) {
  const anchor = `export async function fetchLeague(): Promise<LeagueData> {\n  return normalizeLeagueData(await apiRequest<LeagueData>('/api/v1/league'));\n}\n`;
  if (!api.includes(anchor)) throw new Error('Latest honours: fetchLeague anchor not found');
  api = api.replace(anchor, `${anchor}\nexport function fetchLatestHonours(): Promise<LatestHonours> {\n  return apiRequest<LatestHonours>('/api/v1/league/latest-honours');\n}\n`);
}

fs.writeFileSync(apiPath, api);

let app = fs.readFileSync(appPath, 'utf8');

if (!app.includes('LatestHonours,')) {
  const anchor = `  LeagueSnapshot,\n`;
  if (!app.includes(anchor)) throw new Error('Latest honours: import type anchor not found');
  app = app.replace(anchor, `  LatestHonours,\n${anchor}`);
}

if (!app.includes('fetchLatestHonours,')) {
  const anchor = `  fetchMe,\n`;
  if (!app.includes(anchor)) throw new Error('Latest honours: fetch import anchor not found');
  app = app.replace(anchor, `  fetchLatestHonours,\n${anchor}`);
}

if (!app.includes('const [latestHonours, setLatestHonours]')) {
  const anchor = `  const [snapshot, setSnapshot] = useState<LeagueSnapshot | null>(null);\n`;
  if (!app.includes(anchor)) throw new Error('Latest honours: state anchor not found');
  app = app.replace(anchor, `${anchor}  const [latestHonours, setLatestHonours] = useState<LatestHonours | null>(null);\n`);
}

if (!app.includes('setLatestHonours(await fetchLatestHonours())')) {
  const anchor = `      const snap = await fetchSnapshot();\n      setSnapshot(snap);\n`;
  if (!app.includes(anchor)) throw new Error('Latest honours: loadAll anchor not found');
  app = app.replace(anchor, `${anchor}      try {\n        setLatestHonours(await fetchLatestHonours());\n      } catch {\n        // The home menu stays usable even if the compact historical feed is temporarily unavailable.\n        setLatestHonours(null);\n      }\n`);
}

const honoursBlock = `      <View style={s.honoursWrap}>\n        <Text style={s.honoursHeading}>🏅 ÚLTIMOS LOGROS</Text>\n        <View style={s.honoursRow}>\n          <View style={s.honourCard}>\n            <Text style={s.honourLabel}>🏆 CAMPEÓN</Text>\n            {latestHonours?.season_champion ? (\n              <>\n                <Text numberOfLines={1} style={s.honourPrimary}>{latestHonours.season_champion.team}</Text>\n                <Text numberOfLines={1} style={s.honourSecondary}>DT · {latestHonours.season_champion.manager.username}</Text>\n                <Text numberOfLines={1} style={s.honourMeta}>{latestHonours.season_champion.competition}</Text>\n              </>\n            ) : (\n              <Text style={s.honourEmpty}>Sin campeón registrado</Text>\n            )}\n          </View>\n\n          <View style={s.honourCard}>\n            <Text style={s.honourLabel}>⚽ GOLEADOR</Text>\n            {latestHonours?.top_scorer ? (\n              <>\n                <Text numberOfLines={1} style={s.honourPrimary}>{latestHonours.top_scorer.player}</Text>\n                <Text numberOfLines={1} style={s.honourSecondary}>{latestHonours.top_scorer.goals} goles · {latestHonours.top_scorer.team}</Text>\n                <Text numberOfLines={1} style={s.honourMeta}>DT · {latestHonours.top_scorer.manager.username}</Text>\n              </>\n            ) : (\n              <Text style={s.honourEmpty}>Sin goleador registrado</Text>\n            )}\n          </View>\n\n          <View style={s.honourCard}>\n            <Text style={s.honourLabel}>🏆 COPA</Text>\n            {latestHonours?.cup_champion ? (\n              <>\n                <Text numberOfLines={1} style={s.honourPrimary}>{latestHonours.cup_champion.team}</Text>\n                <Text numberOfLines={1} style={s.honourSecondary}>DT · {latestHonours.cup_champion.manager.username}</Text>\n                <Text numberOfLines={1} style={s.honourMeta}>{latestHonours.cup_champion.competition}</Text>\n              </>\n            ) : (\n              <>\n                <Text style={s.honourEmpty}>Sin campeón todavía</Text>\n                <Text style={s.honourMeta}>Aún no se jugó copa</Text>\n              </>\n            )}\n          </View>\n        </View>\n      </View>\n\n`;

if (!app.includes('s.honoursWrap')) {
  const homeStart = app.indexOf(`  const home = (`);
  const homeEnd = app.indexOf(`  const clubMenu = (`, homeStart + 1);
  if (homeStart < 0 || homeEnd < 0) throw new Error('Latest honours: home block not found');

  const approvedAnchor = `      <SectionLabel title="⚡ ACCIONES RÁPIDAS" />`;
  const approvedPos = app.indexOf(approvedAnchor, homeStart);
  if (approvedPos >= 0 && approvedPos < homeEnd) {
    app = app.slice(0, approvedPos) + honoursBlock + app.slice(approvedPos);
  } else {
    const legacyAnchor = `      <View style={[s.marketState, snapshot.status.market_open ? s.marketOpen : s.marketClosed]}>\n        <Text style={s.marketStateText}>{snapshot.status.market_open ? '🟢 MERCADO ABIERTO' : '🔒 MERCADO CERRADO'}</Text>\n      </View>\n\n`;
    const legacyPos = app.indexOf(legacyAnchor, homeStart);
    if (legacyPos < 0 || legacyPos >= homeEnd) throw new Error('Latest honours: no safe insertion point in home');
    const insertAt = legacyPos + legacyAnchor.length;
    app = app.slice(0, insertAt) + honoursBlock + app.slice(insertAt);
  }
}

if (!app.includes('honoursWrap:')) {
  const styles = `  honoursWrap: { gap: 6, marginTop: 1, marginBottom: 1 },\n  honoursHeading: { color: C.blueSoft, fontSize: 8, fontWeight: '900', letterSpacing: 1.2 },\n  honoursRow: { flexDirection: 'row', gap: 7 },\n  honourCard: { flex: 1, minWidth: 0, minHeight: 96, backgroundColor: 'rgba(7,17,27,0.88)', borderWidth: 1, borderColor: '#274157', borderRadius: 13, paddingHorizontal: 9, paddingVertical: 9 },\n  honourLabel: { color: C.blueSoft, fontSize: 7.5, fontWeight: '900', letterSpacing: 0.7, marginBottom: 6 },\n  honourPrimary: { color: C.white, fontSize: 10.5, fontWeight: '900', lineHeight: 13 },\n  honourSecondary: { color: '#c4d1dc', fontSize: 8.5, fontWeight: '700', lineHeight: 12, marginTop: 4 },\n  honourMeta: { color: C.muted, fontSize: 7.5, lineHeight: 10, marginTop: 4 },\n  honourEmpty: { color: '#c4d1dc', fontSize: 9, fontWeight: '700', lineHeight: 12, marginTop: 2 },\n`;
  const styleClose = app.lastIndexOf('\n});');
  if (styleClose < 0) throw new Error('Latest honours: style block close not found');
  app = app.slice(0, styleClose) + `\n${styles}` + app.slice(styleClose);
}

fs.writeFileSync(appPath, app);
console.log('AJPA Mobile: compact latest honours strip applied');