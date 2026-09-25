import React, { useEffect, useMemo, useState } from 'react';
import {
  ActivityIndicator,
  Image,
  ImageBackground,
  ImageSourcePropType,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';

import { fetchLeague, fetchSnapshot, LeagueStanding } from './api';

const C = {
  bg: '#07111b',
  panel: '#0d1b29',
  panel2: '#102435',
  panel3: '#142b3f',
  border: 'rgba(133,190,225,0.16)',
  text: '#f5f9fc',
  muted: '#8fa7ba',
  cyan: '#35b7ff',
  blue: '#1f82d8',
  green: '#44d17a',
  gold: '#d3a946',
  violet: '#7665df',
  red: '#df6c6c',
};

const BADGES: Record<string, ImageSourcePropType> = {
  ajax: require('../assets/teams/ajax.png'),
  'aston villa': require('../assets/teams/aston_villa.png'),
  'atletico madrid': require('../assets/teams/atletico_madrid.png'),
  benfica: require('../assets/teams/benfica.png'),
  'bolton wanderers': require('../assets/teams/bolton_wanderers.png'),
  everton: require('../assets/teams/everton.png'),
  feyenoord: require('../assets/teams/feyenoord.png'),
  fiorentina: require('../assets/teams/fiorentina.png'),
  fulham: require('../assets/teams/fulham.png'),
  galatasaray: require('../assets/teams/galatasaray.png'),
  lazio: require('../assets/teams/lazio.png'),
  'manchester city': require('../assets/teams/manchester_city.png'),
  middlesbrough: require('../assets/teams/middlesbrough.png'),
  monaco: require('../assets/teams/as_monaco.png'),
  'olympique de lyon': require('../assets/teams/olympique_lyon.png'),
  'olympique de marsella': require('../assets/teams/olympique_marseille.png'),
  porto: require('../assets/teams/porto.png'),
  psg: require('../assets/teams/psg.png'),
  'real betis': require('../assets/teams/real_betis.png'),
  sevilla: require('../assets/teams/sevilla.png'),
  'sevilla fc': require('../assets/teams/sevilla.png'),
  'tottenham hotspur': require('../assets/teams/tottenham_hotspur.png'),
  villarreal: require('../assets/teams/villarreal.png'),
  'west ham united': require('../assets/teams/west_ham_united.png'),
  zaragoza: require('../assets/teams/zaragoza.png'),
  'real zaragoza': require('../assets/teams/zaragoza.png'),
};

function key(name: string) {
  return String(name || '').trim().toLowerCase();
}

function badgeFor(name: string) {
  return BADGES[key(name)] ?? BADGES['atletico madrid'];
}

function CrestMark() {
  return (
    <View style={s.crestOuter}>
      <View style={s.crestInner}>
        <Text style={s.crestText}>AJPA</Text>
        <View style={s.crestStripeRow}>
          <View style={s.crestBlue} />
          <View style={s.crestWhite} />
          <View style={s.crestBlue} />
        </View>
        <Text style={s.sun}>☀</Text>
      </View>
    </View>
  );
}

function QuickCard({
  symbol,
  title,
  subtitle,
  accent,
}: {
  symbol: string;
  title: string;
  subtitle: string;
  accent: string;
}) {
  return (
    <Pressable style={({ pressed }) => [s.quickCard, pressed && s.pressed]}>
      <View style={[s.quickIcon, { backgroundColor: accent }]}>
        <Text style={s.quickSymbol}>{symbol}</Text>
      </View>
      <Text style={s.quickTitle}>{title}</Text>
      <Text style={s.quickSubtitle}>{subtitle}</Text>
      <Text style={s.arrow}>›</Text>
    </Pressable>
  );
}

function StandingRow({ row, index }: { row: LeagueStanding; index: number }) {
  return (
    <View style={s.standingRow}>
      <Text style={s.rank}>{index + 1}</Text>
      <Image source={badgeFor(row.team)} style={s.smallBadge} resizeMode="contain" />
      <Text style={s.teamName} numberOfLines={1}>{row.team}</Text>
      <Text style={s.statCell}>{row.pj}</Text>
      <Text style={s.statCell}>{row.dg > 0 ? '+' : ''}{row.dg}</Text>
      <Text style={s.points}>{row.pts}</Text>
    </View>
  );
}

function BottomItem({
  icon,
  label,
  active,
}: {
  icon: string;
  label: string;
  active?: boolean;
}) {
  return (
    <Pressable style={s.bottomItem}>
      <Text style={[s.bottomIcon, active && s.bottomActive]}>{icon}</Text>
      <Text style={[s.bottomLabel, active && s.bottomActive]}>{label}</Text>
    </Pressable>
  );
}

export default function AJPAConceptCPreview() {
  const [marketOpen, setMarketOpen] = useState<boolean | null>(null);
  const [standings, setStandings] = useState<LeagueStanding[]>([]);
  const [clubCount, setClubCount] = useState<number>(24);
  const [seasonName, setSeasonName] = useState('Temporada 2');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let alive = true;
    Promise.allSettled([fetchSnapshot(), fetchLeague()]).then(results => {
      if (!alive) return;
      const [snapshotResult, leagueResult] = results;
      if (snapshotResult.status === 'fulfilled') {
        setMarketOpen(Boolean(snapshotResult.value.status.market_open));
        setClubCount(snapshotResult.value.clubs?.length || 24);
        if (snapshotResult.value.status.season?.name) {
          setSeasonName(snapshotResult.value.status.season.name);
        }
      }
      if (leagueResult.status === 'fulfilled') {
        setStandings(leagueResult.value.standings || []);
      }
      setLoading(false);
    });
    return () => { alive = false; };
  }, []);

  const topFive = useMemo(() => standings.slice(0, 5), [standings]);
  const marketLabel = marketOpen === null ? 'CARGANDO' : marketOpen ? 'ABIERTO' : 'CERRADO';

  return (
    <View style={s.root}>
      <ScrollView
        contentContainerStyle={s.scroll}
        showsVerticalScrollIndicator={false}
      >
        <View style={s.header}>
          <View style={s.brandRow}>
            <CrestMark />
            <View style={s.brandCopy}>
              <Text style={s.brand}>AJPA</Text>
              <Text style={s.brandSub}>ASOCIACIÓN DE JUGADORES DE PES ARGENTINA</Text>
            </View>
          </View>

          <View style={s.userRow}>
            <View style={s.bell}>
              <Text style={s.bellText}>⌁</Text>
              <View style={s.bellDot} />
            </View>
            <View style={s.userCopy}>
              <Text style={s.hello}>AJPA Mobile</Text>
              <Text style={s.userClub}>Tu club y tu temporada</Text>
            </View>
            <Text style={s.headerArrow}>›</Text>
          </View>
        </View>

        <ImageBackground
          source={require('../assets/xi-ideal-splash-hd.jpg')}
          style={s.hero}
          imageStyle={s.heroImage}
        >
          <View style={s.heroShade} />
          <View style={s.heroContent}>
            <Text style={s.eyebrow}>{seasonName.toUpperCase()}</Text>
            <Text style={s.heroTitle}>La temporada</Text>
            <Text style={[s.heroTitle, s.heroBlue]}>se vive en AJPA</Text>
            <View style={s.heroMeta}>
              <View style={s.heroMetaBlock}>
                <Text style={s.heroMetaIcon}>◫</Text>
                <View>
                  <Text style={s.heroMetaMuted}>{clubCount} clubes</Text>
                  <Text style={s.heroMetaStrong}>Competencia activa</Text>
                </View>
              </View>
              <View style={s.heroDivider} />
              <View style={s.heroMetaBlock}>
                <View style={s.swapBox}><Text style={s.swap}>⇄</Text></View>
                <View>
                  <Text style={s.heroMetaMuted}>Mercado</Text>
                  <Text style={[s.heroMetaStrong, marketOpen ? s.open : s.closed]}>
                    {marketLabel}
                  </Text>
                </View>
              </View>
            </View>
            <View style={s.dots}>
              <View style={[s.dot, s.dotActive]} />
              <View style={s.dot} />
              <View style={s.dot} />
            </View>
          </View>
        </ImageBackground>

        <View style={s.grid}>
          <QuickCard symbol="⇄" title="Mercado" subtitle="Fichajes, ofertas y negociaciones" accent="#2f88c8" />
          <QuickCard symbol="◇" title="Mi Club" subtitle="Plantel, gestión y clásico rival" accent="#2e9f72" />
          <QuickCard symbol="▥" title="Liga" subtitle="Tabla, resultados y estadísticas" accent="#366ecb" />
          <QuickCard symbol="♛" title="Copas" subtitle="Champions, Europa y torneos" accent="#ad842c" />
          <QuickCard symbol="●" title="Perfil" subtitle="Historial, logros y cuenta" accent="#6658bd" />
          <QuickCard symbol="⚙" title="Staff / Admin" subtitle="Gestión de liga y herramientas" accent="#64788b" />
        </View>

        <View style={s.dual}>
          <View style={[s.panel, s.newsPanel]}>
            <View style={s.panelHeader}>
              <Text style={s.panelTitle}>Noticias AJPA</Text>
              <Text style={s.panelLink}>Ver todas ›</Text>
            </View>
            <ImageBackground
              source={require('../assets/trophies/champions-ajpa-banner.jpg')}
              style={s.newsImage}
              imageStyle={s.newsImageRadius}
            >
              <View style={s.newsShade} />
              <View style={s.newsTag}><Text style={s.newsTagText}>AJPA</Text></View>
            </ImageBackground>
            <Text style={s.newsTitle}>Todo listo para una nueva jornada</Text>
            <Text style={s.newsCopy}>Mercado, Liga y Copas en un solo lugar.</Text>
            <Text style={s.newsTime}>◷  Ahora</Text>
          </View>

          <View style={[s.panel, s.tablePanel]}>
            <View style={s.panelHeader}>
              <Text style={s.panelTitle}>Tabla de posiciones</Text>
              <Text style={s.panelLink}>Ver tabla ›</Text>
            </View>

            <View style={s.tableHead}>
              <Text style={s.tableHash}>#</Text>
              <Text style={s.tableClub}>Club</Text>
              <Text style={s.tableCell}>PJ</Text>
              <Text style={s.tableCell}>DG</Text>
              <Text style={s.tablePts}>PTS</Text>
            </View>

            {loading ? (
              <View style={s.loader}><ActivityIndicator size="small" color={C.cyan} /></View>
            ) : topFive.length ? (
              topFive.map((row, index) => <StandingRow key={row.team} row={row} index={index} />)
            ) : (
              <Text style={s.empty}>La tabla se cargará desde AJPA.</Text>
            )}
          </View>
        </View>

        <View style={[s.panel, s.competitionPanel]}>
          <View style={s.panelHeader}>
            <Text style={s.panelTitle}>Competencias</Text>
            <Text style={s.panelLink}>Ver todas ›</Text>
          </View>

          <View style={s.competitions}>
            <View style={s.competitionCard}>
              <Image source={require('../assets/trophies/liga-ajpa-rank-icon.png')} style={s.trophyIcon} resizeMode="contain" />
              <View style={s.competitionText}>
                <Text style={s.competitionTitle}>Liga AJPA</Text>
                <Text style={s.competitionSub}>{seasonName}</Text>
                <Text style={s.live}>● En curso</Text>
              </View>
            </View>
            <View style={s.competitionCard}>
              <Image source={require('../assets/trophies/ranking-icons/champions-ajpa.jpg')} style={s.trophyIconRound} />
              <View style={s.competitionText}>
                <Text style={s.competitionTitle}>Champions AJPA</Text>
                <Text style={s.competitionSub}>Competición oficial</Text>
                <Text style={s.pending}>● Próxima fase</Text>
              </View>
            </View>
            <View style={s.competitionCard}>
              <Image source={require('../assets/trophies/europa-ajpa-card-icon.png')} style={s.trophyIcon} resizeMode="contain" />
              <View style={s.competitionText}>
                <Text style={s.competitionTitle}>Europa AJPA</Text>
                <Text style={s.competitionSub}>Competición oficial</Text>
                <Text style={s.live}>● En curso</Text>
              </View>
            </View>
          </View>
        </View>

        <Text style={s.previewNote}>CONCEPTO C · PREVIEW DE DISEÑO · DATOS AJPA</Text>
      </ScrollView>

      <View style={s.bottom}>
        <BottomItem icon="⌂" label="Inicio" active />
        <BottomItem icon="⇄" label="Mercado" />
        <BottomItem icon="◇" label="Mi Club" />
        <BottomItem icon="▥" label="Liga" />
        <BottomItem icon="♛" label="Copas" />
        <BottomItem icon="•••" label="Más" />
      </View>
    </View>
  );
}

