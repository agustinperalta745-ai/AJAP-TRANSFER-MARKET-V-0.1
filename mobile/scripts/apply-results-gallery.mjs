import fs from 'node:fs';

const path = 'src/BotParityAppV2.tsx';
let ui = fs.readFileSync(path, 'utf8');

// React Native no estaba mostrando de forma confiable el JPEG de Resultados como
// data URI grande. Reconstruimos la imagen elegida por el usuario durante el build
// y la consumimos como asset local, igual que los fondos estables de Liga/Mercado.
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

fs.writeFileSync(path, ui);
console.log(`AJPA Results gallery ready with local background (${resultBytes.length} bytes).`);
