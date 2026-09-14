import fs from 'node:fs';

const uiPath = 'src/BotParityAppV2.tsx';
let ui = fs.readFileSync(uiPath, 'utf8');

function replaceFunction(startMarker, endMarker, replacement, label) {
  const start = ui.indexOf(startMarker);
  const end = ui.indexOf(endMarker, start + startMarker.length);
  if (start < 0 || end < 0) throw new Error(`AJPA HD preview: no pude aislar ${label}`);
  ui = ui.slice(0, start) + replacement + '\n\n' + ui.slice(end);
}

function replaceStyle(name, body) {
  const re = new RegExp(`  ${name}: \\{[^\\n]*\\},`);
  if (re.test(ui)) ui = ui.replace(re, `  ${name}: { ${body} },`);
}

const bgImport = "import { BG_PERFIL } from './bg_perfil';";
const assetBlock = `const AJPA_HD_HERO = require('../assets/generated-broadcast/hero.jpg');\nconst AJPA_HD_MARKET = require('../assets/generated-broadcast/market.jpg');\nconst AJPA_HD_LEAGUE = require('../assets/generated-broadcast/league.jpg');\nconst AJPA_HD_VITRINA = require('../assets/generated-broadcast/vitrina.jpg');\nconst AJPA_HD_CUP = require('../assets/generated-broadcast/cup.jpg');\nconst AJPA_HD_RESULTS = require('../assets/generated-broadcast/results.jpg');`;
if (!ui.includes('const AJPA_HD_HERO')) {
  if (!ui.includes(bgImport)) throw new Error('AJPA HD preview: falta import base de fondos');
  ui = ui.replace(bgImport, `${bgImport}\n\n${assetBlock}`);
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
  const art = key.includes('mercado') ? AJPA_HD_MARKET
    : key === 'liga' ? AJPA_HD_LEAGUE
    : key.includes('vitrina') ? AJPA_HD_VITRINA
    : key === 'copa' ? AJPA_HD_CUP
    : null;

  return (
    <Pressable
      onPress={onPress}
      style={({ pressed }) => [s.featureTile, danger && s.featureTileDanger, pressed && { opacity: 0.82, transform: [{ scale: 0.99 }] }]}
    >
      {art ? (
        <ImageBackground source={art} style={s.featureVisual} imageStyle={s.featureVisualImage} resizeMode="cover">
          <View style={s.featureVisualShade}>
            <View style={[s.featureIconWrap, danger && s.featureIconDanger]}>
              <Text style={[s.featureEmoji, danger && { color: C.red }]}>{broadcastIcon(title, emoji)}</Text>
            </View>
            <View style={s.featureTextWrap}>
              <Text style={[s.featureTitle, danger && { color: C.red }]}>{title}</Text>
              {subtitle ? <Text style={s.featureSubtitle}>{subtitle}</Text> : null}
            </View>
            <Text style={[s.featureArrowText, danger && { color: C.red }]}>›</Text>
          </View>
        </ImageBackground>
      ) : (
        <>
          <View style={[s.featureIconWrap, danger && s.featureIconDanger]}>
            <Text style={[s.featureEmoji, danger && { color: C.red }]}>{broadcastIcon(title, emoji)}</Text>
          </View>
          <View style={s.featureTextWrap}>
            <Text style={[s.featureTitle, danger && { color: C.red }]}>{title}</Text>
            {subtitle ? <Text style={s.featureSubtitle}>{subtitle}</Text> : null}
          </View>
          <Text style={[s.featureArrowText, danger && { color: C.red }]}>›</Text>
        </>
      )}
    </Pressable>
  );
}`;
replaceFunction('function FeatureTile({', 'function QuickAction({', featureTile, 'FeatureTile');

const heroClubCard = String.raw`function HeroClubCard({
  club,
  budget,
  players,
  marketOpen,
  onPress,
}: {
  club: string;
  budget: string;
  players: number;
  marketOpen: boolean;
  onPress: () => void;
}) {
  return (
    <Pressable onPress={onPress} style={({ pressed }) => [s.heroClubCard, pressed && { opacity: 0.86 }]}>
      <ImageBackground source={AJPA_HD_HERO} style={s.heroHdVisual} imageStyle={s.heroHdImage} resizeMode="cover">
        <View style={s.heroHdShade}>
          <View style={s.heroHdCopy}>
            <Text style={s.heroHdEyebrow}>AJPA · CENTRO DE MANDO</Text>
            <Text style={s.heroHdTitle}>Viví la liga desde adentro.</Text>
            <Text style={s.heroHdSubtitle}>Mercado, competencia, club y comunidad en una sola experiencia.</Text>
            <View style={s.heroHdRule} />
            <Text style={s.heroHdMeta}>{club} · {players} jugadores · {budget}</Text>
          </View>
          <View style={s.heroHdStatus}>
            <View style={[s.heroStatusDot, { backgroundColor: marketOpen ? C.green : C.red }]} />
            <Text style={s.heroHdStatusText}>{marketOpen ? 'ABIERTO' : 'CERRADO'}</Text>
          </View>
        </View>
      </ImageBackground>
    </Pressable>
  );
}`;
replaceFunction('function HeroClubCard({', 'function RadioPasilloStrip(', heroClubCard, 'HeroClubCard');

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
  const resultArt = title.toLowerCase().includes('resultado');
  return (
    <Pressable onPress={onPress} style={({ pressed }) => [s.wideTile, danger && s.wideTileDanger, pressed && { opacity: 0.80 }]}>
      {resultArt ? (
        <ImageBackground source={AJPA_HD_RESULTS} style={s.wideHdVisual} imageStyle={s.wideHdImage} resizeMode="cover">
          <View style={s.wideHdShade}>
            <View style={[s.wideIconWrap, danger && s.wideIconDanger]}><Text style={[s.wideEmoji, danger && { color: C.red }]}>{broadcastIcon(title, emoji)}</Text></View>
            <View style={s.wideBody}>
              <Text style={[s.wideTitle, danger && { color: C.red }]}>{title}</Text>
              {subtitle ? <Text style={s.wideSubtitle}>{subtitle}</Text> : null}
            </View>
            <Text style={[s.wideArrowText, danger && { color: C.red }]}>›</Text>
          </View>
        </ImageBackground>
      ) : (
        <>
          <View style={[s.wideIconWrap, danger && s.wideIconDanger]}><Text style={[s.wideEmoji, danger && { color: C.red }]}>{broadcastIcon(title, emoji)}</Text></View>
          <View style={s.wideBody}>
            <Text style={[s.wideTitle, danger && { color: C.red }]}>{title}</Text>
            {subtitle ? <Text style={s.wideSubtitle}>{subtitle}</Text> : null}
          </View>
          <Text style={[s.wideArrowText, danger && { color: C.red }]}>›</Text>
        </>
      )}
    </Pressable>
  );
}`;
replaceFunction('function WideTile({', 'function Title({', wideTile, 'WideTile');

