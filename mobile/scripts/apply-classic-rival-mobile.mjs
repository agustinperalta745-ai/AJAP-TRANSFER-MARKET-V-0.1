import fs from 'node:fs';

const uiPath = new URL('../src/BotParityAppV2.tsx', import.meta.url);
let ui = fs.readFileSync(uiPath, 'utf8');

function mustReplace(search, replacement, label) {
  if (ui.includes(replacement)) return;
  if (!ui.includes(search)) throw new Error(`AJPA clásico mobile: no encontré ${label}`);
  ui = ui.replace(search, replacement);
}

const oldImport = String.raw`import {
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
const newImport = String.raw`import {
  ClassicState,
  ClubProfile,
  ClubProfileSummary,
  TreasuryData,
  addClubTitle,
  cancelClassicRequest,
  fetchClubProfile,
  fetchClubProfiles,
  fetchMyClassic,
  fetchMyTreasury,
  payClubPrize,
  releaseClassic,
  requestClassic,
  respondClassic,
  setClubStars,
} from './clubProfileApi';`;
if (!ui.includes(newImport)) mustReplace(oldImport, newImport, 'import clubProfileApi');

if (!ui.includes(`  | 'classic'`)) {
  mustReplace(`  | 'treasury'\n`, `  | 'treasury'\n  | 'classic'\n`, 'Screen classic');
}

const stateMarker = `  const [prizeAmount, setPrizeAmount] = useState('');`;
if (!ui.includes('const [classicState, setClassicState]')) {
  mustReplace(
    stateMarker,
    stateMarker + `\n  const [classicState, setClassicState] = useState<ClassicState | null>(null);`,
    'estado clásico',
  );
}

// Keep Mi Club's classic card fresh on every normal app refresh.
const rosterLoad = `        setRoster(me.club ? await fetchRoster(me.club) : []);`;
if (!ui.includes(`setClassicState(me.club ? await fetchMyClassic() : null);`)) {
  mustReplace(
    rosterLoad,
    rosterLoad + String.raw`
        try {
          setClassicState(me.club ? await fetchMyClassic() : null);
        } catch {
          setClassicState(null);
        }`,
    'loadAll clásico',
  );
}

const openMarker = `  const openScreen = async (next: Screen) => {`;
if (!ui.includes('const openClassic = async')) {
  const helpers = String.raw`  const refreshClassic = async () => {
    const state = await fetchMyClassic();
    setClassicState(state);
    return state;
  };

  const openClassic = async () => {
    if (!profile?.club) {
      Alert.alert('Sin club', 'Necesitás un club asignado para elegir un clásico rival.');
      return;
    }
    setBusy(true);
    try {
      await refreshClassic();
      setScreen('classic');
    } catch (error) {
      Alert.alert('Clásico rival', apiError(error));
    } finally {
      setBusy(false);
    }
  };

  const proposeClassic = (targetClub: string) => {
    Alert.alert(
      'Elegir clásico rival',
      '¿Querés proponer a ' + targetClub + ' como clásico rival?\n\nSi acepta, el clásico será fijo y solo podrá liberarse cuando uno de los dos tenga 11 o más victorias de diferencia en el historial entre ambos.',
      [
        { text: 'CANCELAR', style: 'cancel' },
        {
          text: 'ENVIAR PROPUESTA',
          onPress: async () => {
            setBusy(true);
            try {
              const result = await requestClassic(targetClub);
              await refreshClassic();
              await refreshClubProfiles();
              Alert.alert('Solicitud enviada', result.target_club + ' recibió la propuesta de clásico rival.');
            } catch (error) {
              Alert.alert('No se pudo enviar', apiError(error));
            } finally {
              setBusy(false);
            }
          },
        },
      ],
    );
  };

  const answerClassic = (requestId: number, requesterClub: string, decision: 'ACCEPT' | 'REJECT') => {
    const accepting = decision === 'ACCEPT';
    Alert.alert(
      accepting ? 'Aceptar clásico rival' : 'Rechazar propuesta',
      accepting
        ? requesterClub + ' quedará como tu clásico rival fijo. Solo podrá liberarse con 11 o más victorias de diferencia en el historial. ¿Confirmás?'
        : '¿Querés rechazar la propuesta de ' + requesterClub + '?',
      [
        { text: 'CANCELAR', style: 'cancel' },
        {
          text: accepting ? 'ACEPTAR CLÁSICO' : 'RECHAZAR',
          style: accepting ? 'default' : 'destructive',
          onPress: async () => {
            setBusy(true);
            try {
              await respondClassic(requestId, decision);
              await refreshClassic();
              await refreshClubProfiles();
              Alert.alert(
                accepting ? '🔥 Clásico confirmado' : 'Propuesta rechazada',
                accepting ? profile?.club + ' y ' + requesterClub + ' ya son clásicos rivales.' : 'La propuesta fue rechazada.',
              );
            } catch (error) {
              Alert.alert('No se pudo responder', apiError(error));
            } finally {
              setBusy(false);
            }
          },
        },
      ],
    );
  };

  const cancelOutgoingClassic = (requestId: number) => {
    Alert.alert('Cancelar propuesta', '¿Querés retirar esta solicitud antes de que el rival responda?', [
      { text: 'NO', style: 'cancel' },
      {
        text: 'SÍ, CANCELAR',
        style: 'destructive',
        onPress: async () => {
          setBusy(true);
          try {
            await cancelClassicRequest(requestId);
            await refreshClassic();
          } catch (error) {
            Alert.alert('No se pudo cancelar', apiError(error));
          } finally {
            setBusy(false);
          }
        },
      },
    ]);
  };

  const releaseCurrentClassic = () => {
    if (!classicState?.classic?.history.release_allowed) return;
    Alert.alert(
      'Liberar clásico rival',
      'El historial ya supera las 10 victorias de diferencia. ¿Querés liberar el clásico actual?',
      [
        { text: 'CANCELAR', style: 'cancel' },
        {
          text: 'LIBERAR CLÁSICO',
          style: 'destructive',
          onPress: async () => {
            setBusy(true);
            try {
              await releaseClassic();
              await refreshClassic();
              await refreshClubProfiles();
              Alert.alert('Clásico liberado', 'Tu club puede elegir un nuevo clásico rival.');
            } catch (error) {
              Alert.alert('No se pudo liberar', apiError(error));
            } finally {
              setBusy(false);
            }
          },
        },
      ],
    );
  };

`;
  mustReplace(openMarker, helpers + openMarker, 'helpers clásico');
}

// Mi Club: the rival and rival DT remain visible as a first-class card.
const treasuryTile = `<WideTile emoji="🏦" title="Tesorería" subtitle="Ingresos, egresos y premios acreditados al club." onPress={() => void openTreasury()} />`;
const classicTile = `<WideTile emoji="🔥" title="Clásico" subtitle={classicState?.classic ? 'Clásico: ' + classicState.classic.opponent + ' · ' + classicState.classic.opponent_manager.name : 'Elegí, aceptá o consultá tu clásico rival.'} onPress={() => void openClassic()} />`;
if (!ui.includes(`title="Clásico" subtitle={classicState?.classic`)) {
  mustReplace(treasuryTile, treasuryTile + '\n      ' + classicTile, 'tarjeta Clásico en Mi Club');
}

// Public club list shows the official rival beneath the titles/stars line.
const publicStars = String.raw`              <Text style={{ color: '#ffd76a', fontWeight: '900', marginTop: 5 }}>
                ⭐ {club.stars} · 🏆 {club.titles_count} título(s)
              </Text>`;
const publicStarsClassic = publicStars + String.raw`
              {club.classic ? (
                <Text style={{ color: '#ffad67', fontWeight: '900', marginTop: 5 }}>
                  🔥 Clásico: {club.classic.opponent} · {club.classic.opponent_manager.name}
                </Text>
              ) : null}`;
if (!ui.includes(`🔥 Clásico: {club.classic.opponent}`)) {
  mustReplace(publicStars, publicStarsClassic, 'clásico en lista pública');
}

// Public team profile: rival + current rival DT + live official H2H.
const summaryEnd = String.raw`      <View style={s.summaryRow}>
        <View style={s.summaryCard}><Text style={s.summaryValue}>{money(selectedClubProfile.squad_value)}</Text><Text style={s.summaryLabel}>VALOR PLANTILLA</Text></View>
        <View style={s.summaryCard}><Text style={s.summaryValue}>{selectedClubProfile.titles.length}</Text><Text style={s.summaryLabel}>TÍTULOS</Text></View>
      </View>`;
const publicClassic = summaryEnd + String.raw`

      <Text style={s.listHeading}>🔥 CLÁSICO</Text>
      {selectedClubProfile.classic ? (
        <View style={[s.card, { borderColor: '#ff8b45', borderWidth: 1.5 }]}>
          <Text style={s.playerName}>Clásico: {selectedClubProfile.classic.opponent} · {selectedClubProfile.classic.opponent_manager.name}</Text>
          <Text style={s.playerValue}>
            Historial · {selectedClubProfile.club} {selectedClubProfile.classic.history.wins} victorias · {selectedClubProfile.classic.history.draws} empates · {selectedClubProfile.classic.opponent} {selectedClubProfile.classic.history.losses} victorias
          </Text>
          <Text style={s.muted}>
            {selectedClubProfile.classic.history.played} partidos · Goles {selectedClubProfile.classic.history.goals_for}-{selectedClubProfile.classic.history.goals_against}
          </Text>
        </View>
      ) : (
        <View style={s.card}><Text style={s.muted}>Este club todavía no tiene clásico rival confirmado.</Text></View>
      )}`;
if (!ui.includes(`selectedClubProfile.classic.history.wins`)) {
  mustReplace(summaryEnd, publicClassic, 'clásico en perfil público');
}

const treasuryScreenMarker = `  const treasuryScreen = (`;
if (!ui.includes('const classicScreen = (')) {
  const classicScreen = String.raw`  const classicScreen = (
    <ScrollView contentContainerStyle={s.content} refreshControl={refreshControl}>
      <Title eyebrow="MI CLUB · CLÁSICO" title="Clásico rival" subtitle="Elegí un rival, respondé propuestas y consultá el historial oficial entre ambos." />

      {classicState?.classic ? (
        <>
          <View style={[s.heroClubCard, { borderColor: '#ff8b45' }]}>
            <View style={s.heroIconWrap}><Text style={s.heroIcon}>🔥</Text></View>
            <View style={s.flex}>
              <Text style={s.heroClubName}>{classicState.club} vs {classicState.classic.opponent}</Text>
              <Text style={s.muted}>DT rival · {classicState.classic.opponent_manager.name}</Text>
            </View>
          </View>

          <Text style={s.listHeading}>📊 HISTORIAL ENTRE AMBOS</Text>
          <View style={s.card}>
            <Text style={s.playerName}>
              {classicState.club} {classicState.classic.history.wins} · {classicState.classic.history.draws} empates · {classicState.classic.opponent} {classicState.classic.history.losses}
            </Text>
            <Text style={s.playerValue}>{classicState.classic.history.played} partidos oficiales</Text>
            <Text style={s.muted}>Goles: {classicState.classic.history.goals_for} - {classicState.classic.history.goals_against}</Text>
          </View>

          <View style={s.card}>
            <Text style={s.playerName}>🔒 Clásico fijo</Text>
            <Text style={s.muted}>{classicState.rule.text}</Text>
            {classicState.classic.history.release_allowed ? (
              <View style={{ marginTop: 12 }}><Button label="LIBERAR CLÁSICO" kind="red" disabled={busy} onPress={releaseCurrentClassic} /></View>
            ) : (
              <Text style={{ color: '#ffad67', fontWeight: '900', marginTop: 10 }}>
                Diferencia actual: {Math.abs(classicState.classic.history.win_difference)} victoria(s) · se necesitan 11.
              </Text>
            )}
          </View>
        </>
      ) : (
        <>
          {classicState?.incoming.length ? <Text style={s.listHeading}>📨 PROPUESTAS RECIBIDAS</Text> : null}
          {classicState?.incoming.map((request) => (
            <View key={request.id} style={[s.card, { borderColor: '#ff8b45', borderWidth: 1.5 }]}>
              <Text style={s.playerName}>🔥 {request.requester_club} considera que sos su clásico rival</Text>
              <Text style={s.muted}>DT · {request.requester_manager.name}</Text>
              <Text style={[s.detail, { marginTop: 8 }]}>⚠️ Si aceptás, {request.requester_club} será tu clásico rival fijo y solo podrá liberarse con 11 o más victorias de diferencia en el historial entre ambos.</Text>
              <View style={s.actionRow}>
                <Button label="ACEPTAR" kind="green" disabled={busy} onPress={() => answerClassic(request.id, request.requester_club, 'ACCEPT')} />
                <Button label="RECHAZAR" kind="red" disabled={busy} onPress={() => answerClassic(request.id, request.requester_club, 'REJECT')} />
              </View>
            </View>
          ))}

          {classicState?.outgoing ? (
            <>
              <Text style={s.listHeading}>📤 PROPUESTA ENVIADA</Text>
              <View style={s.card}>
                <Text style={s.playerName}>Esperando a {classicState.outgoing.target_club}</Text>
                <Text style={s.muted}>DT rival · {classicState.outgoing.target_manager.name}</Text>
                <View style={{ marginTop: 12 }}><Button label="CANCELAR PROPUESTA" kind="ghost" disabled={busy} onPress={() => cancelOutgoingClassic(classicState.outgoing!.id)} /></View>
              </View>
            </>
          ) : null}

          {!classicState?.outgoing ? (
            <>
              <Text style={s.listHeading}>🔥 ELEGIR CLÁSICO</Text>
              <Text style={s.muted}>Seleccioná uno de los equipos de AJPA. El DT rival deberá aceptar la propuesta.</Text>
              {classicState?.available_clubs.map((candidate) => (
                <Pressable
                  key={candidate.club}
                  disabled={!candidate.available || busy}
                  onPress={() => proposeClassic(candidate.club)}
                  style={({ pressed }) => [s.card, !candidate.available && { opacity: 0.45 }, pressed && candidate.available && { opacity: 0.72 }]}
                >
                  <View style={s.playerRow}>
                    <View style={s.flex}>
                      <Text style={s.playerName}>{candidate.club}</Text>
                      <Text style={s.muted}>DT · {candidate.manager.name}</Text>
                      {candidate.reason ? <Text style={{ color: C.orange, marginTop: 4 }}>{candidate.reason}</Text> : null}
                    </View>
                    <Text style={s.chevron}>{candidate.available ? '›' : '🔒'}</Text>
                  </View>
                </Pressable>
              ))}
            </>
          ) : null}
        </>
      )}
    </ScrollView>
  );

`;
  mustReplace(treasuryScreenMarker, classicScreen + treasuryScreenMarker, 'pantalla clásico');
}

const bgOld = `    if (['club', 'roster', 'economy', 'clubValue', 'clubInfo', 'teams', 'teamProfile', 'treasury'].includes(screen)) return BG_EQUIPOS;`;
const bgNew = `    if (['club', 'roster', 'economy', 'clubValue', 'clubInfo', 'teams', 'teamProfile', 'treasury', 'classic'].includes(screen)) return BG_EQUIPOS;`;
if (!ui.includes(bgNew)) mustReplace(bgOld, bgNew, 'fondo clásico');

const routeMarker = `  else if (screen === 'treasury') body = treasuryScreen;`;
const routeWithClassic = routeMarker + `\n  else if (screen === 'classic') body = classicScreen;`;
if (!ui.includes(`screen === 'classic') body = classicScreen`)) {
  mustReplace(routeMarker, routeWithClassic, 'ruta clásico');
}

fs.writeFileSync(uiPath, ui);
console.log('AJPA Mobile: clásico rival + solicitudes + H2H público aplicados');
