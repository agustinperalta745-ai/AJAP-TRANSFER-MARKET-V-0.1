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

import { SafeAreaProvider, SafeAreaView, initialWindowMetrics } from 'react-native-safe-area-context';
import { AjpaIcon, AjpaIconName, AjpaIconTile } from './src/AjpaIcon';
import BotParityAppV2, { Screen as FunctionalScreen } from './src/BotParityAppV2';
import CupCenterFab from './src/CupCenterFab';
import SeasonHistoryFab from './src/SeasonHistoryFab';
import CompetitionCycleAdminFab from './src/CompetitionCycleAdminFab';
import { MobileProfile, fetchMe, setSessionToken } from './src/api';
import { loadStoredSession } from './src/session';

type Section = 'Inicio' | 'Mercado' | 'Mi Club' | 'Liga' | 'Copas' | 'Perfil' | 'Staff' | 'Más';
type Standing = { team: string; pj: number; pts: number };
type Scorer = { player: string; team: string; goals: number };
type SeasonCountdown = {
  configured?: boolean;
  deadline_utc?: number | null;
  deadline_local?: string | null;
  date?: string;
  time?: string;
  closed?: boolean;
};
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
  ajax: require('./assets/team_badge_hq256/ajax.png'),
  as_monaco: require('./assets/team_badge_test/as_monaco_hd.png'),
  aston_villa: require('./assets/team_badge_hq256/aston_villa.png'),
  atletico_madrid: require('./assets/team_badge_hq256/atletico_madrid.png'),
  benfica: require('./assets/team_badge_hq256/benfica.png'),
  bolton_wanderers: require('./assets/team_badge_hq256/bolton_wanderers.png'),
  everton: require('./assets/team_badge_hq256/everton.png'),
  feyenoord: require('./assets/team_badge_hq256/feyenoord.png'),
  fiorentina: require('./assets/team_badge_hq256/fiorentina.png'),
  fulham: require('./assets/team_badge_hq256/fulham.png'),
  galatasaray: require('./assets/team_badge_hq256/galatasaray.png'),
  lazio: require('./assets/team_badge_hq256/lazio.png'),
  manchester_city: require('./assets/team_badge_hq256/manchester_city.png'),
  middlesbrough: require('./assets/team_badge_hq256/middlesbrough.png'),
  olympique_lyon: require('./assets/team_badge_hq256/olympique_lyon.png'),
  olympique_marseille: require('./assets/team_badge_hq256/olympique_marseille.png'),
  porto: require('./assets/team_badge_hq256/porto.png'),
  psg: require('./assets/team_badge_hq256/psg.png'),
  real_betis: require('./assets/team_badge_hq256/real_betis.png'),
  sevilla: require('./assets/team_badge_hq256/sevilla.png'),
  tottenham_hotspur: require('./assets/team_badge_hq256/tottenham_hotspur.png'),
  villarreal: require('./assets/team_badge_hq256/villarreal.png'),
  west_ham_united: require('./assets/team_badge_hq256/west_ham_united.png'),
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

const MENU: Array<{ key: Section; icon: AjpaIconName; title: string; subtitle: string; tone: string }> = [
  { key: 'Mercado', icon: 'market', title: 'Mercado', subtitle: 'Fichajes, ofertas\ny negociaciones', tone: '#1F7FD0' },
  { key: 'Mi Club', icon: 'club', title: 'Mi Club', subtitle: 'Plantel, tácticas\ny gestión', tone: '#198F69' },
  { key: 'Liga', icon: 'league', title: 'Liga', subtitle: 'Tabla, partidos\ny estadísticas', tone: '#355FB8' },
  { key: 'Copas', icon: 'cups', title: 'Copas', subtitle: 'Torneos nacionales\ne internacionales', tone: '#98711E' },
  { key: 'Perfil', icon: 'profile', title: 'Perfil', subtitle: 'Historial, logros\ny rendimiento', tone: '#6046A2' },
  { key: 'Staff', icon: 'admin', title: 'Staff / Admin', subtitle: 'Gestión de liga\ny herramientas', tone: '#526577' },
];

