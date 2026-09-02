import fs from 'node:fs';

const path = 'src/BotParityAppV2.tsx';
let ui = fs.readFileSync(path, 'utf8');

// Reconstruimos la imagen elegida por el usuario durante el build y la dejamos
// como asset local real. De esta forma Resultados no depende de red, Railway ni
// GitHub para mostrar el fondo.
const resultParts = [0, 1, 2, 3].map((index) => {
  const source = fs.readFileSync(
    new URL(`../src/bg_resultados_part${index}.ts`, import.meta.url),
    'utf8',
  );
  const match = source.match(/=\s*'([A-Za-z0-9+/=]+)'\s*;/);
  if (!match) throw new Error(`Results gallery: invalid background part ${index}`);
  return match[1];
});

const resultBytes = Buffer.from(resultParts.join(''), 'base64');
if (
  resultBytes.length < 1024 ||
  resultBytes[0] !== 0xff ||
  resultBytes[1] !== 0xd8 ||
  resultBytes[2] !== 0xff
) {
  throw new Error('Results gallery: reconstructed background is not a valid JPEG');
}

const generatedDir = new URL('../assets/generated/', import.meta.url);
fs.mkdirSync(generatedDir, { recursive: true });
fs.writeFileSync(new URL('results-pique-5-1.jpg', generatedDir), resultBytes);
fs.writeFileSync(
  new URL('../src/bg_resultados.ts', import.meta.url),
  "export const BG_RESULTADOS = require('../assets/generated/results-pique-5-1.jpg');\n",
);

// ResultsGallery debe consumir BG_RESULTADOS como ImageSourcePropType. Un require
// de React Native devuelve un id numérico; envolverlo como { uri: ... } lo rompe
// y deja la pantalla negra. Este guard evita que vuelva a aparecer ese error.
const galleryPath = new URL('../src/ResultsGallery.tsx', import.meta.url);
let gallery = fs.readFileSync(galleryPath, 'utf8');
const resultImport = "import { BG_RESULTADOS } from './bg_resultados';";
if (!gallery.includes(resultImport)) {
  const apiImport = "import { apiRequest } from './api';";
  if (!gallery.includes(apiImport)) throw new Error('Results gallery: missing API import anchor');
  gallery = gallery.replace(apiImport, `${apiImport}\n${resultImport}`);
}

const localSource = `const RESULTS_BACKGROUND = typeof BG_RESULTADOS === 'number'\n ? BG_RESULTADOS\n : { uri: BG_RESULTADOS };`;
if (!gallery.includes(localSource)) {
  const sourceBlock = /const RESULTS_BACKGROUND\s*=\s*[\s\S]*?;\n\nexport default function ResultsGallery/;
  if (!sourceBlock.test(gallery)) throw new Error('Results gallery: missing background source block');
  gallery = gallery.replace(
    sourceBlock,
    `${localSource}\n\nexport default function ResultsGallery`,
  );
}
fs.writeFileSync(galleryPath, gallery);

if (!ui.includes("import ResultsGallery from './ResultsGallery';")) {
  ui = "import ResultsGallery from './ResultsGallery';\n" + ui;
}

if (!ui.includes("import { BG_RESULTADOS } from './bg_resultados';")) {
  const bgAnchor = "import { BG_PERFIL } from './bg_perfil';";
  if (!ui.includes(bgAnchor)) throw new Error('Results gallery: missing background import anchor');
  ui = ui.replace(bgAnchor, `${bgAnchor}\nimport { BG_RESULTADOS } from './bg_resultados';`);
}

if (!ui.includes("  | 'resultsGallery'")) {
  if (!ui.includes("  | 'league'")) throw new Error('Results gallery: missing screen anchor');
  ui = ui.replace("  | 'league'", "  | 'resultsGallery'\n  | 'league'");
}

if (!ui.includes('title="RESULTADOS"')) {
  const anchor = /(<FeatureTile[^\n]*openScreen\('league'\)[^\n]*\n\s*<\/View>)/;
  if (!anchor.test(ui)) throw new Error('Results gallery: missing Liga menu anchor');
  ui = ui.replace(anchor, `$1\n      <WideTile emoji="📸" title="RESULTADOS" subtitle="Los marcadores de todos los partidos" onPress={() => openScreen('resultsGallery')} />`);
}

const resultsDispatch = "else if (screen === 'resultsGallery') body = <ResultsGallery />;";
if (!ui.includes(resultsDispatch)) {
  const dispatch = "else if (screen === 'league')";
  if (!ui.includes(dispatch)) throw new Error('Results gallery: missing navigation');
  ui = ui.replace(dispatch, `${resultsDispatch}\n  ${dispatch}`);
}

if (!ui.includes("if (screen === 'resultsGallery') return BG_RESULTADOS;")) {
  const backgroundAnchor = "  const screenBackground = (() => {";
  if (!ui.includes(backgroundAnchor)) throw new Error('Results gallery: missing screen background function');
  ui = ui.replace(
    backgroundAnchor,
    `${backgroundAnchor}\n    if (screen === 'resultsGallery') return BG_RESULTADOS;`,
  );
}

// BG_RESULTADOS es un require(...) numérico en producción. Las demás pantallas
// usan strings/data URI. ImageBackground debe recibir cada tipo en su forma real.
const safeSource = "source={typeof screenBackground === 'number' ? screenBackground : { uri: screenBackground }}";
if (!ui.includes(safeSource)) {
  const legacySource = 'source={{ uri: screenBackground }}';
  if (!ui.includes(legacySource)) throw new Error('Results gallery: missing ImageBackground source anchor');
  ui = ui.replace(legacySource, safeSource);
}

fs.writeFileSync(path, ui);
console.log(`AJPA Results gallery ready with local background (${resultBytes.length} bytes).`);
