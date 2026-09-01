import React from 'react';
import { Image, Text, View } from 'react-native';
import type { ImageSourcePropType, ImageStyle, StyleProp } from 'react-native';

export type ClubTheme = {
  primary: string;
  secondary: string;
  accent: string;
  soft: string;
};

const BADGES: Record<string, ImageSourcePropType> = {
  ajax: require('../assets/teams/ajax.png'),
  as_monaco: require('../assets/team_badge_test/as_monaco_64.png'),
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

const THEMES: Record<string, ClubTheme> = {
  ajax: { primary: '#D81E34', secondary: '#7A101E', accent: '#F2F4F6', soft: 'rgba(216,30,52,0.18)' },
  as_monaco: { primary: '#D7193F', secondary: '#7D1026', accent: '#F3C04B', soft: 'rgba(215,25,63,0.20)' },
  aston_villa: { primary: '#6A1B3F', secondary: '#341023', accent: '#89CFF0', soft: 'rgba(106,27,63,0.22)' },
  atletico_madrid: { primary: '#D71936', secondary: '#781122', accent: '#2D5FA7', soft: 'rgba(215,25,54,0.20)' },
  benfica: { primary: '#D71920', secondary: '#761017', accent: '#F2C14E', soft: 'rgba(215,25,32,0.20)' },
  bolton_wanderers: { primary: '#173B6C', secondary: '#0B1C34', accent: '#D7282F', soft: 'rgba(23,59,108,0.22)' },
  everton: { primary: '#1B58C7', secondary: '#0D2E6D', accent: '#F4F7FB', soft: 'rgba(27,88,199,0.22)' },
  feyenoord: { primary: '#D71920', secondary: '#171717', accent: '#F3F3F3', soft: 'rgba(215,25,32,0.20)' },
  fiorentina: { primary: '#6E2CA5', secondary: '#35134F', accent: '#F5F1FB', soft: 'rgba(110,44,165,0.22)' },
  fulham: { primary: '#ECECEC', secondary: '#363636', accent: '#D71920', soft: 'rgba(236,236,236,0.12)' },
  galatasaray: { primary: '#C9192D', secondary: '#70101B', accent: '#F5B335', soft: 'rgba(201,25,45,0.22)' },
  lazio: { primary: '#6EBCEB', secondary: '#25577A', accent: '#F4F8FC', soft: 'rgba(110,188,235,0.20)' },
  manchester_city: { primary: '#6CABDD', secondary: '#2C658C', accent: '#F5F8FA', soft: 'rgba(108,171,221,0.22)' },
  middlesbrough: { primary: '#D71920', secondary: '#741015', accent: '#F3F3F3', soft: 'rgba(215,25,32,0.20)' },
  olympique_lyon: { primary: '#174A9C', secondary: '#102C61', accent: '#D7193F', soft: 'rgba(23,74,156,0.22)' },
  olympique_marseille: { primary: '#3FA9E6', secondary: '#1D5E87', accent: '#F6F9FC', soft: 'rgba(63,169,230,0.22)' },
  porto: { primary: '#1D5DA8', secondary: '#0D315F', accent: '#F5F8FC', soft: 'rgba(29,93,168,0.22)' },
  psg: { primary: '#173B73', secondary: '#091F42', accent: '#D7193F', soft: 'rgba(23,59,115,0.24)' },
  real_betis: { primary: '#159447', secondary: '#0B4E28', accent: '#F4F8F5', soft: 'rgba(21,148,71,0.22)' },
  sevilla: { primary: '#D71920', secondary: '#751018', accent: '#F5F5F5', soft: 'rgba(215,25,32,0.20)' },
  torino: { primary: '#7A1E32', secondary: '#3C0D18', accent: '#E7C7A5', soft: 'rgba(122,30,50,0.22)' },
  tottenham_hotspur: { primary: '#183A6E', secondary: '#0B1C38', accent: '#F1F5F9', soft: 'rgba(24,58,110,0.22)' },
  villarreal: { primary: '#D9B61C', secondary: '#7C6510', accent: '#244C87', soft: 'rgba(217,182,28,0.18)' },
  west_ham_united: { primary: '#7A263A', secondary: '#3D111E', accent: '#7FC6E8', soft: 'rgba(122,38,58,0.22)' },
  zaragoza: { primary: '#2A64B7', secondary: '#153664', accent: '#F2F5F8', soft: 'rgba(42,100,183,0.22)' },
};

const normalizeClub = (club: string | null | undefined) =>
  String(club || '')
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, ' ')
    .trim();

