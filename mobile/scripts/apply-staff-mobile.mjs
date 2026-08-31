import fs from 'node:fs';

const uiPath = new URL('../src/BotParityAppV2.tsx', import.meta.url);
let ui = fs.readFileSync(uiPath, 'utf8');

function mustReplace(search, replacement, label) {
  if (!ui.includes(search)) throw new Error(`AJPA Staff mobile patch: no encontré ${label}`);
  ui = ui.replace(search, replacement);
}

mustReplace(
  `import { clearStoredSession, loadStoredSession, saveStoredSession } from './session';`,
  `import { clearStoredSession, loadStoredSession, saveStoredSession } from './session';\nimport {\n  StaffClause,\n  StaffOperation,\n  StaffReversible,\n  fetchStaffClauses,\n  fetchStaffOperations,\n  fetchStaffReversible,\n  staffClauseAction,\n  staffOperationAction,\n  undoStaffTransfer,\n} from './staffApi';`,
  'import de sesión',
);

mustReplace(
  `  | 'adminMarket'\n  | 'adminRosters'`,
  `  | 'adminMarket'\n  | 'adminOperations'\n  | 'adminClauses'\n  | 'adminUndo'\n  | 'adminRosters'`,
  'pantallas Staff del mercado',
);

// Clausulazo puede insertar estados entre assignments y loading. Anclar solo a
// assignments hace que este parche siga funcionando aunque cambie el orden de
// los estados generados por otros parches del workflow.
mustReplace(
  `  const [assignments, setAssignments] = useState<AdminAssignment[]>([]);`,
  `  const [assignments, setAssignments] = useState<AdminAssignment[]>([]);\n  const [staffOperations, setStaffOperations] = useState<StaffOperation[]>([]);\n  const [staffClauses, setStaffClauses] = useState<StaffClause[]>([]);\n  const [staffReversible, setStaffReversible] = useState<StaffReversible[]>([]);`,
  'estado assignments para insertar estados Staff operativos',
);

const openMarker = `  const openScreen = async (next: Screen) => {`;
if (!ui.includes(openMarker)) throw new Error('AJPA Staff mobile patch: no encontré openScreen');
ui = ui.replace(
  openMarker,
  `  const staffMutate = async (work: () => Promise<unknown>, success: string, reload: () => Promise<void>) => {\n    if (busy) return;\n    setBusy(true);\n    try {\n      await work();\n      Alert.alert('AJPA Staff', success);\n      await reload();\n      await loadAll(true);\n    } catch (error) {\n      Alert.alert('No se pudo completar', apiError(error));\n    } finally {\n      setBusy(false);\n    }\n  };\n\n${openMarker}`,
);

mustReplace(
  `  const openScreen = async (next: Screen) => {\n    setScreen(next);`,
  `  const openScreen = async (next: Screen) => {\n    setScreen(next);\n    if (next === 'adminOperations') {\n      try { setStaffOperations(await fetchStaffOperations()); } catch (error) { Alert.alert('Operaciones pendientes', apiError(error)); }\n    }\n    if (next === 'adminClauses') {\n      try { setStaffClauses(await fetchStaffClauses()); } catch (error) { Alert.alert('Clausulazos Staff', apiError(error)); }\n    }\n    if (next === 'adminUndo') {\n      try { setStaffReversible(await fetchStaffReversible()); } catch (error) { Alert.alert('Deshacer pase', apiError(error)); }\n    }`,
  'carga de pantallas Staff',
);

mustReplace(
  `<MenuTile emoji="🛠️" title="OPERACIONES PENDIENTES" subtitle="Revisión Staff / PES" onPress={() => Alert.alert('Operaciones pendientes', 'La pantalla móvil de aprobación se conecta en el próximo endpoint Staff; el botón ya ocupa el mismo lugar que en Discord.')} />`,
  `<MenuTile emoji="🛠️" title="OPERACIONES PENDIENTES" subtitle="Revisión Staff / PES" onPress={() => openScreen('adminOperations')} />`,
  'placeholder de operaciones pendientes',
);

