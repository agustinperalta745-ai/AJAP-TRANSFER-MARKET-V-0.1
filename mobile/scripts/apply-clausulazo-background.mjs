import fs from 'node:fs';

const path = 'src/BotParityAppV2.tsx';
let ui = fs.readFileSync(path, 'utf8');

function replaceOnce(from, to, label) {
  if (ui.includes(to)) return;
  if (!ui.includes(from)) throw new Error(`Clausulazo background patch: no se encontró ${label}`);
  ui = ui.replace(from, to);
}

replaceOnce(
  `import { BG_PERFIL } from './bg_perfil';`,
  `import { BG_PERFIL } from './bg_perfil';\nimport { BG_CLAUSULAZO } from './bg_clausulazo';`,
  'import de BG_CLAUSULAZO',
);

replaceOnce(
  `    if (['market', 'publish', 'clausulazo', 'offers', 'search', 'history'].includes(screen)) return BG_MERCADO;`,
  `    if (screen === 'clausulazo') return BG_CLAUSULAZO;\n    if (['market', 'publish', 'offers', 'search', 'history'].includes(screen)) return BG_MERCADO;`,
  'selección de fondo de Clausulazo',
);

fs.writeFileSync(path, ui);
console.log('Fondo exclusivo de Clausulazo aplicado.');
