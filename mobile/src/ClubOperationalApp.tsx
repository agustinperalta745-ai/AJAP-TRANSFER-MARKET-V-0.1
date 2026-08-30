import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  Pressable,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';

import {
  LeagueSnapshot,
  MarketItem,
  MobileProfile,
  RosterPlayer,
  fetchMe,
  fetchRoster,
  fetchSnapshot,
  pairDevice,
  publishPlayer,
  releasePlayer,
  sendOffer,
  setSessionToken,
  signFreeAgent,
} from './api';
import { clearStoredSession, loadStoredSession, saveStoredSession } from './session';

type Tab = 'club' | 'market' | 'profile';

const C = {
  bg: '#02060a',
  panel: '#08121c',
  panel2: '#0b1824',
  border: '#1f3447',
  blue: '#2d92ff',
  blueSoft: '#8ac5ff',
  white: '#f7fbff',
  muted: '#92a0ad',
  green: '#45d47b',
  red: '#ff7880',
  orange: '#ffc36f',
};

const money = (value: number | null | undefined) =>
  value === null || value === undefined
    ? '—'
    : `$${Math.round(value).toLocaleString('es-AR')}`;

const apiError = (error: unknown) =>
  typeof error === 'object' && error && 'message' in error
    ? String((error as { message?: string }).message)
    : 'No se pudo completar la operación.';

function Button({
  label,
  onPress,
  kind = 'blue',
  disabled = false,
}: {
  label: string;
  onPress: () => void;
  kind?: 'blue' | 'green' | 'red' | 'ghost';
  disabled?: boolean;
}) {
  return (
    <Pressable
      disabled={disabled}
      onPress={onPress}
      style={({ pressed }) => [
        s.button,
        kind === 'green' && s.buttonGreen,
        kind === 'red' && s.buttonRed,
        kind === 'ghost' && s.buttonGhost,
        disabled && s.buttonDisabled,
        pressed && !disabled && { opacity: 0.72 },
      ]}
    >
      <Text style={s.buttonText}>{label}</Text>
    </Pressable>
  );
}

function SectionTitle({ eyebrow, title, subtitle }: { eyebrow: string; title: string; subtitle?: string }) {
  return (
    <View style={{ marginBottom: 8 }}>
      <Text style={s.eyebrow}>{eyebrow}</Text>
      <Text style={s.screenTitle}>{title}</Text>
      {subtitle ? <Text style={s.muted}>{subtitle}</Text> : null}
    </View>
  );
}

function ClubBadge({ club }: { club: string }) {
  const initials = club
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 3)
    .map((part) => part[0]?.toUpperCase())
    .join('') || 'AJ';
  return (
    <View style={s.clubBadge}>
      <Text style={s.clubBadgeText}>{initials}</Text>
    </View>
  );
}

function PlayerCard({
  player,
  onPublish,
  onRelease,
}: {
  player: RosterPlayer;
  onPublish: () => void;
  onRelease: () => void;
}) {
  return (
    <View style={s.card}>
      <View style={s.playerRow}>
        <View style={s.ovrBox}>
          <Text style={s.ovrValue}>{player.ovr ?? '—'}</Text>
          <Text style={s.ovrLabel}>OVR</Text>
        </View>
        <View style={s.flex}>
          <Text style={s.playerName}>{player.name}</Text>
          <Text style={s.muted}>{player.position || 'Sin posición'} · {player.code ?? 'SIN ID'}</Text>
          <Text style={s.playerValue}>Valor AJPA {money(player.market_value)}</Text>
        </View>
      </View>
      <View style={s.actionRow}>
        <Button label="PUBLICAR" onPress={onPublish} />
        <Button label="LIBERAR" onPress={onRelease} kind="ghost" />
      </View>
    </View>
  );
}

