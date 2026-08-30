import fs from 'node:fs';

const uiPath = new URL('../src/BotParityAppV2.tsx', import.meta.url);
let ui = fs.readFileSync(uiPath, 'utf8');

function mustReplace(search, replacement, label) {
  if (!ui.includes(search)) {
    throw new Error(`AJPA parity patch: no encontré ${label}`);
  }
  ui = ui.replace(search, replacement);
}

mustReplace(
  `  LeagueSnapshot,\n  MarketItem,`,
  `  AdminAssignment,\n  LeagueData,\n  LeagueSnapshot,\n  MarketItem,\n  TransferHistoryItem,`,
  'los tipos de API',
);

mustReplace(
  `  fetchMe,\n  fetchMyOffers,\n  fetchRoster,\n  fetchSnapshot,`,
  `  fetchAdminAssignments,\n  fetchHistory,\n  fetchLeague,\n  fetchMe,\n  fetchMyOffers,\n  fetchRoster,\n  fetchSnapshot,`,
  'las funciones de lectura',
);

mustReplace(
  `  sendOffer,\n  setSessionToken,`,
  `  sendOffer,\n  setAdminMarketOpen,\n  setSessionToken,`,
  'la función Staff de mercado',
);

mustReplace(
  `  | 'adminTools'\n  | 'assignments'`,
  `  | 'adminTools'\n  | 'adminMarket'\n  | 'adminRosters'\n  | 'adminEconomy'\n  | 'adminManagement'\n  | 'assignments'`,
  'las pantallas Staff',
);

mustReplace(
  `  const [allPlayers, setAllPlayers] = useState<RosterPlayer[]>([]);\n  const [loading, setLoading] = useState(true);`,
  `  const [allPlayers, setAllPlayers] = useState<RosterPlayer[]>([]);\n  const [leagueData, setLeagueData] = useState<LeagueData | null>(null);\n  const [historyItems, setHistoryItems] = useState<TransferHistoryItem[]>([]);\n  const [assignments, setAssignments] = useState<AdminAssignment[]>([]);\n  const [loading, setLoading] = useState(true);`,
  'los estados de paridad',
);

mustReplace(
  `  const openScreen = async (next: Screen) => {\n    setScreen(next);\n    if (next === 'offers') {\n      try { setOffers(await fetchMyOffers()); } catch (error) { Alert.alert('Ofertas', apiError(error)); }\n    }`,
  `  const openScreen = async (next: Screen) => {\n    setScreen(next);\n    if (next === 'offers') {\n      try { setOffers(await fetchMyOffers()); } catch (error) { Alert.alert('Ofertas', apiError(error)); }\n    }\n    if (next === 'league') {\n      try { setLeagueData(await fetchLeague()); } catch (error) { Alert.alert('Liga', apiError(error)); }\n    }\n    if (next === 'history') {\n      try { setHistoryItems(await fetchHistory()); } catch (error) { Alert.alert('Historial', apiError(error)); }\n    }\n    if (next === 'assignments') {\n      try { setAssignments(await fetchAdminAssignments()); } catch (error) { Alert.alert('Asignaciones', apiError(error)); }\n    }`,
  'la carga de pantallas',
);

const marker = `  const profileScreen = (`;
if (!ui.includes(marker)) {
  throw new Error('AJPA parity patch: no encontré profileScreen');
}

