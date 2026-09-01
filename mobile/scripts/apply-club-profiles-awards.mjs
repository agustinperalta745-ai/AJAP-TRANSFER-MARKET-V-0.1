import fs from 'node:fs';

const uiPath = new URL('../src/BotParityAppV2.tsx', import.meta.url);
let ui = fs.readFileSync(uiPath, 'utf8');

function mustReplace(search, replacement, label) {
  if (ui.includes(replacement)) return;
  if (!ui.includes(search)) throw new Error(`AJPA club profiles patch: no encontré ${label}`);
  ui = ui.replace(search, replacement);
}

// API pública de perfiles + operaciones Staff de palmarés/premios.
const sessionImport = `import { clearStoredSession, loadStoredSession, saveStoredSession } from './session';`;
const profileImport = String.raw`import {
  ClubProfile,
  ClubProfileSummary,
  TreasuryData,
  addClubTitle,
  fetchClubProfile,
  fetchClubProfiles,
  fetchMyTreasury,
  payClubPrize,
  setClubStars,
} from './clubProfileApi';`;
if (!ui.includes(profileImport)) {
  if (!ui.includes(sessionImport)) throw new Error('AJPA club profiles patch: no encontré import de session');
  ui = ui.replace(sessionImport, profileImport + '\n' + sessionImport);
}

if (!ui.includes(`  | 'teams'`)) {
  mustReplace(
    `  | 'profile';`,
    `  | 'teams'\n  | 'teamProfile'\n  | 'treasury'\n  | 'adminClubProfiles'\n  | 'adminPrize'\n  | 'profile';`,
    'unión Screen',
  );
}

const stateMarker = `  const [offeredPlayerId, setOfferedPlayerId] = useState<number | null>(null);`;
const extraState = String.raw`
  const [clubProfiles, setClubProfiles] = useState<ClubProfileSummary[]>([]);
  const [selectedClubProfile, setSelectedClubProfile] = useState<ClubProfile | null>(null);
  const [treasury, setTreasury] = useState<TreasuryData | null>(null);
  const [adminProfileClub, setAdminProfileClub] = useState('');
  const [adminProfileData, setAdminProfileData] = useState<ClubProfile | null>(null);
  const [adminTitle, setAdminTitle] = useState('');
  const [adminTitleImportant, setAdminTitleImportant] = useState(true);
  const [adminStars, setAdminStars] = useState('0');
  const [prizeClub, setPrizeClub] = useState('');
  const [prizeName, setPrizeName] = useState('');
  const [prizeAmount, setPrizeAmount] = useState('');`;
if (!ui.includes('const [clubProfiles, setClubProfiles]')) {
  if (!ui.includes(stateMarker)) throw new Error('AJPA club profiles patch: no encontré estado base');
  ui = ui.replace(stateMarker, stateMarker + extraState);
}