mustReplace(
  `<MenuTile emoji="💥" title="CLAUSULAZOS" subtitle="Solicitudes pendientes" onPress={() => Alert.alert('Clausulazos', 'La revisión móvil de clausulazos conserva el flujo Staff de Discord y se habilitará cuando esté expuesto el endpoint de aprobación.')} danger />`,
  `<MenuTile emoji="💥" title="CLAUSULAZOS" subtitle="Solicitudes pendientes" onPress={() => openScreen('adminClauses')} danger />`,
  'placeholder de clausulazos Staff',
);

mustReplace(
  `<MenuTile emoji="↩️" title="DESHACER PASE" subtitle="Revertir una operación aplicada" onPress={() => Alert.alert('Deshacer pase', 'Por seguridad, la reversión sigue requiriendo la validación completa del bot hasta que ese endpoint esté disponible en la app.')} danger />`,
  `<MenuTile emoji="↩️" title="DESHACER PASE" subtitle="Revertir una operación aplicada" onPress={() => openScreen('adminUndo')} danger />`,
  'placeholder de deshacer pase',
);

// Estas pantallas deben quedar inmediatamente después de adminMarketScreen.
// El parche visual organizado usa ese orden para reemplazar Mercado sin tragarse
// Planteles/Economía/Gestión durante el build.
const screenMarker = `  const adminRostersScreen = (`;
if (!ui.includes(screenMarker)) throw new Error('AJPA Staff mobile patch: no encontré adminRostersScreen');

