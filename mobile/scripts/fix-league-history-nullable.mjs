import fs from 'node:fs';

const uiPath = 'src/BotParityAppV2.tsx';
let ui = fs.readFileSync(uiPath, 'utf8');

const unsafe = `{profile.club} {gf} — {gc} {rival}`;
const safe = `{profile?.club ?? 'Tu equipo'} {gf} — {gc} {rival}`;
if (ui.includes(unsafe)) ui = ui.replace(unsafe, safe);

if (!ui.includes(safe)) {
  throw new Error('AJPA Liga history: no pude asegurar el club nullable dentro de las tarjetas');
}

fs.writeFileSync(uiPath, ui);
console.log('AJPA Liga history: narrowing nullable saneado para TypeScript.');
