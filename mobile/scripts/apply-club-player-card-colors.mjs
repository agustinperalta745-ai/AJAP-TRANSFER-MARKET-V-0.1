import fs from 'node:fs';

const path = new URL('../src/BotParityAppV2.tsx', import.meta.url);
let ui = fs.readFileSync(path, 'utf8');
const marker = '// club-player-card-colors applied';
if (ui.includes(marker)) process.exit(0);
if (!ui.includes('// team-card-gradients applied')) throw new Error('Apply team-card-gradients first');

function section(start, end, transform) {
  const a = ui.indexOf(start);
  const b = ui.indexOf(end, a + start.length);
  if (a < 0 || b < 0) throw new Error(`Missing section: ${start}`);
  ui = ui.slice(0, a) + transform(ui.slice(a, b)) + ui.slice(b);
}
function required(text, from, to) {
  if (!text.includes(from)) throw new Error(`Missing card anchor: ${from}`);
  return text.replace(from, to);
}
const border = club => `clubCardStyle(${club})`;
const backdrop = club => `<TeamCardBackdrop club={${club}} />`;
const glow = club => `<SoftCardGlow color={teamCardTheme(${club}).color} opacity={0.3} />`;
function icon(text, club) {
  text = text.replaceAll('<View style={s.heroIconWrap}>', `<View style={[s.heroIconWrap, ${border(club)}, { backgroundColor: 'transparent' }]}>`);
  return text.replaceAll('<IconSurfaceDepth />', glow(club));
}

// All player lists share these components; the current data controls the colors.
for (const [start, end, club] of [
  ['function PlayerCard(', '\nfunction MarketCard(', 'player.club'],
  ['function MarketCard(', '\nfunction ', "item.is_free_agent ? '' : item.club"],
]) {
  section(start, end, text => {
    text = required(text, '<View style={s.card}>', `<View style={[s.card, ${border(club)}]}>${backdrop(club)}`);
    text = required(text, '<View style={s.ovrBox}>', `<View style={[s.ovrBox, ${border(club)}, { backgroundColor: 'transparent' }]}>${glow(club)}`);
    text = text.replaceAll('style={s.ovrValue}', `style={[s.ovrValue, { color: teamCardTheme(${club}).border }]}`);
    return text.replaceAll('style={s.playerValue}', `style={[s.playerValue, { color: teamCardTheme(${club}).border }]}`);
  });
}

section('  const teamsScreen = (', '  const teamProfileScreen =', text => {
  text = required(text, 's.card, pressed &&', `s.card, ${border('club.club')}, pressed &&`);
  text = required(text, '<View style={s.playerRow}>', `${backdrop('club.club')}<View style={s.playerRow}>`);
  text = text.replaceAll('style={s.playerValue}', 'style={[s.playerValue, { color: teamCardTheme(club.club).border }]}');
  text = text.replaceAll('style={s.chevron}', 'style={[s.chevron, { color: teamCardTheme(club.club).border }]}');
  return icon(text, 'club.club');
});

section('  const teamProfileScreen =', '  const treasuryScreen =', text => {
  // Stop at the profile end: later scripts may insert other screens here.
  const end = text.indexOf('\n  const ', 5);
  const tail = end < 0 ? '' : text.slice(end);
  let profile = end < 0 ? text : text.slice(0, end);
  const club = 'selectedClubProfile.club';
  profile = profile.replace(/(<View(?: key=\{[^}]+\})? )style=\{s\.(card|summaryCard|heroClubCard)\}>/g,
    (_, opening, style) => `${opening}style={[s.${style}, ${border(club)}]}>${style === 'heroClubCard' ? backdrop(club) : glow(club)}`);
  profile = required(profile, `<View style={[s.card, { borderColor: '#ff8b45', borderWidth: 1.5 }]}>`, `<View style={[s.card, ${border(club)}]}>${glow(club)}`);
  profile = profile.replaceAll('style={s.listHeading}', `style={[s.listHeading, { color: teamCardTheme(${club}).border }]}`);
  return icon(profile, club) + tail;
});

ui = ui.replace('function PlayerCard(', `function clubCardStyle(club: string | null | undefined) {
  const { border } = teamCardTheme(club);
  return { borderColor: border, borderTopColor: border, borderBottomColor: border,
    borderLeftColor: border, borderRightColor: border, overflow: 'hidden' as const };
}

function PlayerCard(`);
for (const club of ['club.club', 'selectedClubProfile.club', 'player.club']) {
  if (!ui.includes(backdrop(club))) throw new Error(`Missing themed backdrop: ${club}`);
}
fs.writeFileSync(path, ui + '\n' + marker + '\n');
console.log('Club profiles and player cards now use their current club theme; badge assets unchanged.');

// Liga se tematiza al final para reutilizar exactamente los mismos helpers y assets aprobados.
await import('./apply-league-team-card-colors.mjs');
