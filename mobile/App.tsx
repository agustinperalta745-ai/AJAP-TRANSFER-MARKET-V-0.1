import React, { useEffect, useMemo, useState } from 'react';
import {
  ActivityIndicator,
  Image,
  ImageBackground,
  Pressable,
  RefreshControl,
  ScrollView,
  StatusBar,
  StyleSheet,
  Text,
  View,
} from 'react-native';

type Section = 'Inicio' | 'Mercado' | 'Mi Club' | 'Liga' | 'Copas' | 'Más';
type Standing = { team: string; pj: number; pts: number };
type Snapshot = {
  status?: { market_open?: boolean; season?: { name?: string } | null };
  clubs?: Array<{ name: string }>;
  market?: unknown[];
  free_agents?: unknown[];
};

const API_URL = 'https://site--ajap-transfer-market-v-01--hkzlw9zsgh25.code.run';

const P = {
  bg: '#06111B',
  panel: '#0D2232',
  panel2: '#102A3D',
  border: '#21435B',
  white: '#F5FAFE',
  muted: '#91A6B6',
  blue: '#35A7FF',
  blue2: '#78C8FF',
  green: '#3DDA7A',
  red: '#F26470',
};

const BADGES: Record<string, any> = {
  ajax: require('../assets/teams/ajax.png'),
  as_monaco: require('../assets/teams/as_monaco.png'),
  aston_villa: require('../assets/teams/aston_villa.png'),
  atletico_madrid: require('../assets/teams/atletico_madrid.png'),
  benfica: require('../assets/teams/benfica.png'),
  bolton_wanderers: require('../assets/teams/bolton_wanderers.png'),
  everton: require('../assets/teams/everton.png'),
  feyenoord: require('../assets/teams/feyenoord.png'),
  fiorentina: require('../assets/teams/fiorentina.png'),
  fulham: require('../assets/teams/fulham.png'),
  galatasaray: require('../assets/teams/galatasaray.png'),
  lazio: require('../assets/teams/lazio.png'),
  manchester_city: require('../assets/teams/manchester_city.png'),
  middlesbrough: require('../assets/teams/middlesbrough.png'),
  olympique_lyon: require('../assets/teams/olympique_lyon.png'),
  olympique_marseille: require('../assets/teams/olympique_marseille.png'),
  porto: require('../assets/teams/porto.png'),
  psg: require('../assets/teams/psg.png'),
  real_betis: require('../assets/teams/real_betis.png'),
  sevilla: require('../assets/teams/sevilla.png'),
  torino: require('../assets/teams/torino.png'),
  tottenham_hotspur: require('../assets/teams/tottenham_hotspur.png'),
  villarreal: require('../assets/teams/villarreal.png'),
  west_ham_united: require('../assets/teams/west_ham_united.png'),
  zaragoza: require('../assets/teams/zaragoza.png'),
};

const normalize = (value: string) =>
  value.normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim();

const ALIASES: Record<string, string> = {
  ajax: 'ajax',
  'as monaco': 'as_monaco',
  monaco: 'as_monaco',
  'aston villa': 'aston_villa',
  'atletico madrid': 'atletico_madrid',
  'atletico de madrid': 'atletico_madrid',
  benfica: 'benfica',
  'bolton wanderers': 'bolton_wanderers',
  bolton: 'bolton_wanderers',
  everton: 'everton',
  feyenoord: 'feyenoord',
  fiorentina: 'fiorentina',
  fulham: 'fulham',
  galatasaray: 'galatasaray',
  lazio: 'lazio',
  'manchester city': 'manchester_city',
  'man city': 'manchester_city',
  middlesbrough: 'middlesbrough',
  'olympique lyon': 'olympique_lyon',
  'olympique de lyon': 'olympique_lyon',
  lyon: 'olympique_lyon',
  'olympique marseille': 'olympique_marseille',
  'olympique de marseille': 'olympique_marseille',
  'olympique de marsella': 'olympique_marseille',
  marseille: 'olympique_marseille',
  marsella: 'olympique_marseille',
  porto: 'porto',
  'fc porto': 'porto',
  psg: 'psg',
  'paris saint germain': 'psg',
  'real betis': 'real_betis',
  betis: 'real_betis',
  sevilla: 'sevilla',
  torino: 'torino',
  'tottenham hotspur': 'tottenham_hotspur',
  tottenham: 'tottenham_hotspur',
  villarreal: 'villarreal',
  'west ham united': 'west_ham_united',
  'west ham': 'west_ham_united',
  zaragoza: 'zaragoza',
  'real zaragoza': 'zaragoza',
};