function MarketCard({
  item,
  ownClub,
  marketOpen,
  onOffer,
  onSign,
}: {
  item: MarketItem;
  ownClub: string | null;
  marketOpen: boolean;
  onOffer: () => void;
  onSign: () => void;
}) {
  const own = Boolean(ownClub && ownClub.localeCompare(item.club, undefined, { sensitivity: 'accent' }) === 0);
  return (
    <View style={s.card}>
      <View style={s.playerRow}>
        <View style={s.ovrBox}>
          <Text style={s.ovrValue}>{item.ovr ?? '—'}</Text>
          <Text style={s.ovrLabel}>OVR</Text>
        </View>
        <View style={s.flex}>
          <Text style={s.playerName}>{item.player}</Text>
          <Text style={s.muted}>{item.position} · {item.club}</Text>
          <Text style={s.playerValue}>{item.operation_type}</Text>
        </View>
        <Text style={[s.price, item.is_free_agent && { color: C.green }]}>{item.price}</Text>
      </View>
      {item.detail ? <Text style={s.detail}>{item.detail}</Text> : null}
      {item.is_free_agent ? (
        <View style={s.actionRow}>
          <Button label="FICHAR $0" onPress={onSign} kind="green" disabled={!marketOpen || !ownClub} />
        </View>
      ) : !own ? (
        <View style={s.actionRow}>
          <Button label="HACER OFERTA" onPress={onOffer} disabled={!marketOpen || !ownClub} />
        </View>
      ) : (
        <Text style={s.ownTag}>PUBLICACIÓN DE TU CLUB</Text>
      )}
    </View>
  );
}

