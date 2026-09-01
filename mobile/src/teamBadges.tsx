import React from 'react';
import { Image, Text, View } from 'react-native';
import type { ImageSourcePropType, ImageStyle, StyleProp } from 'react-native';

// Mapeo completo de escudos locales. Mónaco conserva el PNG HD reconstruido
// durante el build; el resto usa los assets ya validados que venía mostrando
// correctamente la app.
const ASSETS = {
  ajax: require('../assets/teams/ajax.png'),
  as_monaco: require('../assets/team_badge_test/as_monaco_hd.png'),
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
  const source = getTeamBadge(club);
  if (!source) return null;
  const key = normalizeClub(club);
  const ajaxWhiteField: ImageStyle | null = key === 'ajax'
    ? { backgroundColor: '#ffffff', borderRadius: size / 2 }
    : null;

  return (
    <Image
      source={source}
      resizeMode="contain"
      fadeDuration={0}
      accessibilityLabel={`Escudo de ${String(club || 'club')}`}
      style={[{ width: size, height: size }, ajaxWhiteField, style]}
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
  const homeBadge = getTeamBadge(home);
  const awayBadge = getTeamBadge(away);
  if (!homeBadge && !awayBadge) return null;

  return (
    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginTop: 8 }}>
      {homeBadge ? <ClubBadge club={home} size={size} /> : null}
      <Text style={{ color: '#92a0ad', fontWeight: '800' }}>VS</Text>
      {awayBadge ? <ClubBadge club={away} size={size} /> : null}
    </View>
  );
}
