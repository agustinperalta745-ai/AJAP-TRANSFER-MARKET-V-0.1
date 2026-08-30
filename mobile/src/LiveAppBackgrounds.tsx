import React, { useCallback, useEffect, useMemo, useState } from 'react';
import {
  ActivityIndicator,
  Image,
  Pressable,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';

import {
  API_CONFIGURED,
  LeagueSnapshot,
  MarketItem,
  RosterPlayer,
  fetchRoster,
  fetchSnapshot,
} from './api';
import { AJPA_LOGO_DATA_URI } from './branding';
import { BG_INICIO } from './bg_inicio';
import { BG_EQUIPOS } from './bg_equipos';
import { BG_MERCADO } from './bg_mercado';
import { BG_LIBRES } from './bg_libres';
import { BG_PERFIL } from './bg_perfil';

type Tab = 'inicio' | 'equipos' | 'mercado' | 'libres' | 'perfil';

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
  muted: '#9aa7b4',
  line: '#203142',
  panel: 'rgba(7,16,25,0.90)',
  dark: '#02060a',
};

const money = (value: number | null | undefined) =>
  value === null || value === undefined ? '—' : `$${Math.round(value).toLocaleString('es-AR')}`;

function GlassCard({ children }: { children: React.ReactNode }) {
  return <View style={s.card}>{children}</View>;
}

