import fs from 'node:fs';
import path from 'node:path';

const trophyDir = path.join('assets', 'trophies');
const europaChunksDir = path.join(trophyDir, 'europa_chunks');
const europaFile = path.join(trophyDir, 'europa-ajpa.jpg');
const championsChunksDir = path.join(trophyDir, 'champions_banner_chunks');
const championsBannerFile = path.join(trophyDir, 'champions-ajpa-banner.jpg');
const europaBannerChunksDir = path.join(trophyDir, 'europa_banner_small_chunks');
const europaBannerFile = path.join(trophyDir, 'europa-ajpa-banner.jpg');

const europaChunks = fs.readdirSync(europaChunksDir)
  .filter(name => name.endsWith('.txt'))
  .sort()
  .map(name => fs.readFileSync(path.join(europaChunksDir, name), 'utf8').trim());

if (europaChunks.length !== 8) {
  throw new Error(`Trophy cabinet: expected 8 Europa trophy chunks, found ${europaChunks.length}.`);
}

const europaBytes = Buffer.from(europaChunks.join(''), 'base64');
const europaIsJpeg = europaBytes.length === 6989
  && europaBytes[0] === 0xff
  && europaBytes[1] === 0xd8
  && europaBytes[europaBytes.length - 2] === 0xff
  && europaBytes[europaBytes.length - 1] === 0xd9;

if (!europaIsJpeg) {
  throw new Error(`Trophy cabinet: reconstructed Europa trophy is invalid (${europaBytes.length} bytes).`);
}

fs.writeFileSync(europaFile, europaBytes);

const championsChunkFiles = [
  'x00.txt',
  'x01.txt',
  'x02.txt',
  'x03.txt',
  'x04.txt',
  '01.txt',
  '02.txt',
  '03.txt',
];
const championsChunks = championsChunkFiles.map(name => {
  const chunkPath = path.join(championsChunksDir, name);
  if (!fs.existsSync(chunkPath)) throw new Error(`Trophy cabinet: missing Champions chunk ${name}.`);
  return fs.readFileSync(chunkPath, 'utf8').trim();
});

const championsBase64 = championsChunks.join('');
if (championsBase64.length !== 19436) {
  throw new Error(`Trophy cabinet: Champions base64 length invalid (${championsBase64.length}).`);
}

const championsBannerBytes = Buffer.from(championsBase64, 'base64');
const championsBannerIsJpeg = championsBannerBytes.length === 14576
  && championsBannerBytes[0] === 0xff
  && championsBannerBytes[1] === 0xd8
  && championsBannerBytes[championsBannerBytes.length - 2] === 0xff
  && championsBannerBytes[championsBannerBytes.length - 1] === 0xd9;

if (!championsBannerIsJpeg) {
  throw new Error(`Trophy cabinet: reconstructed Champions banner is invalid (${championsBannerBytes.length} bytes).`);
}

fs.writeFileSync(championsBannerFile, championsBannerBytes);

const europaBannerChunkFiles = ['b00.txt', 'b01.txt', 'b02.txt'];
const europaBannerChunks = europaBannerChunkFiles.map(name => {
  const chunkPath = path.join(europaBannerChunksDir, name);
  if (!fs.existsSync(chunkPath)) throw new Error(`Trophy cabinet: missing Europa banner chunk ${name}.`);
  return fs.readFileSync(chunkPath, 'utf8').trim();
});

const europaBannerBase64 = europaBannerChunks.join('');
if (europaBannerBase64.length !== 30392) {
  throw new Error(`Trophy cabinet: Europa banner base64 length invalid (${europaBannerBase64.length}).`);
}

const europaBannerBytes = Buffer.from(europaBannerBase64, 'base64');
const europaBannerIsJpeg = europaBannerBytes.length === 22794
  && europaBannerBytes[0] === 0xff
  && europaBannerBytes[1] === 0xd8
  && europaBannerBytes[europaBannerBytes.length - 2] === 0xff
  && europaBannerBytes[europaBannerBytes.length - 1] === 0xd9;

if (!europaBannerIsJpeg) {
  throw new Error(`Trophy cabinet: reconstructed Europa banner is invalid (${europaBannerBytes.length} bytes).`);
}