const badgeFor = (team: string) => BADGES[ALIASES[normalize(team)] || ''];

const MENU: Array<{ key: Section; glyph: string; title: string; subtitle: string; tone: string }> = [
  { key: 'Mercado', glyph: '↔', title: 'Mercado', subtitle: 'Fichajes, ofertas\ny negociaciones', tone: '#1F7FD0' },
  { key: 'Mi Club', glyph: '◇', title: 'Mi Club', subtitle: 'Plantel, tácticas\ny gestión', tone: '#198F69' },
  { key: 'Liga', glyph: '≡', title: 'Liga', subtitle: 'Tabla, partidos\ny estadísticas', tone: '#355FB8' },
  { key: 'Copas', glyph: '⌑', title: 'Copas', subtitle: 'Torneos nacionales\ne internacionales', tone: '#98711E' },
  { key: 'Más', glyph: '○', title: 'Perfil', subtitle: 'Historial, logros\ny rendimiento', tone: '#6046A2' },
  { key: 'Más', glyph: '••', title: 'Staff / Admin', subtitle: 'Gestión de liga\ny herramientas', tone: '#526577' },
];

const BOTTOM: Array<{ key: Section; glyph: string; label: string }> = [
  { key: 'Inicio', glyph: '⌂', label: 'Inicio' },
  { key: 'Mercado', glyph: '↔', label: 'Mercado' },
  { key: 'Mi Club', glyph: '◇', label: 'Mi Club' },
  { key: 'Liga', glyph: '≡', label: 'Liga' },
  { key: 'Copas', glyph: '⌑', label: 'Copas' },
  { key: 'Más', glyph: '••', label: 'Más' },
];

async function fetchJson(path: string) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 7000);
  try {
    const response = await fetch(API_URL + path, { signal: controller.signal });
    if (!response.ok) throw new Error(String(response.status));
    return await response.json();
  } finally {
    clearTimeout(timer);
  }
}

function IconTile({ glyph, tone, small = false }: { glyph: string; tone: string; small?: boolean }) {
  return (
    <View style={[s.iconTile, small && s.iconTileSmall, { backgroundColor: tone }]}>
      <Text style={[s.iconGlyph, small && s.iconGlyphSmall]}>{glyph}</Text>
    </View>
  );
}

