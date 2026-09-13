import fs from 'node:fs';

const generatedDir = new URL('../assets/generated/', import.meta.url);
fs.mkdirSync(generatedDir, { recursive: true });

const assets = {
  hero: 'hero',
  mercado: 'mercado',
  liga: 'liga',
  vitrina: 'vitrina',
  copa: 'copa',
  countdown: 'countdown',
};

for (const [key, file] of Object.entries(assets)) {
  const source = new URL(`../assets/broadcast-reference/${file}.b64`, import.meta.url);
  const target = new URL(`broadcast-${file}.webp`, generatedDir);
  const base64 = fs.readFileSync(source, 'utf8').trim();
  const bytes = Buffer.from(base64, 'base64');
  if (bytes.subarray(0, 4).toString('ascii') !== 'RIFF' || bytes.subarray(8, 12).toString('ascii') !== 'WEBP') {
    throw new Error(`AJPA faithful mockup: ${key} no es WebP válido`);
  }
  fs.writeFileSync(target, bytes);
}

fs.writeFileSync(
  new URL('../src/broadcast_reference_assets.ts', import.meta.url),
  [
    "export const REF_HERO = require('../assets/generated/broadcast-hero.webp');",
    "export const REF_MERCADO = require('../assets/generated/broadcast-mercado.webp');",
    "export const REF_LIGA = require('../assets/generated/broadcast-liga.webp');",
    "export const REF_VITRINA = require('../assets/generated/broadcast-vitrina.webp');",
    "export const REF_COPA = require('../assets/generated/broadcast-copa.webp');",
    "export const REF_COUNTDOWN = require('../assets/generated/broadcast-countdown.webp');",
    '',
  ].join('\n'),
);

const uiPath = new URL('../src/BotParityAppV2.tsx', import.meta.url);
let ui = fs.readFileSync(uiPath, 'utf8');

function replaceStyle(name, body) {
  const re = new RegExp(`  ${name}: \\{[^\\n]*\\},`);
  if (!re.test(ui)) return false;
  ui = ui.replace(re, `  ${name}: { ${body} },`);
  return true;
}

function replaceBlock(startMarker, endMarker, replacement, label) {
  const start = ui.indexOf(startMarker);
  const end = ui.indexOf(endMarker, start + startMarker.length);
  if (start < 0 || end < 0) throw new Error(`AJPA faithful mockup: no pude aislar ${label}`);
  ui = ui.slice(0, start) + replacement + '\n\n' + ui.slice(end);
}

const bgImport = "import { BG_PERFIL } from './bg_perfil';";
const refImport = "import { REF_HERO, REF_MERCADO, REF_LIGA, REF_VITRINA, REF_COPA } from './broadcast_reference_assets';";
if (!ui.includes(refImport)) {
  if (!ui.includes(bgImport)) throw new Error('AJPA faithful mockup: falta import BG_PERFIL');
  ui = ui.replace(bgImport, `${bgImport}\n${refImport}`);
}

const commandHero = String.raw`function CommandHero() {
  return (
    <View style={s.commandHero}>
      <ImageBackground source={REF_HERO} style={s.commandHeroImage} imageStyle={s.commandHeroImageAsset} resizeMode="cover">
        <View style={s.commandHeroShade}>
          <View style={s.commandHeroCopy}>
            <Text style={s.commandHeroTitle}>Centro de mando AJPA</Text>
            <Text style={s.commandHeroSubtitle}>Gestioná, competí y viví el fútbol virtual en un solo lugar.</Text>
            <View style={s.commandHeroRule} />
            <Text style={s.commandHeroMeta}>DISCIPLINA   ·   ESTRATEGIA   ·   COMUNIDAD</Text>
          </View>
          <View style={s.commandHeroTag}>
            <Text style={s.commandHeroTagText}>EL FÚTBOL</Text>
            <Text style={s.commandHeroTagText}>NOS UNE</Text>
            <View style={s.commandHeroTagRule} />
          </View>
        </View>
      </ImageBackground>
    </View>
  );
}`;

