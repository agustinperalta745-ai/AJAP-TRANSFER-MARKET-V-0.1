import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  Image,
  Modal,
  Pressable,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';

import {
  API_CONFIGURED,
  LeagueSnapshot,
  MarketItem,
  MobileProfile,
  MyOffers,
  OfferItem,
  RosterPlayer,
  acceptOffer,
  fetchMe,
  fetchMyOffers,
  fetchRoster,
  fetchSnapshot,
  pairDevice,
  publishPlayer,
  rejectOffer,
  releasePlayer,
  sendOffer,
  setSessionToken,
  signFreeAgent,
  withdrawPublication,
} from './api';
import { loadStoredSession, saveStoredSession, clearStoredSession } from './session';
import { AJPA_LOGO_DATA_URI } from './branding';
import { BG_INICIO } from './bg_inicio';
import { BG_EQUIPOS } from './bg_equipos';
import { BG_MERCADO } from './bg_mercado';
import { BG_LIBRES } from './bg_libres';
import { BG_PERFIL } from './bg_perfil';

type Tab = 'inicio' | 'equipos' | 'mercado' | 'libres' | 'perfil';
type Action =
  | { type: 'publish'; player: RosterPlayer }
  | { type: 'offer'; item: MarketItem }
  | null;

const BG: Record<Tab, string> = {
  inicio: BG_INICIO,
  equipos: BG_EQUIPOS,
  mercado: BG_MERCADO,
  libres: BG_LIBRES,
  perfil: BG_PERFIL,
};

const C = {
  blue: '#2d92ff',
  blueSoft: '#75b8ff',
  white: '#f7fbff',
  muted: '#96a4b2',
  line: '#203142',
  panel: 'rgba(7,16,25,0.92)',
  dark: '#02060a',
  green: '#4ade80',
  red: '#ff8b92',
  orange: '#ffc16f',
};

const money = (value: number | null | undefined) =>
  value === null || value === undefined ? '—' : `$${Math.round(value).toLocaleString('es-AR')}`;

const errorMessage = (err: unknown) =>
  typeof err === 'object' && err && 'message' in err
    ? String((err as { message?: string }).message)
    : 'No se pudo completar la operación.';

function Card({ children, style }: { children: React.ReactNode; style?: any }) {
  return <View style={[s.card, style]}>{children}</View>;
}

function Button({ label, onPress, kind = 'primary', disabled = false, small = false }: {
  label: string;
  onPress: () => void;
  kind?: 'primary' | 'danger' | 'success' | 'ghost';
  disabled?: boolean;
  small?: boolean;
}) {
  return (
    <Pressable
      disabled={disabled}
      onPress={onPress}
      style={({ pressed }) => [
        s.button,
        small && s.buttonSmall,
        kind === 'danger' && s.buttonDanger,
        kind === 'success' && s.buttonSuccess,
        kind === 'ghost' && s.buttonGhost,
        disabled && s.buttonDisabled,
        pressed && !disabled && { opacity: 0.72 },
      ]}
    >
      <Text style={[s.buttonText, kind === 'ghost' && s.buttonGhostText]}>{label}</Text>
    </Pressable>
  );
}

function Stat({ icon, value, label }: { icon: string; value: number; label: string }) {
  return (
    <View style={s.stat}>
      <Text style={s.statIcon}>{icon}</Text>
      <Text style={s.statValue}>{value}</Text>
      <Text style={s.statLabel}>{label}</Text>
    </View>
  );
}

function MenuCard({ eyebrow, title, text, icon, onPress }: {
  eyebrow: string; title: string; text: string; icon: string; onPress: () => void;
}) {
  return (
    <Pressable onPress={onPress} style={({ pressed }) => [s.menuCard, pressed && { opacity: 0.76 }]}>
      <View style={s.menuIcon}><Text style={s.menuIconText}>{icon}</Text></View>
      <View style={s.flex}>
        <Text style={s.eyebrow}>{eyebrow}</Text>
        <Text style={s.menuTitle}>{title}</Text>
        <Text style={s.menuText}>{text}</Text>
      </View>
      <Text style={s.chevron}>›</Text>
    </Pressable>
  );
}

function PlayerCard({ player, own, onPublish, onRelease }: {
  player: RosterPlayer;
  own: boolean;
  onPublish: () => void;
  onRelease: () => void;
}) {
  return (
    <Card>
      <View style={s.row}>
        <View style={s.ovr}>
          <Text style={s.ovrValue}>{player.ovr ?? '—'}</Text>
          <Text style={s.ovrLabel}>OVR</Text>
        </View>
        <View style={s.flex}>
          <Text style={s.name}>{player.name}</Text>
          <Text style={s.muted}>{player.position || 'Sin posición'} · {player.code ?? 'SIN ID'}</Text>
        </View>
        <Text style={s.money}>{money(player.market_value)}</Text>
      </View>
      {own && player.id ? (
        <View style={s.actions}>
          <Button label="PUBLICAR" onPress={onPublish} small />
          <Button label="LIBERAR" onPress={onRelease} kind="ghost" small />
        </View>
      ) : null}
    </Card>
  );
}

