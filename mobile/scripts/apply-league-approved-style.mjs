import fs from 'node:fs';

const uiPath = new URL('../src/BotParityAppV2.tsx', import.meta.url);
let ui = fs.readFileSync(uiPath, 'utf8');
const marker = '// AJPA_LEAGUE_DIRECT_LOAD_FIX_V4';
if (ui.includes(marker)) process.exit(0);

// IMPORTANT: Liga keeps the original production table/UI. This patch only fixes
// direct entry from the redesigned bottom navigation, where openScreen('league')
// is bypassed and the old table used to stay forever with leagueData = null.
const stateAnchor = "  const [leagueData, setLeagueData] = useState<LeagueData | null>(null);";
if (!ui.includes(stateAnchor)) throw new Error('Liga load fix: falta leagueData');

if (!ui.includes("const [leagueLoading, setLeagueLoading]")) {
  ui = ui.replace(
    stateAnchor,
    stateAnchor + "\n  const [leagueLoading, setLeagueLoading] = useState(false);\n  const [leagueError, setLeagueError] = useState<string | null>(null);",
  );
}

const openAnchor = '  const openScreen = async (next: Screen) => {';
if (!ui.includes(openAnchor)) throw new Error('Liga load fix: falta openScreen');

if (!ui.includes('const loadLeagueData = useCallback')) {
  const loader = `  const loadLeagueData = useCallback(async (showAlert = false) => {
    setLeagueLoading(true);
    setLeagueError(null);
    try {
      const data = await fetchLeague();
      setLeagueData(data);
      return data;
    } catch (error) {
      const message = apiError(error);
      setLeagueError(message);
      if (showAlert) Alert.alert('Liga', message);
      return null;
    } finally {
      setLeagueLoading(false);
    }
  }, []);

`;
  ui = ui.replace(openAnchor, loader + openAnchor);
}

const oldA = `    if (next === 'league') {
      try { setLeagueData(await fetchLeague()); } catch (error) { Alert.alert('Liga', apiError(error)); }
    }`;
const oldB = `    if (next === 'league' || next === 'leagueHistory') {
      try { setLeagueData(await fetchLeague()); } catch (error) { Alert.alert('Liga', apiError(error)); }
    }`;

if (ui.includes(oldB)) {
  ui = ui.replace(oldB, `    if (next === 'league' || next === 'leagueHistory') {
      await loadLeagueData(true);
    }`);
} else if (ui.includes(oldA)) {
  ui = ui.replace(oldA, `    if (next === 'league') {
      await loadLeagueData(true);
    }`);
}

const requireClubAnchor = '  const requireClub = (next: Screen) => {';
if (!ui.includes(requireClubAnchor)) throw new Error('Liga load fix: falta requireClub');

if (!ui.includes("initialScreen === 'league'")) {
  const hydration = `  useEffect(() => {
    if (initialScreen === 'league') {
      void loadLeagueData(false);
    }
  }, [initialScreen, loadLeagueData]);

`;
  ui = ui.replace(requireClubAnchor, hydration + requireClubAnchor);
}

ui += '\n' + marker + '\n';
fs.writeFileSync(uiPath, ui);
console.log('AJPA UI Lab: tabla original de Liga preservada + carga directa corregida.');