if (!ui.includes('function CommandHero()')) {
  const marker = 'function RadioPasilloStrip(';
  if (!ui.includes(marker)) throw new Error('AJPA faithful mockup: falta RadioPasilloStrip');
  ui = ui.replace(marker, commandHero + '\n\n' + marker);
}

const featureTile = String.raw`function FeatureTile({
  emoji,
  title,
  subtitle,
  onPress,
  danger = false,
}: {
  emoji: string;
  title: string;
  subtitle?: string;
  onPress: () => void;
  danger?: boolean;
}) {
  const key = title.toLowerCase();
  const art = key.includes('mercado') ? REF_MERCADO
    : key.includes('liga') ? REF_LIGA
    : key.includes('vitrina') ? REF_VITRINA
    : key.includes('copa') ? REF_COPA
    : null;
  const icon = key.includes('mercado') ? '↔'
    : key.includes('liga') ? '▥'
    : key.includes('vitrina') || key.includes('copa') ? '♜'
    : broadcastIcon(title, emoji);

  return (
    <Pressable
      onPress={onPress}
      style={({ pressed }) => [s.featureTile, danger && s.featureTileDanger, pressed && { opacity: 0.80, transform: [{ scale: 0.992 }] }]}
    >
      {art ? (
        <ImageBackground pointerEvents="none" source={art} style={s.featureArt} imageStyle={s.featureArtImage} resizeMode="cover">
          <View style={s.featureArtShade} />
        </ImageBackground>
      ) : null}
      <View style={[s.featureTopLine, danger && s.featureTopLineDanger]} />
      <View style={[s.featureIconWrap, danger && s.featureIconDanger]}>
        <Text style={[s.featureEmoji, danger && { color: C.red }]}>{icon}</Text>
      </View>
      <View style={s.featureTextWrap}>
        <Text style={[s.featureTitle, danger && { color: C.red }]}>{title}</Text>
        {subtitle ? <Text style={s.featureSubtitle}>{subtitle}</Text> : null}
      </View>
      <Text style={[s.featureArrowText, danger && { color: C.red }]}>›</Text>
    </Pressable>
  );
}`;
replaceBlock('function FeatureTile({', 'function QuickAction({', featureTile, 'FeatureTile');

const homeStart = ui.indexOf('  const home = (');
const homeEnd = ui.indexOf('  const clubMenu = (', homeStart);
if (homeStart < 0 || homeEnd < 0) throw new Error('AJPA faithful mockup: no pude aislar Inicio');
let home = ui.slice(homeStart, homeEnd);

const titleStart = home.indexOf('      <Title');
if (titleStart >= 0) {
  const titleEnd = home.indexOf('/>', titleStart);
  if (titleEnd >= 0) home = home.slice(0, titleStart) + home.slice(titleEnd + 2);
}

const heroStart = home.indexOf('      <HeroClubCard');
if (heroStart >= 0) {
  const heroEnd = home.indexOf('/>', heroStart);
  if (heroEnd < 0) throw new Error('AJPA faithful mockup: HeroClubCard sin cierre');
  home = home.slice(0, heroStart) + '      <CommandHero />' + home.slice(heroEnd + 2);
} else if (!home.includes('<CommandHero')) {
  const scrollOpen = home.indexOf('>\n', home.indexOf('<ScrollView'));
  if (scrollOpen >= 0) home = home.slice(0, scrollOpen + 2) + '      <CommandHero />\n' + home.slice(scrollOpen + 2);
}

const radioLine = home.match(/^[ \t]*<RadioPasilloStrip[^\n]*\/>\n?/m)?.[0];
if (radioLine) {
  home = home.replace(radioLine, '');
  const commandPos = home.indexOf('      <CommandHero />');
  if (commandPos >= 0) {
    const insert = commandPos + '      <CommandHero />'.length;
    home = home.slice(0, insert) + `\n${radioLine.trimEnd()}\n` + home.slice(insert);
  }
}

ui = ui.slice(0, homeStart) + home + ui.slice(homeEnd);