const parityScreens = String.raw`  const leagueScreen = (
    <ScrollView contentContainerStyle={s.content} refreshControl={refreshControl}>
      <Title eyebrow="LIGA" title="Liga" subtitle="Tabla y goleadores en vivo, igual que en Discord." />
      <View style={s.card}>
        <Text style={s.infoLabel}>TEMPORADA</Text>
        <Text style={s.infoValue}>{snapshot.status.season?.name ?? 'Sin temporada activa'}</Text>
      </View>

      <Text style={s.listHeading}>🏆 TABLA DE POSICIONES</Text>
      {!leagueData ? <ActivityIndicator color={C.blue} /> : null}
      {leagueData?.standings.length === 0 ? <View style={s.card}><Text style={s.muted}>Todavía no hay equipos en la tabla.</Text></View> : null}
      {leagueData?.standings.map((row, index) => (
        <View style={s.card} key={row.team}>
          <View style={s.playerRow}>
            <View style={s.ovrBox}><Text style={s.ovrValue}>{index + 1}</Text><Text style={s.ovrLabel}>POS</Text></View>
            <View style={s.flex}>
              <Text style={s.playerName}>{row.team}</Text>
              <Text style={s.muted}>PJ {row.pj} · PG {row.pg} · PE {row.pe} · PP {row.pp}</Text>
              <Text style={s.playerValue}>GF {row.gf} · GC {row.gc} · DIF {row.dg >= 0 ? '+' : ''}{row.dg}</Text>
            </View>
            <Text style={s.price}>{row.pts} pts</Text>
          </View>
        </View>
      ))}

      <Text style={s.listHeading}>⚽ GOLEADORES</Text>
      {leagueData?.scorers.length === 0 ? <View style={s.card}><Text style={s.muted}>Todavía no hay goles registrados.</Text></View> : null}
      {leagueData?.scorers.map((row, index) => (
        <View style={s.card} key={row.player + '-' + row.team}>
          <Text style={s.playerName}>{index + 1}. {row.player}</Text>
          <Text style={s.muted}>{row.team || 'Sin club'}</Text>
          <Text style={s.playerValue}>⚽ {row.goals} goles</Text>
        </View>
      ))}
    </ScrollView>
  );

  const historyScreen = (
    <ScrollView contentContainerStyle={s.content} refreshControl={refreshControl}>
      <Title eyebrow="HISTORIAL" title="Movimientos" subtitle="Operaciones registradas en el mismo historial del bot." />
      {historyItems.length === 0 ? <View style={s.card}><Text style={s.muted}>Todavía no hay movimientos registrados.</Text></View> : null}
      {historyItems.map((item) => (
        <View style={s.card} key={item.id}>
          <Text style={s.playerName}>{item.player}</Text>
          <Text style={s.muted}>{item.seller || '—'} → {item.buyer || '—'}</Text>
          <Text style={s.playerValue}>{item.operation_type} · {item.amount}</Text>
          <Text style={[s.statusTag, { color: item.status === 'APLICADA' ? C.green : C.orange }]}>{item.status || 'SIN ESTADO'}</Text>
          {item.notes ? <Text style={s.detail}>{item.notes}</Text> : null}
        </View>
      ))}
    </ScrollView>
  );

  const adminToolsScreen = (
    <ScrollView contentContainerStyle={s.content} refreshControl={refreshControl}>
      <Title eyebrow="STAFF · ADMINISTRACIÓN" title="Administración" subtitle="Mismas cuatro secciones del panel administrativo de Discord." />
      <MenuTile emoji="🔁" title="MERCADO" subtitle="Estado y control de operaciones" onPress={() => openScreen('adminMarket')} />
      <MenuTile emoji="👥" title="PLANTELES" subtitle="Altas, bajas, movimientos y consulta" onPress={() => openScreen('adminRosters')} />
      <MenuTile emoji="💰" title="ECONOMÍA" subtitle="Presupuestos y ajustes" onPress={() => openScreen('adminEconomy')} />
      <MenuTile emoji="⚙️" title="GESTIÓN" subtitle="Asignaciones, temporada y exportación" onPress={() => openScreen('adminManagement')} />
    </ScrollView>
  );

  const adminMarketScreen = (
    <ScrollView contentContainerStyle={s.content} refreshControl={refreshControl}>
      <Title eyebrow="STAFF · ADMINISTRACIÓN" title="Mercado" subtitle="Estado del mercado y control de operaciones." />
      <MenuTile
        emoji={snapshot.status.market_open ? '🔒' : '🟢'}
        title={snapshot.status.market_open ? 'CERRAR MERCADO' : 'ABRIR MERCADO'}
        subtitle={snapshot.status.market_open ? 'El mercado está abierto' : 'El mercado está cerrado'}
        danger={snapshot.status.market_open}
        onPress={() => mutate(
          () => setAdminMarketOpen(!snapshot.status.market_open),
          snapshot.status.market_open ? 'Mercado cerrado por Staff.' : 'Mercado abierto por Staff.',
        )}
      />
      <MenuTile emoji="🛠️" title="OPERACIONES PENDIENTES" subtitle="Revisión Staff / PES" onPress={() => Alert.alert('Operaciones pendientes', 'La pantalla móvil de aprobación se conecta en el próximo endpoint Staff; el botón ya ocupa el mismo lugar que en Discord.')} />
      <MenuTile emoji="💥" title="CLAUSULAZOS" subtitle="Solicitudes pendientes" onPress={() => Alert.alert('Clausulazos', 'La revisión móvil de clausulazos conserva el flujo Staff de Discord y se habilitará cuando esté expuesto el endpoint de aprobación.')} danger />
      <MenuTile emoji="↩️" title="DESHACER PASE" subtitle="Revertir una operación aplicada" onPress={() => Alert.alert('Deshacer pase', 'Por seguridad, la reversión sigue requiriendo la validación completa del bot hasta que ese endpoint esté disponible en la app.')} danger />
    </ScrollView>
  );

  const adminRostersScreen = (
    <ScrollView contentContainerStyle={s.content} refreshControl={refreshControl}>
      <Title eyebrow="STAFF · ADMINISTRACIÓN" title="Planteles" subtitle="Mismo grupo de herramientas de Discord." />
      <MenuTile emoji="➕" title="AGREGAR JUGADOR" onPress={() => Alert.alert('Agregar jugador', 'La alta conserva posición, estadísticas y OVR automático del bot. El formulario móvil se habilita cuando esté conectado su endpoint Staff.')} />
      <MenuTile emoji="🔁" title="MOVER JUGADOR" onPress={() => Alert.alert('Mover jugador', 'La herramienta ya está reflejada; la mutación queda bloqueada hasta usar el endpoint Staff seguro.')} />
      <MenuTile emoji="🗑️" title="QUITAR JUGADOR" onPress={() => Alert.alert('Quitar jugador', 'La eliminación necesita la misma confirmación destructiva del bot antes de habilitarse desde la app.')} danger />
      <MenuTile emoji="📋" title="VER PLANTEL" subtitle="Podés consultar jugadores desde Buscar y Mi Club" onPress={() => openScreen('search')} />
    </ScrollView>
  );

  const adminEconomyScreen = (
    <ScrollView contentContainerStyle={s.content} refreshControl={refreshControl}>
      <Title eyebrow="STAFF · ADMINISTRACIÓN" title="Economía" subtitle="Administración de presupuestos." />
      <MenuTile emoji="➕" title="DAR DINERO" onPress={() => Alert.alert('Dar dinero', 'El ajuste económico necesita registrar la auditoría de tesorería; se habilita al conectar el endpoint Staff correspondiente.')} />
      <MenuTile emoji="➖" title="QUITAR DINERO" onPress={() => Alert.alert('Quitar dinero', 'El ajuste económico necesita registrar la auditoría de tesorería; se habilita al conectar el endpoint Staff correspondiente.')} danger />
      <Text style={s.listHeading}>📊 VER PRESUPUESTOS</Text>
      {snapshot.clubs.map((club) => (
        <View style={s.card} key={club.name}>
          <Text style={s.playerName}>{club.name}</Text>
          <Text style={s.playerValue}>{money(club.balance)}</Text>
          <Text style={s.muted}>{club.roster_count} jugadores</Text>
        </View>
      ))}
    </ScrollView>
  );

  const adminManagementScreen = (
    <ScrollView contentContainerStyle={s.content} refreshControl={refreshControl}>
      <Title eyebrow="STAFF · ADMINISTRACIÓN" title="Gestión" subtitle="Configuración general del torneo y mercado." />
      <MenuTile emoji="👥" title="ASIGNACIONES" subtitle="Clubes vinculados a usuarios" onPress={() => openScreen('assignments')} />
      <MenuTile emoji="🗓️" title="CAMBIAR TEMPORADA" onPress={() => Alert.alert('Cambiar temporada', 'La selección de temporada mantiene la validación Staff de Discord y todavía no expone una mutación móvil.')} />
      <MenuTile emoji="📤" title="EXPORTAR MERCADO" onPress={() => Alert.alert('Exportar mercado', 'El historial ya se consulta desde la app. La descarga CSV se mantiene en Discord hasta habilitar archivos desde el endpoint móvil.')} />
    </ScrollView>
  );

  const assignmentsScreen = (
    <ScrollView contentContainerStyle={s.content} refreshControl={refreshControl}>
      <Title eyebrow="STAFF" title="Asignaciones" subtitle="Asignaciones actuales leídas desde la misma base del bot." />
      {assignments.length === 0 ? <View style={s.card}><Text style={s.muted}>No hay clubes asignados.</Text></View> : null}
      {assignments.map((item) => (
        <View style={s.card} key={item.user_id}>
          <Text style={s.playerName}>{item.club}</Text>
          <Text style={s.muted}>Discord ID: {item.user_id}</Text>
        </View>
      ))}
    </ScrollView>
  );

`;

