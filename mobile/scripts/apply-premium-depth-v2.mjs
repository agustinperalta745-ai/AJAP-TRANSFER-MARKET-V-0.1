import fs from 'node:fs';
import crypto from 'node:crypto';

const backgroundPart = new URL('../assets/background-parts/league-maradona.b64', import.meta.url);
const generatedDir = new URL('../assets/generated/', import.meta.url);
const uiPath = new URL('../src/BotParityAppV2.tsx', import.meta.url);

const base64 = fs.readFileSync(backgroundPart, 'utf8').trim();
if (!base64 || !/^[A-Za-z0-9+/=]+$/.test(base64)) {
  throw new Error('AJPA depth v2: fondo de Liga inválido');
}
const leagueBytes = Buffer.from(base64, 'base64');
const leagueSha = crypto.createHash('sha256').update(leagueBytes).digest('hex');
if (leagueSha !== '8402ae12fc1f174c1a400565dc67bb77390983f2be6e21f1675d35a8b93061ef') {
  throw new Error(`AJPA depth v2: hash incorrecto del fondo Liga: ${leagueSha}`);
}
if (leagueBytes.subarray(0, 4).toString('ascii') !== 'RIFF' || leagueBytes.subarray(8, 12).toString('ascii') !== 'WEBP') {
  throw new Error('AJPA depth v2: el fondo Liga no es WebP válido');
}

fs.mkdirSync(generatedDir, { recursive: true });
fs.writeFileSync(new URL('league-maradona.webp', generatedDir), leagueBytes);
fs.writeFileSync(
  new URL('../src/bg_liga.ts', import.meta.url),
  `export const BG_LIGA = require('../assets/generated/league-maradona.webp');\n`,
);

let ui = fs.readFileSync(uiPath, 'utf8');

function replaceStyle(name, body) {
  const re = new RegExp(`  ${name}: \\{[^\\n]*\\},`);
  if (!re.test(ui)) return false;
  ui = ui.replace(re, `  ${name}: { ${body} },`);
  return true;
}

function injectExact(opening, child, label) {
  if (ui.includes(`${opening}\n${child}`)) return;
  if (!ui.includes(opening)) throw new Error(`AJPA depth v2: no encontré ${label}`);
  ui = ui.replace(opening, `${opening}\n${child}`);
}

// Liga usa la foto elegida por el usuario como asset local, sin depender de URLs.
if (!ui.includes("import { BG_LIGA } from './bg_liga';")) {
  const importMarker = "import { BG_PERFIL } from './bg_perfil';";
  if (!ui.includes(importMarker)) throw new Error('AJPA depth v2: no encontré import BG_PERFIL');
  ui = ui.replace(importMarker, `${importMarker}\nimport { BG_LIGA } from './bg_liga';`);
}
if (!ui.includes("if (screen === 'league') return BG_LIGA;")) {
  const backgroundMarker = `  const screenBackground = (() => {\n`;
  if (!ui.includes(backgroundMarker)) throw new Error('AJPA depth v2: no encontré screenBackground');
  ui = ui.replace(backgroundMarker, `${backgroundMarker}    if (screen === 'league') return BG_LIGA;\n`);
}

// Capas internas que simulan material/relieve sin volver a usar elevation alto
// (en Android había generado rectángulos oscuros alrededor de las tarjetas).
const componentMarker = `function SectionLabel({ title, badge }: { title: string; badge?: string }) {`;
if (!ui.includes('function SurfaceDepth(')) {
  if (!ui.includes(componentMarker)) throw new Error('AJPA depth v2: no encontré SectionLabel');
  const component = String.raw`function SurfaceDepth({ strong = false, danger = false }: { strong?: boolean; danger?: boolean }) {
  return (
    <>
      <View pointerEvents="none" style={[s.surfaceGlow, strong && s.surfaceGlowStrong, danger && s.surfaceGlowDanger]} />
      <View pointerEvents="none" style={[s.surfaceTopLine, strong && s.surfaceTopLineStrong, danger && s.surfaceTopLineDanger]} />
      <View pointerEvents="none" style={s.surfaceBottomShade} />
    </>
  );
}

`;
  ui = ui.replace(componentMarker, component + componentMarker);
}

const featureOpen = `    <Pressable\n      onPress={onPress}\n      style={({ pressed }) => [\n        s.featureTile,\n        danger && s.featureTileDanger,\n        pressed && { opacity: 0.72, transform: [{ scale: 0.985 }] },\n      ]}\n    >`;
injectExact(featureOpen, `      <SurfaceDepth danger={danger} />`, 'FeatureTile');

