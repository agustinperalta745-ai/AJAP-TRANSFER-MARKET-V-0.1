import React from 'react';
import { Image, Text, View } from 'react-native';
import type { ImageSourcePropType, ImageStyle, StyleProp } from 'react-native';
import { ATLETICO_BADGE_DATA_URI } from './atleticoBadge';

// Volvemos al sistema que daba la mejor nitidez: los escudos históricos se
// cargan desde sus PNG originales del repositorio, sin que AAPT/Pillow los
// vuelva a codificar. Sólo Mónaco y Atlético usan fuentes HD dedicadas.
const RAW = 'https://raw.githubusercontent.com/agustinperalta745-ai/AJAP-TRANSFER-MARKET-V-0.1/main/mobile/assets/teams';
const BADGE_VERSION = '20260901-hq-restore';
const remote = (file: string): ImageSourcePropType => ({ uri: `${RAW}/${file}?v=${BADGE_VERSION}` });
const MONACO_BADGE: ImageSourcePropType = require('../assets/team_badge_test/as_monaco_hd.png');
const ATLETICO_BADGE: ImageSourcePropType = { uri: ATLETICO_BADGE_DATA_URI };

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
  ajax: remote('ajax.png'),
  monaco: MONACO_BADGE,
  'as monaco': MONACO_BADGE,
  'as monaco fc': MONACO_BADGE,
  'aston villa': remote('aston_villa.png'),
  'atletico madrid': ATLETICO_BADGE,
  'atletico de madrid': ATLETICO_BADGE,
  'club atletico de madrid': ATLETICO_BADGE,
  'atletico de madrid fc': ATLETICO_BADGE,
  'at madrid': ATLETICO_BADGE,
  benfica: remote('benfica.png'),
  'sl benfica': remote('benfica.png'),
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

  // El escudo clásico de Ajax depende de su campo blanco. El PNG original es
  // transparente y sobre el panel azul oscuro desaparecía esa parte; sólo Ajax
  // recibe este disco blanco, sin modificar el archivo ni los demás clubes.
  if (key === 'ajax') {
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
        accessibilityLabel={`Escudo de ${String(club || 'Ajax')}`}
      >
        <Image
          source={source}
          resizeMode="contain"
          fadeDuration={0}
          style={[{ width: size * 0.96, height: size * 0.96 }, style]}
        />
      </View>
    );
  }

  return (
    <Image
      source={source}
      resizeMode="contain"
      fadeDuration={0}
      accessibilityLabel={`Escudo de ${String(club || 'club')}`}
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
