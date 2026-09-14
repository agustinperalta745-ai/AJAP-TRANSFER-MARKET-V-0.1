import React from 'react';
import Svg, {
  Circle,
  Defs,
  Ellipse,
  G,
  Line,
  LinearGradient,
  Path,
  Polygon,
  RadialGradient,
  Rect,
  Stop,
} from 'react-native-svg';

const BLUE = '#36aaff';
const CYAN = '#8bd9ff';
const DEEP = '#020914';
const PANEL = '#061728';
const GOLD = '#d8a63d';

function Stadium({ id, withPitch = true }: { id: string; withPitch?: boolean }) {
  return (
    <>
      <Defs>
        <LinearGradient id={`${id}-sky`} x1="0" y1="0" x2="0" y2="1">
          <Stop offset="0" stopColor="#010610" />
          <Stop offset="0.55" stopColor="#071a2c" />
          <Stop offset="1" stopColor="#03101d" />
        </LinearGradient>
        <LinearGradient id={`${id}-pitch`} x1="0" y1="0" x2="0" y2="1">
          <Stop offset="0" stopColor="#0b4e43" />
          <Stop offset="1" stopColor="#03281f" />
        </LinearGradient>
        <RadialGradient id={`${id}-glow`} cx="50%" cy="50%" rx="50%" ry="50%">
          <Stop offset="0" stopColor="#7ed2ff" stopOpacity="0.95" />
          <Stop offset="0.22" stopColor="#3e9fe0" stopOpacity="0.34" />
          <Stop offset="1" stopColor="#0b2e4d" stopOpacity="0" />
        </RadialGradient>
        <LinearGradient id={`${id}-shade`} x1="0" y1="0" x2="1" y2="0">
          <Stop offset="0" stopColor="#01060d" stopOpacity="0.86" />
          <Stop offset="0.58" stopColor="#01060d" stopOpacity="0.26" />
          <Stop offset="1" stopColor="#01060d" stopOpacity="0.08" />
        </LinearGradient>
      </Defs>
      <Rect width="1920" height="1080" fill={`url(#${id}-sky)`} />
      <Path d="M0 330 Q960 180 1920 330 L1920 690 Q960 540 0 690 Z" fill="#06182a" />
      <Path d="M0 390 Q960 250 1920 390" stroke="#1a4e72" strokeWidth="5" opacity="0.58" />
      <Path d="M0 475 Q960 345 1920 475" stroke="#123b5a" strokeWidth="4" opacity="0.55" />
      <Path d="M0 560 Q960 445 1920 560" stroke="#0f334e" strokeWidth="4" opacity="0.5" />
      {Array.from({ length: 26 }).map((_, i) => {
        const x = 40 + i * 74;
        return <Circle key={`${id}-crowd-${i}`} cx={x} cy={460 + ((i * 31) % 135)} r={4 + (i % 3)} fill="#9edcff" opacity={0.12 + (i % 4) * 0.035} />;
      })}
      {Array.from({ length: 14 }).map((_, i) => {
        const x = 75 + i * 137;
        return (
          <G key={`${id}-light-${i}`}>
            <Circle cx={x} cy="282" r="62" fill={`url(#${id}-glow)`} />
            <Circle cx={x} cy="282" r="6" fill="#f6fbff" opacity="0.95" />
          </G>
        );
      })}
      <Polygon points="120,0 250,0 820,740 650,740" fill="#4ab6ff" opacity="0.035" />
      <Polygon points="610,0 735,0 1030,740 900,740" fill="#4ab6ff" opacity="0.028" />
      <Polygon points="1300,0 1425,0 1180,740 1050,740" fill="#4ab6ff" opacity="0.032" />
      <Polygon points="1690,0 1810,0 1330,740 1190,740" fill="#4ab6ff" opacity="0.032" />
      {withPitch ? (
        <>
          <Rect y="690" width="1920" height="390" fill={`url(#${id}-pitch)`} />
          {Array.from({ length: 10 }).map((_, i) => <Rect key={`${id}-stripe-${i}`} x={i * 192} y="690" width="96" height="390" fill="#0b5b4b" opacity="0.18" />)}
          <Line x1="0" y1="710" x2="1920" y2="710" stroke="#d9ffff" strokeOpacity="0.38" strokeWidth="4" />
          <Line x1="960" y1="690" x2="960" y2="1080" stroke="#d9ffff" strokeOpacity="0.24" strokeWidth="3" />
          <Ellipse cx="960" cy="870" rx="150" ry="105" fill="none" stroke="#d9ffff" strokeOpacity="0.2" strokeWidth="3" />
        </>
      ) : null}
      <Rect width="1920" height="1080" fill={`url(#${id}-shade)`} />
    </>
  );
}

