import fs from 'node:fs';

const uiFile = 'src/BotParityAppV2.tsx';
let ui = fs.readFileSync(uiFile, 'utf8');

const titleMarker = 'function Title({ eyebrow, title, subtitle }: { eyebrow: string; title: string; subtitle?: string }) {';
if (!ui.includes(titleMarker)) throw new Error('AJPA exact compat: Title no encontrado');

if (!ui.includes('function RadioPasilloStrip(')) {
  const radio = String.raw`function RadioPasilloStrip({ marketOpen, onPress }: { marketOpen: boolean; onPress: () => void }) {
  return (
    <Pressable onPress={onPress} style={({ pressed }) => [s.radioStrip, pressed && { opacity: 0.80 }]}>
      <View style={s.radioIconWrap}><Text style={s.radioIcon}>◉</Text></View>
      <View style={s.flex}>
        <Text style={s.radioEyebrow}>RADIO PASILLO</Text>
        <Text style={s.radioHeadline}>{marketOpen ? 'Mercado abierto · noticias de la liga' : 'Mercado cerrado · noticias de la liga'}</Text>
      </View>
      <Text style={s.radioChevron}>›</Text>
    </Pressable>
  );
}`;
  ui = ui.replace(titleMarker, radio + '\n\n' + titleMarker);
}

const homeStart = ui.indexOf('  const home = (');
const homeEnd = ui.indexOf('  const clubMenu = (', homeStart);
if (homeStart < 0 || homeEnd < 0) throw new Error('AJPA exact compat: Inicio no encontrado');
let home = ui.slice(homeStart, homeEnd);
if (!home.includes('<RadioPasilloStrip')) {
  const heroMatch = home.match(/([ \t]*<HeroClubCard[\s\S]*?\/>)/m);
  if (!heroMatch) throw new Error('AJPA exact compat: HeroClubCard no encontrado en Inicio');
  home = home.replace(heroMatch[1], `${heroMatch[1]}\n\n      <RadioPasilloStrip marketOpen={snapshot.status.market_open} onPress={() => openScreen('market')} />`);
  ui = ui.slice(0, homeStart) + home + ui.slice(homeEnd);
}

const styleClose = '\n});';
const stylePos = ui.lastIndexOf(styleClose);
if (stylePos < 0) throw new Error('AJPA exact compat: cierre de estilos no encontrado');
if (!ui.includes('  radioStrip: {')) {
  const styles = String.raw`
  radioStrip: { minHeight: 46, flexDirection: 'row', alignItems: 'center', borderRadius: 10, borderWidth: 1, borderColor: 'rgba(54,153,219,0.62)', backgroundColor: 'rgba(2,15,25,0.96)', paddingHorizontal: 8 },
  radioIconWrap: { width: 22, height: 22, borderRadius: 7, alignItems: 'center', justifyContent: 'center', borderWidth: 1, borderColor: 'rgba(74,164,224,0.48)', backgroundColor: 'rgba(5,27,43,0.94)', marginRight: 6 },
  radioIcon: { color: '#6bc0ff', fontSize: 11.5, fontWeight: '900' },
  radioEyebrow: { color: '#7fc4f6', fontSize: 7, fontWeight: '900', letterSpacing: 1.1 },
  radioHeadline: { color: '#f7fbff', fontSize: 9, fontWeight: '800', marginTop: 1 },
  radioChevron: { color: '#67b9f1', fontSize: 17, fontWeight: '700', marginLeft: 4 },
`;
  ui = ui.slice(0, stylePos) + styles + ui.slice(stylePos);
}
fs.writeFileSync(uiFile, ui);

// El componente estable de cuenta regresiva no tenía el wrapper fotográfico que
// usa la referencia. Se agrega solo con componentes nativos ya incluidos.
const countdownFile = 'src/SeasonCountdownBanner.tsx';
let countdown = fs.readFileSync(countdownFile, 'utf8');
if (!countdown.includes('ImageBackground,')) {
  countdown = countdown.replace('  AppState,\n', '  AppState,\n  ImageBackground,\n');
}
if (!countdown.includes("import { BG_INICIO } from './bg_inicio';")) {
  countdown = countdown.replace("import { apiRequest } from './api';", "import { apiRequest } from './api';\nimport { BG_INICIO } from './bg_inicio';");
}
if (!countdown.includes('style={styles.bannerShell}')) {
  const open = `      <View style={[styles.banner, closed && styles.bannerClosed]}>`;
  if (!countdown.includes(open)) throw new Error('AJPA exact compat: banner countdown no encontrado');
  countdown = countdown.replace(open, `      <ImageBackground\n        source={typeof BG_INICIO === 'string' ? { uri: BG_INICIO } : BG_INICIO}\n        style={styles.bannerShell}\n        imageStyle={styles.bannerImage}\n        resizeMode="cover"\n      >\n        <View style={[styles.banner, closed && styles.bannerClosed]}>`);
  const closeAnchor = `      </View>\n\n      <Modal visible={editorOpen}`;
  if (!countdown.includes(closeAnchor)) throw new Error('AJPA exact compat: cierre banner countdown no encontrado');
  countdown = countdown.replace(closeAnchor, `        </View>\n      </ImageBackground>\n\n      <Modal visible={editorOpen}`);
}
const countdownStyleMarker = 'const styles = StyleSheet.create({\n';
if (!countdown.includes('  bannerShell: {')) {
  if (!countdown.includes(countdownStyleMarker)) throw new Error('AJPA exact compat: StyleSheet countdown no encontrado');
  countdown = countdown.replace(countdownStyleMarker, countdownStyleMarker + `  bannerShell: { marginHorizontal: '3.25%', marginTop: 6, marginBottom: 3, aspectRatio: 6.84746, borderRadius: 12, overflow: 'hidden', borderWidth: 1, borderColor: 'rgba(58,166,239,0.68)', backgroundColor: '#06121d' },\n  bannerImage: { opacity: 0.60, borderRadius: 12 },\n`);
}
fs.writeFileSync(countdownFile, countdown);

console.log('AJPA exact compat: Radio Pasillo y countdown preparados sobre la base estable.');
