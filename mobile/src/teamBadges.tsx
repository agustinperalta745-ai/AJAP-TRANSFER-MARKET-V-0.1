import React from 'react';
import { Image, Text, View } from 'react-native';
import type { ImageSourcePropType, ImageStyle, StyleProp } from 'react-native';

// Keep GitHub as a fallback only. The visible crest is resolved from Wikipedia's
// page-image API so every club gets a clean rendered thumbnail instead of the
// black-background source files that were uploaded to the repository.
const RAW_MAIN = 'https://raw.githubusercontent.com/agustinperalta745-ai/AJAP-TRANSFER-MARKET-V-0.1/main/mobile/assets/teams';
const BADGE_VERSION = '20260831-wiki-clean-v1';
const remoteMain = (file: string): ImageSourcePropType => ({ uri: `${RAW_MAIN}/${file}?v=${BADGE_VERSION}` });

const ASSETS = {
  ajax: remoteMain('ajax.png'),
  as_monaco: remoteMain('as_monaco.png'),
  aston_villa: remoteMain('aston_villa.png'),
  atletico_madrid: remoteMain('atletico_madrid.png'),
  benfica: remoteMain('benfica.png'),
  bolton_wanderers: remoteMain('bolton_wanderers.png'),
  everton: remoteMain('everton.png'),
  feyenoord: remoteMain('feyenoord.png'),
  fiorentina: remoteMain('fiorentina.png'),
  fulham: remoteMain('fulham.png'),
  galatasaray: remoteMain('galatasaray.png'),
  lazio: remoteMain('lazio.png'),
  manchester_city: remoteMain('manchester_city.png'),
  middlesbrough: remoteMain('middlesbrough.png'),
  olympique_lyon: remoteMain('olympique_lyon.png'),
  olympique_marseille: remoteMain('olympique_marseille.png'),
  porto: remoteMain('porto.png'),
  psg: remoteMain('psg.png'),
  real_betis: remoteMain('real_betis.png'),
  sevilla: remoteMain('sevilla.png'),
  torino: remoteMain('torino.png'),
  tottenham_hotspur: remoteMain('tottenham_hotspur.png'),
  villarreal: remoteMain('villarreal.png'),
  west_ham_united: remoteMain('west_ham_united.png'),
  zaragoza: remoteMain('zaragoza.png'),
} satisfies Record<string, ImageSourcePropType>;

const BADGES: Record<string, ImageSourcePropType> = {
  ajax: ASSETS.ajax,
  'aston villa': ASSETS.aston_villa,
  'atletico madrid': ASSETS.atletico_madrid,
  benfica: ASSETS.benfica,
  'real betis': ASSETS.real_betis,
  betis: ASSETS.real_betis,
  'bolton wanderers': ASSETS.bolton_wanderers,
  bolton: ASSETS.bolton_wanderers,
  everton: ASSETS.everton,
  feyenoord: ASSETS.feyenoord,
  fiorentina: ASSETS.fiorentina,
  fulham: ASSETS.fulham,
  galatasaray: ASSETS.galatasaray,
  lazio: ASSETS.lazio,
  'ss lazio': ASSETS.lazio,
  lyon: ASSETS.olympique_lyon,
  'olympique lyonnais': ASSETS.olympique_lyon,
  'olympique de lyon': ASSETS.olympique_lyon,
  'manchester city': ASSETS.manchester_city,
  'man city': ASSETS.manchester_city,
  marsella: ASSETS.olympique_marseille,
  marseille: ASSETS.olympique_marseille,
  'olympique de marsella': ASSETS.olympique_marseille,
  'olympique de marseille': ASSETS.olympique_marseille,
  middlesbrough: ASSETS.middlesbrough,
  middle: ASSETS.middlesbrough,
  monaco: ASSETS.as_monaco,
  'as monaco': ASSETS.as_monaco,
  psg: ASSETS.psg,
  'paris saint germain': ASSETS.psg,
  porto: ASSETS.porto,
  'fc porto': ASSETS.porto,
  sevilla: ASSETS.sevilla,
  'sevilla fc': ASSETS.sevilla,
  torino: ASSETS.torino,
  'torino fc': ASSETS.torino,
  tottenham: ASSETS.tottenham_hotspur,
  'tottenham hotspur': ASSETS.tottenham_hotspur,
  villareal: ASSETS.villarreal,
  villarreal: ASSETS.villarreal,
  'villarreal cf': ASSETS.villarreal,
  'west ham': ASSETS.west_ham_united,
  'west ham united': ASSETS.west_ham_united,
  zaragoza: ASSETS.zaragoza,
  'real zaragoza': ASSETS.zaragoza,
};

