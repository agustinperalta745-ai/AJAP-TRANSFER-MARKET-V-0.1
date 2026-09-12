// OTA-safe Liga presentation: real football standings table + approved AJPA badges/themes.
import fs from 'node:fs';

const path = new URL('../src/BotParityAppV2.tsx', import.meta.url);
let ui = fs.readFileSync(path, 'utf8');
const marker = '// league-real-table applied';
if (ui.includes(marker)) process.exit(0);

if (!ui.includes('// club-player-card-colors applied')) {
  throw new Error('AJPA Liga table: aplicar primero club-player-card-colors');
}
if (!ui.includes('const leagueScreen = (')) {
  throw new Error('AJPA Liga table: no encontré leagueScreen');
}

const start = ui.indexOf('  const leagueScreen = (');
const end = ui.indexOf('\n  const ', start + 10);
if (start < 0 || end < 0) throw new Error('AJPA Liga table: no pude aislar leagueScreen');

let league = ui.slice(start, end);

const oldStandings = `      <Text style={s.listHeading}>🏆 TABLA DE POSICIONES</Text>\n      {!leagueData ? <ActivityIndicator color={C.blue} /> : null}\n      {leagueData?.standings.length === 0 ? <View style={s.card}><Text style={s.muted}>Todavía no hay equipos en la tabla.</Text></View> : null}\n      {leagueData?.standings.map((row, index) => (\n        <View style={s.card} key={row.team}>\n          <View style={s.playerRow}>\n            <View style={s.ovrBox}><Text style={s.ovrValue}>{index + 1}</Text><Text style={s.ovrLabel}>POS</Text></View>\n            <View style={s.flex}>\n              <Text style={s.playerName}>{row.team}</Text>\n              <Text style={s.muted}>PJ {row.pj} · PG {row.pg} · PE {row.pe} · PP {row.pp}</Text>\n              <Text style={s.playerValue}>GF {row.gf} · GC {row.gc} · DIF {row.dg >= 0 ? '+' : ''}{row.dg}</Text>\n            </View>\n            <Text style={s.price}>{row.pts} pts</Text>\n          </View>\n        </View>\n      ))}`;

const newStandings = `      <Text style={s.listHeading}>🏆 TABLA DE POSICIONES</Text>\n      {!leagueData ? <ActivityIndicator color={C.blue} /> : null}\n      {leagueData?.standings.length === 0 ? <View style={s.card}><Text style={s.muted}>Todavía no hay equipos en la tabla.</Text></View> : null}\n      {leagueData && leagueData.standings.length > 0 ? (\n        <View style={s.leagueTableShell}>\n          <Text style={s.leagueSwipeHint}>Deslizá ↔ para ver todas las estadísticas</Text>\n          <ScrollView\n            horizontal\n            showsHorizontalScrollIndicator\n            contentContainerStyle={s.leagueTableScroller}\n          >\n            <View style={s.leagueTable}>\n              <View style={s.leagueTableHeader}>\n                <Text style={[s.leagueHeaderText, s.leagueColPosition]}>#</Text>\n                <Text style={[s.leagueHeaderText, s.leagueTeamHeader]}>EQUIPO</Text>\n                <Text style={[s.leagueHeaderText, s.leagueColSmall]}>PJ</Text>\n                <Text style={[s.leagueHeaderText, s.leagueColSmall]}>PG</Text>\n                <Text style={[s.leagueHeaderText, s.leagueColSmall]}>PE</Text>\n                <Text style={[s.leagueHeaderText, s.leagueColSmall]}>PP</Text>\n                <Text style={[s.leagueHeaderText, s.leagueColSmall]}>GF</Text>\n                <Text style={[s.leagueHeaderText, s.leagueColSmall]}>GC</Text>\n                <Text style={[s.leagueHeaderText, s.leagueColDiff]}>DG</Text>\n                <Text style={[s.leagueHeaderText, s.leagueColPoints]}>PTS</Text>\n              </View>\n              {leagueData.standings.map((row, index) => (\n                <View\n                  key={row.team}\n                  style={[\n                    s.leagueTableRow,\n                    {\n                      borderLeftColor: teamCardTheme(row.team).border,\n                      backgroundColor: index % 2 === 0 ? 'rgba(8,18,28,0.92)' : 'rgba(12,25,37,0.92)',\n                    },\n                  ]}\n                >\n                  <Text style={[s.leagueCellText, s.leaguePosition, s.leagueColPosition]}>{index + 1}</Text>\n                  <View style={s.leagueTeamCell}>\n                    <ClubBadge club={row.team} size={26} style={s.leagueTeamBadge} />\n                    <Text numberOfLines={1} style={s.leagueTeamName}>{row.team}</Text>\n                  </View>\n                  <Text style={[s.leagueCellText, s.leagueColSmall]}>{row.pj}</Text>\n                  <Text style={[s.leagueCellText, s.leagueColSmall]}>{row.pg}</Text>\n                  <Text style={[s.leagueCellText, s.leagueColSmall]}>{row.pe}</Text>\n                  <Text style={[s.leagueCellText, s.leagueColSmall]}>{row.pp}</Text>\n                  <Text style={[s.leagueCellText, s.leagueColSmall]}>{row.gf}</Text>\n                  <Text style={[s.leagueCellText, s.leagueColSmall]}>{row.gc}</Text>\n                  <Text style={[s.leagueCellText, s.leagueColDiff]}>{row.dg > 0 ? '+' : ''}{row.dg}</Text>\n                  <Text style={[s.leaguePoints, s.leagueColPoints, { color: teamCardTheme(row.team).border }]}>{row.pts}</Text>\n                </View>\n              ))}\n            </View>\n          </ScrollView>\n        </View>\n      ) : null}`;

