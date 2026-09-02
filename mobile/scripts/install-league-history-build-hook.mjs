import fs from 'node:fs';

// The mobile build is intentionally composed by ordered scripts. Attach the Liga
// history patch to the final Monaco/visual pass so it runs after every layout and
// background transformation, without changing the approved badge pipeline itself.
const finalPass = new URL('./apply-monaco-badge-test.mjs', import.meta.url);
let source = fs.readFileSync(finalPass, 'utf8');
const historyHook = "await import('./apply-league-match-history.mjs');";
const hardeningHook = "await import('./fix-league-history-nullable.mjs');";

if (!source.includes(historyHook)) {
  source = `${source.trimEnd()}\n\n// Add Liga match history only after the approved visual/badge pass is complete.\n${historyHook}\n`;
}
if (!source.includes(hardeningHook)) {
  source = `${source.trimEnd()}\n${hardeningHook}\n`;
}
fs.writeFileSync(finalPass, source);

console.log('AJPA build hook listo: historial de Liga se aplica al final del pipeline móvil.');
const resultsHook = "await import('./apply-results-gallery.mjs');";
if (!source.includes(resultsHook)) {
  source = `${source.trimEnd()}\n${resultsHook}\n`;
  fs.writeFileSync(finalPass, source);
}

const playerRecordHook = "await import('./apply-player-record-card.mjs');";
if (!source.includes(playerRecordHook)) {
  source = `${source.trimEnd()}\n${playerRecordHook}\n`;
  fs.writeFileSync(finalPass, source);
}

const exchangePublicationHook = "await import('./apply-exchange-publication.mjs');";
if (!source.includes(exchangePublicationHook)) {
  source = `${source.trimEnd()}\n${exchangePublicationHook}\n`;
  fs.writeFileSync(finalPass, source);
}

// Temporary build diagnostic: print the generated exchange area after the final
// card-color transformation, immediately before TypeScript validation.
const colorPass = new URL('./apply-club-player-card-colors.mjs', import.meta.url);
let colorSource = fs.readFileSync(colorPass, 'utf8');
const exchangeDebugHook = "await import('./debug-exchange-source.mjs');";
if (!colorSource.includes(exchangeDebugHook)) {
  colorSource = `${colorSource.trimEnd()}\n${exchangeDebugHook}\n`;
  fs.writeFileSync(colorPass, colorSource);
}