fs.writeFileSync(europaBannerFile, europaBannerBytes);

const appFile = 'App.tsx';
let app = fs.readFileSync(appFile, 'utf8');
app = app
  .replace("import TrophyCabinetFab from './src/TrophyCabinetFab';\n", '')
  .replace('        <TrophyCabinetFab />\n', '');
fs.writeFileSync(appFile, app);

const file = 'src/BotParityAppV2.tsx';
let source = fs.readFileSync(file, 'utf8');

const importLine = "import TrophyCabinetScreen from './TrophyCabinetFab';";
if (!source.includes(importLine)) {
  const anchor = "import { clearStoredSession, loadStoredSession, saveStoredSession } from './session';";
  if (!source.includes(anchor)) throw new Error('Trophy cabinet: session import anchor not found.');
  source = source.replace(anchor, `${importLine}\n${anchor}`);
}

if (!source.includes("| 'trophyCabinet'")) {
  const anchor = "  | 'profile';";
  if (!source.includes(anchor)) throw new Error('Trophy cabinet: Screen union anchor not found.');
  source = source.replace(anchor, "  | 'trophyCabinet'\n  | 'profile';");
}

if (!source.includes('title="Vitrina de campeones"')) {
  const ligaLine = source.match(/^[ \t]*<FeatureTile[^\n]*title="Liga"[^\n]*\/>$/m)?.[0]
    ?? source.match(/^[ \t]*<MenuTile[^\n]*title="LIGA"[^\n]*\/>$/m)?.[0]
    ?? source.match(/^[ \t]*<WideTile[^\n]*title="Liga"[^\n]*\/>$/m)?.[0];
  if (!ligaLine) throw new Error('Trophy cabinet: main Liga feature anchor not found.');
  const indent = ligaLine.match(/^[ \t]*/)?.[0] ?? '        ';
  const component = ligaLine.includes('<FeatureTile') ? 'FeatureTile' : ligaLine.includes('<WideTile') ? 'WideTile' : 'MenuTile';
  source = source.replace(
    ligaLine,
    `${ligaLine}\n${indent}<${component} emoji="🏛️" title="Vitrina de campeones" subtitle="Trofeos oficiales y palmarés histórico" onPress={() => openScreen('trophyCabinet')} />`,
  );
}

const trophyBodyLine = source.match(/^[ \t]*else if \(screen === 'trophyCabinet'\)[^\n]*$/m)?.[0];
if (trophyBodyLine) {
  const indent = trophyBodyLine.match(/^[ \t]*/)?.[0] ?? '  ';
  source = source.replace(trophyBodyLine, `${indent}else if (screen === 'trophyCabinet') body = <TrophyCabinetScreen onClose={() => setScreen('home')} />;`);
} else {
  const leagueBodyLine = source.match(/^[ \t]*else if \(screen === 'league'\)[^\n]*$/m)?.[0];
  if (!leagueBodyLine) throw new Error('Trophy cabinet: Liga body anchor not found.');
  const indent = leagueBodyLine.match(/^[ \t]*/)?.[0] ?? '  ';
  source = source.replace(leagueBodyLine, `${leagueBodyLine}\n${indent}else if (screen === 'trophyCabinet') body = <TrophyCabinetScreen onClose={() => setScreen('home')} />;`);
}

if (!source.includes(importLine)
  || !source.includes("| 'trophyCabinet'")
  || !source.includes('title="Vitrina de campeones"')
  || !source.includes("<TrophyCabinetScreen onClose={() => setScreen('home')} />")) {
  throw new Error('Trophy cabinet: final main-menu validation failed.');
}

fs.writeFileSync(file, source);

const cabinetFile = 'src/TrophyCabinetFab.tsx';
let cabinet = fs.readFileSync(cabinetFile, 'utf8');
const championsBannerRequire = "const CHAMPIONS_BANNER = require('../assets/trophies/champions-ajpa-banner.jpg');";
const europaBannerRequire = "const EUROPA_BANNER = require('../assets/trophies/europa-ajpa-banner.jpg');";