function Empty({ text }: { text: string }) {
  return <GlassCard><Text style={s.muted}>{text}</Text></GlassCard>;
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

function Player({ player }: { player: RosterPlayer }) {
  return (
    <GlassCard>
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
    </GlassCard>
  );
}

function Market({ item }: { item: MarketItem }) {
  return (
    <GlassCard>
      <View style={s.row}>
        <View style={s.ovr}>
          <Text style={s.ovrValue}>{item.ovr ?? '—'}</Text>
          <Text style={s.ovrLabel}>OVR</Text>
        </View>
        <View style={s.flex}>
          <Text style={s.name}>{item.player}</Text>
          <Text style={s.muted}>{item.position} · {item.club}</Text>
        </View>
        <Text style={[s.money, item.is_free_agent && s.free]}>{item.price}</Text>
      </View>
      <View style={s.divider} />
      <Text style={s.operation}>{item.operation_type}</Text>
      <Text style={s.detail}>{item.detail || 'Sin observaciones'}</Text>
      {item.market_value !== null ? <Text style={s.marketValue}>Valor AJPA: {money(item.market_value)}</Text> : null}
    </GlassCard>
  );
}

function MenuCard({ eyebrow, title, text, icon, onPress }: {
  eyebrow: string;
  title: string;
  text: string;
  icon: string;
  onPress: () => void;
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

export default function LiveAppBackgrounds() {
  const [tab, setTab] = useState<Tab>('inicio');
  const [snapshot, setSnapshot] = useState<LeagueSnapshot | null>(null);
  const [selectedClub, setSelectedClub] = useState<string | null>(null);
  const [roster, setRoster] = useState<RosterPlayer[]>([]);
  const [loading, setLoading] = useState(true);
  const [rosterLoading, setRosterLoading] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (manual = false) => {
    if (!API_CONFIGURED) {
      setLoading(false);
      setError('La APK todavía no tiene una URL de API configurada.');
      return;
    }
    try {
      if (manual) setRefreshing(true); else setLoading(true);
      const data = await fetchSnapshot();
      setSnapshot(data);
      setSelectedClub((current) => current ?? data.clubs[0]?.name ?? null);
      setError(null);
    } catch (err) {
      setError(typeof err === 'object' && err && 'message' in err ? String((err as { message?: string }).message) : 'No se pudo conectar con AJPA.');
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

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

  const selected = useMemo(() => snapshot?.clubs.find((club) => club.name === selectedClub) ?? null, [snapshot, selectedClub]);
  const market = snapshot?.market.filter((item) => !item.is_free_agent) ?? [];
  const free = snapshot?.free_agents ?? [];
  const totalPlayers = snapshot?.clubs.reduce((sum, club) => sum + club.roster_count, 0) ?? 0;

  const refresh = (
    <RefreshControl
      refreshing={refreshing}
      onRefresh={() => load(true)}
      tintColor={C.blue}
      colors={[C.blue]}
    />
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
          <View style={s.headerBox}>
            <Text style={s.screenTitle}>AJPA Mobile</Text>
            <Text style={s.muted}>{error ?? 'Sin conexión.'}</Text>
          </View>
        </ScrollView>
      );
    }

    if (tab === 'inicio') {
      return (
        <ScrollView contentContainerStyle={s.content} refreshControl={refresh}>
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
            <View style={[s.dot, { backgroundColor: snapshot.status.market_open ? '#47df78' : '#ff8b92' }]} />
            <Text style={s.marketText}>Mercado {snapshot.status.market_open ? 'abierto' : 'cerrado'}</Text>
            <Text style={s.season}>{snapshot.status.season?.name ?? 'Temporada activa'}</Text>
          </View>

          <MenuCard eyebrow="MI CLUB" title="Mi Club" text="Plantel, presupuesto y datos oficiales." icon="♢" onPress={() => setTab('equipos')} />
          <MenuCard eyebrow="MERCADO" title="Mercado de Pases" text="Explorá las publicaciones activas de los clubes." icon="⇄" onPress={() => setTab('mercado')} />
          <MenuCard eyebrow="JUGADORES LIBRES" title="Jugadores Libres" text="Talento disponible sin club y por $0." icon="♙" onPress={() => setTab('libres')} />
          <MenuCard eyebrow="PLANTEL" title="Plantel" text="Revisá jugadores, OVR y valor AJPA." icon="▦" onPress={() => setTab('equipos')} />
        </ScrollView>
      );
    }

    if (tab === 'equipos') {
      return (
        <ScrollView contentContainerStyle={s.content}>
          <View style={s.headerBox}>
            <Text style={s.eyebrow}>MI CLUB</Text>
            <Text style={s.screenTitle}>Planteles oficiales</Text>
            <Text style={s.muted}>Elegí un club para ver su información real.</Text>
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
              <View style={s.flex}>
                <Text style={s.name}>{selected.name}</Text>
                <Text style={s.muted}>{selected.roster_count} jugadores</Text>
              </View>
              <View style={{ alignItems: 'flex-end' }}>
                <Text style={s.statLabel}>PRESUPUESTO</Text>
                <Text style={s.money}>{money(selected.balance)}</Text>
              </View>
            </View>
          ) : null}

          {rosterLoading ? <ActivityIndicator color={C.blue} style={{ marginVertical: 18 }} /> : null}
          {!rosterLoading && roster.length === 0 ? <Empty text="No hay jugadores para mostrar." /> : null}
          {roster.map((player) => <Player key={player.id ?? player.name} player={player} />)}
        </ScrollView>
      );
    }

    if (tab === 'mercado') {
      return (
        <ScrollView contentContainerStyle={s.content} refreshControl={refresh}>
          <View style={s.headerBox}>
            <Text style={s.eyebrow}>TRANSFER MARKET</Text>
            <Text style={s.screenTitle}>Mercado de Pases</Text>
            <Text style={s.muted}>Publicaciones activas de clubes.</Text>
          </View>
          <View style={[s.banner, { borderColor: snapshot.status.market_open ? '#1c6a3a' : '#6b3038' }]}>
            <Text style={s.name}>{snapshot.status.market_open ? 'Mercado abierto' : 'Mercado cerrado'}</Text>
            <Text style={s.muted}>Modo lectura · datos directos de AJPA.</Text>
          </View>
          {market.length === 0 ? <Empty text="No hay publicaciones activas." /> : market.map((item) => <Market key={item.publication_id} item={item} />)}
        </ScrollView>
      );
    }

    if (tab === 'libres') {
      return (
        <ScrollView contentContainerStyle={s.content} refreshControl={refresh}>
          <View style={s.headerBox}>
            <Text style={s.eyebrow}>JUGADORES LIBRES</Text>
            <Text style={s.screenTitle}>Agentes libres</Text>
            <Text style={s.muted}>Jugadores liberados disponibles por $0.</Text>
          </View>
          {free.length === 0 ? <Empty text="No hay agentes libres disponibles." /> : free.map((item) => <Market key={item.publication_id} item={item} />)}
        </ScrollView>
      );
    }

    return (
      <ScrollView contentContainerStyle={s.content}>
        <View style={s.profileBox}>
          <Image source={{ uri: AJPA_LOGO_DATA_URI }} style={s.profileLogo} />
          <Text style={s.eyebrow}>AJPA TRANSFER MARKET</Text>
          <Text style={s.screenTitle}>Perfil</Text>
          <Text style={s.muted}>App conectada en modo lectura a los datos oficiales.</Text>
        </View>
        <GlassCard>
          <Text style={s.eyebrow}>ESTADO</Text>
          <Text style={s.name}>Conectado</Text>
          <View style={s.divider} />
          <Text style={s.eyebrow}>VERSIÓN</Text>
          <Text style={s.name}>v0.1</Text>
        </GlassCard>
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
      <Image source={{ uri: BG[tab] }} style={s.background} resizeMode="cover" />
      <View style={s.overlay} />

      <View style={s.topBar}>
        <View>
          <Text style={s.topBrand}>AJPA</Text>
          <Text style={s.topSub}>TRANSFER MARKET</Text>
        </View>
        <View style={s.readPill}><Text style={s.readText}>LECTURA</Text></View>
      </View>

      <View style={s.main}>{content}</View>

      {snapshot ? (
        <View style={s.nav}>
          {tabs.map((item) => {
            const active = item.id === tab;
            const center = item.id === 'mercado';
            return (
              <Pressable key={item.id} onPress={() => setTab(item.id)} style={[s.navItem, center && s.navMarketItem]}>
                <View style={[s.navIconWrap, center && s.marketButton, active && !center && s.navActiveBox, active && center && s.marketButtonActive]}>
                  <Text style={[s.navIcon, active && s.active, center && s.marketIcon]}>{item.icon}</Text>
                </View>
                <Text style={[s.navLabel, active && s.active]}>{item.label}</Text>
              </Pressable>
            );
          })}
        </View>
      ) : null}
    </View>
  );
}

const s = StyleSheet.create({
  root: { flex: 1, backgroundColor: C.dark },
  background: { ...StyleSheet.absoluteFillObject, width: '100%', height: '100%' },
  overlay: { ...StyleSheet.absoluteFillObject, backgroundColor: 'rgba(1,6,12,0.58)' },
  main: { flex: 1 },
  topBar: { height: 58, paddingHorizontal: 18, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', backgroundColor: 'rgba(3,8,13,0.92)', borderBottomWidth: 1, borderBottomColor: '#172534' },
  topBrand: { color: C.white, fontSize: 22, fontWeight: '900', letterSpacing: 1.5, lineHeight: 24 },
  topSub: { color: C.blue, fontSize: 9, fontWeight: '900', letterSpacing: 2.1 },
  readPill: { backgroundColor: 'rgba(11,27,42,0.94)', borderWidth: 1, borderColor: '#173553', borderRadius: 999, paddingHorizontal: 10, paddingVertical: 5 },
  readText: { color: C.blueSoft, fontWeight: '900', fontSize: 9, letterSpacing: 1.1 },
  content: { padding: 16, paddingBottom: 32, gap: 11 },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center', gap: 12 },
  loadingLogo: { width: 78, height: 78, borderRadius: 39 },
  hero: { minHeight: 194, flexDirection: 'row', alignItems: 'center', padding: 20, borderRadius: 24, backgroundColor: 'rgba(5,11,17,0.82)', borderWidth: 1, borderColor: '#24405b' },
  heroCopy: { flex: 1 },
  brand: { color: C.white, fontSize: 34, fontWeight: '900', letterSpacing: 1.5 },
  brandSub: { color: C.blue, fontSize: 11, fontWeight: '900', letterSpacing: 2.2, marginBottom: 18 },
  heroSmall: { color: C.blueSoft, fontSize: 10, fontWeight: '900', letterSpacing: 1.4, marginBottom: 5 },
  heroTitle: { color: C.white, fontSize: 23, fontWeight: '900', lineHeight: 27 },
  heroBlue: { color: C.blue, fontSize: 23, fontWeight: '900', lineHeight: 27 },
  heroLogo: { width: 112, height: 112, borderRadius: 56, borderWidth: 2, borderColor: C.blue, marginLeft: 8 },
  stats: { flexDirection: 'row', backgroundColor: 'rgba(7,16,24,0.90)', borderRadius: 20, borderWidth: 1, borderColor: '#1b2b3a', overflow: 'hidden' },
  stat: { flex: 1, alignItems: 'center', paddingVertical: 11, borderRightWidth: StyleSheet.hairlineWidth, borderRightColor: '#263747' },
  statIcon: { color: C.blue, fontSize: 18, fontWeight: '900' },
  statValue: { color: C.white, fontSize: 16, fontWeight: '900', marginTop: 2 },
  statLabel: { color: C.muted, fontSize: 8, fontWeight: '800', textAlign: 'center', marginTop: 2 },
  marketState: { flexDirection: 'row', alignItems: 'center', backgroundColor: 'rgba(2,8,14,0.62)', borderRadius: 12, padding: 9 },
  dot: { width: 8, height: 8, borderRadius: 4, marginRight: 7 },
  marketText: { color: C.white, fontSize: 12, fontWeight: '800' },
  season: { color: C.muted, fontSize: 11, marginLeft: 'auto' },
  menuCard: { minHeight: 110, flexDirection: 'row', alignItems: 'center', padding: 15, borderRadius: 20, backgroundColor: 'rgba(7,16,25,0.88)', borderWidth: 1, borderColor: '#29425a' },
  menuIcon: { width: 56, height: 56, borderRadius: 28, alignItems: 'center', justifyContent: 'center', backgroundColor: 'rgba(9,23,37,0.95)', borderWidth: 1, borderColor: '#29425a' },
  menuIconText: { color: C.blue, fontSize: 27, fontWeight: '900' },
  menuTitle: { color: C.white, fontSize: 19, fontWeight: '900', marginTop: 2 },
  menuText: { color: C.muted, fontSize: 12, lineHeight: 17, marginTop: 3 },
  chevron: { color: C.white, fontSize: 30, marginLeft: 8 },
  card: { backgroundColor: C.panel, borderWidth: 1, borderColor: C.line, borderRadius: 18, padding: 14 },
  headerBox: { backgroundColor: 'rgba(2,8,14,0.62)', padding: 12, borderRadius: 16, marginBottom: 2 },
  profileBox: { alignItems: 'center', backgroundColor: 'rgba(2,8,14,0.62)', padding: 20, borderRadius: 20 },
  profileLogo: { width: 108, height: 108, borderRadius: 54, borderWidth: 2, borderColor: C.blue, marginBottom: 14 },
  screenTitle: { color: C.white, fontSize: 27, fontWeight: '900' },
  eyebrow: { color: C.blue, fontSize: 10, fontWeight: '900', letterSpacing: 1.6, marginBottom: 3 },
  muted: { color: C.muted, fontSize: 13, marginTop: 3 },
  row: { flexDirection: 'row', alignItems: 'center' },
  flex: { flex: 1, marginLeft: 12 },
  ovr: { width: 50, height: 50, borderRadius: 15, alignItems: 'center', justifyContent: 'center', backgroundColor: '#0b2133', borderWidth: 1, borderColor: '#1f4261' },
  ovrValue: { color: C.blueSoft, fontSize: 19, fontWeight: '900', lineHeight: 20 },
  ovrLabel: { color: '#5f87a8', fontSize: 8, fontWeight: '900' },
  name: { color: C.white, fontSize: 16, fontWeight: '900' },
  money: { color: C.white, fontSize: 14, fontWeight: '900', marginLeft: 8 },
  free: { color: '#51dc79' },
  divider: { height: 1, backgroundColor: '#1a2a38', marginVertical: 12 },
  operation: { color: C.blueSoft, fontSize: 10, fontWeight: '900', letterSpacing: 1 },
  detail: { color: '#c1cbd4', fontSize: 13, lineHeight: 18, marginTop: 5 },
  marketValue: { color: C.muted, fontSize: 11, marginTop: 8 },
  chips: { gap: 8, paddingBottom: 4 },
  chip: { backgroundColor: 'rgba(7,16,25,0.90)', borderWidth: 1, borderColor: '#1d3142', borderRadius: 999, paddingHorizontal: 13, paddingVertical: 9 },
  chipActive: { backgroundColor: 'rgba(12,43,72,0.94)', borderColor: C.blue },
  chipText: { color: C.muted, fontSize: 12, fontWeight: '700' },
  chipTextActive: { color: '#d5eaff' },
  clubSummary: { flexDirection: 'row', alignItems: 'center', backgroundColor: 'rgba(8,18,28,0.92)', borderRadius: 20, borderWidth: 1, borderColor: '#20384c', padding: 14 },
  clubInitial: { width: 54, height: 54, borderRadius: 18, backgroundColor: '#0b2133', alignItems: 'center', justifyContent: 'center' },
  clubInitialText: { color: C.blueSoft, fontWeight: '900', fontSize: 16 },
  banner: { backgroundColor: 'rgba(7,16,25,0.90)', borderWidth: 1, borderRadius: 18, padding: 14 },
  nav: { height: 78, flexDirection: 'row', backgroundColor: 'rgba(3,8,13,0.95)', borderTopWidth: 1, borderTopColor: '#172534', paddingHorizontal: 4 },
  navItem: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  navMarketItem: { marginTop: -15 },
  navIconWrap: { width: 36, height: 34, borderRadius: 12, alignItems: 'center', justifyContent: 'center' },
  navActiveBox: { backgroundColor: '#0b2133' },
  navIcon: { color: '#71808d', fontSize: 20, fontWeight: '800' },
  navLabel: { color: '#71808d', fontSize: 9, fontWeight: '800', marginTop: 2 },
  active: { color: C.blue },
  marketButton: { width: 58, height: 58, borderRadius: 29, backgroundColor: '#0d4f91', borderWidth: 2, borderColor: C.blue, shadowColor: C.blue, shadowOpacity: 0.45, shadowRadius: 10, elevation: 8 },
  marketButtonActive: { backgroundColor: C.blue, borderColor: '#8cc7ff' },
  marketIcon: { color: '#06111c', fontSize: 26, fontWeight: '900' },
});
