import fs from 'node:fs';

const uiPath = new URL('../src/BotParityAppV2.tsx', import.meta.url);
let ui = fs.readFileSync(uiPath, 'utf8');

function mustReplace(search, replacement, label) {
  if (!ui.includes(search)) throw new Error(`AJPA premium UI: no encontré ${label}`);
  ui = ui.replace(search, replacement);
}

function replaceStyle(name, body) {
  const re = new RegExp(`  ${name}: \\{[^\\n]*\\},`);
  if (!re.test(ui)) return;
  ui = ui.replace(re, `  ${name}: { ${body} },`);
}

mustReplace(
  `  const [screen, setScreen] = useState<Screen>('home');`,
  `  const [screen, setScreen] = useState<Screen>('home');\n  const [screenHistory, setScreenHistory] = useState<Screen[]>([]);`,
  'estado de navegación',
);

mustReplace(
  `  const openScreen = async (next: Screen) => {\n    setScreen(next);`,
  `  const openScreen = async (next: Screen) => {\n    const staffOnly = next === 'admin' || next === 'adminTools' || next === 'assignments' || next === 'adminMarket' || next === 'adminOperations' || next === 'adminClauses' || next === 'adminUndo' || next === 'adminRosters' || next === 'adminEconomy' || next === 'adminEconomyAdjust' || next === 'adminManagement';\n    if (staffOnly && !profile?.is_staff) {\n      Alert.alert('Acceso restringido', 'Esta sección es exclusiva para administradores.');\n      return;\n    }\n    if (next !== screen) setScreenHistory((previous) => [...previous, screen].slice(-30));\n    setScreen(next);`,
  'openScreen',
);

mustReplace(
  `  const requireClub = (next: Screen) => {`,
  `  const goBack = () => {\n    setScreenHistory((previous) => {\n      if (previous.length === 0) {\n        setScreen('home');\n        return [];\n      }\n      const nextHistory = [...previous];\n      const previousScreen = nextHistory.pop()!;\n      setScreen(previousScreen);\n      return nextHistory;\n    });\n  };\n\n  const goHome = () => {\n    setScreenHistory([]);\n    setScreen('home');\n  };\n\n  const requireClub = (next: Screen) => {`,
  'controles volver/menu',
);

// Publishing from a player card must also participate in previous-screen navigation.
if (ui.includes(`    setScreen('publish');`)) {
  ui = ui.replace(`    setScreen('publish');`, `    void openScreen('publish');`);
}

mustReplace(
  `        {screen !== 'home' ? (\n          <Pressable onPress={() => setScreen('home')} style={s.topAction}><Text style={s.topActionText}>‹ MENÚ</Text></Pressable>\n        ) : (\n          <View><Text style={s.brand}>AJPA</Text><Text style={s.brandSub}>TRANSFER MARKET · MOBILE</Text></View>\n        )}\n        <Pressable onPress={() => setScreen('profile')} style={s.profileButton}><Text style={s.profileButtonText}>MI PERFIL</Text></Pressable>`,
  `        {screen !== 'home' ? (\n          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 7 }}>\n            <Pressable onPress={goBack} style={s.topAction}><Text style={s.topActionText}>‹ VOLVER</Text></Pressable>\n            <Pressable onPress={goHome} style={s.topAction}><Text style={s.topActionText}>⌂ MENÚ</Text></Pressable>\n          </View>\n        ) : (\n          <View><Text style={s.brand}>AJPA</Text><Text style={s.brandSub}>TRANSFER MARKET · MOBILE</Text></View>\n        )}\n        <Pressable onPress={() => void openScreen('profile')} style={s.profileButton}><Text style={s.profileButtonText}>MI PERFIL</Text></Pressable>`,
  'barra superior con volver y menú',
);

