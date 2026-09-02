// OTA-safe Liga theming: reutiliza exclusivamente assets y temas ya aprobados.
import fs from 'node:fs';

const path = new URL('../src/BotParityAppV2.tsx', import.meta.url);
let ui = fs.readFileSync(path, 'utf8');
const marker = '// league-team-card-colors applied';
if (ui.includes(marker)) process.exit(0);

if (!ui.includes('// club-player-card-colors applied')) {
  throw new Error('AJPA Liga cards: aplicar primero club-player-card-colors');
}
if (!ui.includes('const leagueScreen = (')) {
  throw new Error('AJPA Liga cards: no encontré leagueScreen');
}

const start = ui.indexOf('  const leagueScreen = (');
const end = ui.indexOf('\n  const ', start + 10);
if (start < 0 || end < 0) throw new Error('AJPA Liga cards: no pude aislar leagueScreen');

let league = ui.slice(start, end);

const oldStanding = `<View style={s.card} key={row.team}>\n          <View style={s.playerRow}>\n            <View style={s.ovrBox}><Text style={s.ovrValue}>{index + 1}</Text><Text style={s.ovrLabel}>POS</Text></View>\n            <View style={s.flex}>\n              <Text style={s.playerName}>{row.team}</Text>\n              <Text style={s.muted}>PJ {row.pj} · PG {row.pg} · PE {row.pe} · PP {row.pp}</Text>\n              <Text style={s.playerValue}>GF {row.gf} · GC {row.gc} · DIF {row.dg >= 0 ? '+' : ''}{row.dg}</Text>\n            </View>\n            <Text style={s.price}>{row.pts} pts</Text>\n          </View>\n        </View>`;

const newStanding = `<View style={[s.card, clubCardStyle(row.team)]} key={row.team}>\n          <TeamCardBackdrop club={row.team} />\n          <View style={s.playerRow}>\n            <View style={[s.ovrBox, clubCardStyle(row.team), { backgroundColor: 'transparent' }]}>\n              <SoftCardGlow color={teamCardTheme(row.team).color} opacity={0.3} />\n              <Text style={[s.ovrValue, { color: teamCardTheme(row.team).border }]}>{index + 1}</Text>\n              <Text style={s.ovrLabel}>POS</Text>\n            </View>\n            <ClubBadge club={row.team} size={46} style={{ marginRight: 11 }} />\n            <View style={s.flex}>\n              <Text style={s.playerName}>{row.team}</Text>\n              <Text style={s.muted}>PJ {row.pj} · PG {row.pg} · PE {row.pe} · PP {row.pp}</Text>\n              <Text style={[s.playerValue, { color: teamCardTheme(row.team).border }]}>GF {row.gf} · GC {row.gc} · DIF {row.dg >= 0 ? '+' : ''}{row.dg}</Text>\n            </View>\n            <Text style={[s.price, { color: teamCardTheme(row.team).border }]}>{row.pts} pts</Text>\n          </View>\n        </View>`;

if (!league.includes(oldStanding)) {
  throw new Error('AJPA Liga cards: no encontré la tarjeta actual de posiciones');
}
league = league.replace(oldStanding, newStanding);

const oldScorer = `<View style={s.card} key={row.player + '-' + row.team}>\n          <Text style={s.playerName}>{index + 1}. {row.player}</Text>\n          <Text style={s.muted}>{row.team || 'Sin club'}</Text>\n          <Text style={s.playerValue}>⚽ {row.goals} goles</Text>\n        </View>`;

const newScorer = `<View style={[s.card, clubCardStyle(row.team)]} key={row.player + '-' + row.team}>\n          {row.team ? <TeamCardBackdrop club={row.team} /> : null}\n          <View style={s.playerRow}>\n            {row.team ? <ClubBadge club={row.team} size={42} style={{ marginRight: 11 }} /> : null}\n            <View style={s.flex}>\n              <Text style={s.playerName}>{index + 1}. {row.player}</Text>\n              <Text style={s.muted}>{row.team || 'Sin club'}</Text>\n              <Text style={[s.playerValue, row.team ? { color: teamCardTheme(row.team).border } : null]}>⚽ {row.goals} goles</Text>\n            </View>\n          </View>\n        </View>`;

if (!league.includes(oldScorer)) {
  throw new Error('AJPA Liga cards: no encontré la tarjeta actual de goleadores');
}
league = league.replace(oldScorer, newScorer);

// A bundled APK must not produce a false positive in the OTA smoke test.
const heading = '<Text style={s.listHeading}>🏆 TABLA DE POSICIONES</Text>';
if (!league.includes(heading)) throw new Error('AJPA OTA test: missing standings heading');
league = league.replace(heading, `{Updates.isEnabled && !Updates.isEmbeddedLaunch && Updates.updateId ? (
        <View style={{ backgroundColor: '#123c28', borderColor: '#55e595', borderWidth: 1, borderRadius: 12, padding: 12 }}>
          <Text style={{ color: '#b9ffd5', fontSize: 16, fontWeight: '700' }}>🟢 Actualización de prueba 01 recibida</Text>
        </View>
      ) : null}
      ${heading}`);

ui = ui.slice(0, start) + league + ui.slice(end);
ui = "import * as Updates from 'expo-updates';\n" + ui;

for (const required of [
  '<TeamCardBackdrop club={row.team} />',
  '<ClubBadge club={row.team} size={46}',
  'teamCardTheme(row.team).border',
]) {
  if (!ui.includes(required)) throw new Error(`AJPA Liga cards: falta ${required}`);
}

fs.writeFileSync(path, ui + '\n' + marker + '\n');
console.log('AJPA Liga: tabla y goleadores usan diseño visual del club sin modificar escudos.');
