import fs from 'node:fs';

const uiPath = new URL('../src/BotParityAppV2.tsx', import.meta.url);
let ui = fs.readFileSync(uiPath, 'utf8');

function replaceStyle(name, body) {
  const re = new RegExp(`  ${name}: \\{[^\\n]*\\},`);
  if (!re.test(ui)) return false;
  ui = ui.replace(re, `  ${name}: { ${body} },`);
  return true;
}

function replaceFunction(startMarker, endMarker, replacement, label) {
  const start = ui.indexOf(startMarker);
  const end = ui.indexOf(endMarker, start + startMarker.length);
  if (start < 0 || end < 0) throw new Error(`AJPA final polish: no pude aislar ${label}.`);
  ui = ui.slice(0, start) + replacement + '\n\n' + ui.slice(end);
}

if (!ui.includes("import { BG_LIGA } from './bg_liga';")) {
  throw new Error('AJPA final polish: falta BG_LIGA; no publico una UI incompleta.');
}

const assetAnchor = "import { BG_LIGA } from './bg_liga';";
if (!ui.includes('const AJPA_CARD_VITRINA =')) {
  ui = ui.replace(
    assetAnchor,
    `${assetAnchor}\n\nconst AJPA_CARD_VITRINA = require('../assets/trophies/liga-ajpa.jpg');\nconst AJPA_CARD_COPA = require('../assets/trophies/champions-ajpa-banner.jpg');`,
  );
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
  const art = key === 'mercado' ? BG_MERCADO
    : key === 'liga' ? BG_LIGA
    : key.includes('vitrina') ? AJPA_CARD_VITRINA
    : key === 'copa' ? AJPA_CARD_COPA
    : null;

  const content = (
    <View style={s.featurePhotoShade}>
      <View style={[s.featureIconWrap, danger && s.featureIconDanger]}>
        <Text style={s.featureEmoji}>{emoji}</Text>
      </View>
      <View style={s.featureTextWrap}>
        <Text style={[s.featureTitle, danger && { color: C.red }]}>{title}</Text>
        {subtitle ? <Text style={s.featureSubtitle}>{subtitle}</Text> : null}
      </View>
      <View style={[s.featureArrow, danger && { borderColor: '#74323a' }]}>
        <Text style={[s.featureArrowText, danger && { color: C.red }]}>›</Text>
      </View>
    </View>
  );

  return (
    <Pressable
      onPress={onPress}
      style={({ pressed }) => [s.featureTile, danger && s.featureTileDanger, pressed && { opacity: 0.82, transform: [{ scale: 0.99 }] }]}
    >
      {art ? (
        <ImageBackground
          source={typeof art === 'string' ? { uri: art } : art}
          style={s.featurePhoto}
          imageStyle={s.featurePhotoImage}
          resizeMode="cover"
        >
          {content}
        </ImageBackground>
      ) : content}
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
    <Pressable onPress={onPress} style={({ pressed }) => [s.heroClubCard, pressed && { opacity: 0.86, transform: [{ scale: 0.994 }] }]}>
      <ImageBackground source={{ uri: BG_INICIO }} style={s.heroPhoto} imageStyle={s.heroPhotoImage} resizeMode="cover">
        <View style={s.heroPhotoShade}>
          <View style={s.heroBody}>
            <Text style={s.heroKicker}>AJPA · CENTRO DE MANDO</Text>
            <Text style={s.heroClubName}>{club}</Text>
            <View style={s.heroStatsRow}>
              <View style={s.heroStat}><Text style={s.heroStatLabel}>PRESUPUESTO</Text><Text style={s.heroStatValue}>{budget}</Text></View>
              <View style={s.heroDivider} />
              <View style={s.heroStat}><Text style={s.heroStatLabel}>PLANTILLA</Text><Text style={s.heroStatValue}>{players} jugadores</Text></View>
            </View>
            <View style={s.heroStatusRow}>
              <View style={[s.heroStatusDot, { backgroundColor: marketOpen ? C.green : C.red }]} />
              <Text style={[s.heroStatusText, { color: marketOpen ? C.green : C.red }]}>{marketOpen ? 'Mercado abierto' : 'Mercado cerrado'}</Text>
            </View>
          </View>
          <View style={s.heroOpenPill}><Text style={s.heroOpenPillText}>›</Text></View>
        </View>
      </ImageBackground>
    </Pressable>
  );
}`;

const heroStart = ui.indexOf('function HeroClubCard({');
if (heroStart < 0) throw new Error('AJPA final polish: falta HeroClubCard.');
const heroEndCandidates = ['function WideTile({', 'function RadioPasilloStrip(', 'function Title({']
  .map((marker) => ({ marker, pos: ui.indexOf(marker, heroStart + 1) }))
  .filter((entry) => entry.pos > heroStart)
  .sort((a, b) => a.pos - b.pos);
if (!heroEndCandidates.length) throw new Error('AJPA final polish: no encontré fin de HeroClubCard.');
replaceFunction('function HeroClubCard({', heroEndCandidates[0].marker, heroClubCard, 'HeroClubCard');

replaceStyle('screenBackgroundImage', `opacity: 0.34`);
replaceStyle('screenShade', `flex: 1, backgroundColor: 'rgba(1,6,11,0.62)'`);
replaceStyle('content', `padding: 14, paddingTop: 12, paddingBottom: 108, gap: 12`);
replaceStyle('topBar', `height: 62, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: 14, borderBottomWidth: 1, borderBottomColor: 'rgba(79,152,199,0.26)', backgroundColor: 'rgba(1,7,12,0.97)', shadowColor: '#000', shadowOpacity: 0.32, shadowRadius: 10, shadowOffset: { width: 0, height: 6 }, elevation: 2`);
replaceStyle('heroClubCard', `height: 178, minHeight: 178, borderRadius: 23, borderWidth: 1, borderColor: 'rgba(82,174,232,0.62)', backgroundColor: '#06121d', padding: 0, overflow: 'hidden', shadowColor: '#000', shadowOpacity: 0.44, shadowRadius: 18, shadowOffset: { width: 0, height: 11 }, elevation: 4`);
replaceStyle('featureTile', `width: '48.4%', height: 174, minHeight: 174, borderRadius: 21, borderWidth: 1, borderColor: 'rgba(76,152,203,0.56)', backgroundColor: 'rgba(3,13,22,0.96)', padding: 0, overflow: 'hidden', shadowColor: '#000', shadowOpacity: 0.38, shadowRadius: 14, shadowOffset: { width: 0, height: 9 }, elevation: 3`);
replaceStyle('featureTileDanger', `borderColor: 'rgba(178,78,89,0.62)', backgroundColor: 'rgba(28,8,13,0.96)', shadowColor: '#000', shadowOpacity: 0.34, shadowRadius: 12, shadowOffset: { width: 0, height: 8 }, elevation: 3`);
replaceStyle('featureIconWrap', `width: 43, height: 43, borderRadius: 14, borderWidth: 1, borderColor: 'rgba(139,211,255,0.52)', backgroundColor: 'rgba(2,12,20,0.70)', alignItems: 'center', justifyContent: 'center', shadowColor: '#000', shadowOpacity: 0.28, shadowRadius: 7, shadowOffset: { width: 0, height: 4 }, elevation: 2`);
replaceStyle('featureTitle', `color: '#ffffff', fontSize: 18, fontWeight: '900', lineHeight: 21, textShadowColor: 'rgba(0,0,0,0.88)', textShadowOffset: { width: 0, height: 2 }, textShadowRadius: 6`);
replaceStyle('featureSubtitle', `color: '#cbd9e3', fontSize: 10.5, lineHeight: 14.5, marginTop: 4, textShadowColor: 'rgba(0,0,0,0.9)', textShadowOffset: { width: 0, height: 1 }, textShadowRadius: 5`);
replaceStyle('quickAction', `flexGrow: 1, flexBasis: '30%', minWidth: 96, minHeight: 72, flexDirection: 'row', alignItems: 'center', borderRadius: 18, borderWidth: 1, borderColor: 'rgba(61,119,157,0.48)', backgroundColor: 'rgba(3,14,23,0.92)', paddingHorizontal: 11, paddingVertical: 10, shadowColor: '#000', shadowOpacity: 0.28, shadowRadius: 9, shadowOffset: { width: 0, height: 6 }, elevation: 2`);
replaceStyle('quickActionDanger', `borderColor: 'rgba(151,69,79,0.50)', backgroundColor: 'rgba(28,9,13,0.94)', shadowColor: '#000', shadowOpacity: 0.26, shadowRadius: 8, shadowOffset: { width: 0, height: 5 }, elevation: 2`);
replaceStyle('wideTile', `minHeight: 92, flexDirection: 'row', alignItems: 'center', borderRadius: 20, borderWidth: 1, borderColor: 'rgba(67,132,176,0.48)', backgroundColor: 'rgba(3,14,23,0.94)', padding: 13, overflow: 'hidden', shadowColor: '#000', shadowOpacity: 0.30, shadowRadius: 11, shadowOffset: { width: 0, height: 7 }, elevation: 2`);
replaceStyle('honourCard', `flex: 1, minWidth: 0, minHeight: 118, borderRadius: 18, borderWidth: 1, borderColor: 'rgba(61,108,139,0.42)', backgroundColor: 'rgba(3,13,21,0.91)', padding: 11, shadowColor: '#000', shadowOpacity: 0.28, shadowRadius: 9, shadowOffset: { width: 0, height: 6 }, elevation: 2`);
replaceStyle('radioStrip', `minHeight: 62, flexDirection: 'row', alignItems: 'center', gap: 10, borderRadius: 18, borderWidth: 1, borderColor: 'rgba(70,150,207,0.54)', backgroundColor: 'rgba(2,12,21,0.94)', paddingHorizontal: 12, paddingVertical: 9, shadowColor: '#000', shadowOpacity: 0.30, shadowRadius: 10, shadowOffset: { width: 0, height: 6 }, elevation: 2`);
replaceStyle('card', `borderRadius: 20, borderWidth: 1, borderColor: 'rgba(59,105,136,0.42)', backgroundColor: 'rgba(4,14,23,0.92)', padding: 14, gap: 9, shadowColor: '#000', shadowOpacity: 0.26, shadowRadius: 9, shadowOffset: { width: 0, height: 6 }, elevation: 2`);
replaceStyle('menuTile', `minHeight: 78, flexDirection: 'row', alignItems: 'center', gap: 12, borderRadius: 18, borderWidth: 1, borderColor: 'rgba(59,105,136,0.42)', backgroundColor: 'rgba(4,14,23,0.92)', paddingHorizontal: 13, paddingVertical: 12, shadowColor: '#000', shadowOpacity: 0.24, shadowRadius: 8, shadowOffset: { width: 0, height: 5 }, elevation: 2`);

const styleClose = '\n});';
const stylePos = ui.lastIndexOf(styleClose);
if (stylePos < 0) throw new Error('AJPA final polish: no encontré cierre de estilos.');
if (!ui.includes('  featurePhoto: {')) {
  const extra = String.raw`
  featurePhoto: { flex: 1, width: '100%', height: '100%' },
  featurePhotoImage: { borderRadius: 21 },
  featurePhotoShade: { flex: 1, padding: 13, justifyContent: 'space-between', backgroundColor: 'rgba(1,7,12,0.48)' },
  heroPhoto: { flex: 1, width: '100%', height: '100%' },
  heroPhotoImage: { borderRadius: 23 },
  heroPhotoShade: { flex: 1, flexDirection: 'row', alignItems: 'flex-end', padding: 16, backgroundColor: 'rgba(1,7,12,0.38)' },
  heroKicker: { color: '#77c6f7', fontSize: 8, fontWeight: '900', letterSpacing: 1.45, marginBottom: 4, textShadowColor: 'rgba(0,0,0,0.85)', textShadowOffset: { width: 0, height: 1 }, textShadowRadius: 4 },
  heroOpenPill: { width: 38, height: 38, borderRadius: 19, borderWidth: 1, borderColor: 'rgba(116,203,255,0.56)', backgroundColor: 'rgba(2,12,20,0.62)', alignItems: 'center', justifyContent: 'center', marginLeft: 10 },
  heroOpenPillText: { color: '#8fd3ff', fontSize: 28, fontWeight: '600', lineHeight: 30 },
`;
  ui = ui.slice(0, stylePos) + extra + ui.slice(stylePos);
}

if (!ui.includes("openScreen('admin')") || !ui.includes('const adminMenu = (')) {
  throw new Error('AJPA final polish: detecté pérdida del panel Admin; cancelo publicación.');
}
if (!ui.includes('AJPA_CARD_VITRINA') || !ui.includes('featurePhotoShade') || !ui.includes('heroPhotoShade')) {
  throw new Error('AJPA final polish: la capa visual no quedó completa.');
}

fs.writeFileSync(uiPath, ui);
console.log('AJPA final polish: profundidad, fondos existentes y jerarquía premium aplicados sin tocar Admin ni generar imágenes.');