const openMarker = `  const openScreen = async (next: Screen) => {`;
if (!ui.includes('const openTeams = async')) {
  if (!ui.includes(openMarker)) throw new Error('AJPA club profiles patch: no encontré openScreen');
  const helpers = String.raw`  const refreshClubProfiles = async () => {
    const clubs = await fetchClubProfiles();
    setClubProfiles(clubs);
    return clubs;
  };

  const openTeams = async () => {
    setBusy(true);
    try {
      await refreshClubProfiles();
      setScreen('teams');
    } catch (error) {
      Alert.alert('Equipos', apiError(error));
    } finally {
      setBusy(false);
    }
  };

  const openTeamProfile = async (club: string) => {
    setBusy(true);
    try {
      const data = await fetchClubProfile(club);
      setSelectedClubProfile(data);
      setScreen('teamProfile');
    } catch (error) {
      Alert.alert('Perfil del equipo', apiError(error));
    } finally {
      setBusy(false);
    }
  };

  const openTreasury = async () => {
    if (!profile?.club) {
      Alert.alert('Sin club', 'Necesitás un club asignado para abrir la Tesorería.');
      return;
    }
    setBusy(true);
    try {
      setTreasury(await fetchMyTreasury());
      setScreen('treasury');
    } catch (error) {
      Alert.alert('Tesorería', apiError(error));
    } finally {
      setBusy(false);
    }
  };

  const openAdminClubProfiles = async (club?: string) => {
    setBusy(true);
    try {
      await refreshClubProfiles();
      if (club) {
        const data = await fetchClubProfile(club);
        setAdminProfileClub(club);
        setAdminProfileData(data);
        setAdminStars(String(data.stars));
      } else {
        setAdminProfileClub('');
        setAdminProfileData(null);
        setAdminStars('0');
      }
      setAdminTitle('');
      setAdminTitleImportant(true);
      setScreen('adminClubProfiles');
    } catch (error) {
      Alert.alert('Perfiles de equipo', apiError(error));
    } finally {
      setBusy(false);
    }
  };

  const chooseAdminProfileClub = async (club: string) => {
    setBusy(true);
    try {
      const data = await fetchClubProfile(club);
      setAdminProfileClub(club);
      setAdminProfileData(data);
      setAdminStars(String(data.stars));
      setAdminTitle('');
    } catch (error) {
      Alert.alert('Perfil del equipo', apiError(error));
    } finally {
      setBusy(false);
    }
  };

  const submitClubTitle = async () => {
    if (!adminProfileClub || !adminTitle.trim()) {
      Alert.alert('Faltan datos', 'Elegí el equipo y escribí el título.');
      return;
    }
    setBusy(true);
    try {
      const result = await addClubTitle(adminProfileClub, adminTitle.trim(), adminTitleImportant);
      const data = await fetchClubProfile(adminProfileClub);
      setAdminProfileData(data);
      setAdminStars(String(data.stars));
      setAdminTitle('');
      await refreshClubProfiles();
      Alert.alert(
        'Título asignado',
        result.important
          ? result.title + ' quedó en el perfil y sumó 1 estrella.'
          : result.title + ' quedó agregado al palmarés.',
      );
    } catch (error) {
      Alert.alert('No se pudo asignar', apiError(error));
    } finally {
      setBusy(false);
    }
  };

  const submitClubStars = async () => {
    const stars = Number(adminStars);
    if (!adminProfileClub || !Number.isInteger(stars) || stars < 0) {
      Alert.alert('Estrellas inválidas', 'Elegí un equipo e indicá una cantidad válida.');
      return;
    }
    setBusy(true);
    try {
      await setClubStars(adminProfileClub, stars);
      const data = await fetchClubProfile(adminProfileClub);
      setAdminProfileData(data);
      setAdminStars(String(data.stars));
      await refreshClubProfiles();
      Alert.alert('Estrellas actualizadas', adminProfileClub + ' ahora tiene ' + stars + ' estrella(s).');
    } catch (error) {
      Alert.alert('No se pudo actualizar', apiError(error));
    } finally {
      setBusy(false);
    }
  };

  const submitPrize = () => {
    const amount = Number(prizeAmount);
    if (!prizeClub || !prizeName.trim() || !Number.isFinite(amount) || amount <= 0) {
      Alert.alert('Faltan datos', 'Elegí equipo, escribí el premio y un monto mayor a cero.');
      return;
    }
    const before = snapshot.clubs.find((club) => club.name === prizeClub)?.balance ?? 0;
    Alert.alert(
      'Confirmar premio',
      prizeClub + '\n' + prizeName.trim() + '\n\nPremio: ' + money(amount) + '\nSaldo actual: ' + money(before) + '\nSaldo después: ' + money(before + amount),
      [
        { text: 'CANCELAR', style: 'cancel' },
        {
          text: 'PAGAR PREMIO',
          onPress: async () => {
            setBusy(true);
            try {
              const result = await payClubPrize(prizeClub, prizeName.trim(), amount);
              setPrizeName('');
              setPrizeAmount('');
              await loadAll(true);
              Alert.alert(
                'Premio acreditado',
                result.club + ' recibió ' + money(result.amount) + '. En Tesorería figura como Ingresos por premios.',
              );
            } catch (error) {
              Alert.alert('No se pudo pagar', apiError(error));
            } finally {
              setBusy(false);
            }
          },
        },
      ],
    );
  };

`;
  ui = ui.replace(openMarker, helpers + openMarker);
}

// Inicio: acceso público a todos los perfiles.
const homeMatch = String.raw`      <WideTile
        emoji="⚽"
        title="Buscar partido"`;