replaceStyle('screenBackgroundImage', `opacity: 0.06`);
replaceStyle('screenShade', `flex: 1, backgroundColor: 'rgba(1,6,11,0.77)'`);
replaceStyle('content', `padding: 14, paddingTop: 12, paddingBottom: 98, gap: 11`);
replaceStyle('featureGrid', `flexDirection: 'row', flexWrap: 'wrap', gap: 11`);
replaceStyle('featureTile', `width: '48.3%', height: 156, minHeight: 156, borderRadius: 20, borderWidth: 1, borderColor: 'rgba(73,151,207,0.64)', backgroundColor: '#06121d', overflow: 'hidden', padding: 0, shadowColor: '#000', shadowOpacity: 0.42, shadowRadius: 16, shadowOffset: { width: 0, height: 10 }, elevation: 8`);
replaceStyle('featureIconWrap', `width: 36, height: 36, borderRadius: 12, borderWidth: 1, borderColor: 'rgba(135,211,255,0.54)', backgroundColor: 'rgba(3,14,24,0.76)', alignItems: 'center', justifyContent: 'center'`);
replaceStyle('featureEmoji', `fontSize: 18, color: '#eff9ff', fontWeight: '900'`);
replaceStyle('featureTitle', `color: '#ffffff', fontSize: 17.5, fontWeight: '900', lineHeight: 21, textShadowColor: 'rgba(0,0,0,0.75)', textShadowOffset: { width: 0, height: 2 }, textShadowRadius: 5`);
replaceStyle('featureSubtitle', `color: '#c6d5df', fontSize: 10.5, lineHeight: 14, marginTop: 4, textShadowColor: 'rgba(0,0,0,0.8)', textShadowOffset: { width: 0, height: 1 }, textShadowRadius: 4`);
replaceStyle('featureArrowText', `color: '#6bc5ff', fontSize: 26, fontWeight: '700'`);
replaceStyle('quickAction', `flexGrow: 1, flexBasis: '30%', minWidth: 96, minHeight: 68, flexDirection: 'row', alignItems: 'center', borderRadius: 17, borderWidth: 1, borderColor: 'rgba(59,111,148,0.62)', backgroundColor: 'rgba(3,14,24,0.96)', paddingHorizontal: 10, paddingVertical: 9, shadowColor: '#000', shadowOpacity: 0.24, shadowRadius: 8, shadowOffset: { width: 0, height: 5 }, elevation: 4`);
replaceStyle('wideTile', `minHeight: 78, height: 78, flexDirection: 'row', alignItems: 'center', borderRadius: 19, borderWidth: 1, borderColor: 'rgba(67,139,191,0.62)', backgroundColor: '#06121d', padding: 0, overflow: 'hidden', shadowColor: '#000', shadowOpacity: 0.28, shadowRadius: 10, shadowOffset: { width: 0, height: 6 }, elevation: 5`);
replaceStyle('radioStrip', `height: 54, minHeight: 54, flexDirection: 'row', alignItems: 'center', gap: 9, borderRadius: 17, borderWidth: 1, borderColor: 'rgba(70,156,216,0.66)', backgroundColor: 'rgba(2,13,23,0.96)', paddingHorizontal: 11, paddingVertical: 7, shadowColor: '#000', shadowOpacity: 0.22, shadowRadius: 8, shadowOffset: { width: 0, height: 5 }, elevation: 3`);
replaceStyle('honourCard', `flex: 1, minWidth: 0, minHeight: 104, borderRadius: 17, borderWidth: 1, borderColor: 'rgba(56,98,128,0.58)', backgroundColor: 'rgba(3,14,24,0.93)', padding: 10, shadowColor: '#000', shadowOpacity: 0.22, shadowRadius: 8, shadowOffset: { width: 0, height: 5 }, elevation: 3`);