function Football({ cx, cy, r, id }: { cx: number; cy: number; r: number; id: string }) {
  const pts = Array.from({ length: 5 }).map((_, i) => {
    const a = -Math.PI / 2 + (Math.PI * 2 * i) / 5;
    return `${cx + Math.cos(a) * r * 0.28},${cy + Math.sin(a) * r * 0.28}`;
  }).join(' ');
  return (
    <G>
      <Defs>
        <RadialGradient id={`${id}-ball`} cx="36%" cy="26%" rx="64%" ry="72%">
          <Stop offset="0" stopColor="#183d5d" />
          <Stop offset="0.55" stopColor="#071b2e" />
          <Stop offset="1" stopColor="#010912" />
        </RadialGradient>
        <RadialGradient id={`${id}-ballglow`} cx="50%" cy="50%" rx="50%" ry="50%">
          <Stop offset="0" stopColor="#39aaff" stopOpacity="0.22" />
          <Stop offset="1" stopColor="#39aaff" stopOpacity="0" />
        </RadialGradient>
      </Defs>
      <Circle cx={cx} cy={cy} r={r * 1.14} fill={`url(#${id}-ballglow)`} />
      <Circle cx={cx} cy={cy} r={r} fill={`url(#${id}-ball)`} stroke="#48b4fb" strokeOpacity="0.52" strokeWidth={6} />
      <Polygon points={pts} fill="#0d2d49" stroke="#70caff" strokeOpacity="0.72" strokeWidth={5} />
      {Array.from({ length: 5 }).map((_, i) => {
        const a = -Math.PI / 2 + (Math.PI * 2 * i) / 5;
        const x1 = cx + Math.cos(a) * r * 0.28;
        const y1 = cy + Math.sin(a) * r * 0.28;
        const x2 = cx + Math.cos(a) * r * 0.82;
        const y2 = cy + Math.sin(a) * r * 0.82;
        return <Line key={`${id}-seam-${i}`} x1={x1} y1={y1} x2={x2} y2={y2} stroke="#4a9cd0" strokeOpacity="0.68" strokeWidth={5} />;
      })}
      <Path d={`M ${cx-r*0.75} ${cy-r*0.18} Q ${cx-r*0.2} ${cy-r*0.62} ${cx+r*0.33} ${cy-r*0.48}`} fill="none" stroke="#7bd0ff" strokeOpacity="0.25" strokeWidth={5} />
      <Path d={`M ${cx-r*0.58} ${cy+r*0.48} Q ${cx} ${cy+r*0.18} ${cx+r*0.66} ${cy+r*0.45}`} fill="none" stroke="#4287b5" strokeOpacity="0.42" strokeWidth={4} />
    </G>
  );
}

function Trophy({ cx, cy, scale = 1, id }: { cx: number; cy: number; scale?: number; id: string }) {
  const w = 210 * scale;
  const h = 300 * scale;
  return (
    <G>
      <Defs>
        <LinearGradient id={`${id}-gold`} x1="0" y1="0" x2="1" y2="1">
          <Stop offset="0" stopColor="#fff0a3" />
          <Stop offset="0.38" stopColor="#d8a63d" />
          <Stop offset="0.75" stopColor="#8a5b16" />
          <Stop offset="1" stopColor="#f4d977" />
        </LinearGradient>
        <RadialGradient id={`${id}-trophyglow`} cx="50%" cy="50%" rx="50%" ry="50%">
          <Stop offset="0" stopColor="#f0bc48" stopOpacity="0.23" />
          <Stop offset="1" stopColor="#f0bc48" stopOpacity="0" />
        </RadialGradient>
      </Defs>
      <Circle cx={cx} cy={cy-h*0.08} r={w*0.9} fill={`url(#${id}-trophyglow)`} />
      <Path d={`M ${cx-w*0.42} ${cy-h*0.50} L ${cx+w*0.42} ${cy-h*0.50} L ${cx+w*0.31} ${cy-h*0.02} Q ${cx+w*0.18} ${cy+h*0.13} ${cx} ${cy+h*0.16} Q ${cx-w*0.18} ${cy+h*0.13} ${cx-w*0.31} ${cy-h*0.02} Z`} fill={`url(#${id}-gold)`} stroke="#ffe8a0" strokeWidth={5} />
      <Path d={`M ${cx-w*0.40} ${cy-h*0.40} C ${cx-w*0.95} ${cy-h*0.42}, ${cx-w*0.95} ${cy+h*0.04}, ${cx-w*0.32} ${cy+h*0.04}`} fill="none" stroke="#e0b45a" strokeWidth={18*scale} strokeLinecap="round" />
      <Path d={`M ${cx+w*0.40} ${cy-h*0.40} C ${cx+w*0.95} ${cy-h*0.42}, ${cx+w*0.95} ${cy+h*0.04}, ${cx+w*0.32} ${cy+h*0.04}`} fill="none" stroke="#e0b45a" strokeWidth={18*scale} strokeLinecap="round" />
      <Rect x={cx-w*0.07} y={cy+h*0.15} width={w*0.14} height={h*0.28} rx={8*scale} fill="#c58b27" />
      <Rect x={cx-w*0.36} y={cy+h*0.42} width={w*0.72} height={h*0.13} rx={12*scale} fill="#07111b" stroke="#f0cb6f" strokeWidth={5} />
    </G>
  );
}

