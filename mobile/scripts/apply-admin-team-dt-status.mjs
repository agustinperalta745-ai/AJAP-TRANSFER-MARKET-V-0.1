import fs from 'node:fs';

const uiPath = new URL('../src/BotParityAppV2.tsx', import.meta.url);
let ui = fs.readFileSync(uiPath, 'utf8');
const marker = '// admin-team-dt-status applied';
if (ui.includes(marker)) process.exit(0);

function mustReplace(search, replacement, label) {
  if (!ui.includes(search)) throw new Error(`AJPA equipos/DT Staff: no encontré ${label}`);
  ui = ui.replace(search, replacement);
}

// Nueva pantalla Staff.
if (!ui.includes(`  | 'adminTeamDtStatus'`)) {
  mustReplace(
    `  | 'admin'\n`,
    `  | 'admin'\n  | 'adminTeamDtStatus'\n`,
    'Screen admin',
  );
}

// Reutilizamos el feed real de perfiles de club, que ya trae manager.user_id y manager.name.
const openScreenMarker = `  const openScreen = async (next: Screen) => {`;
if (!ui.includes('const openAdminTeamDtStatus = async')) {
  if (!ui.includes('const refreshClubProfiles = async')) {
    throw new Error('AJPA equipos/DT Staff: falta refreshClubProfiles');
  }
  const helper = String.raw`  const openAdminTeamDtStatus = async () => {
    setBusy(true);
    try {
      await refreshClubProfiles();
      setScreen('adminTeamDtStatus');
    } catch (error) {
      Alert.alert('Equipos y DTs', apiError(error));
    } finally {
      setBusy(false);
    }
  };

`;
  mustReplace(openScreenMarker, helper + openScreenMarker, 'openScreen');
}

// Acceso visible dentro del Panel Staff, junto a Planteles.
const rostersTile = `<WideTile emoji="👥" title="Planteles" subtitle="Altas, bajas, movimientos y consulta." onPress={() => openScreen('adminRosters')} />`;
const dtTile = `<WideTile emoji="🧑‍💼" title="Equipos y DTs" subtitle="Ver qué clubes tienen DT asignado y cuáles están libres." onPress={() => void openAdminTeamDtStatus()} />`;
if (!ui.includes(`title="Equipos y DTs"`)) {
  mustReplace(rostersTile, rostersTile + '\n      ' + dtTile, 'tile Planteles del Panel Staff');
}

// Pantalla de consulta: primero los equipos libres, luego los ocupados.
if (!ui.includes('const adminTeamDtStatusScreen = (')) {
  const insertMarker = `  const teamsScreen = (`;
  const screen = String.raw`  const adminTeamDtStatusScreen = (
    <ScrollView contentContainerStyle={s.content} refreshControl={refreshControl}>
      <Title
        eyebrow="STAFF · EQUIPOS"
        title="Equipos y DTs"
        subtitle="Estado real de asignaciones. Se actualiza con los perfiles de clubes de AJPA."
      />

      <View style={s.summaryRow}>
        <View style={s.summaryCard}>
          <Text style={[s.summaryValue, { color: C.green }]}>
            {clubProfiles.filter((club) => Boolean(club.manager?.user_id)).length}
          </Text>
          <Text style={s.summaryLabel}>CON DT</Text>
        </View>
        <View style={s.summaryCard}>
          <Text style={[s.summaryValue, { color: C.red }]}>
            {clubProfiles.filter((club) => !club.manager?.user_id).length}
          </Text>
          <Text style={s.summaryLabel}>SIN DT</Text>
        </View>
      </View>

      <Text style={[s.listHeading, { color: C.red }]}>🔴 SIN DT · {clubProfiles.filter((club) => !club.manager?.user_id).length}</Text>
      {clubProfiles.filter((club) => !club.manager?.user_id).length === 0 ? (
        <View style={s.card}><Text style={s.muted}>Todos los equipos tienen DT asignado.</Text></View>
      ) : null}
      {clubProfiles
        .filter((club) => !club.manager?.user_id)
        .slice()
        .sort((a, b) => a.club.localeCompare(b.club, 'es'))
        .map((club) => (
          <View key={'free-' + club.club} style={[s.card, { borderColor: 'rgba(255,120,128,0.55)' }]}>
            <View style={s.playerRow}>
              <View style={[s.heroIconWrap, { borderColor: 'rgba(255,120,128,0.55)' }]}>
                <Text style={s.heroIcon}>🏟️</Text>
              </View>
              <View style={s.flex}>
                <Text style={s.playerName}>{club.club}</Text>
                <Text style={[s.statusTag, { color: C.red }]}>SIN DT ASIGNADO</Text>
                <Text style={s.muted}>{club.roster_count} jugadores · {money(club.balance)}</Text>
              </View>
            </View>
          </View>
        ))}

      <Text style={[s.listHeading, { color: C.green, marginTop: 18 }]}>🟢 CON DT · {clubProfiles.filter((club) => Boolean(club.manager?.user_id)).length}</Text>
      {clubProfiles
        .filter((club) => Boolean(club.manager?.user_id))
        .slice()
        .sort((a, b) => a.club.localeCompare(b.club, 'es'))
        .map((club) => (
          <View key={'assigned-' + club.club} style={[s.card, { borderColor: 'rgba(69,212,123,0.42)' }]}>
            <View style={s.playerRow}>
              <View style={[s.heroIconWrap, { borderColor: 'rgba(69,212,123,0.45)' }]}>
                <Text style={s.heroIcon}>🛡️</Text>
              </View>
              <View style={s.flex}>
                <Text style={s.playerName}>{club.club}</Text>
                <Text style={[s.statusTag, { color: C.green }]}>DT ASIGNADO</Text>
                <Text style={s.muted}>DT · {club.manager.name}</Text>
              </View>
            </View>
          </View>
        ))}
    </ScrollView>
  );

`;
  mustReplace(insertMarker, screen + insertMarker, 'teamsScreen');
}

// Despacho de la nueva pantalla.
if (!ui.includes(`else if (screen === 'adminTeamDtStatus') body = adminTeamDtStatusScreen;`)) {
  mustReplace(
    `  else if (screen === 'admin') body = adminMenu;`,
    `  else if (screen === 'admin') body = adminMenu;\n  else if (screen === 'adminTeamDtStatus') body = adminTeamDtStatusScreen;`,
    'despacho admin',
  );
}

fs.writeFileSync(uiPath, ui + '\n' + marker + '\n');
console.log('AJPA Staff: vista Equipos y DTs aplicada.');