const ALIASES: Record<string, string> = {
  'ajax': 'ajax',
  'as monaco': 'as_monaco',
  'as monaco fc': 'as_monaco',
  'monaco': 'as_monaco',
  'aston villa': 'aston_villa',
  'west midlands village': 'aston_villa',
  'atletico madrid': 'atletico_madrid',
  'club atletico de madrid': 'atletico_madrid',
  'benfica': 'benfica',
  'sl benfica': 'benfica',
  'bolton wanderers': 'bolton_wanderers',
  'bolton': 'bolton_wanderers',
  'middlebrook': 'bolton_wanderers',
  'everton': 'everton',
  'merseyside blue': 'everton',
  'feyenoord': 'feyenoord',
  'fiorentina': 'fiorentina',
  'acf fiorentina': 'fiorentina',
  'fulham': 'fulham',
  'west london white': 'fulham',
  'west lindo white': 'fulham',
  'galatasaray': 'galatasaray',
  'lazio': 'lazio',
  'ss lazio': 'lazio',
  'manchester city': 'manchester_city',
  'man city': 'manchester_city',
  'man blue': 'manchester_city',
  'middlesbrough': 'middlesbrough',
  'teesside': 'middlesbrough',
  'olympique de lyon': 'olympique_lyon',
  'olympique lyonnais': 'olympique_lyon',
  'olympique lyon': 'olympique_lyon',
  'lyon': 'olympique_lyon',
  'olympique de marseille': 'olympique_marseille',
  'olympique marseille': 'olympique_marseille',
  'olympique de marsella': 'olympique_marseille',
  'marsella': 'olympique_marseille',
  'marseille': 'olympique_marseille',
  'porto': 'porto',
  'fc porto': 'porto',
  'psg': 'psg',
  'paris saint germain': 'psg',
  'paris saint germain fc': 'psg',
  'real betis': 'real_betis',
  'real betis balompie': 'real_betis',
  'sevilla': 'sevilla',
  'sevilla fc': 'sevilla',
  'torino': 'torino',
  'torino fc': 'torino',
  'tottenham hotspur': 'tottenham_hotspur',
  'tottenham': 'tottenham_hotspur',
  'north east london': 'tottenham_hotspur',
  'villarreal': 'villarreal',
  'villarreal cf': 'villarreal',
  'west ham united': 'west_ham_united',
  'west ham': 'west_ham_united',
  'zaragoza': 'zaragoza',
  'real zaragoza': 'zaragoza',
};

export function getClubAssetKey(club: string | null | undefined): string | null {
  const key = ALIASES[normalizeClub(club)];
  return key && BADGES[key] ? key : null;
}

export function getTeamBadge(club: string | null | undefined): ImageSourcePropType | null {
  const key = getClubAssetKey(club);
  return key ? BADGES[key] : null;
}

export function getClubTheme(club: string | null | undefined): ClubTheme {
  const key = getClubAssetKey(club);
  return (key && THEMES[key]) || {
    primary: '#258BE8',
    secondary: '#103A61',
    accent: '#8AC5FF',
    soft: 'rgba(37,139,232,0.20)',
  };
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
  return (
    <Image
      source={source}
      resizeMode="contain"
      style={[{ width: size, height: size }, style]}
      accessibilityLabel={`Escudo de ${String(club || 'club')}`}
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
