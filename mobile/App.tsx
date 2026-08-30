import React, { useMemo, useState } from 'react';
import {
  Pressable,
  SafeAreaView,
  ScrollView,
  StatusBar,
  StyleSheet,
  Text,
  View,
} from 'react-native';

type Tab = 'inicio' | 'plantel' | 'mercado' | 'ofertas';

type Player = {
  id: string;
  name: string;
  position: string;
  ovr: number;
  value: number;
  club?: string;
};

const roster: Player[] = [
  { id: 'AJPA-000101', name: 'Ronaldinho', position: 'MCO', ovr: 90, value: 30_000_000 },
  { id: 'AJPA-000102', name: 'Riquelme', position: 'MCO', ovr: 88, value: 20_000_000 },
  { id: 'AJPA-000103', name: 'Mascherano', position: 'MCD', ovr: 84, value: 4_500_000 },
  { id: 'AJPA-000104', name: 'Tevez', position: 'SD', ovr: 86, value: 8_000_000 },
  { id: 'AJPA-000105', name: 'Samuel', position: 'DFC', ovr: 82, value: 3_500_000 },
];

const market: Player[] = [
  { id: 'AJPA-000221', name: 'Aimar', position: 'MCO', ovr: 84, value: 4_500_000, club: 'Ajax' },
  { id: 'AJPA-000222', name: 'Crespo', position: 'DC', ovr: 83, value: 4_500_000, club: 'Torino' },
  { id: 'AJPA-000223', name: 'Saviola', position: 'DC', ovr: 81, value: 3_500_000, club: 'West Ham' },
];

const money = (value: number) => `$${(value / 1_000_000).toFixed(value % 1_000_000 === 0 ? 0 : 1)}M`;

function Card({ children }: { children: React.ReactNode }) {
  return <View style={styles.card}>{children}</View>;
}

function SectionTitle({ children }: { children: React.ReactNode }) {
  return <Text style={styles.sectionTitle}>{children}</Text>;
}

function PlayerRow({ player, marketMode = false }: { player: Player; marketMode?: boolean }) {
  return (
    <View style={styles.playerRow}>
      <View style={styles.ovrBubble}>
        <Text style={styles.ovrValue}>{player.ovr}</Text>
        <Text style={styles.ovrLabel}>OVR</Text>
      </View>
      <View style={styles.playerMain}>
        <Text style={styles.playerName}>{player.name}</Text>
        <Text style={styles.muted}>{player.position}{player.club ? ` · ${player.club}` : ''}</Text>
        <Text style={styles.playerId}>{player.id}</Text>
      </View>
      <View style={styles.rightColumn}>
        <Text style={styles.valueText}>{money(player.value)}</Text>
        {marketMode ? (
          <Pressable style={styles.smallButton}>
            <Text style={styles.smallButtonText}>Ofertar</Text>
          </Pressable>
        ) : null}
      </View>
    </View>
  );
}

function HomeScreen() {
  return (
    <ScrollView contentContainerStyle={styles.content}>
      <View style={styles.hero}>
        <View style={styles.clubBadge}>
          <Text style={styles.clubBadgeText}>MC</Text>
        </View>
        <View style={styles.heroText}>
          <Text style={styles.eyebrow}>MI CLUB</Text>
          <Text style={styles.clubName}>Manchester City</Text>
          <Text style={styles.muted}>AJPA Transfer Market</Text>
        </View>
      </View>

      <View style={styles.statsGrid}>
        <Card>
          <Text style={styles.statLabel}>PRESUPUESTO</Text>
          <Text style={styles.statValue}>$10M</Text>
        </Card>
        <Card>
          <Text style={styles.statLabel}>PLANTEL</Text>
          <Text style={styles.statValue}>24 / 32</Text>
        </Card>
        <Card>
          <Text style={styles.statLabel}>OFERTAS</Text>
          <Text style={styles.statValue}>2</Text>
        </Card>
        <Card>
          <Text style={styles.statLabel}>MERCADO</Text>
          <Text style={[styles.statValue, styles.openText]}>ABIERTO</Text>
        </Card>
      </View>

      <SectionTitle>Actividad reciente</SectionTitle>
      <Card>
        <Text style={styles.activityTitle}>Oferta recibida</Text>
        <Text style={styles.activityBody}>Ajax envió una oferta por Ronaldinho.</Text>
        <Text style={styles.activityTime}>Hace 8 min</Text>
      </Card>
      <Card>
        <Text style={styles.activityTitle}>Movimiento aprobado</Text>
        <Text style={styles.activityBody}>El staff aprobó el fichaje de Mascherano.</Text>
        <Text style={styles.activityTime}>Hace 1 h</Text>
      </Card>
    </ScrollView>
  );
}

