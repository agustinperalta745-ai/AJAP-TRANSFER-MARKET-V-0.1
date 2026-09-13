import fs from 'node:fs';

// 1) Remove the old floating COPAS trigger from the global app shell.
const appFile = 'App.tsx';
let app = fs.readFileSync(appFile, 'utf8');
app = app
  .replace("import CupCenterFab from './src/CupCenterFab';\n", '')
  .replace('        <CupCenterFab />\n', '');
fs.writeFileSync(appFile, app);

// 2) Make CupCenter reusable from the new main-menu hub and add Staff lifecycle controls.
const cupFile = 'src/CupCenterFab.tsx';
let cup = fs.readFileSync(cupFile, 'utf8');

if (!cup.includes('type CupCenterProps =')) {
  const anchor = "const compName = (key: CompetitionKey) => key === 'champions' ? 'Champions League' : 'Europa League';\n";
  if (!cup.includes(anchor)) throw new Error('Cup menu: compName anchor not found.');
  cup = cup.replace(anchor, `${anchor}\ntype CupCenterProps = {\n  hideTrigger?: boolean;\n  initialVisible?: boolean;\n  initialCompetition?: CompetitionKey;\n  onDismiss?: () => void;\n};\n`);
}

cup = cup.replace(
  'export default function CupCenterFab() {',
  "export default function CupCenterFab({ hideTrigger = false, initialVisible = false, initialCompetition = 'champions', onDismiss }: CupCenterProps = {}) {",
);
cup = cup.replace('const [visible, setVisible] = useState(false);', 'const [visible, setVisible] = useState(initialVisible);');
cup = cup.replace("const [competition, setCompetition] = useState<CompetitionKey>('champions');", 'const [competition, setCompetition] = useState<CompetitionKey>(initialCompetition);');

if (!cup.includes('champions_finished_at?: string | null;')) {
  cup = cup.replace(
    '  finished_at: string | null;\n',
    '  finished_at: string | null;\n  champions_finished_at?: string | null;\n  europa_finished_at?: string | null;\n',
  );
}

// Replace modal dismiss calls before adding the close helper, avoiding recursion.
cup = cup.replaceAll('setVisible(false)', 'close()');

if (!cup.includes('const close = () => {')) {
  const openBlock = `  const open = () => {\n    setVisible(true);\n    void load();\n  };`;
  if (!cup.includes(openBlock)) throw new Error('Cup menu: open helper anchor not found.');
  cup = cup.replace(
    openBlock,
    `${openBlock}\n\n  const close = () => {\n    setVisible(false);\n    onDismiss?.();\n  };`,
  );
  // The replaceAll above also touched the helper we just want to contain a real state update.
  cup = cup.replace('  const close = () => {\n    close();\n    onDismiss?.();\n  };', '  const close = () => {\n    setVisible(false);\n    onDismiss?.();\n  };');
}

if (!cup.includes('const resetCups = () => {')) {
  const anchor = '  const scoreText = (match: CupMatch) => {';
  if (!cup.includes(anchor)) throw new Error('Cup menu: scoreText anchor not found.');
  const controls = `  const resetCups = () => {\n    if (!edition) return;\n    Alert.alert(\n      'Reiniciar Champions y Europa',\n      'Esto borra preclasificados, cruces y TODOS los resultados cargados en esta edición. Sirve para limpiar pruebas y volver a empezar. No toca Liga, planteles ni historial de otras temporadas.',\n      [\n        { text: 'Cancelar', style: 'cancel' },\n        {\n          text: 'REINICIAR TODO',\n          style: 'destructive',\n          onPress: () => { void mutate(\`/api/v1/cups/\${edition.id}/reset\`, {}, 'Copas reiniciadas. El cuadro quedó limpio.'); },\n        },\n      ],\n    );\n  };\n\n  const finishCompetition = (key: CompetitionKey) => {\n    if (!edition) return;\n    const champion = key === 'champions' ? edition.champions_champion : edition.europa_champion;\n    const name = key === 'champions' ? 'Champions AJPA' : 'Europa AJPA';\n    if (!champion) {\n      Alert.alert('Todavía no se puede finalizar', \`Primero cargá el resultado de la final de \${name}.\`);\n      return;\n    }\n    Alert.alert(\n      \`Finalizar \${name}\`,\n      \`Se confirmará a \${champion} como campeón y Radio Pasillo publicará el anuncio oficial. ¿Confirmás?\`,\n      [\n        { text: 'Cancelar', style: 'cancel' },\n        {\n          text: 'FINALIZAR',\n          onPress: () => { void mutate(\`/api/v1/cups/\${edition.id}/finish/\${key}\`, {}, \`\${name} finalizada. Radio Pasillo anunciará al campeón.\`); },\n        },\n      ],\n    );\n  };\n\n`;
  cup = cup.replace(anchor, `${controls}${anchor}`);
}

if (!cup.includes('const competitionFinishedAt =')) {
  const anchor = "  const activeRounds = useMemo(() => edition?.rounds?.[competition] ?? [], [edition, competition]);\n";
  if (!cup.includes(anchor)) throw new Error('Cup menu: activeRounds anchor not found.');
  cup = cup.replace(
    anchor,
    `${anchor}  const competitionFinishedAt = edition ? (competition === 'champions' ? edition.champions_finished_at : edition.europa_finished_at) : null;\n  const competitionChampion = edition ? (competition === 'champions' ? edition.champions_champion : edition.europa_champion) : null;\n`,
  );
}

