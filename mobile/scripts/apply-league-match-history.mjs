import fs from 'node:fs';

const uiPath = 'src/BotParityAppV2.tsx';
const apiPath = 'src/api.ts';

let api = fs.readFileSync(apiPath, 'utf8');

if (!api.includes('export type LeagueMatch = {')) {
  const marker = `export type LeagueData = {\n  standings: LeagueStanding[];\n  scorers: LeagueScorer[];\n};`;
  if (!api.includes(marker)) {
    throw new Error('AJPA Liga history: no encontré LeagueData en api.ts');
  }
  api = api.replace(
    marker,
    `export type LeagueMatch = {\n  id: number;\n  home_team: string;\n  away_team: string;\n  home_goals: number;\n  away_goals: number;\n  created_at: string;\n};\n\nexport type LeagueData = {\n  standings: LeagueStanding[];\n  scorers: LeagueScorer[];\n  matches: LeagueMatch[];\n};`,
  );
}
fs.writeFileSync(apiPath, api);

let ui = fs.readFileSync(uiPath, 'utf8');

function mustReplace(search, replacement, label) {
  if (!ui.includes(search)) throw new Error(`AJPA Liga history: no encontré ${label}`);
  ui = ui.replace(search, replacement);
}

if (!ui.includes("  | 'leagueHistory'")) {
  mustReplace("  | 'league'\n", "  | 'league'\n  | 'leagueHistory'\n", 'tipo Screen de Liga');
}

if (ui.includes("if (next === 'league') {")) {
  ui = ui.replace(
    "if (next === 'league') {",
    "if (next === 'league' || next === 'leagueHistory') {",
  );
}

if (!ui.includes('const myLeagueMatches =')) {
  const marker = `  const leagueScreen = (`;
  if (!ui.includes(marker)) throw new Error('AJPA Liga history: no encontré leagueScreen');
  const dataBlock = String.raw`  const leagueClubKey = String(profile?.club ?? '').trim().toLowerCase();
  const myLeagueMatches = (leagueData?.matches ?? []).filter((match) =>
    leagueClubKey && (
      String(match.home_team).trim().toLowerCase() === leagueClubKey ||
      String(match.away_team).trim().toLowerCase() === leagueClubKey
    ),
  );
  const leagueHistorySummary = myLeagueMatches.reduce(
    (acc, match) => {
      const isHome = String(match.home_team).trim().toLowerCase() === leagueClubKey;
      const gf = isHome ? Number(match.home_goals) : Number(match.away_goals);
      const gc = isHome ? Number(match.away_goals) : Number(match.home_goals);
      acc.gf += gf;
      acc.gc += gc;
      if (gf > gc) acc.pg += 1;
      else if (gf < gc) acc.pp += 1;
      else acc.pe += 1;
      return acc;
    },
    { pg: 0, pe: 0, pp: 0, gf: 0, gc: 0 },
  );

`;
  ui = ui.replace(marker, dataBlock + marker);
}

if (!ui.includes("title=\"HISTORIAL DE PARTIDOS\"")) {
  const standingsMarker = `      <Text style={s.listHeading}>🏆 TABLA DE POSICIONES</Text>`;
  if (!ui.includes(standingsMarker)) throw new Error('AJPA Liga history: no encontré tabla de Liga');
  const historyEntry = String.raw`      <WideTile
        emoji="📜"
        title="HISTORIAL DE PARTIDOS"
        subtitle="Rivales, marcadores y resultados de tu equipo"
        onPress={() => requireClub('leagueHistory')}
      />

`;
  ui = ui.replace(standingsMarker, historyEntry + standingsMarker);
}

