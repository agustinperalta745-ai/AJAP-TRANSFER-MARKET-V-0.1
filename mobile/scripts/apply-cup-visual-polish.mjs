import fs from 'node:fs';

const cupFile = 'src/CupCenterFab.tsx';
let cup = fs.readFileSync(cupFile, 'utf8');

// Team badges in every cup match.
if (!cup.includes("import { ClubBadge } from './teamBadges';")) {
  const apiImport = "import { apiRequest, fetchMe, getSessionToken } from './api';";
  if (!cup.includes(apiImport)) throw new Error('Cup visuals: API import anchor not found.');
  cup = cup.replace(apiImport, `${apiImport}\nimport { ClubBadge } from './teamBadges';`);
}

if (!cup.includes('  Image,\n')) {
  const alertAnchor = '  Alert,\n';
  if (!cup.includes(alertAnchor)) throw new Error('Cup visuals: React Native import anchor not found.');
  cup = cup.replace(alertAnchor, `${alertAnchor}  Image,\n`);
}

const compNameAnchor = "const compName = (key: CompetitionKey) => key === 'champions' ? 'Champions League' : 'Europa League';";
if (!cup.includes('const CHAMPIONS_TROPHY =')) {
  if (!cup.includes(compNameAnchor)) throw new Error('Cup visuals: competition helper anchor not found.');
  cup = cup.replace(
    compNameAnchor,
    `${compNameAnchor}\n\nconst CHAMPIONS_TROPHY = require('../assets/trophies/champions-ajpa.jpg');\nconst EUROPA_TROPHY = require('../assets/trophies/europa-ajpa.jpg');`,
  );
}

const oldHeader = `                <Text style={styles.eyebrow}>AJPA · COMPETICIONES</Text>\n                <Text style={styles.title}>Champions & Europa League</Text>\n                <Text style={styles.subtitle}>Clasificación, descenso entre copas, cuadros y resultados oficiales.</Text>`;
const newHeader = `                <View style={styles.competitionHeaderRow}>\n                  <View style={[styles.competitionTrophyWrap, competition === 'europa' && styles.competitionTrophyWrapEuropa]}>\n                    <Image\n                      source={competition === 'champions' ? CHAMPIONS_TROPHY : EUROPA_TROPHY}\n                      resizeMode="contain"\n                      fadeDuration={0}\n                      style={styles.competitionTrophy}\n                    />\n                  </View>\n                  <View style={styles.flex}>\n                    <Text style={[styles.eyebrow, competition === 'europa' && styles.europaEyebrow]}>\n                      {competition === 'champions' ? 'AJPA · CHAMPIONS' : 'AJPA · EUROPA'}\n                    </Text>\n                    <Text style={styles.title}>\n                      {competition === 'champions' ? 'Champions AJPA' : 'Europa AJPA'}\n                    </Text>\n                    <Text style={styles.subtitle}>\n                      {competition === 'champions'\n                        ? 'Cuadro, cruces y resultados oficiales de Champions.'\n                        : 'Cuadro, cruces y resultados oficiales de Europa.'}\n                    </Text>\n                  </View>\n                </View>`;
if (cup.includes(oldHeader)) {
  cup = cup.replace(oldHeader, newHeader);
}

const oldHomeLine = `        <View style={styles.teamLine}>\n          <Text style={[styles.matchTeam, match.winner_team === match.home_team && styles.winner]} numberOfLines={1}>\n            {match.home_team || 'Por definir'}\n          </Text>\n          <Text style={styles.teamScore}>{match.home_goals ?? '—'}</Text>\n        </View>`;
const newHomeLine = `        <View style={styles.teamLine}>\n          <View style={styles.matchTeamIdentity}>\n            <View style={styles.matchBadgeSlot}>\n              {match.home_team ? <ClubBadge club={match.home_team} size={30} /> : <View style={styles.badgeGhost} />}\n            </View>\n            <Text style={[styles.matchTeam, match.winner_team === match.home_team && styles.winner]} numberOfLines={1}>\n              {match.home_team || 'Por definir'}\n            </Text>\n          </View>\n          <Text style={styles.teamScore}>{match.home_goals ?? '—'}</Text>\n        </View>`;
if (cup.includes(oldHomeLine)) cup = cup.replace(oldHomeLine, newHomeLine);

