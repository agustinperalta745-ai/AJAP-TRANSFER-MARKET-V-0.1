import fs from 'node:fs';

const uiPath = 'src/BotParityAppV2.tsx';
const countdownPath = 'src/SeasonCountdownBanner.tsx';
const adminPath = 'src/CompetitionCycleAdminFab.tsx';
const seasonsPath = 'src/SeasonHistoryFab.tsx';

let ui = fs.readFileSync(uiPath, 'utf8');

function replaceStyle(source, name, body) {
  const re = new RegExp(`  ${name}: \\{[^\\n]*\\},`);
  if (!re.test(source)) return source;
  return source.replace(re, `  ${name}: { ${body} },`);
}

function replaceFunction(source, startMarker, endMarker, replacement, label) {
  const start = source.indexOf(startMarker);
  const end = source.indexOf(endMarker, start + startMarker.length);
  if (start < 0 || end < 0) throw new Error(`AJPA exact 864: no pude aislar ${label}`);
  return source.slice(0, start) + replacement + '\n\n' + source.slice(end);
}

// Radio Pasillo: misma estructura visual que la referencia aprobada.
const radio = String.raw`function RadioPasilloStrip({ marketOpen, onPress }: { marketOpen: boolean; onPress: () => void }) {
  return (
    <Pressable onPress={onPress} style={({ pressed }) => [s.radioStrip, pressed && { opacity: 0.80 }]}>
      <View style={s.radioIconWrap}><Text style={s.radioIcon}>◉</Text></View>
      <Text style={s.radioTitle}>Radio Pasillo</Text>
      <View style={s.radioLiveDot} />
      <Text style={s.radioLive}>En vivo</Text>
      <View style={s.radioDivider} />
      <Text style={s.radioVoice} numberOfLines={1}>La voz de la comunidad AJPA</Text>
      <Text style={s.radioChevron}>›</Text>
    </Pressable>
  );
}`;
ui = replaceFunction(ui, 'function RadioPasilloStrip(', 'function Title(', radio, 'RadioPasilloStrip');

// Encabezado de últimos logros con VER TODOS, como en la captura final.
ui = ui.replace(
  /<Text style=\{s\.honoursHeading\}>[^<]*ÚLTIMOS LOGROS<\/Text>/,
  `<View style={s.honoursHeader}><Text style={s.honoursHeading}>🏆 ÚLTIMOS LOGROS</Text><Pressable onPress={() => openScreen('history')}><Text style={s.honoursSeeAll}>VER TODOS ›</Text></Pressable></View>`,
);

// Fondo general y proporciones medidas sobre la referencia 864 x 1536.
ui = replaceStyle(ui, 'root', `flex: 1, backgroundColor: '#01070d'`);
ui = replaceStyle(ui, 'main', `flex: 1, backgroundColor: '#01070d'`);
ui = replaceStyle(ui, 'content', `paddingHorizontal: 12.5, paddingTop: 4, paddingBottom: 48, gap: 5`);
ui = replaceStyle(ui, 'screenBackgroundImage', `opacity: 0.30`);
ui = replaceStyle(ui, 'screenShade', `flex: 1, backgroundColor: 'rgba(0,5,10,0.58)'`);

// Cabecera AJPA: 104 px de alto en la referencia => ~43 dp en el Moto.
ui = replaceStyle(ui, 'topBar', `height: 44, minHeight: 44, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: 18, paddingVertical: 4, borderBottomWidth: 0, backgroundColor: 'rgba(0,6,11,0.40)'`);
ui = replaceStyle(ui, 'brand', `color: C.white, fontSize: 21, fontWeight: '900', letterSpacing: 1.0, lineHeight: 23`);
ui = replaceStyle(ui, 'brandSub', `color: '#38a9ff', fontSize: 7.4, fontWeight: '900', letterSpacing: 1.75, marginTop: 1`);
ui = replaceStyle(ui, 'brandMotto', `minWidth: 92, paddingLeft: 11, borderLeftWidth: 1, borderLeftColor: 'rgba(95,183,239,0.54)'`);
ui = replaceStyle(ui, 'brandMottoText', `color: '#9fb3c5', fontSize: 6.2, fontWeight: '800', letterSpacing: 1.25, lineHeight: 9.5`);

// Hero 804x186 px => 4.32258:1 exacto.
ui = replaceStyle(ui, 'commandHero', `width: '100%', aspectRatio: 4.32258, borderRadius: 13, overflow: 'hidden', borderWidth: 1, borderColor: 'rgba(51,157,229,0.72)', backgroundColor: '#06101a'`);
ui = replaceStyle(ui, 'commandHeroImage', `flex: 1, width: '100%', height: '100%'`);
ui = replaceStyle(ui, 'commandHeroImageAsset', `opacity: 1, borderRadius: 13`);

