import fs from 'node:fs';

const path = 'src/BotParityAppV2.tsx';
let ui = fs.readFileSync(path, 'utf8');

function replaceOnce(from, to, label) {
  if (ui.includes(to)) return;
  if (!ui.includes(from)) throw new Error(`Clausulazo mobile patch: no se encontró ${label}`);
  ui = ui.replace(from, to);
}

replaceOnce(
  `  AdminAssignment,\n  LeagueData,`,
  `  AdminAssignment,\n  ClausulazoData,\n  ClausulazoPlayer,\n  LeagueData,`,
  'tipos de Clausulazo',
);

replaceOnce(
  `  acceptOffer,\n  fetchAdminAssignments,`,
  `  acceptOffer,\n  executeClausulazo,\n  fetchAdminAssignments,\n  fetchClausulazo,`,
  'API de Clausulazo',
);

replaceOnce(
  `  const [assignments, setAssignments] = useState<AdminAssignment[]>([]);\n  const [loading, setLoading] = useState(true);`,
  `  const [assignments, setAssignments] = useState<AdminAssignment[]>([]);\n  const [clausulazoData, setClausulazoData] = useState<ClausulazoData | null>(null);\n  const [clausulazoQuery, setClausulazoQuery] = useState('');\n  const [clausulazoTarget, setClausulazoTarget] = useState<ClausulazoPlayer | null>(null);\n  const [loading, setLoading] = useState(true);`,
  'estado de Clausulazo',
);

replaceOnce(
  `    if (next === 'search' && allPlayers.length === 0 && snapshot) {`,
  `    if (next === 'clausulazo') {\n      if (!profile?.club) {\n        Alert.alert('Sin club', 'Necesitás un club asignado para ejecutar un clausulazo.');\n        setScreen('market');\n        return;\n      }\n      try {\n        setBusy(true);\n        setClausulazoTarget(null);\n        setClausulazoQuery('');\n        setClausulazoData(await fetchClausulazo());\n      } catch (error) {\n        setClausulazoData(null);\n        Alert.alert('Clausulazo', apiError(error));\n      } finally {\n        setBusy(false);\n      }\n    }\n    if (next === 'search' && allPlayers.length === 0 && snapshot) {`,
  'carga de Clausulazo',
);

replaceOnce(
  `  const mutate = async (work: () => Promise<unknown>, success: string) => {`,
  `  const clausulazoPlayers = clausulazoQuery.trim()\n    ? (clausulazoData?.players ?? []).filter((player) =>\n        \`\${player.name} \${player.club} \${player.position}\`.toLowerCase().includes(clausulazoQuery.trim().toLowerCase()),\n      )\n    : [];\n\n  const mutate = async (work: () => Promise<unknown>, success: string) => {`,
  'filtro de Clausulazo',
);

replaceOnce(
  `  if (loading) {`,
  `  const submitClausulazo = (target: ClausulazoPlayer) => {\n    if (!clausulazoData?.available || !target.available) {\n      Alert.alert('Clausulazo bloqueado', target.blocked_reason || clausulazoData?.blocked_reason || 'La operación no está disponible.');\n      return;\n    }\n    Alert.alert(\n      'Confirmar clausulazo',\n      \`Vas a ejecutar la cláusula de \${target.name} (\${target.club}) por \${money(target.clause)}. El importe queda reservado hasta que Staff apruebe o rechace la operación.\`,\n      [\n        { text: 'Cancelar', style: 'cancel' },\n        {\n          text: 'EJECUTAR',\n          style: 'destructive',\n          onPress: () => void mutate(\n            async () => {\n              const result = await executeClausulazo(target.id);\n              setClausulazoTarget(null);\n              setClausulazoQuery('');\n              try { setClausulazoData(await fetchClausulazo()); } catch {}\n              return result;\n            },\n            \`Clausulazo de \${target.name} enviado a revisión del Staff.\`,\n          ),\n        },\n      ],\n    );\n  };\n\n  if (loading) {`,
  'submit Clausulazo',
);

replaceOnce(
  `      <MenuTile emoji="💥" title="CLAUSULAZO" subtitle="Ejecutar cláusula de rescisión" onPress={() => openScreen('clausulazo')} danger />`,
  `      <MenuTile emoji="💥" title="CLAUSULAZO" subtitle="Ejecutar cláusula de rescisión" onPress={() => requireClub('clausulazo')} danger />`,
  'acceso Clausulazo',
);

