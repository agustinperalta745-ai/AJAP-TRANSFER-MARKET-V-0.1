import React, { useMemo, useState } from 'react';
import {
  Image,
  ImageBackground,
  Pressable,
  ScrollView,
  StatusBar,
  StyleSheet,
  Text,
  View,
} from 'react-native';

import { AJPA_LOGO_DATA_URI } from './branding';
import { BG_INICIO } from './bg_inicio';
import { ClubBadge, getClubTheme } from './teamBadges';

const CLUB = 'Olympique de Marsella';

const MENU = [
  { key: 'market', icon: '⇄', title: 'Mercado', sub: 'Fichajes, ofertas\ny negociaciones', tone: '#2e84d4' },
  { key: 'club', icon: '◇', title: 'Mi Club', sub: 'Plantel, economía\ny gestión', tone: '#2a9a70' },
  { key: 'league', icon: '▥', title: 'Liga', sub: 'Tabla, partidos\ny estadísticas', tone: '#426dcc' },
  { key: 'cups', icon: '♕', title: 'Copas', sub: 'Torneos nacionales\ne internacionales', tone: '#a47b29' },
  { key: 'profile', icon: '●', title: 'Perfil', sub: 'Historial, logros\ny rendimiento', tone: '#6554b7' },
  { key: 'staff', icon: '⚙', title: 'Staff / Admin', sub: 'Gestión de liga\ny herramientas', tone: '#657180' },
];

const TABLE = [
  ['1', 'Olympique de Marsella', '13', '+18', '31'],
  ['2', 'Everton', '13', '+12', '28'],
  ['3', 'Ajax', '13', '+8', '26'],
  ['4', 'Porto', '13', '+6', '24'],
  ['5', 'Benfica', '13', '+4', '22'],
];

const trophyLiga = require('../assets/trophies/liga-ajpa-rank-icon.png');
const trophyChampions = require('../assets/trophies/champions-ajpa.jpg');
const trophyEuropa = require('../assets/trophies/europa-ajpa-card-icon.png');

function MenuCard({
  icon,
  title,
  sub,
  tone,
  onPress,
}: {
  icon: string;
  title: string;
  sub: string;
  tone: string;
  onPress: () => void;
}) {
  return (
    <Pressable onPress={onPress} style={({ pressed }) => [s.menuCard, pressed && s.pressed]}>
      <View style={[s.menuIcon, { backgroundColor: tone }]}>
        <Text style={s.menuIconText}>{icon}</Text>
      </View>
      <Text style={s.menuTitle}>{title}</Text>
      <Text style={s.menuSub}>{sub}</Text>
      <Text style={s.menuArrow}>›</Text>
    </Pressable>
  );
}

function Pill({ text, active = false }: { text: string; active?: boolean }) {
  return (
    <View style={[s.pill, active && s.pillActive]}>
      <View style={[s.pillDot, active && s.pillDotActive]} />
      <Text style={[s.pillText, active && s.pillTextActive]}>{text}</Text>
    </View>
  );
}

function TrophyCard({
  image,
  title,
  meta,
  active,
}: {
  image: any;
  title: string;
  meta: string;
  active?: boolean;
}) {
  return (
    <View style={s.trophyCard}>
      <View style={s.trophyImageWrap}>
        <Image source={image} style={s.trophyImage} resizeMode="contain" />
      </View>
      <View style={{ flex: 1, minWidth: 0 }}>
        <Text numberOfLines={1} style={s.trophyTitle}>{title}</Text>
        <Text numberOfLines={1} style={s.trophyMeta}>{meta}</Text>
        <View style={s.trophyState}>
          <View style={[s.trophyDot, active && s.trophyDotActive]} />
          <Text style={[s.trophyStateText, active && s.trophyStateTextActive]}>
            {active ? 'En curso' : 'Próxima fase'}
          </Text>
        </View>
      </View>
    </View>
  );
}

