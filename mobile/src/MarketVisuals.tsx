import React from 'react';
import { View } from 'react-native';
import {
  ArrowRightLeft,
  Briefcase,
  History,
  Megaphone,
  Search,
  TrendingUp,
  UserPlus,
  Zap,
  type LucideIcon,
} from 'lucide-react-native';

export const MARKET_STATUS_BG = require('../assets/market/market-status.jpg');
export const MARKET_SEARCH_BG = require('../assets/market/search-player.jpg');
export const MARKET_HISTORY_BG = require('../assets/market/history.jpg');
export const MARKET_CLAUSE_BG = require('../assets/market/clausulazo.jpg');

export type MarketIconName =
  | 'status'
  | 'transfer'
  | 'offers'
  | 'publish'
  | 'freeAgents'
  | 'search'
  | 'history'
  | 'clause';

const ICONS: Record<MarketIconName, LucideIcon> = {
  status: TrendingUp,
  transfer: ArrowRightLeft,
  offers: Briefcase,
  publish: Megaphone,
  freeAgents: UserPlus,
  search: Search,
  history: History,
  clause: Zap,
};

const TONES: Record<MarketIconName, string> = {
  status: '#18B987',
  transfer: '#2688EF',
  offers: '#346DE6',
  publish: '#2688EF',
  freeAgents: '#2A80E8',
  search: '#0A3859',
  history: '#0A3859',
  clause: '#6B1722',
};

export function MarketIcon({
  name,
  size = 24,
  color = '#FFFFFF',
}: {
  name: MarketIconName;
  size?: number;
  color?: string;
}) {
  const Icon = ICONS[name];
  return <Icon size={size} color={color} strokeWidth={2.15} />;
}

export function MarketIconTile({
  name,
  tileSize = 48,
  size = 24,
  tone,
  iconColor = '#FFFFFF',
}: {
  name: MarketIconName;
  tileSize?: number;
  size?: number;
  tone?: string;
  iconColor?: string;
}) {
  const bg = tone ?? TONES[name];
  return (
    <View
      style={{
        width: tileSize,
        height: tileSize,
        borderRadius: Math.round(tileSize * 0.26),
        backgroundColor: bg,
        borderWidth: 1,
        borderColor: name === 'clause' ? '#B63747' : '#2A88C8',
        alignItems: 'center',
        justifyContent: 'center',
      }}
    >
      <MarketIcon name={name} size={size} color={iconColor} />
    </View>
  );
}