const quickOpen = `    <Pressable\n      onPress={onPress}\n      style={({ pressed }) => [s.quickAction, danger && s.quickActionDanger, pressed && { opacity: 0.72 }]}\n    >`;
injectExact(quickOpen, `      <SurfaceDepth danger={danger} />`, 'QuickAction');

const heroOpen = `<Pressable onPress={onPress} style={({ pressed }) => [s.heroClubCard, pressed && { opacity: 0.76 }]}>`;
injectExact(heroOpen, `      <SurfaceDepth strong />`, 'HeroClubCard');

const wideOpen = `    <Pressable\n      onPress={onPress}\n      style={({ pressed }) => [s.wideTile, danger && s.wideTileDanger, pressed && { opacity: 0.74, transform: [{ scale: 0.992 }] }]}\n    >`;
injectExact(wideOpen, `      <SurfaceDepth danger={danger} />`, 'WideTile');

// Más profundidad y menos sensación de caja plana: borde superior luminoso,
// base más oscura y contraste distinto para cada jerarquía.
replaceStyle('heroClubCard', `minHeight: 154, flexDirection: 'row', alignItems: 'center', borderRadius: 25, borderWidth: 1.2, borderTopWidth: 1.8, borderBottomWidth: 2.2, borderTopColor: 'rgba(113,196,255,0.92)', borderBottomColor: 'rgba(8,77,124,0.96)', borderLeftColor: 'rgba(45,146,255,0.68)', borderRightColor: 'rgba(45,146,255,0.68)', backgroundColor: 'rgba(3,17,29,0.96)', padding: 17, overflow: 'hidden', shadowColor: '#000', shadowOpacity: 0.18, shadowRadius: 12, shadowOffset: { width: 0, height: 8 }, elevation: 0`);
replaceStyle('featureTile', `width: '48.4%', minHeight: 184, borderRadius: 24, borderWidth: 1.05, borderTopWidth: 1.55, borderBottomWidth: 2, borderTopColor: 'rgba(92,183,247,0.78)', borderBottomColor: 'rgba(7,62,101,0.98)', borderLeftColor: 'rgba(39,119,176,0.62)', borderRightColor: 'rgba(39,119,176,0.62)', backgroundColor: 'rgba(3,16,27,0.955)', padding: 15, overflow: 'hidden', shadowColor: '#000', shadowOpacity: 0.16, shadowRadius: 10, shadowOffset: { width: 0, height: 7 }, elevation: 0`);
replaceStyle('quickAction', `flexGrow: 1, flexBasis: '30%', minWidth: 96, minHeight: 66, flexDirection: 'row', alignItems: 'center', borderRadius: 18, borderWidth: 1, borderTopWidth: 1.45, borderBottomWidth: 1.8, borderTopColor: 'rgba(87,177,238,0.72)', borderBottomColor: 'rgba(7,57,92,0.98)', borderLeftColor: 'rgba(39,112,164,0.56)', borderRightColor: 'rgba(39,112,164,0.56)', backgroundColor: 'rgba(3,17,29,0.96)', paddingHorizontal: 11, paddingVertical: 10, overflow: 'hidden', shadowColor: '#000', shadowOpacity: 0.14, shadowRadius: 8, shadowOffset: { width: 0, height: 6 }, elevation: 0`);
replaceStyle('wideTile', `minHeight: 106, flexDirection: 'row', alignItems: 'center', borderRadius: 22, borderWidth: 1.05, borderTopWidth: 1.55, borderBottomWidth: 2, borderTopColor: 'rgba(92,183,247,0.80)', borderBottomColor: 'rgba(7,62,101,0.98)', borderLeftColor: 'rgba(39,119,176,0.60)', borderRightColor: 'rgba(39,119,176,0.60)', backgroundColor: 'rgba(3,16,27,0.96)', padding: 15, overflow: 'hidden', shadowColor: '#000', shadowOpacity: 0.15, shadowRadius: 9, shadowOffset: { width: 0, height: 6 }, elevation: 0`);
replaceStyle('featureIconWrap', `width: 56, height: 56, borderRadius: 19, borderWidth: 1.1, borderTopWidth: 1.5, borderTopColor: 'rgba(116,202,255,0.86)', borderBottomColor: 'rgba(8,73,118,0.96)', borderLeftColor: 'rgba(45,146,255,0.62)', borderRightColor: 'rgba(45,146,255,0.62)', backgroundColor: 'rgba(5,27,44,0.98)', alignItems: 'center', justifyContent: 'center', marginBottom: 16, shadowColor: '#000', shadowOpacity: 0.18, shadowRadius: 6, shadowOffset: { width: 0, height: 5 }, elevation: 0`);
replaceStyle('heroIconWrap', `width: 66, height: 66, borderRadius: 22, borderWidth: 1.1, borderTopWidth: 1.6, borderTopColor: 'rgba(130,211,255,0.90)', borderBottomColor: 'rgba(8,72,116,0.96)', borderLeftColor: 'rgba(45,146,255,0.66)', borderRightColor: 'rgba(45,146,255,0.66)', backgroundColor: 'rgba(5,28,45,0.98)', alignItems: 'center', justifyContent: 'center', marginRight: 15, shadowColor: '#000', shadowOpacity: 0.18, shadowRadius: 7, shadowOffset: { width: 0, height: 5 }, elevation: 0`);
replaceStyle('wideIconWrap', `width: 58, height: 58, borderRadius: 19, borderWidth: 1.1, borderTopWidth: 1.5, borderTopColor: 'rgba(116,202,255,0.84)', borderBottomColor: 'rgba(8,70,114,0.96)', borderLeftColor: 'rgba(45,146,255,0.60)', borderRightColor: 'rgba(45,146,255,0.60)', backgroundColor: 'rgba(5,27,44,0.98)', alignItems: 'center', justifyContent: 'center', marginRight: 13, shadowColor: '#000', shadowOpacity: 0.17, shadowRadius: 6, shadowOffset: { width: 0, height: 5 }, elevation: 0`);
replaceStyle('topBar', `height: 64, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: 14, borderBottomWidth: 1.5, borderBottomColor: 'rgba(45,146,255,0.48)', backgroundColor: 'rgba(2,8,14,0.96)'`);
replaceStyle('screenShade', `flex: 1, backgroundColor: 'rgba(2,6,10,0.26)'`);

