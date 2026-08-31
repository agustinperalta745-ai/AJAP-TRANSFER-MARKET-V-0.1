import React from 'react';
import { Image, Text, View } from 'react-native';
import type { ImageSourcePropType, ImageStyle, StyleProp } from 'react-native';

const RAW = 'https://raw.githubusercontent.com/agustinperalta745-ai/AJAP-TRANSFER-MARKET-V-0.1/main/mobile/assets/teams';
const BADGE_VERSION = '20260831-hq2';
const remote = (file: string): ImageSourcePropType => ({ uri: `${RAW}/${file}?v=${BADGE_VERSION}` });

const BADGES: Record<string, ImageSourcePropType> = {
  ajax: remote('ajax.png'),
  'aston villa': remote('aston_villa.png'),
  'atletico madrid': remote('atletico_madrid.png'),
  benfica: remote('benfica.png'),
  'real betis': remote('real_betis.png'),
  betis: remote('real_betis.png'),
  'bolton wanderers': remote('bolton_wanderers.png'),
  bolton: remote('bolton_wanderers.png'),
  everton: remote('everton.png'),
  feyenoord: remote('feyenoord.png'),
  fiorentina: remote('fiorentina.png'),
  fulham: remote('fulham.png'),
  galatasaray: remote('galatasaray.png'),
  lazio: remote('lazio.png'),
  'ss lazio': remote('lazio.png'),
  lyon: remote('olympique_lyon.png'),
  'olympique lyonnais': remote('olympique_lyon.png'),
  'olympique de lyon': remote('olympique_lyon.png'),
  'manchester city': remote('manchester_city.png'),
  'man city': remote('manchester_city.png'),
  marsella: remote('olympique_marseille.png'),
  marseille: remote('olympique_marseille.png'),
  'olympique de marsella': remote('olympique_marseille.png'),
  'olympique de marseille': remote('olympique_marseille.png'),
  middlesbrough: remote('middlesbrough.png'),
  middle: remote('middlesbrough.png'),
  monaco: remote('as_monaco.png'),
  'as monaco': remote('as_monaco.png'),
  psg: remote('psg.png'),
  'paris saint germain': remote('psg.png'),
  porto: remote('porto.png'),
  'fc porto': remote('porto.png'),
  sevilla: remote('sevilla.png'),
  'sevilla fc': remote('sevilla.png'),
  torino: remote('torino.png'),
  'torino fc': remote('torino.png'),
  tottenham: remote('tottenham_hotspur.png'),
  'tottenham hotspur': remote('tottenham_hotspur.png'),
  villareal: remote('villarreal.png'),
  villarreal: remote('villarreal.png'),
  'villarreal cf': remote('villarreal.png'),
  'west ham': remote('west_ham_united.png'),
  'west ham united': remote('west_ham_united.png'),
  zaragoza: remote('zaragoza.png'),
  'real zaragoza': remote('zaragoza.png'),
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
