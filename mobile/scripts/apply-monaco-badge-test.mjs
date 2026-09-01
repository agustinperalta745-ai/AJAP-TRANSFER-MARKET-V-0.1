import fs from 'node:fs';
import crypto from 'node:crypto';

const uiPath = 'src/BotParityAppV2.tsx';
const chunkDir = 'assets/team_badge_hd3k_chunks';
const badgePath = 'assets/team_badge_test/as_monaco_hd.png';
const expectedSha = '7c5f6a3de64725801f500e6a1895a736c26733909b88d73ed6b083ae38ef2e75';

// Reconstruimos un PNG 256x256 desde el vector original. A 62dp cubre
// incluso pantallas Android xxxhdpi (4x) sin ampliar una miniatura borrosa.
if (!fs.existsSync(chunkDir)) {
  throw new Error('Monaco HD: no encontré los fragmentos del escudo');
}
const parts = fs.readdirSync(chunkDir).filter((name) => name.endsWith('.txt')).sort();
if (!parts.length) throw new Error('Monaco HD: no hay fragmentos para reconstruir');
const base64 = parts.map((name) => fs.readFileSync(`${chunkDir}/${name}`, 'utf8').trim()).join('').replace(/\s+/g, '');
if (!base64 || !/^[A-Za-z0-9+/=]+$/.test(base64)) {
  throw new Error('Monaco HD: base64 inválido');
}
const badge = Buffer.from(base64, 'base64');
const sha = crypto.createHash('sha256').update(badge).digest('hex');
if (sha !== expectedSha) throw new Error(`Monaco HD: SHA-256 inesperado ${sha}`);
if (!badge.subarray(0, 8).equals(Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]))) {
  throw new Error('Monaco HD: firma PNG inválida');
}
const width = badge.readUInt32BE(16);
const height = badge.readUInt32BE(20);
const bitDepth = badge[24];
const colorType = badge[25];
if (width !== 256 || height !== 256 || bitDepth !== 8 || colorType !== 6) {
  throw new Error(`Monaco HD: se esperaba PNG RGBA 256x256 y llegó ${width}x${height}, depth=${bitDepth}, type=${colorType}`);
}
fs.mkdirSync('assets/team_badge_test', { recursive: true });
fs.writeFileSync(badgePath, badge);

let ui = fs.readFileSync(uiPath, 'utf8');

if (!ui.includes("import { ClubBadge } from './teamBadges';")) {
  const anchor = "import { BG_PERFIL } from './bg_perfil';";
  if (!ui.includes(anchor)) throw new Error('Monaco badge test: no encontré el import de BG_PERFIL');
  ui = ui.replace(anchor, `${anchor}\nimport { ClubBadge } from './teamBadges';`);
}

const oldHero = '<View style={s.heroIconWrap}><Text style={s.heroIcon}>🛡️</Text></View>';
const newHero = `<View style={s.heroIconWrap}>\n        <ClubBadge club={club} size={62} />\n      </View>`;
if (!ui.includes('<ClubBadge club={club} size={62} />')) {
  if (!ui.includes(oldHero)) throw new Error('Monaco badge test: no encontré el escudo genérico de HeroClubCard');
  ui = ui.replace(oldHero, newHero);
}

// Profundidad suave también dentro de los cuadrados de iconos. Son capas
// translúcidas, sin elevation, para evitar los rectángulos oscuros de Android.
if (!ui.includes('function IconSurfaceDepth(')) {
  const marker = 'function SurfaceDepth(';
  if (!ui.includes(marker)) throw new Error('Monaco badge test: no encontré SurfaceDepth');
  const component = String.raw`function IconSurfaceDepth({ danger = false }: { danger?: boolean }) {
  return (
    <>
      <View pointerEvents="none" style={[s.iconSurfaceGlow, danger && s.iconSurfaceGlowDanger]} />
      <View pointerEvents="none" style={[s.iconSurfaceSheen, danger && s.iconSurfaceSheenDanger]} />
      <View pointerEvents="none" style={s.iconSurfaceShade} />
    </>
  );
}

`;
  ui = ui.replace(marker, component + marker);
}

