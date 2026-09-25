import React, { useEffect, useMemo, useState } from 'react';
import {
  ActivityIndicator, Image, ImageBackground, Pressable, RefreshControl,
  ScrollView, StatusBar, StyleSheet, Text, View,
} from 'react-native';

import { LeagueData, LeagueSnapshot, fetchLeague, fetchSnapshot } from './api';
import { BG_INICIO } from './bg_inicio';
import { ClubBadge } from './teamBadges';
import { AjpaIcon, AjpaIconName, AjpaIconTile } from './AjpaIcon';
import { HERO_NEUTRAL } from './heroNeutral';

type MenuKey = 'home' | 'market' | 'club' | 'league' | 'cups' | 'profile' | 'admin';

const P = {
  bg: '#06111B', panel: 'rgba(14,34,49,0.94)', panel2: 'rgba(18,42,60,0.94)',
  border: 'rgba(110,164,198,0.18)', white: '#F5FAFE', muted: '#93A7B8',
  blue: '#36A7FF', blue2: '#79C8FF', green: '#42D97F', red: '#F0626E',
};

const menuItems: Array<{
  key: MenuKey;
  icon: AjpaIconName;
  title: string;
  subtitle: string;
  tone: string;
}> = [
  { key: 'market', icon: 'market', title: 'Mercado', subtitle: 'Fichajes, ofertas\ny negociaciones', tone: '#248EF2' },
  { key: 'club', icon: 'club', title: 'Mi Club', subtitle: 'Plantel, tácticas\ny gestión', tone: '#20A77D' },
  { key: 'league', icon: 'league', title: 'Liga', subtitle: 'Tabla, partidos\ny estadísticas', tone: '#3976DD' },
  { key: 'cups', icon: 'cups', title: 'Copas', subtitle: 'Torneos nacionales\ne internacionales', tone: '#C08A21' },
  { key: 'profile', icon: 'profile', title: 'Perfil', subtitle: 'Historial, logros\ny rendimiento', tone: '#7652C5' },
  { key: 'admin', icon: 'admin', title: 'Staff / Admin', subtitle: 'Gestión de liga\ny herramientas', tone: '#65798C' },
];

const bottomItems: Array<{ key: MenuKey; icon: AjpaIconName; label: string }> = [
  { key: 'home', icon: 'home', label: 'Inicio' },
  { key: 'market', icon: 'market', label: 'Mercado' },
  { key: 'club', icon: 'club', label: 'Mi Club' },
  { key: 'league', icon: 'league', label: 'Liga' },
  { key: 'cups', icon: 'cups', label: 'Copas' },
  { key: 'profile', icon: 'more', label: 'Más' },
];

function MenuCard(props: { icon: AjpaIconName; title: string; subtitle: string; tone: string; onPress: () => void }) {
  return (
    <Pressable onPress={props.onPress} style={({ pressed }) => [s.menuCard, pressed && s.pressed]}>
      <AjpaIconTile name={props.icon} tone={props.tone} size={25} tileSize={50} />
      <Text style={s.menuTitle}>{props.title}</Text>
      <Text style={s.menuSubtitle}>{props.subtitle}</Text>
      <Text style={s.menuChevron}>›</Text>
    </Pressable>
  );
}

