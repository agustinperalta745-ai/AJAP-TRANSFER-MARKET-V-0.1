import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  ActivityIndicator,
  Image,
  Pressable,
  RefreshControl,
  ScrollView,
  StatusBar,
  StyleSheet,
  Text,
  View,
} from 'react-native';

import {
  API_CONFIGURED,
  ClubSummary,
  LeagueSnapshot,
  MarketItem,
  RosterPlayer,
  fetchRoster,
  fetchSnapshot,
} from './api';
import { AJPA_LOGO_DATA_URI } from './branding';

type Tab = 'inicio' | 'equipos' | 'mercado' | 'libres' | 'perfil';

const C = {
  bg: '#02060a',
  panel: '#071019',
  line: '#203142',
  blue: '#2d92ff',
  blueSoft: '#75b8ff',
  white: '#f7fbff',
  muted: '#8996a3',
  danger: '#ff8b92',
};

const money = (value: number | null | undefined) => {
  if (value === null || value === undefined) return '—';
  return `$${Math.round(value).toLocaleString('es-AR')}`;
};

function Card({ children }: { children: React.ReactNode }) {
  return <View style={styles.card}>{children}</View>;
}

function Empty({ children }: { children: React.ReactNode }) {
  return <Card><Text style={styles.muted}>{children}</Text></Card>;
}

function PlayerRow({ player }: { player: RosterPlayer }) {
  return (
    <View style={styles.playerRow}>
      <View style={styles.ovrBubble}>
        <Text style={styles.ovrValue}>{player.ovr ?? '—'}</Text>
        <Text style={styles.ovrLabel}>OVR</Text>
      </View>
      <View style={styles.playerMain}>
        <Text style={styles.playerName}>{player.name}</Text>
        <Text style={styles.muted}>{player.position || 'Sin posición'} · {player.code ?? 'SIN ID'}</Text>
      </View>
      <Text style={styles.valueText}>{money(player.market_value)}</Text>
    </View>
  );
}

function MarketRow({ item }: { item: MarketItem }) {
  return (
    <Card>
      <View style={styles.marketTop}>
        <View style={styles.ovrBubble}>
          <Text style={styles.ovrValue}>{item.ovr ?? '—'}</Text>
          <Text style={styles.ovrLabel}>OVR</Text>
        </View>
        <View style={styles.playerMain}>
          <Text style={styles.playerName}>{item.player}</Text>
          <Text style={styles.muted}>{item.position} · {item.club}</Text>
        </View>
        <Text style={item.is_free_agent ? styles.freePrice : styles.valueText}>{item.price}</Text>
      </View>
      <View style={styles.divider} />
      <Text style={styles.operation}>{item.operation_type}</Text>
      <Text style={styles.detail}>{item.detail || 'Sin observaciones'}</Text>
      {item.market_value !== null ? <Text style={styles.marketValue}>Valor AJPA: {money(item.market_value)}</Text> : null}
    </Card>
  );
}

function Stat({ icon, value, label }: { icon: string; value: string | number; label: string }) {
  return (
    <View style={styles.statBox}>
      <View style={styles.statIcon}><Text style={styles.statIconText}>{icon}</Text></View>
      <Text style={styles.statValue}>{value}</Text>
      <Text style={styles.statLabel}>{label}</Text>
    </View>
  );
}

function HomeMenuCard({ eyebrow, title, description, icon, onPress }: {
  eyebrow: string;
  title: string;
  description: string;
  icon: string;
  onPress: () => void;
}) {
  return (
    <Pressable onPress={onPress} style={({ pressed }) => [styles.menuCard, pressed && styles.pressed]}>
      <View style={styles.menuIconWrap}><Text style={styles.menuIcon}>{icon}</Text></View>
      <View style={styles.menuTextWrap}>
        <Text style={styles.menuEyebrow}>{eyebrow}</Text>
        <Text style={styles.menuTitle}>{title}</Text>
        <Text style={styles.menuDescription}>{description}</Text>
      </View>
      <View style={styles.chevron}><Text style={styles.chevronText}>›</Text></View>
    </Pressable>
  );
}