if (!league.includes(oldStandings)) {
  throw new Error('AJPA Liga table: no encontré el bloque actual de posiciones');
}
league = league.replace(oldStandings, newStandings);

const oldScorer = `<View style={s.card} key={row.player + '-' + row.team}>\n          <Text style={s.playerName}>{index + 1}. {row.player}</Text>\n          <Text style={s.muted}>{row.team || 'Sin club'}</Text>\n          <Text style={s.playerValue}>⚽ {row.goals} goles</Text>\n        </View>`;

const newScorer = `<View style={[s.card, clubCardStyle(row.team)]} key={row.player + '-' + row.team}>\n          {row.team ? <TeamCardBackdrop club={row.team} /> : null}\n          <View style={s.playerRow}>\n            {row.team ? <ClubBadge club={row.team} size={42} style={{ marginRight: 11 }} /> : null}\n            <View style={s.flex}>\n              <Text style={s.playerName}>{index + 1}. {row.player}</Text>\n              <Text style={s.muted}>{row.team || 'Sin club'}</Text>\n              <Text style={[s.playerValue, row.team ? { color: teamCardTheme(row.team).border } : null]}>⚽ {row.goals} goles</Text>\n            </View>\n          </View>\n        </View>`;

if (!league.includes(oldScorer)) {
  throw new Error('AJPA Liga table: no encontré la tarjeta actual de goleadores');
}
league = league.replace(oldScorer, newScorer);
ui = ui.slice(0, start) + league + ui.slice(end);

const styleAnchor = `const s = StyleSheet.create({\n`;
if (!ui.includes(styleAnchor)) {
  throw new Error('AJPA Liga table: no encontré StyleSheet.create');
}

const leagueStyles = `  leagueTableShell: { backgroundColor: 'rgba(5,13,21,0.94)', borderWidth: 1, borderColor: '#263b4d', borderRadius: 14, overflow: 'hidden' },\n  leagueSwipeHint: { color: '#718596', fontSize: 9, fontWeight: '700', paddingHorizontal: 10, paddingTop: 8, paddingBottom: 5 },\n  leagueTableScroller: { paddingBottom: 2 },\n  leagueTable: { width: 524 },\n  leagueTableHeader: { minHeight: 34, flexDirection: 'row', alignItems: 'center', backgroundColor: '#0d1d2a', borderTopWidth: 1, borderTopColor: '#1d3447', borderBottomWidth: 1, borderBottomColor: '#31495c' },\n  leagueTableRow: { minHeight: 48, flexDirection: 'row', alignItems: 'center', borderLeftWidth: 3, borderBottomWidth: 1, borderBottomColor: '#182c3b' },\n  leagueHeaderText: { color: '#8fa6b8', fontSize: 8.5, fontWeight: '900', textAlign: 'center', letterSpacing: 0.45 },\n  leagueCellText: { color: '#d6e1e9', fontSize: 11, fontWeight: '700', textAlign: 'center' },\n  leaguePosition: { color: C.white, fontWeight: '900' },\n  leagueTeamHeader: { width: 170, textAlign: 'left', paddingLeft: 8 },\n  leagueTeamCell: { width: 170, minWidth: 170, flexDirection: 'row', alignItems: 'center', paddingHorizontal: 8 },\n  leagueTeamBadge: { marginRight: 8 },\n  leagueTeamName: { flex: 1, minWidth: 0, color: C.white, fontSize: 11, fontWeight: '900' },\n  leagueColPosition: { width: 34 },\n  leagueColSmall: { width: 38 },\n  leagueColDiff: { width: 44 },\n  leagueColPoints: { width: 48 },\n  leaguePoints: { fontSize: 12, fontWeight: '900', textAlign: 'center' },\n`;
ui = ui.replace(styleAnchor, styleAnchor + leagueStyles);

for (const required of [
  '// league-real-table applied',
  's.leagueTableHeader',
  '<ClubBadge club={row.team} size={26}',
  '>PTS</Text>',
  'teamCardTheme(row.team).border',
]) {
  if (required === '// league-real-table applied') continue;
  if (!ui.includes(required)) throw new Error(`AJPA Liga table: falta ${required}`);
}

fs.writeFileSync(
  path,
  ui + '\n// league-team-card-colors applied\n' + marker + '\n',
);
console.log('AJPA Liga: clasificación convertida a tabla real de fútbol; goleadores mantienen tarjetas tematizadas.');