import React, { useEffect, useMemo, useState } from 'react';
import {
  ActivityIndicator,
  Image,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';

import { fetchLeague, fetchSnapshot, LeagueData, LeagueSnapshot } from './api';
import { ClubBadge, getClubTheme } from './teamBadges';

const DEMO_CLUB = 'Olympique de Marsella';

type NavKey = 'Inicio' | 'Mercado' | 'Mi Club' | 'Liga' | 'Copas' | 'Más';

const C = {
  bg: '#030914',
  panel: '#0a1623',
  panel2: '#0d1c2b',
  line: 'rgba(142,183,219,0.14)',
  white: '#f5f9ff',
  muted: '#8fa1b4',
  blue: '#39a9ff',
  green: '#45d982',
  gold: '#d6aa45',
};

function money(value: number | null | undefined) {
  if (value === null || value === undefined) return '—';
  return '$' + Math.round(value).toLocaleString('es-AR');
}

function MenuCard({
  icon,
  title,
  subtitle,
  accent,
  onPress,
}: {
  icon: string;
  title: string;
  subtitle: string;
  accent: string;
  onPress: () => void;
}) {
  return (
    <Pressable onPress={onPress} style={({ pressed }) => [s.menuCard, pressed && s.pressed]}>
      <View style={[s.menuIcon, { backgroundColor: accent }]}>
        <Text style={s.menuIconText}>{icon}</Text>
      </View>
      <Text style={s.menuTitle}>{title}</Text>
      <Text style={s.menuSubtitle}>{subtitle}</Text>
      <Text style={s.menuArrow}>›</Text>
    </Pressable>
  );
}

function StatusPill({
  label,
  value,
  valueColor = C.white,
}: {
  label: string;
  value: string;
  valueColor?: string;
}) {
  return (
    <View style={s.statusPill}>
      <Text style={s.statusLabel}>{label}</Text>
      <Text style={[s.statusValue, { color: valueColor }]}>{value}</Text>
    </View>
  );
}

function SectionTitle({ title, action }: { title: string; action?: string }) {
  return (
    <View style={s.sectionHeader}>
      <Text style={s.sectionTitle}>{title}</Text>
      {action ? <Text style={s.sectionAction}>{action} ›</Text> : null}
    </View>
  );
}

function BottomNav({
  active,
  onChange,
}: {
  active: NavKey;
  onChange: (key: NavKey) => void;
}) {
  const items: Array<[NavKey, string]> = [
    ['Inicio', '⌂'],
    ['Mercado', '⇄'],
    ['Mi Club', '◇'],
    ['Liga', '▥'],
    ['Copas', '♜'],
    ['Más', '•••'],
  ];
  return (
    <View style={s.bottomNav}>
      {items.map(([key, icon]) => {
        const selected = key === active;
        return (
          <Pressable key={key} onPress={() => onChange(key)} style={s.navItem}>
            <Text style={[s.navIcon, selected && s.navSelected]}>{icon}</Text>
            <Text style={[s.navText, selected && s.navSelected]}>{key}</Text>
          </Pressable>
        );
      })}
    </View>
  );
}

export default function ConceptCUiLab() {
  const [snapshot, setSnapshot] = useState<LeagueSnapshot | null>(null);
  const [league, setLeague] = useState<LeagueData | null>(null);
  const [loading, setLoading] = useState(true);
  const [active, setActive] = useState<NavKey>('Inicio');
  const [lastTap, setLastTap] = useState('Inicio');

  useEffect(() => {
    let mounted = true;
    (async () => {
      try {
        const [snap, table] = await Promise.all([fetchSnapshot(), fetchLeague()]);
        if (!mounted) return;
        setSnapshot(snap);
        setLeague(table);
      } catch {
        // UI Lab keeps rendering with safe demo values if the live API is unavailable.
      } finally {
        if (mounted) setLoading(false);
      }
    })();
    return () => { mounted = false; };
  }, []);

  const standings = league?.standings ?? [];
  const heroClub = useMemo(() => {
    if (standings.some(row => row.team.toLowerCase().includes('marsell'))) return standings.find(row => row.team.toLowerCase().includes('marsell'))!.team;
    return DEMO_CLUB;
  }, [standings]);
  const theme = getClubTheme(heroClub);
  const marketOpen = snapshot?.status.market_open ?? true;
  const currentRound = standings.length ? Math.max(...standings.map(row => row.pj || 0)) : 0;
  const topFive = standings.slice(0, 5);
  const clubSummary = snapshot?.clubs.find(c => c.name.toLowerCase() === heroClub.toLowerCase());
  const activeMessage = active === 'Inicio' ? '' : `${active} · vista del laboratorio`;

  const onMenu = (name: string) => {
    setLastTap(name);
    if (['Mercado', 'Mi Club', 'Liga', 'Copas'].includes(name)) setActive(name as NavKey);
  };

  return (
    <View style={s.root}>
      <ScrollView contentContainerStyle={s.scroll} showsVerticalScrollIndicator={false}>
        <View style={s.topBar}>
          <View style={s.brandRow}>
            <Image source={require('../assets/ajpa-app-icon.png')} style={s.logo} resizeMode="contain" />
            <View style={{ flex: 1 }}>
              <Text style={s.brand}>AJPA</Text>
              <Text style={s.brandSub}>ASOCIACIÓN DE JUGADORES DE PES ARGENTINA</Text>
            </View>
          </View>
          <View style={s.userMini}>
            <ClubBadge club={heroClub} size={32} />
            <View style={{ flex: 1 }}>
              <Text style={s.userHello}>UI LAB · PREVIEW</Text>
              <Text style={s.userClub} numberOfLines={1}>{heroClub}</Text>
            </View>
            <Text style={s.bell}>◌</Text>
          </View>
        </View>

        {activeMessage ? (
          <View style={s.labNotice}>
            <Text style={s.labNoticeText}>{activeMessage}</Text>
            <Text style={s.labNoticeSub}>En esta primera versión estamos afinando la Home visual.</Text>
          </View>
        ) : null}

        <View style={[s.hero, { borderColor: theme.primary + '55' }]}>
          <View style={[s.heroGlow, { backgroundColor: theme.primary }]} />
          <View style={[s.heroGlow2, { backgroundColor: theme.accent }]} />
          <View style={s.heroBadgeWatermark}>
            <ClubBadge club={heroClub} size={210} />
          </View>

          <Text style={[s.heroEyebrow, { color: theme.accent }]}>TEMPORADA 2 · AJPA</Text>
          <Text style={s.heroTitle}>
            {currentRound ? `Fecha ${currentRound}` : 'La temporada'}
          </Text>
          <Text style={[s.heroTitle, { color: theme.accent, marginTop: 0 }]}>sigue en juego</Text>
          <Text style={s.heroClubLine}>{heroClub}</Text>

          <View style={s.heroStats}>
            <View>
              <Text style={s.heroStatLabel}>PLANTEL</Text>
              <Text style={s.heroStatValue}>{clubSummary?.roster_count ?? '—'} jugadores</Text>
            </View>
            <View style={s.heroDivider} />
            <View>
              <Text style={s.heroStatLabel}>PRESUPUESTO</Text>
              <Text style={s.heroStatValue}>{money(clubSummary?.balance)}</Text>
            </View>
          </View>

          <View style={s.statusRow}>
            <StatusPill label="TEMPORADA" value="2" valueColor={theme.accent} />
            <StatusPill label="COPAS" value="EN CURSO" valueColor={C.blue} />
            <StatusPill label="MERCADO" value={marketOpen ? 'ABIERTO' : 'CERRADO'} valueColor={marketOpen ? C.green : '#ff747a'} />
          </View>
        </View>

        <View style={s.menuGrid}>
          <MenuCard icon="⇄" title="Mercado" subtitle="Fichajes, ofertas y negociaciones" accent="#277fc1" onPress={() => onMenu('Mercado')} />
          <MenuCard icon="◇" title="Mi Club" subtitle="Plantel, economía y gestión" accent="#1c8c62" onPress={() => onMenu('Mi Club')} />
          <MenuCard icon="▥" title="Liga" subtitle="Tabla, partidos y estadísticas" accent="#2863b7" onPress={() => onMenu('Liga')} />
          <MenuCard icon="♜" title="Copas" subtitle="Competencias internacionales" accent="#a47827" onPress={() => onMenu('Copas')} />
          <MenuCard icon="●" title="Perfil" subtitle="Historial y cuenta del DT" accent="#6249ad" onPress={() => onMenu('Perfil')} />
          <MenuCard icon="⚙" title="Staff / Admin" subtitle="Gestión de liga y herramientas" accent="#526170" onPress={() => onMenu('Staff / Admin')} />
        </View>

        <View style={s.dualRow}>
          <View style={s.newsCard}>
            <SectionTitle title="Noticias AJPA" action="Ver todas" />
            <View style={s.newsImage}>
              <View style={s.newsOrb} />
              <Image source={require('../assets/ajpa-app-icon.png')} style={s.newsLogo} resizeMode="contain" />
              <Text style={s.newsTag}>AJPA</Text>
            </View>
            <Text style={s.newsHeadline}>Todo listo para la nueva etapa de competencia</Text>
            <Text style={s.newsText}>Mercado, liga y copas reunidos en una sola experiencia.</Text>
            <Text style={s.newsTime}>◷ Ahora</Text>
          </View>

          <View style={s.tableCard}>
            <SectionTitle title="Tabla" action="Ver tabla" />
            <View style={s.tableHead}>
              <Text style={[s.th, { width: 22 }]}>#</Text>
              <Text style={[s.th, { flex: 1 }]}>Club</Text>
              <Text style={[s.th, { width: 26, textAlign: 'right' }]}>PJ</Text>
              <Text style={[s.th, { width: 34, textAlign: 'right' }]}>PTS</Text>
            </View>
            {topFive.length ? topFive.map((row, index) => (
              <View key={row.team} style={s.tableRow}>
                <Text style={[s.rank, { width: 22 }]}>{index + 1}</Text>
                <View style={s.tableClub}>
                  <ClubBadge club={row.team} size={20} />
                  <Text style={s.clubName} numberOfLines={1}>{row.team}</Text>
                </View>
                <Text style={[s.td, { width: 26, textAlign: 'right' }]}>{row.pj}</Text>
                <Text style={[s.points, { width: 34, textAlign: 'right' }]}>{row.pts}</Text>
              </View>
            )) : (
              <View style={s.loadingTable}>
                {loading ? <ActivityIndicator color={C.blue} /> : <Text style={s.muted}>Sin datos</Text>}
              </View>
            )}
          </View>
        </View>

        <View style={s.competitions}>
          <SectionTitle title="Competencias" action="Ver todas" />
          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={s.competitionRow}>
            {[
              ['🏆', 'Liga AJPA', 'Temporada 2', C.blue],
              ['♛', 'Champions AJPA', 'En curso', '#caa24c'],
              ['♜', 'Europa AJPA', 'En curso', '#d98b39'],
            ].map(([icon, title, subtitle, color]) => (
              <Pressable key={String(title)} onPress={() => onMenu(String(title))} style={({ pressed }) => [s.competitionCard, pressed && s.pressed]}>
                <Text style={[s.competitionIcon, { color: String(color) }]}>{icon}</Text>
                <View style={{ flex: 1 }}>
                  <Text style={s.competitionTitle}>{title}</Text>
                  <Text style={s.competitionSub}>{subtitle}</Text>
                  <Text style={[s.competitionState, { color: String(color) }]}>● EN CURSO</Text>
                </View>
              </Pressable>
            ))}
          </ScrollView>
        </View>

        <View style={s.versionCard}>
          <Text style={s.versionKicker}>AJPA UI LAB · CONCEPTO C</Text>
          <Text style={s.versionTitle}>Primera versión funcional del rediseño</Text>
          <Text style={s.versionText}>Última interacción: {lastTap}. Esta APK es paralela y no reemplaza la app real.</Text>
        </View>
      </ScrollView>

      <BottomNav active={active} onChange={(key) => { setActive(key); setLastTap(key); }} />
    </View>
  );
}

const s = StyleSheet.create({
  root: { flex: 1, backgroundColor: C.bg },
  scroll: { paddingHorizontal: 16, paddingTop: 12, paddingBottom: 108 },
  topBar: { marginBottom: 14 },
  brandRow: { flexDirection: 'row', alignItems: 'center', gap: 11 },
  logo: { width: 58, height: 58 },
  brand: { color: C.white, fontSize: 34, fontWeight: '900', letterSpacing: 1.2 },
  brandSub: { color: '#66bfff', fontSize: 9, fontWeight: '800', letterSpacing: 1.7, lineHeight: 13, maxWidth: 240 },
  userMini: { marginTop: 10, flexDirection: 'row', alignItems: 'center', gap: 9, paddingHorizontal: 12, paddingVertical: 8, borderRadius: 14, backgroundColor: 'rgba(9,22,34,0.74)', borderWidth: 1, borderColor: C.line },
  userHello: { color: C.muted, fontSize: 9, fontWeight: '800', letterSpacing: 1.1 },
  userClub: { color: C.white, fontSize: 13, fontWeight: '800', marginTop: 1 },
  bell: { color: C.blue, fontSize: 26, fontWeight: '700' },

  labNotice: { marginBottom: 10, borderRadius: 13, backgroundColor: 'rgba(42,139,232,0.10)', borderWidth: 1, borderColor: 'rgba(57,169,255,0.22)', padding: 10 },
  labNoticeText: { color: C.blue, fontSize: 12, fontWeight: '900' },
  labNoticeSub: { color: C.muted, fontSize: 10, marginTop: 2 },

  hero: { minHeight: 280, overflow: 'hidden', borderRadius: 24, backgroundColor: '#07131f', borderWidth: 1, padding: 20, marginBottom: 14 },
  heroGlow: { position: 'absolute', width: 280, height: 280, borderRadius: 280, opacity: 0.22, right: -100, top: -80 },
  heroGlow2: { position: 'absolute', width: 170, height: 170, borderRadius: 170, opacity: 0.08, left: -60, bottom: -60 },
  heroBadgeWatermark: { position: 'absolute', right: -42, bottom: -30, opacity: 0.12 },
  heroEyebrow: { fontSize: 11, fontWeight: '900', letterSpacing: 2.1 },
  heroTitle: { color: C.white, fontSize: 31, lineHeight: 34, fontWeight: '900', marginTop: 10, maxWidth: 275 },
  heroClubLine: { color: '#d6e6f3', fontSize: 12, fontWeight: '800', marginTop: 8 },
  heroStats: { flexDirection: 'row', alignItems: 'center', gap: 14, marginTop: 22 },
  heroDivider: { height: 34, width: 1, backgroundColor: 'rgba(255,255,255,0.18)' },
  heroStatLabel: { color: C.muted, fontSize: 8, fontWeight: '900', letterSpacing: 1.2 },
  heroStatValue: { color: C.white, fontSize: 12, fontWeight: '800', marginTop: 3 },
  statusRow: { flexDirection: 'row', gap: 7, marginTop: 18 },
  statusPill: { flex: 1, minWidth: 0, borderRadius: 11, backgroundColor: 'rgba(3,10,17,0.64)', borderWidth: 1, borderColor: 'rgba(255,255,255,0.08)', paddingHorizontal: 9, paddingVertical: 8 },
  statusLabel: { color: C.muted, fontSize: 7, fontWeight: '900', letterSpacing: 0.8 },
  statusValue: { fontSize: 9, fontWeight: '900', marginTop: 3 },

  menuGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: 10, marginBottom: 14 },
  menuCard: { width: '48.6%', minHeight: 132, borderRadius: 18, backgroundColor: C.panel, borderWidth: 1, borderColor: C.line, padding: 14, position: 'relative' },
  menuIcon: { width: 40, height: 40, borderRadius: 11, alignItems: 'center', justifyContent: 'center', marginBottom: 11 },
  menuIconText: { color: '#fff', fontSize: 22, fontWeight: '900' },
  menuTitle: { color: C.white, fontSize: 16, fontWeight: '900' },
  menuSubtitle: { color: C.muted, fontSize: 10.5, lineHeight: 14, marginTop: 3, paddingRight: 11 },
  menuArrow: { color: C.blue, position: 'absolute', right: 10, top: 72, fontSize: 21 },
  pressed: { opacity: 0.68, transform: [{ scale: 0.985 }] },

  dualRow: { flexDirection: 'row', gap: 10, marginBottom: 14 },
  newsCard: { flex: 1, borderRadius: 18, backgroundColor: C.panel, borderWidth: 1, borderColor: C.line, padding: 11, minHeight: 250 },
  tableCard: { flex: 1, borderRadius: 18, backgroundColor: C.panel, borderWidth: 1, borderColor: C.line, padding: 11, minHeight: 250 },
  sectionHeader: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 9 },
  sectionTitle: { color: C.white, fontSize: 13, fontWeight: '900' },
  sectionAction: { color: C.blue, fontSize: 9, fontWeight: '800' },
  newsImage: { height: 83, borderRadius: 12, overflow: 'hidden', backgroundColor: '#0a2133', alignItems: 'center', justifyContent: 'center', marginBottom: 10 },
  newsOrb: { position: 'absolute', width: 120, height: 120, borderRadius: 120, backgroundColor: C.blue, opacity: 0.12 },
  newsLogo: { width: 54, height: 54, opacity: 0.9 },
  newsTag: { position: 'absolute', left: 8, bottom: 7, color: C.white, fontSize: 9, fontWeight: '900', backgroundColor: 'rgba(17,91,144,0.85)', paddingHorizontal: 7, paddingVertical: 3, borderRadius: 5 },
  newsHeadline: { color: C.white, fontSize: 12, lineHeight: 15, fontWeight: '900' },
  newsText: { color: C.muted, fontSize: 9, lineHeight: 12, marginTop: 5 },
  newsTime: { color: '#6f8499', fontSize: 8, marginTop: 8 },
  tableHead: { flexDirection: 'row', alignItems: 'center', paddingBottom: 6, borderBottomWidth: 1, borderBottomColor: C.line },
  th: { color: '#687f94', fontSize: 7.5, fontWeight: '900' },
  tableRow: { flexDirection: 'row', alignItems: 'center', minHeight: 33, borderBottomWidth: 1, borderBottomColor: 'rgba(133,168,199,0.08)' },
  rank: { color: C.white, fontSize: 10, fontWeight: '900' },
  tableClub: { flex: 1, minWidth: 0, flexDirection: 'row', alignItems: 'center', gap: 5 },
  clubName: { flex: 1, minWidth: 0, color: '#e4edf6', fontSize: 8.5, fontWeight: '700' },
  td: { color: C.muted, fontSize: 8, fontWeight: '700' },
  points: { color: C.white, fontSize: 9, fontWeight: '900' },
  loadingTable: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  muted: { color: C.muted, fontSize: 10 },

  competitions: { borderRadius: 18, backgroundColor: C.panel, borderWidth: 1, borderColor: C.line, padding: 12, marginBottom: 14 },
  competitionRow: { gap: 9 },
  competitionCard: { width: 182, minHeight: 86, flexDirection: 'row', alignItems: 'center', gap: 10, backgroundColor: C.panel2, borderWidth: 1, borderColor: C.line, borderRadius: 14, padding: 11 },
  competitionIcon: { fontSize: 30 },
  competitionTitle: { color: C.white, fontSize: 11, fontWeight: '900' },
  competitionSub: { color: C.muted, fontSize: 9, marginTop: 2 },
  competitionState: { fontSize: 7.5, fontWeight: '900', marginTop: 6 },

  versionCard: { borderRadius: 18, padding: 14, backgroundColor: 'rgba(20,48,70,0.50)', borderWidth: 1, borderColor: 'rgba(57,169,255,0.18)' },
  versionKicker: { color: C.blue, fontSize: 8, fontWeight: '900', letterSpacing: 1.5 },
  versionTitle: { color: C.white, fontSize: 14, fontWeight: '900', marginTop: 4 },
  versionText: { color: C.muted, fontSize: 10, lineHeight: 14, marginTop: 4 },

  bottomNav: { position: 'absolute', left: 0, right: 0, bottom: 0, height: 79, paddingHorizontal: 8, paddingTop: 8, paddingBottom: 8, flexDirection: 'row', backgroundColor: 'rgba(5,15,24,0.98)', borderTopWidth: 1, borderTopColor: 'rgba(120,170,210,0.15)' },
  navItem: { flex: 1, alignItems: 'center', justifyContent: 'center', gap: 2 },
  navIcon: { color: '#8a9aaa', fontSize: 18, fontWeight: '900' },
  navText: { color: '#8a9aaa', fontSize: 8, fontWeight: '800' },
  navSelected: { color: C.blue },
});