const s = StyleSheet.create({
  root: { flex: 1, backgroundColor: C.bg },
  scroll: { paddingHorizontal: 16, paddingTop: 10, paddingBottom: 108 },
  header: {
    paddingTop: 4,
    paddingBottom: 16,
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  brandRow: { flexDirection: 'row', alignItems: 'center', flex: 1 },
  crestOuter: {
    width: 54, height: 64, borderRadius: 16,
    borderWidth: 1, borderColor: 'rgba(120,210,255,0.65)',
    backgroundColor: '#dcebf6', padding: 4,
    shadowColor: '#2cbcff', shadowOpacity: 0.22, shadowRadius: 10, elevation: 6,
  },
  crestInner: { flex: 1, borderRadius: 12, overflow: 'hidden', backgroundColor: '#eaf4fb', alignItems: 'center' },
  crestText: { color: '#102536', fontSize: 10, fontWeight: '900', marginTop: 3, letterSpacing: 1 },
  crestStripeRow: { flexDirection: 'row', height: 22, width: '100%', marginTop: 3 },
  crestBlue: { flex: 1, backgroundColor: '#75c7f4' },
  crestWhite: { flex: 1, backgroundColor: '#f6fbff' },
  sun: { position: 'absolute', bottom: 2, color: '#d2a735', fontSize: 13 },
  brandCopy: { marginLeft: 12, flex: 1 },
  brand: { color: C.text, fontSize: 30, fontWeight: '900', letterSpacing: 2 },
  brandSub: { color: C.cyan, fontSize: 7.5, fontWeight: '800', letterSpacing: 1.5, maxWidth: 180, lineHeight: 11 },
  userRow: { flexDirection: 'row', alignItems: 'center', marginLeft: 8, maxWidth: 145 },
  bell: { width: 28, height: 28, marginRight: 6, alignItems: 'center', justifyContent: 'center' },
  bellText: { color: '#dce9f2', fontSize: 25, transform: [{ rotate: '20deg' }] },
  bellDot: { position: 'absolute', right: 2, top: 1, width: 8, height: 8, borderRadius: 4, backgroundColor: C.cyan },
  userCopy: { flex: 1 },
  hello: { color: '#dce5ec', fontSize: 10, fontWeight: '700' },
  userClub: { color: C.muted, fontSize: 9, marginTop: 2 },
  headerArrow: { color: C.cyan, fontSize: 22, marginLeft: 3 },

  hero: {
    height: 258, borderRadius: 22, overflow: 'hidden',
    borderWidth: 1, borderColor: 'rgba(117,189,229,0.28)',
    backgroundColor: C.panel2,
  },
  heroImage: { borderRadius: 22, opacity: 0.78 },
  heroShade: {
    ...StyleSheet.absoluteFillObject,
    backgroundColor: 'rgba(2,13,23,0.62)',
  },
  heroContent: { flex: 1, paddingHorizontal: 20, paddingVertical: 22, justifyContent: 'flex-end' },
  eyebrow: { color: '#74ceff', fontSize: 10, letterSpacing: 3, fontWeight: '800', marginBottom: 8 },
  heroTitle: { color: '#fff', fontSize: 31, lineHeight: 34, fontWeight: '900', maxWidth: 320 },
  heroBlue: { color: C.cyan },
  heroMeta: { flexDirection: 'row', alignItems: 'center', marginTop: 18 },
  heroMetaBlock: { flexDirection: 'row', alignItems: 'center' },
  heroMetaIcon: { color: '#fff', fontSize: 26, marginRight: 10 },
  swapBox: { width: 34, height: 34, borderRadius: 9, backgroundColor: '#145d3a', alignItems: 'center', justifyContent: 'center', marginRight: 10 },
  swap: { color: '#fff', fontSize: 22, fontWeight: '800' },
  heroMetaMuted: { color: '#c0cbd3', fontSize: 10 },
  heroMetaStrong: { color: '#fff', fontSize: 11, fontWeight: '800', marginTop: 3 },
  open: { color: C.green },
  closed: { color: C.red },
  heroDivider: { width: 1, height: 34, backgroundColor: 'rgba(255,255,255,0.25)', marginHorizontal: 18 },
  dots: { flexDirection: 'row', gap: 7, marginTop: 16 },
  dot: { width: 7, height: 7, borderRadius: 4, backgroundColor: 'rgba(255,255,255,0.25)' },
  dotActive: { width: 18, backgroundColor: C.cyan },

  grid: { flexDirection: 'row', flexWrap: 'wrap', justifyContent: 'space-between', marginTop: 14 },
  quickCard: {
    width: '32%', minHeight: 154, backgroundColor: C.panel,
    borderRadius: 17, borderWidth: 1, borderColor: C.border,
    padding: 13, marginBottom: 8, position: 'relative',
    shadowColor: '#000', shadowOpacity: 0.22, shadowRadius: 8, elevation: 3,
  },
  pressed: { opacity: 0.78, transform: [{ scale: 0.985 }] },
  quickIcon: { width: 42, height: 42, borderRadius: 11, alignItems: 'center', justifyContent: 'center', marginBottom: 12 },
  quickSymbol: { color: '#fff', fontSize: 24, fontWeight: '700' },
  quickTitle: { color: C.text, fontSize: 15, fontWeight: '900' },
  quickSubtitle: { color: C.muted, fontSize: 10, lineHeight: 14, marginTop: 5, paddingRight: 4 },
  arrow: { color: C.cyan, fontSize: 20, position: 'absolute', right: 8, top: 76 },

  dual: { flexDirection: 'row', gap: 10, marginTop: 4 },
  panel: { backgroundColor: C.panel, borderRadius: 17, borderWidth: 1, borderColor: C.border, overflow: 'hidden' },
  newsPanel: { flex: 0.95, padding: 12 },
  tablePanel: { flex: 1.05, padding: 12 },
  panelHeader: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 10 },
  panelTitle: { color: C.text, fontSize: 13, fontWeight: '900' },
  panelLink: { color: '#5ec5ff', fontSize: 9, fontWeight: '700' },
  newsImage: { height: 74, justifyContent: 'flex-end' },
  newsImageRadius: { borderRadius: 10 },
  newsShade: { ...StyleSheet.absoluteFillObject, borderRadius: 10, backgroundColor: 'rgba(2,10,18,0.28)' },
  newsTag: { margin: 7, alignSelf: 'flex-start', backgroundColor: '#154b70', borderWidth: 1, borderColor: '#65c8ff', borderRadius: 7, paddingHorizontal: 8, paddingVertical: 4 },
  newsTagText: { color: '#dff5ff', fontSize: 8, fontWeight: '900' },
  newsTitle: { color: '#fff', fontSize: 12, lineHeight: 15, fontWeight: '900', marginTop: 9 },
  newsCopy: { color: C.muted, fontSize: 8.5, lineHeight: 12, marginTop: 5 },
  newsTime: { color: '#849aaa', fontSize: 8, marginTop: 7 },

  tableHead: { flexDirection: 'row', alignItems: 'center', paddingVertical: 5, borderBottomWidth: 1, borderBottomColor: C.border },
  tableHash: { width: 16, color: '#708899', fontSize: 8, fontWeight: '800' },
  tableClub: { flex: 1, color: '#708899', fontSize: 8, fontWeight: '800' },
  tableCell: { width: 22, textAlign: 'center', color: '#708899', fontSize: 8, fontWeight: '800' },
  tablePts: { width: 24, textAlign: 'right', color: '#708899', fontSize: 8, fontWeight: '800' },
  standingRow: { flexDirection: 'row', alignItems: 'center', minHeight: 27, borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: 'rgba(130,176,205,0.11)' },
  rank: { width: 16, color: '#edf5fb', fontSize: 9, fontWeight: '800' },
  smallBadge: { width: 17, height: 17, marginRight: 6 },
  teamName: { flex: 1, color: '#dfe9ef', fontSize: 8.5, fontWeight: '700' },
  statCell: { width: 22, textAlign: 'center', color: '#a5b8c6', fontSize: 8 },
  points: { width: 24, textAlign: 'right', color: '#fff', fontSize: 9, fontWeight: '900' },
  loader: { height: 130, alignItems: 'center', justifyContent: 'center' },
  empty: { color: C.muted, fontSize: 9, paddingVertical: 28, textAlign: 'center' },

  competitionPanel: { marginTop: 11, padding: 12 },
  competitions: { flexDirection: 'row', gap: 8 },
  competitionCard: { flex: 1, minHeight: 92, borderRadius: 13, backgroundColor: '#102131', borderWidth: 1, borderColor: 'rgba(120,182,219,0.12)', flexDirection: 'row', padding: 9, alignItems: 'center' },
  trophyIcon: { width: 38, height: 56, marginRight: 8 },
  trophyIconRound: { width: 40, height: 56, borderRadius: 8, marginRight: 8 },
  competitionText: { flex: 1 },
  competitionTitle: { color: '#eef6fb', fontSize: 9.5, fontWeight: '900', lineHeight: 12 },
  competitionSub: { color: C.muted, fontSize: 8, marginTop: 3, lineHeight: 10 },
  live: { color: C.cyan, fontSize: 8, fontWeight: '700', marginTop: 5 },
  pending: { color: '#889aaa', fontSize: 8, fontWeight: '700', marginTop: 5 },
  previewNote: { color: '#496274', fontSize: 7, letterSpacing: 2.2, textAlign: 'center', marginTop: 16 },

  bottom: {
    position: 'absolute', left: 0, right: 0, bottom: 0,
    minHeight: 76, backgroundColor: 'rgba(6,18,29,0.97)',
    borderTopWidth: 1, borderTopColor: 'rgba(105,173,214,0.16)',
    flexDirection: 'row', justifyContent: 'space-around', alignItems: 'center',
    paddingBottom: 6,
  },
  bottomItem: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  bottomIcon: { color: '#91a6b5', fontSize: 22, fontWeight: '800' },
  bottomLabel: { color: '#91a6b5', fontSize: 8, fontWeight: '700', marginTop: 4 },
  bottomActive: { color: C.cyan },
});