const BOTTOM: Array<{ key: Section; icon: AjpaIconName; label: string }> = [
  { key: 'Inicio', icon: 'home', label: 'Inicio' },
  { key: 'Mercado', icon: 'market', label: 'Mercado' },
  { key: 'Mi Club', icon: 'club', label: 'Mi Club' },
  { key: 'Liga', icon: 'league', label: 'Liga' },
  { key: 'Copas', icon: 'cups', label: 'Copas' },
  { key: 'Más', icon: 'more', label: 'Más' },
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

export default function App() {
  const [selected, setSelected] = useState<Section>('Inicio');
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [standings, setStandings] = useState<Standing[]>([]);
  const [scorers, setScorers] = useState<Scorer[]>([]);
  const [newsWidth, setNewsWidth] = useState(0);
  const [statsWidth, setStatsWidth] = useState(0);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [online, setOnline] = useState(false);
  const [seasonCountdown, setSeasonCountdown] = useState<SeasonCountdown | null>(null);
  const [profile, setProfile] = useState<MobileProfile | null>(null);
  const [now, setNow] = useState(Date.now());

  const load = async (manual = false) => {
    manual ? setRefreshing(true) : setLoading(true);
    try {
      const [snap, league, countdown] = await Promise.all([
        fetchJson('/api/v1/snapshot'),
        fetchJson('/api/v1/league').catch(() => ({ standings: [], scorers: [] })),
        fetchJson('/api/v1/season-countdown').catch(() => null),
      ]);
      setSnapshot(snap as Snapshot);
      setStandings(Array.isArray(league?.standings) ? league.standings : []);
      setScorers(Array.isArray(league?.scorers) ? [...league.scorers].sort((a: Scorer, b: Scorer) => b.goals - a.goals || a.player.localeCompare(b.player)).slice(0, 5) : []);
      setSeasonCountdown(countdown as SeasonCountdown | null);
      setNow(Date.now());
      try {
        const token = await loadStoredSession();
        setSessionToken(token);
        setProfile(token ? await fetchMe() : null);
      } catch {
        setProfile(null);
      }
      setOnline(true);
    } catch {
      setOnline(false);
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  };

  useEffect(() => { void load(); }, []);
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 30000);
    return () => clearInterval(timer);
  }, []);

  const season = snapshot?.status?.season?.name || 'TEMPORADA 2';
  const marketOpen = Boolean(snapshot?.status?.market_open);
  const countdownText = useMemo(() => {
    if (!seasonCountdown?.configured || !seasonCountdown.deadline_utc) return null;
    const remaining = Math.max(0, Math.ceil((seasonCountdown.deadline_utc * 1000 - now) / 1000));
    const dateLabel = [seasonCountdown.date, seasonCountdown.time].filter(Boolean).join(' ');
    if (remaining <= 0) return dateLabel ? `Finalizó · ${dateLabel}` : 'Temporada finalizada';
    const days = Math.floor(remaining / 86400);
    const hours = Math.floor((remaining % 86400) / 3600);
    const minutes = Math.floor((remaining % 3600) / 60);
    const left = days > 0 ? `${days}d ${hours}h ${String(minutes).padStart(2, '0')}m` : `${hours}h ${String(minutes).padStart(2, '0')}m`;
    return dateLabel ? `${left} · ${dateLabel}` : left;
  }, [seasonCountdown, now]);

  const myClub = profile?.club || '';
  const myClubDisplay = myClub || (profile?.is_staff ? 'Staff / sin club' : 'Club sin vincular');
  const myManager = profile?.user?.global_name || profile?.user?.username || 'DT sin vincular';
  const myClubRank = useMemo(() => {
    if (!myClub) return null;
    const index = standings.findIndex(row => normalize(row.team) === normalize(myClub));
    return index >= 0 ? index + 1 : null;
  }, [standings, myClub]);
  const myClubBadge = myClub ? badgeFor(myClub) : null;

  const top = useMemo(
    () => standings.length ? standings.slice(0, 5) : [
      { team: 'Olympique Marseille', pj: 0, pts: 0 },
      { team: 'Fulham', pj: 0, pts: 0 },
      { team: 'Ajax', pj: 0, pts: 0 },
      { team: 'AS Monaco', pj: 0, pts: 0 },
      { team: 'Porto', pj: 0, pts: 0 },
    ],
    [standings],
  );

  const functionalScreen: FunctionalScreen | null = selected === 'Mercado' ? 'market'
    : selected === 'Mi Club' ? 'club'
      : selected === 'Liga' ? 'league'
        : selected === 'Copas' ? 'titles'
          : selected === 'Perfil' || selected === 'Más' ? 'profile'
            : selected === 'Staff' ? 'admin'
              : null;

  const functionalTitle = selected === 'Mi Club' ? 'Mi Club'
    : selected === 'Staff' ? 'Staff / Admin'
      : selected === 'Más' ? 'Perfil'
        : selected;

  const newsItems = useMemo(() => [
    {
      badge: 'AJPA',
      mark: 'PES 6',
      title: 'Nueva etapa, misma competencia',
      text: 'Mercado, Liga y Copas en una experiencia más clara y moderna.',
    },
    {
      badge: 'MERCADO',
      mark: marketOpen ? 'ABIERTO' : 'CERRADO',
      title: marketOpen ? 'El mercado está abierto' : 'El mercado está cerrado',
      text: marketOpen
        ? 'Los DT pueden publicar jugadores, negociar y seguir los movimientos desde AJPA.'
        : 'Las operaciones quedan pausadas hasta la próxima apertura oficial.',
    },
    {
      badge: 'COMPETENCIAS',
      mark: 'AJPA',
      title: 'Liga, Champions y Europa',
      text: 'Seguí desde la app las tres competencias oficiales de la temporada.',
    },
  ], [marketOpen]);

  const mainContent = functionalScreen ? (
    <View style={s.functionalRoot}>
      <View style={s.functionalBody}>
        <BotParityAppV2 key={selected} initialScreen={functionalScreen} embedded onExit={() => setSelected('Inicio')} />
        {selected === 'Copas' ? <CupCenterFab /> : null}
        {selected === 'Liga' ? <SeasonHistoryFab /> : null}
        {selected === 'Staff' ? <CompetitionCycleAdminFab /> : null}
      </View>
    </View>
  ) : (
      <ScrollView
        style={s.scroll}
        contentContainerStyle={s.content}
        showsVerticalScrollIndicator={false}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => void load(true)} tintColor={P.blue} colors={[P.blue]} />}
      >
        <View style={s.header}>
          <Image source={require('./assets/ajpa-league-logo.png')} style={s.brandLogo} resizeMode="contain" />
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
          source={require('./assets/ajpa-hero-neutral.jpg')}
          resizeMode="cover"
          style={s.hero}
          imageStyle={s.heroImage}
        >
          <View style={s.heroShade} />
          <View style={s.heroContent}>
            <Text style={s.heroEyebrow}>{season.toUpperCase()}</Text>
            <Text style={s.heroTitle}>La pasión{'\n'}sigue en <Text style={s.heroBlue}>AJPA</Text></Text>

            <View style={s.heroMetaRow}>
              <View style={[s.heroMeta, s.heroMetaSeason]}>
                <AjpaIcon name="season" size={21} color={P.white} />
                <View>
                  <Text style={s.metaSmall}>Temporada oficial</Text>
                  <Text style={s.metaStrong}>En curso</Text>
                  {countdownText ? <Text numberOfLines={1} style={s.metaTimer}>{countdownText}</Text> : null}
                </View>
              </View>
              <View style={s.metaDivider} />
              <View style={[s.heroMeta, s.heroMetaMarket]}>
                <AjpaIcon name={marketOpen ? 'market' : 'closed'} size={21} color={marketOpen ? P.green : P.red} />
                <View>
                  <Text style={s.metaSmall}>Mercado</Text>
                  <Text style={[s.metaStrong, { color: marketOpen ? P.green : P.red }]}>{marketOpen ? 'ABIERTO' : 'CERRADO'}</Text>
                </View>
              </View>
            </View>
          </View>
        </ImageBackground>

        <View style={s.clubIdentityCard}>
          {myClubBadge ? (
            <Image source={myClubBadge} style={s.clubIdentityBadge} resizeMode="contain" />
          ) : (
            <View style={s.clubIdentityBadgeFallback}><AjpaIcon name="club" size={24} color={P.blue2} /></View>
          )}
          <View style={s.clubIdentityCopy}>
            <Text style={s.clubIdentityEyebrow}>TU CLUB</Text>
            <Text numberOfLines={1} style={s.clubIdentityName}>{myClubDisplay}</Text>
            <View style={s.clubIdentityMetaRow}>
              <Text numberOfLines={1} style={s.clubIdentityManager}>DT: {myManager}</Text>
              {myClub ? <View style={s.linkedPill}><View style={s.linkedDot} /><Text style={s.linkedText}>Vinculado</Text></View> : null}
            </View>
          </View>
          <View style={s.clubIdentityDivider} />
          <View style={s.clubIdentityPosition}>
            <Text style={s.clubIdentityPosLabel}>Pos</Text>
            <Text style={s.clubIdentityPosValue}>{myClubRank ?? '—'}</Text>
          </View>
        </View>

        <View style={s.menuGrid}>
          {MENU.map((item, index) => (
            <Pressable
              key={item.title}
              onPress={() => setSelected(item.key)}
              style={({ pressed }) => [s.menuCard, pressed && s.pressed, selected === item.key && s.menuCardActive]}
            >
              <AjpaIconTile name={item.icon} tone={item.tone} size={21} tileSize={42} />
              <Text style={s.menuTitle}>{item.title}</Text>
              <Text style={s.menuSubtitle}>{item.subtitle}</Text>
              <Text style={s.menuChevron}>›</Text>
            </Pressable>
          ))}
        </View>

        <View style={s.dualRow}>
          <View
            style={s.newsCard}
            onLayout={(event) => setNewsWidth(Math.round(event.nativeEvent.layout.width - 22))}
          >
            <View style={s.sectionHeader}>
              <Text style={s.sectionTitle}>Noticias AJPA</Text>
              <Text style={s.link}>Deslizá ›</Text>
            </View>

            <ScrollView
              horizontal
              pagingEnabled
              nestedScrollEnabled
              showsHorizontalScrollIndicator={false}
              decelerationRate="fast"
              style={s.innerCarousel}
            >
              {newsItems.map((item, index) => (
                <View key={item.title} style={[s.newsPage, newsWidth > 0 && { width: newsWidth }]}>
                  <View style={s.newsVisual}>
                    <View style={s.newsGlow} />
                    <Text style={s.newsBadge}>{item.badge}</Text>
                    <Text numberOfLines={1} style={s.newsVisualMark}>{item.mark}</Text>
                  </View>
                  <Text style={s.newsTitle}>{item.title}</Text>
                  <Text style={s.newsText}>{item.text}</Text>
                  <View style={s.carouselDots}>
                    {newsItems.map((_dot, dotIndex) => (
                      <View key={dotIndex} style={[s.carouselDot, dotIndex === index && s.carouselDotActive]} />
                    ))}
                  </View>
                </View>
              ))}
            </ScrollView>
          </View>

          <View
            style={s.tableCard}
            onLayout={(event) => setStatsWidth(Math.round(event.nativeEvent.layout.width - 20))}
          >
            <View style={s.sectionHeader}>
              <Text style={s.sectionTitle}>Tabla</Text>
              <Text style={s.link}>Deslizá ›</Text>
            </View>

            <ScrollView
              horizontal
              pagingEnabled
              nestedScrollEnabled
              showsHorizontalScrollIndicator={false}
              decelerationRate="fast"
              style={s.innerCarousel}
            >
              <View style={[s.statsPage, statsWidth > 0 && { width: statsWidth }]}>
                <View style={s.tableHead}>
                  <Text style={[s.th, s.rankCol]}>#</Text>
                  <Text style={[s.th, s.clubHeadCol]}>Club</Text>
                  <Text style={[s.th, s.pjCol]}>PJ</Text>
                  <Text style={[s.th, s.ptsCol]}>PTS</Text>
                </View>

                {top.map((row, index) => {
                  const source = badgeFor(row.team);
                  return (
                    <View key={row.team + index} style={s.tableRow}>
                      <Text style={[s.rank, s.rankCol]}>{index + 1}</Text>
                      <View style={s.clubCell}>
                        {source ? <Image source={source} style={s.badge} resizeMode="contain" /> : <View style={s.badgeFallback}><Text style={s.badgeFallbackText}>{row.team.slice(0, 1)}</Text></View>}
                        <Text numberOfLines={1} style={s.clubName}>{row.team}</Text>
                      </View>
                      <Text style={[s.stat, s.pjCol]}>{row.pj}</Text>
                      <Text style={[s.stat, s.points, s.ptsCol]}>{row.pts}</Text>
                    </View>
                  );
                })}
                <View style={s.carouselDots}>
                  <View style={[s.carouselDot, s.carouselDotActive]} />
                  <View style={s.carouselDot} />
                </View>
              </View>

              <View style={[s.statsPage, statsWidth > 0 && { width: statsWidth }]}>
                <Text style={s.scorersTitle}>Top 5 goleadores</Text>
                <View style={s.tableHead}>
                  <Text style={[s.th, s.rankCol]}>#</Text>
                  <Text style={[s.th, s.clubHeadCol]}>Jugador</Text>
                  <Text style={[s.th, s.goalsCol]}>G</Text>
                </View>

                {scorers.length > 0 ? scorers.map((row, index) => {
                  const source = badgeFor(row.team);
                  return (
                    <View key={row.player + row.team + index} style={s.scorerRow}>
                      <Text style={[s.rank, s.rankCol]}>{index + 1}</Text>
                      <View style={s.scorerCell}>
                        {source ? <Image source={source} style={s.badge} resizeMode="contain" /> : <View style={s.badgeFallback}><Text style={s.badgeFallbackText}>{row.team.slice(0, 1)}</Text></View>}
                        <View style={s.scorerCopy}>
                          <Text numberOfLines={1} style={s.scorerName}>{row.player}</Text>
                          <Text numberOfLines={1} style={s.scorerTeam}>{row.team}</Text>
                        </View>
                      </View>
                      <Text style={[s.goals, s.goalsCol]}>{row.goals}</Text>
                    </View>
                  );
                }) : (
                  <View style={s.emptyScorers}>
                    <Text style={s.emptyScorersText}>Todavía no hay goleadores cargados.</Text>
                  </View>
                )}
                <View style={s.carouselDots}>
                  <View style={s.carouselDot} />
                  <View style={[s.carouselDot, s.carouselDotActive]} />
                </View>
              </View>
            </ScrollView>
          </View>
        </View>

        <View style={s.competitions}>
          <View style={s.sectionHeader}>
            <Text style={s.sectionTitle}>Competencias</Text>
            <Text style={s.link}>Ver todas ›</Text>
          </View>
          <View style={s.competitionRow}>
            <View style={s.compCard}><AjpaIconTile name="league" tone="#173C5B" size={16} tileSize={30} /><Text style={s.compTitle}>Liga AJPA</Text><Text style={s.compSub}>{season}</Text><Text style={s.compLive}>● En curso</Text></View>
            <View style={s.compCard}><AjpaIconTile name="competitions" tone="#6D531D" size={16} tileSize={30} /><Text style={s.compTitle}>Champions AJPA</Text><Text style={s.compSub}>Internacional</Text><Text style={s.compMuted}>● Próxima fase</Text></View>
            <View style={s.compCard}><AjpaIconTile name="cups" tone="#42366A" size={16} tileSize={30} /><Text style={s.compTitle}>Europa AJPA</Text><Text style={s.compSub}>Internacional</Text><Text style={s.compLive}>● En curso</Text></View>
          </View>
        </View>

        <View style={s.previewNote}>
          <Text style={s.previewNoteTitle}>UI LAB · BASE ESTABLE</Text>
          <Text style={s.previewNoteText}>Diseño visual renovado sobre la base estable. Las funciones originales se integran dentro de la nueva navegación de AJPA.</Text>
        </View>
      </ScrollView>
  );

  return (
    <SafeAreaProvider initialMetrics={initialWindowMetrics}>
      <SafeAreaView style={s.safeRoot} edges={['top', 'bottom', 'left', 'right']}>
        <StatusBar barStyle="light-content" backgroundColor={P.bg} translucent={false} />
        <View style={s.root}>
          {mainContent}

      <View style={s.bottomNav}>
        {BOTTOM.map(item => {
          const active = item.key === 'Más'
            ? selected === 'Más' || selected === 'Perfil' || selected === 'Staff'
            : selected === item.key;
          return (
            <Pressable key={item.label} onPress={() => setSelected(item.key === 'Más' ? 'Perfil' : item.key)} style={s.bottomItem}>
              <AjpaIcon name={item.icon} size={19} color={active ? P.blue : '#788D9C'} />
              <Text style={[s.bottomLabel, active && s.bottomActive]}>{item.label}</Text>
            </Pressable>
          );
        })}
      </View>
        </View>
      </SafeAreaView>
    </SafeAreaProvider>
  );
}