if (!ui.includes(`title="Equipos"`)) {
  if (!ui.includes(homeMatch)) throw new Error('AJPA club profiles patch: no encontré Buscar partido en Inicio');
  ui = ui.replace(
    homeMatch,
    String.raw`      <WideTile
        emoji="🏟️"
        title="Equipos"
        subtitle="Perfiles, DT, presupuesto, títulos, estrellas y planteles."
        onPress={() => void openTeams()}
      />

` + homeMatch,
  );
}

// Mi Club: tesorería real, incluyendo premios.
const economyTile = `<WideTile emoji="💰" title="Economía" subtitle="Revisá presupuesto, valor de plantilla y cupos." onPress={() => openScreen('economy')} />`;
const treasuryTile = `<WideTile emoji="🏦" title="Tesorería" subtitle="Ingresos, egresos y premios acreditados al club." onPress={() => void openTreasury()} />`;
if (!ui.includes(`title="Tesorería" subtitle="Ingresos, egresos`)) {
  if (!ui.includes(economyTile)) throw new Error('AJPA club profiles patch: no encontré Economía en Mi Club');
  ui = ui.replace(economyTile, economyTile + '\n      ' + treasuryTile);
}

// Staff: palmarés y pago de premios como módulos explícitos.
const managementTile = `<WideTile emoji="⚙️" title="Gestión" subtitle="Asignaciones y configuración general." onPress={() => openScreen('adminManagement')} />`;
if (!ui.includes(`title="Títulos y estrellas"`)) {
  if (!ui.includes(managementTile)) throw new Error('AJPA club profiles patch: no encontré Gestión Staff');
  ui = ui.replace(
    managementTile,
    `<WideTile emoji="⭐" title="Títulos y estrellas" subtitle="Administrá el palmarés público de cada equipo." onPress={() => void openAdminClubProfiles()} />\n      <WideTile emoji="🏆" title="Pagar premios" subtitle="Elegí equipo, premio y monto; queda auditado en Tesorería." onPress={() => { setPrizeClub(''); setPrizeName(''); setPrizeAmount(''); setScreen('adminPrize'); }} />\n      ${managementTile}`,
  );
}

