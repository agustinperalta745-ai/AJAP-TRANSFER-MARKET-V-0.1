import React from 'react';
import { StyleSheet, View } from 'react-native';
import { MaterialCommunityIcons } from '@expo/vector-icons';

export type AjpaIconName =
  | 'home' | 'market' | 'club' | 'league' | 'cups' | 'more'
  | 'profile' | 'settings' | 'admin' | 'notifications'
  | 'transferibles' | 'free-agents' | 'publish-player' | 'offers' | 'negotiations' | 'history'
  | 'squad' | 'tactics' | 'stats' | 'stadium' | 'staff' | 'injuries'
  | 'standings' | 'matches' | 'results' | 'scorers' | 'xi-ideal'
  | 'competitions' | 'bracket' | 'champions'
  | 'news' | 'radio' | 'chat' | 'dice' | 'polls' | 'rivalry'
  | 'objectives' | 'achievements' | 'ranking' | 'favorites' | 'help' | 'logout'
  | 'season' | 'available' | 'closed' | 'recovery';

const ICONS: Record<AjpaIconName, string> = {
  home: 'home-outline',
  market: 'swap-horizontal',
  club: 'shield-account-outline',
  league: 'chart-box-outline',
  cups: 'trophy-outline',
  more: 'dots-horizontal',
  profile: 'account-outline',
  settings: 'cog-outline',
  admin: 'account-group-outline',
  notifications: 'bell-outline',
  transferibles: 'swap-horizontal-bold',
  'free-agents': 'account-plus-outline',
  'publish-player': 'file-document-plus-outline',
  offers: 'gavel',
  negotiations: 'handshake-outline',
  history: 'clipboard-text-clock-outline',
  squad: 'shield-account-outline',
  tactics: 'soccer-field',
  stats: 'chart-line',
  stadium: 'stadium-variant',
  staff: 'account-group-outline',
  injuries: 'medical-bag',
  standings: 'format-list-numbered',
  matches: 'calendar-month-outline',
  results: 'whistle-outline',
  scorers: 'soccer',
  'xi-ideal': 'star-outline',
  competitions: 'trophy-variant-outline',
  bracket: 'tournament',
  champions: 'crown-outline',
  news: 'newspaper-variant-outline',
  radio: 'bullhorn-outline',
  chat: 'chat-outline',
  dice: 'dice-5-outline',
  polls: 'poll',
  rivalry: 'target-account',
  objectives: 'bullseye-arrow',
  achievements: 'medal-outline',
  ranking: 'crown-outline',
  favorites: 'bookmark-outline',
  help: 'help-circle-outline',
  logout: 'logout-variant',
  season: 'calendar-check-outline',
  available: 'check-circle-outline',
  closed: 'close-circle-outline',
  recovery: 'bed-outline',
};

export const AJPA_ICON_TONES: Record<AjpaIconName, string> = {
  home: '#248EF2',
  market: '#3C67D7',
  club: '#25A974',
  league: '#3976DD',
  cups: '#C08A21',
  more: '#405469',
  profile: '#7652C5',
  settings: '#65798C',
  admin: '#65798C',
  notifications: '#C74155',
  transferibles: '#248EF2',
  'free-agents': '#20A77D',
  'publish-player': '#7652C5',
  offers: '#C08A21',
  negotiations: '#405469',
  history: '#65798C',
  squad: '#18B471',
  tactics: '#3F6D9D',
  stats: '#7455C7',
  stadium: '#248EF2',
  staff: '#65798C',
  injuries: '#C74155',
  standings: '#248EF2',
  matches: '#20A77D',
  results: '#7652C5',
  scorers: '#C74155',
  'xi-ideal': '#65798C',
  competitions: '#C08A21',
  bracket: '#248EF2',
  champions: '#7652C5',
  news: '#248EF2',
  radio: '#C08A21',
  chat: '#7652C5',
  dice: '#20A77D',
  polls: '#65798C',
  rivalry: '#C74155',
  objectives: '#248EF2',
  achievements: '#C08A21',
  ranking: '#7652C5',
  favorites: '#20A77D',
  help: '#65798C',
  logout: '#C74155',
  season: '#F3F7FA',
  available: '#35D579',
  closed: '#F35C65',
  recovery: '#74BDF8',
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
    <MaterialCommunityIcons
      name={ICONS[name] as any}
      size={size}
      color={color}
    />
  );
}

export function AjpaIconTile({
  name,
  size = 25,
  tileSize = 50,
  tone,
}: {
  name: AjpaIconName;
  size?: number;
  tileSize?: number;
  tone?: string;
}) {
  const backgroundColor = tone || AJPA_ICON_TONES[name];
  return (
    <View
      style={[
        styles.tile,
        {
          width: tileSize,
          height: tileSize,
          borderRadius: Math.round(tileSize * 0.27),
          backgroundColor,
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
    borderColor: 'rgba(255,255,255,0.08)',
  },
});
