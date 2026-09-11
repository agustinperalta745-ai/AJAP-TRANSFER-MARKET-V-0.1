import fs from 'node:fs';

const file = 'src/BotParityAppV2.tsx';
let src = fs.readFileSync(file, 'utf8');

if (!src.includes('Image,\n  ImageBackground,')) {
  src = src.replace('  ImageBackground,', '  Image,\n  ImageBackground,');
}

const badgeHelper = `
const HONOUR_TEAM_BADGES: Record<string, any> = {
  'ajax': require('../assets/teams/ajax.png'),
  'as monaco': require('../assets/teams/as_monaco.png'),
  'aston villa': require('../assets/teams/aston_villa.png'),
  'atletico de madrid': require('../assets/teams/atletico_madrid.png'),
  'atletico madrid': require('../assets/teams/atletico_madrid.png'),
  'benfica': require('../assets/teams/benfica.png'),
  'bolton wanderers': require('../assets/teams/bolton_wanderers.png'),
  'everton': require('../assets/teams/everton.png'),
  'feyenoord': require('../assets/teams/feyenoord.png'),
  'fiorentina': require('../assets/teams/fiorentina.png'),
  'fulham': require('../assets/teams/fulham.png'),
  'galatasaray': require('../assets/teams/galatasaray.png'),
  'lazio': require('../assets/teams/lazio.png'),
  'manchester city': require('../assets/teams/manchester_city.png'),
  'middlesbrough': require('../assets/teams/middlesbrough.png'),
  'olympique de lyon': require('../assets/teams/olympique_lyon.png'),
  'olympique lyon': require('../assets/teams/olympique_lyon.png'),
  'lyon': require('../assets/teams/olympique_lyon.png'),
  'olympique de marsella': require('../assets/teams/olympique_marseille.png'),
  'olympique de marseille': require('../assets/teams/olympique_marseille.png'),
  'marsella': require('../assets/teams/olympique_marseille.png'),
  'porto': require('../assets/teams/porto.png'),
  'paris saint germain psg': require('../assets/teams/psg.png'),
  'paris saint germain': require('../assets/teams/psg.png'),
  'psg': require('../assets/teams/psg.png'),
  'real betis': require('../assets/teams/real_betis.png'),
  'sevilla': require('../assets/teams/sevilla.png'),
  'torino': require('../assets/teams/torino.png'),
  'tottenham hotspur': require('../assets/teams/tottenham_hotspur.png'),
  'tottenham': require('../assets/teams/tottenham_hotspur.png'),
  'villarreal': require('../assets/teams/villarreal.png'),
  'west ham united': require('../assets/teams/west_ham_united.png'),
  'west ham': require('../assets/teams/west_ham_united.png'),
  'real zaragoza': require('../assets/teams/zaragoza.png'),
  'zaragoza': require('../assets/teams/zaragoza.png'),
};

const honourTeamKey = (team?: string | null) =>
  String(team || '')
    .normalize('NFD')
    .replace(/[\\u0300-\\u036f]/g, '')
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, ' ')
    .trim();

const honourTeamBadge = (team?: string | null) => HONOUR_TEAM_BADGES[honourTeamKey(team)] || null;

`;

if (!src.includes('const HONOUR_TEAM_BADGES')) {
  src = src.replace('\ntype Screen =', `\n${badgeHelper}type Screen =`);
}

const championPattern = /<>\s*<Text numberOfLines=\{1\} style=\{s\.honourPrimary\}>\{latestHonours\.season_champion\.team\}<\/Text>\s*<Text numberOfLines=\{1\} style=\{s\.honourSecondary\}>DT · \{latestHonours\.season_champion\.manager\.username\}<\/Text>\s*<Text numberOfLines=\{1\} style=\{s\.honourMeta\}>\{latestHonours\.season_champion\.competition\}<\/Text>\s*<\/>/s;

src = src.replace(championPattern, `<View style={s.honourBody}>
                {honourTeamBadge(latestHonours.season_champion.team) ? (
                  <Image source={honourTeamBadge(latestHonours.season_champion.team)} style={s.honourBadge} resizeMode="contain" />
                ) : null}
                <View style={s.honourText}>
                  <Text numberOfLines={1} style={s.honourPrimary}>{latestHonours.season_champion.team}</Text>
                  <Text numberOfLines={1} style={s.honourSecondary}>DT · {latestHonours.season_champion.manager.username}</Text>
                  <Text numberOfLines={1} style={s.honourMeta}>{latestHonours.season_champion.competition}</Text>
                </View>
              </View>`);

const scorerPattern = /<>\s*<Text numberOfLines=\{1\} style=\{s\.honourPrimary\}>\{latestHonours\.top_scorer\.player\}<\/Text>\s*<Text numberOfLines=\{1\} style=\{s\.honourSecondary\}>\{latestHonours\.top_scorer\.goals\} goles · \{latestHonours\.top_scorer\.team\}<\/Text>\s*<Text numberOfLines=\{1\} style=\{s\.honourMeta\}>DT · \{latestHonours\.top_scorer\.manager\.username\}<\/Text>\s*<\/>/s;

src = src.replace(scorerPattern, `<View style={s.honourBody}>
                {honourTeamBadge(latestHonours.top_scorer.team) ? (
                  <Image source={honourTeamBadge(latestHonours.top_scorer.team)} style={s.honourBadge} resizeMode="contain" />
                ) : null}
                <View style={s.honourText}>
                  <Text numberOfLines={1} style={s.honourPrimary}>{latestHonours.top_scorer.player}</Text>
                  <Text numberOfLines={1} style={s.honourSecondary}>{latestHonours.top_scorer.goals} goles</Text>
                  <Text numberOfLines={1} style={s.honourMeta}>{latestHonours.top_scorer.team} · DT {latestHonours.top_scorer.manager.username}</Text>
                </View>
              </View>`);

const cupPattern = /<>\s*<Text numberOfLines=\{1\} style=\{s\.honourPrimary\}>\{latestHonours\.cup_champion\.team\}<\/Text>\s*<Text numberOfLines=\{1\} style=\{s\.honourSecondary\}>DT · \{latestHonours\.cup_champion\.manager\.username\}<\/Text>\s*<Text numberOfLines=\{1\} style=\{s\.honourMeta\}>\{latestHonours\.cup_champion\.competition\}<\/Text>\s*<\/>/s;

src = src.replace(cupPattern, `<View style={s.honourBody}>
                {honourTeamBadge(latestHonours.cup_champion.team) ? (
                  <Image source={honourTeamBadge(latestHonours.cup_champion.team)} style={s.honourBadge} resizeMode="contain" />
                ) : null}
                <View style={s.honourText}>
                  <Text numberOfLines={1} style={s.honourPrimary}>{latestHonours.cup_champion.team}</Text>
                  <Text numberOfLines={1} style={s.honourSecondary}>DT · {latestHonours.cup_champion.manager.username}</Text>
                  <Text numberOfLines={1} style={s.honourMeta}>{latestHonours.cup_champion.competition}</Text>
                </View>
              </View>`);

if (!src.includes('honourBadge: {')) {
  src = src.replace(
    /\n  honourLabel: \{/,
    `\n  honourBody: { flexDirection: 'row', alignItems: 'center', gap: 7, minWidth: 0 },\n  honourBadge: { width: 30, height: 30, flexShrink: 0 },\n  honourText: { flex: 1, minWidth: 0 },\n  honourLabel: {`,
  );
}

fs.writeFileSync(file, src);
console.log('AJPA Mobile: tarjetas de últimos logros con escudos + DT + goleador corregidas');