const profileScreenMarker = `  const profileScreen = (`;
if (!ui.includes('const teamsScreen = (')) {
  if (!ui.includes(profileScreenMarker)) throw new Error('AJPA club profiles patch: no encontré profileScreen');
  const screens = String.raw`  const teamsScreen = (
    <ScrollView contentContainerStyle={s.content} refreshControl={refreshControl}>
      <Title eyebrow="AJPA · EQUIPOS" title="Perfiles de equipo" subtitle="Consultá quién dirige cada club, su economía, palmarés, mercado y plantilla." />
      <Text style={s.listHeading}>🏟️ CLUBES · {clubProfiles.length}</Text>
      {busy && clubProfiles.length === 0 ? <ActivityIndicator color={C.blue} /> : null}
      {clubProfiles.map((club) => (
        <Pressable
          key={club.club}
          onPress={() => void openTeamProfile(club.club)}
          style={({ pressed }) => [s.card, pressed && { opacity: 0.74 }]}
        >
          <View style={s.playerRow}>
            <View style={s.heroIconWrap}><Text style={s.heroIcon}>🛡️</Text></View>
            <View style={s.flex}>
              <Text style={s.playerName}>{club.club}</Text>
              <Text style={s.muted}>DT · {club.manager.name}</Text>
              <Text style={s.playerValue}>{money(club.balance)} · {club.roster_count} jugadores</Text>
              <Text style={{ color: '#ffd76a', fontWeight: '900', marginTop: 5 }}>
                ⭐ {club.stars} · 🏆 {club.titles_count} título(s)
              </Text>
            </View>
            <Text style={s.chevron}>›</Text>
          </View>
        </Pressable>
      ))}
    </ScrollView>
  );

  const teamProfileScreen = selectedClubProfile ? (
    <ScrollView contentContainerStyle={s.content} refreshControl={refreshControl}>
      <Title eyebrow="PERFIL PÚBLICO" title={selectedClubProfile.club} subtitle={'DT · ' + selectedClubProfile.manager.name} />

      <View style={s.heroClubCard}>
        <View style={s.heroIconWrap}><Text style={s.heroIcon}>🛡️</Text></View>
        <View style={s.flex}>
          <Text style={s.heroClubName}>{selectedClubProfile.club}</Text>
          <Text style={s.muted}>Dueño / DT · {selectedClubProfile.manager.name}</Text>
          <Text style={{ color: '#ffd76a', fontSize: 20, fontWeight: '900', marginTop: 7 }}>
            {'★'.repeat(Math.min(selectedClubProfile.stars, 10))}{selectedClubProfile.stars > 10 ? ' +' + (selectedClubProfile.stars - 10) : ''}
          </Text>
        </View>
      </View>

      <View style={s.summaryRow}>
        <View style={s.summaryCard}><Text style={s.summaryValue}>{money(selectedClubProfile.balance)}</Text><Text style={s.summaryLabel}>PRESUPUESTO</Text></View>
        <View style={s.summaryCard}><Text style={s.summaryValue}>{selectedClubProfile.roster_count}</Text><Text style={s.summaryLabel}>JUGADORES</Text></View>
      </View>
      <View style={s.summaryRow}>
        <View style={s.summaryCard}><Text style={s.summaryValue}>{money(selectedClubProfile.squad_value)}</Text><Text style={s.summaryLabel}>VALOR PLANTILLA</Text></View>
        <View style={s.summaryCard}><Text style={s.summaryValue}>{selectedClubProfile.titles.length}</Text><Text style={s.summaryLabel}>TÍTULOS</Text></View>
      </View>

      <Text style={s.listHeading}>🏆 TÍTULOS</Text>
      {selectedClubProfile.titles.length === 0 ? <View style={s.card}><Text style={s.muted}>Este club todavía no tiene títulos cargados por Staff.</Text></View> : null}
      {selectedClubProfile.titles.map((title) => (
        <View key={title.id} style={s.card}>
          <Text style={s.playerName}>{title.important ? '⭐ ' : '🏆 '}{title.title}</Text>
          <Text style={s.muted}>{title.important ? 'Título importante · otorga estrella' : 'Título registrado'}</Text>
        </View>
      ))}

      <Text style={s.listHeading}>🔄 MOVIMIENTOS DE MERCADO</Text>
      {selectedClubProfile.movements.length === 0 ? <View style={s.card}><Text style={s.muted}>Sin movimientos registrados.</Text></View> : null}
      {selectedClubProfile.movements.slice(0, 20).map((item) => {
        const arrived = item.buyer.toLowerCase() === selectedClubProfile.club.toLowerCase();
        return (
          <View key={item.id} style={s.card}>
            <Text style={s.playerName}>{arrived ? '📥' : '📤'} {item.player}</Text>
            <Text style={s.playerValue}>{arrived ? 'Llegó desde ' + (item.seller || '—') : 'Salió hacia ' + (item.buyer || '—')} · {item.amount || '$0'}</Text>
            <Text style={s.muted}>{item.operation_type} · {item.status}</Text>
          </View>
        );
      })}

      <Text style={s.listHeading}>📤 PUBLICADOS EN MERCADO</Text>
      {selectedClubProfile.market.length === 0 ? <View style={s.card}><Text style={s.muted}>No tiene jugadores publicados actualmente.</Text></View> : null}
      {selectedClubProfile.market.map((item) => <MarketCard key={item.publication_id} item={item} />)}

      <Text style={s.listHeading}>👥 PLANTILLA · {selectedClubProfile.roster.length}</Text>
      {selectedClubProfile.roster.map((player) => <PlayerCard key={player.id ?? player.name} player={player} />)}
    </ScrollView>
  ) : (
    <ScrollView contentContainerStyle={s.content}><ActivityIndicator color={C.blue} /></ScrollView>
  );

  const treasuryScreen = (
    <ScrollView contentContainerStyle={s.content} refreshControl={refreshControl}>
      <Title eyebrow="MI CLUB · TESORERÍA" title="Tesorería" subtitle="Movimientos reales que modifican el presupuesto del club." />
      <View style={s.statCard}>
        <Text style={s.statLabel}>SALDO ACTUAL</Text>
        <Text style={s.statValue}>{money(treasury?.balance ?? profile?.balance)}</Text>
      </View>

      <Text style={s.listHeading}>📜 MOVIMIENTOS</Text>
      {!treasury || treasury.items.length === 0 ? <View style={s.card}><Text style={s.muted}>Todavía no hay movimientos registrados.</Text></View> : null}
      {treasury?.items.map((item) => {
        const incoming = item.direction === 'INGRESO';
        return (
          <View key={item.id} style={[s.card, item.category === 'PREMIO' && { borderColor: '#d9af45', borderWidth: 1.5 }]}>
            <View style={s.playerRow}>
              <View style={s.flex}>
                <Text style={[s.playerName, item.category === 'PREMIO' && { color: '#ffd76a' }]}>
                  {item.category === 'PREMIO' ? '🏆 ' : incoming ? '📈 ' : '📉 '}{item.category_label}
                </Text>
                {item.description ? <Text style={s.muted}>{item.description}</Text> : null}
                <Text style={s.muted}>{item.created_at ? item.created_at.slice(0, 10) : ''}</Text>
              </View>
              <Text style={{ color: incoming ? C.green : C.red, fontSize: 16, fontWeight: '900' }}>
                {incoming ? '+' : '−'}{money(item.amount)}
              </Text>
            </View>
          </View>
        );
      })}
    </ScrollView>
  );

  const adminClubProfilesScreen = (
    <ScrollView contentContainerStyle={s.content} refreshControl={refreshControl} keyboardShouldPersistTaps="handled">
      <Title eyebrow="STAFF · PERFILES" title="Títulos y estrellas" subtitle="Staff define el palmarés y qué títulos importantes suman estrellas." />

      <Text style={s.listHeading}>🏟️ ELEGÍ EL EQUIPO</Text>
      {snapshot.clubs.map((club) => {
        const selected = adminProfileClub === club.name;
        return (
          <Pressable
            key={club.name}
            onPress={() => void chooseAdminProfileClub(club.name)}
            style={({ pressed }) => [s.card, selected && { borderColor: '#d9af45', borderWidth: 2 }, pressed && { opacity: 0.72 }]}
          >
            <View style={s.playerRow}>
              <View style={s.flex}>
                <Text style={s.playerName}>{club.name}</Text>
                <Text style={s.muted}>{club.roster_count} jugadores · {money(club.balance)}</Text>
              </View>
              <Text style={{ color: selected ? '#ffd76a' : C.muted, fontSize: 22, fontWeight: '900' }}>{selected ? '✓' : '›'}</Text>
            </View>
          </Pressable>
        );
      })}

      {adminProfileClub ? (
        <>
          <View style={s.editorCard}>
            <Text style={s.playerName}>🏆 Asignar título</Text>
            <Text style={s.inputLabel}>TÍTULO</Text>
            <TextInput
              style={s.input}
              value={adminTitle}
              onChangeText={(value) => setAdminTitle(value.slice(0, 100))}
              placeholder="Ej: Campeón Liga AJPA T2"
              placeholderTextColor="#657382"
            />
            <Pressable
              onPress={() => setAdminTitleImportant((value) => !value)}
              style={({ pressed }) => [s.card, { marginTop: 10, borderColor: adminTitleImportant ? '#d9af45' : C.border }, pressed && { opacity: 0.75 }]}
            >
              <Text style={s.playerName}>{adminTitleImportant ? '⭐ TÍTULO IMPORTANTE' : '🏆 TÍTULO SIN ESTRELLA'}</Text>
              <Text style={s.muted}>{adminTitleImportant ? 'Al asignarlo se suma automáticamente 1 estrella.' : 'Se agrega al palmarés sin modificar las estrellas.'}</Text>
            </Pressable>
            <View style={{ marginTop: 12 }}><Button label={busy ? 'GUARDANDO…' : 'ASIGNAR TÍTULO'} kind="green" disabled={busy || !adminTitle.trim()} onPress={() => void submitClubTitle()} /></View>
          </View>

          <View style={s.editorCard}>
            <Text style={s.playerName}>⭐ Estrellas del club</Text>
            <Text style={s.muted}>Cada título importante puede sumar una. Este control permite corregir manualmente el total.</Text>
            <TextInput
              style={s.input}
              value={adminStars}
              onChangeText={(value) => setAdminStars(value.replace(/\D/g, '').slice(0, 2))}
              keyboardType="numeric"
              placeholder="0"
              placeholderTextColor="#657382"
            />
            <Button label={busy ? 'GUARDANDO…' : 'ACTUALIZAR ESTRELLAS'} disabled={busy} onPress={() => void submitClubStars()} />
          </View>

          <Text style={s.listHeading}>PALMARÉS ACTUAL · {adminProfileData?.titles.length ?? 0}</Text>
          {adminProfileData?.titles.map((title) => (
            <View key={title.id} style={s.card}>
              <Text style={s.playerName}>{title.important ? '⭐ ' : '🏆 '}{title.title}</Text>
              <Text style={s.muted}>{title.important ? 'Importante · contó para estrellas' : 'Sin estrella'}</Text>
            </View>
          ))}
        </>
      ) : null}
    </ScrollView>
  );

  const adminPrizeScreen = (
    <ScrollView contentContainerStyle={s.content} refreshControl={refreshControl} keyboardShouldPersistTaps="handled">
      <Title eyebrow="STAFF · ECONOMÍA" title="Pagar premios" subtitle="El premio se acredita al presupuesto real y aparece en Tesorería como Ingresos por premios." />

      <Text style={s.listHeading}>🏟️ EQUIPO</Text>
      {snapshot.clubs.map((club) => {
        const selected = prizeClub === club.name;
        return (
          <Pressable
            key={club.name}
            onPress={() => setPrizeClub(club.name)}
            style={({ pressed }) => [s.card, selected && { borderColor: '#d9af45', borderWidth: 2 }, pressed && { opacity: 0.72 }]}
          >
            <View style={s.playerRow}>
              <View style={s.flex}>
                <Text style={s.playerName}>{club.name}</Text>
                <Text style={s.playerValue}>Saldo: {money(club.balance)}</Text>
              </View>
              <Text style={{ color: selected ? '#ffd76a' : C.muted, fontSize: 22, fontWeight: '900' }}>{selected ? '✓' : '›'}</Text>
            </View>
          </Pressable>
        );
      })}

      <View style={s.editorCard}>
        <Text style={s.inputLabel}>PREMIO</Text>
        <TextInput
          style={s.input}
          value={prizeName}
          onChangeText={(value) => setPrizeName(value.slice(0, 120))}
          placeholder="Ej: Campeón de Liga · Temporada 2"
          placeholderTextColor="#657382"
        />
        <Text style={s.inputLabel}>MONTO</Text>
        <TextInput
          style={s.input}
          value={prizeAmount}
          onChangeText={(value) => setPrizeAmount(value.replace(/\D/g, '').slice(0, 12))}
          keyboardType="numeric"
          placeholder="Ej: 8000000"
          placeholderTextColor="#657382"
        />
        <Text style={s.muted}>{prizeClub ? 'Se acreditará a ' + prizeClub + ' como Ingresos por premios.' : 'Elegí primero el equipo.'}</Text>
        <View style={{ marginTop: 14 }}>
          <Button label={busy ? 'PROCESANDO…' : 'PAGAR PREMIO'} kind="green" disabled={busy || !prizeClub || !prizeName.trim() || !prizeAmount} onPress={submitPrize} />
        </View>
      </View>
    </ScrollView>
  );

`;
  ui = ui.replace(profileScreenMarker, screens + profileScreenMarker);
}