const WIKIPEDIA_TITLES: Record<string, string> = {
  ajax: 'AFC Ajax',
  monaco: 'AS Monaco FC',
  'as monaco': 'AS Monaco FC',
  'aston villa': 'Aston Villa F.C.',
  'atletico madrid': 'Atlético Madrid',
  benfica: 'S.L. Benfica',
  'real betis': 'Real Betis',
  betis: 'Real Betis',
  'bolton wanderers': 'Bolton Wanderers F.C.',
  bolton: 'Bolton Wanderers F.C.',
  everton: 'Everton F.C.',
  feyenoord: 'Feyenoord',
  fiorentina: 'ACF Fiorentina',
  fulham: 'Fulham F.C.',
  galatasaray: 'Galatasaray S.K. (football)',
  lazio: 'S.S. Lazio',
  'ss lazio': 'S.S. Lazio',
  lyon: 'Olympique Lyonnais',
  'olympique lyonnais': 'Olympique Lyonnais',
  'olympique de lyon': 'Olympique Lyonnais',
  'manchester city': 'Manchester City F.C.',
  'man city': 'Manchester City F.C.',
  marsella: 'Olympique de Marseille',
  marseille: 'Olympique de Marseille',
  'olympique de marsella': 'Olympique de Marseille',
  'olympique de marseille': 'Olympique de Marseille',
  middlesbrough: 'Middlesbrough F.C.',
  middle: 'Middlesbrough F.C.',
  psg: 'Paris Saint-Germain F.C.',
  'paris saint germain': 'Paris Saint-Germain F.C.',
  porto: 'FC Porto',
  'fc porto': 'FC Porto',
  sevilla: 'Sevilla FC',
  'sevilla fc': 'Sevilla FC',
  torino: 'Torino FC',
  'torino fc': 'Torino FC',
  tottenham: 'Tottenham Hotspur F.C.',
  'tottenham hotspur': 'Tottenham Hotspur F.C.',
  villareal: 'Villarreal CF',
  villarreal: 'Villarreal CF',
  'villarreal cf': 'Villarreal CF',
  'west ham': 'West Ham United F.C.',
  'west ham united': 'West Ham United F.C.',
  zaragoza: 'Real Zaragoza',
  'real zaragoza': 'Real Zaragoza',
};

const normalizeClub = (club: string | null | undefined) =>
  String(club || '')
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .replace(/[._-]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();

const cleanBadgeCache: Record<string, string> = {};
const badgeRequests: Record<string, Promise<string | null>> = {};

async function resolveCleanBadgeUri(club: string | null | undefined): Promise<string | null> {
  const key = normalizeClub(club);
  const title = WIKIPEDIA_TITLES[key];
  if (!title) return null;
  if (cleanBadgeCache[key]) return cleanBadgeCache[key];
  if (badgeRequests[key]) return badgeRequests[key];

  badgeRequests[key] = (async () => {
    try {
      const api = `https://en.wikipedia.org/w/api.php?action=query&format=json&redirects=1&prop=pageimages&piprop=thumbnail&pithumbsize=512&titles=${encodeURIComponent(title)}`;
      const response = await fetch(api, { headers: { Accept: 'application/json' } });
      if (!response.ok) return null;
      const payload = await response.json();
      const pages = payload?.query?.pages ? Object.values(payload.query.pages) as Array<any> : [];
      const uri = pages[0]?.thumbnail?.source;
      if (typeof uri === 'string' && uri.startsWith('http')) {
        cleanBadgeCache[key] = uri;
        return uri;
      }
      return null;
    } catch {
      return null;
    } finally {
      delete badgeRequests[key];
    }
  })();

  return badgeRequests[key];
}

export function getTeamBadge(club: string | null | undefined): ImageSourcePropType | null {
  const key = normalizeClub(club);
  if (!key || key === 'jugador libre') return null;
  return BADGES[key] ?? null;
}

export function ClubBadge({
  club,
  size = 72,
  style,
}: {
  club: string | null | undefined;
  size?: number;
  style?: StyleProp<ImageStyle>;
}) {
  const fallback = getTeamBadge(club);
  const cacheKey = normalizeClub(club);
  const [cleanUri, setCleanUri] = React.useState<string | null>(() => cleanBadgeCache[cacheKey] ?? null);
  const [resolved, setResolved] = React.useState(() => Boolean(cleanBadgeCache[cacheKey]));

  React.useEffect(() => {
    let active = true;
    const nextKey = normalizeClub(club);
    const cached = cleanBadgeCache[nextKey];
    if (cached) {
      setCleanUri(cached);
      setResolved(true);
      return () => { active = false; };
    }

    setCleanUri(null);
    setResolved(false);
    resolveCleanBadgeUri(club).then(uri => {
      if (!active) return;
      setCleanUri(uri);
      setResolved(true);
    });
    return () => { active = false; };
  }, [club]);

  if (!fallback && !cleanUri) return null;
  if (!resolved && !cleanUri) {
    return <View style={{ width: size, height: size, backgroundColor: 'transparent' }} />;
  }

  return (
    <Image
      source={cleanUri ? { uri: cleanUri } : fallback!}
      resizeMode="contain"
      fadeDuration={0}
      accessibilityLabel={`Escudo de ${club}`}
      style={[{ width: size, height: size, backgroundColor: 'transparent' }, style]}
    />
  );
}

export function ClubMatchup({
  home,
  away,
  size = 58,
}: {
  home: string | null | undefined;
  away: string | null | undefined;
  size?: number;
}) {
  if (!home && !away) return null;
  return (
    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10, marginTop: 8 }}>
      <ClubBadge club={home} size={size} />
      <Text style={{ color: '#8ac5ff', fontWeight: '900', fontSize: 11 }}>VS</Text>
      <ClubBadge club={away} size={size} />
    </View>
  );
}
