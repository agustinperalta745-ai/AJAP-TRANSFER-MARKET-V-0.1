import fs from 'node:fs';

const file = 'src/CupCenterFab.tsx';
let cup = fs.readFileSync(file, 'utf8');

// The hub opens Champions and Europa as two separate screens. Their draft/loading
// controls must therefore be separate too, even though they share one season edition.
if (!cup.includes('champions_started_at?: string | null;')) {
  const anchor = '  champions_finished_at?: string | null;\n';
  if (!cup.includes(anchor)) throw new Error('Cup split: champions_finished_at anchor not found.');
  cup = cup.replace(
    anchor,
    '  champions_started_at?: string | null;\n  europa_started_at?: string | null;\n' + anchor,
  );
}

const activeAnchor = "  const activeRounds = useMemo(() => edition?.rounds?.[competition] ?? [], [edition, competition]);\n";
if (!cup.includes('const competitionStartedAt =')) {
  if (!cup.includes(activeAnchor)) throw new Error('Cup split: activeRounds anchor not found.');
  cup = cup.replace(
    activeAnchor,
    activeAnchor +
      "  const competitionStartedAt = edition ? (competition === 'champions' ? edition.champions_started_at : edition.europa_started_at) : null;\n",
  );
}

const oldSeed = `  const seedFromTable = () => {
    if (!edition) return;
    Alert.alert(
      'Cargar clasificados',
      'Se cargarán los cupos según la tabla y la regla vigente. Después podés cambiar cualquier equipo manualmente antes de iniciar.',
      [
        { text: 'Cancelar', style: 'cancel' },
        { text: 'CARGAR', onPress: () => { void mutate(\`/api/v1/cups/\${edition.id}/seed-from-table\`, {}); } },
      ],
    );
  };
  const startCups = () => {
    if (!edition) return;
    Alert.alert(
      'Iniciar Champions y Europa',
      'Al iniciar se congela la preclasificación. Los resultados harán avanzar automáticamente a los ganadores y los 8 perdedores de la primera ronda de Champions bajarán a Europa.',
      [
        { text: 'Volver', style: 'cancel' },
        { text: 'INICIAR COPAS', onPress: () => { void mutate(\`/api/v1/cups/\${edition.id}/start\`, {}, 'Los cuadros quedaron iniciados.'); } },
      ],
    );
  };
`;

const newSeed = `  const seedFromTable = () => {
    if (!edition) return;
    const name = competition === 'champions' ? 'Champions AJPA' : 'Europa AJPA';
    Alert.alert(
      \`Cargar \${name} según tabla\`,
      \`Se cargarán solamente los cupos de \${name}. Después podés cambiar cualquier equipo manualmente antes de iniciar esta copa.\`,
      [
        { text: 'Cancelar', style: 'cancel' },
        {
          text: 'CARGAR',
          onPress: () => {
            void mutate(\`/api/v1/cups/\${edition.id}/seed-from-table\`, { competition });
          },
        },
      ],
    );
  };
  const startCompetition = () => {
    if (!edition) return;
    const isChampions = competition === 'champions';
    const name = isChampions ? 'Champions AJPA' : 'Europa AJPA';
    const explanation = isChampions
      ? 'Se congelarán solamente los 16 cupos de Champions. Sus 8 eliminados de primera ronda seguirán bajando automáticamente a Europa.'
      : 'Se congelarán solamente los 8 preclasificados de Europa. Cada uno esperará al eliminado correspondiente de la primera ronda de Champions.';
    Alert.alert(
      \`Iniciar \${name}\`,
      explanation,
      [
        { text: 'Volver', style: 'cancel' },
        {
          text: \`INICIAR \${isChampions ? 'CHAMPIONS' : 'EUROPA'}\`,
          onPress: () => {
            void mutate(
              \`/api/v1/cups/\${edition.id}/start\`,
              { competition },
              \`\${name} quedó iniciada.\`,
            );
          },
        },
      ],
    );
  };
`;

if (!cup.includes('const startCompetition = () => {')) {
  if (!cup.includes(oldSeed)) throw new Error('Cup split: seed/start block not found.');
  cup = cup.replace(oldSeed, newSeed);
}

