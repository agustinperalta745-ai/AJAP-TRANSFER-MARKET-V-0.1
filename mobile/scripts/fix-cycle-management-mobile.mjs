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

const staleMenuTile = `<MenuTile emoji="🗓️" title="CAMBIAR TEMPORADA" onPress={() => Alert.alert('Cambiar temporada', 'La selección de temporada mantiene la validación Staff de Discord y todavía no expone una mutación móvil.')} />`;
const liveMenuTile = `<MenuTile\n        emoji="🗓️"\n        title="CAMBIAR TEMPORADA"\n        subtitle="Gestionar la etapa oficial de AJPA"\n        onPress={() => {\n          void openCompetitionCycleManagement(async () => {\n            await loadAll(true);\n          });\n        }}\n      />`;

const staleFeatureTile = `<FeatureTile emoji="🗓️" title="Cambiar temporada" subtitle="Seleccionar la temporada activa" onPress={() => Alert.alert('Cambiar temporada', 'La selección de temporada mantiene la validación Staff de Discord y todavía no expone una mutación móvil.')} />`;
const liveFeatureTile = `<FeatureTile\n          emoji="🗓️"\n          title="Gestionar etapa"\n          subtitle="Cambiar la etapa oficial de AJPA"\n          onPress={() => {\n            void openCompetitionCycleManagement(async () => {\n              await loadAll(true);\n            });\n          }}\n        />`;

if (ui.includes(staleFeatureTile)) {
  ui = ui.replace(staleFeatureTile, liveFeatureTile);
} else if (ui.includes(staleMenuTile)) {
  ui = ui.replace(staleMenuTile, liveMenuTile);
} else if (!ui.includes('openCompetitionCycleManagement(async () =>')) {
  throw new Error('AJPA cycle mobile fix: no encontré el control viejo de temporada');
}

if (ui.includes('todavía no expone una mutación móvil')) {
  throw new Error('AJPA cycle mobile fix: quedó el placeholder viejo de temporada');
}

fs.writeFileSync(uiPath, ui);
console.log('AJPA Mobile Gestión: etapa oficial conectada al endpoint real en la UI final');
