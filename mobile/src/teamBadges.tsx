import React from 'react';
import { Image, Text, View } from 'react-native';
import type { ImageSourcePropType, ImageStyle, StyleProp } from 'react-native';
import { ATLETICO_BADGE_DATA_URI } from './atleticoBadge';

// AS Monaco conserva su PNG reconstruido durante el build. Atlético de Madrid
// usa el PNG 256x256 renderizado desde el EPS original y embebido en el bundle.
const MONACO_BADGE: ImageSourcePropType = require('../assets/team_badge_test/as_monaco_hd.png');
const ATLETICO_BADGE: ImageSourcePropType = { uri: ATLETICO_BADGE_DATA_URI };

const normalizeClub = (club: string | null | undefined) =>
  String(club || '')
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, ' ')
    .trim();

export function getTeamBadge(club: string | null | undefined): ImageSourcePropType | null {
  const key = normalizeClub(club);
  if (key === 'as monaco' || key === 'monaco' || key === 'as monaco fc') return MONACO_BADGE;
  if (
    key === 'atletico de madrid' ||
    key === 'atletico madrid' ||
    key === 'club atletico de madrid' ||
    key === 'atletico de madrid fc' ||
    key === 'at madrid'
  ) return ATLETICO_BADGE;
  return null;
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
      fadeDuration={0}
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