// Radio 802x57 px => 14.07017:1.
ui = replaceStyle(ui, 'radioStrip', `width: '100%', aspectRatio: 14.07017, flexDirection: 'row', alignItems: 'center', borderRadius: 10, borderWidth: 1, borderColor: 'rgba(54,153,219,0.62)', backgroundColor: 'rgba(2,15,25,0.96)', paddingHorizontal: 8, overflow: 'hidden'`);
ui = replaceStyle(ui, 'radioIconWrap', `width: 22, height: 22, borderRadius: 7, alignItems: 'center', justifyContent: 'center', borderWidth: 1, borderColor: 'rgba(74,164,224,0.48)', backgroundColor: 'rgba(5,27,43,0.94)', marginRight: 6`);
ui = replaceStyle(ui, 'radioIcon', `color: '#6bc0ff', fontSize: 11.5, fontWeight: '900'`);
ui = replaceStyle(ui, 'radioChevron', `color: '#67b9f1', fontSize: 17, fontWeight: '700', marginLeft: 4`);

// Grid de logros: tres tarjetas 260x158 px => 1.64557:1.
ui = replaceStyle(ui, 'honoursWrap', `gap: 4`);
ui = replaceStyle(ui, 'honoursRow', `flexDirection: 'row', gap: 6`);
ui = replaceStyle(ui, 'honourRow', `flexDirection: 'row', gap: 6`);
ui = replaceStyle(ui, 'honourCard', `flex: 1, minWidth: 0, aspectRatio: 1.64557, borderRadius: 11, borderWidth: 1, borderColor: 'rgba(52,112,154,0.58)', backgroundColor: 'rgba(3,15,25,0.94)', padding: 7, overflow: 'hidden'`);
ui = replaceStyle(ui, 'honourLabel', `color: '#83cafa', fontSize: 6.4, fontWeight: '900', letterSpacing: 0.85, marginBottom: 5`);
ui = replaceStyle(ui, 'honourPrimary', `color: '#f7fbff', fontSize: 10.1, fontWeight: '900', lineHeight: 12`);
ui = replaceStyle(ui, 'honourSecondary', `color: '#edf5fa', fontSize: 7.7, fontWeight: '800', lineHeight: 9.5, marginTop: 1`);
ui = replaceStyle(ui, 'honourMeta', `color: '#8fa2b1', fontSize: 7.2, lineHeight: 9, marginTop: 2`);
ui = replaceStyle(ui, 'honourDt', `color: '#c6d3dc', fontSize: 6.8, fontWeight: '700', lineHeight: 8.5, marginTop: 1, flexShrink: 1`);

// Acciones rápidas 260x88 px => 2.95455:1.
ui = replaceStyle(ui, 'quickGrid', `flexDirection: 'row', flexWrap: 'wrap', gap: 6`);
ui = replaceStyle(ui, 'quickAction', `flexGrow: 1, flexBasis: '30%', minWidth: 0, aspectRatio: 2.95455, flexDirection: 'row', alignItems: 'center', borderRadius: 10, borderWidth: 1, borderColor: 'rgba(51,122,171,0.60)', backgroundColor: 'rgba(2,15,25,0.95)', paddingHorizontal: 7, paddingVertical: 4, overflow: 'hidden'`);
ui = replaceStyle(ui, 'quickIconWrap', `width: 26, height: 26, borderRadius: 8, borderWidth: 1, borderColor: 'rgba(69,133,177,0.54)', backgroundColor: 'rgba(5,25,40,0.94)', alignItems: 'center', justifyContent: 'center', marginRight: 6`);
ui = replaceStyle(ui, 'quickEmoji', `fontSize: 12, color: '#cde9fa', fontWeight: '900'`);
ui = replaceStyle(ui, 'quickTitle', `flex: 1, color: C.white, fontSize: 8.7, fontWeight: '800', lineHeight: 10.5`);
ui = replaceStyle(ui, 'quickChevron', `color: '#66b8ef', fontSize: 14, fontWeight: '700'`);

// Buscar jugador 804x70 px => 11.4857:1.
ui = replaceStyle(ui, 'wideTile', `width: '100%', aspectRatio: 11.4857, minHeight: 0, flexDirection: 'row', alignItems: 'center', borderRadius: 10, borderWidth: 1, borderColor: 'rgba(51,122,171,0.60)', backgroundColor: 'rgba(2,15,25,0.95)', paddingHorizontal: 8, paddingVertical: 4, overflow: 'hidden'`);
ui = replaceStyle(ui, 'wideIconWrap', `width: 26, height: 26, borderRadius: 8, borderWidth: 1, borderColor: 'rgba(69,133,177,0.54)', backgroundColor: 'rgba(5,25,40,0.94)', alignItems: 'center', justifyContent: 'center', marginRight: 7`);
ui = replaceStyle(ui, 'wideEmoji', `fontSize: 12, color: '#d8edf9', fontWeight: '900'`);
ui = replaceStyle(ui, 'wideTitle', `color: C.white, fontSize: 9.6, fontWeight: '900'`);
ui = replaceStyle(ui, 'wideSubtitle', `color: '#8fa5b6', fontSize: 7.2, lineHeight: 9, marginTop: 1`);
ui = replaceStyle(ui, 'wideArrowText', `color: '#66b8ef', fontSize: 16, fontWeight: '700'`);

