import fs from 'node:fs';

const uiPath = new URL('../src/BotParityAppV2.tsx', import.meta.url);
let ui = fs.readFileSync(uiPath, 'utf8');

function replaceStyle(name, body) {
  const re = new RegExp(`  ${name}: \\{[^\\n]*\\},`);
  if (re.test(ui)) ui = ui.replace(re, `  ${name}: { ${body} },`);
}

function replaceBlock(startMarker, endMarker, replacement, label) {
  const start = ui.indexOf(startMarker);
  const end = ui.indexOf(endMarker, start + startMarker.length);
  if (start < 0 || end < 0) throw new Error(`AJPA generated visuals: no pude aislar ${label}`);
  ui = ui.slice(0, start) + replacement + '\n\n' + ui.slice(end);
}

const bgImport = "import { BG_PERFIL } from './bg_perfil';";
const visualImport = "import { HeroArt, MarketArt, LeagueArt, VitrinaArt, CupArt, ResultsArt, HomeBackdrop } from './FullHdVisuals';";
if (!ui.includes(visualImport)) {
  if (!ui.includes(bgImport)) throw new Error('AJPA generated visuals: falta BG_PERFIL');
  ui = ui.replace(bgImport, `${bgImport}\n${visualImport}`);
}

const commandHero = String.raw`function CommandHero() {
  return (
    <View style={s.commandHero}>
      <View pointerEvents="none" style={s.vectorFill}><HeroArt /></View>
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
    </View>
  );
}`;

