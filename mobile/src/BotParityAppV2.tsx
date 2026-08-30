import React, { ReactNode, useCallback, useEffect, useMemo, useState } from 'react';
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
import { clearStoredSession, loadStoredSession, saveStoredSession } from './session';

type Screen =
  | 'home'
  | 'club'
  | 'roster'
  | 'economy'
  | 'clubValue'
  | 'clubInfo'
  | 'market'
  | 'publish'
  | 'transferibles'
  | 'clausulazo'
  | 'offers'
  | 'search'
  | 'history'
  | 'league'
  | 'admin'
  | 'adminTools'
  | 'assignments'
  | 'resign'
  | 'profile';

type PublicationType = 'TRANSFERENCIA' | 'PRÉSTAMO' | 'INTERCAMBIO';

type OffersState = { incoming: OfferItem[]; outgoing: OfferItem[] };

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
  value === null || value === undefined ? '—' : `$${Math.round(value).toLocaleString('es-AR')}`;

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
        disabled && s.disabled,
        pressed && !disabled && { opacity: 0.72 },
      ]}
    >
      <Text style={s.buttonText}>{label}</Text>
    </Pressable>
  );
}

function MenuTile({
  emoji,
  title,
  subtitle,
  onPress,
  danger = false,
}: {
  emoji: string;
  title: string;
  subtitle?: string;
  onPress: () => void;
  danger?: boolean;
}) {
  return (
    <Pressable
      onPress={onPress}
      style={({ pressed }) => [s.menuTile, danger && s.menuDanger, pressed && { opacity: 0.72 }]}
    >
      <Text style={s.menuEmoji}>{emoji}</Text>
      <View style={s.flex}>
        <Text style={[s.menuTitle, danger && { color: C.red }]}>{title}</Text>
        {subtitle ? <Text style={s.menuSubtitle}>{subtitle}</Text> : null}
      </View>
      <Text style={s.chevron}>›</Text>
    </Pressable>
  );
}

function Title({ eyebrow, title, subtitle }: { eyebrow: string; title: string; subtitle?: string }) {
  return (
    <View style={{ marginBottom: 6 }}>
      <Text style={s.eyebrow}>{eyebrow}</Text>
      <Text style={s.screenTitle}>{title}</Text>
      {subtitle ? <Text style={s.muted}>{subtitle}</Text> : null}
    </View>
  );
}

function PlayerCard({ player, actions }: { player: RosterPlayer; actions?: ReactNode }) {
  return (
    <View style={s.card}>
      <View style={s.playerRow}>
        <View style={s.ovrBox}>
          <Text style={s.ovrValue}>{player.ovr ?? '—'}</Text>
          <Text style={s.ovrLabel}>OVR</Text>
        </View>
        <View style={s.flex}>
          <Text style={s.playerName}>{player.name}</Text>
          <Text style={s.muted}>{player.position || 'Sin posición'} · {player.club}</Text>
          <Text style={s.playerValue}>Valor AJPA {money(player.market_value)}</Text>
        </View>
      </View>
      {actions ? <View style={s.actionRow}>{actions}</View> : null}
    </View>
  );
}

function MarketCard({ item, actions }: { item: MarketItem; actions?: ReactNode }) {
  return (
    <View style={s.card}>
      <View style={s.playerRow}>
        <View style={s.ovrBox}>
          <Text style={s.ovrValue}>{item.ovr ?? '—'}</Text>
          <Text style={s.ovrLabel}>OVR</Text>
        </View>
        <View style={s.flex}>
          <Text style={s.playerName}>{item.player}</Text>
          <Text style={s.muted}>{item.position || '—'} · {item.club}</Text>
          <Text style={s.playerValue}>{item.operation_type}</Text>
        </View>
        <Text style={[s.price, item.is_free_agent && { color: C.green }]}>{item.price}</Text>
      </View>
      {item.detail ? <Text style={s.detail}>{item.detail}</Text> : null}
      {actions ? <View style={s.actionRow}>{actions}</View> : null}
    </View>
  );
}

function OfferCard({
  offer,
  onAccept,
  onCounter,
  onReject,
}: {
  offer: OfferItem;
  onAccept?: () => void;
  onCounter?: () => void;
  onReject?: () => void;
}) {
  const pending = offer.status.toUpperCase() === 'PENDIENTE';
  return (
    <View style={s.card}>
      <Text style={s.playerName}>{offer.player}</Text>
      <Text style={s.muted}>{offer.from_club} → {offer.to_club}</Text>
      <Text style={s.playerValue}>Propuesta: {offer.amount || '$0'} · {offer.operation_type}</Text>
      {offer.offered_player ? <Text style={s.detail}>Jugador ofrecido: {offer.offered_player}</Text> : null}
      {offer.message ? <Text style={s.detail}>{offer.message}</Text> : null}
      <Text style={[s.statusTag, pending ? { color: C.orange } : { color: C.blueSoft }]}>{offer.status}</Text>
      {offer.incoming && pending && onAccept && onCounter && onReject ? (
        <View style={s.actionRow}>
          <Button label="ACEPTAR" kind="green" onPress={onAccept} />
          <Button label="CONTRAOFERTAR" onPress={onCounter} />
          <Button label="RECHAZAR" kind="red" onPress={onReject} />
        </View>
      ) : null}
    </View>
  );
}

