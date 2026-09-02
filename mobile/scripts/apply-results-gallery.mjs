import fs from 'node:fs';

const path = 'src/BotParityAppV2.tsx';
let ui = fs.readFileSync(path, 'utf8');

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

if (!ui.includes("screen === 'resultsGallery'")) {
  const dispatch = "else if (screen === 'league')";
  if (!ui.includes(dispatch)) throw new Error('Results gallery: missing navigation');
  ui = ui.replace(dispatch, "else if (screen === 'resultsGallery') body = <ResultsGallery />;\n  " + dispatch);
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
console.log('AJPA Results gallery ready with its dedicated background.');
