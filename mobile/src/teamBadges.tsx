import React from 'react';
import type { ImageSourcePropType, ImageStyle, StyleProp } from 'react-native';

// Escudos deshabilitados temporalmente en AJPA Mobile.
// La app mantiene toda la funcionalidad sin depender de assets de clubes.
export function getTeamBadge(_club: string | null | undefined): ImageSourcePropType | null {
  return null;
}

export function ClubBadge({
  club: _club,
  size: _size = 72,
  style: _style,
}: {
  club: string | null | undefined;
  size?: number;
  style?: StyleProp<ImageStyle>;
}) {
  return null;
}

export function ClubMatchup({
  home: _home,
  away: _away,
  size: _size = 58,
}: {
  home: string | null | undefined;
  away: string | null | undefined;
  size?: number;
}) {
  return null;
}
