import fs from 'node:fs';

const uiPath = new URL('../src/BotParityAppV2.tsx', import.meta.url);
let ui = fs.readFileSync(uiPath, 'utf8');

const PATCH_MARKER = 'AJPA_PLAYER_RECORD_CARD_V1';
if (ui.includes(PATCH_MARKER)) {
  console.log('AJPA player record card: ya estaba aplicada.');
  process.exit(0);
}

function requireMarker(condition, label) {
  if (!condition) throw new Error(`AJPA player record card: no encontré ${label}`);
}

// Mantener las estadísticas competitivas disponibles desde que abre Inicio,
// no solamente después de entrar manualmente a la pantalla de Liga.
const loadAllStart = ui.indexOf('  const loadAll = useCallback');
requireMarker(loadAllStart >= 0, 'loadAll');
const snapshotMarker = '      setSnapshot(snap);';
const snapshotPos = ui.indexOf(snapshotMarker, loadAllStart);
requireMarker(snapshotPos >= 0, 'setSnapshot dentro de loadAll');
const afterSnapshot = snapshotPos + snapshotMarker.length;
if (!ui.slice(afterSnapshot, afterSnapshot + 220).includes('setLeagueData(await fetchLeague())')) {
  ui = ui.slice(0, afterSnapshot)
    + "\n      try { setLeagueData(await fetchLeague()); } catch { setLeagueData(null); }"
    + ui.slice(afterSnapshot);
}

requireMarker(ui.includes('const [leagueData, setLeagueData]'), 'estado leagueData');
requireMarker(ui.includes('fetchLeague'), 'fetchLeague');

const wideTileMarker = '\nfunction WideTile({';
const wideTilePos = ui.indexOf(wideTileMarker);
requireMarker(wideTilePos >= 0, 'WideTile');

const recordComponent = String.raw`
// ${PATCH_MARKER}
function PlayerRecordCard({
  played,
  wins,
  draws,
  losses,
}: {
  played: number;
  wins: number;
  draws: number;
  losses: number;
}) {
  const stats = [
    { emoji: '🏆', value: wins, label: 'GANADOS' },
    { emoji: '🤝', value: draws, label: 'EMPATADOS' },
    { emoji: '❌', value: losses, label: 'PERDIDOS' },
  ];

  return (
    <View style={s.playerRecordCard}>
      <View style={s.playerRecordHeader}>
        <View>
          <Text style={s.playerRecordEyebrow}>TU RENDIMIENTO</Text>
          <Text style={s.playerRecordTitle}>Partidos jugados</Text>
        </View>
        <View style={s.playerRecordPlayedPill}>
          <Text style={s.playerRecordPlayedValue}>{played}</Text>
          <Text style={s.playerRecordPlayedLabel}>PJ</Text>
        </View>
      </View>

      <View style={s.playerRecordStatsRow}>
        {stats.map((stat) => (
          <View style={s.playerRecordStat} key={stat.label}>
            <Text style={s.playerRecordEmoji}>{stat.emoji}</Text>
            <Text style={s.playerRecordValue}>{stat.value}</Text>
            <Text style={s.playerRecordLabel}>{stat.label}</Text>
          </View>
        ))}
      </View>
    </View>
  );
}
`;
ui = ui.slice(0, wideTilePos) + recordComponent + ui.slice(wideTilePos);

const homeMarker = '  const home = (';
const homePos = ui.indexOf(homeMarker);
requireMarker(homePos >= 0, 'pantalla Inicio');

const recordLogic = String.raw`  const recordTeamKey = (value: string | null | undefined) => {
    const key = String(value ?? '')
      .normalize('NFD')
      .replace(/[\u0300-\u036f]/g, '')
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, ' ')
      .trim();
    return ['psg', 'paris saint germain', 'paris saint germain psg', 'paris saint germain fc'].includes(key)
      ? 'paris saint germain'
      : key;
  };
  const myLeagueRecord = profile?.club
    ? leagueData?.standings.find((row) => recordTeamKey(row.team) === recordTeamKey(profile.club)) ?? null
    : null;

`;
ui = ui.slice(0, homePos) + recordLogic + ui.slice(homePos);

const updatedHomePos = ui.indexOf(homeMarker);
const clubMenuPos = ui.indexOf('  const clubMenu = (', updatedHomePos);
requireMarker(clubMenuPos > updatedHomePos, 'fin de Inicio');
const heroPos = ui.indexOf('<HeroClubCard', updatedHomePos);
requireMarker(heroPos >= 0 && heroPos < clubMenuPos, 'tarjeta principal de Tu Club en Inicio');
const heroClose = ui.indexOf('/>', heroPos);
requireMarker(heroClose >= 0 && heroClose < clubMenuPos, 'cierre de HeroClubCard');
const insertAfterHero = heroClose + 2;

const recordCardUsage = String.raw`

      {profile?.club ? (
        <PlayerRecordCard
          played={myLeagueRecord?.pj ?? 0}
          wins={myLeagueRecord?.pg ?? 0}
          draws={myLeagueRecord?.pe ?? 0}
          losses={myLeagueRecord?.pp ?? 0}
        />
      ) : null}`;
ui = ui.slice(0, insertAfterHero) + recordCardUsage + ui.slice(insertAfterHero);

const styleClose = '\n});';
const stylePos = ui.lastIndexOf(styleClose);
requireMarker(stylePos >= 0, 'cierre de StyleSheet');
const recordStyles = String.raw`
  playerRecordCard: { borderRadius: 22, borderWidth: 1.1, borderColor: '#2c75a8', backgroundColor: 'rgba(3,17,29,0.78)', padding: 14, shadowColor: '#168cff', shadowOpacity: 0.16, shadowRadius: 9, shadowOffset: { width: 0, height: 4 }, elevation: 5 },
  playerRecordHeader: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 13 },
  playerRecordEyebrow: { color: C.blueSoft, fontSize: 9, fontWeight: '900', letterSpacing: 1.3 },
  playerRecordTitle: { color: C.white, fontSize: 16, fontWeight: '900', marginTop: 3 },
  playerRecordPlayedPill: { minWidth: 54, height: 42, paddingHorizontal: 10, borderRadius: 14, borderWidth: 1, borderColor: '#2d7fb6', backgroundColor: 'rgba(4,28,47,0.72)', flexDirection: 'row', alignItems: 'baseline', justifyContent: 'center', gap: 4 },
  playerRecordPlayedValue: { color: C.white, fontSize: 20, fontWeight: '900' },
  playerRecordPlayedLabel: { color: C.blueSoft, fontSize: 8, fontWeight: '900', letterSpacing: 0.8 },
  playerRecordStatsRow: { flexDirection: 'row', gap: 8 },
  playerRecordStat: { flex: 1, minHeight: 78, borderRadius: 17, borderWidth: 1, borderColor: '#244f6e', backgroundColor: 'rgba(5,22,36,0.72)', alignItems: 'center', justifyContent: 'center', paddingVertical: 9, paddingHorizontal: 5 },
  playerRecordEmoji: { fontSize: 17 },
  playerRecordValue: { color: C.white, fontSize: 21, lineHeight: 24, fontWeight: '900', marginTop: 3 },
  playerRecordLabel: { color: C.muted, fontSize: 7.5, fontWeight: '900', letterSpacing: 0.7, marginTop: 2 },
`;
ui = ui.slice(0, stylePos) + recordStyles + ui.slice(stylePos);

fs.writeFileSync(uiPath, ui);
console.log('AJPA player record card: PJ, ganados, empatados y perdidos agregados debajo de Tu Club.');
