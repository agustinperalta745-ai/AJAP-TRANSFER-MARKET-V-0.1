import fs from 'node:fs';
const path='src/BotParityAppV2.tsx';
let ui=fs.readFileSync(path,'utf8');
if(!ui.includes("import ResultsGallery from './ResultsGallery';")){
 ui="import ResultsGallery from './ResultsGallery';\n"+ui;
 if(!ui.includes("  | 'league'"))throw new Error('Results gallery: missing screen anchor');
 ui=ui.replace("  | 'league'","  | 'resultsGallery'\n  | 'league'");
 const anchor = /(<FeatureTile[^\n]*openScreen\('league'\)[^\n]*\n\s*<\/View>)/;
 if(!anchor.test(ui))throw new Error('Results gallery: missing Liga menu anchor');
 ui=ui.replace(anchor, `$1\n      <WideTile emoji="📸" title="RESULTADOS" subtitle="Los marcadores de todos los partidos" onPress={() => openScreen('resultsGallery')} />`);
 const dispatch="else if (screen === 'league')";
 if(!ui.includes(dispatch))throw new Error('Results gallery: missing navigation');
 ui=ui.replace(dispatch,"else if (screen === 'resultsGallery') body = <ResultsGallery />;\n  "+dispatch);
 fs.writeFileSync(path,ui);
}
console.log('AJPA Results gallery ready.');