if (!ui.includes("if (screen === 'home') return REF_HERO;")) {
  const marker = `  const screenBackground = (() => {\n`;
  if (!ui.includes(marker)) throw new Error('AJPA faithful mockup: falta screenBackground');
  ui = ui.replace(marker, `${marker}    if (screen === 'home') return REF_HERO;\n`);
}

ui = ui.replace(
  `<View><Text style={s.brand}>AJPA</Text><Text style={s.brandSub}>LIGA · MERCADO · COMUNIDAD</Text></View>`,
  `<View style={s.brandIdentity}><Text style={s.brand}>AJPA</Text><Text style={s.brandSub}>LIGA · MERCADO · COMUNIDAD</Text></View>`,
);
ui = ui.replace(
  `<Pressable onPress={() => void openScreen('profile')} style={s.profileButton}><Text style={s.profileButtonText}>◎</Text></Pressable>`,
  `{screen === 'home' ? (\n          <View style={s.brandMotto}><Text style={s.brandMottoText}>MÁS QUE UNA LIGA</Text><Text style={s.brandMottoText}>UNA COMUNIDAD</Text></View>\n        ) : (\n          <Pressable onPress={() => void openScreen('profile')} style={s.profileButton}><Text style={s.profileButtonText}>◎</Text></Pressable>\n        )}`,
);

replaceStyle('root', `flex: 1, backgroundColor: '#020911'`);
replaceStyle('main', `flex: 1, backgroundColor: '#020911'`);
replaceStyle('content', `padding: 18, paddingTop: 16, paddingBottom: 28, gap: 14`);
replaceStyle('screenBackgroundImage', `opacity: 0.18`);
replaceStyle('screenShade', `flex: 1, backgroundColor: 'rgba(1,7,13,0.78)'`);
replaceStyle('topBar', `minHeight: 92, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: 20, paddingVertical: 14, borderBottomWidth: 1, borderBottomColor: 'rgba(55,145,209,0.42)', backgroundColor: 'rgba(1,7,13,0.98)'`);
replaceStyle('brand', `color: C.white, fontSize: 33, fontWeight: '900', letterSpacing: 1.2, lineHeight: 36`);
replaceStyle('brandSub', `color: '#3fa8ff', fontSize: 10, fontWeight: '900', letterSpacing: 2.2, marginTop: 3`);
replaceStyle('featureGrid', `flexDirection: 'row', flexWrap: 'wrap', gap: 12`);
replaceStyle('featureTile', `width: '48.4%', minHeight: 186, borderRadius: 22, borderWidth: 1.2, borderColor: 'rgba(59,155,224,0.66)', backgroundColor: 'rgba(3,18,31,0.96)', padding: 16, overflow: 'hidden', shadowColor: '#000', shadowOpacity: 0.36, shadowRadius: 14, shadowOffset: { width: 0, height: 9 }, elevation: 0`);
replaceStyle('featureTileDanger', `borderColor: 'rgba(179,69,80,0.70)', backgroundColor: 'rgba(34,8,14,0.96)'`);
replaceStyle('featureIconWrap', `width: 58, height: 58, borderRadius: 18, borderWidth: 1.1, borderColor: 'rgba(75,164,226,0.58)', backgroundColor: 'rgba(4,21,35,0.92)', alignItems: 'center', justifyContent: 'center', marginBottom: 18`);
replaceStyle('featureEmoji', `fontSize: 28, color: '#edf8ff', fontWeight: '900'`);
replaceStyle('featureTitle', `color: C.white, fontSize: 20, fontWeight: '900', lineHeight: 24`);
replaceStyle('featureSubtitle', `color: '#a7b9c9', fontSize: 12.5, lineHeight: 18, marginTop: 6`);
replaceStyle('quickAction', `flexGrow: 1, flexBasis: '30%', minWidth: 96, minHeight: 84, flexDirection: 'row', alignItems: 'center', borderRadius: 18, borderWidth: 1.1, borderColor: 'rgba(54,140,201,0.56)', backgroundColor: 'rgba(3,17,29,0.96)', paddingHorizontal: 12, paddingVertical: 11, shadowColor: '#000', shadowOpacity: 0.22, shadowRadius: 8, shadowOffset: { width: 0, height: 5 }, elevation: 0`);
replaceStyle('wideTile', `minHeight: 92, flexDirection: 'row', alignItems: 'center', borderRadius: 20, borderWidth: 1.1, borderColor: 'rgba(54,140,201,0.56)', backgroundColor: 'rgba(3,17,29,0.96)', padding: 14, overflow: 'hidden', shadowColor: '#000', shadowOpacity: 0.20, shadowRadius: 8, shadowOffset: { width: 0, height: 5 }, elevation: 0`);
replaceStyle('radioStrip', `minHeight: 62, flexDirection: 'row', alignItems: 'center', gap: 12, borderRadius: 18, borderWidth: 1, borderColor: 'rgba(58,148,211,0.62)', backgroundColor: 'rgba(2,14,25,0.96)', paddingHorizontal: 14, paddingVertical: 10, overflow: 'hidden'`);
replaceStyle('bottomNav', `minHeight: 74, flexDirection: 'row', alignItems: 'stretch', gap: 3, paddingHorizontal: 7, paddingTop: 7, paddingBottom: 6, borderTopWidth: 1, borderTopColor: 'rgba(55,145,209,0.38)', backgroundColor: 'rgba(1,7,13,0.995)'`);
replaceStyle('bottomNavItemActive', `borderColor: 'rgba(48,153,232,0.58)', backgroundColor: 'rgba(13,70,112,0.52)', shadowColor: '#168cff', shadowOpacity: 0.18, shadowRadius: 8, shadowOffset: { width: 0, height: 2 }, elevation: 0`);
replaceStyle('bottomNavIconActive', `color: '#61c2ff'`);
replaceStyle('bottomNavLabelActive', `color: '#7fd0ff'`);