export default function LiveApp() {
  const [tab, setTab] = useState<Tab>('inicio');
  const [snapshot, setSnapshot] = useState<LeagueSnapshot | null>(null);
  const [selectedClub, setSelectedClub] = useState<string | null>(null);
  const [roster, setRoster] = useState<RosterPlayer[]>([]);
  const [loading, setLoading] = useState(true);
  const [rosterLoading, setRosterLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadSnapshot = useCallback(async (manual = false) => {
    if (!API_CONFIGURED) {
      setLoading(false);
      setError('La APK todavía no tiene una URL de API configurada.');
      return;
    }
    try {
      if (manual) setRefreshing(true);
      else setLoading(true);
      const data = await fetchSnapshot();
      setSnapshot(data);
      setError(null);
      setSelectedClub((current) => current ?? data.clubs[0]?.name ?? null);
    } catch (err) {
      const message = typeof err === 'object' && err && 'message' in err
        ? String((err as { message?: string }).message)
        : 'No se pudo conectar con AJPA.';
      setError(message);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => { loadSnapshot(); }, [loadSnapshot]);

  useEffect(() => {
    if (!selectedClub || !API_CONFIGURED) {
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
  }, [selectedClub]);

  const selected = useMemo<ClubSummary | null>(() => {
    return snapshot?.clubs.find((club) => club.name === selectedClub) ?? null;
  }, [snapshot, selectedClub]);

  const normalMarket = snapshot?.market.filter((item) => !item.is_free_agent) ?? [];
  const freeAgents = snapshot?.free_agents ?? [];
  const totalPlayers = snapshot?.clubs.reduce((sum, club) => sum + club.roster_count, 0) ?? 0;

  const body = (() => {
    if (loading) {
      return (
        <View style={styles.center}>
          <Image source={{ uri: AJPA_LOGO_DATA_URI }} style={styles.loadingLogo} />
          <ActivityIndicator size="large" color={C.blue} />
          <Text style={styles.muted}>Cargando AJPA…</Text>
        </View>
      );
    }

    if (!snapshot) {
      return (
        <ScrollView contentContainerStyle={styles.content}>
          <Text style={styles.screenTitle}>AJPA Mobile</Text>
          <Card>
            <Text style={styles.errorTitle}>Sin conexión</Text>
            <Text style={styles.detail}>{error ?? 'Todavía no hay conexión.'}</Text>
          </Card>
        </ScrollView>
      );
    }

    if (tab === 'inicio') {
      return (
        <ScrollView
          contentContainerStyle={styles.homeContent}
          refreshControl={<RefreshControl tintColor={C.blue} colors={[C.blue]} refreshing={refreshing} onRefresh={() => loadSnapshot(true)} />}
        >
          <View style={styles.hero}>
            <View style={styles.heroGlow} />
            <View style={styles.heroCopy}>
              <Text style={styles.brandWord}>AJPA</Text>
              <Text style={styles.brandSub}>TRANSFER MARKET</Text>
              <Text style={styles.heroSmall}>Temporada en vivo</Text>
              <Text style={styles.heroTitle}>Gestioná tu club.</Text>
              <Text style={styles.heroTitleBlue}>Dominá el mercado.</Text>
            </View>
            <Image source={{ uri: AJPA_LOGO_DATA_URI }} style={styles.heroLogo} resizeMode="cover" />
          </View>

          <View style={styles.statsStrip}>
            <Stat icon="◇" value={snapshot.clubs.length} label="Equipos" />
            <Stat icon="●" value={totalPlayers} label="Jugadores" />
            <Stat icon="⇄" value={normalMarket.length} label="Transferibles" />
            <Stat icon="○" value={freeAgents.length} label="Libres" />
          </View>

          <View style={styles.marketStateRow}>
            <View style={[styles.stateDot, snapshot.status.market_open ? styles.stateDotOpen : styles.stateDotClosed]} />
            <Text style={styles.marketStateText}>Mercado {snapshot.status.market_open ? 'abierto' : 'cerrado'}</Text>
            <Text style={styles.seasonText}>{snapshot.status.season?.name ?? 'Temporada activa'}</Text>
          </View>

          <HomeMenuCard eyebrow="MI CLUB" title="Mi Club" description="Plantel, presupuesto y datos oficiales." icon="♢" onPress={() => setTab('equipos')} />
          <HomeMenuCard eyebrow="MERCADO" title="Mercado de Pases" description="Explorá las publicaciones activas de los clubes." icon="⇄" onPress={() => setTab('mercado')} />
          <HomeMenuCard eyebrow="JUGADORES LIBRES" title="Jugadores Libres" description="Talento disponible sin club y por $0." icon="♙" onPress={() => setTab('libres')} />
          <HomeMenuCard eyebrow="PLANTEL" title="Plantel" description="Revisá jugadores, OVR y valor AJPA." icon="▦" onPress={() => setTab('equipos')} />
        </ScrollView>
      );
    }

    if (tab === 'equipos') {
      return (
        <ScrollView contentContainerStyle={styles.content}>
          <View style={styles.screenHeader}>
            <Text style={styles.screenEyebrow}>MI CLUB</Text>
            <Text style={styles.screenTitle}>Planteles oficiales</Text>
            <Text style={styles.muted}>Elegí un club para ver su información real.</Text>
          </View>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.clubChips}>
            {snapshot.clubs.map((club) => (
              <Pressable key={club.name} style={[styles.chip, selectedClub === club.name && styles.chipActive]} onPress={() => setSelectedClub(club.name)}>
                <Text style={[styles.chipText, selectedClub === club.name && styles.chipTextActive]}>{club.name}</Text>
              </Pressable>
            ))}
          </ScrollView>

          {selected ? (
            <View style={styles.clubSummary}>
              <View style={styles.clubSummaryIcon}><Text style={styles.clubSummaryInitial}>{selected.name.slice(0, 2).toUpperCase()}</Text></View>
              <View style={styles.clubSummaryMain}>
                <Text style={styles.summaryName}>{selected.name}</Text>
                <Text style={styles.muted}>{selected.roster_count} jugadores</Text>
              </View>
              <View style={styles.summaryRight}>
                <Text style={styles.statLabel}>PRESUPUESTO</Text>
                <Text style={styles.balance}>{money(selected.balance)}</Text>
              </View>
            </View>
          ) : null}

          {rosterLoading ? <ActivityIndicator color={C.blue} style={styles.loader} /> : null}
          {!rosterLoading && roster.length === 0 ? <Empty>No hay jugadores para mostrar.</Empty> : null}
          {roster.map((player) => <Card key={player.id ?? player.name}><PlayerRow player={player} /></Card>)}
        </ScrollView>
      );
    }

    if (tab === 'mercado') {
      return (
        <ScrollView contentContainerStyle={styles.content} refreshControl={<RefreshControl tintColor={C.blue} colors={[C.blue]} refreshing={refreshing} onRefresh={() => loadSnapshot(true)} />}>
          <View style={styles.screenHeader}>
            <Text style={styles.screenEyebrow}>TRANSFER MARKET</Text>
            <Text style={styles.screenTitle}>Mercado de Pases</Text>
            <Text style={styles.muted}>Publicaciones activas de clubes.</Text>
          </View>
          <View style={snapshot.status.market_open ? styles.marketOpenBanner : styles.marketClosedBanner}>
            <Text style={styles.bannerTitle}>{snapshot.status.market_open ? 'Mercado abierto' : 'Mercado cerrado'}</Text>
            <Text style={styles.bannerBody}>Modo lectura · datos directos de AJPA.</Text>
          </View>
          {normalMarket.length === 0 ? <Empty>No hay publicaciones activas.</Empty> : normalMarket.map((item) => <MarketRow key={item.publication_id} item={item} />)}
        </ScrollView>
      );
    }

    if (tab === 'libres') {
      return (
        <ScrollView contentContainerStyle={styles.content} refreshControl={<RefreshControl tintColor={C.blue} colors={[C.blue]} refreshing={refreshing} onRefresh={() => loadSnapshot(true)} />}>
          <View style={styles.screenHeader}>
            <Text style={styles.screenEyebrow}>JUGADORES LIBRES</Text>
            <Text style={styles.screenTitle}>Agentes libres</Text>
            <Text style={styles.muted}>Jugadores liberados disponibles por $0.</Text>
          </View>
          {freeAgents.length === 0 ? <Empty>No hay agentes libres disponibles.</Empty> : freeAgents.map((item) => <MarketRow key={item.publication_id} item={item} />)}
        </ScrollView>
      );
    }

    return (
      <ScrollView contentContainerStyle={styles.content}>
        <View style={styles.profileHero}>
          <Image source={{ uri: AJPA_LOGO_DATA_URI }} style={styles.profileLogo} />
          <Text style={styles.screenEyebrow}>AJPA TRANSFER MARKET</Text>
          <Text style={styles.screenTitle}>Perfil</Text>
          <Text style={styles.muted}>App conectada en modo lectura a los datos oficiales.</Text>
        </View>
        <Card>
          <Text style={styles.profileLabel}>ESTADO</Text>
          <Text style={styles.profileValue}>Conectado</Text>
          <View style={styles.divider} />
          <Text style={styles.profileLabel}>VERSIÓN</Text>
          <Text style={styles.profileValue}>v0.1</Text>
        </Card>
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
    <View style={styles.safe}>
      <StatusBar barStyle="light-content" backgroundColor={C.bg} />
      <View style={styles.topBar}>
        <View>
          <Text style={styles.topBrand}>AJPA</Text>
          <Text style={styles.topBrandSub}>TRANSFER MARKET</Text>
        </View>
        <View style={styles.readPill}><Text style={styles.readPillText}>LECTURA</Text></View>
      </View>
      <View style={styles.main}>{body}</View>
      {snapshot ? (
        <View style={styles.bottomNav}>
          {tabs.map((item) => {
            const active = tab === item.id;
            const market = item.id === 'mercado';
            return (
              <Pressable key={item.id} style={[styles.navItem, market && styles.navItemMarket]} onPress={() => setTab(item.id)}>
                <View style={[styles.navIconWrap, market && styles.marketButton, active && !market && styles.navIconActiveWrap, active && market && styles.marketButtonActive]}>
                  <Text style={[styles.navIcon, active && styles.navActive, market && styles.marketButtonIcon]}>{item.icon}</Text>
                </View>
                <Text style={[styles.navLabel, active && styles.navActive]}>{item.label}</Text>
                {active && !market ? <View style={styles.navUnderline} /> : null}
              </Pressable>
            );
          })}
        </View>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: C.bg },
  main: { flex: 1, backgroundColor: C.bg },
  topBar: { height: 58, paddingHorizontal: 18, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', borderBottomWidth: 1, borderBottomColor: '#13202c', backgroundColor: '#03080d' },
  topBrand: { color: C.white, fontWeight: '900', fontSize: 22, letterSpacing: 1.5, lineHeight: 24 },
  topBrandSub: { color: C.blue, fontWeight: '900', fontSize: 9, letterSpacing: 2.1 },
  readPill: { backgroundColor: '#0b1b2a', borderWidth: 1, borderColor: '#173553', borderRadius: 999, paddingHorizontal: 10, paddingVertical: 5 },
  readPillText: { color: C.blueSoft, fontWeight: '900', fontSize: 9, letterSpacing: 1.1 },
  content: { padding: 16, paddingBottom: 32, gap: 11 },
  homeContent: { padding: 16, paddingBottom: 32, gap: 12 },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center', gap: 12 },
  loadingLogo: { width: 78, height: 78, borderRadius: 39, marginBottom: 8 },
  hero: { minHeight: 196, borderRadius: 24, overflow: 'hidden', borderWidth: 1, borderColor: '#182b3c', backgroundColor: '#050b11', padding: 20, flexDirection: 'row', alignItems: 'center' },
  heroGlow: { position: 'absolute', right: -60, top: -80, width: 240, height: 240, borderRadius: 120, backgroundColor: '#082849', opacity: 0.72 },
  heroCopy: { flex: 1, zIndex: 2 },
  brandWord: { color: C.white, fontSize: 34, fontWeight: '900', letterSpacing: 1.5 },
  brandSub: { color: C.blue, fontSize: 11, fontWeight: '900', letterSpacing: 2.2, marginTop: -2, marginBottom: 18 },
  heroSmall: { color: C.blueSoft, fontSize: 10, fontWeight: '900', letterSpacing: 1.4, textTransform: 'uppercase', marginBottom: 5 },
  heroTitle: { color: C.white, fontSize: 24, fontWeight: '900', lineHeight: 27 },
  heroTitleBlue: { color: C.blue, fontSize: 24, fontWeight: '900', lineHeight: 27 },
  heroLogo: { width: 118, height: 118, borderRadius: 59, borderWidth: 2, borderColor: C.blue, marginLeft: 8, zIndex: 2 },
  statsStrip: { flexDirection: 'row', borderRadius: 20, borderWidth: 1, borderColor: '#1b2b3a', backgroundColor: '#071018', overflow: 'hidden' },
  statBox: { flex: 1, alignItems: 'center', paddingVertical: 12, paddingHorizontal: 3, borderRightWidth: StyleSheet.hairlineWidth, borderRightColor: '#263747' },
  statIcon: { width: 30, height: 30, borderRadius: 9, backgroundColor: '#0b1d2d', alignItems: 'center', justifyContent: 'center', marginBottom: 6 },
  statIconText: { color: C.blue, fontWeight: '900', fontSize: 17 },
  statValue: { color: C.white, fontWeight: '900', fontSize: 16 },
  statLabel: { color: C.muted, fontWeight: '800', fontSize: 8, marginTop: 2, textAlign: 'center' },
  marketStateRow: { flexDirection: 'row', alignItems: 'center', paddingHorizontal: 4 },
  stateDot: { width: 8, height: 8, borderRadius: 4, marginRight: 7 },
  stateDotOpen: { backgroundColor: '#47df78' },
  stateDotClosed: { backgroundColor: C.danger },
  marketStateText: { color: C.white, fontWeight: '800', fontSize: 12 },
  seasonText: { color: C.muted, marginLeft: 'auto', fontSize: 11 },
  menuCard: { minHeight: 112, borderRadius: 20, borderWidth: 1, borderColor: '#1c2b39', backgroundColor: '#071019', padding: 15, flexDirection: 'row', alignItems: 'center' },
  pressed: { opacity: 0.78, transform: [{ scale: 0.995 }] },
  menuIconWrap: { width: 58, height: 58, borderRadius: 29, borderWidth: 1, borderColor: '#29425a', backgroundColor: '#091725', alignItems: 'center', justifyContent: 'center' },
  menuIcon: { color: C.blue, fontSize: 28, fontWeight: '900' },
  menuTextWrap: { flex: 1, marginLeft: 14, paddingRight: 10 },
  menuEyebrow: { color: C.blue, fontWeight: '900', fontSize: 9, letterSpacing: 1.5 },
  menuTitle: { color: C.white, fontWeight: '900', fontSize: 20, marginTop: 3 },
  menuDescription: { color: C.muted, fontSize: 12, lineHeight: 17, marginTop: 4 },
  chevron: { width: 38, height: 38, borderRadius: 19, borderWidth: 1, borderColor: '#263a4c', alignItems: 'center', justifyContent: 'center' },
  chevronText: { color: C.white, fontSize: 28, marginTop: -3 },
  card: { backgroundColor: C.panel, borderWidth: 1, borderColor: C.line, borderRadius: 18, padding: 14 },
  muted: { color: C.muted, fontSize: 13, marginTop: 3 },
  screenHeader: { marginBottom: 8 },
  screenEyebrow: { color: C.blue, fontWeight: '900', fontSize: 10, letterSpacing: 1.8, marginBottom: 4 },
  screenTitle: { color: C.white, fontSize: 27, fontWeight: '900' },
  errorTitle: { color: '#ffc16f', fontWeight: '900', fontSize: 17 },
  playerRow: { flexDirection: 'row', alignItems: 'center' },
  ovrBubble: { width: 50, height: 50, borderRadius: 15, backgroundColor: '#0b2133', borderWidth: 1, borderColor: '#1f4261', alignItems: 'center', justifyContent: 'center' },
  ovrValue: { color: C.blueSoft, fontSize: 19, fontWeight: '900', lineHeight: 20 },
  ovrLabel: { color: '#5f87a8', fontSize: 8, fontWeight: '900' },
  playerMain: { flex: 1, marginLeft: 12 },
  playerName: { color: C.white, fontSize: 16, fontWeight: '800' },
  valueText: { color: C.white, fontSize: 14, fontWeight: '900', marginLeft: 8 },
  freePrice: { color: '#51dc79', fontSize: 16, fontWeight: '900', marginLeft: 8 },
  marketTop: { flexDirection: 'row', alignItems: 'center' },
  divider: { height: 1, backgroundColor: '#1a2a38', marginVertical: 12 },
  operation: { color: C.blueSoft, fontSize: 10, fontWeight: '900', letterSpacing: 1 },
  detail: { color: '#b7c2cc', fontSize: 13, marginTop: 5, lineHeight: 18 },
  marketValue: { color: C.muted, fontSize: 11, marginTop: 8 },
  clubChips: { gap: 8, paddingBottom: 5 },
  chip: { backgroundColor: '#071019', borderWidth: 1, borderColor: '#1d3142', borderRadius: 999, paddingHorizontal: 13, paddingVertical: 9 },
  chipActive: { backgroundColor: '#0c2b48', borderColor: C.blue },
  chipText: { color: C.muted, fontSize: 12, fontWeight: '700' },
  chipTextActive: { color: '#d5eaff' },
  clubSummary: { flexDirection: 'row', alignItems: 'center', backgroundColor: '#08121c', borderRadius: 20, borderWidth: 1, borderColor: '#20384c', padding: 14 },
  clubSummaryIcon: { width: 54, height: 54, borderRadius: 18, backgroundColor: '#0b2133', alignItems: 'center', justifyContent: 'center' },
  clubSummaryInitial: { color: C.blueSoft, fontWeight: '900', fontSize: 16 },
  clubSummaryMain: { flex: 1, marginLeft: 12 },
  summaryName: { color: C.white, fontSize: 20, fontWeight: '900' },
  summaryRight: { alignItems: 'flex-end' },
  balance: { color: C.white, fontWeight: '900', fontSize: 14, marginTop: 4 },
  loader: { marginVertical: 20 },
  marketOpenBanner: { backgroundColor: '#092417', borderWidth: 1, borderColor: '#1c6a3a', borderRadius: 18, padding: 14 },
  marketClosedBanner: { backgroundColor: '#251015', borderWidth: 1, borderColor: '#6b3038', borderRadius: 18, padding: 14 },
  bannerTitle: { color: C.white, fontSize: 16, fontWeight: '900' },
  bannerBody: { color: '#a7b5c0', fontSize: 12, marginTop: 5, lineHeight: 17 },
  profileHero: { alignItems: 'center', paddingVertical: 22 },
  profileLogo: { width: 112, height: 112, borderRadius: 56, borderWidth: 2, borderColor: C.blue, marginBottom: 14 },
  profileLabel: { color: C.muted, fontWeight: '900', fontSize: 10, letterSpacing: 1.4 },
  profileValue: { color: C.white, fontWeight: '900', fontSize: 17, marginTop: 4 },
  bottomNav: { height: 78, flexDirection: 'row', backgroundColor: '#03080d', borderTopWidth: 1, borderTopColor: '#172534', paddingHorizontal: 4 },
  navItem: { flex: 1, alignItems: 'center', justifyContent: 'center', position: 'relative' },
  navItemMarket: { marginTop: -15 },
  navIconWrap: { width: 36, height: 34, borderRadius: 12, alignItems: 'center', justifyContent: 'center' },
  navIconActiveWrap: { backgroundColor: '#0b2133' },
  navIcon: { color: '#71808d', fontSize: 20, fontWeight: '800', lineHeight: 23 },
  navLabel: { color: '#71808d', fontSize: 9, fontWeight: '800', marginTop: 2 },
  navActive: { color: C.blue },
  navUnderline: { position: 'absolute', bottom: 3, width: 24, height: 3, borderRadius: 2, backgroundColor: C.blue },
  marketButton: { width: 58, height: 58, borderRadius: 29, backgroundColor: '#0d4f91', borderWidth: 2, borderColor: '#2d92ff', shadowColor: '#2d92ff', shadowOpacity: 0.45, shadowRadius: 10, elevation: 8 },
  marketButtonActive: { backgroundColor: C.blue, borderColor: '#8cc7ff' },
  marketButtonIcon: { color: '#06111c', fontSize: 26, fontWeight: '900' },
});