// Cuatro tarjetas principales 391x182 px => 2.14835:1.
ui = replaceStyle(ui, 'featureGrid', `flexDirection: 'row', flexWrap: 'wrap', gap: 7`);
ui = replaceStyle(ui, 'featureTileReference', `width: '49%', aspectRatio: 2.14835, borderRadius: 12, overflow: 'hidden', backgroundColor: '#06101a'`);
ui = replaceStyle(ui, 'featureReferenceImage', `flex: 1, width: '100%', height: '100%'`);
ui = replaceStyle(ui, 'featureReferenceAsset', `opacity: 1, borderRadius: 12`);

// Barra inferior 864x88 px => ~37dp en el viewport del Moto.
ui = replaceStyle(ui, 'bottomNav', `height: 38, minHeight: 38, flexDirection: 'row', alignItems: 'stretch', paddingHorizontal: 5, paddingTop: 3, paddingBottom: 3, borderTopWidth: 1, borderTopColor: 'rgba(55,118,160,0.46)', backgroundColor: 'rgba(0,6,11,0.995)'`);
ui = replaceStyle(ui, 'bottomNavItem', `flex: 1, minWidth: 0, borderRadius: 8, alignItems: 'center', justifyContent: 'center', paddingVertical: 1`);
ui = replaceStyle(ui, 'bottomNavItemActive', `backgroundColor: 'rgba(12,72,114,0.56)', borderRadius: 8`);
ui = replaceStyle(ui, 'bottomNavIcon', `color: '#647a8d', fontSize: 12.5, fontWeight: '900', lineHeight: 14`);
ui = replaceStyle(ui, 'bottomNavIconActive', `color: '#61c2ff'`);
ui = replaceStyle(ui, 'bottomNavLabel', `color: '#708194', fontSize: 5.8, fontWeight: '800', marginTop: 1`);
ui = replaceStyle(ui, 'bottomNavLabelActive', `color: '#7fd0ff'`);

const styleClose = '\n});';
const stylePos = ui.lastIndexOf(styleClose);
if (stylePos < 0) throw new Error('AJPA exact 864: cierre de estilos UI no encontrado');
if (!ui.includes('  radioTitle: {')) {
  const extra = String.raw`
  radioTitle: { color: '#f6fbff', fontSize: 8.8, fontWeight: '900', marginRight: 5 },
  radioLiveDot: { width: 5, height: 5, borderRadius: 3, backgroundColor: '#24e8a1', marginRight: 3 },
  radioLive: { color: '#24e8a1', fontSize: 7.3, fontWeight: '800', marginRight: 7 },
  radioDivider: { width: 1, alignSelf: 'stretch', marginVertical: 7, backgroundColor: 'rgba(110,174,217,0.35)', marginRight: 7 },
  radioVoice: { flex: 1, color: '#bac8d4', fontSize: 7.4, fontWeight: '600' },
  honoursHeader: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', minHeight: 16 },
  honoursSeeAll: { color: '#4cb9ff', fontSize: 6.7, fontWeight: '900', letterSpacing: 0.8 },
`;
  ui = ui.slice(0, stylePos) + extra + ui.slice(stylePos);
}
ui = replaceStyle(ui, 'honoursHeading', `color: '#4db9ff', fontSize: 7.2, fontWeight: '900', letterSpacing: 1.1`);

if (!ui.includes('aspectRatio: 4.32258')) throw new Error('AJPA exact 864: hero ratio no aplicado');
if (!ui.includes('aspectRatio: 2.14835')) throw new Error('AJPA exact 864: tarjetas ratio no aplicado');
if (!ui.includes('Radio Pasillo')) throw new Error('AJPA exact 864: Radio Pasillo no aplicado');
fs.writeFileSync(uiPath, ui);

