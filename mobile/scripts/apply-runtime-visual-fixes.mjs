import fs from 'node:fs';

const uiPath = new URL('../src/BotParityAppV2.tsx', import.meta.url);
let ui = fs.readFileSync(uiPath, 'utf8');

function mustReplace(search, replacement, label) {
  if (ui.includes(replacement)) return;
  if (!ui.includes(search)) throw new Error(`AJPA runtime visual fix: no encontré ${label}`);
  ui = ui.replace(search, replacement);
}

function replaceStyle(name, body) {
  const re = new RegExp(`  ${name}: \\{[^\\n]*\\},`);
  if (!re.test(ui)) return false;
  ui = ui.replace(re, `  ${name}: { ${body} },`);
  return true;
}

// Clausulazo used ClubBadge even though team badges are intentionally disabled in
// this APK. The reference only explodes at runtime when the screen/list is rendered.
ui = ui.replace(
  /<ClubBadge club=\{clausulazoTarget\.club\} size=\{82\} \/>/g,
  `<View style={[s.clausulazoOvr, s.clausulazoOvrLarge]}><Text style={s.clausulazoOvrValue}>{clausulazoTarget.rating ?? '—'}</Text><Text style={s.clausulazoOvrLabel}>OVR</Text></View>`,
);
ui = ui.replace(
  /<ClubBadge club=\{player\.club\} size=\{58\} \/>/g,
  `<View style={s.clausulazoOvr}><Text style={s.clausulazoOvrValue}>{player.rating ?? '—'}</Text><Text style={s.clausulazoOvrLabel}>OVR</Text></View>`,
);

if (ui.includes('<ClubBadge') && ui.includes('const clausulazoScreen = (')) {
  const start = ui.indexOf('  const clausulazoScreen = (');
  const end = ui.indexOf('  const publishScreen = (', start);
  if (end > start && ui.slice(start, end).includes('<ClubBadge')) {
    throw new Error('AJPA runtime visual fix: quedó un ClubBadge dentro de Clausulazo');
  }
}

// Bundle the Figo visual inside the APK. No external hotlink/network dependency.
mustReplace(
  `import { BG_PERFIL } from './bg_perfil';`,
  `import { BG_PERFIL } from './bg_perfil';\nimport { BG_CLAUSULAZO } from './bg_clausulazo';`,
  'import del fondo Clausulazo',
);

const remoteFigo = `    if (screen === 'clausulazo') return 'https://img.vavel.com/b/figo%20traspaso.jpg';`;
if (ui.includes(remoteFigo)) {
  ui = ui.replace(remoteFigo, `    if (screen === 'clausulazo') return BG_CLAUSULAZO;`);
} else if (!ui.includes(`if (screen === 'clausulazo') return BG_CLAUSULAZO;`)) {
  const marker = `  const screenBackground = (() => {\n`;
  if (!ui.includes(marker)) throw new Error('AJPA runtime visual fix: no encontré screenBackground');
  ui = ui.replace(marker, `${marker}    if (screen === 'clausulazo') return BG_CLAUSULAZO;\n`);
}

// Let the background participate in the glass look instead of hiding behind an
// almost opaque layer. Clausulazo gets its own slightly lighter shade.
if (ui.includes(`<View style={s.screenShade}>{body}</View>`)) {
  ui = ui.replace(
    `<View style={s.screenShade}>{body}</View>`,
    `<View style={[s.screenShade, screen === 'clausulazo' && s.clausulazoShade]}>{body}</View>`,
  );
}
replaceStyle('screenBackgroundImage', `opacity: 0.96`);
replaceStyle('screenShade', `flex: 1, backgroundColor: 'rgba(2,6,10,0.20)'`);

