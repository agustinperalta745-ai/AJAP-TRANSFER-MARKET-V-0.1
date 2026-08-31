import React from 'react';
import { Image, Text, View } from 'react-native';
import type { ImageSourcePropType, ImageStyle, StyleProp } from 'react-native';

// All crests are loaded remotely from main so Android AAPT2 never compiles them as bundled resources.
const RAW_MAIN = 'https://raw.githubusercontent.com/agustinperalta745-ai/AJAP-TRANSFER-MARKET-V-0.1/main/mobile/assets/teams';
const BADGE_VERSION = '20260831-all-remote';
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

const normalizeClub = (club: string | null | undefined) =>
  String(club || '')
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .replace(/[._-]+/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();

export function getTeamBadge(club: string | null | undefined): ImageSourcePropType | null {
  const key = normalizeClub(club);
  if (!key || key === 'jugador libre') return null;
  return BADGES[key] ?? null;
}

export function ClubBadge({
  club,
  size = 48,
  style,
}: {
  club: string | null | undefined;
  size?: number;
  style?: StyleProp<ImageStyle>;
}) {
  const source = getTeamBadge(club);
  if (!source) return null;
  return (
    <Image
      source={source}
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
  size = 38,
}: {
  home: string | null | undefined;
  away: string | null | undefined;
  size?: number;
}) {
  if (!home && !away) return null;
  return (
    <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginTop: 8 }}>
      <ClubBadge club={home} size={size} />
      <Text style={{ color: '#8ac5ff', fontWeight: '900', fontSize: 11 }}>VS</Text>
      <ClubBadge club={away} size={size} />
    </View>
  );
}