const marker = `  const publishScreen = (`;
if (!ui.includes(marker)) throw new Error('Clausulazo mobile patch: no se encontró publishScreen');
const screen = String.raw`  const clausulazoScreen = (
    <ScrollView contentContainerStyle={s.content} refreshControl={refreshControl} keyboardShouldPersistTaps="handled">
      <Title
        eyebrow="MERCADO · CLAUSULAZO"
        title="Clausulazo"
        subtitle="Ejecutá una cláusula de rescisión con exactamente las mismas protecciones del bot."
      />

      {clausulazoData ? (
        <>
          <View style={s.summaryRow}>
            <View style={s.summaryCard}>
              <Text style={s.summaryValue}>{money(clausulazoData.clause)}</Text>
              <Text style={s.summaryLabel}>CLÁUSULA</Text>
            </View>
            <View style={s.summaryCard}>
              <Text style={[s.summaryValue, { color: clausulazoData.balance >= clausulazoData.clause ? C.green : C.red }]}>{money(clausulazoData.balance)}</Text>
              <Text style={s.summaryLabel}>TU PRESUPUESTO</Text>
            </View>
          </View>

          <View style={[s.marketState, clausulazoData.available ? s.marketOpen : s.marketClosed]}>
            <Text style={s.marketStateText}>{clausulazoData.available ? '💥 CLAUSULAZO DISPONIBLE' : '🔒 CLAUSULAZO BLOQUEADO'}</Text>
            {clausulazoData.blocked_reason ? <Text style={s.detail}>{clausulazoData.blocked_reason}</Text> : null}
          </View>

          <View style={s.card}>
            <Text style={s.infoLabel}>REGLAS ACTIVAS</Text>
            <Text style={s.detail}>1 clausulazo por DT y mercado · 1 pérdida por club vendedor · 1 por jugador · planteles entre 20 y 32 · aprobación final de Staff.</Text>
          </View>

          <Text style={s.inputLabel}>BUSCAR JUGADOR</Text>
          <TextInput
            style={s.input}
            value={clausulazoQuery}
            onChangeText={(value) => { setClausulazoQuery(value); setClausulazoTarget(null); }}
            placeholder="Nombre, club o posición"
            placeholderTextColor="#657382"
          />

          {clausulazoTarget ? (
            <View style={s.editorCard}>
              <View style={s.playerRow}>
                <ClubBadge club={clausulazoTarget.club} size={82} />
                <View style={[s.flex, { marginLeft: 14 }]}>
                  <Text style={s.editorTitle}>{clausulazoTarget.name}</Text>
                  <Text style={s.muted}>{clausulazoTarget.position} · {clausulazoTarget.club}</Text>
                  <Text style={s.playerValue}>OVR {clausulazoTarget.rating ?? '—'} · Valor AJPA {money(clausulazoTarget.market_value)}</Text>
                </View>
              </View>
              <View style={s.separator} />
              <Text style={s.infoLabel}>CLÁUSULA A RESERVAR</Text>
              <Text style={s.statValue}>{money(clausulazoTarget.clause)}</Text>
              {clausulazoTarget.blocked_reason ? <Text style={[s.detail, { color: C.red }]}>{clausulazoTarget.blocked_reason}</Text> : null}
              <View style={s.actionRow}>
                <Button
                  label={busy ? 'PROCESANDO…' : 'EJECUTAR CLAUSULAZO'}
                  kind="red"
                  disabled={busy || !clausulazoData.available || !clausulazoTarget.available}
                  onPress={() => submitClausulazo(clausulazoTarget)}
                />
                <Button label="CAMBIAR JUGADOR" kind="ghost" disabled={busy} onPress={() => setClausulazoTarget(null)} />
              </View>
            </View>
          ) : null}

          {!clausulazoQuery.trim() ? (
            <View style={s.card}><Text style={s.muted}>Escribí un nombre o club para buscar al jugador que querés clausular.</Text></View>
          ) : null}

          {clausulazoQuery.trim() && clausulazoPlayers.length === 0 ? (
            <View style={s.card}><Text style={s.muted}>No encontré jugadores con esa búsqueda.</Text></View>
          ) : null}

          {!clausulazoTarget && clausulazoPlayers.slice(0, 60).map((player) => (
            <Pressable
              key={player.club + '-' + player.id}
              disabled={!player.available}
              onPress={() => setClausulazoTarget(player)}
              style={({ pressed }) => [s.card, !player.available && s.disabled, pressed && player.available && { opacity: 0.72 }]}
            >
              <View style={s.playerRow}>
                <ClubBadge club={player.club} size={58} />
                <View style={[s.flex, { marginLeft: 12 }]}>
                  <Text style={s.playerName}>{player.name}</Text>
                  <Text style={s.muted}>{player.position} · {player.club}</Text>
                  <Text style={s.playerValue}>OVR {player.rating ?? '—'} · Cláusula {money(player.clause)}</Text>
                  {player.blocked_reason ? <Text style={[s.detail, { color: C.red }]}>{player.blocked_reason}</Text> : null}
                </View>
                <Text style={s.chevron}>{player.available ? '›' : '🔒'}</Text>
              </View>
            </Pressable>
          ))}
        </>
      ) : (
        <View style={s.card}>
          <Text style={s.playerName}>No se pudo cargar Clausulazo</Text>
          <Text style={s.detail}>Reintentá para consultar saldo, cláusula y jugadores habilitados.</Text>
          <View style={s.actionRow}><Button label={busy ? 'CARGANDO…' : 'REINTENTAR'} disabled={busy} onPress={() => void openScreen('clausulazo')} /></View>
        </View>
      )}
    </ScrollView>
  );

`;
ui = ui.replace(marker, screen + marker);

replaceOnce(
  `  else if (screen === 'clausulazo') body = placeholder('Clausulazo', 'Ejecución de cláusula de rescisión con las reglas del bot.');`,
  `  else if (screen === 'clausulazo') body = clausulazoScreen;`,
  'despacho Clausulazo',
);

if (ui.includes("placeholder('Clausulazo'")) {
  throw new Error('Clausulazo mobile patch: quedó el placeholder viejo');
}

fs.writeFileSync(path, ui);
console.log('Clausulazo mobile operativo aplicado.');
