import fs from 'node:fs';

const file = 'src/BotParityAppV2.tsx';
let src = fs.readFileSync(file, 'utf8');

// Últimos logros debe reutilizar exactamente el mismo componente de escudos
// aprobado para el resto de la app. Así no vuelve a caer en los PNG legacy
// pequeños/borrosos de assets/teams.
const existingTeamBadgesImport = src.match(/import\s*\{([^}]*)\}\s*from\s*['"]\.\/teamBadges['"];?/m);
if (existingTeamBadgesImport) {
  const importedNames = existingTeamBadgesImport[1];
  if (!/\bClubBadge\b/.test(importedNames)) {
    src = src.replace(
      existingTeamBadgesImport[0],
      existingTeamBadgesImport[0].replace('{', '{ ClubBadge,'),
    );
  }
} else {
  const anchor = "import { BG_PERFIL } from './bg_perfil';";
  if (!src.includes(anchor)) throw new Error('Latest honours badges: import anchor not found');
  src = src.replace(anchor, `${anchor}\nimport { ClubBadge } from './teamBadges';`);
}

const championPattern = /<>\s*<Text numberOfLines=\{1\} style=\{s\.honourPrimary\}>\{latestHonours\.season_champion\.team\}<\/Text>\s*<Text numberOfLines=\{1\} style=\{s\.honourSecondary\}>DT · \{latestHonours\.season_champion\.manager\.username\}<\/Text>\s*<Text numberOfLines=\{1\} style=\{s\.honourMeta\}>\{latestHonours\.season_champion\.competition\}<\/Text>\s*<\/>/s;

src = src.replace(championPattern, `<View style={s.honourBody}>
                <ClubBadge club={latestHonours.season_champion.team} size={30} />
                <View style={s.honourText}>
                  <Text numberOfLines={1} style={s.honourPrimary}>{latestHonours.season_champion.team}</Text>
                  <Text style={s.honourDt}>DT · {latestHonours.season_champion.manager.username}</Text>
                  <Text numberOfLines={1} style={s.honourMeta}>{latestHonours.season_champion.competition}</Text>
                </View>
              </View>`);

const scorerPattern = /<>\s*<Text numberOfLines=\{1\} style=\{s\.honourPrimary\}>\{latestHonours\.top_scorer\.player\}<\/Text>\s*<Text numberOfLines=\{1\} style=\{s\.honourSecondary\}>\{latestHonours\.top_scorer\.goals\} goles · \{latestHonours\.top_scorer\.team\}<\/Text>\s*<Text numberOfLines=\{1\} style=\{s\.honourMeta\}>DT · \{latestHonours\.top_scorer\.manager\.username\}<\/Text>\s*<\/>/s;

src = src.replace(scorerPattern, `<View style={s.honourBody}>
                <ClubBadge club={latestHonours.top_scorer.team} size={30} />
                <View style={s.honourText}>
                  <Text numberOfLines={1} style={s.honourPrimary}>{latestHonours.top_scorer.player}</Text>
                  <Text numberOfLines={1} style={s.honourSecondary}>{latestHonours.top_scorer.goals} goles</Text>
                  <Text numberOfLines={1} style={s.honourMeta}>{latestHonours.top_scorer.team}</Text>
                  <Text style={s.honourDt}>DT · {latestHonours.top_scorer.manager.username}</Text>
                </View>
              </View>`);

const cupPattern = /<>\s*<Text numberOfLines=\{1\} style=\{s\.honourPrimary\}>\{latestHonours\.cup_champion\.team\}<\/Text>\s*<Text numberOfLines=\{1\} style=\{s\.honourSecondary\}>DT · \{latestHonours\.cup_champion\.manager\.username\}<\/Text>\s*<Text numberOfLines=\{1\} style=\{s\.honourMeta\}>\{latestHonours\.cup_champion\.competition\}<\/Text>\s*<\/>/s;

src = src.replace(cupPattern, `<View style={s.honourBody}>
                <ClubBadge club={latestHonours.cup_champion.team} size={30} />
                <View style={s.honourText}>
                  <Text numberOfLines={1} style={s.honourPrimary}>{latestHonours.cup_champion.team}</Text>
                  <Text style={s.honourDt}>DT · {latestHonours.cup_champion.manager.username}</Text>
                  <Text numberOfLines={1} style={s.honourMeta}>{latestHonours.cup_champion.competition}</Text>
                </View>
              </View>`);

if (!src.includes('honourBody: {')) {
  src = src.replace(
    /\n  honourLabel: \{/,
    `\n  honourBody: { flexDirection: 'row', alignItems: 'flex-start', gap: 5, minWidth: 0 },\n  honourText: { flex: 1, minWidth: 0 },\n  honourDt: { color: '#c4d1dc', fontSize: 7.5, fontWeight: '700', lineHeight: 10, marginTop: 3, flexShrink: 1 },\n  honourLabel: {`,
  );
} else if (!src.includes('honourDt: {')) {
  src = src.replace(
    /\n  honourLabel: \{/,
    `\n  honourDt: { color: '#c4d1dc', fontSize: 7.5, fontWeight: '700', lineHeight: 10, marginTop: 3, flexShrink: 1 },\n  honourLabel: {`,
  );
}

fs.writeFileSync(file, src);
console.log('AJPA Mobile: últimos logros con escudos HQ y nombres completos de DT');