const s = StyleSheet.create({
  safeRoot: { flex: 1, backgroundColor: P.bg },
  root: { flex: 1, backgroundColor: P.bg },
  functionalRoot: { flex: 1, backgroundColor: P.bg },
  functionalHeader: { height: 62, flexDirection: 'row', alignItems: 'center', paddingHorizontal: 14, borderBottomWidth: 1, borderBottomColor: P.border, backgroundColor: '#081927' },
  functionalBack: { width: 38, height: 38, borderRadius: 12, alignItems: 'center', justifyContent: 'center', borderWidth: 1, borderColor: '#24465F', backgroundColor: '#0C2232' },
  functionalBackText: { color: P.blue2, fontSize: 28, lineHeight: 30, fontWeight: '700', marginTop: -2 },
  functionalHeaderCopy: { flex: 1, minWidth: 0, marginLeft: 10 },
  functionalEyebrow: { color: P.blue2, fontSize: 7.5, fontWeight: '900', letterSpacing: 1.4 },
  functionalTitle: { color: P.white, fontSize: 17, fontWeight: '900', marginTop: 1 },
  functionalLogo: { width: 38, height: 38, borderRadius: 19 },
  functionalBody: { flex: 1 },
  scroll: { flex: 1 },
  content: { paddingHorizontal: 14, paddingTop: 12, paddingBottom: 86 },

  header: { flexDirection: 'row', alignItems: 'center', marginBottom: 8 },
  brandLogo: { width: 52, height: 52, borderRadius: 26, borderWidth: 1, borderColor: '#2D6A8E', backgroundColor: '#02070B' },
  brandCopy: { flex: 1, marginLeft: 10 },
  brand: { color: P.white, fontSize: 28, lineHeight: 30, fontWeight: '800', letterSpacing: 1 },
  brandSub: { color: P.blue2, fontSize: 7.1, fontWeight: '700', letterSpacing: 1.55, marginTop: 2 },
  liveDot: { width: 7, height: 7, borderRadius: 7, marginLeft: 6 },

  helloRow: { alignSelf: 'flex-end', minWidth: 132, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', backgroundColor: '#0A1D2C', borderWidth: 1, borderColor: P.border, borderRadius: 12, paddingVertical: 6, paddingHorizontal: 9, marginBottom: 9 },
  hello: { color: P.white, fontSize: 11, fontWeight: '700' },
  helloSub: { color: P.muted, fontSize: 8.5, marginTop: 1 },
  chevronTop: { color: P.blue, fontSize: 18 },

  hero: { minHeight: 205, borderRadius: 18, overflow: 'hidden', borderWidth: 1, borderColor: '#2B5B79', justifyContent: 'flex-end', backgroundColor: '#0A1925' },
  heroImage: { borderRadius: 18 },
  heroShade: { ...StyleSheet.absoluteFillObject, backgroundColor: 'rgba(2,10,17,0.52)' },
  heroContent: { paddingHorizontal: 16, paddingVertical: 14 },
  heroEyebrow: { color: P.blue2, fontSize: 9, fontWeight: '800', letterSpacing: 1.9, marginBottom: 6 },
  heroTitle: { color: P.white, fontSize: 27, lineHeight: 29, fontWeight: '800', letterSpacing: -0.35 },
  heroBlue: { color: P.blue },
  heroMetaRow: { flexDirection: 'row', alignItems: 'stretch', marginTop: 14 },
  heroMeta: { flex: 1, minHeight: 47, flexDirection: 'row', alignItems: 'center', justifyContent: 'center' },
  heroMetaSeason: { paddingRight: 4 },
  heroMetaMarket: { paddingLeft: 4 },
  metaSmall: { color: '#C0CED8', fontSize: 8.5, marginLeft: 7 },
  metaStrong: { color: P.white, fontSize: 11.5, fontWeight: '800', marginTop: 1, marginLeft: 7 },
  metaTimer: { color: '#93A9B8', fontSize: 6.9, fontWeight: '700', marginTop: 2, marginLeft: 7, maxWidth: 126 },
  metaDivider: { width: 1, height: 40, alignSelf: 'center', backgroundColor: 'rgba(255,255,255,0.82)', marginHorizontal: 7 },

  clubIdentityCard: { minHeight: 76, marginTop: 9, borderRadius: 16, borderWidth: 1, borderColor: '#23618A', backgroundColor: '#0A2233', flexDirection: 'row', alignItems: 'center', paddingHorizontal: 12, paddingVertical: 9 },
  clubIdentityBadge: { width: 52, height: 52, marginRight: 10 },
  clubIdentityBadgeFallback: { width: 52, height: 52, borderRadius: 16, marginRight: 10, alignItems: 'center', justifyContent: 'center', backgroundColor: '#12354B' },
  clubIdentityBadgeLetter: { color: P.blue2, fontSize: 22, fontWeight: '900' },
  clubIdentityCopy: { flex: 1, minWidth: 0 },
  clubIdentityEyebrow: { color: P.blue2, fontSize: 7.8, fontWeight: '900', letterSpacing: 1.35 },
  clubIdentityName: { color: P.white, fontSize: 14.5, fontWeight: '900', marginTop: 2 },
  clubIdentityMetaRow: { flexDirection: 'row', alignItems: 'center', marginTop: 4 },
  clubIdentityManager: { color: P.muted, fontSize: 8.5, marginRight: 8, maxWidth: 122 },
  linkedPill: { height: 20, paddingHorizontal: 7, borderRadius: 10, borderWidth: 1, borderColor: '#15784B', backgroundColor: 'rgba(8,76,46,0.34)', flexDirection: 'row', alignItems: 'center' },
  linkedDot: { width: 5, height: 5, borderRadius: 5, backgroundColor: P.green, marginRight: 4 },
  linkedText: { color: P.green, fontSize: 7.2, fontWeight: '800' },
  clubIdentityDivider: { width: 1, height: 46, marginHorizontal: 11, backgroundColor: '#2B5874' },
  clubIdentityPosition: { width: 58, minHeight: 48, alignItems: 'center', justifyContent: 'center' },
  clubIdentityPosLabel: { color: P.blue2, fontSize: 8.5, fontWeight: '800', lineHeight: 10, marginBottom: 1 },
  clubIdentityPosValue: { color: P.white, fontSize: 20, lineHeight: 23, fontWeight: '900', textAlign: 'center' },

  menuGrid: { flexDirection: 'row', flexWrap: 'wrap', justifyContent: 'space-between', marginTop: 9 },
  menuCard: { width: '48.5%', minHeight: 121, borderRadius: 16, borderWidth: 1, borderColor: P.border, backgroundColor: P.panel, padding: 12, marginBottom: 8 },
  menuCardActive: { borderColor: '#2C8FD3' },
  pressed: { opacity: 0.75 },
    menuTitle: { color: P.white, fontSize: 15.5, fontWeight: '800', marginTop: 8 },
  menuSubtitle: { color: P.muted, fontSize: 9.4, lineHeight: 13, marginTop: 3, paddingRight: 11 },
  menuChevron: { position: 'absolute', right: 11, top: 58, color: P.blue, fontSize: 20, fontWeight: '800' },

  dualRow: { flexDirection: 'row', marginTop: 2 },
  newsCard: { flex: 0.94, minHeight: 252, borderRadius: 16, backgroundColor: P.panel, borderWidth: 1, borderColor: P.border, padding: 11, marginRight: 5, overflow: 'hidden' },
  tableCard: { flex: 1.06, minHeight: 252, borderRadius: 16, backgroundColor: P.panel, borderWidth: 1, borderColor: P.border, padding: 10, marginLeft: 5, overflow: 'hidden' },
  sectionHeader: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 9 },
  sectionTitle: { color: P.white, fontSize: 12.5, fontWeight: '800' },
  link: { color: P.blue2, fontSize: 8.5, fontWeight: '800' },

  innerCarousel: { flexGrow: 0 },
  newsPage: { minHeight: 204, paddingRight: 1 },
  statsPage: { minHeight: 204, paddingRight: 1 },
  newsVisual: { height: 78, borderRadius: 11, overflow: 'hidden', backgroundColor: '#0B1C29', borderWidth: 1, borderColor: '#1F4E6B', marginBottom: 9, justifyContent: 'center', alignItems: 'center' },
  newsGlow: { position: 'absolute', width: 150, height: 150, borderRadius: 90, backgroundColor: 'rgba(38,145,220,0.18)' },
  newsBadge: { position: 'absolute', left: 8, top: 8, color: P.blue2, fontSize: 8.5, fontWeight: '900', letterSpacing: 1.3 },
  newsVisualMark: { color: P.white, fontSize: 22, fontWeight: '900', letterSpacing: 1.5 },
  newsTitle: { color: P.white, fontSize: 11.5, lineHeight: 14.5, fontWeight: '800' },
  newsText: { color: P.muted, fontSize: 9, lineHeight: 13, marginTop: 4 },
  newsTime: { color: P.muted, fontSize: 8.5, marginTop: 8 },
  carouselDots: { flexDirection: 'row', justifyContent: 'center', alignItems: 'center', gap: 4, marginTop: 8 },
  carouselDot: { width: 4, height: 4, borderRadius: 4, backgroundColor: '#425B6C' },
  carouselDotActive: { width: 11, backgroundColor: P.blue },

  tableHead: { flexDirection: 'row', alignItems: 'center', paddingBottom: 5, borderBottomWidth: 1, borderBottomColor: '#1F3B50' },
  th: { color: '#71899A', fontSize: 7.1, fontWeight: '800', textAlignVertical: 'center' },
  rankCol: { width: 16, flexShrink: 0, textAlign: 'left' },
  clubHeadCol: { flex: 1, minWidth: 0 },
  pjCol: { width: 20, flexShrink: 0, textAlign: 'center' },
  ptsCol: { width: 26, flexShrink: 0, textAlign: 'center' },
  goalsCol: { width: 24, flexShrink: 0, textAlign: 'center' },
  tableRow: { flexDirection: 'row', alignItems: 'center', minHeight: 31, borderBottomWidth: 1, borderBottomColor: '#183247' },
  rank: { color: P.white, fontSize: 9, fontWeight: '800', textAlignVertical: 'center' },
  clubCell: { flex: 1, minWidth: 0, flexDirection: 'row', alignItems: 'center', paddingRight: 2 },
  badge: { width: 16, height: 16, marginRight: 4, flexShrink: 0 },
  badgeFallback: { width: 16, height: 16, borderRadius: 7, backgroundColor: '#173C56', alignItems: 'center', justifyContent: 'center', marginRight: 4, flexShrink: 0 },
  badgeFallbackText: { color: P.blue2, fontSize: 7.5, fontWeight: '900' },
  clubName: { color: '#D8E4EC', fontSize: 8.2, flex: 1, minWidth: 0 },
  stat: { color: '#B4C3CE', fontSize: 8.2, textAlignVertical: 'center' },
  points: { color: P.white, fontWeight: '900' },
  scorersTitle: { color: P.white, fontSize: 10.5, fontWeight: '800', marginBottom: 6 },
  scorerRow: { flexDirection: 'row', alignItems: 'center', minHeight: 34, borderBottomWidth: 1, borderBottomColor: '#183247' },
  scorerCell: { flex: 1, minWidth: 0, flexDirection: 'row', alignItems: 'center', paddingRight: 2 },
  scorerCopy: { flex: 1, minWidth: 0 },
  scorerName: { color: '#E4EDF3', fontSize: 8.2, fontWeight: '800' },
  scorerTeam: { color: P.muted, fontSize: 6.9, marginTop: 1 },
  goals: { color: P.white, fontSize: 10, fontWeight: '900', textAlignVertical: 'center' },
  emptyScorers: { minHeight: 150, alignItems: 'center', justifyContent: 'center', paddingHorizontal: 12 },
  emptyScorersText: { color: P.muted, fontSize: 9, lineHeight: 13, textAlign: 'center' },

  competitions: { marginTop: 8, borderRadius: 16, backgroundColor: P.panel, borderWidth: 1, borderColor: P.border, padding: 11 },
  competitionRow: { flexDirection: 'row' },
  compCard: { flex: 1, minHeight: 100, padding: 8, borderRadius: 12, backgroundColor: P.panel2, borderWidth: 1, borderColor: '#1D4056', marginHorizontal: 3 },
  compTitle: { color: P.white, fontSize: 9.3, fontWeight: '800' },
  compSub: { color: P.muted, fontSize: 8, lineHeight: 11, marginTop: 3 },
  compLive: { color: P.blue2, fontSize: 7.5, marginTop: 6, fontWeight: '800' },
  compMuted: { color: '#8C9EAB', fontSize: 7.5, marginTop: 6, fontWeight: '800' },

  previewNote: { marginTop: 8, padding: 11, borderRadius: 14, backgroundColor: '#0A1E2D', borderWidth: 1, borderColor: '#1D4D6C' },
  previewNoteTitle: { color: P.blue2, fontSize: 8.5, fontWeight: '900', letterSpacing: 1.4 },
  previewNoteText: { color: '#B1C2CE', fontSize: 9.5, lineHeight: 14, marginTop: 5 },

  bottomNav: { position: 'absolute', left: 0, right: 0, bottom: 0, height: 64, flexDirection: 'row', alignItems: 'center', backgroundColor: '#07141F', borderTopWidth: 1, borderTopColor: '#19384D', paddingBottom: 6 },
  bottomItem: { flex: 1, alignItems: 'center', justifyContent: 'center' },
    bottomLabel: { color: '#788D9C', fontSize: 7.3, fontWeight: '700', marginTop: 2 },
  bottomActive: { color: P.blue },
});
