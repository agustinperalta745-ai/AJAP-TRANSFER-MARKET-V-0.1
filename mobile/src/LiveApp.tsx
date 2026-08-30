import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  ActivityIndicator,
  Pressable,
  RefreshControl,
  SafeAreaView,
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

type Tab = 'inicio' | 'equipos' | 'mercado' | 'libres';

const money = (value: number | null | undefined) => {
  if (value === null || value === undefined) return '—';
  return `$${Math.round(value).toLocaleString('es-AR')}`;
};

function Card({ children }: { children: React.ReactNode }) {
  return <View style={styles.card}>{children}</View>;
}

function Empty({ children }: { children: React.ReactNode }) {
  return (
    <Card>
      <Text style={styles.muted}>{children}</Text>
    </Card>
  );
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
        <Text style={styles.muted}>{player.position || 'Sin posición'}</Text>
        <Text style={styles.playerId}>{player.code ?? 'SIN ID'}</Text>
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
      {item.market_value !== null ? (
        <Text style={styles.marketValue}>Valor AJPA: {money(item.market_value)}</Text>
      ) : null}
    </Card>
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

  useEffect(() => {
    loadSnapshot();
  }, [loadSnapshot]);

  useEffect(() => {
    if (!selectedClub || !API_CONFIGURED) {
      setRoster([]);
      return;
    }
    let cancelled = false;
    setRosterLoading(true);
    fetchRoster(selectedClub)
      .then((players) => {
        if (!cancelled) setRoster(players);
      })
      .catch(() => {
        if (!cancelled) setRoster([]);
      })
      .finally(() => {
        if (!cancelled) setRosterLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [selectedClub]);

  const selected = useMemo<ClubSummary | null>(() => {
    return snapshot?.clubs.find((club) => club.name === selectedClub) ?? null;
  }, [snapshot, selectedClub]);

  const normalMarket = snapshot?.market.filter((item) => !item.is_free_agent) ?? [];
  const freeAgents = snapshot?.free_agents ?? [];

  const body = (() => {
    if (loading) {
      return (
        <View style={styles.center}>
          <ActivityIndicator size="large" />
          <Text style={styles.muted}>Cargando AJPA…</Text>
        </View>
      );
    }

    if (!snapshot) {
      return (
        <ScrollView contentContainerStyle={styles.content}>
          <View style={styles.screenHeader}>
            <Text style={styles.screenTitle}>AJPA Mobile</Text>
            <Text style={styles.muted}>Puente de datos reales preparado</Text>
          </View>
          <Card>
            <Text style={styles.errorTitle}>API pendiente de publicar</Text>
            <Text style={styles.detail}>{error ?? 'Todavía no hay conexión.'}</Text>
            <Text style={styles.helper}>
              Esta compilación no usa datos falsos. Cuando publiquemos la API de Railway, equipos, saldos y jugadores aparecerán acá automáticamente.
            </Text>
          </Card>
        </ScrollView>
      );
    }

    if (tab === 'inicio') {
      return (
        <ScrollView
          contentContainerStyle={styles.content}
          refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => loadSnapshot(true)} />}
        >
          <View style={styles.hero}>
            <View style={styles.logoBox}><Text style={styles.logoBoxText}>AJPA</Text></View>
            <View style={styles.heroText}>
              <Text style={styles.eyebrow}>LIGA EN VIVO</Text>
              <Text style={styles.clubName}>{snapshot.status.season?.name ?? 'Temporada activa'}</Text>
              <Text style={styles.muted}>Datos directos del Transfer Market</Text>
            </View>
          </View>

          <View style={styles.statsGrid}>
            <Card><Text style={styles.statLabel}>MERCADO</Text><Text style={snapshot.status.market_open ? styles.openText : styles.closedText}>{snapshot.status.market_open ? 'ABIERTO' : 'CERRADO'}</Text></Card>
            <Card><Text style={styles.statLabel}>EQUIPOS</Text><Text style={styles.statValue}>{snapshot.clubs.length}</Text></Card>
            <Card><Text style={styles.statLabel}>TRANSFERIBLES</Text><Text style={styles.statValue}>{normalMarket.length}</Text></Card>
            <Card><Text style={styles.statLabel}>AGENTES LIBRES</Text><Text style={styles.statValue}>{freeAgents.length}</Text></Card>
          </View>

          <Text style={styles.sectionTitle}>Clubes oficiales</Text>
          {snapshot.clubs.map((club) => (
            <Pressable key={club.name} onPress={() => { setSelectedClub(club.name); setTab('equipos'); }}>
              <Card>
                <View style={styles.clubRow}>
                  <View style={styles.clubInitial}><Text style={styles.clubInitialText}>{club.name.slice(0, 2).toUpperCase()}</Text></View>
                  <View style={styles.playerMain}>
                    <Text style={styles.playerName}>{club.name}</Text>
                    <Text style={styles.muted}>{club.roster_count} jugadores</Text>
                  </View>
                  <Text style={styles.balance}>{money(club.balance)}</Text>
                </View>
              </Card>
            </Pressable>
          ))}
        </ScrollView>
      );
    }

    if (tab === 'equipos') {
      return (
        <ScrollView contentContainerStyle={styles.content}>
          <View style={styles.screenHeader}>
            <Text style={styles.screenTitle}>Equipos</Text>
            <Text style={styles.muted}>Elegí un club para ver su plantel oficial</Text>
          </View>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.clubChips}>
            {snapshot.clubs.map((club) => (
              <Pressable
                key={club.name}
                style={[styles.chip, selectedClub === club.name && styles.chipActive]}
                onPress={() => setSelectedClub(club.name)}
              >
                <Text style={[styles.chipText, selectedClub === club.name && styles.chipTextActive]}>{club.name}</Text>
              </Pressable>
            ))}
          </ScrollView>

          {selected ? (
            <View style={styles.clubSummary}>
              <View><Text style={styles.eyebrow}>CLUB</Text><Text style={styles.summaryName}>{selected.name}</Text></View>
              <View style={styles.summaryRight}><Text style={styles.statLabel}>PRESUPUESTO</Text><Text style={styles.balance}>{money(selected.balance)}</Text></View>
            </View>
          ) : null}

          {rosterLoading ? <ActivityIndicator style={styles.loader} /> : null}
          {!rosterLoading && roster.length === 0 ? <Empty>No hay jugadores para mostrar.</Empty> : null}
          {roster.map((player) => <Card key={player.id ?? player.name}><PlayerRow player={player} /></Card>)}
        </ScrollView>
      );
    }

    if (tab === 'mercado') {
      return (
        <ScrollView contentContainerStyle={styles.content} refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => loadSnapshot(true)} />}>
          <View style={styles.screenHeader}>
            <Text style={styles.screenTitle}>Mercado</Text>
            <Text style={styles.muted}>Publicaciones activas de clubes</Text>
          </View>
          <View style={snapshot.status.market_open ? styles.marketOpenBanner : styles.marketClosedBanner}>
            <Text style={styles.bannerTitle}>{snapshot.status.market_open ? 'Mercado abierto' : 'Mercado cerrado'}</Text>
            <Text style={styles.bannerBody}>Modo lectura · las operaciones desde la app se habilitarán después del login.</Text>
          </View>
          {normalMarket.length === 0 ? <Empty>No hay publicaciones activas.</Empty> : normalMarket.map((item) => <MarketRow key={item.publication_id} item={item} />)}
        </ScrollView>
      );
    }

    return (
      <ScrollView contentContainerStyle={styles.content} refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => loadSnapshot(true)} />}>
        <View style={styles.screenHeader}>
          <Text style={styles.screenTitle}>Agentes libres</Text>
          <Text style={styles.muted}>Jugadores liberados disponibles por $0</Text>
        </View>
        {freeAgents.length === 0 ? <Empty>No hay agentes libres disponibles.</Empty> : freeAgents.map((item) => <MarketRow key={item.publication_id} item={item} />)}
      </ScrollView>
    );
  })();

  const tabs: { id: Tab; label: string; icon: string }[] = [
    { id: 'inicio', label: 'Inicio', icon: '⌂' },
    { id: 'equipos', label: 'Equipos', icon: '♟' },
    { id: 'mercado', label: 'Mercado', icon: '⇄' },
    { id: 'libres', label: 'Libres', icon: '☆' },
  ];

  return (
    <SafeAreaView style={styles.safe}>
      <StatusBar barStyle="light-content" backgroundColor="#08110d" />
      <View style={styles.appBar}>
        <Text style={styles.logo}>AJPA</Text>
        <Text style={styles.appBarTitle}>TRANSFER MARKET</Text>
        <View style={styles.readPill}><Text style={styles.readPillText}>LECTURA</Text></View>
      </View>
      <View style={styles.main}>{body}</View>
      {snapshot ? (
        <View style={styles.bottomNav}>
          {tabs.map((item) => {
            const active = tab === item.id;
            return (
              <Pressable key={item.id} style={styles.navItem} onPress={() => setTab(item.id)}>
                <Text style={[styles.navIcon, active && styles.navActive]}>{item.icon}</Text>
                <Text style={[styles.navLabel, active && styles.navActive]}>{item.label}</Text>
              </Pressable>
            );
          })}
        </View>
      ) : null}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: '#08110d' },
  main: { flex: 1, backgroundColor: '#0c1712' },
  appBar: { height: 58, paddingHorizontal: 18, flexDirection: 'row', alignItems: 'center', borderBottomWidth: 1, borderBottomColor: '#1d2d25' },
  logo: { color: '#f5fff8', fontWeight: '900', fontSize: 21, letterSpacing: 1 },
  appBarTitle: { color: '#59df88', fontSize: 11, fontWeight: '800', marginLeft: 8, letterSpacing: 1.5, flex: 1 },
  readPill: { backgroundColor: '#193326', borderRadius: 10, paddingHorizontal: 9, paddingVertical: 5 },
  readPillText: { color: '#8fe7ad', fontWeight: '900', fontSize: 9, letterSpacing: 1 },
  content: { padding: 16, paddingBottom: 28, gap: 10 },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center', gap: 12 },
  hero: { flexDirection: 'row', alignItems: 'center', paddingVertical: 12 },
  logoBox: { width: 66, height: 66, borderRadius: 18, backgroundColor: '#163b2a', borderWidth: 1, borderColor: '#2b6b48', alignItems: 'center', justifyContent: 'center' },
  logoBoxText: { color: '#8fe7ad', fontWeight: '900', fontSize: 18 },
  heroText: { marginLeft: 14, flex: 1 },
  eyebrow: { color: '#5edc89', fontWeight: '900', fontSize: 10, letterSpacing: 1.8 },
  clubName: { color: '#f6fff8', fontWeight: '900', fontSize: 24, marginTop: 2 },
  muted: { color: '#8da398', fontSize: 13, marginTop: 3 },
  statsGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: 10 },
  card: { backgroundColor: '#111f18', borderWidth: 1, borderColor: '#21372b', borderRadius: 16, padding: 14, flexGrow: 1 },
  statLabel: { color: '#82998d', fontSize: 10, fontWeight: '800', letterSpacing: 1 },
  statValue: { color: '#f6fff8', fontWeight: '900', fontSize: 20, marginTop: 6 },
  openText: { color: '#61e08b', fontSize: 16, fontWeight: '900', marginTop: 6 },
  closedText: { color: '#f19c9c', fontSize: 16, fontWeight: '900', marginTop: 6 },
  sectionTitle: { color: '#f6fff8', fontSize: 17, fontWeight: '900', marginTop: 12, marginBottom: 2 },
  screenHeader: { marginBottom: 8 },
  screenTitle: { color: '#f6fff8', fontSize: 26, fontWeight: '900' },
  playerRow: { flexDirection: 'row', alignItems: 'center' },
  ovrBubble: { width: 48, height: 48, borderRadius: 14, backgroundColor: '#193326', alignItems: 'center', justifyContent: 'center' },
  ovrValue: { color: '#8eeaab', fontSize: 18, fontWeight: '900', lineHeight: 20 },
  ovrLabel: { color: '#5f8f70', fontSize: 8, fontWeight: '900' },
  playerMain: { flex: 1, marginLeft: 12 },
  playerName: { color: '#f6fff8', fontSize: 16, fontWeight: '800' },
  playerId: { color: '#5f7569', fontSize: 10, marginTop: 4 },
  valueText: { color: '#f6fff8', fontSize: 14, fontWeight: '900', marginLeft: 8 },
  freePrice: { color: '#61e08b', fontSize: 16, fontWeight: '900', marginLeft: 8 },
  marketTop: { flexDirection: 'row', alignItems: 'center' },
  divider: { height: 1, backgroundColor: '#21372b', marginVertical: 12 },
  operation: { color: '#70dc94', fontSize: 10, fontWeight: '900', letterSpacing: 1 },
  detail: { color: '#b6c7be', fontSize: 13, marginTop: 5, lineHeight: 18 },
  marketValue: { color: '#82998d', fontSize: 11, marginTop: 8 },
  clubRow: { flexDirection: 'row', alignItems: 'center' },
  clubInitial: { width: 44, height: 44, borderRadius: 13, backgroundColor: '#193326', alignItems: 'center', justifyContent: 'center' },
  clubInitialText: { color: '#8eeaab', fontWeight: '900', fontSize: 13 },
  balance: { color: '#f6fff8', fontWeight: '900', fontSize: 15 },
  clubChips: { gap: 8, paddingBottom: 4 },
  chip: { backgroundColor: '#111f18', borderWidth: 1, borderColor: '#21372b', borderRadius: 999, paddingHorizontal: 13, paddingVertical: 9 },
  chipActive: { backgroundColor: '#1a4d30', borderColor: '#3aad68' },
  chipText: { color: '#8da398', fontSize: 12, fontWeight: '700' },
  chipTextActive: { color: '#bff5cf' },
  clubSummary: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingVertical: 12 },
  summaryName: { color: '#f6fff8', fontSize: 21, fontWeight: '900', marginTop: 3 },
  summaryRight: { alignItems: 'flex-end' },
  loader: { marginVertical: 20 },
  marketOpenBanner: { backgroundColor: '#12351f', borderWidth: 1, borderColor: '#226b3a', borderRadius: 16, padding: 14 },
  marketClosedBanner: { backgroundColor: '#321b1b', borderWidth: 1, borderColor: '#633333', borderRadius: 16, padding: 14 },
  bannerTitle: { color: '#f5fff8', fontSize: 16, fontWeight: '900' },
  bannerBody: { color: '#aed4ba', fontSize: 12, marginTop: 5, lineHeight: 17 },
  errorTitle: { color: '#f3c07c', fontWeight: '900', fontSize: 17 },
  helper: { color: '#82998d', fontSize: 12, lineHeight: 18, marginTop: 12 },
  bottomNav: { height: 68, flexDirection: 'row', backgroundColor: '#08110d', borderTopWidth: 1, borderTopColor: '#1d2d25' },
  navItem: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  navIcon: { color: '#71877b', fontSize: 20, fontWeight: '700', lineHeight: 23 },
  navLabel: { color: '#71877b', fontSize: 10, fontWeight: '800', marginTop: 2 },
  navActive: { color: '#59df88' },
});