export default function PremiumHomePreview() {
  const [snapshot, setSnapshot] = useState<LeagueSnapshot | null>(null);
  const [league, setLeague] = useState<LeagueData | null>(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [selected, setSelected] = useState<MenuKey>('home');

  const load = async (manual = false) => {
    try {
      manual ? setRefreshing(true) : setLoading(true);
      const result = await Promise.all([
        fetchSnapshot(),
        fetchLeague().catch(() => ({ standings: [], scorers: [] } as LeagueData)),
      ]);
      setSnapshot(result[0]);
      setLeague(result[1]);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  useEffect(() => { void load(); }, []);

  const standings = useMemo(() => (league?.standings ?? []).slice(0, 5), [league]);
  const seasonName = snapshot?.status.season?.name || 'TEMPORADA 2';
  const marketOpen = Boolean(snapshot?.status.market_open);

  if (loading) {
    return (
      <View style={s.loading}>
        <StatusBar barStyle="light-content" backgroundColor={P.bg} />
        <ActivityIndicator size="large" color={P.blue} />
        <Text style={s.loadingText}>Preparando AJPA UI Lab…</Text>
      </View>
    );
  }

  return (
    <View style={s.root}>
      <StatusBar barStyle="light-content" backgroundColor={P.bg} />
      <View pointerEvents="none" style={s.orbOne} />
      <View pointerEvents="none" style={s.orbTwo} />

      <ScrollView
        style={s.scroll}
        contentContainerStyle={s.content}
        showsVerticalScrollIndicator={false}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => void load(true)} tintColor={P.blue} colors={[P.blue]} />}
      >
        <View style={s.header}>
          <View style={s.brandRow}>
            <Image source={require('../assets/ajpa-app-icon.png')} style={s.logo} resizeMode="contain" />
            <View style={{ flex: 1 }}>
              <Text style={s.brand}>AJPA</Text>
              <Text style={s.brandSub}>ASOCIACIÓN DE JUGADORES DE PES ARGENTINA</Text>
            </View>
          </View>
          <View style={s.helloWrap}>
            <View style={s.previewDot} />
            <View>
              <Text style={s.hello}>Hola, DT</Text>
              <Text style={s.helloSub}>Vista previa · UI Lab</Text>
            </View>
            <Text style={s.headerChevron}>›</Text>
          </View>
        </View>

        <ImageBackground source={{ uri: HERO_NEUTRAL }} style={s.hero} imageStyle={s.heroImage} resizeMode="cover">
          <View style={s.heroShade} />
          <View style={s.heroContent}>
            <Text style={s.heroEyebrow}>{seasonName.toUpperCase()}</Text>
            <Text style={s.heroTitle}>La pasión{'\n'}sigue en <Text style={s.heroBlue}>AJPA</Text></Text>
            <View style={s.heroMetaRow}>
              <View style={s.heroMeta}>
                <AjpaIcon name="season" size={25} color={P.white} />
                <View><Text style={s.metaSmall}>Temporada oficial</Text><Text style={s.metaStrong}>En curso</Text></View>
              </View>
              <View style={s.metaDivider} />
              <View style={s.heroMeta}>
                <AjpaIcon name={marketOpen ? 'market' : 'closed'} size={25} color={marketOpen ? P.green : P.red} />
                <View>
                  <Text style={s.metaSmall}>Mercado</Text>
                  <Text style={[s.metaStrong, { color: marketOpen ? P.green : P.red }]}>{marketOpen ? 'ABIERTO' : 'CERRADO'}</Text>
                </View>
              </View>
            </View>
            <View style={s.dots}><View style={[s.dot, s.dotActive]} /><View style={s.dot} /><View style={s.dot} /></View>
          </View>
        </ImageBackground>

        <View style={s.menuGrid}>
          {menuItems.map(item => <MenuCard key={item.key} icon={item.icon} title={item.title} subtitle={item.subtitle} tone={item.tone} onPress={() => setSelected(item.key)} />)}
        </View>

        <View style={s.dualRow}>
          <View style={s.newsCard}>
            <View style={s.sectionHeader}><Text style={s.sectionTitle}>Noticias AJPA</Text><Text style={s.link}>Ver todas ›</Text></View>
            <View style={s.newsImage}>
              <ImageBackground source={{ uri: BG_INICIO }} style={StyleSheet.absoluteFill} imageStyle={{ borderRadius: 13 }}><View style={s.newsShade} /></ImageBackground>
              <View style={s.newsBadge}><Text style={s.newsBadgeText}>AJPA</Text></View>
            </View>
            <Text style={s.newsTitle}>Nueva etapa, misma competencia</Text>
            <Text style={s.newsText}>Mercado, Liga y Copas en una experiencia más clara y moderna.</Text>
            <Text style={s.newsTime}>◷ Ahora</Text>
          </View>

          <View style={s.tableCard}>
            <View style={s.sectionHeader}><Text style={s.sectionTitle}>Tabla</Text><Text style={s.link}>Ver tabla ›</Text></View>
            <View style={s.tableHead}>
              <Text style={[s.th, { width: 20 }]}>#</Text><Text style={[s.th, { flex: 1 }]}>Club</Text>
              <Text style={[s.th, { width: 22, textAlign: 'right' }]}>PJ</Text><Text style={[s.th, { width: 34, textAlign: 'right' }]}>PTS</Text>
            </View>
            {standings.length ? standings.map((row, index) => (
              <View key={row.team + '-' + index} style={s.tableRow}>
                <Text style={[s.rank, { width: 20 }]}>{index + 1}</Text>
                <View style={s.clubCell}><ClubBadge club={row.team} size={19} /><Text numberOfLines={1} style={s.clubName}>{row.team}</Text></View>
                <Text style={s.stat}>{row.pj}</Text><Text style={[s.stat, s.points]}>{row.pts}</Text>
              </View>
            )) : <Text style={s.empty}>La tabla real aparecerá cuando cargue la Liga.</Text>}
          </View>
        </View>

        <View style={s.competitions}>
          <View style={s.sectionHeader}><Text style={s.sectionTitle}>Competencias</Text><Text style={s.link}>Ver todas ›</Text></View>
          <View style={s.competitionRow}>
            <View style={s.competitionCard}>
              <AjpaIconTile name="league" size={18} tileSize={34} tone="#173C5B" />
              <Text style={s.compTitle}>Liga AJPA</Text><Text style={s.compSub}>{seasonName}</Text><Text style={s.compLive}>● En curso</Text>
            </View>
            <View style={s.competitionCard}>
              <AjpaIconTile name="competitions" size={18} tileSize={34} tone="#6D531D" />
              <Text style={s.compTitle}>Copa Libertador</Text><Text style={s.compSub}>Competencia principal</Text><Text style={s.compMuted}>● Próxima fase</Text>
            </View>
            <View style={s.competitionCard}>
              <AjpaIconTile name="cups" size={18} tileSize={34} tone="#42366A" />
              <Text style={s.compTitle}>Copa Regional</Text><Text style={s.compSub}>Internacional</Text><Text style={s.compLive}>● En curso</Text>
            </View>
          </View>
        </View>

        <View style={s.previewNote}>
          <Text style={s.previewNoteTitle}>PRIMERA VERSIÓN · CONCEPTO C</Text>
          <Text style={s.previewNoteText}>Build visual paralela. La app real no se toca mientras ajustamos diseño, tamaños, espacios y jerarquía.</Text>
        </View>
      </ScrollView>

      <View style={s.bottomNav}>
        {bottomItems.map(item => {
          const active = selected === item.key || (selected === 'admin' && item.key === 'profile');
          return (
            <Pressable key={item.key} onPress={() => setSelected(item.key)} style={s.bottomItem}>
              <AjpaIcon name={item.icon} size={22} color={active ? P.blue : '#8294A2'} />
              <Text style={[s.bottomLabel, active && s.bottomActive]}>{item.label}</Text>
            </Pressable>
          );
        })}
      </View>
    </View>
  );
}

const s = StyleSheet.create({
  root: { flex: 1, backgroundColor: P.bg }, scroll: { flex: 1 },
  content: { paddingHorizontal: 16, paddingTop: 10, paddingBottom: 108 },
  loading: { flex: 1, backgroundColor: P.bg, alignItems: 'center', justifyContent: 'center', gap: 12 },
  loadingText: { color: P.muted, fontSize: 13, fontWeight: '700' },
  orbOne: { position: 'absolute', width: 280, height: 280, borderRadius: 280, top: -120, right: -100, backgroundColor: 'rgba(34,137,204,0.10)' },
  orbTwo: { position: 'absolute', width: 240, height: 240, borderRadius: 240, top: 420, left: -150, backgroundColor: 'rgba(22,95,145,0.09)' },
  header: { marginBottom: 14 }, brandRow: { flexDirection: 'row', alignItems: 'center', gap: 12 },
  logo: { width: 62, height: 62 }, brand: { color: P.white, fontSize: 34, lineHeight: 36, fontWeight: '900', letterSpacing: 1 },
  brandSub: { color: P.blue2, fontSize: 8.5, fontWeight: '800', letterSpacing: 2.1, marginTop: 3 },
  helloWrap: { marginTop: 10, alignSelf: 'flex-end', flexDirection: 'row', alignItems: 'center', gap: 8, backgroundColor: 'rgba(9,25,38,0.72)', borderRadius: 13, borderWidth: 1, borderColor: P.border, paddingVertical: 8, paddingHorizontal: 10 },
  previewDot: { width: 7, height: 7, borderRadius: 7, backgroundColor: P.blue }, hello: { color: P.white, fontSize: 12, fontWeight: '800' },
  helloSub: { color: P.muted, fontSize: 10, marginTop: 1 }, headerChevron: { color: P.blue, fontSize: 21, marginLeft: 5 },
  hero: { minHeight: 245, borderRadius: 20, overflow: 'hidden', borderWidth: 1, borderColor: 'rgba(125,190,226,0.24)', backgroundColor: '#0A1925', justifyContent: 'flex-end' },
  heroImage: { borderRadius: 20 }, heroShade: { ...StyleSheet.absoluteFillObject, backgroundColor: 'rgba(2,10,17,0.52)' }, heroContent: { paddingHorizontal: 19, paddingVertical: 18 },
  heroEyebrow: { color: P.blue2, fontSize: 10, fontWeight: '900', letterSpacing: 2.4, marginBottom: 7 },
  heroTitle: { color: P.white, fontSize: 31, lineHeight: 33, fontWeight: '900', letterSpacing: -0.6 }, heroBlue: { color: P.blue },
  heroMetaRow: { flexDirection: 'row', alignItems: 'center', marginTop: 20 }, heroMeta: { flexDirection: 'row', alignItems: 'center', gap: 9, flex: 1 },
metaSmall: { color: '#C4D0DA', fontSize: 10 }, metaStrong: { color: P.white, fontSize: 13, fontWeight: '900', marginTop: 2 },
  metaDivider: { width: 1, height: 34, backgroundColor: 'rgba(255,255,255,0.25)', marginHorizontal: 13 },
  dots: { flexDirection: 'row', gap: 7, marginTop: 16 }, dot: { width: 7, height: 7, borderRadius: 7, backgroundColor: 'rgba(255,255,255,0.25)' }, dotActive: { width: 16, backgroundColor: P.blue },
  menuGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: 10, marginTop: 12 },
  menuCard: { width: '48.6%', minHeight: 146, borderRadius: 18, padding: 14, backgroundColor: P.panel, borderWidth: 1, borderColor: P.border, shadowColor: '#000', shadowOffset: { width: 0, height: 8 }, shadowOpacity: 0.25, shadowRadius: 16, elevation: 4 },
  pressed: { opacity: 0.74, transform: [{ scale: 0.985 }] },
  menuTitle: { color: P.white, fontSize: 17, fontWeight: '900', marginTop: 11 }, menuSubtitle: { color: P.muted, fontSize: 11, lineHeight: 15, marginTop: 4 },
  menuChevron: { color: P.blue, fontSize: 22, position: 'absolute', right: 12, top: 72 },
  dualRow: { flexDirection: 'row', gap: 10, marginTop: 12 },
  newsCard: { flex: 1, minHeight: 278, borderRadius: 18, backgroundColor: P.panel, borderWidth: 1, borderColor: P.border, padding: 12 },
  tableCard: { flex: 1, minHeight: 278, borderRadius: 18, backgroundColor: P.panel, borderWidth: 1, borderColor: P.border, padding: 12 },
  sectionHeader: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 9 }, sectionTitle: { color: P.white, fontSize: 14, fontWeight: '900' }, link: { color: P.blue2, fontSize: 9, fontWeight: '800' },
  newsImage: { height: 92, borderRadius: 13, overflow: 'hidden', backgroundColor: '#0A1925', marginBottom: 9 }, newsShade: { ...StyleSheet.absoluteFillObject, backgroundColor: 'rgba(2,8,13,0.22)' },
  newsBadge: { position: 'absolute', left: 8, top: 8, paddingHorizontal: 8, paddingVertical: 4, borderRadius: 7, backgroundColor: 'rgba(14,58,88,0.90)', borderWidth: 1, borderColor: 'rgba(100,190,255,0.45)' },
  newsBadgeText: { color: P.blue2, fontSize: 9, fontWeight: '900' }, newsTitle: { color: P.white, fontSize: 13, lineHeight: 16, fontWeight: '900' },
  newsText: { color: P.muted, fontSize: 9.5, lineHeight: 13, marginTop: 4 }, newsTime: { color: P.muted, fontSize: 9, marginTop: 8 },
  tableHead: { flexDirection: 'row', paddingBottom: 5, borderBottomWidth: 1, borderBottomColor: 'rgba(120,160,185,0.16)' }, th: { color: '#72889A', fontSize: 8, fontWeight: '800' },
  tableRow: { flexDirection: 'row', alignItems: 'center', minHeight: 35, borderBottomWidth: 1, borderBottomColor: 'rgba(120,160,185,0.10)' }, rank: { color: P.white, fontSize: 10, fontWeight: '800' },
  clubCell: { flex: 1, minWidth: 0, flexDirection: 'row', alignItems: 'center', gap: 5 }, clubName: { color: '#D9E5ED', fontSize: 9.2, flex: 1 },
  stat: { color: '#B4C3CE', fontSize: 9, width: 22, textAlign: 'right' }, points: { color: P.white, fontWeight: '900', width: 34 }, empty: { color: P.muted, fontSize: 10, lineHeight: 14, marginTop: 16 },
  competitions: { marginTop: 12, borderRadius: 18, backgroundColor: P.panel, borderWidth: 1, borderColor: P.border, padding: 12 }, competitionRow: { flexDirection: 'row', gap: 8 },
  competitionCard: { flex: 1, minHeight: 112, padding: 10, borderRadius: 14, backgroundColor: P.panel2, borderWidth: 1, borderColor: 'rgba(120,165,192,0.15)' },
  compTitle: { color: P.white, fontSize: 10.5, fontWeight: '900' }, compSub: { color: P.muted, fontSize: 8.5, lineHeight: 11, marginTop: 3 },
  compLive: { color: P.blue2, fontSize: 8, marginTop: 6, fontWeight: '800' }, compMuted: { color: '#8C9EAB', fontSize: 8, marginTop: 6, fontWeight: '800' },
  previewNote: { marginTop: 12, padding: 14, borderRadius: 16, backgroundColor: 'rgba(16,48,70,0.72)', borderWidth: 1, borderColor: 'rgba(64,164,225,0.28)' },
  previewNoteTitle: { color: P.blue2, fontSize: 9, fontWeight: '900', letterSpacing: 1.6 }, previewNoteText: { color: '#B6C8D4', fontSize: 10.5, lineHeight: 15, marginTop: 5 },
  bottomNav: { position: 'absolute', left: 0, right: 0, bottom: 0, height: 78, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-around', backgroundColor: 'rgba(5,16,25,0.98)', borderTopWidth: 1, borderTopColor: 'rgba(104,160,193,0.22)', paddingBottom: 6 },
  bottomItem: { flex: 1, alignItems: 'center', justifyContent: 'center', gap: 3 },
  bottomLabel: { color: '#8294A2', fontSize: 8.5, fontWeight: '700' }, bottomActive: { color: P.blue },
});