// Make the final Android build visibly match the approved neon/glass concept.
// elevation is the important Android shadow primitive; the iOS shadow values stay too.
replaceStyle('featureTile', `width: '48.4%', minHeight: 184, borderRadius: 24, borderWidth: 1.6, borderColor: '#168cff', backgroundColor: 'rgba(2,15,27,0.68)', padding: 15, shadowColor: '#168cff', shadowOpacity: 0.42, shadowRadius: 17, shadowOffset: { width: 0, height: 7 }, elevation: 13`);
replaceStyle('quickAction', `flexGrow: 1, flexBasis: '30%', minWidth: 96, minHeight: 66, flexDirection: 'row', alignItems: 'center', borderRadius: 18, borderWidth: 1.35, borderColor: '#168cff', backgroundColor: 'rgba(2,16,28,0.70)', paddingHorizontal: 11, paddingVertical: 10, shadowColor: '#168cff', shadowOpacity: 0.34, shadowRadius: 13, shadowOffset: { width: 0, height: 5 }, elevation: 10`);
replaceStyle('wideTile', `minHeight: 106, flexDirection: 'row', alignItems: 'center', borderRadius: 22, borderWidth: 1.55, borderColor: '#168cff', backgroundColor: 'rgba(2,15,27,0.68)', padding: 15, shadowColor: '#168cff', shadowOpacity: 0.38, shadowRadius: 15, shadowOffset: { width: 0, height: 6 }, elevation: 12`);
replaceStyle('heroClubCard', `minHeight: 154, flexDirection: 'row', alignItems: 'center', borderRadius: 25, borderWidth: 1.65, borderColor: '#168cff', backgroundColor: 'rgba(2,15,27,0.67)', padding: 17, shadowColor: '#168cff', shadowOpacity: 0.43, shadowRadius: 18, shadowOffset: { width: 0, height: 7 }, elevation: 13`);
replaceStyle('menuTile', `minHeight: 84, flexDirection: 'row', alignItems: 'center', backgroundColor: 'rgba(2,15,27,0.68)', borderWidth: 1.45, borderColor: '#168cff', borderRadius: 21, padding: 15, shadowColor: '#168cff', shadowOpacity: 0.33, shadowRadius: 13, shadowOffset: { width: 0, height: 5 }, elevation: 10`);
replaceStyle('card', `backgroundColor: 'rgba(2,15,27,0.69)', borderWidth: 1.35, borderColor: '#217fc1', borderRadius: 21, padding: 15, shadowColor: '#168cff', shadowOpacity: 0.28, shadowRadius: 12, shadowOffset: { width: 0, height: 5 }, elevation: 9`);
replaceStyle('editorCard', `backgroundColor: 'rgba(2,15,27,0.74)', borderWidth: 1.55, borderColor: '#168cff', borderRadius: 21, padding: 15, shadowColor: '#168cff', shadowOpacity: 0.36, shadowRadius: 14, shadowOffset: { width: 0, height: 6 }, elevation: 11`);
replaceStyle('marketControlCard', `flexDirection: 'row', alignItems: 'center', gap: 12, borderRadius: 21, borderWidth: 1.45, padding: 15, backgroundColor: 'rgba(2,15,27,0.70)', shadowColor: '#168cff', shadowOpacity: 0.32, shadowRadius: 13, shadowOffset: { width: 0, height: 5 }, elevation: 10`);
replaceStyle('topAction', `minHeight: 38, paddingHorizontal: 11, borderRadius: 14, borderWidth: 1.35, borderColor: '#168cff', backgroundColor: 'rgba(2,15,27,0.80)', alignItems: 'center', justifyContent: 'center', shadowColor: '#168cff', shadowOpacity: 0.35, shadowRadius: 10, shadowOffset: { width: 0, height: 4 }, elevation: 8`);

// Give Clausulazo a distinct red danger glow while preserving the shared glass layout.
const clauseStart = ui.indexOf('  const clausulazoScreen = (');
const clauseEnd = clauseStart >= 0 ? ui.indexOf('  const publishScreen = (', clauseStart) : -1;
if (clauseStart >= 0 && clauseEnd > clauseStart) {
  let block = ui.slice(clauseStart, clauseEnd);
  block = block.replace(/style=\{s\.card\}/g, `style={[s.card, s.clausulazoCard]}`);
  block = block.replace(/style=\{\(\{ pressed \}\) => \[s\.card,/g, `style={({ pressed }) => [s.card, s.clausulazoCard,`);
  block = block.replace(/style=\{s\.summaryCard\}/g, `style={[s.summaryCard, s.clausulazoSummaryCard]}`);
  ui = ui.slice(0, clauseStart) + block + ui.slice(clauseEnd);
}

const styleClose = '\n});';
const stylePos = ui.lastIndexOf(styleClose);
if (stylePos < 0) throw new Error('AJPA runtime visual fix: no encontré cierre de estilos');
if (!ui.includes('  clausulazoShade: {')) {
  const extra = String.raw`
  clausulazoShade: { backgroundColor: 'rgba(4,1,3,0.13)' },
  clausulazoCard: { borderColor: '#e14b59', backgroundColor: 'rgba(24,5,10,0.66)', shadowColor: '#ff3347', shadowOpacity: 0.40, shadowRadius: 15, shadowOffset: { width: 0, height: 6 }, elevation: 12 },
  clausulazoSummaryCard: { borderColor: '#b83b48', backgroundColor: 'rgba(24,5,10,0.72)', shadowColor: '#ff3347', shadowOpacity: 0.30, shadowRadius: 12, shadowOffset: { width: 0, height: 5 }, elevation: 10 },
  clausulazoOvr: { width: 58, height: 58, borderRadius: 18, borderWidth: 1.4, borderColor: '#e14b59', backgroundColor: 'rgba(30,5,10,0.82)', alignItems: 'center', justifyContent: 'center', shadowColor: '#ff3347', shadowOpacity: 0.34, shadowRadius: 10, shadowOffset: { width: 0, height: 4 }, elevation: 9 },
  clausulazoOvrLarge: { width: 82, height: 82, borderRadius: 24 },
  clausulazoOvrValue: { color: C.white, fontSize: 20, lineHeight: 22, fontWeight: '900' },
  clausulazoOvrLabel: { color: C.red, fontSize: 8.5, fontWeight: '900', letterSpacing: 1.1, marginTop: 2 },
`;
  ui = ui.slice(0, stylePos) + extra + ui.slice(stylePos);
}

fs.writeFileSync(uiPath, ui);
console.log('AJPA runtime visual fix: Clausulazo crash-safe + fondo embebido + glass/neon reforzado');
