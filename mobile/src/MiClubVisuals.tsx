import React from 'react';
import { View } from 'react-native';
import Svg, { Circle, Line, Path, Rect, Polyline } from 'react-native-svg';

export type MiClubIconName =
  | 'roster' | 'economy' | 'treasury' | 'classic' | 'clubValue'
  | 'clubInfo' | 'history' | 'publish' | 'offers' | 'search' | 'resign';

export const MI_CLUB_CARD_BG_DATA_URI =
  'data:image/jpeg;base64,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';

const tones: Record<MiClubIconName, string> = {
  roster: '#238EF1',
  economy: '#B2851F',
  treasury: '#2B6FA5',
  classic: '#A33A35',
  clubValue: '#6251C8',
  clubInfo: '#20A878',
  history: '#5E7285',
  publish: '#207FC9',
  offers: '#207FC9',
  search: '#207FC9',
  resign: '#A92F3A',
};

function IconSvg({ name, size = 24, color = '#F5FAFE' }: { name: MiClubIconName; size?: number; color?: string }) {
  const common = { stroke: color, strokeWidth: 2.2, strokeLinecap: 'round' as const, strokeLinejoin: 'round' as const, fill: 'none' };
  return (
    <Svg width={size} height={size} viewBox="0 0 24 24">
      {name === 'roster' ? <Path d="M8 4 5 6 3 9l3 2v9h12v-9l3-2-2-3-3-2-2 2h-4Z" {...common} /> : null}
      {name === 'economy' ? <>
        <Path d="M5 7c0 1 3 2 7 2s7-1 7-2-3-2-7-2-7 1-7 2Z" {...common} />
        <Path d="M5 7v4c0 1 3 2 7 2s7-1 7-2V7M5 11v4c0 1 3 2 7 2s7-1 7-2v-4M5 15v3c0 1 3 2 7 2s7-1 7-2v-3" {...common} />
      </> : null}
      {name === 'treasury' ? <>
        <Path d="m3 9 9-5 9 5M4 10h16M5 19h14M3 21h18" {...common} />
        <Line x1="7" y1="10" x2="7" y2="19" {...common} /><Line x1="11" y1="10" x2="11" y2="19" {...common} />
        <Line x1="15" y1="10" x2="15" y2="19" {...common} /><Line x1="19" y1="10" x2="19" y2="19" {...common} />
      </> : null}
      {name === 'classic' ? <Path d="M13 2c1 4-2 5-1 8 1 2 4 1 5-1 2 3 4 5 3 8-1 4-4 5-8 5s-7-2-8-6c-1-3 1-6 4-9 0 3 1 4 3 5 0-4 0-7 2-10Z" {...common} /> : null}
      {name === 'clubValue' ? <>
        <Line x1="4" y1="20" x2="21" y2="20" {...common} />
        <Rect x="5" y="13" width="3" height="6" rx="1" {...common} />
        <Rect x="11" y="9" width="3" height="10" rx="1" {...common} />
        <Rect x="17" y="5" width="3" height="14" rx="1" {...common} />
      </> : null}
      {name === 'clubInfo' ? <>
        <Path d="M12 3 20 6v5c0 5-3 8-8 10-5-2-8-5-8-10V6l8-3Z" {...common} />
        <Circle cx="12" cy="9" r="1" fill={color} /><Line x1="12" y1="12" x2="12" y2="16" {...common} />
      </> : null}
      {name === 'history' ? <>
        <Path d="M4 7V3M4 3h4M4 3l2.5 2.5" {...common} />
        <Path d="M5.2 5.2A9 9 0 1 1 3 12" {...common} />
        <Path d="M12 7v5l3 2" {...common} />
      </> : null}
      {name === 'publish' ? <>
        <Path d="M5 3h10l4 4v14H5Z" {...common} /><Path d="M15 3v5h5M8 12h6M8 16h4" {...common} />
        <Path d="M17 17h5M19.5 14.5V19.5" {...common} />
      </> : null}
      {name === 'offers' ? <>
        <Rect x="3" y="5" width="12" height="10" rx="2" {...common} /><Rect x="9" y="9" width="12" height="10" rx="2" {...common} />
        <Path d="M6 12h5m-2-2 2 2-2 2M18 12h-5m2-2-2 2 2 2" {...common} />
      </> : null}
      {name === 'search' ? <>
        <Circle cx="10" cy="10" r="6" {...common} /><Line x1="14.5" y1="14.5" x2="21" y2="21" {...common} />
      </> : null}
      {name === 'resign' ? <>
        <Path d="M4 3h10v18H4Z" {...common} /><Path d="M10 12h11m-4-4 4 4-4 4" {...common} />
      </> : null}
    </Svg>
  );
}

export function MiClubIcon({ name, size = 24, color = '#F5FAFE' }: { name: MiClubIconName; size?: number; color?: string }) {
  return <IconSvg name={name} size={size} color={color} />;
}

export function MiClubIconTile({ name, size = 24, tileSize = 48, tone }: { name: MiClubIconName; size?: number; tileSize?: number; tone?: string }) {
  return (
    <View style={{ width: tileSize, height: tileSize, borderRadius: Math.round(tileSize * 0.27), alignItems: 'center', justifyContent: 'center', backgroundColor: tone || tones[name], borderWidth: 1, borderColor: 'rgba(255,255,255,0.08)' }}>
      <MiClubIcon name={name} size={size} />
    </View>
  );
}