// Cuenta regresiva: 808x118 px => 6.84746:1, mismas proporciones de la captura.
let countdown = fs.readFileSync(countdownPath, 'utf8');
countdown = countdown.replace(
  /  bannerShell: \{[\s\S]*?\n  \},\n  bannerImage: \{[^\n]*\},/,
  `  bannerShell: {\n    marginHorizontal: '3.25%',\n    marginTop: 6,\n    marginBottom: 3,\n    aspectRatio: 6.84746,\n    borderRadius: 12,\n    overflow: 'hidden',\n    borderWidth: 1,\n    borderColor: 'rgba(58,166,239,0.68)',\n    backgroundColor: '#06121d',\n  },\n  bannerImage: { opacity: 0.60, borderRadius: 12 },`,
);
countdown = countdown.replace(/  banner: \{[\s\S]*?\n  \},\n  bannerClosed:/, `  banner: {\n    flex: 1,\n    flexDirection: 'row',\n    alignItems: 'center',\n    gap: 7,\n    paddingHorizontal: 14,\n    paddingVertical: 5,\n    backgroundColor: 'rgba(4,18,29,0.50)',\n  },\n  bannerClosed:`);
countdown = countdown.replace(/  eyebrow: \{[^\n]*\},/, `  eyebrow: { color: '#76c2f7', fontSize: 8.2, fontWeight: '900', letterSpacing: 1.05 },`);
countdown = countdown.replace(/  countRow: \{[^\n]*\},/, `  countRow: { flexDirection: 'row', alignItems: 'baseline', gap: 7, marginTop: 1 },`);
countdown = countdown.replace(/  countValue: \{[^\n]*\},/, `  countValue: { color: '#f7fbff', fontSize: 18.5, fontWeight: '900' },`);
countdown = countdown.replace(/  unit: \{[^\n]*\},/, `  unit: { color: '#91a6b8', fontSize: 7.5, fontWeight: '900' },`);
countdown = countdown.replace(/  deadline: \{[^\n]*\},/, `  deadline: { color: '#a2b3c1', fontSize: 7.5, fontWeight: '700', marginTop: 1 },`);
countdown = countdown.replace(/  editButton: \{[\s\S]*?\n  \},\n  editText:/, `  editButton: {\n    minHeight: 28,\n    minWidth: 72,\n    paddingHorizontal: 10,\n    borderRadius: 10,\n    alignItems: 'center',\n    justifyContent: 'center',\n    backgroundColor: 'rgba(5,27,44,0.72)',\n    borderWidth: 1,\n    borderColor: '#35aaff',\n  },\n  editText:`);
countdown = countdown.replace(/  editText: \{[^\n]*\},/, `  editText: { color: '#58baff', fontSize: 8.5, fontWeight: '900', letterSpacing: 0.6 },`);
if (!countdown.includes('aspectRatio: 6.84746')) throw new Error('AJPA exact 864: countdown ratio no aplicado');
fs.writeFileSync(countdownPath, countdown);

// Botones flotantes de la referencia: TEMPORADAS izquierda / ADMIN derecha, justo sobre la navegación.
let admin = fs.readFileSync(adminPath, 'utf8');
admin = admin.replace(/  fab: \{[\s\S]*?\n  \},\n  fabText:/, `  fab: {\n    position: 'absolute',\n    right: 9,\n    bottom: 41,\n    zIndex: 80,\n    minHeight: 30,\n    minWidth: 88,\n    borderRadius: 16,\n    paddingHorizontal: 12,\n    alignItems: 'center',\n    justifyContent: 'center',\n    backgroundColor: '#d8efff',\n    borderWidth: 1,\n    borderColor: '#62c2ff',\n    shadowColor: '#26aaff',\n    shadowOpacity: 0.28,\n    shadowRadius: 7,\n    shadowOffset: { width: 0, height: 3 },\n    elevation: 6,\n  },\n  fabText:`);
admin = admin.replace(/  fabText: \{[^\n]*\},/, `  fabText: { color: '#082338', fontSize: 9.5, fontWeight: '900', letterSpacing: 0.7 },`);
fs.writeFileSync(adminPath, admin);

let seasons = fs.readFileSync(seasonsPath, 'utf8');
seasons = seasons.replace(/  fab: \{[\s\S]*?\n  \},\n  fabText:/, `  fab: {\n    position: 'absolute',\n    left: 9,\n    bottom: 41,\n    zIndex: 88,\n    elevation: 6,\n    minHeight: 30,\n    borderWidth: 1,\n    borderColor: 'rgba(58,150,211,0.62)',\n    backgroundColor: 'rgba(6,18,29,0.96)',\n    borderRadius: 16,\n    paddingHorizontal: 12,\n    paddingVertical: 5,\n  },\n  fabText:`);
seasons = seasons.replace(/  fabText: \{[^\n]*\},/, `  fabText: { color: '#f4fbff', fontWeight: '900', fontSize: 9.3, letterSpacing: 0.4 },`);
fs.writeFileSync(seasonsPath, seasons);

console.log('AJPA exact 864: inicio, countdown, Radio Pasillo, tarjetas, FABs y navegación alineados a la referencia 864x1536.');