function MarketCard({ item, profile, marketOpen, onOffer, onWithdraw, onSign }: {
  item: MarketItem;
  profile: MobileProfile | null;
  marketOpen: boolean;
  onOffer: () => void;
  onWithdraw: () => void;
  onSign: () => void;
}) {
  const ownClub = Boolean(profile?.club && profile.club.toLocaleLowerCase() === item.club.toLocaleLowerCase());
  return (
    <Card>
      <View style={s.row}>
        <View style={s.ovr}>
          <Text style={s.ovrValue}>{item.ovr ?? '—'}</Text>
          <Text style={s.ovrLabel}>OVR</Text>
        </View>
        <View style={s.flex}>
          <Text style={s.name}>{item.player}</Text>
          <Text style={s.muted}>{item.position} · {item.club}</Text>
        </View>
        <Text style={[s.money, item.is_free_agent && { color: C.green }]}>{item.price}</Text>
      </View>
      <View style={s.divider} />
      <Text style={s.operation}>{item.operation_type}</Text>
      <Text style={s.detail}>{item.detail || 'Sin observaciones'}</Text>
      {item.market_value !== null ? <Text style={s.marketValue}>Valor AJPA: {money(item.market_value)}</Text> : null}
      {profile ? (
        <View style={s.actions}>
          {item.is_free_agent ? (
            <Button label="FICHAR $0" onPress={onSign} kind="success" disabled={!marketOpen} small />
          ) : ownClub ? (
            <Button label="RETIRAR PUBLICACIÓN" onPress={onWithdraw} kind="ghost" small />
          ) : (
            <Button label="HACER OFERTA" onPress={onOffer} disabled={!marketOpen} small />
          )}
        </View>
      ) : null}
    </Card>
  );
}

function OfferCard({ offer, onAccept, onReject }: {
  offer: OfferItem;
  onAccept?: () => void;
  onReject?: () => void;
}) {
  const pending = offer.status === 'PENDIENTE';
  return (
    <Card>
      <View style={s.offerTop}>
        <View style={s.flex}>
          <Text style={s.name}>{offer.player}</Text>
          <Text style={s.muted}>{offer.from_club} → {offer.to_club}</Text>
        </View>
        <Text style={[s.status, pending ? s.statusPending : s.statusDone]}>{offer.status}</Text>
      </View>
      <Text style={s.operation}>{offer.offer_kind}</Text>
      <Text style={s.detail}>Dinero: {offer.amount}</Text>
      {offer.offered_player ? <Text style={s.detail}>Jugador: {offer.offered_player}</Text> : null}
      <Text style={s.marketValue}>{offer.message}</Text>
      {pending && onAccept && onReject ? (
        <View style={s.actions}>
          <Button label="ACEPTAR" onPress={onAccept} kind="success" small />
          <Button label="RECHAZAR" onPress={onReject} kind="danger" small />
        </View>
      ) : null}
    </Card>
  );
}

