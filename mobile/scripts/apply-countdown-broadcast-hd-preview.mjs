import fs from 'node:fs';

const path = 'src/SeasonCountdownBanner.tsx';
let src = fs.readFileSync(path, 'utf8');

if (!src.includes('ImageBackground,')) {
  src = src.replace('  AppState,\n', '  AppState,\n  ImageBackground,\n');
}
if (!src.includes('const AJPA_COUNTDOWN_HD')) {
  src = src.replace("import { apiRequest } from './api';", "import { apiRequest } from './api';\n\nconst AJPA_COUNTDOWN_HD = require('../assets/generated-broadcast/countdown.jpg');");
}

const open = '      <View style={[styles.banner, closed && styles.bannerClosed]}>';
if (src.includes(open)) {
  src = src.replace(open, '      <ImageBackground source={AJPA_COUNTDOWN_HD} style={[styles.banner, closed && styles.bannerClosed]} imageStyle={styles.bannerImage} resizeMode="cover">\n        <View style={styles.bannerShade}>');
  const close = '      </View>\n\n      <Modal visible={editorOpen}';
  if (!src.includes(close)) throw new Error('Countdown HD preview: no encontré cierre del banner');
  src = src.replace(close, '        </View>\n      </ImageBackground>\n\n      <Modal visible={editorOpen}');
}

const bannerRe = /  banner: \{[\s\S]*?\n  \},\n  bannerClosed:/;
if (bannerRe.test(src)) {
  src = src.replace(bannerRe, `  banner: {\n    minHeight: 94,\n    marginHorizontal: 20,\n    marginTop: 12,\n    marginBottom: 8,\n    borderRadius: 18,\n    overflow: 'hidden',\n    borderWidth: 1,\n    borderColor: 'rgba(67,157,216,0.66)',\n    backgroundColor: '#06121d',\n    shadowColor: '#000',\n    shadowOpacity: 0.30,\n    shadowRadius: 12,\n    shadowOffset: { width: 0, height: 7 },\n    elevation: 6,\n  },\n  bannerClosed:`);
}

const styleClose = '\n});';
const pos = src.lastIndexOf(styleClose);
if (pos < 0) throw new Error('Countdown HD preview: cierre de estilos no encontrado');
if (!src.includes('  bannerImage: {')) {
  const extra = `\n  bannerImage: { borderRadius: 18 },\n  bannerShade: { minHeight: 94, flexDirection: 'row', alignItems: 'center', gap: 10, paddingHorizontal: 18, paddingVertical: 10, backgroundColor: 'rgba(1,8,14,0.36)' },\n`;
  src = src.slice(0, pos) + extra + src.slice(pos);
}

fs.writeFileSync(path, src);
console.log('AJPA HD preview: countdown Full HD aplicado.');
