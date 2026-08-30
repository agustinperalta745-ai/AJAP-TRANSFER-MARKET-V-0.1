import React from 'react';
import { Image, Text, View } from 'react-native';
import type { ImageSourcePropType, ImageStyle, StyleProp } from 'react-native';

const BADGES: Record<string, ImageSourcePropType> = {
  ajax: require('../assets/teams/ajax.png'),
  'aston villa': require('../assets/teams/aston_villa.png'),
  'atletico madrid': require('../assets/teams/atletico_madrid.png'),
  benfica: require('../assets/teams/benfica.png'),
  'real betis': require('../assets/teams/real_betis.png'),
  betis: require('../assets/teams/real_betis.png'),
  'bolton wanderers': require('../assets/teams/bolton_wanderers.png'),
  bolton: require('../assets/teams/bolton_wanderers.png'),
  everton: require('../assets/teams/everton.png'),
  feyenoord: require('../assets/teams/feyenoord.png'),
  fiorentina: require('../assets/teams/fiorentina.png'),
  fulham: require('../assets/teams/fulham.png'),
  galatasaray: require('../assets/teams/galatasaray.png'),
  lazio: require('../assets/teams/lazio.png'),
  'ss lazio': require('../assets/teams/lazio.png'),
  lyon: require('../assets/teams/olympique_lyon.png'),
  'olympique lyonnais': require('../assets/teams/olympique_lyon.png'),
  'olympique de lyon': require('../assets/teams/olympique_lyon.png'),
  'manchester city': require('../assets/teams/manchester_city.png'),
  'man city': require('../assets/teams/manchester_city.png'),
  marsella: require('../assets/teams/olympique_marseille.png'),
  marseille: require('../assets/teams/olympique_marseille.png'),
  'olympique de marsella': require('../assets/teams/olympique_marseille.png'),
  'olympique de marseille': require('../assets/teams/olympique_marseille.png'),
  middlesbrough: require('../assets/teams/middlesbrough.png'),
  middle: require('../assets/teams/middlesbrough.png'),
  monaco: require('../assets/teams/as_monaco.png'),
  'as monaco': require('../assets/teams/as_monaco.png'),
  psg: require('../assets/teams/psg.png'),
  'paris saint germain': require('../assets/teams/psg.png'),
  porto: require('../assets/teams/porto.png'),
  'fc porto': require('../assets/teams/porto.png'),
  sevilla: require('../assets/teams/sevilla.png'),
  'sevilla fc': require('../assets/teams/sevilla.png'),
  torino: require('../assets/teams/torino.png'),
  'torino fc': require('../assets/teams/torino.png'),
  tottenham: require('../assets/teams/tottenham_hotspur.png'),
  'tottenham hotspur': require('../assets/teams/tottenham_hotspur.png'),
  villareal: require('../assets/teams/villarreal.png'),
  villarreal: require('../assets/teams/villarreal.png'),
  'villarreal cf': require('../assets/teams/villarreal.png'),
  'west ham': require('../assets/teams/west_ham_united.png'),
  'west ham united': require('../assets/teams/west_ham_united.png'),
  zaragoza: require('../assets/teams/zaragoza.png'),
  'real zaragoza': require('../assets/teams/zaragoza.png'),
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
  size = 42,
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
      accessibilityLabel={`Escudo de ${club}`}
      style={[{ width: size, height: size }, style]}
    />
  );
}

export function ClubMatchup({
  home,
  away,
  size = 34,
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
