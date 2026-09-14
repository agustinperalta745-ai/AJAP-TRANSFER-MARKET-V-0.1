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
  if (start < 0 || end < 0) throw new Error(`AJPA faithful v2: no pude aislar ${label}`);
  ui = ui.slice(0, start) + replacement + '\n\n' + ui.slice(end);
}

// The approved hero crop already contains its typography and composition.
// Rendering more text above it caused the duplicated/misaligned result seen on device.
const commandHero = String.raw`function CommandHero() {
  return (
    <View style={s.commandHero}>
      <ImageBackground
        source={REF_HERO}
        style={s.commandHeroImage}
        imageStyle={s.commandHeroImageAsset}
        resizeMode="cover"
      />
    </View>
  );
}`;
replaceBlock('function CommandHero()', 'function RadioPasilloStrip(', commandHero, 'CommandHero');

// For the four main cards, use the approved crop as the complete visual card.
// This preserves exactly the image, typography, lighting and depth from the mockup.
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
  const art = key === 'mercado' ? REF_MERCADO
    : key === 'liga' ? REF_LIGA
    : key.includes('vitrina de campeones') ? REF_VITRINA
    : key === 'copa' ? REF_COPA
    : null;

  if (art) {
    return (
      <Pressable
        onPress={onPress}
        style={({ pressed }) => [s.featureTileReference, pressed && { opacity: 0.82, transform: [{ scale: 0.994 }] }]}
      >
        <ImageBackground source={art} style={s.featureReferenceImage} imageStyle={s.featureReferenceAsset} resizeMode="cover" />
      </Pressable>
    );
  }

  return (
    <Pressable
      onPress={onPress}
      style={({ pressed }) => [s.featureTile, danger && s.featureTileDanger, pressed && { opacity: 0.78 }]}
    >
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

// Scale the whole home composition to the approved 941px-wide reference.
// On the target 691px device this corresponds to ~0.734x reference dimensions.
replaceStyle('content', `padding: 12, paddingTop: 10, paddingBottom: 92, gap: 9`);
replaceStyle('topBar', `height: 85, minHeight: 85, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: 18, paddingVertical: 9, borderBottomWidth: 1, borderBottomColor: 'rgba(55,145,209,0.42)', backgroundColor: 'rgba(1,7,13,0.985)'`);
replaceStyle('brand', `color: C.white, fontSize: 29, fontWeight: '900', letterSpacing: 1.1, lineHeight: 32`);
replaceStyle('brandSub', `color: '#3fa8ff', fontSize: 8.5, fontWeight: '900', letterSpacing: 1.9, marginTop: 2`);
replaceStyle('screenBackgroundImage', `opacity: 0.13`);
replaceStyle('screenShade', `flex: 1, backgroundColor: 'rgba(1,7,13,0.84)'`);
replaceStyle('featureGrid', `flexDirection: 'row', flexWrap: 'wrap', gap: 10`);
replaceStyle('featureTile', `width: '48.6%', height: 142, minHeight: 142, borderRadius: 17, borderWidth: 1, borderColor: 'rgba(58,112,151,0.62)', backgroundColor: 'rgba(3,16,27,0.97)', padding: 12, overflow: 'hidden'`);
replaceStyle('featureIconWrap', `width: 40, height: 40, borderRadius: 12, borderWidth: 1, borderColor: 'rgba(75,164,226,0.48)', backgroundColor: 'rgba(4,21,35,0.94)', alignItems: 'center', justifyContent: 'center', marginBottom: 10`);
replaceStyle('featureEmoji', `fontSize: 19, color: '#edf8ff', fontWeight: '900'`);
replaceStyle('featureTitle', `color: C.white, fontSize: 15.5, fontWeight: '900', lineHeight: 19`);
replaceStyle('featureSubtitle', `color: '#9bafc0', fontSize: 10.5, lineHeight: 14, marginTop: 4`);
replaceStyle('quickAction', `flexGrow: 1, flexBasis: '30%', minWidth: 92, height: 68, minHeight: 68, flexDirection: 'row', alignItems: 'center', borderRadius: 15, borderWidth: 1, borderColor: 'rgba(54,118,163,0.56)', backgroundColor: 'rgba(3,16,27,0.96)', paddingHorizontal: 9, paddingVertical: 8`);
replaceStyle('quickTitle', `flex: 1, color: C.white, fontSize: 10.5, fontWeight: '800', lineHeight: 13.5`);
replaceStyle('quickEmoji', `fontSize: 14, color: '#bfe3fa', fontWeight: '900'`);
replaceStyle('quickChevron', `color: '#67b9f1', fontSize: 17, fontWeight: '700'`);
replaceStyle('wideTile', `minHeight: 60, height: 60, flexDirection: 'row', alignItems: 'center', borderRadius: 15, borderWidth: 1, borderColor: 'rgba(54,118,163,0.56)', backgroundColor: 'rgba(3,16,27,0.96)', paddingHorizontal: 11, paddingVertical: 8, overflow: 'hidden'`);
replaceStyle('wideIconWrap', `width: 36, height: 36, borderRadius: 11, borderWidth: 1, borderColor: 'rgba(76,140,184,0.50)', backgroundColor: 'rgba(5,24,39,0.96)', alignItems: 'center', justifyContent: 'center', marginRight: 10`);
replaceStyle('wideEmoji', `fontSize: 16, color: '#e5f4ff', fontWeight: '900'`);
replaceStyle('wideTitle', `color: C.white, fontSize: 13.5, fontWeight: '900'`);
replaceStyle('wideSubtitle', `color: '#93a8b9', fontSize: 9.5, lineHeight: 13, marginTop: 2`);
replaceStyle('radioStrip', `height: 46, minHeight: 46, flexDirection: 'row', alignItems: 'center', gap: 8, borderRadius: 14, borderWidth: 1, borderColor: 'rgba(58,148,211,0.60)', backgroundColor: 'rgba(2,14,25,0.96)', paddingHorizontal: 10, paddingVertical: 6, overflow: 'hidden'`);
replaceStyle('radioIconWrap', `width: 30, height: 30, borderRadius: 9, alignItems: 'center', justifyContent: 'center', borderWidth: 1, borderColor: 'rgba(83,170,229,0.48)', backgroundColor: 'rgba(6,28,45,0.88)'`);
replaceStyle('radioIcon', `color: '#6bc0ff', fontSize: 15, fontWeight: '900'`);
replaceStyle('radioEyebrow', `color: '#7fc4f6', fontSize: 7.2, fontWeight: '900', letterSpacing: 1.2`);
replaceStyle('radioHeadline', `color: C.white, fontSize: 10.5, fontWeight: '800', marginTop: 1, lineHeight: 13`);
replaceStyle('radioChevron', `color: '#67b9f1', fontSize: 20, fontWeight: '700'`);
replaceStyle('bottomNav', `height: 73, minHeight: 73, flexDirection: 'row', alignItems: 'stretch', paddingHorizontal: 6, paddingTop: 5, paddingBottom: 5, borderTopWidth: 1, borderTopColor: 'rgba(57,118,160,0.48)', backgroundColor: 'rgba(1,7,13,0.995)'`);
replaceStyle('bottomNavIcon', `color: '#657889', fontSize: 18, fontWeight: '900', lineHeight: 20`);
replaceStyle('bottomNavLabel', `color: '#687b8c', fontSize: 7.5, fontWeight: '800', marginTop: 2`);
replaceStyle('bottomNavItemActive', `backgroundColor: 'rgba(13,70,112,0.48)', borderRadius: 12`);
replaceStyle('bottomNavIconActive', `color: '#61c2ff'`);
replaceStyle('bottomNavLabelActive', `color: '#7fd0ff'`);

// Compact honours cards to the same physical height as the mockup when scaled to phone width.
replaceStyle('honoursRow', `flexDirection: 'row', gap: 8`);
replaceStyle('honourRow', `flexDirection: 'row', gap: 8`);
replaceStyle('honourCard', `flex: 1, minWidth: 0, height: 124, minHeight: 124, borderRadius: 16, borderWidth: 1, borderColor: 'rgba(55,112,153,0.56)', backgroundColor: 'rgba(3,15,25,0.95)', padding: 10, overflow: 'hidden'`);
replaceStyle('honourLabel', `color: '#8acbfa', fontSize: 7.5, fontWeight: '900', letterSpacing: 1.0, marginBottom: 8`);
replaceStyle('honourPrimary', `color: '#f7fbff', fontSize: 11.5, fontWeight: '900', lineHeight: 14`);
replaceStyle('honourSecondary', `color: '#eef5fa', fontSize: 9.2, fontWeight: '800', lineHeight: 12, marginTop: 2`);
replaceStyle('honourMeta', `color: '#8b9dac', fontSize: 8.5, lineHeight: 11, marginTop: 3`);
replaceStyle('honourDt', `color: '#c4d1dc', fontSize: 8, fontWeight: '700', lineHeight: 10, marginTop: 2, flexShrink: 1`);

// Reference-derived exact visual blocks.
replaceStyle('commandHero', `height: 145, minHeight: 145, borderRadius: 17, overflow: 'hidden', borderWidth: 0, backgroundColor: '#06101a'`);
replaceStyle('commandHeroImage', `flex: 1, width: '100%', height: 145`);
replaceStyle('commandHeroImageAsset', `opacity: 1, borderRadius: 17`);
replaceStyle('brandMotto', `minWidth: 116, paddingLeft: 14, borderLeftWidth: 1, borderLeftColor: 'rgba(102,187,244,0.50)'`);
replaceStyle('brandMottoText', `color: '#9bb5cb', fontSize: 7.4, fontWeight: '800', letterSpacing: 1.55, lineHeight: 12`);

const styleClose = '\n});';
const stylePos = ui.lastIndexOf(styleClose);
if (stylePos < 0) throw new Error('AJPA faithful v2: no encontré cierre de estilos');

if (!ui.includes('  featureTileReference: {')) {
  const extra = String.raw`
  featureTileReference: { width: '48.6%', height: 142, borderRadius: 17, overflow: 'hidden', backgroundColor: '#06101a' },
  featureReferenceImage: { flex: 1, width: '100%', height: 142 },
  featureReferenceAsset: { opacity: 1, borderRadius: 17 },
`;
  ui = ui.slice(0, stylePos) + extra + ui.slice(stylePos);
}

if (!ui.includes('featureTileReference')) throw new Error('AJPA faithful v2: tarjetas de referencia no aplicadas');
if (!ui.includes('height: 145')) throw new Error('AJPA faithful v2: hero no quedó escalado');

fs.writeFileSync(uiPath, ui);
console.log('AJPA faithful mockup v2: proporciones reales del mockup + hero/tarjetas sin duplicar texto.');
