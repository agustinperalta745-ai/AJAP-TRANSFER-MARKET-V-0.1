import React from 'react';
import { Image, Text, View } from 'react-native';
import type { ImageSourcePropType, ImageStyle, StyleProp } from 'react-native';
import { ATLETICO_BADGE_DATA_URI } from './atleticoBadge';

// RESTAURADO DEL BUILD BUENO (fa74b6e): el escudo visible se resuelve desde
// Wikipedia pageimages a 512 px. Eso fue lo que dio la apariencia nítida y sin
// fondos negros que ya estaba aprobada. El asset histórico queda SOLO como
// respaldo y además está fijado al commit bueno para que main no pueda degradarlo.
const RAW_GOOD = 'https://raw.githubusercontent.com/agustinperalta745-ai/AJAP-TRANSFER-MARKET-V-0.1/fa74b6ea72536eb1b60acf864f4497826d2402db/mobile/assets/teams';
const BADGE_VERSION = '20260901-wiki-clean-restored';
const remoteGood = (file: string): ImageSourcePropType => ({ uri: `${RAW_GOOD}/${file}?v=${BADGE_VERSION}` });

const ASSETS = {
  ajax: remoteGood('ajax.png'),
  as_monaco: remoteGood('as_monaco.png'),
  aston_villa: remoteGood('aston_villa.png'),
  atletico_madrid: { uri: ATLETICO_BADGE_DATA_URI } as ImageSourcePropType,
  benfica: remoteGood('benfica.png'),
  bolton_wanderers: remoteGood('bolton_wanderers.png'),
  everton: remoteGood('everton.png'),
  feyenoord: remoteGood('feyenoord.png'),
  fiorentina: remoteGood('fiorentina.png'),
  fulham: remoteGood('fulham.png'),
  galatasaray: remoteGood('galatasaray.png'),
  lazio: remoteGood('lazio.png'),
  manchester_city: remoteGood('manchester_city.png'),
  middlesbrough: remoteGood('middlesbrough.png'),
  olympique_lyon: remoteGood('olympique_lyon.png'),
  olympique_marseille: remoteGood('olympique_marseille.png'),
  porto: remoteGood('porto.png'),
  psg: remoteGood('psg.png'),
  real_betis: remoteGood('real_betis.png'),
  sevilla: remoteGood('sevilla.png'),
  torino: remoteGood('torino.png'),
  tottenham_hotspur: remoteGood('tottenham_hotspur.png'),
  villarreal: remoteGood('villarreal.png'),
  west_ham_united: remoteGood('west_ham_united.png'),
  zaragoza: remoteGood('zaragoza.png'),
} satisfies Record<string, ImageSourcePropType>;

const normalizeClub = (club: string | null | undefined) =>
  String(club || '')
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .replace(/[._-]+/g, ' ')
    .replace(/[^a-z0-9 ]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();

const BADGES: Record<string, ImageSourcePropType> = {
  ajax: ASSETS.ajax,
  monaco: ASSETS.as_monaco,
  'as monaco': ASSETS.as_monaco,
  'as monaco fc': ASSETS.as_monaco,
  'aston villa': ASSETS.aston_villa,
  'atletico madrid': ASSETS.atletico_madrid,
  'atletico de madrid': ASSETS.atletico_madrid,
  'club atletico de madrid': ASSETS.atletico_madrid,
  'atletico de madrid fc': ASSETS.atletico_madrid,
  'at madrid': ASSETS.atletico_madrid,
  benfica: ASSETS.benfica,
  'sl benfica': ASSETS.benfica,
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

// EXACTAMENTE el resolver del build bueno. Atlético es la única excepción:
// ya no consulta Wikipedia porque debe usar el PNG 512x512 producido desde el EPS.
const WIKIPEDIA_TITLES: Record<string, string> = {
  ajax: 'AFC Ajax',
  monaco: 'AS Monaco FC',
  'as monaco': 'AS Monaco FC',
  'as monaco fc': 'AS Monaco FC',
  'aston villa': 'Aston Villa F.C.',
  benfica: 'S.L. Benfica',
  'sl benfica': 'S.L. Benfica',
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

const cleanBadgeCache: Record<string, string> = {};
const badgeRequests: Record<string, Promise<string | null>> = {};

const isAtleticoKey = (key: string) =>
  key === 'atletico madrid' ||
  key === 'atletico de madrid' ||
  key === 'club atletico de madrid' ||
  key === 'atletico de madrid fc' ||
  key === 'at madrid';

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
  const pinnedLocal = isAtleticoKey(cacheKey);
  const [cleanUri, setCleanUri] = React.useState<string | null>(() => cleanBadgeCache[cacheKey] ?? null);
  const [resolved, setResolved] = React.useState(() => pinnedLocal || Boolean(cleanBadgeCache[cacheKey]));

  React.useEffect(() => {
    let active = true;
    const nextKey = normalizeClub(club);

    if (isAtleticoKey(nextKey)) {
      setCleanUri(null);
      setResolved(true);
      return () => { active = false; };
    }

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

  const image = (
    <Image
      source={cleanUri ? { uri: cleanUri } : fallback!}
      resizeMode="contain"
      fadeDuration={0}
      accessibilityLabel={`Escudo de ${String(club || 'club')}`}
      style={[{ width: size, height: size, backgroundColor: 'transparent' }, style]}
    />
  );

  // Ajax necesita conservar el campo blanco que forma parte visual del escudo.
  // Se añade SOLO detrás del Ajax y nunca como fondo rectangular de los demás.
  if (cacheKey === 'ajax') {
    return (
      <View
        style={{
          width: size,
          height: size,
          borderRadius: size / 2,
          backgroundColor: '#ffffff',
          alignItems: 'center',
          justifyContent: 'center',
          overflow: 'hidden',
        }}
      >
        {image}
      </View>
    );
  }

  return image;
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