if (!ui.includes('function CommandHero()')) {
  const marker = 'function RadioPasilloStrip(';
  if (!ui.includes(marker)) throw new Error('AJPA generated visuals: falta RadioPasilloStrip');
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
  const art = key.includes('mercado') ? <MarketArt />
    : key === 'liga' ? <LeagueArt />
    : key.includes('vitrina') ? <VitrinaArt />
    : key === 'copa' ? <CupArt />
    : null;
  return (
    <Pressable
      onPress={onPress}
      style={({ pressed }) => [s.featureTile, danger && s.featureTileDanger, pressed && { opacity: 0.78, transform: [{ scale: 0.992 }] }]}
    >
      {art ? <View pointerEvents="none" style={s.featureVisual}>{art}</View> : null}
      {art ? <View pointerEvents="none" style={s.featureShade} /> : null}
      <View style={[s.featureIconWrap, danger && s.featureIconDanger]}>
        <Text style={[s.featureEmoji, danger && { color: C.red }]}>{broadcastIcon(title, emoji)}</Text>
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

const wideTile = String.raw`function WideTile({
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
  const resultVisual = title.toLowerCase().includes('resultado');
  return (
    <Pressable
      onPress={onPress}
      style={({ pressed }) => [s.wideTile, danger && s.wideTileDanger, pressed && { opacity: 0.76 }]}
    >
      {resultVisual ? <View pointerEvents="none" style={s.wideVisual}><ResultsArt /></View> : null}
      {resultVisual ? <View pointerEvents="none" style={s.wideVisualShade} /> : null}
      <View style={[s.wideIconWrap, danger && s.wideIconDanger]}><Text style={[s.wideEmoji, danger && { color: C.red }]}>{broadcastIcon(title, emoji)}</Text></View>
      <View style={s.wideBody}>
        <Text style={[s.wideTitle, danger && { color: C.red }]}>{title}</Text>
        {subtitle ? <Text style={s.wideSubtitle}>{subtitle}</Text> : null}
      </View>
      <Text style={[s.wideArrowText, danger && { color: C.red }]}>›</Text>
    </Pressable>
  );
}`;
replaceBlock('function WideTile({', 'function Title({', wideTile, 'WideTile');

const homeStart = ui.indexOf('  const home = (');
const homeEnd = ui.indexOf('  const clubMenu = (', homeStart);
if (homeStart < 0 || homeEnd < 0) throw new Error('AJPA generated visuals: no pude aislar Inicio');
let home = ui.slice(homeStart, homeEnd);

// Keep the home clean: the branded header already explains the section.
const titleStart = home.indexOf('      <Title');
if (titleStart >= 0) {
  const titleEnd = home.indexOf('/>', titleStart);
  if (titleEnd >= 0) home = home.slice(0, titleStart) + home.slice(titleEnd + 2);
}

// Replace the data-heavy club hero only on Home with the generated visual hero.
const heroStart = home.indexOf('      <HeroClubCard');
if (heroStart >= 0) {
  const heroEnd = home.indexOf('/>', heroStart);
  if (heroEnd < 0) throw new Error('AJPA generated visuals: HeroClubCard sin cierre');
  home = home.slice(0, heroStart) + '      <CommandHero />' + home.slice(heroEnd + 2);
}

// Put Radio Pasillo immediately after the hero, like the approved layout.
const radioMatch = home.match(/^[ \t]*<RadioPasilloStrip[^\n]*\/>\n?/m)?.[0];
if (radioMatch) {
  home = home.replace(radioMatch, '');
  const heroToken = '      <CommandHero />';
  const pos = home.indexOf(heroToken);
  if (pos >= 0) {
    const insert = pos + heroToken.length;
    home = home.slice(0, insert) + `\n${radioMatch.trimEnd()}\n` + home.slice(insert);
  }
}
ui = ui.slice(0, homeStart) + home + ui.slice(homeEnd);

// Replace the home bitmap background with a generated resolution-independent backdrop.
const oldMain = `<View style={s.main}>\n        <ImageBackground source={typeof screenBackground === 'string' ? { uri: screenBackground } : screenBackground} style={s.screenBackground} imageStyle={s.screenBackgroundImage} resizeMode="cover">\n          <View style={[s.screenShade, screen === 'clausulazo' && s.clausulazoShade, screen === 'league' && s.leagueShade]}>{body}</View>\n        </ImageBackground>\n      </View>`;
const newMain = `<View style={s.main}>\n        {screen === 'home' ? (\n          <View style={s.screenBackground}>\n            <View pointerEvents="none" style={s.homeBackdrop}><HomeBackdrop /></View>\n            <View style={s.screenShade}>{body}</View>\n          </View>\n        ) : (\n          <ImageBackground source={typeof screenBackground === 'string' ? { uri: screenBackground } : screenBackground} style={s.screenBackground} imageStyle={s.screenBackgroundImage} resizeMode="cover">\n            <View style={[s.screenShade, screen === 'clausulazo' && s.clausulazoShade, screen === 'league' && s.leagueShade]}>{body}</View>\n          </ImageBackground>\n        )}\n      </View>`;
if (ui.includes(oldMain)) ui = ui.replace(oldMain, newMain);

replaceStyle('root', `flex: 1, backgroundColor: '#01060c'`);
replaceStyle('main', `flex: 1, backgroundColor: '#01060c'`);
replaceStyle('content', `padding: 12, paddingTop: 10, paddingBottom: 94, gap: 9`);
replaceStyle('topBar', `height: 84, minHeight: 84, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: 18, paddingVertical: 9, borderBottomWidth: 1, borderBottomColor: 'rgba(55,145,209,0.42)', backgroundColor: 'rgba(1,7,13,0.985)'`);
replaceStyle('brand', `color: C.white, fontSize: 29, fontWeight: '900', letterSpacing: 1.1, lineHeight: 32`);
replaceStyle('brandSub', `color: '#3fa8ff', fontSize: 8.5, fontWeight: '900', letterSpacing: 1.9, marginTop: 2`);
replaceStyle('screenBackgroundImage', `opacity: 0.10`);
replaceStyle('screenShade', `flex: 1, backgroundColor: 'rgba(1,7,13,0.36)'`);
replaceStyle('featureGrid', `flexDirection: 'row', flexWrap: 'wrap', gap: 10`);
replaceStyle('featureTile', `width: '48.6%', height: 148, minHeight: 148, borderRadius: 18, borderWidth: 1, borderColor: 'rgba(58,148,211,0.70)', backgroundColor: 'rgba(3,16,27,0.96)', padding: 12, overflow: 'hidden', shadowColor: '#000', shadowOpacity: 0.34, shadowRadius: 12, shadowOffset: { width: 0, height: 8 }, elevation: 0`);
replaceStyle('featureIconWrap', `width: 40, height: 40, borderRadius: 12, borderWidth: 1, borderColor: 'rgba(93,191,255,0.60)', backgroundColor: 'rgba(2,18,31,0.82)', alignItems: 'center', justifyContent: 'center', marginBottom: 10`);
replaceStyle('featureEmoji', `fontSize: 19, color: '#eaf7ff', fontWeight: '900'`);
replaceStyle('featureTitle', `color: C.white, fontSize: 15.5, fontWeight: '900', lineHeight: 19`);
replaceStyle('featureSubtitle', `color: '#c2d1dd', fontSize: 10.5, lineHeight: 14, marginTop: 4`);
replaceStyle('featureArrowText', `color: '#68c0fb', fontSize: 24, fontWeight: '700'`);
replaceStyle('quickAction', `flexGrow: 1, flexBasis: '30%', minWidth: 92, height: 68, minHeight: 68, flexDirection: 'row', alignItems: 'center', borderRadius: 15, borderWidth: 1, borderColor: 'rgba(54,118,163,0.64)', backgroundColor: 'rgba(3,16,27,0.94)', paddingHorizontal: 9, paddingVertical: 8, shadowColor: '#000', shadowOpacity: 0.18, shadowRadius: 7, shadowOffset: { width: 0, height: 4 }, elevation: 0`);
replaceStyle('quickTitle', `flex: 1, color: C.white, fontSize: 10.5, fontWeight: '800', lineHeight: 13.5`);
replaceStyle('quickEmoji', `fontSize: 14, color: '#bfe3fa', fontWeight: '900'`);
replaceStyle('quickChevron', `color: '#67b9f1', fontSize: 17, fontWeight: '700'`);
replaceStyle('wideTile', `minHeight: 64, height: 64, flexDirection: 'row', alignItems: 'center', borderRadius: 16, borderWidth: 1, borderColor: 'rgba(54,118,163,0.62)', backgroundColor: 'rgba(3,16,27,0.95)', paddingHorizontal: 11, paddingVertical: 8, overflow: 'hidden', shadowColor: '#000', shadowOpacity: 0.16, shadowRadius: 7, shadowOffset: { width: 0, height: 4 }, elevation: 0`);
replaceStyle('wideIconWrap', `width: 36, height: 36, borderRadius: 11, borderWidth: 1, borderColor: 'rgba(76,140,184,0.55)', backgroundColor: 'rgba(5,24,39,0.88)', alignItems: 'center', justifyContent: 'center', marginRight: 10`);
replaceStyle('wideEmoji', `fontSize: 16, color: '#e5f4ff', fontWeight: '900'`);
replaceStyle('wideTitle', `color: C.white, fontSize: 13.5, fontWeight: '900'`);
replaceStyle('wideSubtitle', `color: '#a9bdcc', fontSize: 9.5, lineHeight: 13, marginTop: 2`);
replaceStyle('wideArrowText', `color: '#67b9f1', fontSize: 23, fontWeight: '700'`);
replaceStyle('radioStrip', `height: 48, minHeight: 48, flexDirection: 'row', alignItems: 'center', gap: 8, borderRadius: 14, borderWidth: 1, borderColor: 'rgba(58,148,211,0.65)', backgroundColor: 'rgba(2,14,25,0.94)', paddingHorizontal: 10, paddingVertical: 6, overflow: 'hidden'`);
replaceStyle('radioIconWrap', `width: 30, height: 30, borderRadius: 9, alignItems: 'center', justifyContent: 'center', borderWidth: 1, borderColor: 'rgba(83,170,229,0.54)', backgroundColor: 'rgba(6,28,45,0.84)'`);
replaceStyle('radioIcon', `color: '#6bc0ff', fontSize: 15, fontWeight: '900'`);
replaceStyle('radioEyebrow', `color: '#7fc4f6', fontSize: 7.2, fontWeight: '900', letterSpacing: 1.2`);
replaceStyle('radioHeadline', `color: C.white, fontSize: 10.5, fontWeight: '800', marginTop: 1, lineHeight: 13`);
replaceStyle('radioChevron', `color: '#67b9f1', fontSize: 20, fontWeight: '700'`);
replaceStyle('bottomNav', `height: 73, minHeight: 73, flexDirection: 'row', alignItems: 'stretch', paddingHorizontal: 6, paddingTop: 5, paddingBottom: 5, borderTopWidth: 1, borderTopColor: 'rgba(57,118,160,0.48)', backgroundColor: 'rgba(1,7,13,0.995)'`);
replaceStyle('bottomNavItemActive', `backgroundColor: 'rgba(13,70,112,0.48)', borderRadius: 12`);
replaceStyle('bottomNavIconActive', `color: '#61c2ff'`);
replaceStyle('bottomNavLabelActive', `color: '#7fd0ff'`);

const styleClose = '\n});';
const stylePos = ui.lastIndexOf(styleClose);
if (stylePos < 0) throw new Error('AJPA generated visuals: no encontré cierre de estilos');
const extraStyles = String.raw`
  homeBackdrop: { ...StyleSheet.absoluteFillObject, opacity: 1 },
  vectorFill: { ...StyleSheet.absoluteFillObject },
  commandHero: { height: 160, minHeight: 160, borderRadius: 18, overflow: 'hidden', borderWidth: 1, borderColor: 'rgba(58,166,239,0.72)', backgroundColor: '#06101a', shadowColor: '#000', shadowOpacity: 0.38, shadowRadius: 16, shadowOffset: { width: 0, height: 10 }, elevation: 0 },
  commandHeroShade: { flex: 1, height: 160, flexDirection: 'row', alignItems: 'flex-end', padding: 14, backgroundColor: 'rgba(1,8,14,0.14)' },
  commandHeroCopy: { flex: 1, paddingRight: 10 },
  commandHeroTitle: { color: '#f8fbff', fontSize: 18, lineHeight: 21, fontWeight: '900' },
  commandHeroSubtitle: { color: '#d0dde7', fontSize: 10.5, lineHeight: 14.5, marginTop: 3, maxWidth: 285 },
  commandHeroRule: { width: 36, height: 3, borderRadius: 2, backgroundColor: '#31aaff', marginTop: 10, marginBottom: 7 },
  commandHeroMeta: { color: '#a8bdcd', fontSize: 6.8, fontWeight: '800', letterSpacing: 0.95 },
  commandHeroTag: { width: 78, alignItems: 'flex-start', paddingBottom: 2 },
  commandHeroTagText: { color: '#d0deea', fontSize: 7.1, fontWeight: '900', letterSpacing: 1.05, lineHeight: 10.5 },
  commandHeroTagRule: { width: 27, height: 3, backgroundColor: '#31aaff', borderRadius: 2, marginTop: 6 },
  featureVisual: { ...StyleSheet.absoluteFillObject },
  featureShade: { ...StyleSheet.absoluteFillObject, backgroundColor: 'rgba(1,8,14,0.28)' },
  wideVisual: { ...StyleSheet.absoluteFillObject },
  wideVisualShade: { ...StyleSheet.absoluteFillObject, backgroundColor: 'rgba(1,8,14,0.46)' },
`;
if (!ui.includes('  commandHero: {')) ui = ui.slice(0, stylePos) + extraStyles + ui.slice(stylePos);
else {
  // In case another layer added these names, replace only the generated set at the end.
  if (!ui.includes('  featureVisual: {')) ui = ui.slice(0, stylePos) + extraStyles + ui.slice(stylePos);
}

fs.writeFileSync(uiPath, ui);

// Countdown: generated vector background, no recropped bitmap.
const countdownPath = new URL('../src/SeasonCountdownBanner.tsx', import.meta.url);
let countdown = fs.readFileSync(countdownPath, 'utf8');
if (!countdown.includes("import { CountdownArt } from './FullHdVisuals';")) {
  countdown = countdown.replace("import { apiRequest } from './api';", "import { apiRequest } from './api';\nimport { CountdownArt } from './FullHdVisuals';");
}
const countdownOpen = `<View style={[styles.banner, closed && styles.bannerClosed]}>`;
if (countdown.includes(countdownOpen)) {
  countdown = countdown.replace(countdownOpen, `<View style={[styles.banner, closed && styles.bannerClosed]}>\n        <View pointerEvents="none" style={styles.bannerVisual}><CountdownArt /></View>\n        <View style={styles.bannerShade}>`);
  const beforeModal = `      </View>\n\n      <Modal visible={editorOpen}`;
  if (countdown.includes(beforeModal)) countdown = countdown.replace(beforeModal, `        </View>\n      </View>\n\n      <Modal visible={editorOpen}`);
}
function replaceCountdownStyle(name, body) {
  const re = new RegExp(`  ${name}: \\{[^\\n]*\\},`);
  if (re.test(countdown)) countdown = countdown.replace(re, `  ${name}: { ${body} },`);
}
replaceCountdownStyle('banner', `height: 94, minHeight: 94, marginHorizontal: 20, marginTop: 12, marginBottom: 8, borderRadius: 17, overflow: 'hidden', borderWidth: 1, borderColor: 'rgba(58,166,239,0.68)', backgroundColor: '#06121d'`);
replaceCountdownStyle('bannerClosed', `backgroundColor: '#190a0d', borderColor: 'rgba(155,58,70,0.72)'`);
replaceCountdownStyle('left', `flex: 1, minWidth: 0`);
replaceCountdownStyle('eyebrow', `color: '#76c2f7', fontSize: 8.5, fontWeight: '900', letterSpacing: 1.25`);
replaceCountdownStyle('countRow', `flexDirection: 'row', alignItems: 'baseline', gap: 8, marginTop: 3`);
replaceCountdownStyle('countValue', `color: '#f7fbff', fontSize: 20, fontWeight: '900', lineHeight: 23`);
replaceCountdownStyle('unit', `color: '#9fb1c0', fontSize: 9, fontWeight: '900'`);
replaceCountdownStyle('deadline', `color: '#a2b3c1', fontSize: 8.5, fontWeight: '700', marginTop: 2`);
replaceCountdownStyle('editButton', `height: 48, minHeight: 48, minWidth: 104, paddingHorizontal: 15, borderRadius: 13, borderWidth: 1, borderColor: '#36a6f4', alignItems: 'center', justifyContent: 'center', backgroundColor: 'rgba(3,20,34,0.62)'`);
replaceCountdownStyle('editText', `color: '#5fc2ff', fontSize: 10, fontWeight: '900', letterSpacing: 0.8`);
const countdownClose = '\n});';
const countdownStylePos = countdown.lastIndexOf(countdownClose);
if (countdownStylePos < 0) throw new Error('AJPA generated visuals: cierre de estilos countdown no encontrado');
if (!countdown.includes('  bannerVisual: {')) {
  const extra = String.raw`
  bannerVisual: { ...StyleSheet.absoluteFillObject },
  bannerShade: { flex: 1, height: 94, flexDirection: 'row', alignItems: 'center', gap: 10, paddingHorizontal: 20, paddingVertical: 10, backgroundColor: 'rgba(2,10,17,0.32)' },
`;
  countdown = countdown.slice(0, countdownStylePos) + extra + countdown.slice(countdownStylePos);
}
fs.writeFileSync(countdownPath, countdown);

console.log('AJPA generated visuals v3: arte vectorial nativo, sin recortes, resolución independiente.');