const staffScreens = String.raw`  const adminOperationsScreen = (
    <ScrollView contentContainerStyle={s.content} refreshControl={refreshControl}>
      <Title eyebrow="STAFF · MERCADO" title="Operaciones pendientes" subtitle="Aprobación Staff y carga en PES sobre la misma base de Discord." />
      {staffOperations.length === 0 ? <View style={s.card}><Text style={s.muted}>No hay operaciones pendientes.</Text></View> : null}
      {staffOperations.map((item) => (
        <View style={s.card} key={item.id}>
          <Text style={s.playerName}>#{item.id} · {item.players.join(' + ')}</Text>
          <Text style={s.muted}>{item.seller} → {item.buyer}</Text>
          <Text style={s.playerValue}>{item.operation_type} · {item.amount}</Text>
          <Text style={[s.statusTag, { color: item.status === 'APROBADA' ? C.orange : C.blueSoft }]}>{item.status}</Text>
          <View style={s.actionRow}>
            {item.status === 'PENDIENTE_ADMIN' ? <Button label="APROBAR" kind="green" disabled={busy} onPress={() => staffMutate(
              () => staffOperationAction(item.id, 'approve'),
              'Operación #' + item.id + ' aprobada.',
              async () => setStaffOperations(await fetchStaffOperations()),
            )} /> : null}
            {item.status === 'APROBADA' ? <Button label="CARGADO EN PES" kind="green" disabled={busy} onPress={() => staffMutate(
              () => staffOperationAction(item.id, 'pes'),
              'Operación #' + item.id + ' aplicada y marcada como cargada en PES.',
              async () => setStaffOperations(await fetchStaffOperations()),
            )} /> : null}
            <Button label="RECHAZAR" kind="red" disabled={busy} onPress={() => staffMutate(
              () => staffOperationAction(item.id, 'reject'),
              'Operación #' + item.id + ' rechazada.',
              async () => setStaffOperations(await fetchStaffOperations()),
            )} />
          </View>
        </View>
      ))}
    </ScrollView>
  );

  const adminClausesScreen = (
    <ScrollView contentContainerStyle={s.content} refreshControl={refreshControl}>
      <Title eyebrow="STAFF · MERCADO" title="Clausulazos" subtitle="Solicitudes pendientes de aprobación Staff." />
      {staffClauses.length === 0 ? <View style={s.card}><Text style={s.muted}>No hay clausulazos pendientes.</Text></View> : null}
      {staffClauses.map((item) => (
        <View style={s.card} key={item.id}>
          <Text style={s.playerName}>#{item.id} · {item.player}</Text>
          <Text style={s.muted}>{item.seller_club} → {item.buyer_club}</Text>
          <Text style={s.playerValue}>Cláusula {money(item.amount)}</Text>
          <Text style={s.detail}>Solicitado por {item.buyer_username || 'usuario vinculado'}</Text>
          <View style={s.actionRow}>
            <Button label="APROBAR" kind="green" disabled={busy} onPress={() => staffMutate(
              () => staffClauseAction(item.id, 'approve'),
              'Clausulazo #' + item.id + ' aprobado. Quedó pendiente de cargar en PES.',
              async () => setStaffClauses(await fetchStaffClauses()),
            )} />
            <Button label="RECHAZAR" kind="red" disabled={busy} onPress={() => staffMutate(
              () => staffClauseAction(item.id, 'reject'),
              'Clausulazo #' + item.id + ' rechazado y reserva devuelta.',
              async () => setStaffClauses(await fetchStaffClauses()),
            )} />
          </View>
        </View>
      ))}
    </ScrollView>
  );

  const adminUndoScreen = (
    <ScrollView contentContainerStyle={s.content} refreshControl={refreshControl}>
      <Title eyebrow="STAFF · MERCADO" title="Deshacer pase" subtitle="Solo muestra operaciones aplicadas que la validación del bot permite revertir." />
      {staffReversible.length === 0 ? <View style={s.card}><Text style={s.muted}>No hay pases disponibles para revertir.</Text></View> : null}
      {staffReversible.map((item) => (
        <View style={s.card} key={item.id}>
          <Text style={s.playerName}>#{item.id} · {item.players.join(' + ')}</Text>
          <Text style={s.muted}>{item.seller} → {item.buyer}</Text>
          <Text style={s.playerValue}>{item.operation_type} · {item.amount}</Text>
          <View style={s.actionRow}>
            <Button label="DESHACER PASE" kind="red" disabled={busy} onPress={() => Alert.alert(
              'Confirmar reversión',
              '¿Deshacer #' + item.id + ' y devolver ' + item.players.join(' + ') + ' a ' + item.seller + '?',
              [
                { text: 'CANCELAR', style: 'cancel' },
                { text: 'DESHACER', style: 'destructive', onPress: () => staffMutate(
                  () => undoStaffTransfer(item.id),
                  'Operación #' + item.id + ' revertida.',
                  async () => setStaffReversible(await fetchStaffReversible()),
                ) },
              ],
            )} />
          </View>
        </View>
      ))}
    </ScrollView>
  );

`;

ui = ui.replace(screenMarker, staffScreens + screenMarker);

mustReplace(
  `  else if (screen === 'adminMarket') body = adminMarketScreen;\n  else if (screen === 'adminRosters') body = adminRostersScreen;`,
  `  else if (screen === 'adminMarket') body = adminMarketScreen;\n  else if (screen === 'adminOperations') body = adminOperationsScreen;\n  else if (screen === 'adminClauses') body = adminClausesScreen;\n  else if (screen === 'adminUndo') body = adminUndoScreen;\n  else if (screen === 'adminRosters') body = adminRostersScreen;`,
  'despacho de pantallas Staff',
);

if (ui.includes('La pantalla móvil de aprobación se conecta en el próximo endpoint Staff') ||
    ui.includes('se habilitará cuando esté expuesto el endpoint de aprobación') ||
    ui.includes('la reversión sigue requiriendo la validación completa del bot')) {
  throw new Error('AJPA Staff mobile patch: quedaron placeholders de Mercado Staff');
}

fs.writeFileSync(uiPath, ui);
console.log('AJPA Staff mobile operativo: pendientes + clausulazos + deshacer pase');