export default function ClubOperationalApp() {
  const [tab, setTab] = useState<Tab>('club');
  const [snapshot, setSnapshot] = useState<LeagueSnapshot | null>(null);
  const [profile, setProfile] = useState<MobileProfile | null>(null);
  const [roster, setRoster] = useState<RosterPlayer[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [pairCode, setPairCode] = useState('');
  const [publishTarget, setPublishTarget] = useState<RosterPlayer | null>(null);
  const [publishPrice, setPublishPrice] = useState('');
  const [publishDetail, setPublishDetail] = useState('');
  const [offerTarget, setOfferTarget] = useState<MarketItem | null>(null);
  const [offerAmount, setOfferAmount] = useState('');
  const [offerMessage, setOfferMessage] = useState('');

  const loadAll = useCallback(async (manual = false) => {
    try {
      if (manual) setRefreshing(true); else setLoading(true);
      const snap = await fetchSnapshot();
      setSnapshot(snap);
      setError(null);

      try {
        const me = await fetchMe();
        setProfile(me);
        if (me.club) {
          setRoster(await fetchRoster(me.club));
        } else {
          setRoster([]);
        }
      } catch {
        setProfile(null);
        setRoster([]);
      }
    } catch (err) {
      setError(apiError(err));
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    (async () => {
      const token = await loadStoredSession();
      setSessionToken(token);
      await loadAll();
    })();
  }, [loadAll]);

  const mutate = async (work: () => Promise<unknown>, success: string) => {
    if (busy) return;
    setBusy(true);
    try {
      await work();
      setPublishTarget(null);
      setOfferTarget(null);
      Alert.alert('AJPA Transfer Market', success);
      await loadAll(true);
    } catch (err) {
      Alert.alert('No se pudo completar', apiError(err));
    } finally {
      setBusy(false);
    }
  };

  const pair = async () => {
    const code = pairCode.trim().toUpperCase();
    if (code.length !== 8) {
      Alert.alert('Código inválido', 'En Discord ejecutá /app_codigo e ingresá los 8 caracteres.');
      return;
    }
    setBusy(true);
    try {
      const result = await pairDevice(code);
      setSessionToken(result.token);
      await saveStoredSession(result.token);
      setPairCode('');
      setProfile(result.profile);
      if (result.profile.club) setRoster(await fetchRoster(result.profile.club));
      setTab('club');
      Alert.alert('Cuenta vinculada', `Tu equipo es ${result.profile.club ?? 'Staff / sin club'}.`);
    } catch (err) {
      Alert.alert('No se pudo vincular', apiError(err));
    } finally {
      setBusy(false);
    }
  };

  const logout = async () => {
    setSessionToken('');
    await clearStoredSession();
    setProfile(null);
    setRoster([]);
    setTab('profile');
  };

  const normalMarket = snapshot?.market.filter((item) => !item.is_free_agent) ?? [];
  const freeAgents = snapshot?.free_agents ?? [];
  const myClubData = useMemo(
    () => snapshot?.clubs.find((club) => profile?.club && club.name.toLocaleLowerCase() === profile.club.toLocaleLowerCase()) ?? null,
    [snapshot, profile?.club],
  );

  if (loading) {
    return (
      <View style={[s.root, s.center]}>
        <ActivityIndicator color={C.blue} size="large" />
        <Text style={s.loadingText}>Cargando AJPA Mobile…</Text>
      </View>
    );
  }

  if (!snapshot) {
    return (
      <View style={[s.root, s.center]}>
        <Text style={s.screenTitle}>Sin conexión</Text>
        <Text style={s.muted}>{error ?? 'No se pudo cargar el mercado.'}</Text>
        <View style={{ marginTop: 16 }}><Button label="REINTENTAR" onPress={() => loadAll()} /></View>
      </View>
    );
  }

  const refresh = (
    <RefreshControl refreshing={refreshing} onRefresh={() => loadAll(true)} tintColor={C.blue} colors={[C.blue]} />
  );

  const clubScreen = (
    <ScrollView contentContainerStyle={s.content} refreshControl={refresh}>
      <SectionTitle
        eyebrow="AJPA MOBILE v0.3 · OPERATIVA"
        title="Mi Club"
        subtitle="Esta pantalla usa tu asignación real de Discord."
      />

      {profile?.club ? (
        <View style={s.clubHero}>
          <ClubBadge club={profile.club} />
          <View style={s.flex}>
            <Text style={s.heroEyebrow}>TU EQUIPO ACTUAL</Text>
            <Text style={s.clubName}>{profile.club}</Text>
            <Text style={s.clubMeta}>
              {myClubData?.roster_count ?? profile.roster_count} jugadores · {money(myClubData?.balance ?? profile.balance)}
            </Text>
          </View>
          <View style={s.connectedPill}><Text style={s.connectedText}>VINCULADO</Text></View>
        </View>
      ) : (
        <View style={s.warningCard}>
          <Text style={s.warningTitle}>Todavía no hay equipo vinculado</Text>
          <Text style={s.muted}>Entrá a Perfil, ejecutá /app_codigo en Discord y cargá el código. Después esta pantalla mostrará tu club real.</Text>
          <View style={{ marginTop: 12 }}><Button label="VINCULAR DISCORD" onPress={() => setTab('profile')} /></View>
        </View>
      )}

      {profile?.club ? (
        <>
          <View style={s.quickRow}>
            <View style={s.quickCard}>
              <Text style={s.quickValue}>{roster.length}</Text>
              <Text style={s.quickLabel}>JUGADORES</Text>
            </View>
            <View style={s.quickCard}>
              <Text style={s.quickValue}>{money(myClubData?.balance ?? profile.balance)}</Text>
              <Text style={s.quickLabel}>PRESUPUESTO</Text>
            </View>
          </View>

          {publishTarget ? (
            <View style={s.editorCard}>
              <Text style={s.eyebrow}>PUBLICAR JUGADOR</Text>
              <Text style={s.editorTitle}>{publishTarget.name}</Text>
              <Text style={s.muted}>Transferencia definitiva · mínimo AJPA {money(publishTarget.market_value)}</Text>
              <Text style={s.inputLabel}>PRECIO PEDIDO</Text>
              <TextInput
                style={s.input}
                keyboardType="numeric"
                value={publishPrice}
                onChangeText={setPublishPrice}
                placeholder="Ej: 2500000"
                placeholderTextColor="#657382"
              />
              <Text style={s.inputLabel}>OBSERVACIÓN</Text>
              <TextInput
                style={[s.input, s.textarea]}
                value={publishDetail}
                onChangeText={setPublishDetail}
                multiline
                placeholder="Ej: negociable"
                placeholderTextColor="#657382"
              />
              <View style={s.actionRow}>
                <Button
                  label={busy ? 'PUBLICANDO…' : 'CONFIRMAR PUBLICACIÓN'}
                  disabled={busy}
                  onPress={() => {
                    if (!publishTarget.id) return;
                    mutate(
                      () => publishPlayer({
                        player_id: publishTarget.id!,
                        operation_type: 'TRANSFERENCIA',
                        price: publishPrice,
                        detail: publishDetail,
                      }),
                      `${publishTarget.name} ya aparece en Transferibles.`,
                    );
                  }}
                />
                <Button label="CANCELAR" kind="ghost" onPress={() => setPublishTarget(null)} disabled={busy} />
              </View>
            </View>
          ) : null}

          <SectionTitle eyebrow="PLANTEL" title="Tus jugadores" subtitle="Acá ya podés hacer una operación real." />
          {roster.length === 0 ? <View style={s.card}><Text style={s.muted}>No hay jugadores cargados para este club.</Text></View> : null}
          {roster.map((player) => (
            <PlayerCard
              key={player.id ?? player.name}
              player={player}
              onPublish={() => {
                setPublishTarget(player);
                setPublishPrice(player.market_value ? String(player.market_value) : '');
                setPublishDetail('');
              }}
              onRelease={() => {
                if (!player.id) return;
                const cost = player.market_value ? money(player.market_value * 0.2) : '20% del valor AJPA';
                Alert.alert(
                  'Liberar jugador',
                  `¿Confirmás liberar a ${player.name}? Se descontará ${cost} y pasará a Jugador Libre.`,
                  [
                    { text: 'Cancelar', style: 'cancel' },
                    {
                      text: 'LIBERAR',
                      style: 'destructive',
                      onPress: () => mutate(() => releasePlayer(player.id!), `${player.name} fue liberado y ahora figura como agente libre.`),
                    },
                  ],
                );
              }}
            />
          ))}
        </>
      ) : null}
    </ScrollView>
  );

  const marketScreen = (
    <ScrollView contentContainerStyle={s.content} refreshControl={refresh}>
      <SectionTitle
        eyebrow="MERCADO"
        title="Mercado de Pases"
        subtitle={snapshot.status.market_open ? 'Mercado abierto · operaciones habilitadas.' : 'Mercado cerrado · solo consulta.'}
      />

      <View style={[s.marketState, snapshot.status.market_open ? s.marketStateOpen : s.marketStateClosed]}>
        <View style={[s.dot, { backgroundColor: snapshot.status.market_open ? C.green : C.red }]} />
        <Text style={s.marketStateText}>{snapshot.status.market_open ? 'MERCADO ABIERTO' : 'MERCADO CERRADO'}</Text>
        <Text style={s.marketStateRight}>{profile?.club ?? 'Sin club vinculado'}</Text>
      </View>

      {offerTarget ? (
        <View style={s.editorCard}>
          <Text style={s.eyebrow}>OFERTAR POR</Text>
          <Text style={s.editorTitle}>{offerTarget.player}</Text>
          <Text style={s.muted}>{offerTarget.club} · precio publicado {offerTarget.price}</Text>
          <Text style={s.inputLabel}>DINERO OFRECIDO</Text>
          <TextInput
            style={s.input}
            keyboardType="numeric"
            value={offerAmount}
            onChangeText={setOfferAmount}
            placeholder="Ej: 5000000"
            placeholderTextColor="#657382"
          />
          <Text style={s.inputLabel}>MENSAJE / CONDICIONES</Text>
          <TextInput
            style={[s.input, s.textarea]}
            value={offerMessage}
            onChangeText={setOfferMessage}
            multiline
            placeholder="Opcional"
            placeholderTextColor="#657382"
          />
          <View style={s.actionRow}>
            <Button
              label={busy ? 'ENVIANDO…' : 'ENVIAR OFERTA'}
              disabled={busy}
              onPress={() => mutate(
                () => sendOffer(offerTarget.publication_id, { amount: offerAmount, message: offerMessage }),
                `Oferta enviada por ${offerTarget.player}.`,
              )}
            />
            <Button label="CANCELAR" kind="ghost" onPress={() => setOfferTarget(null)} disabled={busy} />
          </View>
        </View>
      ) : null}

      <Text style={s.listHeading}>TRANSFERIBLES · {normalMarket.length}</Text>
      {normalMarket.length === 0 ? <View style={s.card}><Text style={s.muted}>No hay publicaciones activas.</Text></View> : null}
      {normalMarket.map((item) => (
        <MarketCard
          key={item.publication_id}
          item={item}
          ownClub={profile?.club ?? null}
          marketOpen={snapshot.status.market_open}
          onOffer={() => {
            setOfferTarget(item);
            setOfferAmount('');
            setOfferMessage('');
          }}
          onSign={() => {}}
        />
      ))}

      <Text style={s.listHeading}>AGENTES LIBRES · {freeAgents.length}</Text>
      {freeAgents.length === 0 ? <View style={s.card}><Text style={s.muted}>No hay agentes libres ahora.</Text></View> : null}
      {freeAgents.map((item) => (
        <MarketCard
          key={item.publication_id}
          item={item}
          ownClub={profile?.club ?? null}
          marketOpen={snapshot.status.market_open}
          onOffer={() => {}}
          onSign={() => Alert.alert(
            'Fichar agente libre',
            `¿Querés fichar a ${item.player} por $0 para ${profile?.club ?? 'tu club'}?`,
            [
              { text: 'Cancelar', style: 'cancel' },
              {
                text: 'FICHAR $0',
                onPress: () => mutate(() => signFreeAgent(item.publication_id), `${item.player} quedó reservado para tu club y enviado a Staff/PES.`),
              },
            ],
          )}
        />
      ))}
    </ScrollView>
  );

  const profileScreen = (
    <ScrollView contentContainerStyle={s.content} refreshControl={refresh}>
      <SectionTitle eyebrow="CUENTA" title="Perfil" subtitle="La cuenta de Discord define qué club podés manejar." />
      {profile ? (
        <View style={s.profileCard}>
          <Text style={s.profileLabel}>DISCORD</Text>
          <Text style={s.profileValue}>{profile.user.global_name || profile.user.username || profile.user.id}</Text>
          <View style={s.separator} />
          <Text style={s.profileLabel}>TU CLUB</Text>
          <Text style={s.profileClub}>{profile.club ?? 'Staff / sin club'}</Text>
          <View style={s.separator} />
          <Text style={s.profileLabel}>ESTADO</Text>
          <Text style={[s.profileValue, { color: C.green }]}>VINCULADO · OPERACIONES HABILITADAS</Text>
          <View style={{ marginTop: 16 }}><Button label="CERRAR SESIÓN" kind="ghost" onPress={logout} /></View>
        </View>
      ) : (
        <View style={s.profileCard}>
          <Text style={s.profileLabel}>PASO 1 · DISCORD</Text>
          <Text style={s.profileValue}>Ejecutá /app_codigo dentro del servidor AJPA.</Text>
          <Text style={s.muted}>El bot te va a mostrar un código privado de 8 caracteres.</Text>
          <Text style={s.profileLabel}>PASO 2 · APP</Text>
          <TextInput
            style={[s.input, s.codeInput]}
            value={pairCode}
            onChangeText={(value) => setPairCode(value.toUpperCase().replace(/[^A-Z0-9]/g, '').slice(0, 8))}
            autoCapitalize="characters"
            maxLength={8}
            placeholder="XXXXXXXX"
            placeholderTextColor="#596878"
          />
          <Button label={busy ? 'VINCULANDO…' : 'VINCULAR DISCORD'} onPress={pair} disabled={busy} />
          <Text style={s.securityText}>El código dura 10 minutos y solo puede usarse una vez.</Text>
        </View>
      )}
    </ScrollView>
  );

  return (
    <View style={s.root}>
      <View style={s.topBar}>
        <View>
          <Text style={s.brand}>AJPA</Text>
          <Text style={s.brandSub}>TRANSFER MARKET · MOBILE</Text>
        </View>
        <View style={[s.topStatus, profile?.club ? s.topStatusLive : null]}>
          <Text style={[s.topStatusText, profile?.club ? { color: C.green } : null]}>
            {profile?.club ? 'OPERATIVA' : 'VINCULAR'}
          </Text>
        </View>
      </View>

      <View style={s.main}>
        {tab === 'club' ? clubScreen : tab === 'market' ? marketScreen : profileScreen}
      </View>

      <View style={s.nav}>
        {([
          ['club', 'MI CLUB', '▣'],
          ['market', 'MERCADO', '⇄'],
          ['profile', 'PERFIL', '◎'],
        ] as const).map(([id, label, icon]) => {
          const active = tab === id;
          return (
            <Pressable key={id} onPress={() => setTab(id)} style={s.navButton}>
              <Text style={[s.navIcon, active && s.navActive]}>{icon}</Text>
              <Text style={[s.navLabel, active && s.navActive]}>{label}</Text>
              {active ? <View style={s.navLine} /> : null}
            </Pressable>
          );
        })}
      </View>
    </View>
  );
}

const s = StyleSheet.create({
  root: { flex: 1, backgroundColor: C.bg },
  main: { flex: 1 },
  center: { alignItems: 'center', justifyContent: 'center', padding: 24 },
  loadingText: { color: C.muted, marginTop: 12 },
  content: { padding: 16, paddingBottom: 28, gap: 11 },
  topBar: {
    height: 60,
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 16,
    borderBottomWidth: 1,
    borderBottomColor: '#142230',
    backgroundColor: '#03080d',
  },
  brand: { color: C.white, fontSize: 23, fontWeight: '900', letterSpacing: 1.8, lineHeight: 25 },
  brandSub: { color: C.blue, fontSize: 8, fontWeight: '900', letterSpacing: 1.8 },
  topStatus: { borderRadius: 999, borderWidth: 1, borderColor: '#314454', paddingHorizontal: 10, paddingVertical: 6 },
  topStatusLive: { borderColor: '#24583a', backgroundColor: '#071a12' },
  topStatusText: { color: C.orange, fontSize: 9, fontWeight: '900', letterSpacing: 1 },
  eyebrow: { color: C.blue, fontSize: 10, fontWeight: '900', letterSpacing: 1.6, marginBottom: 4 },
  screenTitle: { color: C.white, fontSize: 28, fontWeight: '900' },
  muted: { color: C.muted, fontSize: 12.5, lineHeight: 18, marginTop: 3 },
  flex: { flex: 1, minWidth: 0 },
  card: { backgroundColor: C.panel, borderWidth: 1, borderColor: C.border, borderRadius: 18, padding: 14 },
  clubHero: {
    minHeight: 112,
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#071725',
    borderWidth: 1,
    borderColor: '#245781',
    borderRadius: 22,
    padding: 15,
  },
  clubBadge: { width: 66, height: 66, borderRadius: 16, backgroundColor: '#10283b', borderWidth: 1, borderColor: '#3e77a8', alignItems: 'center', justifyContent: 'center', marginRight: 13 },
  clubBadgeText: { color: C.blueSoft, fontSize: 19, fontWeight: '900', letterSpacing: 1 },
  heroEyebrow: { color: C.blueSoft, fontSize: 9, fontWeight: '900', letterSpacing: 1.4 },
  clubName: { color: C.white, fontSize: 22, fontWeight: '900', marginTop: 3 },
  clubMeta: { color: C.muted, fontSize: 11, marginTop: 4 },
  connectedPill: { marginLeft: 8, borderRadius: 999, backgroundColor: '#092219', borderWidth: 1, borderColor: '#245a3b', paddingHorizontal: 8, paddingVertical: 5 },
  connectedText: { color: C.green, fontSize: 8, fontWeight: '900' },
  warningCard: { backgroundColor: '#15120a', borderWidth: 1, borderColor: '#56451f', borderRadius: 18, padding: 15 },
  warningTitle: { color: C.orange, fontWeight: '900', fontSize: 17 },
  quickRow: { flexDirection: 'row', gap: 10 },
  quickCard: { flex: 1, backgroundColor: C.panel2, borderWidth: 1, borderColor: C.border, borderRadius: 16, padding: 13 },
  quickValue: { color: C.white, fontSize: 16, fontWeight: '900' },
  quickLabel: { color: C.muted, fontSize: 8, fontWeight: '900', letterSpacing: 1, marginTop: 3 },
  playerRow: { flexDirection: 'row', alignItems: 'center' },
  ovrBox: { width: 52, height: 52, borderRadius: 14, backgroundColor: '#0d2233', borderWidth: 1, borderColor: '#2a4d68', alignItems: 'center', justifyContent: 'center', marginRight: 12 },
  ovrValue: { color: C.blueSoft, fontSize: 19, fontWeight: '900', lineHeight: 20 },
  ovrLabel: { color: '#6b90ab', fontSize: 8, fontWeight: '900' },
  playerName: { color: C.white, fontSize: 16, fontWeight: '900' },
  playerValue: { color: C.blueSoft, fontSize: 10, fontWeight: '800', marginTop: 4 },
  price: { color: C.white, fontWeight: '900', fontSize: 14, marginLeft: 8 },
  detail: { color: '#b7c2cc', fontSize: 12, lineHeight: 17, marginTop: 10 },
  ownTag: { alignSelf: 'flex-start', color: C.blueSoft, borderRadius: 999, borderWidth: 1, borderColor: '#284967', paddingHorizontal: 9, paddingVertical: 5, fontSize: 8, fontWeight: '900', marginTop: 12 },
  actionRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginTop: 12 },
  button: { minHeight: 42, borderRadius: 12, paddingHorizontal: 14, alignItems: 'center', justifyContent: 'center', backgroundColor: C.blue },
  buttonGreen: { backgroundColor: '#176a3a' },
  buttonRed: { backgroundColor: '#a93840' },
  buttonGhost: { backgroundColor: '#0a1620', borderWidth: 1, borderColor: '#30475b' },
  buttonDisabled: { opacity: 0.4 },
  buttonText: { color: C.white, fontSize: 10, fontWeight: '900', letterSpacing: 0.5 },
  editorCard: { backgroundColor: '#091928', borderWidth: 1, borderColor: C.blue, borderRadius: 19, padding: 15 },
  editorTitle: { color: C.white, fontSize: 21, fontWeight: '900' },
  inputLabel: { color: C.blueSoft, fontWeight: '900', fontSize: 9, letterSpacing: 1.2, marginTop: 13, marginBottom: 6 },
  input: { minHeight: 48, backgroundColor: '#05101a', borderWidth: 1, borderColor: '#29435a', borderRadius: 12, paddingHorizontal: 13, color: C.white, fontSize: 16 },
  textarea: { minHeight: 78, paddingTop: 12, textAlignVertical: 'top' },
  codeInput: { textAlign: 'center', letterSpacing: 5, fontWeight: '900', fontSize: 21, marginVertical: 12 },
  marketState: { flexDirection: 'row', alignItems: 'center', borderWidth: 1, borderRadius: 14, padding: 12 },
  marketStateOpen: { backgroundColor: '#071b12', borderColor: '#245a3b' },
  marketStateClosed: { backgroundColor: '#1b0b0d', borderColor: '#613037' },
  dot: { width: 8, height: 8, borderRadius: 4, marginRight: 8 },
  marketStateText: { color: C.white, fontSize: 10, fontWeight: '900' },
  marketStateRight: { color: C.muted, fontSize: 10, marginLeft: 'auto', maxWidth: '48%' },
  listHeading: { color: C.blueSoft, fontWeight: '900', fontSize: 10, letterSpacing: 1.4, marginTop: 8 },
  profileCard: { backgroundColor: C.panel, borderWidth: 1, borderColor: C.border, borderRadius: 20, padding: 16 },
  profileLabel: { color: C.blueSoft, fontSize: 9, fontWeight: '900', letterSpacing: 1.2, marginTop: 8 },
  profileValue: { color: C.white, fontSize: 15, fontWeight: '800', marginTop: 5, lineHeight: 21 },
  profileClub: { color: C.white, fontSize: 24, fontWeight: '900', marginTop: 5 },
  separator: { height: 1, backgroundColor: '#1b2e3d', marginVertical: 13 },
  securityText: { color: C.muted, textAlign: 'center', fontSize: 10, marginTop: 11 },
  nav: { height: 70, flexDirection: 'row', borderTopWidth: 1, borderTopColor: '#152431', backgroundColor: '#03080d', paddingHorizontal: 8 },
  navButton: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  navIcon: { color: '#71808e', fontSize: 20, fontWeight: '900' },
  navLabel: { color: '#71808e', fontSize: 8, fontWeight: '900', letterSpacing: 0.7, marginTop: 3 },
  navActive: { color: C.blue },
  navLine: { width: 26, height: 2, borderRadius: 1, backgroundColor: C.blue, marginTop: 5 },
});