// Si el runtime anterior ya dejó la sombra especial de Clausulazo, extendemos la
// misma composición para Liga. En caso contrario se agrega igualmente sin romper.
ui = ui.replace(
  `<View style={[s.screenShade, screen === 'clausulazo' && s.clausulazoShade]}>{body}</View>`,
  `<View style={[s.screenShade, screen === 'clausulazo' && s.clausulazoShade, screen === 'league' && s.leagueShade]}>{body}</View>`,
);
if (!ui.includes(`screen === 'league' && s.leagueShade`)) {
  ui = ui.replace(
    `<View style={s.screenShade}>{body}</View>`,
    `<View style={[s.screenShade, screen === 'league' && s.leagueShade]}>{body}</View>`,
  );
}

const styleClose = '\n});';
const stylePos = ui.lastIndexOf(styleClose);
if (stylePos < 0) throw new Error('AJPA depth v2: no encontré cierre de estilos');
if (!ui.includes('  surfaceGlow: {')) {
  const extra = String.raw`
  surfaceGlow: { position: 'absolute', top: -34, left: -18, width: 150, height: 105, borderRadius: 70, backgroundColor: 'rgba(45,146,255,0.055)' },
  surfaceGlowStrong: { width: 210, height: 128, backgroundColor: 'rgba(65,170,255,0.085)' },
  surfaceGlowDanger: { backgroundColor: 'rgba(255,75,91,0.055)' },
  surfaceTopLine: { position: 'absolute', top: 0, left: 20, right: 20, height: 1, borderRadius: 1, backgroundColor: 'rgba(155,218,255,0.34)' },
  surfaceTopLineStrong: { backgroundColor: 'rgba(179,228,255,0.48)' },
  surfaceTopLineDanger: { backgroundColor: 'rgba(255,150,158,0.30)' },
  surfaceBottomShade: { position: 'absolute', left: 0, right: 0, bottom: 0, height: 34, backgroundColor: 'rgba(0,0,0,0.16)' },
  leagueShade: { backgroundColor: 'rgba(1,5,8,0.34)' },
`;
  ui = ui.slice(0, stylePos) + extra + ui.slice(stylePos);
}

if (!ui.includes("if (screen === 'league') return BG_LIGA;")) {
  throw new Error('AJPA depth v2: Liga no quedó conectada al fondo Maradona');
}
if (!ui.includes(`${featureOpen}\n      <SurfaceDepth danger={danger} />`)) {
  throw new Error('AJPA depth v2: FeatureTile sin capa de profundidad');
}
if (!ui.includes('<SurfaceDepth strong />')) {
  throw new Error('AJPA depth v2: Hero sin capa de profundidad');
}

fs.writeFileSync(uiPath, ui);
console.log('AJPA depth v2: tarjetas con relieve interno + fondo Maradona en Liga');
