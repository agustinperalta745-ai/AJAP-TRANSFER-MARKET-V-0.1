import fs from 'node:fs';

// Keep the large background shield treatment consistent across every club, but
// give Ajax/Tottenham a tiny visibility correction because their artwork loses
// contrast against their own card gradients. This is intentionally opacity-only:
// no extra halo, border or different sizing, so they still match the rest.
const themePath = new URL('../src/TeamCardTheme.tsx', import.meta.url);
let theme = fs.readFileSync(themePath, 'utf8');
const oldBackdrop = `export function TeamCardBackdrop({ club }: { club: string | null | undefined }) {
  return <View pointerEvents="none" accessible={false} accessibilityElementsHidden importantForAccessibility="no-hide-descendants" style={StyleSheet.absoluteFill}>
    <SoftCardGlow color={teamCardTheme(club).color} opacity={0.95} />
    <View style={{ position: 'absolute', right: -8, top: -8, bottom: -8, justifyContent: 'center', opacity: 0.07 }}>
      <ClubBadge club={club} size={154} />
    </View>
  </View>;
}`;
const newBackdrop = `export function TeamCardBackdrop({ club }: { club: string | null | undefined }) {
  const key = (club ?? '').normalize('NFD').replace(/[\\u0300-\\u036f]/g, '').toLowerCase();
  const badgeOpacity = /ajax/.test(key) ? 0.105 : /tottenham/.test(key) ? 0.10 : 0.07;
  return <View pointerEvents="none" accessible={false} accessibilityElementsHidden importantForAccessibility="no-hide-descendants" style={StyleSheet.absoluteFill}>
    <SoftCardGlow color={teamCardTheme(club).color} opacity={0.95} />
    <View style={{ position: 'absolute', right: -8, top: -8, bottom: -8, justifyContent: 'center', opacity: badgeOpacity }}>
      <ClubBadge club={club} size={154} />
    </View>
  </View>;
}`;
if (theme.includes(oldBackdrop)) {
  theme = theme.replace(oldBackdrop, newBackdrop);
  fs.writeFileSync(themePath, theme);
  console.log('Ajax/Tottenham background badges: subtle visibility correction applied.');
} else if (!theme.includes('const badgeOpacity = /ajax/.test(key) ? 0.105 : /tottenham/.test(key) ? 0.10 : 0.07;')) {
  throw new Error('Team card gradients: TeamCardBackdrop shape changed; visibility correction was not applied.');
}

const path = new URL('../src/BotParityAppV2.tsx', import.meta.url);
let ui = fs.readFileSync(path, 'utf8');
if (ui.includes('// team-card-gradients applied')) process.exit(0);
function replace(from, to) {
  if (!ui.includes(from)) throw new Error(`Team card gradients: missing ${from.slice(0, 100)}`);
  ui = ui.replace(from, to);
}
replace("import { ClubBadge } from './teamBadges';", "import { ClubBadge } from './teamBadges';\nimport { SoftCardGlow, TeamCardBackdrop, teamCardTheme } from './TeamCardTheme';");
const start = ui.indexOf('function HeroClubCard(');
const end = ui.indexOf('\nfunction WideTile(', start);
if (start < 0 || end < 0) throw new Error('Team card gradients: HeroClubCard missing');
let hero = ui.slice(start, end);
hero = hero.replace('  return (', '  const theme = teamCardTheme(club);\n  return (');
hero = hero.replace('s.heroClubCard, pressed', "s.heroClubCard, { borderColor: theme.border, borderTopColor: theme.border, borderBottomColor: theme.border, borderLeftColor: theme.border, borderRightColor: theme.border }, pressed");
hero = hero.replace('<SurfaceDepth strong />', '<TeamCardBackdrop club={club} />');
hero = hero.replace('<View style={s.heroIconWrap}>', "<View style={[s.heroIconWrap, { backgroundColor: 'transparent', borderColor: theme.border, borderTopColor: theme.border, borderBottomColor: theme.border, borderLeftColor: theme.border, borderRightColor: theme.border }]}> ");
hero = hero.replace('<IconSurfaceDepth />', '<SoftCardGlow color={theme.color} opacity={0.3} />');
hero = hero.replace('<View style={s.wideArrow}><Text style={s.wideArrowText}>', '<View style={[s.wideArrow, { borderColor: theme.border }]}><Text style={[s.wideArrowText, { color: theme.border }]}>');
if (!hero.includes('<TeamCardBackdrop club={club} />') || !hero.includes('<ClubBadge club={club} size={62} />')) throw new Error('Team card gradients: hero or original badge missing');
ui = ui.slice(0, start) + hero + ui.slice(end);
// Replace solid interior patches with one continuous transparent gradient.
replace('<View pointerEvents="none" style={[s.surfaceGlow, strong && s.surfaceGlowStrong, danger && s.surfaceGlowDanger]} />', '<SoftCardGlow color={danger ? C.red : C.blue} opacity={strong ? 0.3 : 0.18} />');
replace('<View pointerEvents="none" style={s.surfaceBottomShade} />', '');
replace('<View pointerEvents="none" style={[s.iconSurfaceGlow, danger && s.iconSurfaceGlowDanger]} />', '<SoftCardGlow color={danger ? C.red : C.blue} opacity={0.24} />');
replace('<View pointerEvents="none" style={s.iconSurfaceShade} />', '');
fs.writeFileSync(path, ui + '\n// team-card-gradients applied\n');
console.log('Team card colors and soft gradients applied; foreground badges unchanged.');