function RosterScreen() {
  return (
    <ScrollView contentContainerStyle={styles.content}>
      <View style={styles.screenHeader}>
        <Text style={styles.screenTitle}>Mi plantel</Text>
        <Text style={styles.muted}>24 jugadores · mínimo 20 · máximo 32</Text>
      </View>
      {roster.map((player) => (
        <Card key={player.id}>
          <PlayerRow player={player} />
        </Card>
      ))}
    </ScrollView>
  );
}

function MarketScreen() {
  return (
    <ScrollView contentContainerStyle={styles.content}>
      <View style={styles.screenHeader}>
        <Text style={styles.screenTitle}>Mercado</Text>
        <Text style={styles.muted}>Jugadores publicados por otros clubes</Text>
      </View>
      <View style={styles.marketBanner}>
        <Text style={styles.marketBannerTitle}>Mercado abierto</Text>
        <Text style={styles.marketBannerBody}>Podés ofertar dinero, jugador o combinar ambos.</Text>
      </View>
      {market.map((player) => (
        <Card key={player.id}>
          <PlayerRow player={player} marketMode />
        </Card>
      ))}
    </ScrollView>
  );
}

function OffersScreen() {
  return (
    <ScrollView contentContainerStyle={styles.content}>
      <View style={styles.screenHeader}>
        <Text style={styles.screenTitle}>Mis ofertas</Text>
        <Text style={styles.muted}>Recibidas y enviadas</Text>
      </View>

      <SectionTitle>Recibidas</SectionTitle>
      <Card>
        <View style={styles.offerTop}>
          <Text style={styles.offerPlayer}>Ronaldinho · 90 OVR</Text>
          <Text style={styles.pendingPill}>PENDIENTE</Text>
        </View>
        <Text style={styles.activityBody}>Ajax ofrece $18M + Aimar (84 OVR).</Text>
        <View style={styles.offerActions}>
          <Pressable style={[styles.actionButton, styles.acceptButton]}>
            <Text style={styles.actionText}>Aceptar</Text>
          </Pressable>
          <Pressable style={styles.actionButton}>
            <Text style={styles.actionText}>Contraoferta</Text>
          </Pressable>
          <Pressable style={styles.actionButton}>
            <Text style={styles.actionText}>Rechazar</Text>
          </Pressable>
        </View>
      </Card>

      <SectionTitle>Enviadas</SectionTitle>
      <Card>
        <View style={styles.offerTop}>
          <Text style={styles.offerPlayer}>Crespo · 83 OVR</Text>
          <Text style={styles.pendingPill}>ESPERANDO</Text>
        </View>
        <Text style={styles.activityBody}>Tu oferta: $5M.</Text>
        <Text style={styles.activityTime}>Torino todavía no respondió.</Text>
      </Card>
    </ScrollView>
  );
}