export default function BotParityAppV2() {
  const [screen, setScreen] = useState<Screen>('home');
  const [snapshot, setSnapshot] = useState<LeagueSnapshot | null>(null);
  const [profile, setProfile] = useState<MobileProfile | null>(null);
  const [roster, setRoster] = useState<RosterPlayer[]>([]);
  const [offers, setOffers] = useState<OffersState>({ incoming: [], outgoing: [] });
  const [allPlayers, setAllPlayers] = useState<RosterPlayer[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [busy, setBusy] = useState(false);

  const [pairCode, setPairCode] = useState('');
  const [searchText, setSearchText] = useState('');
  const [publishTarget, setPublishTarget] = useState<RosterPlayer | null>(null);
  const [publishType, setPublishType] = useState<PublicationType>('TRANSFERENCIA');
  const [publishPrice, setPublishPrice] = useState('');
  const [publishDetail, setPublishDetail] = useState('');
  const [loanSeasons, setLoanSeasons] = useState('1');
  const [purchaseOption, setPurchaseOption] = useState(false);
  const [purchaseValue, setPurchaseValue] = useState('');
  const [offerTarget, setOfferTarget] = useState<MarketItem | null>(null);
  const [offerAmount, setOfferAmount] = useState('');
  const [offerMessage, setOfferMessage] = useState('');
  const [offeredPlayerId, setOfferedPlayerId] = useState<number | null>(null);

  const loadAll = useCallback(async (manual = false) => {
    try {
      manual ? setRefreshing(true) : setLoading(true);
      const snap = await fetchSnapshot();
      setSnapshot(snap);
      try {
        const me = await fetchMe();
        setProfile(me);
        setRoster(me.club ? await fetchRoster(me.club) : []);
      } catch {
        setProfile(null);
        setRoster([]);
      }
    } catch (error) {
      Alert.alert('AJPA Mobile', apiError(error));
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

  const refreshControl = (
    <RefreshControl refreshing={refreshing} onRefresh={() => loadAll(true)} tintColor={C.blue} colors={[C.blue]} />
  );

  const myClubData = useMemo(
    () => snapshot?.clubs.find((club) => profile?.club && club.name.toLowerCase() === profile.club.toLowerCase()) ?? null,
    [snapshot, profile?.club],
  );

  const squadValue = useMemo(
    () => roster.reduce((sum, player) => sum + Number(player.market_value || 0), 0),
    [roster],
  );

  const normalMarket = snapshot?.market.filter((item) => !item.is_free_agent) ?? [];
  const freeAgents = snapshot?.free_agents ?? [];
  const myPublications = normalMarket.filter((item) => profile?.club && item.club.toLowerCase() === profile.club.toLowerCase());
  const otherPublications = normalMarket.filter((item) => !profile?.club || item.club.toLowerCase() !== profile.club.toLowerCase());

  const mutate = async (work: () => Promise<unknown>, success: string) => {
    if (busy) return;
    setBusy(true);
    try {
      await work();
      setOfferTarget(null);
      setPublishTarget(null);
      Alert.alert('AJPA Transfer Market', success);
      await loadAll(true);
      if (screen === 'offers') setOffers(await fetchMyOffers());
    } catch (error) {
      Alert.alert('No se pudo completar', apiError(error));
    } finally {
      setBusy(false);
    }
  };

  const openScreen = async (next: Screen) => {
    setScreen(next);
    if (next === 'offers') {
      try { setOffers(await fetchMyOffers()); } catch (error) { Alert.alert('Ofertas', apiError(error)); }
    }
    if (next === 'search' && allPlayers.length === 0 && snapshot) {
      try {
        setBusy(true);
        const chunks = await Promise.all(snapshot.clubs.map((club) => fetchRoster(club.name)));
        setAllPlayers(chunks.flat());
      } catch (error) {
        Alert.alert('Buscar', apiError(error));
      } finally {
        setBusy(false);
      }
    }
  };

  const requireClub = (next: Screen) => {
    if (!profile?.club) {
      Alert.alert('Sin club', 'Esta opción necesita un club asignado en Discord.');
      return;
    }
    void openScreen(next);
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
      setProfile(result.profile);
      setRoster(result.profile.club ? await fetchRoster(result.profile.club) : []);
      setPairCode('');
      setScreen('home');
      Alert.alert('Cuenta vinculada', 'La app quedó vinculada con tu cuenta de Discord.');
    } catch (error) {
      Alert.alert('No se pudo vincular', apiError(error));
    } finally {
      setBusy(false);
    }
  };

  const logout = async () => {
    setSessionToken('');
    await clearStoredSession();
    setProfile(null);
    setRoster([]);
    setOffers({ incoming: [], outgoing: [] });
    setScreen('profile');
  };

  const startPublish = (player: RosterPlayer) => {
    setPublishTarget(player);
    setPublishType('TRANSFERENCIA');
    setPublishPrice(player.market_value ? String(player.market_value) : '');
    setPublishDetail('');
    setLoanSeasons('1');
    setPurchaseOption(false);
    setPurchaseValue('');
    setScreen('publish');
  };

  const submitPublication = () => {
    if (!publishTarget?.id) return;
    if (!publishPrice.trim()) {
      Alert.alert('Precio requerido', 'Indicá el precio o cargo de la operación.');
      return;
    }
    if (publishType === 'PRÉSTAMO' && Number(loanSeasons) <= 0) {
      Alert.alert('Duración requerida', 'La duración debe ser mayor a 0 temporadas.');
      return;
    }
    if (publishType === 'PRÉSTAMO' && purchaseOption && !purchaseValue.trim()) {
      Alert.alert('Opción de compra', 'Indicá el valor de la opción de compra.');
      return;
    }
    mutate(
      () => publishPlayer({
        player_id: publishTarget.id!,
        operation_type: publishType,
        price: publishPrice,
        detail: publishDetail,
        loan_seasons: publishType === 'PRÉSTAMO' ? loanSeasons : undefined,
        purchase_option_enabled: publishType === 'PRÉSTAMO' ? purchaseOption : undefined,
        purchase_option_value: publishType === 'PRÉSTAMO' && purchaseOption ? purchaseValue : undefined,
      }),
      `${publishTarget.name} fue publicado.`,
    );
  };

  const submitOffer = () => {
    if (!offerTarget) return;
    if (!offerAmount.trim() && !offeredPlayerId) {
      Alert.alert('Oferta vacía', 'Ofrecé dinero, un jugador o ambas cosas.');
      return;
    }
    mutate(
      () => sendOffer(offerTarget.publication_id, {
        amount: offerAmount,
        offered_player_id: offeredPlayerId,
        message: offerMessage,
      }),
      `Oferta enviada por ${offerTarget.player}.`,
    );
  };

  if (loading) {
    return (
      <View style={[s.root, s.center]}>
        <ActivityIndicator color={C.blue} size="large" />
        <Text style={s.muted}>Cargando AJPA Mobile…</Text>
      </View>
    );
  }

  if (!snapshot) {
    return (
      <View style={[s.root, s.center]}>
        <Text style={s.screenTitle}>Sin conexión</Text>
        <Button label="REINTENTAR" onPress={() => loadAll()} />
      </View>
    );
  }

  const placeholder = (title: string, text: string) => (
    <ScrollView contentContainerStyle={s.content} refreshControl={refreshControl}>
      <Title eyebrow="AJPA MOBILE" title={title} subtitle={text} />
      <View style={s.card}>
        <Text style={s.playerName}>Opción reflejada desde Discord</Text>
        <Text style={s.detail}>Esta sección mantiene el mismo lugar y permisos del bot. Las operaciones móviles se habilitan únicamente cuando existe su endpoint seguro en el backend.</Text>
      </View>
    </ScrollView>
  );

  const home = (
    <ScrollView contentContainerStyle={s.content} refreshControl={refreshControl}>
      <Title
        eyebrow="AJPA TRANSFER MARKET"
        title={profile?.club ? profile.club.toUpperCase() : profile?.is_staff ? 'PANEL STAFF' : 'MENÚ PRINCIPAL'}
        subtitle="La misma jerarquía que el panel /mercado de Discord."
      />
      <View style={s.summaryRow}>
        <View style={s.summaryCard}><Text style={s.summaryValue}>{money(profile?.balance)}</Text><Text style={s.summaryLabel}>PRESUPUESTO</Text></View>
        <View style={s.summaryCard}><Text style={s.summaryValue}>{profile?.roster_count ?? 0}</Text><Text style={s.summaryLabel}>JUGADORES</Text></View>
      </View>
      <View style={[s.marketState, snapshot.status.market_open ? s.marketOpen : s.marketClosed]}>
        <Text style={s.marketStateText}>{snapshot.status.market_open ? '🟢 MERCADO ABIERTO' : '🔒 MERCADO CERRADO'}</Text>
      </View>

      {profile?.club ? <MenuTile emoji="🏟️" title="MI CLUB" subtitle="Plantilla, economía, valor e información" onPress={() => requireClub('club')} /> : null}
      <MenuTile emoji="🔁" title="MERCADO" subtitle="Publicar, transferibles y clausulazo" onPress={() => openScreen('market')} />
      <MenuTile emoji="📩" title="OFERTAS" subtitle="Recibidas, enviadas y decisiones" onPress={() => openScreen('offers')} />
      <MenuTile emoji="🔎" title="BUSCAR" subtitle="Buscar jugadores" onPress={() => openScreen('search')} />
      <MenuTile emoji="📜" title="HISTORIAL" subtitle="Movimientos del mercado" onPress={() => openScreen('history')} />
      <MenuTile emoji="🏆" title="LIGA" subtitle="Tabla y goleadores" onPress={() => openScreen('league')} />
      {profile?.is_staff ? <MenuTile emoji="⚙️" title="ADMINISTRACIÓN" subtitle="Administración y asignaciones" onPress={() => openScreen('admin')} /> : null}
      {profile?.club ? <MenuTile emoji="🚪" title="RENUNCIAR AL CLUB" subtitle="Salida del club" onPress={() => openScreen('resign')} danger /> : null}
    </ScrollView>
  );

  const clubMenu = (
    <ScrollView contentContainerStyle={s.content} refreshControl={refreshControl}>
      <Title eyebrow="MI CLUB" title={profile?.club ?? 'Mi Club'} subtitle="Mismas opciones que el submenú del bot." />
      <MenuTile emoji="👥" title="PLANTILLA" onPress={() => openScreen('roster')} />
      <MenuTile emoji="💰" title="ECONOMÍA" onPress={() => openScreen('economy')} />
      <MenuTile emoji="📊" title="VALOR DEL CLUB" onPress={() => openScreen('clubValue')} />
      <MenuTile emoji="ℹ️" title="INFORMACIÓN" onPress={() => openScreen('clubInfo')} />
    </ScrollView>
  );

  const rosterScreen = (
    <ScrollView contentContainerStyle={s.content} refreshControl={refreshControl}>
      <Title eyebrow="MI CLUB · PLANTILLA" title="Plantilla" subtitle={`${roster.length} jugadores`} />
      {roster.map((player) => (
        <PlayerCard
          key={player.id ?? player.name}
          player={player}
          actions={
            <>
              <Button label="PUBLICAR" onPress={() => startPublish(player)} />
              <Button
                label="LIBERAR"
                kind="ghost"
                onPress={() => {
                  if (!player.id) return;
                  Alert.alert('Liberar jugador', `¿Confirmás liberar a ${player.name}?`, [
                    { text: 'Cancelar', style: 'cancel' },
                    { text: 'LIBERAR', style: 'destructive', onPress: () => mutate(() => releasePlayer(player.id!), `${player.name} fue liberado.`) },
                  ]);
                }}
              />
            </>
          }
        />
      ))}
    </ScrollView>
  );

  const economy = (
    <ScrollView contentContainerStyle={s.content} refreshControl={refreshControl}>
      <Title eyebrow="MI CLUB · ECONOMÍA" title="Economía" />
      <View style={s.statCard}><Text style={s.statLabel}>PRESUPUESTO DISPONIBLE</Text><Text style={s.statValue}>{money(myClubData?.balance ?? profile?.balance)}</Text></View>
      <View style={s.statCard}><Text style={s.statLabel}>VALOR DE LA PLANTILLA</Text><Text style={s.statValue}>{money(squadValue)}</Text></View>
      <View style={s.statCard}><Text style={s.statLabel}>JUGADORES</Text><Text style={s.statValue}>{roster.length}</Text></View>
    </ScrollView>
  );

  const clubValue = (
    <ScrollView contentContainerStyle={s.content} refreshControl={refreshControl}>
      <Title eyebrow="MI CLUB · VALOR DEL CLUB" title="Valor del Club" />
      <View style={s.statCard}><Text style={s.statLabel}>VALOR TOTAL</Text><Text style={s.statValue}>{money(squadValue)}</Text></View>
      <View style={s.statCard}><Text style={s.statLabel}>PROMEDIO POR JUGADOR</Text><Text style={s.statValue}>{money(roster.length ? squadValue / roster.length : 0)}</Text></View>
      <View style={s.statCard}><Text style={s.statLabel}>CANTIDAD DE JUGADORES</Text><Text style={s.statValue}>{roster.length}</Text></View>
    </ScrollView>
  );

  const clubInfo = (
    <ScrollView contentContainerStyle={s.content} refreshControl={refreshControl}>
      <Title eyebrow="MI CLUB · INFORMACIÓN" title={profile?.club ?? 'Club'} />
      <View style={s.card}>
        <Text style={s.infoLabel}>CLUB</Text><Text style={s.infoValue}>{profile?.club ?? '—'}</Text>
        <View style={s.separator} />
        <Text style={s.infoLabel}>JUGADORES</Text><Text style={s.infoValue}>{roster.length}</Text>
        <View style={s.separator} />
        <Text style={s.infoLabel}>MERCADO</Text><Text style={s.infoValue}>{snapshot.status.market_open ? '🟢 ABIERTO' : '🔒 CERRADO'}</Text>
        <View style={s.separator} />
        <Text style={s.infoLabel}>PRESUPUESTO</Text><Text style={s.infoValue}>{money(myClubData?.balance ?? profile?.balance)}</Text>
        <View style={s.separator} />
        <Text style={s.infoLabel}>VALOR PLANTILLA</Text><Text style={s.infoValue}>{money(squadValue)}</Text>
      </View>
    </ScrollView>
  );

  const marketMenu = (
    <ScrollView contentContainerStyle={s.content} refreshControl={refreshControl}>
      <Title eyebrow="MERCADO" title="Mercado de Pases" subtitle="Mismas tres opciones del bot." />
      <MenuTile emoji="📤" title="PUBLICAR" subtitle="Transferencia, préstamo o intercambio" onPress={() => requireClub('publish')} />
      <MenuTile emoji="📋" title="TRANSFERIBLES" subtitle="Otros equipos, mis publicaciones y libres" onPress={() => openScreen('transferibles')} />
      <MenuTile emoji="💥" title="CLAUSULAZO" subtitle="Ejecutar cláusula de rescisión" onPress={() => openScreen('clausulazo')} danger />
    </ScrollView>
  );

  const publishScreen = (
    <ScrollView contentContainerStyle={s.content} refreshControl={refreshControl} keyboardShouldPersistTaps="handled">
      <Title eyebrow="MERCADO · PUBLICAR" title="Publicar jugador" subtitle="Transferencia, préstamo o intercambio." />
      {!publishTarget ? (
        roster.map((player) => (
          <Pressable key={player.id ?? player.name} onPress={() => startPublish(player)}>
            <PlayerCard player={player} />
          </Pressable>
        ))
      ) : (
        <View style={s.editorCard}>
          <Text style={s.eyebrow}>JUGADOR</Text>
          <Text style={s.editorTitle}>{publishTarget.name}</Text>
          <Text style={s.muted}>Valor AJPA {money(publishTarget.market_value)}</Text>

          <Text style={s.inputLabel}>TIPO DE OPERACIÓN</Text>
          <View style={s.actionRow}>
            {(['TRANSFERENCIA', 'PRÉSTAMO', 'INTERCAMBIO'] as PublicationType[]).map((type) => (
              <Button key={type} label={type} kind={publishType === type ? 'blue' : 'ghost'} onPress={() => setPublishType(type)} />
            ))}
          </View>

          <Text style={s.inputLabel}>{publishType === 'PRÉSTAMO' ? 'CARGO / PRECIO' : 'PRECIO PEDIDO'}</Text>
          <TextInput style={s.input} keyboardType="numeric" value={publishPrice} onChangeText={setPublishPrice} placeholder="Ej: 5000000" placeholderTextColor="#657382" />

          {publishType === 'PRÉSTAMO' ? (
            <>
              <Text style={s.inputLabel}>DURACIÓN (TEMPORADAS)</Text>
              <TextInput style={s.input} keyboardType="numeric" value={loanSeasons} onChangeText={setLoanSeasons} placeholder="1" placeholderTextColor="#657382" />
              <Text style={s.inputLabel}>OPCIÓN DE COMPRA</Text>
              <View style={s.actionRow}>
                <Button label="SÍ" kind={purchaseOption ? 'blue' : 'ghost'} onPress={() => setPurchaseOption(true)} />
                <Button label="NO" kind={!purchaseOption ? 'blue' : 'ghost'} onPress={() => { setPurchaseOption(false); setPurchaseValue(''); }} />
              </View>
              {purchaseOption ? (
                <>
                  <Text style={s.inputLabel}>VALOR OPCIÓN DE COMPRA</Text>
                  <TextInput style={s.input} keyboardType="numeric" value={purchaseValue} onChangeText={setPurchaseValue} placeholder="Ej: 30000000" placeholderTextColor="#657382" />
                </>
              ) : null}
            </>
          ) : null}

          <Text style={s.inputLabel}>OBSERVACIÓN</Text>
          <TextInput style={[s.input, s.textarea]} value={publishDetail} onChangeText={setPublishDetail} multiline placeholder="Opcional" placeholderTextColor="#657382" />
          <View style={s.actionRow}>
            <Button label={busy ? 'PUBLICANDO…' : 'CONFIRMAR PUBLICACIÓN'} disabled={busy} onPress={submitPublication} />
            <Button label="CAMBIAR JUGADOR" kind="ghost" onPress={() => setPublishTarget(null)} disabled={busy} />
          </View>
        </View>
      )}
    </ScrollView>
  );

  const transferibles = (
    <ScrollView contentContainerStyle={s.content} refreshControl={refreshControl} keyboardShouldPersistTaps="handled">
      <Title eyebrow="MERCADO · TRANSFERIBLES" title="Jugadores transferibles" subtitle="Separados igual que en Discord." />

      {offerTarget ? (
        <View style={s.editorCard}>
          <Text style={s.eyebrow}>HACER OFERTA</Text>
          <Text style={s.editorTitle}>{offerTarget.player}</Text>
          <Text style={s.muted}>{offerTarget.club} · {offerTarget.price}</Text>
          <Text style={s.inputLabel}>DINERO OFRECIDO</Text>
          <TextInput style={s.input} keyboardType="numeric" value={offerAmount} onChangeText={setOfferAmount} placeholder="Puede ser 0 si ofrecés jugador" placeholderTextColor="#657382" />
          <Text style={s.inputLabel}>JUGADOR OFRECIDO (OPCIONAL)</Text>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={s.horizontalChoices}>
            <Button label={offeredPlayerId ? 'SIN JUGADOR' : 'NINGUNO'} kind="ghost" onPress={() => setOfferedPlayerId(null)} />
            {roster.filter((player) => player.id).map((player) => (
              <Button key={player.id!} label={player.name} kind={offeredPlayerId === player.id ? 'blue' : 'ghost'} onPress={() => setOfferedPlayerId(player.id)} />
            ))}
          </ScrollView>
          <Text style={s.inputLabel}>MENSAJE / CONDICIONES</Text>
          <TextInput style={[s.input, s.textarea]} value={offerMessage} onChangeText={setOfferMessage} multiline placeholder="Opcional" placeholderTextColor="#657382" />
          <View style={s.actionRow}>
            <Button label={busy ? 'ENVIANDO…' : 'ENVIAR OFERTA'} disabled={busy} onPress={submitOffer} />
            <Button label="CANCELAR" kind="ghost" onPress={() => setOfferTarget(null)} />
          </View>
        </View>
      ) : null}

      <Text style={s.listHeading}>🌍 TRANSFERIBLES DE OTROS EQUIPOS · {otherPublications.length}</Text>
      {otherPublications.length === 0 ? <View style={s.card}><Text style={s.muted}>No hay publicaciones de otros equipos.</Text></View> : null}
      {otherPublications.map((item) => (
        <MarketCard
          key={item.publication_id}
          item={item}
          actions={<Button label="HACER OFERTA" disabled={!snapshot.status.market_open || !profile?.club} onPress={() => {
            setOfferTarget(item);
            setOfferAmount('');
            setOfferMessage('');
            setOfferedPlayerId(null);
          }} />}
        />
      ))}

      <Text style={s.listHeading}>📤 MIS TRANSFERIBLES · {myPublications.length}</Text>
      {myPublications.length === 0 ? <View style={s.card}><Text style={s.muted}>No tenés publicaciones activas.</Text></View> : null}
      {myPublications.map((item) => (
        <MarketCard
          key={item.publication_id}
          item={item}
          actions={<Button label="RETIRAR PUBLICACIÓN" kind="red" onPress={() => Alert.alert('Retirar publicación', `¿Retirar a ${item.player}?`, [
            { text: 'Cancelar', style: 'cancel' },
            { text: 'RETIRAR', style: 'destructive', onPress: () => mutate(() => withdrawPublication(item.publication_id), `${item.player} fue retirado del mercado.`) },
          ])} />}
        />
      ))}

      <Text style={s.listHeading}>🆓 AGENTES LIBRES · {freeAgents.length}</Text>
      {freeAgents.length === 0 ? <View style={s.card}><Text style={s.muted}>No hay agentes libres.</Text></View> : null}
      {freeAgents.map((item) => (
        <MarketCard
          key={item.publication_id}
          item={item}
          actions={<Button label="FICHAR $0" kind="green" disabled={!snapshot.status.market_open || !profile?.club} onPress={() => Alert.alert('Fichar agente libre', `¿Fichar a ${item.player} por $0?`, [
            { text: 'Cancelar', style: 'cancel' },
            { text: 'FICHAR $0', onPress: () => mutate(() => signFreeAgent(item.publication_id), `${item.player} fue reservado y enviado a Staff/PES.`) },
          ])} />}
        />
      ))}
    </ScrollView>
  );

  const offersScreen = (
    <ScrollView contentContainerStyle={s.content} refreshControl={refreshControl}>
      <Title eyebrow="OFERTAS" title="Mis ofertas" subtitle="Aceptar, contraofertar o rechazar como en Discord." />
      <Text style={s.listHeading}>📥 RECIBIDAS · {offers.incoming.length}</Text>
      {offers.incoming.length === 0 ? <View style={s.card}><Text style={s.muted}>No tenés ofertas recibidas.</Text></View> : null}
      {offers.incoming.map((offer) => (
        <OfferCard
          key={offer.id}
          offer={offer}
          onAccept={() => mutate(() => acceptOffer(offer.id), `Oferta #${offer.id} aceptada.`)}
          onCounter={() => Alert.alert('Contraofertar', 'La opción ya está ubicada igual que en Discord. Falta exponer el endpoint móvil de contraoferta para ejecutarla con seguridad desde la app.')}
          onReject={() => mutate(() => rejectOffer(offer.id), `Oferta #${offer.id} rechazada.`)}
        />
      ))}
      <Text style={s.listHeading}>📤 ENVIADAS · {offers.outgoing.length}</Text>
      {offers.outgoing.length === 0 ? <View style={s.card}><Text style={s.muted}>No tenés ofertas enviadas.</Text></View> : null}
      {offers.outgoing.map((offer) => <OfferCard key={offer.id} offer={offer} />)}
    </ScrollView>
  );

  const filteredPlayers = searchText.trim()
    ? allPlayers.filter((player) => `${player.name} ${player.club} ${player.position}`.toLowerCase().includes(searchText.trim().toLowerCase()))
    : [];

  const search = (
    <ScrollView contentContainerStyle={s.content} refreshControl={refreshControl} keyboardShouldPersistTaps="handled">
      <Title eyebrow="BUSCAR" title="Buscar jugador" subtitle="Busca en los planteles actuales." />
      <TextInput style={s.input} value={searchText} onChangeText={setSearchText} placeholder="Nombre, club o posición" placeholderTextColor="#657382" />
      {busy && allPlayers.length === 0 ? <ActivityIndicator color={C.blue} /> : null}
      {filteredPlayers.slice(0, 60).map((player) => <PlayerCard key={`${player.club}-${player.id ?? player.name}`} player={player} />)}
      {searchText.trim() && filteredPlayers.length === 0 && !busy ? <View style={s.card}><Text style={s.muted}>No encontré jugadores.</Text></View> : null}
    </ScrollView>
  );

  const adminMenu = (
    <ScrollView contentContainerStyle={s.content} refreshControl={refreshControl}>
      <Title eyebrow="STAFF" title="Administración" subtitle="Mismo submenú administrativo del bot." />
      <MenuTile emoji="⚙️" title="ADMINISTRACIÓN" subtitle="Herramientas de gestión" onPress={() => openScreen('adminTools')} />
      <MenuTile emoji="👥" title="ASIGNACIONES" subtitle="Gestión de clubes y usuarios" onPress={() => openScreen('assignments')} />
    </ScrollView>
  );

  const profileScreen = (
    <ScrollView contentContainerStyle={s.content} refreshControl={refreshControl} keyboardShouldPersistTaps="handled">
      <Title eyebrow="CUENTA" title="Perfil" subtitle="Discord define club y permisos." />
      {profile ? (
        <View style={s.card}>
          <Text style={s.infoLabel}>DISCORD</Text><Text style={s.infoValue}>{profile.user.global_name || profile.user.username || profile.user.id}</Text>
          <View style={s.separator} />
          <Text style={s.infoLabel}>CLUB</Text><Text style={s.infoValue}>{profile.club ?? 'Staff / sin club'}</Text>
          <View style={s.separator} />
          <Text style={s.infoLabel}>PERMISOS</Text><Text style={s.infoValue}>{profile.is_staff ? 'STAFF / ADMIN' : 'DT / USUARIO'}</Text>
          <View style={{ marginTop: 16 }}><Button label="CERRAR SESIÓN" kind="ghost" onPress={logout} /></View>
        </View>
      ) : (
        <View style={s.editorCard}>
          <Text style={s.playerName}>Vincular Discord</Text>
          <Text style={s.muted}>Ejecutá /app_codigo en Discord y escribí el código privado de 8 caracteres.</Text>
          <TextInput style={[s.input, s.codeInput]} value={pairCode} onChangeText={(value) => setPairCode(value.toUpperCase().replace(/[^A-Z0-9]/g, '').slice(0, 8))} maxLength={8} autoCapitalize="characters" placeholder="XXXXXXXX" placeholderTextColor="#657382" />
          <Button label={busy ? 'VINCULANDO…' : 'VINCULAR DISCORD'} onPress={pair} disabled={busy} />
        </View>
      )}
    </ScrollView>
  );

  let body: ReactNode = home;
  if (screen === 'club') body = clubMenu;
  else if (screen === 'roster') body = rosterScreen;
  else if (screen === 'economy') body = economy;
  else if (screen === 'clubValue') body = clubValue;
  else if (screen === 'clubInfo') body = clubInfo;
  else if (screen === 'market') body = marketMenu;
  else if (screen === 'publish') body = publishScreen;
  else if (screen === 'transferibles') body = transferibles;
  else if (screen === 'clausulazo') body = placeholder('Clausulazo', 'Ejecución de cláusula de rescisión con las reglas del bot.');
  else if (screen === 'offers') body = offersScreen;
  else if (screen === 'search') body = search;
  else if (screen === 'history') body = placeholder('Historial', 'Movimientos y operaciones cerradas del mercado.');
  else if (screen === 'league') body = placeholder('Liga', 'Tabla, goleadores y estado de la competencia.');
  else if (screen === 'admin') body = adminMenu;
  else if (screen === 'adminTools') body = placeholder('Administración', 'Herramientas de gestión exclusivas para Staff.');
  else if (screen === 'assignments') body = placeholder('Asignaciones', 'Gestión de asignaciones de usuarios y clubes.');
  else if (screen === 'resign') body = placeholder('Renunciar al Club', 'Renuncia con la misma validación administrativa del bot.');
  else if (screen === 'profile') body = profileScreen;

  return (
    <View style={s.root}>
      <View style={s.topBar}>
        {screen !== 'home' ? (
          <Pressable onPress={() => setScreen('home')} style={s.topAction}><Text style={s.topActionText}>‹ MENÚ</Text></Pressable>
        ) : (
          <View><Text style={s.brand}>AJPA</Text><Text style={s.brandSub}>TRANSFER MARKET · MOBILE</Text></View>
        )}
        <Pressable onPress={() => setScreen('profile')} style={s.profileButton}><Text style={s.profileButtonText}>◎</Text></Pressable>
      </View>
      <View style={s.main}>{body}</View>
    </View>
  );
}

const s = StyleSheet.create({
  root: { flex: 1, backgroundColor: C.bg },
  main: { flex: 1 },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center', padding: 24, gap: 14 },
  content: { padding: 16, paddingBottom: 34, gap: 11 },
  flex: { flex: 1, minWidth: 0 },
  topBar: { height: 60, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: 16, borderBottomWidth: 1, borderBottomColor: '#142230', backgroundColor: '#03080d' },
  brand: { color: C.white, fontSize: 23, fontWeight: '900', letterSpacing: 1.8, lineHeight: 25 },
  brandSub: { color: C.blue, fontSize: 8, fontWeight: '900', letterSpacing: 1.8 },
  topAction: { paddingVertical: 10, paddingRight: 14 },
  topActionText: { color: C.blueSoft, fontSize: 11, fontWeight: '900', letterSpacing: 1 },
  profileButton: { width: 38, height: 38, borderRadius: 19, borderWidth: 1, borderColor: '#29435a', alignItems: 'center', justifyContent: 'center', backgroundColor: '#07111a' },
  profileButtonText: { color: C.blueSoft, fontSize: 20, fontWeight: '900' },
  eyebrow: { color: C.blue, fontSize: 10, fontWeight: '900', letterSpacing: 1.6, marginBottom: 4 },
  screenTitle: { color: C.white, fontSize: 28, fontWeight: '900' },
  muted: { color: C.muted, fontSize: 12.5, lineHeight: 18, marginTop: 3 },
  menuTile: { minHeight: 76, flexDirection: 'row', alignItems: 'center', backgroundColor: C.panel, borderWidth: 1, borderColor: C.border, borderRadius: 18, padding: 14 },
  menuDanger: { borderColor: '#5b2a32', backgroundColor: '#170b0e' },
  menuEmoji: { fontSize: 25, width: 42 },
  menuTitle: { color: C.white, fontSize: 15, fontWeight: '900' },
  menuSubtitle: { color: C.muted, fontSize: 11, lineHeight: 15, marginTop: 3 },
  chevron: { color: C.blueSoft, fontSize: 28, marginLeft: 8 },
  summaryRow: { flexDirection: 'row', gap: 10 },
  summaryCard: { flex: 1, backgroundColor: C.panel2, borderWidth: 1, borderColor: C.border, borderRadius: 16, padding: 13 },
  summaryValue: { color: C.white, fontSize: 16, fontWeight: '900' },
  summaryLabel: { color: C.muted, fontSize: 8, fontWeight: '900', letterSpacing: 1, marginTop: 4 },
  marketState: { borderWidth: 1, borderRadius: 14, padding: 12 },
  marketOpen: { backgroundColor: '#071b12', borderColor: '#245a3b' },
  marketClosed: { backgroundColor: '#1b0b0d', borderColor: '#613037' },
  marketStateText: { color: C.white, fontSize: 10, fontWeight: '900' },
  card: { backgroundColor: C.panel, borderWidth: 1, borderColor: C.border, borderRadius: 18, padding: 14 },
  statCard: { backgroundColor: C.panel, borderWidth: 1, borderColor: C.border, borderRadius: 18, padding: 16 },
  statLabel: { color: C.blueSoft, fontSize: 9, fontWeight: '900', letterSpacing: 1.2 },
  statValue: { color: C.white, fontSize: 26, fontWeight: '900', marginTop: 5 },
  playerRow: { flexDirection: 'row', alignItems: 'center' },
  ovrBox: { width: 52, height: 52, borderRadius: 14, backgroundColor: '#0d2233', borderWidth: 1, borderColor: '#2a4d68', alignItems: 'center', justifyContent: 'center', marginRight: 12 },
  ovrValue: { color: C.blueSoft, fontSize: 19, fontWeight: '900', lineHeight: 20 },
  ovrLabel: { color: '#6b90ab', fontSize: 8, fontWeight: '900' },
  playerName: { color: C.white, fontSize: 16, fontWeight: '900' },
  playerValue: { color: C.blueSoft, fontSize: 10, fontWeight: '800', marginTop: 4 },
  price: { color: C.white, fontWeight: '900', fontSize: 14, marginLeft: 8 },
  detail: { color: '#b7c2cc', fontSize: 12, lineHeight: 17, marginTop: 10 },
  statusTag: { fontSize: 9, fontWeight: '900', letterSpacing: 1, marginTop: 10 },
  actionRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginTop: 12 },
  horizontalChoices: { gap: 8, paddingVertical: 4 },
  button: { minHeight: 42, borderRadius: 12, paddingHorizontal: 14, alignItems: 'center', justifyContent: 'center', backgroundColor: C.blue },
  buttonGreen: { backgroundColor: '#176a3a' },
  buttonRed: { backgroundColor: '#a93840' },
  buttonGhost: { backgroundColor: '#0a1620', borderWidth: 1, borderColor: '#30475b' },
  disabled: { opacity: 0.4 },
  buttonText: { color: C.white, fontSize: 10, fontWeight: '900', letterSpacing: 0.5 },
  editorCard: { backgroundColor: '#091928', borderWidth: 1, borderColor: C.blue, borderRadius: 19, padding: 15 },
  editorTitle: { color: C.white, fontSize: 21, fontWeight: '900' },
  inputLabel: { color: C.blueSoft, fontWeight: '900', fontSize: 9, letterSpacing: 1.2, marginTop: 13, marginBottom: 6 },
  input: { minHeight: 48, backgroundColor: '#05101a', borderWidth: 1, borderColor: '#29435a', borderRadius: 12, paddingHorizontal: 13, color: C.white, fontSize: 16 },
  textarea: { minHeight: 78, paddingTop: 12, textAlignVertical: 'top' },
  codeInput: { textAlign: 'center', letterSpacing: 5, fontWeight: '900', fontSize: 21, marginVertical: 12 },
  listHeading: { color: C.blueSoft, fontWeight: '900', fontSize: 10, letterSpacing: 1.4, marginTop: 8 },
  infoLabel: { color: C.blueSoft, fontSize: 9, fontWeight: '900', letterSpacing: 1.2 },
  infoValue: { color: C.white, fontSize: 16, fontWeight: '800', marginTop: 5 },
  separator: { height: 1, backgroundColor: '#1b2e3d', marginVertical: 13 },
});