function injectAll(opening, child, label) {
  if (!ui.includes(opening)) throw new Error(`Monaco badge test: no encontré ${label}`);
  const replacement = `${opening}\n${child}`;
  if (!ui.includes(replacement)) ui = ui.split(opening).join(replacement);
}

injectAll('<View style={s.heroIconWrap}>', '        <IconSurfaceDepth />', 'heroIconWrap');
injectAll(
  '      <View style={[s.featureIconWrap, danger && s.featureIconDanger]}>',
  '        <IconSurfaceDepth danger={danger} />',
  'featureIconWrap',
);
injectAll(
  '      <View style={[s.wideIconWrap, danger && s.wideIconDanger]}>',
  '        <IconSurfaceDepth danger={danger} />',
  'wideIconWrap',
);

function ensureOverflow(name) {
  // Los estilos generados son de una sola línea y algunos contienen objetos
  // anidados (shadowOffset). La expresión debe tomar el cierre FINAL de la línea;
  // de lo contrario overflow terminaba dentro de shadowOffset y TypeScript fallaba.
  const re = new RegExp(`^(  ${name}: \\{.*)(\\},)$`, 'm');
  const match = ui.match(re);
  if (!match) throw new Error(`Monaco badge test: no encontré estilo ${name}`);
  if (!match[1].includes("overflow: 'hidden'")) {
    ui = ui.replace(re, `$1, overflow: 'hidden' $2`);
  }
}
ensureOverflow('heroIconWrap');
ensureOverflow('featureIconWrap');
ensureOverflow('wideIconWrap');

// TypeScript no conserva el narrowing de un estado nullable dentro de callbacks JSX.
// Aplicamos optional chaining a todas las lecturas del estado de mercado generado;
// cuando snapshot todavía es null el resultado es undefined/falsy y la UI sigue segura.
ui = ui.split('snapshot.status.market_open').join('snapshot?.status.market_open');

const styleClose = '\n});';
const stylePos = ui.lastIndexOf(styleClose);
if (stylePos < 0) throw new Error('Monaco badge test: no encontré cierre de estilos');
if (!ui.includes('  iconSurfaceGlow: {')) {
  const extra = String.raw`
  iconSurfaceGlow: { position: 'absolute', top: -18, left: -15, width: 70, height: 58, borderRadius: 34, backgroundColor: 'rgba(70,178,255,0.12)' },
  iconSurfaceGlowDanger: { backgroundColor: 'rgba(255,87,101,0.10)' },
  iconSurfaceSheen: { position: 'absolute', top: 1, left: 10, right: 10, height: 1, borderRadius: 1, backgroundColor: 'rgba(173,226,255,0.38)' },
  iconSurfaceSheenDanger: { backgroundColor: 'rgba(255,178,184,0.28)' },
  iconSurfaceShade: { position: 'absolute', left: 0, right: 0, bottom: 0, height: 20, backgroundColor: 'rgba(0,0,0,0.14)' },
`;
  ui = ui.slice(0, stylePos) + extra + ui.slice(stylePos);
}

if (!ui.includes('<ClubBadge club={club} size={62} />')) throw new Error('Monaco HD no quedó conectado al HeroClubCard');
if (!ui.includes('<IconSurfaceDepth')) throw new Error('Profundidad interna no quedó aplicada');

fs.writeFileSync(uiPath, ui);

// React Native tipa ImageBackground de forma más estricta que View y no acepta
// pointerEvents como prop directa en esta versión. La capa está detrás del contenido,
// así que retirar esa prop mantiene el fondo y desbloquea el chequeo de tipos.
const matchPath = 'src/MatchSearchShell.tsx';
let matchUi = fs.readFileSync(matchPath, 'utf8');
matchUi = matchUi.replace(
  `          <ImageBackground\n            pointerEvents="none"\n            source={BG_MATCH_SEARCH}`,
  `          <ImageBackground\n            source={BG_MATCH_SEARCH}`,
);
fs.writeFileSync(matchPath, matchUi);

console.log(`Monaco HD listo: ${width}x${height}, SHA-256 verificado + profundidad interna aplicada + build TS saneado.`);