if (!cabinet.includes(championsBannerRequire)) {
  const dataUriConst = /const CHAMPIONS_BANNER = \{ uri: "data:image\/jpeg;base64,[^"]+" \} as const;/;
  if (dataUriConst.test(cabinet)) {
    cabinet = cabinet.replace(dataUriConst, championsBannerRequire);
  } else if (!cabinet.includes('const CHAMPIONS_BANNER =')) {
    const anchor = `} as const;\n\nconst META:`;
    if (!cabinet.includes(anchor)) throw new Error('Trophy cabinet: TROPHY map anchor not found.');
    cabinet = cabinet.replace(anchor, `} as const;\n\n${championsBannerRequire}\n${europaBannerRequire}\n\nconst META:`);
  }
}

if (!cabinet.includes(europaBannerRequire)) {
  if (cabinet.includes(championsBannerRequire)) {
    cabinet = cabinet.replace(championsBannerRequire, `${championsBannerRequire}\n${europaBannerRequire}`);
  } else {
    throw new Error('Trophy cabinet: could not place Europa banner require.');
  }
}

const oldStage = `      <View style={styles.trophyStage}>\n        <Image source={TROPHY[trophyKey]} resizeMode="contain" style={styles.trophyImage} />\n      </View>`;
const championsOnlyStage = `      <View style={trophyKey === 'champions' ? styles.championsBannerStage : styles.trophyStage}>\n        {trophyKey === 'champions' ? (\n          <Image source={CHAMPIONS_BANNER} resizeMode="cover" fadeDuration={0} style={styles.championsBannerImage} />\n        ) : (\n          <Image source={TROPHY[trophyKey]} resizeMode="contain" style={styles.trophyImage} />\n        )}\n      </View>`;
const dualBannerStage = `      <View style={trophyKey === 'league' ? styles.trophyStage : styles.competitionBannerStage}>\n        {trophyKey === 'league' ? (\n          <Image source={TROPHY[trophyKey]} resizeMode="contain" style={styles.trophyImage} />\n        ) : (\n          <Image\n            source={trophyKey === 'champions' ? CHAMPIONS_BANNER : EUROPA_BANNER}\n            resizeMode="cover"\n            fadeDuration={0}\n            style={styles.competitionBannerImage}\n          />\n        )}\n      </View>`;

if (cabinet.includes(oldStage)) {
  cabinet = cabinet.replace(oldStage, dualBannerStage);
} else if (cabinet.includes(championsOnlyStage)) {
  cabinet = cabinet.replace(championsOnlyStage, dualBannerStage);
} else if (!cabinet.includes('styles.competitionBannerStage')) {
  throw new Error('Trophy cabinet: trophy image stage anchor not found.');
}

if (!cabinet.includes('competitionBannerStage: {')) {
  const championsStyles = /  championsBannerStage: \{[\s\S]*?  championsBannerImage: \{ width: '100%', height: '100%' \},\n/;
  const replacement = `  competitionBannerStage: {\n    width: '100%',\n    aspectRatio: 3,\n    backgroundColor: '#03070c',\n    borderBottomWidth: 1,\n    borderBottomColor: 'rgba(255,255,255,0.07)',\n    overflow: 'hidden',\n  },\n  competitionBannerImage: { width: '100%', height: '100%' },\n`;
  if (championsStyles.test(cabinet)) {
    cabinet = cabinet.replace(championsStyles, replacement);
  } else {
    const anchor = `  trophyStage: {`;
    if (!cabinet.includes(anchor)) throw new Error('Trophy cabinet: trophyStage style anchor not found.');
    cabinet = cabinet.replace(anchor, `${replacement}${anchor}`);
  }
}

if (!cabinet.includes(championsBannerRequire)
  || !cabinet.includes(europaBannerRequire)
  || !cabinet.includes('styles.competitionBannerStage')
  || !cabinet.includes('competitionBannerImage:')) {
  throw new Error('Trophy cabinet: competition banner validation failed.');
}

fs.writeFileSync(cabinetFile, cabinet);
console.log(`AJPA trophy cabinet: Champions banner (${championsBannerBytes.length} bytes) + Europa banner (${europaBannerBytes.length} bytes) + Europa trophy (${europaBytes.length} bytes).`);