export default function App() {
  const [selected, setSelected] = useState<Section>('Inicio');
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [standings, setStandings] = useState<Standing[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [online, setOnline] = useState(false);

  const load = async (manual = false) => {
    manual ? setRefreshing(true) : setLoading(true);
    try {
      const [snap, league] = await Promise.all([
        fetchJson('/api/v1/snapshot'),
        fetchJson('/api/v1/league').catch(() => ({ standings: [] })),
      ]);
      setSnapshot(snap as Snapshot);
      setStandings(Array.isArray(league?.standings) ? league.standings.slice(0, 5) : []);
      setOnline(true);
    } catch {
      setOnline(false);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  useEffect(() => { void load(); }, []);

  const season = snapshot?.status?.season?.name || 'TEMPORADA 2';
  const marketOpen = Boolean(snapshot?.status?.market_open);
  const clubs = snapshot?.clubs?.length || 24;
  const published = snapshot?.market?.length || 0;

  const top = useMemo(
    () => standings.length ? standings : [
      { team: 'Olympique Marseille', pj: 0, pts: 0 },
      { team: 'Fulham', pj: 0, pts: 0 },
      { team: 'Ajax', pj: 0, pts: 0 },
      { team: 'AS Monaco', pj: 0, pts: 0 },
      { team: 'Porto', pj: 0, pts: 0 },
    ],
    [standings],
  );

  return (
    <View style={s.root}>
      <StatusBar barStyle="light-content" backgroundColor={P.bg} translucent={false} />

      <ScrollView
        style={s.scroll}
        contentContainerStyle={s.content}
        showsVerticalScrollIndicator={false}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => void load(true)} tintColor={P.blue} colors={[P.blue]} />}
      >
        <View style={s.header}>
          <View style={s.brandMark}><Text style={s.brandMarkText}>AJ</Text></View>
          <View style={s.brandCopy}>
            <Text style={s.brand}>AJPA</Text>
            <Text style={s.brandSub}>ASOCIACIÓN DE JUGADORES DE PES ARGENTINA</Text>
          </View>
          <View style={[s.liveDot, { backgroundColor: online ? P.green : P.red }]} />
        </View>

        <View style={s.helloRow}>
          <View>
            <Text style={s.hello}>Hola, DT</Text>
            <Text style={s.helloSub}>{online ? 'Conectado a AJPA' : 'Vista local · reconectando'}</Text>
          </View>
          {loading ? <ActivityIndicator color={P.blue} size="small" /> : <Text style={s.chevronTop}>›</Text>}
        </View>

        <ImageBackground
          source={require('../assets/ajpa-hero-neutral.jpg')}
          resizeMode="cover"
          style={s.hero}
          imageStyle={s.heroImage}
        >
          <View style={s.heroShade} />
          <View style={s.heroContent}>
            <Text style={s.heroEyebrow}>{season.toUpperCase()}</Text>
            <Text style={s.heroTitle}>La pasión{'
'}sigue en <Text style={s.heroBlue}>AJPA</Text></Text>

            <View style={s.heroMetaRow}>
              <View style={s.heroMeta}>
                <Text style={s.metaSymbol}>□</Text>
                <View>
                  <Text style={s.metaSmall}>Temporada oficial</Text>
                  <Text style={s.metaStrong}>En curso</Text>
                </View>
              </View>
              <View style={s.metaDivider} />
              <View style={s.heroMeta}>
                <Text style={[s.metaSymbol, { color: marketOpen ? P.green : P.red }]}>↔</Text>
                <View>
                  <Text style={s.metaSmall}>Mercado</Text>
                  <Text style={[s.metaStrong, { color: marketOpen ? P.green : P.red }]}>{marketOpen ? 'ABIERTO' : 'CERRADO'}</Text>
                </View>
              </View>
            </View>
          </View>
        </ImageBackground>

        <View style={s.quickStrip}>
          <View style={s.quickStat}><Text style={s.quickValue}>{clubs}</Text><Text style={s.quickLabel}>CLUBES</Text></View>
          <View style={s.quickDivider} />
          <View style={s.quickStat}><Text style={s.quickValue}>{published}</Text><Text style={s.quickLabel}>PUBLICADOS</Text></View>
          <View style={s.quickDivider} />
          <View style={s.quickStat}><Text style={[s.quickValue, { color: online ? P.green : P.red }]}>{online ? 'LIVE' : 'OFF'}</Text><Text style={s.quickLabel}>DATOS</Text></View>
        </View>

        <View style={s.menuGrid}>
          {MENU.map((item, index) => (
            <Pressable
              key={item.title}
              onPress={() => setSelected(item.key)}
              style={({ pressed }) => [s.menuCard, pressed && s.pressed, selected === item.key && s.menuCardActive]}
            >
              <IconTile glyph={item.glyph} tone={item.tone} />
              <Text style={s.menuTitle}>{item.title}</Text>
              <Text style={s.menuSubtitle}>{item.subtitle}</Text>
              <Text style={s.menuChevron}>›</Text>
            </Pressable>
          ))}
        </View>

        <View style={s.dualRow}>
          <View style={s.newsCard}>
            <View style={s.sectionHeader}>
              <Text style={s.sectionTitle}>Noticias AJPA</Text>
              <Text style={s.link}>Ver todas ›</Text>
            </View>
            <View style={s.newsVisual}>
              <View style={s.newsGlow} />
              <Text style={s.newsBadge}>AJPA</Text>
              <Text style={s.newsVisualMark}>PES 6</Text>
            </View>
            <Text style={s.newsTitle}>Nueva etapa, misma competencia</Text>
            <Text style={s.newsText}>Mercado, Liga y Copas en una experiencia más clara y moderna.</Text>
            <Text style={s.newsTime}>○ Ahora</Text>
          </View>

          <View style={s.tableCard}>
            <View style={s.sectionHeader}>
              <Text style={s.sectionTitle}>Tabla</Text>
              <Text style={s.link}>Ver tabla ›</Text>
            </View>
            <View style={s.tableHead}>
              <Text style={[s.th, { width: 18 }]}>#</Text>
              <Text style={[s.th, { flex: 1 }]}>Club</Text>
              <Text style={[s.th, { width: 22, textAlign: 'right' }]}>PJ</Text>
              <Text style={[s.th, { width: 30, textAlign: 'right' }]}>PTS</Text>
            </View>

            {top.map((row, index) => {
              const source = badgeFor(row.team);
              return (
                <View key={row.team + index} style={s.tableRow}>
                  <Text style={[s.rank, { width: 18 }]}>{index + 1}</Text>
                  <View style={s.clubCell}>
                    {source ? <Image source={source} style={s.badge} resizeMode="contain" /> : <View style={s.badgeFallback}><Text style={s.badgeFallbackText}>{row.team.slice(0, 1)}</Text></View>}
                    <Text numberOfLines={1} style={s.clubName}>{row.team}</Text>
                  </View>
                  <Text style={s.stat}>{row.pj}</Text>
                  <Text style={[s.stat, s.points]}>{row.pts}</Text>
                </View>
              );
            })}
          </View>
        </View>

        <View style={s.competitions}>
          <View style={s.sectionHeader}>
            <Text style={s.sectionTitle}>Competencias</Text>
            <Text style={s.link}>Ver todas ›</Text>
          </View>
          <View style={s.competitionRow}>
            <View style={s.compCard}><IconTile glyph="≡" tone="#173C5B" small /><Text style={s.compTitle}>Liga AJPA</Text><Text style={s.compSub}>{season}</Text><Text style={s.compLive}>● En curso</Text></View>
            <View style={s.compCard}><IconTile glyph="⌑" tone="#6D531D" small /><Text style={s.compTitle}>Copa Libertador</Text><Text style={s.compSub}>Principal</Text><Text style={s.compMuted}>● Próxima fase</Text></View>
            <View style={s.compCard}><IconTile glyph="◇" tone="#42366A" small /><Text style={s.compTitle}>Copa Regional</Text><Text style={s.compSub}>Internacional</Text><Text style={s.compLive}>● En curso</Text></View>
          </View>
        </View>

        <View style={s.previewNote}>
          <Text style={s.previewNoteTitle}>UI LAB · BASE ESTABLE</Text>
          <Text style={s.previewNoteText}>Diseño completo reconstruido sobre la APK que sí abrió. La capa nativa segura se mantiene sin OTA, Secure Store, Safe Area ni New Architecture.</Text>
        </View>
      </ScrollView>

      <View style={s.bottomNav}>
        {BOTTOM.map(item => {
          const active = selected === item.key;
          return (
            <Pressable key={item.label} onPress={() => setSelected(item.key)} style={s.bottomItem}>
              <Text style={[s.bottomGlyph, active && s.bottomActive]}>{item.glyph}</Text>
              <Text style={[s.bottomLabel, active && s.bottomActive]}>{item.label}</Text>
            </Pressable>
          );
        })}
      </View>
    </View>
  );
}

const s = StyleSheet.create({
  root: { flex: 1, backgroundColor: P.bg },
  scroll: { flex: 1 },
  content: { paddingHorizontal: 16, paddingTop: 10, paddingBottom: 106 },

  header: { flexDirection: 'row', alignItems: 'center', marginBottom: 8 },
  brandMark: { width: 60, height: 60, borderRadius: 20, borderWidth: 1.5, borderColor: P.blue, backgroundColor: '#0A1B29', alignItems: 'center', justifyContent: 'center' },
  brandMarkText: { color: P.white, fontSize: 21, fontWeight: '900', letterSpacing: 1 },
  brandCopy: { flex: 1, marginLeft: 12 },
  brand: { color: P.white, fontSize: 33, lineHeight: 35, fontWeight: '900', letterSpacing: 1.2 },
  brandSub: { color: P.blue2, fontSize: 7.7, fontWeight: '800', letterSpacing: 1.8, marginTop: 3 },
  liveDot: { width: 8, height: 8, borderRadius: 8, marginLeft: 8 },

  helloRow: { alignSelf: 'flex-end', minWidth: 148, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', backgroundColor: '#0A1D2C', borderWidth: 1, borderColor: P.border, borderRadius: 14, paddingVertical: 8, paddingHorizontal: 11, marginBottom: 12 },
  hello: { color: P.white, fontSize: 12, fontWeight: '800' },
  helloSub: { color: P.muted, fontSize: 9.5, marginTop: 1 },
  chevronTop: { color: P.blue, fontSize: 21 },

  hero: { minHeight: 245, borderRadius: 21, overflow: 'hidden', borderWidth: 1, borderColor: '#2B5B79', justifyContent: 'flex-end', backgroundColor: '#0A1925' },
  heroImage: { borderRadius: 21 },
  heroShade: { ...StyleSheet.absoluteFillObject, backgroundColor: 'rgba(2,10,17,0.52)' },
  heroContent: { paddingHorizontal: 19, paddingVertical: 18 },
  heroEyebrow: { color: P.blue2, fontSize: 10, fontWeight: '900', letterSpacing: 2.2, marginBottom: 7 },
  heroTitle: { color: P.white, fontSize: 31, lineHeight: 33, fontWeight: '900', letterSpacing: -0.5 },
  heroBlue: { color: P.blue },
  heroMetaRow: { flexDirection: 'row', alignItems: 'center', marginTop: 20 },
  heroMeta: { flex: 1, flexDirection: 'row', alignItems: 'center' },
  metaSymbol: { color: P.white, fontSize: 25, fontWeight: '900', marginRight: 9 },
  metaSmall: { color: '#C0CED8', fontSize: 9.5 },
  metaStrong: { color: P.white, fontSize: 12.5, fontWeight: '900', marginTop: 2 },
  metaDivider: { width: 1, height: 34, backgroundColor: 'rgba(255,255,255,0.22)', marginHorizontal: 12 },

  quickStrip: { marginTop: 10, flexDirection: 'row', alignItems: 'center', borderRadius: 16, borderWidth: 1, borderColor: P.border, backgroundColor: '#0A1D2C', paddingVertical: 10 },
  quickStat: { flex: 1, alignItems: 'center' },
  quickValue: { color: P.white, fontSize: 14, fontWeight: '900' },
  quickLabel: { color: P.muted, fontSize: 7.5, fontWeight: '800', letterSpacing: 1.1, marginTop: 2 },
  quickDivider: { width: 1, height: 26, backgroundColor: P.border },

  menuGrid: { flexDirection: 'row', flexWrap: 'wrap', justifyContent: 'space-between', marginTop: 12 },
  menuCard: { width: '48.5%', minHeight: 146, borderRadius: 19, borderWidth: 1, borderColor: P.border, backgroundColor: P.panel, padding: 14, marginBottom: 10 },
  menuCardActive: { borderColor: '#2C8FD3' },
  pressed: { opacity: 0.75 },
  iconTile: { width: 49, height: 49, borderRadius: 14, alignItems: 'center', justifyContent: 'center' },
  iconTileSmall: { width: 34, height: 34, borderRadius: 10, marginBottom: 7 },
  iconGlyph: { color: P.white, fontSize: 23, fontWeight: '900' },
  iconGlyphSmall: { fontSize: 17 },
  menuTitle: { color: P.white, fontSize: 17, fontWeight: '900', marginTop: 11 },
  menuSubtitle: { color: P.muted, fontSize: 10.5, lineHeight: 15, marginTop: 4, paddingRight: 12 },
  menuChevron: { position: 'absolute', right: 12, top: 72, color: P.blue, fontSize: 23, fontWeight: '900' },

  dualRow: { flexDirection: 'row', marginTop: 2 },
  newsCard: { flex: 1, minHeight: 280, borderRadius: 18, backgroundColor: P.panel, borderWidth: 1, borderColor: P.border, padding: 11, marginRight: 5 },
  tableCard: { flex: 1, minHeight: 280, borderRadius: 18, backgroundColor: P.panel, borderWidth: 1, borderColor: P.border, padding: 11, marginLeft: 5 },
  sectionHeader: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 9 },
  sectionTitle: { color: P.white, fontSize: 13.5, fontWeight: '900' },
  link: { color: P.blue2, fontSize: 8.5, fontWeight: '800' },

  newsVisual: { height: 92, borderRadius: 13, overflow: 'hidden', backgroundColor: '#0B1C29', borderWidth: 1, borderColor: '#1F4E6B', marginBottom: 9, justifyContent: 'center', alignItems: 'center' },
  newsGlow: { position: 'absolute', width: 150, height: 150, borderRadius: 90, backgroundColor: 'rgba(38,145,220,0.18)' },
  newsBadge: { position: 'absolute', left: 8, top: 8, color: P.blue2, fontSize: 8.5, fontWeight: '900', letterSpacing: 1.3 },
  newsVisualMark: { color: P.white, fontSize: 22, fontWeight: '900', letterSpacing: 1.5 },
  newsTitle: { color: P.white, fontSize: 12.5, lineHeight: 16, fontWeight: '900' },
  newsText: { color: P.muted, fontSize: 9, lineHeight: 13, marginTop: 4 },
  newsTime: { color: P.muted, fontSize: 8.5, marginTop: 8 },

  tableHead: { flexDirection: 'row', paddingBottom: 5, borderBottomWidth: 1, borderBottomColor: '#1F3B50' },
  th: { color: '#71899A', fontSize: 7.5, fontWeight: '800' },
  tableRow: { flexDirection: 'row', alignItems: 'center', minHeight: 36, borderBottomWidth: 1, borderBottomColor: '#183247' },
  rank: { color: P.white, fontSize: 9.5, fontWeight: '800' },
  clubCell: { flex: 1, minWidth: 0, flexDirection: 'row', alignItems: 'center' },
  badge: { width: 19, height: 19, marginRight: 5 },
  badgeFallback: { width: 19, height: 19, borderRadius: 7, backgroundColor: '#173C56', alignItems: 'center', justifyContent: 'center', marginRight: 5 },
  badgeFallbackText: { color: P.blue2, fontSize: 8, fontWeight: '900' },
  clubName: { color: '#D8E4EC', fontSize: 8.8, flex: 1 },
  stat: { color: '#B4C3CE', fontSize: 8.5, width: 22, textAlign: 'right' },
  points: { color: P.white, fontWeight: '900', width: 30 },

  competitions: { marginTop: 10, borderRadius: 18, backgroundColor: P.panel, borderWidth: 1, borderColor: P.border, padding: 11 },
  competitionRow: { flexDirection: 'row' },
  compCard: { flex: 1, minHeight: 116, padding: 9, borderRadius: 14, backgroundColor: P.panel2, borderWidth: 1, borderColor: '#1D4056', marginHorizontal: 3 },
  compTitle: { color: P.white, fontSize: 10, fontWeight: '900' },
  compSub: { color: P.muted, fontSize: 8, lineHeight: 11, marginTop: 3 },
  compLive: { color: P.blue2, fontSize: 7.5, marginTop: 6, fontWeight: '800' },
  compMuted: { color: '#8C9EAB', fontSize: 7.5, marginTop: 6, fontWeight: '800' },

  previewNote: { marginTop: 10, padding: 13, borderRadius: 16, backgroundColor: '#0A1E2D', borderWidth: 1, borderColor: '#1D4D6C' },
  previewNoteTitle: { color: P.blue2, fontSize: 8.5, fontWeight: '900', letterSpacing: 1.4 },
  previewNoteText: { color: '#B1C2CE', fontSize: 9.5, lineHeight: 14, marginTop: 5 },

  bottomNav: { position: 'absolute', left: 0, right: 0, bottom: 0, height: 80, flexDirection: 'row', alignItems: 'center', backgroundColor: '#07141F', borderTopWidth: 1, borderTopColor: '#19384D', paddingBottom: 6 },
  bottomItem: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  bottomGlyph: { color: '#788D9C', fontSize: 19, fontWeight: '900' },
  bottomLabel: { color: '#788D9C', fontSize: 8, fontWeight: '700', marginTop: 3 },
  bottomActive: { color: P.blue },
});