export default function LiveAppFunctional() {
  const [tab, setTab] = useState<Tab>('inicio');
  const [snapshot, setSnapshot] = useState<LeagueSnapshot | null>(null);
  const [profile, setProfile] = useState<MobileProfile | null>(null);
  const [offers, setOffers] = useState<MyOffers>({ incoming: [], outgoing: [] });
  const [selectedClub, setSelectedClub] = useState<string | null>(null);
  const [roster, setRoster] = useState<RosterPlayer[]>([]);
  const [ownRoster, setOwnRoster] = useState<RosterPlayer[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [rosterLoading, setRosterLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [pairCode, setPairCode] = useState('');
  const [action, setAction] = useState<Action>(null);

  const [pubType, setPubType] = useState('TRANSFERENCIA');
  const [pubPrice, setPubPrice] = useState('');
  const [pubDetail, setPubDetail] = useState('');
  const [loanSeasons, setLoanSeasons] = useState('1');
  const [purchaseOption, setPurchaseOption] = useState(false);
  const [purchaseValue, setPurchaseValue] = useState('');

  const [offerAmount, setOfferAmount] = useState('');
  const [offerMessage, setOfferMessage] = useState('');
  const [offeredPlayerId, setOfferedPlayerId] = useState<number | null>(null);

  const load = useCallback(async (manual = false) => {
    if (!API_CONFIGURED) {
      setLoading(false);
      setError('La APK no tiene URL de API configurada.');
      return;
    }
    try {
      if (manual) setRefreshing(true); else setLoading(true);
      const snap = await fetchSnapshot();
      setSnapshot(snap);
      setError(null);
      try {
        const me = await fetchMe();
        setProfile(me);
        if (me.club) setSelectedClub(me.club);
        try { setOffers(await fetchMyOffers()); } catch { setOffers({ incoming: [], outgoing: [] }); }
      } catch (authErr) {
        const msg = errorMessage(authErr);
        if (msg.toLocaleLowerCase().includes('sesión') || msg.toLocaleLowerCase().includes('vincul')) {
          setProfile(null);
          setOffers({ incoming: [], outgoing: [] });
        }
        setSelectedClub((current) => current ?? snap.clubs[0]?.name ?? null);
      }
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    (async () => {
      const token = await loadStoredSession();
      setSessionToken(token);
      await load();
    })();
  }, [load]);

  useEffect(() => {
    if (!selectedClub) {
      setRoster([]);
      return;
    }
    let cancelled = false;
    setRosterLoading(true);
    fetchRoster(selectedClub)
      .then((players) => { if (!cancelled) setRoster(players); })
      .catch(() => { if (!cancelled) setRoster([]); })
      .finally(() => { if (!cancelled) setRosterLoading(false); });
    return () => { cancelled = true; };
  }, [selectedClub, snapshot]);

  useEffect(() => {
    if (!profile?.club) {
      setOwnRoster([]);
      return;
    }
    fetchRoster(profile.club).then(setOwnRoster).catch(() => setOwnRoster([]));
  }, [profile?.club, snapshot]);

  const market = snapshot?.market.filter((item) => !item.is_free_agent) ?? [];
  const free = snapshot?.free_agents ?? [];
  const totalPlayers = snapshot?.clubs.reduce((sum, club) => sum + club.roster_count, 0) ?? 0;
  const selected = useMemo(() => snapshot?.clubs.find((club) => club.name === selectedClub) ?? null, [snapshot, selectedClub]);
  const ownSelected = Boolean(profile?.club && selectedClub && profile.club.toLocaleLowerCase() === selectedClub.toLocaleLowerCase());

  const reloadAfterMutation = async () => {
    setAction(null);
    await load(true);
  };

  const mutate = async (work: () => Promise<any>, success: string) => {
    if (busy) return;
    setBusy(true);
    try {
      await work();
      Alert.alert('AJPA Transfer Market', success);
      await reloadAfterMutation();
    } catch (err) {
      Alert.alert('No se pudo completar', errorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  const doPair = async () => {
    if (pairCode.trim().length < 8) {
      Alert.alert('Código inválido', 'En Discord usá /app_codigo y copiá los 8 caracteres.');
      return;
    }
    setBusy(true);
    try {
      const result = await pairDevice(pairCode);
      setSessionToken(result.token);
      await saveStoredSession(result.token);
      setProfile(result.profile);
      setPairCode('');
      if (result.profile.club) setSelectedClub(result.profile.club);
      await load(true);
      Alert.alert('Cuenta vinculada', 'Ya podés operar el mercado desde la app.');
    } catch (err) {
      Alert.alert('No se pudo vincular', errorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  const logout = async () => {
    setSessionToken('');
    await clearStoredSession();
    setProfile(null);
    setOffers({ incoming: [], outgoing: [] });
    Alert.alert('Sesión cerrada', 'La app volvió a modo consulta.');
  };

  const openPublish = (player: RosterPlayer) => {
    setPubType('TRANSFERENCIA');
    setPubPrice(player.market_value ? String(player.market_value) : '');
    setPubDetail('');
    setLoanSeasons('1');
    setPurchaseOption(false);
    setPurchaseValue('');
    setAction({ type: 'publish', player });
  };

  const openOffer = (item: MarketItem) => {
    setOfferAmount('');
    setOfferMessage('');
    setOfferedPlayerId(null);
    setAction({ type: 'offer', item });
  };

  const submitPublication = () => {
    if (action?.type !== 'publish' || !action.player.id) return;
    mutate(
      () => publishPlayer({
        player_id: action.player.id!,
        operation_type: pubType,
        price: pubPrice,
        detail: pubDetail,
        loan_seasons: pubType === 'PRÉSTAMO' ? loanSeasons : undefined,
        purchase_option_enabled: pubType === 'PRÉSTAMO' ? purchaseOption : undefined,
        purchase_option_value: pubType === 'PRÉSTAMO' && purchaseOption ? purchaseValue : undefined,
      }),
      `${action.player.name} quedó publicado.`,
    );
  };

  const submitOffer = () => {
    if (action?.type !== 'offer') return;
    mutate(
      () => sendOffer(action.item.publication_id, {
        amount: offerAmount,
        offered_player_id: offeredPlayerId,
        message: offerMessage,
      }),
      `Oferta enviada por ${action.item.player}.`,
    );
  };

  const refreshControl = (
    <RefreshControl refreshing={refreshing} onRefresh={() => load(true)} tintColor={C.blue} colors={[C.blue]} />
  );

  const content = (() => {
    if (loading) {
      return (
        <View style={s.center}>
          <Image source={{ uri: AJPA_LOGO_DATA_URI }} style={s.loadingLogo} />
          <ActivityIndicator size="large" color={C.blue} />
          <Text style={s.muted}>Cargando AJPA…</Text>
        </View>
      );
    }
    if (!snapshot) {
      return (
        <ScrollView contentContainerStyle={s.content}>
          <Card><Text style={s.screenTitle}>Sin conexión</Text><Text style={s.muted}>{error ?? 'No se pudo cargar AJPA.'}</Text></Card>
        </ScrollView>
      );
    }

    if (tab === 'inicio') {
      return (
        <ScrollView contentContainerStyle={s.content} refreshControl={refreshControl}>
          <View style={s.hero}>
            <View style={s.heroCopy}>
              <Text style={s.brand}>AJPA</Text>
              <Text style={s.brandSub}>TRANSFER MARKET</Text>
              <Text style={s.heroSmall}>Temporada en vivo</Text>
              <Text style={s.heroTitle}>Gestioná tu club.</Text>
              <Text style={s.heroBlue}>Dominá el mercado.</Text>
            </View>
            <Image source={{ uri: AJPA_LOGO_DATA_URI }} style={s.heroLogo} />
          </View>
          <View style={s.stats}>
            <Stat icon="◇" value={snapshot.clubs.length} label="Equipos" />
            <Stat icon="●" value={totalPlayers} label="Jugadores" />
            <Stat icon="⇄" value={market.length} label="Transferibles" />
            <Stat icon="○" value={free.length} label="Libres" />
          </View>
          <View style={s.marketState}>
            <View style={[s.dot, { backgroundColor: snapshot.status.market_open ? C.green : C.red }]} />
            <Text style={s.marketText}>Mercado {snapshot.status.market_open ? 'abierto' : 'cerrado'}</Text>
            <Text style={s.season}>{snapshot.status.season?.name ?? 'Temporada activa'}</Text>
          </View>
          {profile?.club ? (
            <Card style={s.operationalCard}>
              <Text style={s.eyebrow}>CUENTA VINCULADA</Text>
              <Text style={s.menuTitle}>{profile.club}</Text>
              <Text style={s.menuText}>{profile.roster_count} jugadores · {money(profile.balance)} disponibles</Text>
            </Card>
          ) : (
            <Card style={s.linkCard}>
              <Text style={s.eyebrow}>ACTIVAR OPERACIONES</Text>
              <Text style={s.menuTitle}>Vinculá tu Discord</Text>
              <Text style={s.menuText}>Para publicar, ofertar, aceptar, liberar o fichar desde la app.</Text>
              <View style={s.actions}><Button label="IR A PERFIL" onPress={() => setTab('perfil')} small /></View>
            </Card>
          )}
          <MenuCard eyebrow="MI CLUB" title="Mi Club" text="Plantel, presupuesto, publicar y liberar jugadores." icon="♢" onPress={() => setTab('equipos')} />
          <MenuCard eyebrow="MERCADO" title="Mercado de Pases" text="Ofertá, negociá y gestioná tus publicaciones." icon="⇄" onPress={() => setTab('mercado')} />
          <MenuCard eyebrow="JUGADORES LIBRES" title="Jugadores Libres" text="Fichá agentes libres directamente por $0." icon="♙" onPress={() => setTab('libres')} />
          <MenuCard eyebrow="OFERTAS" title="Mis negociaciones" text="Aceptá o rechazá las ofertas que recibís." icon="◎" onPress={() => setTab('perfil')} />
        </ScrollView>
      );
    }

    if (tab === 'equipos') {
      return (
        <ScrollView contentContainerStyle={s.content} refreshControl={refreshControl}>
          <View style={s.headerBox}>
            <Text style={s.eyebrow}>MI CLUB</Text>
            <Text style={s.screenTitle}>{profile?.club ? 'Gestión de plantel' : 'Planteles oficiales'}</Text>
            <Text style={s.muted}>{profile?.club ? 'Desde cada jugador podés publicar o liberar.' : 'Vinculá tu cuenta para operar tu club.'}</Text>
          </View>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={s.chips}>
            {snapshot.clubs.map((club) => (
              <Pressable key={club.name} style={[s.chip, selectedClub === club.name && s.chipActive]} onPress={() => setSelectedClub(club.name)}>
                <Text style={[s.chipText, selectedClub === club.name && s.chipTextActive]}>{club.name}</Text>
              </Pressable>
            ))}
          </ScrollView>
          {selected ? (
            <View style={s.clubSummary}>
              <View style={s.clubInitial}><Text style={s.clubInitialText}>{selected.name.slice(0, 2).toUpperCase()}</Text></View>
              <View style={s.flex}><Text style={s.name}>{selected.name}</Text><Text style={s.muted}>{selected.roster_count} jugadores</Text></View>
              <View style={{ alignItems: 'flex-end' }}><Text style={s.statLabel}>PRESUPUESTO</Text><Text style={s.money}>{money(selected.balance)}</Text></View>
            </View>
          ) : null}
          {rosterLoading ? <ActivityIndicator color={C.blue} style={{ marginVertical: 18 }} /> : null}
          {!rosterLoading && roster.length === 0 ? <Card><Text style={s.muted}>No hay jugadores para mostrar.</Text></Card> : null}
          {roster.map((player) => (
            <PlayerCard
              key={player.id ?? player.name}
              player={player}
              own={ownSelected && Boolean(profile)}
              onPublish={() => openPublish(player)}
              onRelease={() => {
                if (!player.id) return;
                const cost = player.market_value ? money(player.market_value * 0.2) : '20% del valor AJPA';
                Alert.alert(
                  'Liberar jugador',
                  `¿Liberar a ${player.name}? El costo es ${cost}. Pasará a Jugador Libre y aparecerá disponible por $0.`,
                  [
                    { text: 'Cancelar', style: 'cancel' },
                    { text: 'LIBERAR', style: 'destructive', onPress: () => mutate(() => releasePlayer(player.id!), `${player.name} fue liberado.`) },
                  ],
                );
              }}
            />
          ))}
        </ScrollView>
      );
    }

    if (tab === 'mercado') {
      return (
        <ScrollView contentContainerStyle={s.content} refreshControl={refreshControl}>
          <View style={s.headerBox}>
            <Text style={s.eyebrow}>TRANSFER MARKET</Text>
            <Text style={s.screenTitle}>Mercado de Pases</Text>
            <Text style={s.muted}>Publicaciones activas y negociación desde la app.</Text>
          </View>
          <View style={[s.banner, { borderColor: snapshot.status.market_open ? '#1c6a3a' : '#6b3038' }]}>
            <Text style={s.name}>{snapshot.status.market_open ? 'Mercado abierto' : 'Mercado cerrado'}</Text>
            <Text style={s.muted}>{profile ? 'Gestión habilitada · datos directos de AJPA.' : 'Consulta pública · vinculá Discord para operar.'}</Text>
          </View>
          {market.length === 0 ? <Card><Text style={s.muted}>No hay publicaciones activas.</Text></Card> : null}
          {market.map((item) => (
            <MarketCard
              key={item.publication_id}
              item={item}
              profile={profile}
              marketOpen={snapshot.status.market_open}
              onOffer={() => openOffer(item)}
              onWithdraw={() => Alert.alert('Retirar publicación', `¿Retirar a ${item.player} del mercado?`, [
                { text: 'Cancelar', style: 'cancel' },
                { text: 'RETIRAR', style: 'destructive', onPress: () => mutate(() => withdrawPublication(item.publication_id), 'Publicación retirada.') },
              ])}
              onSign={() => {}}
            />
          ))}
        </ScrollView>
      );
    }

    if (tab === 'libres') {
      return (
        <ScrollView contentContainerStyle={s.content} refreshControl={refreshControl}>
          <View style={s.headerBox}>
            <Text style={s.eyebrow}>JUGADORES LIBRES</Text>
            <Text style={s.screenTitle}>Agentes libres</Text>
            <Text style={s.muted}>Primer club en confirmar reserva al jugador para Staff/PES.</Text>
          </View>
          {free.length === 0 ? <Card><Text style={s.muted}>No hay agentes libres disponibles.</Text></Card> : null}
          {free.map((item) => (
            <MarketCard
              key={item.publication_id}
              item={item}
              profile={profile}
              marketOpen={snapshot.status.market_open}
              onOffer={() => {}}
              onWithdraw={() => {}}
              onSign={() => Alert.alert('Fichar agente libre', `¿Reservar a ${item.player} para ${profile?.club}? El fichaje cuesta $0.`, [
                { text: 'Cancelar', style: 'cancel' },
                { text: 'FICHAR $0', onPress: () => mutate(() => signFreeAgent(item.publication_id), `${item.player} quedó reservado para Staff/PES.`) },
              ])}
            />
          ))}
        </ScrollView>
      );
    }

    return (
      <ScrollView contentContainerStyle={s.content} refreshControl={refreshControl}>
        <View style={s.profileBox}>
          <Image source={{ uri: AJPA_LOGO_DATA_URI }} style={s.profileLogo} />
          <Text style={s.eyebrow}>AJPA TRANSFER MARKET</Text>
          <Text style={s.screenTitle}>Perfil</Text>
          <Text style={s.muted}>{profile ? 'Cuenta vinculada al sistema oficial.' : 'Vinculá Discord para habilitar operaciones.'}</Text>
        </View>
        {!profile ? (
          <Card>
            <Text style={s.name}>1. En Discord escribí /app_codigo</Text>
            <Text style={s.muted}>El bot te da un código privado de 8 caracteres que vence en 10 minutos.</Text>
            <Text style={s.name}>2. Pegalo acá</Text>
            <TextInput
              value={pairCode}
              onChangeText={(text) => setPairCode(text.toUpperCase())}
              autoCapitalize="characters"
              maxLength={8}
              placeholder="XXXXXXXX"
              placeholderTextColor="#596675"
              style={[s.input, s.codeInput]}
            />
            <Button label={busy ? 'VINCULANDO…' : 'VINCULAR DISCORD'} onPress={doPair} disabled={busy} />
          </Card>
        ) : (
          <>
            <Card>
              <Text style={s.eyebrow}>CLUB VINCULADO</Text>
              <Text style={s.screenTitleSmall}>{profile.club ?? 'Staff AJPA'}</Text>
              <View style={s.profileStats}>
                <View><Text style={s.statLabel}>PLANTEL</Text><Text style={s.name}>{profile.roster_count}</Text></View>
                <View><Text style={s.statLabel}>PRESUPUESTO</Text><Text style={s.name}>{money(profile.balance)}</Text></View>
                <View><Text style={s.statLabel}>ROL</Text><Text style={s.name}>{profile.is_staff ? 'Staff' : 'DT'}</Text></View>
              </View>
              <View style={s.actions}><Button label="CERRAR SESIÓN" onPress={logout} kind="ghost" small /></View>
            </Card>
            <View style={s.sectionHead}>
              <Text style={s.eyebrow}>OFERTAS RECIBIDAS</Text>
              <Text style={s.sectionCount}>{offers.incoming.length}</Text>
            </View>
            {offers.incoming.length === 0 ? <Card><Text style={s.muted}>No tenés ofertas recibidas.</Text></Card> : offers.incoming.map((offer) => (
              <OfferCard
                key={offer.id}
                offer={offer}
                onAccept={offer.status === 'PENDIENTE' ? () => mutate(() => acceptOffer(offer.id), `Oferta #${offer.id} aceptada. Quedó pendiente de Staff/PES.`) : undefined}
                onReject={offer.status === 'PENDIENTE' ? () => mutate(() => rejectOffer(offer.id), `Oferta #${offer.id} rechazada.`) : undefined}
              />
            ))}
            <View style={s.sectionHead}>
              <Text style={s.eyebrow}>OFERTAS ENVIADAS</Text>
              <Text style={s.sectionCount}>{offers.outgoing.length}</Text>
            </View>
            {offers.outgoing.length === 0 ? <Card><Text style={s.muted}>No enviaste ofertas todavía.</Text></Card> : offers.outgoing.map((offer) => <OfferCard key={offer.id} offer={offer} />)}
          </>
        )}
      </ScrollView>
    );
  })();

  const tabs: { id: Tab; label: string; icon: string }[] = [
    { id: 'inicio', label: 'Inicio', icon: '⌂' },
    { id: 'equipos', label: 'Mi Club', icon: '♢' },
    { id: 'mercado', label: 'Mercado', icon: '⇄' },
    { id: 'libres', label: 'Libres', icon: '♙' },
    { id: 'perfil', label: 'Perfil', icon: '◎' },
  ];

  return (
    <View style={s.root}>
      <Image source={{ uri: BG[tab] }} style={s.background} resizeMode="cover" blurRadius={6} />
      <View style={s.overlay} />
      <View style={s.topBar}>
        <View><Text style={s.topBrand}>AJPA</Text><Text style={s.topSub}>TRANSFER MARKET</Text></View>
        <View style={[s.readPill, profile && s.livePill]}><Text style={[s.readText, profile && s.liveText]}>{profile ? 'OPERATIVO' : 'VINCULAR'}</Text></View>
      </View>
      <View style={s.main}>{content}</View>
      {snapshot ? (
        <View style={s.bottomNav}>
          {tabs.map((item) => {
            const active = tab === item.id;
            const center = item.id === 'mercado';
            return (
              <Pressable key={item.id} onPress={() => setTab(item.id)} style={s.navItem}>
                <View style={[s.navIconWrap, active && s.navIconActive, center && s.marketButton, active && center && s.marketButtonActive]}>
                  <Text style={[s.navIcon, active && { color: C.blue }, center && { fontSize: 25 }]}>{item.icon}</Text>
                </View>
                <Text style={[s.navLabel, active && { color: C.blue }]}>{item.label}</Text>
              </Pressable>
            );
          })}
        </View>
      ) : null}

      <Modal visible={Boolean(action)} animationType="slide" transparent onRequestClose={() => setAction(null)}>
        <View style={s.modalShade}>
          <View style={s.modalCard}>
            <ScrollView contentContainerStyle={s.modalContent} keyboardShouldPersistTaps="handled">
              {action?.type === 'publish' ? (
                <>
                  <Text style={s.eyebrow}>PUBLICAR JUGADOR</Text>
                  <Text style={s.screenTitleSmall}>{action.player.name}</Text>
                  <Text style={s.muted}>OVR {action.player.ovr ?? '—'} · Valor AJPA {money(action.player.market_value)}</Text>
                  <Text style={s.formLabel}>TIPO DE OPERACIÓN</Text>
                  <View style={s.choiceRow}>
                    {['TRANSFERENCIA', 'PRÉSTAMO', 'INTERCAMBIO'].map((value) => (
                      <Pressable key={value} onPress={() => setPubType(value)} style={[s.choice, pubType === value && s.choiceActive]}>
                        <Text style={[s.choiceText, pubType === value && s.choiceTextActive]}>{value}</Text>
                      </Pressable>
                    ))}
                  </View>
                  <Text style={s.formLabel}>{pubType === 'PRÉSTAMO' ? 'CARGO DEL PRÉSTAMO' : 'PRECIO PEDIDO'}</Text>
                  <TextInput value={pubPrice} onChangeText={setPubPrice} keyboardType="numeric" placeholder="Ej: 2500000" placeholderTextColor="#596675" style={s.input} />
                  {pubType === 'PRÉSTAMO' ? (
                    <>
                      <Text style={s.formLabel}>TEMPORADAS</Text>
                      <TextInput value={loanSeasons} onChangeText={setLoanSeasons} keyboardType="numeric" style={s.input} />
                      <Pressable onPress={() => setPurchaseOption((v) => !v)} style={[s.toggle, purchaseOption && s.toggleActive]}>
                        <Text style={s.choiceText}>Opción de compra: {purchaseOption ? 'SÍ' : 'NO'}</Text>
                      </Pressable>
                      {purchaseOption ? <TextInput value={purchaseValue} onChangeText={setPurchaseValue} keyboardType="numeric" placeholder="Valor de compra" placeholderTextColor="#596675" style={s.input} /> : null}
                    </>
                  ) : null}
                  <Text style={s.formLabel}>OBSERVACIÓN</Text>
                  <TextInput value={pubDetail} onChangeText={setPubDetail} placeholder="Negociable, condiciones, etc." placeholderTextColor="#596675" style={[s.input, s.inputMulti]} multiline />
                  <Button label={busy ? 'PUBLICANDO…' : 'PUBLICAR'} onPress={submitPublication} disabled={busy} />
                  <Button label="CANCELAR" onPress={() => setAction(null)} kind="ghost" disabled={busy} />
                </>
              ) : action?.type === 'offer' ? (
                <>
                  <Text style={s.eyebrow}>HACER OFERTA</Text>
                  <Text style={s.screenTitleSmall}>{action.item.player}</Text>
                  <Text style={s.muted}>{action.item.club} · Mínimo AJPA {money(action.item.market_value)}</Text>
                  <Text style={s.formLabel}>DINERO OFRECIDO</Text>
                  <TextInput value={offerAmount} onChangeText={setOfferAmount} keyboardType="numeric" placeholder="Dejá vacío si ofrecés solo jugador" placeholderTextColor="#596675" style={s.input} />
                  <Text style={s.formLabel}>JUGADOR OFRECIDO (OPCIONAL)</Text>
                  <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={s.offerPlayers}>
                    <Pressable onPress={() => setOfferedPlayerId(null)} style={[s.playerChoice, offeredPlayerId === null && s.choiceActive]}>
                      <Text style={s.choiceText}>NINGUNO</Text>
                    </Pressable>
                    {ownRoster.filter((p) => p.id).map((player) => (
                      <Pressable key={player.id} onPress={() => setOfferedPlayerId(player.id!)} style={[s.playerChoice, offeredPlayerId === player.id && s.choiceActive]}>
                        <Text style={[s.choiceText, offeredPlayerId === player.id && s.choiceTextActive]}>{player.name}</Text>
                        <Text style={s.playerChoiceSub}>OVR {player.ovr ?? '—'} · {money(player.market_value)}</Text>
                      </Pressable>
                    ))}
                  </ScrollView>
                  <Text style={s.formLabel}>MENSAJE / CONDICIONES</Text>
                  <TextInput value={offerMessage} onChangeText={setOfferMessage} placeholder="Opcional" placeholderTextColor="#596675" style={[s.input, s.inputMulti]} multiline />
                  <Button label={busy ? 'ENVIANDO…' : 'ENVIAR OFERTA'} onPress={submitOffer} disabled={busy} />
                  <Button label="CANCELAR" onPress={() => setAction(null)} kind="ghost" disabled={busy} />
                </>
              ) : null}
            </ScrollView>
          </View>
        </View>
      </Modal>
    </View>
  );
}

const s = StyleSheet.create({
  root: { flex: 1, backgroundColor: C.dark },
  background: { ...StyleSheet.absoluteFillObject, width: '100%', height: '100%', opacity: 0.72 },
  overlay: { ...StyleSheet.absoluteFillObject, backgroundColor: 'rgba(2,6,10,0.43)' },
  topBar: { height: 58, paddingHorizontal: 18, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', borderBottomWidth: 1, borderBottomColor: '#172637', backgroundColor: 'rgba(2,7,12,0.95)' },
  topBrand: { color: C.white, fontSize: 22, fontWeight: '900', letterSpacing: 1.6, lineHeight: 24 },
  topSub: { color: C.blue, fontWeight: '900', fontSize: 9, letterSpacing: 2.1 },
  readPill: { borderRadius: 999, paddingHorizontal: 11, paddingVertical: 6, borderWidth: 1, borderColor: '#29425b', backgroundColor: '#0a1724' },
  readText: { color: C.blueSoft, fontWeight: '900', fontSize: 9, letterSpacing: 1.2 },
  livePill: { borderColor: '#23653c', backgroundColor: '#092017' },
  liveText: { color: C.green },
  main: { flex: 1 },
  content: { padding: 16, paddingBottom: 30, gap: 11 },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center', gap: 12 },
  loadingLogo: { width: 84, height: 84, borderRadius: 42 },
  card: { backgroundColor: C.panel, borderWidth: 1, borderColor: C.line, borderRadius: 18, padding: 14 },
  flex: { flex: 1 },
  row: { flexDirection: 'row', alignItems: 'center' },
  muted: { color: C.muted, fontSize: 12.5, lineHeight: 18, marginTop: 3 },
  name: { color: C.white, fontSize: 16, fontWeight: '800' },
  money: { color: C.white, fontSize: 14, fontWeight: '900', marginLeft: 8 },
  eyebrow: { color: C.blue, fontWeight: '900', fontSize: 10, letterSpacing: 1.7, marginBottom: 4 },
  operation: { color: C.blueSoft, fontWeight: '900', fontSize: 10, letterSpacing: 1.2, marginTop: 1 },
  detail: { color: '#c0cbd5', fontSize: 13, lineHeight: 18, marginTop: 5 },
  marketValue: { color: C.muted, fontSize: 11, marginTop: 7 },
  divider: { height: 1, backgroundColor: '#1a2a38', marginVertical: 11 },
  ovr: { width: 50, height: 50, borderRadius: 15, backgroundColor: '#0b2133', borderWidth: 1, borderColor: '#1f4261', alignItems: 'center', justifyContent: 'center' },
  ovrValue: { color: C.blueSoft, fontSize: 19, fontWeight: '900', lineHeight: 20 },
  ovrLabel: { color: '#5f87a8', fontSize: 8, fontWeight: '900' },
  actions: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginTop: 12 },
  button: { minHeight: 46, borderRadius: 14, paddingHorizontal: 16, alignItems: 'center', justifyContent: 'center', backgroundColor: C.blue },
  buttonSmall: { minHeight: 36, paddingHorizontal: 12, borderRadius: 11 },
  buttonDanger: { backgroundColor: '#a52d38' },
  buttonSuccess: { backgroundColor: '#176a3a' },
  buttonGhost: { backgroundColor: '#0a1723', borderWidth: 1, borderColor: '#2a4054' },
  buttonDisabled: { opacity: 0.42 },
  buttonText: { color: C.white, fontWeight: '900', fontSize: 11, letterSpacing: 0.6 },
  buttonGhostText: { color: '#c5d3df' },
  hero: { minHeight: 196, borderRadius: 24, overflow: 'hidden', borderWidth: 1, borderColor: '#1a2c3e', backgroundColor: 'rgba(4,11,17,0.92)', padding: 20, flexDirection: 'row', alignItems: 'center' },
  heroCopy: { flex: 1 },
  brand: { color: C.white, fontSize: 34, fontWeight: '900', letterSpacing: 1.5 },
  brandSub: { color: C.blue, fontSize: 11, fontWeight: '900', letterSpacing: 2.2, marginTop: -2, marginBottom: 18 },
  heroSmall: { color: C.blueSoft, fontSize: 10, fontWeight: '900', letterSpacing: 1.4, textTransform: 'uppercase', marginBottom: 5 },
  heroTitle: { color: C.white, fontSize: 23, fontWeight: '900', lineHeight: 26 },
  heroBlue: { color: C.blue, fontSize: 23, fontWeight: '900', lineHeight: 26 },
  heroLogo: { width: 108, height: 108, borderRadius: 54, borderWidth: 2, borderColor: C.blue, marginLeft: 7 },
  stats: { flexDirection: 'row', borderRadius: 20, borderWidth: 1, borderColor: '#1b2b3a', backgroundColor: 'rgba(7,16,24,0.90)', overflow: 'hidden' },
  stat: { flex: 1, alignItems: 'center', paddingVertical: 11, borderRightWidth: StyleSheet.hairlineWidth, borderRightColor: '#263747' },
  statIcon: { color: C.blue, fontSize: 17, fontWeight: '900' },
  statValue: { color: C.white, fontWeight: '900', fontSize: 16, marginTop: 3 },
  statLabel: { color: C.muted, fontWeight: '800', fontSize: 8, marginTop: 2 },
  marketState: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: 4 },
  dot: { width: 8, height: 8, borderRadius: 4, marginRight: 7 },
  marketText: { color: C.white, fontWeight: '800', fontSize: 12 },
  season: { color: C.muted, marginLeft: 'auto', fontSize: 11 },
  operationalCard: { borderColor: '#205f3a' },
  linkCard: { borderColor: '#234769' },
  menuCard: { minHeight: 110, borderRadius: 20, borderWidth: 1, borderColor: '#1c2b39', backgroundColor: 'rgba(7,16,25,0.90)', padding: 15, flexDirection: 'row', alignItems: 'center' },
  menuIcon: { width: 58, height: 58, borderRadius: 29, borderWidth: 1, borderColor: '#29425a', backgroundColor: '#091725', alignItems: 'center', justifyContent: 'center', marginRight: 14 },
  menuIconText: { color: C.blue, fontSize: 28, fontWeight: '900' },
  menuTitle: { color: C.white, fontWeight: '900', fontSize: 19, marginTop: 2 },
  menuText: { color: C.muted, fontSize: 12, lineHeight: 17, marginTop: 4 },
  chevron: { color: C.white, fontSize: 30, marginLeft: 10 },
  headerBox: { marginBottom: 6 },
  screenTitle: { color: C.white, fontSize: 27, fontWeight: '900' },
  screenTitleSmall: { color: C.white, fontSize: 22, fontWeight: '900' },
  chips: { gap: 8, paddingBottom: 5 },
  chip: { backgroundColor: 'rgba(7,16,25,0.90)', borderWidth: 1, borderColor: '#1d3142', borderRadius: 999, paddingHorizontal: 13, paddingVertical: 9 },
  chipActive: { backgroundColor: '#0c2b48', borderColor: C.blue },
  chipText: { color: C.muted, fontSize: 12, fontWeight: '700' },
  chipTextActive: { color: '#d5eaff' },
  clubSummary: { flexDirection: 'row', alignItems: 'center', backgroundColor: 'rgba(8,18,28,0.92)', borderRadius: 20, borderWidth: 1, borderColor: '#20384c', padding: 14 },
  clubInitial: { width: 54, height: 54, borderRadius: 18, backgroundColor: '#0b2133', alignItems: 'center', justifyContent: 'center', marginRight: 12 },
  clubInitialText: { color: C.blueSoft, fontWeight: '900', fontSize: 16 },
  banner: { borderRadius: 18, borderWidth: 1, padding: 14, backgroundColor: 'rgba(8,17,25,0.92)' },
  profileBox: { alignItems: 'center', paddingVertical: 17 },
  profileLogo: { width: 104, height: 104, borderRadius: 52, borderWidth: 2, borderColor: C.blue, marginBottom: 12 },
  profileStats: { flexDirection: 'row', justifyContent: 'space-between', marginTop: 16, gap: 16 },
  sectionHead: { flexDirection: 'row', alignItems: 'center', marginTop: 5 },
  sectionCount: { marginLeft: 'auto', color: C.white, fontWeight: '900', backgroundColor: '#0b2133', borderRadius: 999, paddingHorizontal: 9, paddingVertical: 3 },
  offerTop: { flexDirection: 'row', alignItems: 'center' },
  status: { fontSize: 9, fontWeight: '900', paddingHorizontal: 8, paddingVertical: 5, borderRadius: 999, overflow: 'hidden' },
  statusPending: { color: C.orange, backgroundColor: '#342913' },
  statusDone: { color: '#a9b8c6', backgroundColor: '#14202b' },
  input: { minHeight: 48, borderRadius: 13, borderWidth: 1, borderColor: '#284057', backgroundColor: '#07121c', color: C.white, paddingHorizontal: 13, fontSize: 14, marginBottom: 10 },
  inputMulti: { minHeight: 82, paddingTop: 12, textAlignVertical: 'top' },
  codeInput: { textAlign: 'center', letterSpacing: 5, fontSize: 20, fontWeight: '900', marginTop: 12 },
  formLabel: { color: C.blueSoft, fontWeight: '900', fontSize: 9, letterSpacing: 1.2, marginTop: 12, marginBottom: 6 },
  choiceRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 7 },
  choice: { borderRadius: 999, borderWidth: 1, borderColor: '#29425a', backgroundColor: '#0a1621', paddingHorizontal: 10, paddingVertical: 8 },
  choiceActive: { borderColor: C.blue, backgroundColor: '#0c2b48' },
  choiceText: { color: '#b4c1cd', fontWeight: '800', fontSize: 10 },
  choiceTextActive: { color: C.white },
  toggle: { borderRadius: 13, borderWidth: 1, borderColor: '#29425a', padding: 12, marginBottom: 10 },
  toggleActive: { borderColor: C.blue, backgroundColor: '#0c2b48' },
  offerPlayers: { gap: 8, paddingBottom: 5 },
  playerChoice: { minWidth: 110, maxWidth: 160, borderRadius: 13, borderWidth: 1, borderColor: '#29425a', backgroundColor: '#0a1621', padding: 10 },
  playerChoiceSub: { color: C.muted, fontSize: 9, marginTop: 3 },
  bottomNav: { height: 72, flexDirection: 'row', alignItems: 'center', borderTopWidth: 1, borderTopColor: '#172637', backgroundColor: 'rgba(2,7,12,0.98)', paddingHorizontal: 8 },
  navItem: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  navIconWrap: { width: 38, height: 34, borderRadius: 12, alignItems: 'center', justifyContent: 'center' },
  navIconActive: { backgroundColor: '#0b2237' },
  navIcon: { color: '#788998', fontSize: 20, fontWeight: '900' },
  navLabel: { color: '#788998', fontSize: 9, fontWeight: '800', marginTop: 2 },
  marketButton: { width: 58, height: 58, borderRadius: 29, marginTop: -22, backgroundColor: '#123f68', borderWidth: 2, borderColor: '#5ab0ff' },
  marketButtonActive: { backgroundColor: C.blue },
  modalShade: { flex: 1, backgroundColor: 'rgba(0,0,0,0.72)', justifyContent: 'flex-end' },
  modalCard: { maxHeight: '88%', borderTopLeftRadius: 26, borderTopRightRadius: 26, borderWidth: 1, borderColor: '#29425a', backgroundColor: '#050c13' },
  modalContent: { padding: 20, paddingBottom: 34 },
});