ui = ui.replace(marker, parityScreens + marker);

mustReplace(
  `  else if (screen === 'history') body = placeholder('Historial', 'Movimientos y operaciones cerradas del mercado.');\n  else if (screen === 'league') body = placeholder('Liga', 'Tabla, goleadores y estado de la competencia.');\n  else if (screen === 'admin') body = adminMenu;\n  else if (screen === 'adminTools') body = placeholder('Administración', 'Herramientas de gestión exclusivas para Staff.');\n  else if (screen === 'assignments') body = placeholder('Asignaciones', 'Gestión de asignaciones de usuarios y clubes.');`,
  `  else if (screen === 'history') body = historyScreen;\n  else if (screen === 'league') body = leagueScreen;\n  else if (screen === 'admin') body = adminMenu;\n  else if (screen === 'adminTools') body = adminToolsScreen;\n  else if (screen === 'adminMarket') body = adminMarketScreen;\n  else if (screen === 'adminRosters') body = adminRostersScreen;\n  else if (screen === 'adminEconomy') body = adminEconomyScreen;\n  else if (screen === 'adminManagement') body = adminManagementScreen;\n  else if (screen === 'assignments') body = assignmentsScreen;`,
  'el despacho de Liga/Historial/Administración',
);

if (ui.includes("placeholder('Liga'") || ui.includes("placeholder('Administración'")) {
  throw new Error('AJPA parity patch: quedaron placeholders en Liga/Administración');
}

fs.writeFileSync(uiPath, ui);
console.log('AJPA mobile parity aplicada: Liga + Historial + Administración + Asignaciones');