const styleClose = '\n});';
const stylePos = ui.lastIndexOf(styleClose);
if (stylePos < 0) throw new Error('AJPA faithful mockup: no encontré cierre de estilos');
const extraStyles = String.raw`
  brandIdentity: { flex: 1 },
  brandMotto: { minWidth: 138, paddingLeft: 20, borderLeftWidth: 1, borderLeftColor: 'rgba(102,187,244,0.54)' },
  brandMottoText: { color: '#9bb5cb', fontSize: 8.5, fontWeight: '800', letterSpacing: 1.8, lineHeight: 14 },
  commandHero: { minHeight: 190, borderRadius: 22, overflow: 'hidden', borderWidth: 1.2, borderColor: 'rgba(58,166,239,0.72)', shadowColor: '#000', shadowOpacity: 0.38, shadowRadius: 16, shadowOffset: { width: 0, height: 10 }, elevation: 0 },
  commandHeroImage: { minHeight: 190, justifyContent: 'flex-end' },
  commandHeroImageAsset: { opacity: 0.98 },
  commandHeroShade: { flex: 1, minHeight: 190, flexDirection: 'row', alignItems: 'flex-end', padding: 18, backgroundColor: 'rgba(1,8,14,0.42)' },
  commandHeroCopy: { flex: 1, paddingRight: 16 },
  commandHeroTitle: { color: '#f8fbff', fontSize: 24, lineHeight: 28, fontWeight: '900' },
  commandHeroSubtitle: { color: '#c0cfdb', fontSize: 14, lineHeight: 20, marginTop: 5, maxWidth: 360 },
  commandHeroRule: { width: 42, height: 3, borderRadius: 2, backgroundColor: '#31aaff', marginTop: 16, marginBottom: 10 },
  commandHeroMeta: { color: '#9bb1c4', fontSize: 8.5, fontWeight: '800', letterSpacing: 1.25 },
  commandHeroTag: { width: 96, alignItems: 'flex-start', paddingBottom: 3 },
  commandHeroTagText: { color: '#b7c9d8', fontSize: 8.5, fontWeight: '900', letterSpacing: 1.3, lineHeight: 13 },
  commandHeroTagRule: { width: 29, height: 3, backgroundColor: '#31aaff', borderRadius: 2, marginTop: 8 },
  featureArt: { position: 'absolute', top: 0, right: 0, bottom: 0, width: '62%' },
  featureArtImage: { opacity: 0.88 },
  featureArtShade: { flex: 1, backgroundColor: 'rgba(1,8,14,0.35)' },
  featureTopLine: { position: 'absolute', top: 0, left: 20, width: 70, height: 3, borderBottomLeftRadius: 3, borderBottomRightRadius: 3, backgroundColor: '#42b7ff' },
  featureTopLineDanger: { backgroundColor: '#ff7d86' },
`;
if (!ui.includes('  commandHero: {')) ui = ui.slice(0, stylePos) + extraStyles + ui.slice(stylePos);

