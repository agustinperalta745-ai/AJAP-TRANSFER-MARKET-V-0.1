import fs from 'node:fs';

const uiPath = new URL('../src/BotParityAppV2.tsx', import.meta.url);
const clausulazoPatchPath = new URL('./apply-clausulazo-mobile.mjs', import.meta.url);

let ui = fs.readFileSync(uiPath, 'utf8');

const dispatch = `  else if (screen === 'clausulazo') body = clausulazoScreen;`;
const screenMarker = `  const clausulazoScreen = (`;

if (!ui.includes(dispatch)) {
  throw new Error('AJPA Clausulazo guard: falta el despacho de la pantalla Clausulazo');
}

if (!ui.includes(screenMarker)) {
  const patchSource = fs.readFileSync(clausulazoPatchPath, 'utf8');
  const startMarker = 'const screen = String.raw`';
  const endMarker = '`;\nui = ui.replace(marker, screen + marker);';
  const start = patchSource.indexOf(startMarker);
  if (start < 0) {
    throw new Error('AJPA Clausulazo guard: no pude localizar el bloque fuente de Clausulazo');
  }
  const contentStart = start + startMarker.length;
  const end = patchSource.indexOf(endMarker, contentStart);
  if (end < 0) {
    throw new Error('AJPA Clausulazo guard: no pude cerrar el bloque fuente de Clausulazo');
  }

  const clausulazoScreen = patchSource.slice(contentStart, end);
  const publishMarker = `  const publishScreen = (`;
  if (!ui.includes(publishMarker)) {
    throw new Error('AJPA Clausulazo guard: falta publishScreen para reinsertar Clausulazo');
  }
  ui = ui.replace(publishMarker, clausulazoScreen + publishMarker);
}

if (!ui.includes(screenMarker) || !ui.includes(dispatch)) {
  throw new Error('AJPA Clausulazo guard: la pantalla sigue incompleta después de restaurarla');
}

fs.writeFileSync(uiPath, ui);
console.log('AJPA Clausulazo guard: pantalla preservada después del layout personalizado');
