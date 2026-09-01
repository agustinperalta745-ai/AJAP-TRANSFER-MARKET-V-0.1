import React from 'react';
import { Image, StyleSheet, View } from 'react-native';
import { ClubBadge } from './teamBadges';

// A smooth alpha mask keeps gradients consistent on Android without native dependencies.
const GLOW = { uri: 'data:image/png;base64,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' };
const THEMES: [RegExp, string, string][] = [
  [/monaco/, '#c51239', '#d8b753'],
  [/ajax/, '#c81937', '#eeeeee'],
  [/atletico/, '#c9233f', '#d7b75c'],
  [/aston.*villa/, '#8e244c', '#85c9ec'],
  [/benfica/, '#c9233f', '#d8b753'],
  [/bolton/, '#e0e6ed', '#679cd7'],
  [/everton/, '#165cba', '#aac9ee'],
  [/feyenoord/, '#c72534', '#eeeeee'],
  [/fiorentina/, '#7139a8', '#c1a0e5'],
  [/fulham/, '#e0e6ed', '#b92d3c'],
  [/galatasaray/, '#a82130', '#f4b236'],
  [/lazio/, '#6bb6d7', '#daeef4'],
  [/manchester.*city/, '#69add5', '#cee8f4'],
  [/middlesbrough/, '#c9283a', '#eeeeee'],
  [/lyon/, '#255fae', '#db4053'],
  [/marseille|marsella/, '#168fc2', '#c5e5f4'],
  [/porto/, '#205bc0', '#d2e3ff'],
  [/psg|paris/, '#163f8b', '#d83b52'],
  [/betis/, '#219362', '#e0eee6'],
  [/sevilla/, '#c72b3d', '#eeeeee'],
  [/torino/, '#812d3e', '#d5b876'],
  [/tottenham/, '#294878', '#dce5ef'],
  [/villarreal/, '#dac136', '#e8d878'],
  [/west.*ham/, '#832748', '#83badb'],
  [/zaragoza/, '#2d64be', '#d5b65a'],
];
export function teamCardTheme(club: string | null | undefined) {
  const key = (club ?? '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase();
  const entry = THEMES.find(([pattern]) => pattern.test(key));
  return { color: entry?.[1] ?? '#2d92ff', border: entry?.[2] ?? '#71c4ff' };
}
export function SoftCardGlow({ color = '#2d92ff', opacity = 0.22 }: { color?: string; opacity?: number }) {
  return <View pointerEvents="none" accessible={false} style={StyleSheet.absoluteFill}>
    <Image source={GLOW} resizeMode="stretch" fadeDuration={0} style={[StyleSheet.absoluteFill, { width: '100%', height: '100%', tintColor: color, opacity }]} />
  </View>;
}
export function TeamCardBackdrop({ club }: { club: string | null | undefined }) {
  return <View pointerEvents="none" accessible={false} accessibilityElementsHidden importantForAccessibility="no-hide-descendants" style={StyleSheet.absoluteFill}>
    <SoftCardGlow color={teamCardTheme(club).color} opacity={0.95} />
    <View style={{ position: 'absolute', right: -8, top: -8, bottom: -8, justifyContent: 'center', opacity: 0.07 }}>
      <ClubBadge club={club} size={154} />
    </View>
  </View>;
}