if (!ui.includes('const leagueHistoryScreen =')) {
  const marker = `  const historyScreen = (`;
  if (!ui.includes(marker)) throw new Error('AJPA Liga history: no encontré historyScreen');
  const screen = String.raw`  const leagueHistoryScreen = (
    <ScrollView contentContainerStyle={s.content} refreshControl={refreshControl}>
      <Title
        eyebrow="LIGA · HISTORIAL"
        title="Historial de partidos"
        subtitle={profile?.club ? `Partidos oficiales de ${profile.club}` : 'Necesitás un club asignado'}
      />

      {profile?.club ? (
        <View style={[s.card, { borderColor: 'rgba(90,177,235,0.72)', backgroundColor: 'rgba(3,16,27,0.94)' }]}>
          <Text style={s.infoLabel}>RESUMEN</Text>
          <Text style={s.playerName}>{profile.club}</Text>
          <Text style={s.playerValue}>
            PJ {myLeagueMatches.length} · PG {leagueHistorySummary.pg} · PE {leagueHistorySummary.pe} · PP {leagueHistorySummary.pp}
          </Text>
          <Text style={s.muted}>GF {leagueHistorySummary.gf} · GC {leagueHistorySummary.gc}</Text>
        </View>
      ) : null}

      {profile?.club && myLeagueMatches.length === 0 ? (
        <View style={s.card}>
          <Text style={s.playerName}>Todavía no hay partidos oficiales</Text>
          <Text style={s.muted}>Cuando se cargue un resultado de Liga aparecerá automáticamente acá.</Text>
        </View>
      ) : null}

      {myLeagueMatches.map((match) => {
        const isHome = String(match.home_team).trim().toLowerCase() === leagueClubKey;
        const rival = isHome ? match.away_team : match.home_team;
        const gf = isHome ? Number(match.home_goals) : Number(match.away_goals);
        const gc = isHome ? Number(match.away_goals) : Number(match.home_goals);
        const won = gf > gc;
        const lost = gf < gc;
        const result = won ? 'VICTORIA' : lost ? 'DERROTA' : 'EMPATE';
        const resultColor = won ? C.green : lost ? C.red : '#aeb7c0';
        const resultBackground = won
          ? 'rgba(20,82,47,0.68)'
          : lost
            ? 'rgba(91,25,31,0.70)'
            : 'rgba(54,62,70,0.72)';
        const rawDate = String(match.created_at || '').slice(0, 10);
        const dateParts = rawDate.split('-');
        const dateText = dateParts.length === 3
          ? `${dateParts[2]}/${dateParts[1]}/${dateParts[0]}`
          : (rawDate || 'Sin fecha');

        return (
          <View
            key={match.id}
            style={[
              s.card,
              {
                borderWidth: 1.7,
                borderColor: resultColor,
                backgroundColor: resultBackground,
              },
            ]}
          >
            <View style={[s.playerRow, { alignItems: 'center' }]}>
              <View style={{ flex: 1 }}>
                <Text style={[s.statusTag, { color: resultColor }]}>
                  {won ? '🟢' : lost ? '🔴' : '⚪'} {result}
                </Text>
                <Text style={s.playerName}>vs {rival}</Text>
                <Text style={[s.playerValue, { fontSize: 19 }]}> {profile.club} {gf} — {gc} {rival}</Text>
                <Text style={[s.muted, { marginTop: 5 }]}>{dateText}</Text>
              </View>
            </View>
          </View>
        );
      })}
    </ScrollView>
  );

`;
  ui = ui.replace(marker, screen + marker);
}

if (!ui.includes("else if (screen === 'leagueHistory') body = leagueHistoryScreen;")) {
  mustReplace(
    `  else if (screen === 'league') body = leagueScreen;`,
    `  else if (screen === 'league') body = leagueScreen;\n  else if (screen === 'leagueHistory') body = leagueHistoryScreen;`,
    'despacho de pantalla Liga',
  );
}

if (ui.includes("if (screen === 'league') return BG_LIGA;")) {
  ui = ui.replace(
    "if (screen === 'league') return BG_LIGA;",
    "if (screen === 'league' || screen === 'leagueHistory') return BG_LIGA;",
  );
}
ui = ui.split("screen === 'league' && s.leagueShade").join(
  "(screen === 'league' || screen === 'leagueHistory') && s.leagueShade",
);

if (!ui.includes("title=\"HISTORIAL DE PARTIDOS\"")) throw new Error('AJPA Liga history: falta botón en Liga');
if (!ui.includes('const leagueHistoryScreen =')) throw new Error('AJPA Liga history: falta pantalla de historial');
if (!ui.includes("screen === 'leagueHistory'")) throw new Error('AJPA Liga history: falta navegación');

fs.writeFileSync(uiPath, ui);
console.log('AJPA Mobile Liga: historial oficial activo con verde/rojo/gris según resultado.');
