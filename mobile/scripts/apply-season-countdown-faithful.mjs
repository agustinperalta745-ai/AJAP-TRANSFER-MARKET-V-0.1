import fs from 'node:fs';

const file = new URL('../src/SeasonCountdownBanner.tsx', import.meta.url);
let src = fs.readFileSync(file, 'utf8');

function replaceStyle(name, body) {
  const re = new RegExp(`  ${name}: \\{[^\\n]*\\},`);
  if (re.test(src)) src = src.replace(re, `  ${name}: { ${body} },`);
}

if (!src.includes('ImageBackground,')) {
  src = src.replace('  AppState,\n', '  AppState,\n  ImageBackground,\n');
}
if (!src.includes("import { BG_INICIO } from './bg_inicio';")) {
  src = src.replace("import { apiRequest } from './api';", "import { apiRequest } from './api';\nimport { BG_INICIO } from './bg_inicio';");
}

const bannerOpen = `      <View style={[styles.banner, closed && styles.bannerClosed]}>`;
const bannerReplacement = `      <ImageBackground\n        source={typeof BG_INICIO === 'string' ? { uri: BG_INICIO } : BG_INICIO}\n        style={[styles.banner, closed && styles.bannerClosed]}\n        imageStyle={styles.bannerImage}\n        resizeMode=\"cover\"\n      >\n        <View style={styles.bannerShade}>`;
if (src.includes(bannerOpen)) src = src.replace(bannerOpen, bannerReplacement);

const beforeModal = `      </View>\n\n      <Modal visible={editorOpen}`;
if (src.includes(beforeModal)) {
  src = src.replace(beforeModal, `        </View>\n      </ImageBackground>\n\n      <Modal visible={editorOpen}`);
}

replaceStyle('banner', `height: 94, minHeight: 94, marginHorizontal: 20, marginTop: 12, marginBottom: 0, borderRadius: 17, overflow: 'hidden', borderWidth: 1, borderColor: 'rgba(58,166,239,0.68)', backgroundColor: '#06121d'`);
replaceStyle('bannerClosed', `backgroundColor: '#190a0d', borderColor: 'rgba(155,58,70,0.72)'`);
replaceStyle('left', `flex: 1, minWidth: 0`);
replaceStyle('eyebrow', `color: '#76c2f7', fontSize: 8.5, fontWeight: '900', letterSpacing: 1.25`);
replaceStyle('countRow', `flexDirection: 'row', alignItems: 'baseline', gap: 8, marginTop: 3`);
replaceStyle('countValue', `color: '#f7fbff', fontSize: 20, fontWeight: '900', lineHeight: 23`);
replaceStyle('unit', `color: '#9fb1c0', fontSize: 9, fontWeight: '900'`);
replaceStyle('deadline', `color: '#a2b3c1', fontSize: 8.5, fontWeight: '700', marginTop: 2`);
replaceStyle('closedText', `color: '#ff858d', fontSize: 14, fontWeight: '900', marginTop: 3`);
replaceStyle('unset', `color: '#ffc36f', fontSize: 11, fontWeight: '900', marginTop: 4`);
replaceStyle('editButton', `height: 48, minHeight: 48, minWidth: 104, paddingHorizontal: 15, borderRadius: 13, borderWidth: 1, borderColor: '#36a6f4', alignItems: 'center', justifyContent: 'center', backgroundColor: 'rgba(3,20,34,0.72)'`);
replaceStyle('editText', `color: '#5fc2ff', fontSize: 10, fontWeight: '900', letterSpacing: 0.8`);

const styleClose = '\n});';
const stylePos = src.lastIndexOf(styleClose);
if (stylePos < 0) throw new Error('AJPA countdown faithful: cierre de estilos no encontrado');
if (!src.includes('  bannerImage: {')) {
  const extra = String.raw`
  bannerImage: { opacity: 0.72, borderRadius: 17 },
  bannerShade: { flex: 1, height: 94, flexDirection: 'row', alignItems: 'center', gap: 10, paddingHorizontal: 20, paddingVertical: 10, backgroundColor: 'rgba(2,10,17,0.43)' },
`;
  src = src.slice(0, stylePos) + extra + src.slice(stylePos);
}

if (!src.includes('<ImageBackground')) throw new Error('AJPA countdown faithful: fondo visual no aplicado');
fs.writeFileSync(file, src);
console.log('AJPA countdown faithful: proporción, estadio y botón tipo mockup aplicados.');
