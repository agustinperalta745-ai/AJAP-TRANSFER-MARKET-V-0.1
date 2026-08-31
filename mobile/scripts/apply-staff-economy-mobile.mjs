import fs from 'node:fs';

const uiPath = new URL('../src/BotParityAppV2.tsx', import.meta.url);
let ui = fs.readFileSync(uiPath, 'utf8');

function mustReplace(search, replacement, label) {
  if (!ui.includes(search)) throw new Error(`AJPA Staff economy mobile patch: no encontré ${label}`);
  ui = ui.replace(search, replacement);
}

mustReplace(
  `  undoStaffTransfer,\n} from './staffApi';`,
  `  undoStaffTransfer,\n  adjustStaffEconomy,\n} from './staffApi';`,
  'import Staff API',
);

mustReplace(
  `  | 'adminEconomy'\n  | 'adminManagement'`,
  `  | 'adminEconomy'\n  | 'adminEconomyAdjust'\n  | 'adminManagement'`,
  'pantalla de ajuste económico',
);

mustReplace(
  `  const [staffReversible, setStaffReversible] = useState<StaffReversible[]>([]);`,
  `  const [staffReversible, setStaffReversible] = useState<StaffReversible[]>([]);\n  const [economyMode, setEconomyMode] = useState<'ADD' | 'REMOVE'>('ADD');\n  const [economyClub, setEconomyClub] = useState('');\n  const [economyAmount, setEconomyAmount] = useState('');`,
  'estados Staff economy',
);

const openMarker = `  const openScreen = async (next: Screen) => {`;
if (!ui.includes(openMarker)) throw new Error('AJPA Staff economy mobile patch: no encontré openScreen');
ui = ui.replace(
  openMarker,
  `  const openEconomyAdjustment = (mode: 'ADD' | 'REMOVE') => {\n    setEconomyMode(mode);\n    setEconomyClub('');\n    setEconomyAmount('');\n    setScreen('adminEconomyAdjust');\n  };\n\n  const submitEconomyAdjustment = () => {\n    const amount = Number(economyAmount);\n    if (!economyClub) {\n      Alert.alert('Elegí un equipo', 'Seleccioná el club al que querés ajustar el presupuesto.');\n      return;\n    }\n    if (!Number.isFinite(amount) || amount <= 0) {\n      Alert.alert('Monto inválido', 'Escribí un monto mayor a cero.');\n      return;\n    }\n    const selected = snapshot.clubs.find((club) => club.name === economyClub);\n    const before = selected?.balance ?? 0;\n    const after = economyMode === 'ADD' ? before + amount : before - amount;\n    if (economyMode === 'REMOVE' && amount > before) {\n      Alert.alert('Saldo insuficiente', economyClub + ' tiene ' + money(before) + ' disponibles.');\n      return;\n    }\n    const action = economyMode === 'ADD' ? 'acreditar' : 'quitar';\n    Alert.alert(\n      economyMode === 'ADD' ? 'Confirmar ingreso' : 'Confirmar egreso',\n      '¿' + action.charAt(0).toUpperCase() + action.slice(1) + ' ' + money(amount) + ' a ' + economyClub + '?\\n\\nSaldo actual: ' + money(before) + '\\nSaldo después: ' + money(after),\n      [\n        { text: 'CANCELAR', style: 'cancel' },\n        {\n          text: economyMode === 'ADD' ? 'DAR DINERO' : 'QUITAR DINERO',\n          style: economyMode === 'REMOVE' ? 'destructive' : 'default',\n          onPress: () => staffMutate(\n            () => adjustStaffEconomy(economyClub, amount, economyMode),\n            (economyMode === 'ADD' ? 'Se acreditaron ' : 'Se quitaron ') + money(amount) + ' ' + (economyMode === 'ADD' ? 'a ' : 'de ') + economyClub + '. El movimiento quedó auditado en Tesorería.',\n            async () => {},\n          ),\n        },\n      ],\n    );\n  };\n\n${openMarker}`,
);

mustReplace(
  `<MenuTile emoji="➕" title="DAR DINERO" onPress={() => Alert.alert('Dar dinero', 'El ajuste económico necesita registrar la auditoría de tesorería; se habilita al conectar el endpoint Staff correspondiente.')} />`,
  `<MenuTile emoji="➕" title="DAR DINERO" subtitle="Acreditar presupuesto con auditoría" onPress={() => openEconomyAdjustment('ADD')} />`,
  'placeholder Dar dinero',
);

