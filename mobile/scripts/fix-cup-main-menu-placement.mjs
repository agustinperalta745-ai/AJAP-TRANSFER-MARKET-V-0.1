import fs from 'node:fs';

const uiFile = 'src/BotParityAppV2.tsx';
let ui = fs.readFileSync(uiFile, 'utf8');

// Remove any previous visual entry to Copas, regardless of where an earlier
// script inserted it. The route itself (screen === 'cupHub') is preserved.
ui = ui.replace(/^[ \t]*<[^\n>]+openScreen\('cupHub'\)[^\n]*\/>\n?/gm, '');

const homeStart = ui.indexOf('  const home = (');
const homeEnd = ui.indexOf('  const clubMenu = (', homeStart);
if (homeStart < 0 || homeEnd < 0) {
  throw new Error('Cup placement: no pude aislar el menú principal.');
}

let home = ui.slice(homeStart, homeEnd);

// Vitrina is the left card of the second row. Putting Copa immediately after it
// makes Copa the right card of that row: visually, directly below Liga.
const vitrinaLine = home.match(/^[ \t]*<FeatureTile[^\n]*title="Vitrina de campeones"[^\n]*\/>$/m)?.[0];
const ligaLine = home.match(/^[ \t]*<FeatureTile[^\n]*title="Liga"[^\n]*\/>$/m)?.[0];
const anchor = vitrinaLine ?? ligaLine;
if (!anchor) {
  throw new Error('Cup placement: no encontré Liga/Vitrina dentro del menú principal.');
}

const indent = anchor.match(/^[ \t]*/)?.[0] ?? '        ';
const cupCard = `${indent}<FeatureTile emoji="🏆" title="Copa" subtitle="Champions AJPA · Europa AJPA · brackets y resultados" onPress={() => openScreen('cupHub')} />`;
home = home.replace(anchor, `${anchor}\n${cupCard}`);
ui = ui.slice(0, homeStart) + home + ui.slice(homeEnd);

const finalHomeStart = ui.indexOf('  const home = (');
const finalHomeEnd = ui.indexOf('  const clubMenu = (', finalHomeStart);
const finalHome = ui.slice(finalHomeStart, finalHomeEnd);
const cupMatches = ui.match(/openScreen\('cupHub'\)/g) ?? [];

if (cupMatches.length !== 1) {
  throw new Error(`Cup placement: esperaba un solo acceso visual a Copas y encontré ${cupMatches.length}.`);
}
if (!finalHome.includes(cupCard)) {
  throw new Error('Cup placement: la tarjeta Copa no quedó dentro del menú principal.');
}
if (vitrinaLine && finalHome.indexOf(cupCard) <= finalHome.indexOf(vitrinaLine)) {
  throw new Error('Cup placement: Copa no quedó después de Vitrina/debajo de Liga.');
}

fs.writeFileSync(uiFile, ui);
console.log('AJPA Copas: tarjeta Copa movida al menú principal, segunda fila derecha, debajo de Liga.');