const oldTrigger = `      <Pressable\n        accessibilityRole="button"\n        accessibilityLabel="Champions y Europa League"\n        onPress={open}\n        style={({ pressed }) => [styles.fab, pressed && styles.pressed]}\n      >\n        <Text style={styles.fabText}>🏆 COPAS</Text>\n      </Pressable>`;
if (cup.includes(oldTrigger)) {
  cup = cup.replace(oldTrigger, `{!hideTrigger ? (\n${oldTrigger}\n      ) : null}`);
}

if (!cup.includes('REINICIAR COPAS')) {
  const draftAnchor = "                {edition?.status === 'DRAFT' && currentEditionReady ? (";
  if (!cup.includes(draftAnchor)) throw new Error('Cup menu: DRAFT anchor not found.');
  const resetUi = `                {isStaff && edition ? (\n                  <Pressable disabled={saving} onPress={resetCups} style={[styles.dangerButton, saving && styles.disabled]}>\n                    <Text style={styles.dangerText}>🧹 REINICIAR COPAS · BORRAR PRUEBAS</Text>\n                  </Pressable>\n                ) : null}\n\n`;
  cup = cup.replace(draftAnchor, `${resetUi}${draftAnchor}`);
}

if (!cup.includes('FINALIZAR CHAMPIONS') && !cup.includes("competitionFinishedAt ? '✓ FINALIZADA'")) {
  const championAnchor = `                    {(competition === 'champions' ? edition.champions_champion : edition.europa_champion) ? (`;
  if (!cup.includes(championAnchor)) throw new Error('Cup menu: champion card anchor not found.');
  const finishUi = `                    {isStaff ? (\n                      <Pressable\n                        disabled={saving || !competitionChampion || Boolean(competitionFinishedAt)}\n                        onPress={() => finishCompetition(competition)}\n                        style={[styles.primary, (saving || !competitionChampion || Boolean(competitionFinishedAt)) && styles.disabled]}\n                      >\n                        <Text style={styles.primaryText}>\n                          {competitionFinishedAt ? '✓ FINALIZADA' : \`🏁 FINALIZAR \${competition === 'champions' ? 'CHAMPIONS' : 'EUROPA'}\`}\n                        </Text>\n                      </Pressable>\n                    ) : null}\n\n`;
  cup = cup.replace(championAnchor, `${finishUi}${championAnchor}`);
}

if (!cup.includes('hideTrigger') || !cup.includes('REINICIAR COPAS') || !cup.includes('finishCompetition')) {
  throw new Error('Cup menu: CupCenter final validation failed.');
}
fs.writeFileSync(cupFile, cup);

// 3) Put COPAS AJPA in the real main menu and route it to Vitrina-style cards.
const uiFile = 'src/BotParityAppV2.tsx';
let ui = fs.readFileSync(uiFile, 'utf8');
const hubImport = "import CupHubScreen from './CupHubScreen';";
if (!ui.includes(hubImport)) {
  const sessionImport = "import { clearStoredSession, loadStoredSession, saveStoredSession } from './session';";
  if (!ui.includes(sessionImport)) throw new Error('Cup menu: session import anchor not found.');
  ui = ui.replace(sessionImport, `${hubImport}\n${sessionImport}`);
}

if (!ui.includes("| 'cupHub'")) {
  const profileUnion = "  | 'profile';";
  if (!ui.includes(profileUnion)) throw new Error('Cup menu: screen union anchor not found.');
  ui = ui.replace(profileUnion, "  | 'cupHub'\n  | 'profile';");
}

if (!ui.includes('title="COPAS AJPA"')) {
  const ligaLine = ui.match(/^[ \t]*<[^>]+title="(?:LIGA|Liga)"[^>]*\/>$/m)?.[0];
  if (!ligaLine) throw new Error('Cup menu: Liga menu anchor not found.');
  const indent = ligaLine.match(/^[ \t]*/)?.[0] ?? '      ';
  ui = ui.replace(
    ligaLine,
    `${ligaLine}\n${indent}<MenuTile emoji="🏆" title="COPAS AJPA" subtitle="Champions, Europa, brackets y resultados" onPress={() => openScreen('cupHub')} />`,
  );
}

if (!ui.includes("screen === 'cupHub'")) {
  const leagueBody = ui.match(/^[ \t]*else if \(screen === 'league'\)[^\n]*$/m)?.[0];
  if (!leagueBody) throw new Error('Cup menu: Liga body anchor not found.');
  const indent = leagueBody.match(/^[ \t]*/)?.[0] ?? '  ';
  ui = ui.replace(leagueBody, `${leagueBody}\n${indent}else if (screen === 'cupHub') body = <CupHubScreen />;`);
}

if (!ui.includes(hubImport) || !ui.includes('title="COPAS AJPA"') || !ui.includes("screen === 'cupHub'")) {
  throw new Error('Cup menu: main-menu final validation failed.');
}
fs.writeFileSync(uiFile, ui);

console.log('AJPA Copas: main-menu Vitrina cards + no floating button + reset/finalize Staff controls applied.');
