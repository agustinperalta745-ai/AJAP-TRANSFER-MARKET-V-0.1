import fs from 'node:fs';

// The mobile build is intentionally composed by ordered scripts. Attach the Liga
// history patch to the final Monaco/visual pass so it runs after every layout and
// background transformation, without changing the approved badge pipeline itself.
const finalPass = new URL('./apply-monaco-badge-test.mjs', import.meta.url);
let source = fs.readFileSync(finalPass, 'utf8');
const hook = "await import('./apply-league-match-history.mjs');";

if (!source.includes(hook)) {
  source = `${source.trimEnd()}\n\n// Add Liga match history only after the approved visual/badge pass is complete.\n${hook}\n`;
  fs.writeFileSync(finalPass, source);
}

console.log('AJPA build hook listo: historial de Liga se aplica al final del pipeline móvil.');
