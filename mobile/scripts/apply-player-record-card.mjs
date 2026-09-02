import fs from 'node:fs';

const shellPath = new URL('../src/MatchSearchShell.tsx', import.meta.url);
let shell = fs.readFileSync(shellPath, 'utf8');

const PATCH_MARKER = 'AJPA_PLAYER_RECORD_CARD_SEARCH_V2';
if (shell.includes(PATCH_MARKER)) {
  console.log('AJPA player record card: ya estaba aplicada en Buscar Partido.');
  process.exit(0);
}

function requireMarker(condition, label) {
  if (!condition) throw new Error(`AJPA player record card: no encontré ${label}`);
}

// La tarjeta de rendimiento pertenece a Buscar Partido. Inicio conserva solamente
// la tarjeta principal de Tu Club; las estadísticas se cargan dentro del overlay.
const apiImport = "import { apiRequest } from './api';";
requireMarker(shell.includes(apiImport), 'import de api en MatchSearchShell');
shell = shell.replace(
  apiImport,
  "import { apiRequest, fetchLeague, type LeagueData } from './api';",
);

const exportMarker = '\nexport default function MatchSearchShell() {';
const exportPos = shell.indexOf(exportMarker);
requireMarker(exportPos >= 0, 'MatchSearchShell');

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

function recordTeamKey(value: string | null | undefined) {
  const key = String(value ?? '')
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, ' ')
    .trim();
  return ['psg', 'paris saint germain', 'paris saint germain psg', 'paris saint germain fc'].includes(key)
    ? 'paris saint germain'
    : key;
}
`;
shell = shell.slice(0, exportPos) + recordComponent + shell.slice(exportPos);

const viewerState = "  const [viewerClub, setViewerClub] = useState<string | null>(null);";
requireMarker(shell.includes(viewerState), 'estado viewerClub');
shell = shell.replace(
  viewerState,
  `${viewerState}\n  const [leagueData, setLeagueData] = useState<LeagueData | null>(null);`,
);

const viewerLoad = '      setViewerClub(result.viewer_club ?? null);';
requireMarker(shell.includes(viewerLoad), 'carga de viewerClub');
shell = shell.replace(
  viewerLoad,
  `${viewerLoad}\n      try { setLeagueData(await fetchLeague()); } catch { setLeagueData(null); }`,
);

const returnMarker = '  return (\n    <View style={s.root}>';
const returnPos = shell.indexOf(returnMarker);
requireMarker(returnPos >= 0, 'return principal de MatchSearchShell');
const recordLogic = String.raw`  const myLeagueRecord = viewerClub
    ? leagueData?.standings.find((row) => recordTeamKey(row.team) === recordTeamKey(viewerClub)) ?? null
    : null;

`;
shell = shell.slice(0, returnPos) + recordLogic + shell.slice(returnPos);

const searchButtonMarker = '            {viewerClub && !creating && !hasActiveSearch ? (';
const searchButtonPos = shell.indexOf(searchButtonMarker);
requireMarker(searchButtonPos >= 0, 'botón Buscar Rival');
const recordUsage = String.raw`            {viewerClub ? (
              <PlayerRecordCard
                played={myLeagueRecord?.pj ?? 0}
                wins={myLeagueRecord?.pg ?? 0}
                draws={myLeagueRecord?.pe ?? 0}
                losses={myLeagueRecord?.pp ?? 0}
              />
            ) : null}

`;
shell = shell.slice(0, searchButtonPos) + recordUsage + shell.slice(searchButtonPos);

const styleClose = '\n});';
const stylePos = shell.lastIndexOf(styleClose);
requireMarker(stylePos >= 0, 'cierre de StyleSheet');
const recordStyles = String.raw`
  playerRecordCard: { borderRadius: 15, borderWidth: 1, borderColor: '#25445c', backgroundColor: C.panel2, padding: 13 },
  playerRecordHeader: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 13 },
  playerRecordEyebrow: { color: C.blueSoft, fontSize: 9, fontWeight: '900', letterSpacing: 1.3 },
  playerRecordTitle: { color: C.white, fontSize: 16, fontWeight: '900', marginTop: 3 },
  playerRecordPlayedPill: { minWidth: 54, height: 42, paddingHorizontal: 10, borderRadius: 13, borderWidth: 1, borderColor: C.border, backgroundColor: C.panel, flexDirection: 'row', alignItems: 'baseline', justifyContent: 'center', gap: 4 },
  playerRecordPlayedValue: { color: C.white, fontSize: 20, fontWeight: '900' },
  playerRecordPlayedLabel: { color: C.blueSoft, fontSize: 8, fontWeight: '900', letterSpacing: 0.8 },
  playerRecordStatsRow: { flexDirection: 'row', gap: 8 },
  playerRecordStat: { flex: 1, minHeight: 78, borderRadius: 14, borderWidth: 1, borderColor: C.border, backgroundColor: C.panel, alignItems: 'center', justifyContent: 'center', paddingVertical: 9, paddingHorizontal: 5 },
  playerRecordEmoji: { fontSize: 17 },
  playerRecordValue: { color: C.white, fontSize: 21, lineHeight: 24, fontWeight: '900', marginTop: 3 },
  playerRecordLabel: { color: C.muted, fontSize: 7.5, fontWeight: '900', letterSpacing: 0.7, marginTop: 2 },
`;
shell = shell.slice(0, stylePos) + recordStyles + shell.slice(stylePos);

fs.writeFileSync(shellPath, shell);
console.log('AJPA player record card: movida de Inicio a Buscar Partido, debajo de Tu Club.');