// Fondo Equipos para perfiles y tesorería; Staff conserva la estética del panel.
const bgMarker = `    if (['club', 'roster', 'economy', 'clubValue', 'clubInfo'].includes(screen)) return BG_EQUIPOS;`;
const bgReplacement = `    if (['club', 'roster', 'economy', 'clubValue', 'clubInfo', 'teams', 'teamProfile', 'treasury'].includes(screen)) return BG_EQUIPOS;`;
if (!ui.includes(bgReplacement)) {
  if (!ui.includes(bgMarker)) throw new Error('AJPA club profiles patch: no encontré fondo Equipos');
  ui = ui.replace(bgMarker, bgReplacement);
}

// Router final.
const profileRoute = `  else if (screen === 'profile') body = profileScreen;`;
if (!ui.includes(`screen === 'teams') body = teamsScreen`)) {
  if (!ui.includes(profileRoute)) throw new Error('AJPA club profiles patch: no encontré ruta Perfil');
  ui = ui.replace(
    profileRoute,
    `  else if (screen === 'teams') body = teamsScreen;\n  else if (screen === 'teamProfile') body = teamProfileScreen;\n  else if (screen === 'treasury') body = treasuryScreen;\n  else if (screen === 'adminClubProfiles') body = adminClubProfilesScreen;\n  else if (screen === 'adminPrize') body = adminPrizeScreen;\n${profileRoute}`,
  );
}

fs.writeFileSync(uiPath, ui);
console.log('AJPA Mobile: perfiles de equipo + títulos/estrellas + Tesorería + premios Staff aplicados');