// Each list remains editable until THAT competition starts. Starting Champions must
// not freeze the eight Europa preclassified slots.
const rowsAnchor = "    const rows = slots.length ? slots : Array.from({ length: expected }, (_, slot_index) => ({ slot_index, team: null, source: null }));\n";
if (!cup.includes('const seedListStarted =')) {
  if (!cup.includes(rowsAnchor)) throw new Error('Cup split: seed rows anchor not found.');
  cup = cup.replace(
    rowsAnchor,
    rowsAnchor +
      "    const seedListStarted = Boolean(key === 'champions' ? edition?.champions_started_at : edition?.europa_started_at);\n",
  );
}
cup = cup.replace(
  "            disabled={!isStaff || edition?.status !== 'DRAFT'}",
  "            disabled={!isStaff || seedListStarted}",
);
cup = cup.replace(
  "{isStaff && edition?.status === 'DRAFT' ? <Text style={styles.chevron}>›</Text> : null}",
  "{isStaff && !seedListStarted ? <Text style={styles.chevron}>›</Text> : null}",
);

// Preparing the shared edition is a technical detail. The button must read as the
// competition the Staff actually opened.
cup = cup.replace(
  '<Text style={styles.primaryText}>⚙️ PREPARAR COPAS · TEMPORADA {currentSeason}</Text>',
  "<Text style={styles.primaryText}>⚙️ PREPARAR {competition === 'champions' ? 'CHAMPIONS' : 'EUROPA'} · TEMPORADA {currentSeason}</Text>",
);

// Draft panel: one competition only.
cup = cup.replace(
  "{edition?.status === 'DRAFT' && currentEditionReady ? (",
  "{edition && currentEditionReady && !competitionStartedAt ? (",
);
cup = cup.replace(
  '<Text style={styles.muted}>Staff está armando los cupos antes del inicio de las copas.</Text>',
  "<Text style={styles.muted}>Staff está armando los cupos antes del inicio de {competition === 'champions' ? 'Champions' : 'Europa'}.</Text>",
);

const oldWarnings = `                      {data.qualification_suggestion.warnings.map((warning, index) => (
                        <Text key={\`\${warning}-\${index}\`} style={styles.warning}>⚠ {warning}</Text>
                      ))}`;
const newWarnings = `                      {data.qualification_suggestion.warnings
                        .filter((warning) => competition === 'champions'
                          ? !warning.includes('8 equipos disponibles para Europa League')
                          : warning.includes('8 equipos disponibles para Europa League'))
                        .map((warning, index) => (
                          <Text key={\`\${warning}-\${index}\`} style={styles.warning}>⚠ {warning}</Text>
                        ))}`;
if (cup.includes(oldWarnings)) cup = cup.replace(oldWarnings, newWarnings);

cup = cup.replace('onPress={startCups}', 'onPress={startCompetition}');
cup = cup.replace(
  '<Text style={styles.primaryText}>▶ INICIAR COPAS</Text>',
  "<Text style={styles.primaryText}>▶ INICIAR {competition === 'champions' ? 'CHAMPIONS' : 'EUROPA'}</Text>",
);
cup = cup.replace(
  "                    {renderSeedList('champions')}\n                    {renderSeedList('europa')}",
  "                    {renderSeedList(competition)}",
);

// Once one cup starts, the other still shows its own loading menu. A bracket is
// visible only after the selected competition itself has started.
cup = cup.replace(
  "{edition && edition.status !== 'DRAFT' ? (",
  "{edition && competitionStartedAt ? (",
);

// The user entered a specific cup from the hub, so do not show an internal switch
// that can jump to the other competition and recreate the duplicated-menu problem.
const tabs = `                    <View style={styles.competitionTabs}>
                      {(['champions', 'europa'] as CompetitionKey[]).map((key) => (
                        <Pressable key={key} onPress={() => setCompetition(key)} style={[styles.tab, competition === key && styles.tabActive]}>
                          <Text style={[styles.tabText, competition === key && styles.tabTextActive]}>{key === 'champions' ? '🏆 CHAMPIONS' : '🟠 EUROPA'}</Text>
                        </Pressable>
                      ))}
                    </View>

`;
if (cup.includes(tabs)) cup = cup.replace(tabs, '');

for (const required of [
  'champions_started_at?: string | null;',
  'europa_started_at?: string | null;',
  'const competitionStartedAt =',
  'const startCompetition = () => {',
  '{ competition }',
  '{renderSeedList(competition)}',
  'edition && competitionStartedAt',
  "INICIAR {competition === 'champions' ? 'CHAMPIONS' : 'EUROPA'}",
]) {
  if (!cup.includes(required)) throw new Error(`Cup split: missing final marker ${required}`);
}
if (cup.includes("{renderSeedList('champions')}\n                    {renderSeedList('europa')}")) {
  throw new Error('Cup split: both seed lists are still rendered together.');
}

fs.writeFileSync(file, cup);
console.log('AJPA Copas: carga e inicio independientes por Champions/Europa aplicados.');
