import fs from 'node:fs';

const uiPath = new URL('../src/BotParityAppV2.tsx', import.meta.url);
let ui = fs.readFileSync(uiPath, 'utf8');

const importLine = "import CopasMenuScreen from './CopasMenuScreen';";
if (!ui.includes(importLine)) {
  const anchor = "import TrophyCabinetScreen from './TrophyCabinetFab';";
  if (!ui.includes(anchor)) throw new Error('Copas approved UI: no encontré import TrophyCabinetScreen');
  ui = ui.replace(anchor, anchor + '\n' + importLine);
}

if (!ui.includes("else if (screen === 'titles') body = <CopasMenuScreen />;")) {
  const adminBranch = "  else if (screen === 'admin') body = adminMenu;";
  if (!ui.includes(adminBranch)) throw new Error('Copas approved UI: no encontré rama admin');
  ui = ui.replace(adminBranch, "  else if (screen === 'titles') body = <CopasMenuScreen />;\n" + adminBranch);
}

ui = ui.replace(
  /\s*\{screen === 'titles' \? <TrophyCabinetScreen[^\n]*\n?/g,
  '\n',
);

fs.writeFileSync(uiPath, ui);
console.log('AJPA UI Lab: menú Copas aprobado aplicado.');