export default function ConceptCPreview() {
  const [active, setActive] = useState('home');
  const theme = useMemo(() => getClubTheme(CLUB), []);
  const selectedLabel = active === 'home'
    ? 'Inicio'
    : MENU.find(item => item.key === active)?.title ?? 'Inicio';

  return (
    <View style={s.root}>
      <StatusBar barStyle="light-content" backgroundColor="#06111d" />
      <ImageBackground source={{ uri: BG_INICIO }} style={s.background} resizeMode="cover">
        <View style={s.darkLayer}>
          <ScrollView contentContainerStyle={s.content} showsVerticalScrollIndicator={false}>
            <View style={s.header}>
              <View style={s.brandRow}>
                <Image source={{ uri: AJPA_LOGO_DATA_URI }} style={s.logo} resizeMode="contain" />
                <View>
                  <Text style={s.brand}>AJPA</Text>
                  <Text style={s.brandSub}>LIGA ARGENTINA DE</Text>
                  <Text style={s.brandSub}>FÚTBOL VIRTUAL</Text>
                </View>
              </View>
              <View style={s.userArea}>
                <View style={s.bell}><Text style={s.bellText}>♢</Text><View style={s.notifyDot} /></View>
                <View style={s.userLine}>
                  <ClubBadge club={CLUB} size={26} />
                  <View style={{ marginLeft: 8 }}>
                    <Text style={s.hello}>Hola, DT</Text>
                    <Text style={s.userClub}>Marsella</Text>
                  </View>
                  <Text style={s.userArrow}>›</Text>
                </View>
              </View>
            </View>

            <View style={[s.hero, { borderColor: theme.primary + '88' }]}>
              <View style={[s.heroGlowA, { backgroundColor: theme.primary }]} />
              <View style={[s.heroGlowB, { backgroundColor: theme.secondary }]} />
              <View style={s.heroBadgeGhost}>
                <ClubBadge club={CLUB} size={154} style={{ opacity: 0.16 }} />
              </View>

              <Text style={[s.heroEyebrow, { color: theme.accent }]}>TEMPORADA 2 · AJPA</Text>
              <Text style={s.heroTitle}>Tu club.</Text>
              <Text style={s.heroTitle}>Tu temporada.</Text>
              <Text style={[s.heroTitleAccent, { color: theme.accent }]}>Todo en un solo lugar.</Text>

              <View style={s.heroBottom}>
                <View>
                  <Text style={s.heroInfoLabel}>ESTADO DE TEMPORADA</Text>
                  <Text style={s.heroInfoValue}>Temporada cerrada</Text>
                </View>
                <View style={s.heroDivider} />
                <View>
                  <Text style={s.heroInfoLabel}>MERCADO</Text>
                  <Text style={s.marketOpen}>ABIERTO</Text>
                </View>
              </View>
            </View>

            <View style={s.statusRow}>
              <Pill text="Temporada 2" active />
              <Pill text="Copas" active />
              <Pill text="Temporada cerrada" />
              <Pill text="Mercado abierto" active />
            </View>

            <View style={s.menuGrid}>
              {MENU.map(item => (
                <MenuCard
                  key={item.key}
                  {...item}
                  onPress={() => setActive(item.key)}
                />
              ))}
            </View>

            <View style={s.twoCol}>
              <View style={[s.panel, s.newsPanel]}>
                <View style={s.panelHeader}>
                  <Text style={s.panelTitle}>Noticias AJPA</Text>
                  <Text style={s.panelLink}>Ver todas ›</Text>
                </View>
                <View style={s.newsVisual}>
                  <View style={s.newsVisualGlow} />
                  <Image source={{ uri: AJPA_LOGO_DATA_URI }} style={s.newsLogo} resizeMode="contain" />
                  <Text style={s.newsTag}>AJPA</Text>
                </View>
                <Text style={s.newsTitle}>La Temporada 2 ya tiene todo listo</Text>
                <Text style={s.newsBody}>Mercado, copas y gestión del club desde una sola app.</Text>
                <Text style={s.newsMeta}>◷ Hace 2 h</Text>
              </View>

              <View style={[s.panel, s.tablePanel]}>
                <View style={s.panelHeader}>
                  <Text style={s.panelTitle}>Tabla de posiciones</Text>
                  <Text style={s.panelLink}>Ver tabla ›</Text>
                </View>
                <View style={s.tableHead}>
                  <Text style={[s.th, { width: 18 }]}>#</Text>
                  <Text style={[s.th, { flex: 1 }]}>Club</Text>
                  <Text style={[s.th, { width: 22, textAlign: 'right' }]}>PJ</Text>
                  <Text style={[s.th, { width: 28, textAlign: 'right' }]}>DG</Text>
                  <Text style={[s.th, { width: 26, textAlign: 'right' }]}>PTS</Text>
                </View>
                {TABLE.map(row => (
                  <View key={row[0]} style={s.tableRow}>
                    <Text style={[s.tdRank, { width: 18 }]}>{row[0]}</Text>
                    <View style={s.clubCell}>
                      <ClubBadge club={row[1]} size={17} />
                      <Text numberOfLines={1} style={s.tdClub}>{row[1]}</Text>
                    </View>
                    <Text style={[s.td, { width: 22 }]}>{row[2]}</Text>
                    <Text style={[s.td, { width: 28 }]}>{row[3]}</Text>
                    <Text style={[s.tdPts, { width: 26 }]}>{row[4]}</Text>
                  </View>
                ))}
              </View>
            </View>

            <View style={s.competitions}>
              <View style={s.panelHeader}>
                <Text style={s.panelTitle}>Competiciones</Text>
                <Text style={s.panelLink}>Ver todas ›</Text>
              </View>
              <View style={s.trophyRow}>
                <TrophyCard image={trophyLiga} title="Liga AJPA" meta="Temporada 2" active />
                <TrophyCard image={trophyChampions} title="Champions AJPA" meta="Fase inicial" active />
                <TrophyCard image={trophyEuropa} title="Europa AJPA" meta="Próxima fase" />
              </View>
            </View>

            <View style={s.previewNote}>
              <Text style={s.previewNoteTitle}>AJPA UI LAB · V1</Text>
              <Text style={s.previewNoteText}>Vista seleccionada: {selectedLabel}. Esta APK es solo de diseño y no toca la app oficial.</Text>
            </View>
          </ScrollView>

          <View style={s.bottomNav}>
            {[
              ['home', '⌂', 'Inicio'],
              ['market', '⇄', 'Mercado'],
              ['club', '◇', 'Mi Club'],
              ['league', '▥', 'Liga'],
              ['cups', '♕', 'Copas'],
              ['more', '•••', 'Más'],
            ].map(([key, icon, label]) => {
              const on = active === key || (key === 'more' && ['profile', 'staff'].includes(active));
              return (
                <Pressable key={key} onPress={() => setActive(key)} style={s.navItem}>
                  <Text style={[s.navIcon, on && s.navOn]}>{icon}</Text>
                  <Text style={[s.navLabel, on && s.navOn]}>{label}</Text>
                </Pressable>
              );
            })}
          </View>
        </View>
      </ImageBackground>
    </View>
  );
}