fs.writeFileSync(uiPath, ui);

const countdownPath = new URL('../src/SeasonCountdownBanner.tsx', import.meta.url);
let countdown = fs.readFileSync(countdownPath, 'utf8');
if (!countdown.includes('ImageBackground,')) {
  countdown = countdown.replace('  ActivityIndicator,\n', '  ActivityIndicator,\n  ImageBackground,\n');
}
if (!countdown.includes("REF_COUNTDOWN")) {
  countdown = countdown.replace("import { apiRequest } from './api';", "import { apiRequest } from './api';\nimport { REF_COUNTDOWN } from './broadcast_reference_assets';");
}
countdown = countdown.replace(
  `<View style={[styles.banner, closed && styles.bannerClosed]}>`,
  `<ImageBackground source={REF_COUNTDOWN} style={styles.bannerShell} imageStyle={styles.bannerImage} resizeMode="cover">\n      <View style={[styles.banner, closed && styles.bannerClosed]}>`,
);
countdown = countdown.replace(
  `      </View>\n\n      <Modal visible={editorOpen}`,
  `      </View>\n      </ImageBackground>\n\n      <Modal visible={editorOpen}`,
);
countdown = countdown.replace(
  `  banner: {\n    minHeight: 66,`,
  `  bannerShell: {\n    marginHorizontal: 14,\n    marginTop: 10,\n    marginBottom: 8,\n    borderRadius: 20,\n    overflow: 'hidden',\n    borderWidth: 1.2,\n    borderColor: 'rgba(60,161,231,0.72)',\n    backgroundColor: '#07131e',\n  },\n  bannerImage: { opacity: 0.72 },\n  banner: {\n    minHeight: 88,`,
);
countdown = countdown.replace(`    backgroundColor: '#07131e',`, `    backgroundColor: 'rgba(3,14,24,0.58)',`);
countdown = countdown.replace(`    borderBottomWidth: 1,`, `    borderBottomWidth: 0,`);
countdown = countdown.replace(`    paddingHorizontal: 15,`, `    paddingHorizontal: 18,`);
countdown = countdown.replace(`    paddingVertical: 9,`, `    paddingVertical: 13,`);
countdown = countdown.replace(`countValue: { color: '#f7fbff', fontSize: 18,`, `countValue: { color: '#f7fbff', fontSize: 22,`);
countdown = countdown.replace(`editButton: {\n    minHeight: 38,`, `editButton: {\n    minHeight: 52,`);
countdown = countdown.replace(`    minWidth: 66,`, `    minWidth: 92,`);
countdown = countdown.replace(`    borderRadius: 12,`, `    borderRadius: 17,`);
countdown = countdown.replace(`    backgroundColor: '#eaf4fb',`, `    backgroundColor: 'rgba(3,24,40,0.92)',\n    borderWidth: 1,\n    borderColor: '#35aaff',`);
countdown = countdown.replace(`editText: { color: '#07131e',`, `editText: { color: '#58baff',`);
fs.writeFileSync(countdownPath, countdown);

console.log('AJPA faithful mockup v1: assets exactos + home broadcast + countdown aplicados');