const oldAwayLine = `        <View style={styles.teamLine}>\n          <Text style={[styles.matchTeam, match.winner_team === match.away_team && styles.winner]} numberOfLines={1}>\n            {match.away_team || match.source_away || 'Por definir'}\n          </Text>\n          <Text style={styles.teamScore}>{match.away_goals ?? '—'}</Text>\n        </View>`;
const newAwayLine = `        <View style={styles.teamLine}>\n          <View style={styles.matchTeamIdentity}>\n            <View style={styles.matchBadgeSlot}>\n              {match.away_team ? <ClubBadge club={match.away_team} size={30} /> : <View style={styles.badgeGhost} />}\n            </View>\n            <Text style={[styles.matchTeam, match.winner_team === match.away_team && styles.winner]} numberOfLines={1}>\n              {match.away_team || match.source_away || 'Por definir'}\n            </Text>\n          </View>\n          <Text style={styles.teamScore}>{match.away_goals ?? '—'}</Text>\n        </View>`;
if (cup.includes(oldAwayLine)) cup = cup.replace(oldAwayLine, newAwayLine);

const cupStyleClose = '\n});';
const cupStylePos = cup.lastIndexOf(cupStyleClose);
if (cupStylePos < 0) throw new Error('Cup visuals: CupCenter style close not found.');
if (!cup.includes('  competitionHeaderRow: {')) {
  const extra = String.raw`
  competitionHeaderRow: { flexDirection: 'row', alignItems: 'center', gap: 12 },
  competitionTrophyWrap: { width: 66, height: 66, borderRadius: 16, borderWidth: 1, borderColor: 'rgba(136,184,255,0.45)', backgroundColor: 'rgba(7,18,31,0.94)', alignItems: 'center', justifyContent: 'center', overflow: 'hidden' },
  competitionTrophyWrapEuropa: { borderColor: 'rgba(231,161,92,0.48)', backgroundColor: 'rgba(28,17,8,0.94)' },
  competitionTrophy: { width: 58, height: 58 },
  europaEyebrow: { color: '#e7a15c' },
  matchTeamIdentity: { flex: 1, minWidth: 0, flexDirection: 'row', alignItems: 'center', gap: 9 },
  matchBadgeSlot: { width: 32, height: 32, alignItems: 'center', justifyContent: 'center', flexShrink: 0 },
  badgeGhost: { width: 26, height: 26, borderRadius: 13, borderWidth: 1, borderColor: 'rgba(132,154,172,0.20)', backgroundColor: 'rgba(132,154,172,0.05)' },
`;
  cup = cup.slice(0, cupStylePos) + extra + cup.slice(cupStylePos);
}

if (!cup.includes('<ClubBadge club={match.home_team} size={30} />') || !cup.includes('<ClubBadge club={match.away_team} size={30} />')) {
  throw new Error('Cup visuals: team badges were not injected into bracket matches.');
}
if (!cup.includes('CHAMPIONS_TROPHY') || !cup.includes('EUROPA_TROPHY')) {
  throw new Error('Cup visuals: competition trophies were not injected.');
}
fs.writeFileSync(cupFile, cup);

// Vitrina-style cards: explicitly show each competition trophy as well as the banner.
const hubFile = 'src/CupHubScreen.tsx';
let hub = fs.readFileSync(hubFile, 'utf8');

if (!hub.includes('const CHAMPIONS_TROPHY =')) {
  const bannerAnchor = "const EUROPA_BANNER = require('../assets/trophies/europa-ajpa-banner.jpg');";
  if (!hub.includes(bannerAnchor)) throw new Error('Cup visuals: CupHub banner anchor not found.');
  hub = hub.replace(
    bannerAnchor,
    `${bannerAnchor}\nconst CHAMPIONS_TROPHY = require('../assets/trophies/champions-ajpa.jpg');\nconst EUROPA_TROPHY = require('../assets/trophies/europa-ajpa.jpg');`,
  );
}