export function HeroArt() {
  return (
    <Svg width="100%" height="100%" viewBox="0 0 1920 1080" preserveAspectRatio="xMidYMid slice">
      <Stadium id="hero" />
      <Football cx={1510} cy={650} r={315} id="hero" />
      <Rect x="0" y="0" width="1180" height="1080" fill="#010710" opacity="0.32" />
      <Rect x="0" y="0" width="1920" height="1080" fill="none" stroke={BLUE} strokeOpacity="0.82" strokeWidth="5" rx="54" />
    </Svg>
  );
}

export function MarketArt() {
  return (
    <Svg width="100%" height="100%" viewBox="0 0 1920 1080" preserveAspectRatio="xMidYMid slice">
      <Stadium id="market" />
      <Rect width="900" height="1080" fill="#01060c" opacity="0.58" />
      <Path d="M1030 365 H1430 V260 L1730 480 L1430 700 V595 H1030 Z" fill="#65c8ff" opacity="0.86" />
      <Path d="M1590 760 H1190 V865 L890 645 L1190 425 V530 H1590 Z" fill="#2f8cc7" opacity="0.78" />
      <Circle cx="1420" cy="530" r="360" fill="#36aaff" opacity="0.05" />
      <Rect width="1920" height="1080" fill="none" stroke={BLUE} strokeOpacity="0.76" strokeWidth="5" rx="54" />
    </Svg>
  );
}

export function LeagueArt() {
  return (
    <Svg width="100%" height="100%" viewBox="0 0 1920 1080" preserveAspectRatio="xMidYMid slice">
      <Stadium id="league" />
      <Rect x="85" y="235" width="430" height="50" rx="20" fill="#2c7fb2" opacity="0.46" />
      <Rect x="85" y="330" width="355" height="50" rx="20" fill="#24709f" opacity="0.38" />
      <Rect x="85" y="425" width="285" height="50" rx="20" fill="#1b628d" opacity="0.34" />
      <Path d="M990 210 V740" stroke="#4cb7fa" strokeOpacity="0.18" strokeWidth="8" />
      <Path d="M1160 210 V740" stroke="#4cb7fa" strokeOpacity="0.12" strokeWidth="8" />
      <Rect width="1920" height="1080" fill="none" stroke={BLUE} strokeOpacity="0.76" strokeWidth="5" rx="54" />
    </Svg>
  );
}

export function VitrinaArt() {
  return (
    <Svg width="100%" height="100%" viewBox="0 0 1920 1080" preserveAspectRatio="xMidYMid slice">
      <Defs>
        <LinearGradient id="cabinet" x1="0" y1="0" x2="1" y2="1">
          <Stop offset="0" stopColor="#03070d" />
          <Stop offset="0.55" stopColor="#111b24" />
          <Stop offset="1" stopColor="#07101a" />
        </LinearGradient>
        <LinearGradient id="glass" x1="0" y1="0" x2="1" y2="0">
          <Stop offset="0" stopColor="#4fa6d8" stopOpacity="0.04" />
          <Stop offset="0.5" stopColor="#d9f4ff" stopOpacity="0.10" />
          <Stop offset="1" stopColor="#4fa6d8" stopOpacity="0.03" />
        </LinearGradient>
      </Defs>
      <Rect width="1920" height="1080" fill="url(#cabinet)" />
      <Rect x="80" y="230" width="1760" height="24" rx="10" fill="#6e4c20" opacity="0.72" />
      <Rect x="80" y="760" width="1760" height="24" rx="10" fill="#6e4c20" opacity="0.72" />
      <Rect x="125" y="120" width="1670" height="760" rx="40" fill="url(#glass)" stroke="#285a76" strokeOpacity="0.5" strokeWidth="4" />
      <Trophy cx={1010} cy={540} scale={1.45} id="main-trophy" />
      <Trophy cx={560} cy={590} scale={0.82} id="left-trophy" />
      <Trophy cx={1455} cy={590} scale={0.82} id="right-trophy" />
      <Circle cx="1010" cy="500" r="380" fill={GOLD} opacity="0.035" />
      <Rect width="1920" height="1080" fill="none" stroke={BLUE} strokeOpacity="0.72" strokeWidth="5" rx="54" />
    </Svg>
  );
}

