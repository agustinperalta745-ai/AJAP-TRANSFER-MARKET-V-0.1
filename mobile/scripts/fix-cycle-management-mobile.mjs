import fs from 'node:fs';

const uiPath = new URL('../src/BotParityAppV2.tsx', import.meta.url);
let ui = fs.readFileSync(uiPath, 'utf8');

const sessionImport = `import { clearStoredSession, loadStoredSession, saveStoredSession } from './session';`;
const cycleImport = `import { openCompetitionCycleManagement } from './CompetitionCycleManagement';`;
if (!ui.includes(cycleImport)) {
  if (!ui.includes(sessionImport)) {
    throw new Error('AJPA cycle mobile fix: no encontré el import de session');
  }
  ui = ui.replace(sessionImport, `${sessionImport}\n${cycleImport}`);
}

const stale = `<MenuTile emoji="🗓️" title="CAMBIAR TEMPORADA" onPress={() => Alert.alert('Cambiar temporada', 'La selección de temporada mantiene la validación Staff de Discord y todavía no expone una mutación móvil.')} />`;
const live = `<MenuTile\n        emoji="🗓️"\n        title="CAMBIAR TEMPORADA"\n        subtitle="Gestionar la etapa oficial de AJPA"\n        onPress={() => {\n          void openCompetitionCycleManagement(async () => {\n            await loadAll(true);\n          });\n        }}\n      />`;

if (ui.includes(stale)) {
  ui = ui.replace(stale, live);
} else if (!ui.includes('openCompetitionCycleManagement(async () =>')) {
  throw new Error('AJPA cycle mobile fix: no encontré el botón CAMBIAR TEMPORADA viejo');
}

if (ui.includes('todavía no expone una mutación móvil')) {
  throw new Error('AJPA cycle mobile fix: quedó el placeholder viejo de temporada');
}

fs.writeFileSync(uiPath, ui);
console.log('AJPA Mobile Gestión: CAMBIAR TEMPORADA conectado al endpoint real del ciclo');