const close = '\n});';
const pos = ui.lastIndexOf(close);
if (pos < 0) throw new Error('AJPA HD preview: no encontré cierre de estilos');
if (!ui.includes('  featureVisual: {')) {
  const extra = String.raw`
  featureVisual: { flex: 1, width: '100%', height: '100%' },
  featureVisualImage: { borderRadius: 20 },
  featureVisualShade: { flex: 1, padding: 12, justifyContent: 'space-between', backgroundColor: 'rgba(1,7,13,0.37)' },
  heroHdVisual: { flex: 1, width: '100%', height: '100%' },
  heroHdImage: { borderRadius: 22 },
  heroHdShade: { flex: 1, flexDirection: 'row', alignItems: 'flex-end', padding: 16, backgroundColor: 'rgba(1,7,13,0.24)' },
  heroHdCopy: { flex: 1, paddingRight: 10 },
  heroHdEyebrow: { color: '#82cdfd', fontSize: 8, fontWeight: '900', letterSpacing: 1.35 },
  heroHdTitle: { color: '#ffffff', fontSize: 20, lineHeight: 23, fontWeight: '900', marginTop: 4, textShadowColor: 'rgba(0,0,0,0.82)', textShadowOffset: { width: 0, height: 2 }, textShadowRadius: 6 },
  heroHdSubtitle: { color: '#d0dee8', fontSize: 10.5, lineHeight: 14.5, marginTop: 4, maxWidth: 285, textShadowColor: 'rgba(0,0,0,0.82)', textShadowOffset: { width: 0, height: 1 }, textShadowRadius: 4 },
  heroHdRule: { width: 40, height: 3, borderRadius: 2, backgroundColor: '#38b4ff', marginTop: 10, marginBottom: 7 },
  heroHdMeta: { color: '#b9cbd8', fontSize: 7.5, fontWeight: '800', letterSpacing: 0.4 },
  heroHdStatus: { alignSelf: 'flex-end', flexDirection: 'row', alignItems: 'center', gap: 5, borderRadius: 10, backgroundColor: 'rgba(1,9,15,0.66)', paddingHorizontal: 8, paddingVertical: 6 },
  heroHdStatusText: { color: '#e9f6ff', fontSize: 7, fontWeight: '900', letterSpacing: 0.8 },
  wideHdVisual: { flex: 1, width: '100%', height: '100%' },
  wideHdImage: { borderRadius: 19 },
  wideHdShade: { flex: 1, flexDirection: 'row', alignItems: 'center', paddingHorizontal: 12, backgroundColor: 'rgba(1,8,14,0.50)' },
`;
  ui = ui.slice(0, pos) + extra + ui.slice(pos);
}

replaceStyle('heroClubCard', `height: 174, minHeight: 174, borderRadius: 22, borderWidth: 1, borderColor: 'rgba(73,165,225,0.72)', backgroundColor: '#06121d', padding: 0, overflow: 'hidden', shadowColor: '#000', shadowOpacity: 0.45, shadowRadius: 18, shadowOffset: { width: 0, height: 11 }, elevation: 9`);

fs.writeFileSync(uiPath, ui);
console.log('AJPA HD preview: visuales raster Full HD aplicados sin recortes ni módulos nativos nuevos.');