export function CupArt() {
  const star = '1370,225 1440,420 1650,425 1480,555 1540,755 1370,635 1200,755 1260,555 1090,425 1300,420';
  return (
    <Svg width="100%" height="100%" viewBox="0 0 1920 1080" preserveAspectRatio="xMidYMid slice">
      <Stadium id="cup" />
      <Football cx={1425} cy={590} r={300} id="cup" />
      <Polygon points={star} fill="#4eaef1" opacity="0.15" stroke="#8cd6ff" strokeOpacity="0.4" strokeWidth="5" />
      <Circle cx="1425" cy="590" r="390" fill="#2f9de5" opacity="0.045" />
      <Rect width="1920" height="1080" fill="none" stroke={BLUE} strokeOpacity="0.76" strokeWidth="5" rx="54" />
    </Svg>
  );
}

export function ResultsArt() {
  return (
    <Svg width="100%" height="100%" viewBox="0 0 1920 1080" preserveAspectRatio="xMidYMid slice">
      <Stadium id="results" />
      <Rect x="1185" y="285" width="230" height="310" rx="38" fill="#020812" stroke="#5bbdff" strokeOpacity="0.7" strokeWidth="5" />
      <Rect x="1480" y="285" width="230" height="310" rx="38" fill="#020812" stroke="#5bbdff" strokeOpacity="0.7" strokeWidth="5" />
      <Path d="M1245 355 H1360 V405 H1245 V455 H1360 V505 H1245" fill="none" stroke="#b9eaff" strokeWidth="34" strokeLinecap="round" strokeLinejoin="round" />
      <Path d="M1565 355 H1625 V505" fill="none" stroke="#b9eaff" strokeWidth="34" strokeLinecap="round" />
      <Rect x="1425" y="420" width="40" height="18" rx="9" fill="#74caff" />
      <Rect width="1920" height="1080" fill="none" stroke={BLUE} strokeOpacity="0.76" strokeWidth="5" rx="54" />
    </Svg>
  );
}

export function CountdownArt() {
  return (
    <Svg width="100%" height="100%" viewBox="0 0 1920 1080" preserveAspectRatio="xMidYMid slice">
      <Stadium id="countdown" withPitch={false} />
      <Rect width="1920" height="1080" fill="#020913" opacity="0.42" />
      <Circle cx="1450" cy="320" r="380" fill="#36aaff" opacity="0.05" />
      <Rect width="1920" height="1080" fill="none" stroke={BLUE} strokeOpacity="0.72" strokeWidth="5" rx="54" />
    </Svg>
  );
}

export function HomeBackdrop() {
  return (
    <Svg width="100%" height="100%" viewBox="0 0 1080 1920" preserveAspectRatio="xMidYMid slice">
      <Defs>
        <LinearGradient id="home-bg" x1="0" y1="0" x2="0" y2="1">
          <Stop offset="0" stopColor="#01060d" />
          <Stop offset="0.46" stopColor="#03101c" />
          <Stop offset="1" stopColor="#01060b" />
        </LinearGradient>
        <RadialGradient id="home-glow" cx="50%" cy="50%" rx="50%" ry="50%">
          <Stop offset="0" stopColor="#1597ef" stopOpacity="0.14" />
          <Stop offset="1" stopColor="#1597ef" stopOpacity="0" />
        </RadialGradient>
      </Defs>
      <Rect width="1080" height="1920" fill="url(#home-bg)" />
      <Circle cx="900" cy="320" r="430" fill="url(#home-glow)" />
      <Circle cx="160" cy="1160" r="470" fill="url(#home-glow)" opacity="0.52" />
      <Path d="M-60 1520 Q540 1320 1140 1520" stroke="#36aaff" strokeOpacity="0.08" strokeWidth="4" fill="none" />
      <Path d="M-80 1650 Q540 1450 1160 1650" stroke="#36aaff" strokeOpacity="0.05" strokeWidth="3" fill="none" />
    </Svg>
  );
}
