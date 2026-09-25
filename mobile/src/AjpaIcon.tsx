import React from 'react';
import { Image, ImageSourcePropType, StyleSheet, View } from 'react-native';

export type AjpaIconName =
  | 'home' | 'market' | 'briefcase' | 'club' | 'league' | 'cups' | 'more'
  | 'profile' | 'admin' | 'season' | 'closed' | 'competitions';

export const AJPA_ICON_TONES: Record<AjpaIconName, string> = {
  home: '#248EF2',
  market: '#3C67D7',
  briefcase: '#3C67D7',
  club: '#25A974',
  league: '#3976DD',
  cups: '#C08A21',
  more: '#405469',
  profile: '#7652C5',
  admin: '#65798C',
  season: '#F3F7FA',
  closed: '#F35C65',
  competitions: '#C08A21',
};

const ICONS: Record<AjpaIconName, ImageSourcePropType> = {
  home: require('../assets/ui-icons/home.png'),
  market: require('../assets/ui-icons/market.png'),
  briefcase: require('../assets/ui-icons/market.png'),
  club: require('../assets/ui-icons/club.png'),
  league: require('../assets/ui-icons/league.png'),
  cups: require('../assets/ui-icons/cups.png'),
  more: require('../assets/ui-icons/more.png'),
  profile: require('../assets/ui-icons/profile.png'),
  admin: require('../assets/ui-icons/admin.png'),
  season: require('../assets/ui-icons/season.png'),
  closed: require('../assets/ui-icons/closed.png'),
  competitions: require('../assets/ui-icons/cups.png'),
};

export function AjpaIcon({
  name,
  size = 24,
  color = '#F5FAFE',
}: {
  name: AjpaIconName;
  size?: number;
  color?: string;
}) {
  return (
    <Image
      source={ICONS[name]}
      resizeMode="contain"
      style={{ width: size, height: size, tintColor: color }}
    />
  );
}

export function AjpaIconTile({
  name,
  size = 22,
  tileSize = 42,
  tone,
}: {
  name: AjpaIconName;
  size?: number;
  tileSize?: number;
  tone?: string;
}) {
  return (
    <View
      style={[
        styles.tile,
        {
          width: tileSize,
          height: tileSize,
          borderRadius: Math.round(tileSize * 0.27),
          backgroundColor: tone || AJPA_ICON_TONES[name],
        },
      ]}
    >
      <AjpaIcon name={name} size={size} />
    </View>
  );
}

const styles = StyleSheet.create({
  tile: {
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 1,
    borderColor: 'rgba(255,255,255,0.07)',
  },
});