export default function App() {
  const [tab, setTab] = useState<Tab>('inicio');

  const screen = useMemo(() => {
    if (tab === 'plantel') return <RosterScreen />;
    if (tab === 'mercado') return <MarketScreen />;
    if (tab === 'ofertas') return <OffersScreen />;
    return <HomeScreen />;
  }, [tab]);

  const tabs: { id: Tab; label: string; icon: string }[] = [
    { id: 'inicio', label: 'Inicio', icon: '⌂' },
    { id: 'plantel', label: 'Plantel', icon: '♟' },
    { id: 'mercado', label: 'Mercado', icon: '⇄' },
    { id: 'ofertas', label: 'Ofertas', icon: '✉' },
  ];

  return (
    <SafeAreaView style={styles.safe}>
      <StatusBar barStyle="light-content" backgroundColor="#08110d" />
      <View style={styles.appBar}>
        <Text style={styles.logo}>AJPA</Text>
        <Text style={styles.appBarTitle}>TRANSFER MARKET</Text>
        <View style={styles.profileCircle}>
          <Text style={styles.profileText}>AP</Text>
        </View>
      </View>

      <View style={styles.main}>{screen}</View>

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
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: '#08110d' },
  main: { flex: 1, backgroundColor: '#0c1712' },
  appBar: {
    height: 58,
    paddingHorizontal: 18,
    flexDirection: 'row',
    alignItems: 'center',
    borderBottomWidth: 1,
    borderBottomColor: '#1d2d25',
  },
  logo: { color: '#f5fff8', fontWeight: '900', fontSize: 21, letterSpacing: 1 },
  appBarTitle: { color: '#59df88', fontSize: 11, fontWeight: '800', marginLeft: 8, letterSpacing: 1.5, flex: 1 },
  profileCircle: { width: 34, height: 34, borderRadius: 17, backgroundColor: '#193326', alignItems: 'center', justifyContent: 'center' },
  profileText: { color: '#9cf0b7', fontWeight: '900', fontSize: 12 },
  content: { padding: 16, paddingBottom: 28, gap: 10 },
  hero: { flexDirection: 'row', alignItems: 'center', paddingVertical: 12 },
  clubBadge: { width: 66, height: 66, borderRadius: 18, backgroundColor: '#163b2a', borderWidth: 1, borderColor: '#2b6b48', alignItems: 'center', justifyContent: 'center' },
  clubBadgeText: { color: '#8fe7ad', fontWeight: '900', fontSize: 22 },
  heroText: { marginLeft: 14, flex: 1 },
  eyebrow: { color: '#5edc89', fontWeight: '900', fontSize: 10, letterSpacing: 1.8 },
  clubName: { color: '#f6fff8', fontWeight: '900', fontSize: 24, marginTop: 2 },
  muted: { color: '#8da398', fontSize: 13, marginTop: 3 },
  statsGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: 10 },
  card: { backgroundColor: '#111f18', borderWidth: 1, borderColor: '#21372b', borderRadius: 16, padding: 14, flexGrow: 1 },
  statLabel: { color: '#82998d', fontSize: 10, fontWeight: '800', letterSpacing: 1 },
  statValue: { color: '#f6fff8', fontWeight: '900', fontSize: 20, marginTop: 6 },
  openText: { color: '#61e08b', fontSize: 16 },
  sectionTitle: { color: '#f6fff8', fontSize: 17, fontWeight: '900', marginTop: 12, marginBottom: 2 },
  activityTitle: { color: '#f6fff8', fontSize: 15, fontWeight: '800' },
  activityBody: { color: '#b6c7be', fontSize: 14, marginTop: 5, lineHeight: 20 },
  activityTime: { color: '#667b70', fontSize: 12, marginTop: 8 },
  screenHeader: { marginBottom: 8 },
  screenTitle: { color: '#f6fff8', fontSize: 26, fontWeight: '900' },
  playerRow: { flexDirection: 'row', alignItems: 'center' },
  ovrBubble: { width: 48, height: 48, borderRadius: 14, backgroundColor: '#193326', alignItems: 'center', justifyContent: 'center' },
  ovrValue: { color: '#8eeaab', fontSize: 18, fontWeight: '900', lineHeight: 20 },
  ovrLabel: { color: '#5f8f70', fontSize: 8, fontWeight: '900' },
  playerMain: { flex: 1, marginLeft: 12 },
  playerName: { color: '#f6fff8', fontSize: 16, fontWeight: '900' },
  playerId: { color: '#5f7569', fontSize: 10, marginTop: 4 },
  rightColumn: { alignItems: 'flex-end', marginLeft: 8 },
  valueText: { color: '#f6fff8', fontSize: 14, fontWeight: '900' },
  smallButton: { backgroundColor: '#34bd68', borderRadius: 9, paddingHorizontal: 12, paddingVertical: 7, marginTop: 8 },
  smallButtonText: { color: '#07120c', fontSize: 11, fontWeight: '900' },
  marketBanner: { backgroundColor: '#12351f', borderWidth: 1, borderColor: '#226b3a', borderRadius: 16, padding: 14, marginBottom: 2 },
  marketBannerTitle: { color: '#7dec9f', fontSize: 16, fontWeight: '900' },
  marketBannerBody: { color: '#aed4ba', fontSize: 13, marginTop: 4 },
  offerTop: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 8 },
  offerPlayer: { color: '#f6fff8', fontWeight: '900', fontSize: 16, flex: 1 },
  pendingPill: { color: '#ffe698', backgroundColor: '#40370f', paddingVertical: 5, paddingHorizontal: 8, borderRadius: 8, fontSize: 9, fontWeight: '900', overflow: 'hidden' },
  offerActions: { flexDirection: 'row', gap: 7, marginTop: 14, flexWrap: 'wrap' },
  actionButton: { backgroundColor: '#1d3027', borderRadius: 10, paddingHorizontal: 12, paddingVertical: 9 },
  acceptButton: { backgroundColor: '#2fbf67' },
  actionText: { color: '#f5fff8', fontSize: 11, fontWeight: '900' },
  bottomNav: { height: 68, flexDirection: 'row', backgroundColor: '#08110d', borderTopWidth: 1, borderTopColor: '#1d2d25' },
  navItem: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  navIcon: { color: '#71877b', fontSize: 20, fontWeight: '700', lineHeight: 23 },
  navLabel: { color: '#71877b', fontSize: 10, fontWeight: '800', marginTop: 2 },
  navActive: { color: '#59df88' },
});