const s = StyleSheet.create({
  root: { flex: 1, backgroundColor: '#06111d' },
  background: { flex: 1, backgroundColor: '#06111d' },
  darkLayer: { flex: 1, backgroundColor: 'rgba(3,12,21,0.88)' },
  content: { paddingHorizontal: 14, paddingTop: 12, paddingBottom: 104 },
  header: { minHeight: 92, flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingHorizontal: 4 },
  brandRow: { flexDirection: 'row', alignItems: 'center' },
  logo: { width: 66, height: 66, marginRight: 10 },
  brand: { color: '#f7fbff', fontSize: 34, fontWeight: '900', letterSpacing: 1.5, lineHeight: 35 },
  brandSub: { color: '#52b7f5', fontSize: 8.5, fontWeight: '900', letterSpacing: 2.1, lineHeight: 12 },
  userArea: { alignItems: 'flex-end', gap: 7 },
  bell: { width: 28, height: 28, alignItems: 'center', justifyContent: 'center' },
  bellText: { color: '#eef7ff', fontSize: 24, transform: [{ rotate: '45deg' }] },
  notifyDot: { position: 'absolute', right: 1, top: 1, width: 8, height: 8, borderRadius: 4, backgroundColor: '#39b7ff' },
  userLine: { flexDirection: 'row', alignItems: 'center' },
  hello: { color: '#dce9f3', fontSize: 11, fontWeight: '700' },
  userClub: { color: '#8da0b1', fontSize: 10 },
  userArrow: { color: '#46b8ff', fontSize: 24, marginLeft: 8, marginTop: -1 },

  hero: { minHeight: 224, borderRadius: 23, overflow: 'hidden', backgroundColor: '#0b1723', borderWidth: 1, padding: 20, marginTop: 5 },
  heroGlowA: { position: 'absolute', width: 300, height: 220, borderRadius: 160, right: -85, top: -80, opacity: 0.32 },
  heroGlowB: { position: 'absolute', width: 240, height: 180, borderRadius: 130, left: -100, bottom: -90, opacity: 0.32 },
  heroBadgeGhost: { position: 'absolute', right: 6, top: 32 },
  heroEyebrow: { fontSize: 10, fontWeight: '900', letterSpacing: 2.1, marginBottom: 10 },
  heroTitle: { color: '#f8fbff', fontSize: 30, lineHeight: 32, fontWeight: '900' },
  heroTitleAccent: { fontSize: 27, lineHeight: 31, fontWeight: '900' },
  heroBottom: { marginTop: 26, flexDirection: 'row', alignItems: 'center' },
  heroInfoLabel: { color: '#8ea0ae', fontSize: 8, fontWeight: '900', letterSpacing: 1 },
  heroInfoValue: { color: '#edf5fb', fontSize: 12, fontWeight: '800', marginTop: 4 },
  heroDivider: { width: 1, height: 34, backgroundColor: 'rgba(180,211,232,0.22)', marginHorizontal: 20 },
  marketOpen: { color: '#4be27d', fontSize: 13, fontWeight: '900', marginTop: 3 },

  statusRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 7, marginTop: 10, marginBottom: 11 },
  pill: { flexDirection: 'row', alignItems: 'center', gap: 6, minHeight: 27, paddingHorizontal: 9, borderRadius: 9, borderWidth: 1, borderColor: '#23394a', backgroundColor: 'rgba(10,26,39,0.84)' },
  pillActive: { borderColor: '#2d607e' },
  pillDot: { width: 6, height: 6, borderRadius: 3, backgroundColor: '#63717d' },
  pillDotActive: { backgroundColor: '#35baff' },
  pillText: { color: '#8f9eaa', fontSize: 8.5, fontWeight: '800' },
  pillTextActive: { color: '#ccecff' },

  menuGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: 9 },
  menuCard: { width: '31.7%', minHeight: 154, borderRadius: 17, backgroundColor: 'rgba(14,31,45,0.92)', borderWidth: 1, borderColor: '#20384a', padding: 12, overflow: 'hidden' },
  pressed: { opacity: 0.76, transform: [{ scale: 0.985 }] },
  menuIcon: { width: 43, height: 43, borderRadius: 11, alignItems: 'center', justifyContent: 'center', marginBottom: 10 },
  menuIconText: { color: '#ffffff', fontSize: 24, fontWeight: '800' },
  menuTitle: { color: '#f6f9fb', fontSize: 15, fontWeight: '900' },
  menuSub: { color: '#98a7b3', fontSize: 9.5, lineHeight: 14, marginTop: 4 },
  menuArrow: { position: 'absolute', right: 9, bottom: 8, color: '#3fb9ff', fontSize: 21 },

  twoCol: { flexDirection: 'row', gap: 9, marginTop: 11 },
  panel: { borderRadius: 17, backgroundColor: 'rgba(10,25,38,0.94)', borderWidth: 1, borderColor: '#20384a', padding: 11 },
  newsPanel: { width: '45%' },
  tablePanel: { flex: 1 },
  panelHeader: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 9 },
  panelTitle: { color: '#f5f9fc', fontSize: 12, fontWeight: '900' },
  panelLink: { color: '#43b9ff', fontSize: 8.5, fontWeight: '700' },
  newsVisual: { height: 73, borderRadius: 10, backgroundColor: '#112b40', overflow: 'hidden', alignItems: 'center', justifyContent: 'center' },
  newsVisualGlow: { position: 'absolute', width: 150, height: 90, borderRadius: 75, backgroundColor: '#208ed0', opacity: 0.22 },
  newsLogo: { width: 52, height: 52, opacity: 0.85 },
  newsTag: { position: 'absolute', left: 8, top: 7, color: '#a9ddff', fontSize: 8, fontWeight: '900', borderWidth: 1, borderColor: '#327ba8', paddingHorizontal: 5, paddingVertical: 2, borderRadius: 4 },
  newsTitle: { color: '#f1f6f9', fontSize: 12, lineHeight: 15, fontWeight: '900', marginTop: 8 },
  newsBody: { color: '#97a7b3', fontSize: 8.7, lineHeight: 12, marginTop: 4 },
  newsMeta: { color: '#7d8c99', fontSize: 8, marginTop: 6 },

  tableHead: { flexDirection: 'row', paddingBottom: 4, borderBottomWidth: 1, borderBottomColor: '#1c3445' },
  th: { color: '#768998', fontSize: 7.5, fontWeight: '800' },
  tableRow: { minHeight: 29, flexDirection: 'row', alignItems: 'center', borderBottomWidth: 1, borderBottomColor: 'rgba(30,53,70,0.72)' },
  tdRank: { color: '#dfe9ef', fontSize: 8.5, fontWeight: '900' },
  clubCell: { flex: 1, flexDirection: 'row', alignItems: 'center', gap: 5, minWidth: 0 },
  tdClub: { flex: 1, color: '#e9f0f5', fontSize: 7.8, fontWeight: '700' },
  td: { color: '#c0ccd5', fontSize: 8, textAlign: 'right' },
  tdPts: { color: '#f6fbff', fontSize: 8.5, fontWeight: '900', textAlign: 'right' },

  competitions: { marginTop: 11, borderRadius: 17, backgroundColor: 'rgba(10,25,38,0.94)', borderWidth: 1, borderColor: '#20384a', padding: 11 },
  trophyRow: { flexDirection: 'row', gap: 7 },
  trophyCard: { flex: 1, minHeight: 91, borderRadius: 12, backgroundColor: '#102638', borderWidth: 1, borderColor: '#234056', padding: 8, flexDirection: 'row', gap: 7, alignItems: 'center' },
  trophyImageWrap: { width: 38, height: 58, borderRadius: 8, backgroundColor: '#0a1925', alignItems: 'center', justifyContent: 'center', overflow: 'hidden' },
  trophyImage: { width: 34, height: 52 },
  trophyTitle: { color: '#f1f6f9', fontSize: 9.5, fontWeight: '900' },
  trophyMeta: { color: '#8fa0ad', fontSize: 7.5, marginTop: 3 },
  trophyState: { flexDirection: 'row', gap: 4, alignItems: 'center', marginTop: 8 },
  trophyDot: { width: 6, height: 6, borderRadius: 3, backgroundColor: '#677580' },
  trophyDotActive: { backgroundColor: '#33b9ff' },
  trophyStateText: { color: '#7f8d98', fontSize: 7.2, fontWeight: '700' },
  trophyStateTextActive: { color: '#56c5ff' },

  previewNote: { marginTop: 11, borderRadius: 13, padding: 11, borderWidth: 1, borderColor: '#1f3a4e', backgroundColor: 'rgba(4,14,23,0.76)' },
  previewNoteTitle: { color: '#46baff', fontSize: 8.5, letterSpacing: 1.2, fontWeight: '900' },
  previewNoteText: { color: '#8fa0ac', fontSize: 8.5, lineHeight: 12, marginTop: 4 },

  bottomNav: { position: 'absolute', left: 0, right: 0, bottom: 0, height: 72, paddingHorizontal: 8, backgroundColor: 'rgba(5,16,26,0.98)', borderTopWidth: 1, borderTopColor: '#1b3447', flexDirection: 'row', alignItems: 'center', justifyContent: 'space-around' },
  navItem: { flex: 1, alignItems: 'center', justifyContent: 'center', height: 62 },
  navIcon: { color: '#8fa0ad', fontSize: 20, fontWeight: '900', lineHeight: 23 },
  navLabel: { color: '#8798a5', fontSize: 8.5, fontWeight: '700', marginTop: 2 },
  navOn: { color: '#40baff' },
});