mustReplace(
  `<MenuTile emoji="➖" title="QUITAR DINERO" onPress={() => Alert.alert('Quitar dinero', 'El ajuste económico necesita registrar la auditoría de tesorería; se habilita al conectar el endpoint Staff correspondiente.')} danger />`,
  `<MenuTile emoji="➖" title="QUITAR DINERO" subtitle="Descontar presupuesto con auditoría" onPress={() => openEconomyAdjustment('REMOVE')} danger />`,
  'placeholder Quitar dinero',
);

const managementMarker = `  const adminManagementScreen = (`;
if (!ui.includes(managementMarker)) throw new Error('AJPA Staff economy mobile patch: no encontré adminManagementScreen');

const economyAdjustScreen = String.raw`  const adminEconomyAdjustScreen = (
    <ScrollView contentContainerStyle={s.content} refreshControl={refreshControl} keyboardShouldPersistTaps="handled">
      <Title
        eyebrow="STAFF · ECONOMÍA"
        title={economyMode === 'ADD' ? 'Dar dinero' : 'Quitar dinero'}
        subtitle="El ajuste se aplica a la misma economía de Discord y queda registrado en Tesorería."
      />

      <Text style={s.listHeading}>🏟️ ELEGÍ EL EQUIPO</Text>
      {snapshot.clubs.map((club) => {
        const selected = economyClub === club.name;
        return (
          <Pressable
            key={club.name}
            onPress={() => setEconomyClub(club.name)}
            style={({ pressed }) => [
              s.card,
              selected && { borderColor: economyMode === 'ADD' ? C.green : C.red, borderWidth: 2 },
              pressed && { opacity: 0.72 },
            ]}
          >
            <View style={s.playerRow}>
              <View style={s.flex}>
                <Text style={s.playerName}>{club.name}</Text>
                <Text style={s.playerValue}>Saldo actual: {money(club.balance)}</Text>
                <Text style={s.muted}>{club.roster_count} jugadores</Text>
              </View>
              <Text style={{ color: selected ? (economyMode === 'ADD' ? C.green : C.red) : C.muted, fontSize: 22, fontWeight: '900' }}>
                {selected ? '✓' : '›'}
              </Text>
            </View>
          </Pressable>
        );
      })}

      <View style={s.editorCard}>
        <Text style={s.inputLabel}>MONTO</Text>
        <TextInput
          style={s.input}
          value={economyAmount}
          onChangeText={(value) => setEconomyAmount(value.replace(/\D/g, '').slice(0, 12))}
          keyboardType="numeric"
          placeholder="Ej: 25000000"
          placeholderTextColor="#657382"
        />
        <Text style={s.muted}>
          {economyClub
            ? (economyMode === 'ADD' ? 'Acreditar a ' : 'Descontar de ') + economyClub
            : 'Primero seleccioná un equipo.'}
        </Text>
        <View style={{ marginTop: 14, gap: 9 }}>
          <Button
            label={busy ? 'PROCESANDO…' : economyMode === 'ADD' ? 'CONFIRMAR INGRESO' : 'CONFIRMAR EGRESO'}
            kind={economyMode === 'ADD' ? 'green' : 'red'}
            disabled={busy || !economyClub || !economyAmount}
            onPress={submitEconomyAdjustment}
          />
          <Button label="VOLVER A ECONOMÍA" kind="ghost" disabled={busy} onPress={() => setScreen('adminEconomy')} />
        </View>
      </View>
    </ScrollView>
  );

`;

ui = ui.replace(managementMarker, economyAdjustScreen + managementMarker);

mustReplace(
  `  else if (screen === 'adminEconomy') body = adminEconomyScreen;\n  else if (screen === 'adminManagement') body = adminManagementScreen;`,
  `  else if (screen === 'adminEconomy') body = adminEconomyScreen;\n  else if (screen === 'adminEconomyAdjust') body = adminEconomyAdjustScreen;\n  else if (screen === 'adminManagement') body = adminManagementScreen;`,
  'despacho Staff economy',
);

if (ui.includes('El ajuste económico necesita registrar la auditoría de tesorería')) {
  throw new Error('AJPA Staff economy mobile patch: quedó el placeholder de Economía');
}

fs.writeFileSync(uiPath, ui);
console.log('AJPA Staff economy móvil operativo: Dar/Quitar dinero + auditoría');