// Give the whole interface the same translucent neon/glass language as the
// approved concept while leaving every screen background asset untouched.
replaceStyle('topBar', `height: 64, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: 14, borderBottomWidth: 1, borderBottomColor: '#16486f', backgroundColor: 'rgba(2,8,14,0.78)'`);
replaceStyle('topAction', `minHeight: 38, paddingHorizontal: 11, borderRadius: 14, borderWidth: 1, borderColor: '#245f8d', backgroundColor: 'rgba(3,18,31,0.82)', alignItems: 'center', justifyContent: 'center', shadowColor: '#168cff', shadowOpacity: 0.22, shadowRadius: 7, shadowOffset: { width: 0, height: 2 }, elevation: 4`);
replaceStyle('topActionText', `color: C.blueSoft, fontSize: 9.5, fontWeight: '900', letterSpacing: 0.8`);
replaceStyle('profileButton', `minWidth: 92, height: 40, paddingHorizontal: 12, borderRadius: 20, borderWidth: 1.2, borderColor: '#2d7fba', alignItems: 'center', justifyContent: 'center', backgroundColor: 'rgba(4,20,33,0.80)', shadowColor: '#168cff', shadowOpacity: 0.26, shadowRadius: 8, shadowOffset: { width: 0, height: 2 }, elevation: 5`);
replaceStyle('profileButtonText', `color: C.blueSoft, fontSize: 10, fontWeight: '900', letterSpacing: 0.8`);
replaceStyle('featureTile', `width: '48.4%', minHeight: 184, borderRadius: 24, borderWidth: 1.25, borderColor: '#2f8fd2', backgroundColor: 'rgba(3,17,29,0.78)', padding: 15, overflow: 'hidden', shadowColor: '#168cff', shadowOpacity: 0.24, shadowRadius: 12, shadowOffset: { width: 0, height: 5 }, elevation: 7`);
replaceStyle('featureTileDanger', `borderColor: '#9b3b45', backgroundColor: 'rgba(31,7,13,0.78)', shadowColor: '#ff4f5d', shadowOpacity: 0.18, shadowRadius: 10, shadowOffset: { width: 0, height: 4 }, elevation: 6`);
replaceStyle('featureIconWrap', `width: 56, height: 56, borderRadius: 19, borderWidth: 1.1, borderColor: '#2d7fb6', backgroundColor: 'rgba(4,28,47,0.78)', alignItems: 'center', justifyContent: 'center', marginBottom: 16, shadowColor: '#168cff', shadowOpacity: 0.20, shadowRadius: 7, shadowOffset: { width: 0, height: 2 }, elevation: 4`);
replaceStyle('quickAction', `flexGrow: 1, flexBasis: '30%', minWidth: 96, minHeight: 66, flexDirection: 'row', alignItems: 'center', borderRadius: 18, borderWidth: 1.1, borderColor: '#2d6c98', backgroundColor: 'rgba(4,19,31,0.78)', paddingHorizontal: 11, paddingVertical: 10, shadowColor: '#168cff', shadowOpacity: 0.18, shadowRadius: 8, shadowOffset: { width: 0, height: 3 }, elevation: 5`);
replaceStyle('quickActionDanger', `borderColor: '#8b3741', backgroundColor: 'rgba(29,8,13,0.78)', shadowColor: '#ff4f5d', shadowOpacity: 0.14, shadowRadius: 7, shadowOffset: { width: 0, height: 3 }, elevation: 4`);
replaceStyle('homeStatusCard', `flex: 1, minHeight: 76, borderRadius: 19, borderWidth: 1.1, borderColor: '#2b668f', backgroundColor: 'rgba(4,18,30,0.76)', padding: 13, justifyContent: 'center', shadowColor: '#168cff', shadowOpacity: 0.16, shadowRadius: 8, shadowOffset: { width: 0, height: 3 }, elevation: 4`);
replaceStyle('marketControlCard', `flexDirection: 'row', alignItems: 'center', gap: 12, borderRadius: 21, borderWidth: 1.1, padding: 15, backgroundColor: 'rgba(4,18,30,0.78)', shadowColor: '#168cff', shadowOpacity: 0.16, shadowRadius: 8, shadowOffset: { width: 0, height: 3 }, elevation: 4`);
replaceStyle('budgetCard', `minHeight: 76, flexDirection: 'row', alignItems: 'center', gap: 12, borderRadius: 19, borderWidth: 1.1, borderColor: '#2b668f', backgroundColor: 'rgba(4,18,30,0.76)', padding: 14, shadowColor: '#168cff', shadowOpacity: 0.15, shadowRadius: 7, shadowOffset: { width: 0, height: 3 }, elevation: 4`);
replaceStyle('menuTile', `minHeight: 84, flexDirection: 'row', alignItems: 'center', backgroundColor: 'rgba(4,18,30,0.76)', borderWidth: 1.1, borderColor: '#2b668f', borderRadius: 21, padding: 15, shadowColor: '#168cff', shadowOpacity: 0.16, shadowRadius: 8, shadowOffset: { width: 0, height: 3 }, elevation: 4`);
replaceStyle('card', `backgroundColor: 'rgba(4,18,30,0.76)', borderWidth: 1.1, borderColor: '#2b668f', borderRadius: 21, padding: 15, shadowColor: '#168cff', shadowOpacity: 0.14, shadowRadius: 7, shadowOffset: { width: 0, height: 3 }, elevation: 4`);

fs.writeFileSync(uiPath, ui);
console.log('AJPA premium UI: navegación VOLVER + MENÚ, Staff protegido y paneles glass/neon aplicados');