hub = hub.replace(
  "const CUP_META: Record<CompetitionKey, { title: string; eyebrow: string; subtitle: string; accent: string; image: any }> = {",
  "const CUP_META: Record<CompetitionKey, { title: string; eyebrow: string; subtitle: string; accent: string; image: any; trophy: any }> = {",
);
if (!hub.includes('trophy: CHAMPIONS_TROPHY')) {
  hub = hub.replace("    image: CHAMPIONS_BANNER,\n", "    image: CHAMPIONS_BANNER,\n    trophy: CHAMPIONS_TROPHY,\n");
}
if (!hub.includes('trophy: EUROPA_TROPHY')) {
  hub = hub.replace("    image: EUROPA_BANNER,\n", "    image: EUROPA_BANNER,\n    trophy: EUROPA_TROPHY,\n");
}

const oldHubCopy = `      <View style={styles.copy}>\n        <Text style={[styles.eyebrow, { color: meta.accent }]}>{meta.eyebrow}</Text>\n        <Text style={styles.title}>{meta.title}</Text>\n        <Text style={styles.subtitle}>{meta.subtitle}</Text>\n        <View style={styles.openRow}>`;
const newHubCopy = `      <View style={styles.copy}>\n        <View style={styles.cardTitleRow}>\n          <View style={[styles.trophyThumbWrap, { borderColor: \`${meta.accent}66\` }]}>\n            <Image source={meta.trophy} resizeMode="contain" fadeDuration={0} style={styles.trophyThumb} />\n          </View>\n          <View style={styles.cardTitleCopy}>\n            <Text style={[styles.eyebrow, { color: meta.accent }]}>{meta.eyebrow}</Text>\n            <Text style={styles.title}>{meta.title}</Text>\n            <Text style={styles.subtitle}>{meta.subtitle}</Text>\n          </View>\n        </View>\n        <View style={styles.openRow}>`;
if (hub.includes(oldHubCopy)) hub = hub.replace(oldHubCopy, newHubCopy);

const hubStylePos = hub.lastIndexOf(cupStyleClose);
if (hubStylePos < 0) throw new Error('Cup visuals: CupHub style close not found.');
if (!hub.includes('  cardTitleRow: {')) {
  const extra = String.raw`
  cardTitleRow: { flexDirection: 'row', alignItems: 'center', gap: 12 },
  cardTitleCopy: { flex: 1, minWidth: 0 },
  trophyThumbWrap: { width: 62, height: 62, borderRadius: 15, borderWidth: 1, backgroundColor: '#04090d', alignItems: 'center', justifyContent: 'center', overflow: 'hidden' },
  trophyThumb: { width: 54, height: 54 },
`;
  hub = hub.slice(0, hubStylePos) + extra + hub.slice(hubStylePos);
}

if (!hub.includes('meta.trophy') || !hub.includes('trophy: CHAMPIONS_TROPHY') || !hub.includes('trophy: EUROPA_TROPHY')) {
  throw new Error('Cup visuals: CupHub trophy validation failed.');
}
fs.writeFileSync(hubFile, hub);

// Main menu: COPA is a standalone card immediately below LIGA, never inside Liga.
const uiFile = 'src/BotParityAppV2.tsx';
let ui = fs.readFileSync(uiFile, 'utf8');
ui = ui.replace(/^[ \t]*<MenuTile[^\n]*openScreen\('cupHub'\)[^\n]*\/>\n?/gm, '');

const ligaLine = ui.match(/^[ \t]*<MenuTile[^\n]*title="(?:LIGA|Liga)"[^\n]*\/>$/m)?.[0];
if (!ligaLine) throw new Error('Cup visuals: main-menu Liga card not found.');
const indent = ligaLine.match(/^[ \t]*/)?.[0] ?? '      ';
const cupCard = `${indent}<MenuTile emoji="🏆" title="COPA" subtitle="Champions AJPA · Europa AJPA · brackets y resultados" onPress={() => openScreen('cupHub')} />`;
ui = ui.replace(ligaLine, `${ligaLine}\n${cupCard}`);

const ligaPos = ui.indexOf(ligaLine);
const cupPos = ui.indexOf(cupCard);
if (ligaPos < 0 || cupPos < 0 || cupPos <= ligaPos) {
  throw new Error('Cup visuals: COPA card was not placed below LIGA.');
}
if ((ui.match(/openScreen\('cupHub'\)/g) || []).length !== 1) {
  throw new Error('Cup visuals: expected exactly one main-menu COPA card.');
}
fs.writeFileSync(uiFile, ui);

console.log('AJPA Copas: escudos en cruces + copa propia por competencia + tarjeta COPA independiente debajo de LIGA.');
