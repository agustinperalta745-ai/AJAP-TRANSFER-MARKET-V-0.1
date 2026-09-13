import fs from 'node:fs';
import path from 'node:path';

const trophyDir = path.join('assets', 'trophies');
const europaChunksDir = path.join(trophyDir, 'europa_chunks');
const europaFile = path.join(trophyDir, 'europa-ajpa.jpg');

const europaChunks = fs.readdirSync(europaChunksDir)
  .filter(name => name.endsWith('.txt'))
  .sort()
  .map(name => fs.readFileSync(path.join(europaChunksDir, name), 'utf8').trim());

if (europaChunks.length !== 8) {
  throw new Error(`Trophy cabinet: expected 8 Europa trophy chunks, found ${europaChunks.length}.`);
}

const europaBytes = Buffer.from(europaChunks.join(''), 'base64');
const isJpeg = europaBytes.length === 6989
  && europaBytes[0] === 0xff
  && europaBytes[1] === 0xd8
  && europaBytes[europaBytes.length - 2] === 0xff
  && europaBytes[europaBytes.length - 1] === 0xd9;

if (!isJpeg) {
  throw new Error(`Trophy cabinet: reconstructed Europa trophy is invalid (${europaBytes.length} bytes).`);
}

fs.writeFileSync(europaFile, europaBytes);

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

if (!cabinet.includes("const CHAMPIONS_BANNER = require('../assets/trophies/champions-ajpa-banner.jpg');")) {
  const anchor = `} as const;\n\nconst META:`;
  if (!cabinet.includes(anchor)) throw new Error('Trophy cabinet: TROPHY map anchor not found.');
  cabinet = cabinet.replace(
    anchor,
    `} as const;\n\nconst CHAMPIONS_BANNER = require('../assets/trophies/champions-ajpa-banner.jpg');\n\nconst META:`,
  );
}

if (!cabinet.includes('styles.championsBannerStage')) {
  const oldStage = `      <View style={styles.trophyStage}>\n        <Image source={TROPHY[trophyKey]} resizeMode="contain" style={styles.trophyImage} />\n      </View>`;
  const newStage = `      <View style={trophyKey === 'champions' ? styles.championsBannerStage : styles.trophyStage}>\n        {trophyKey === 'champions' ? (\n          <Image source={CHAMPIONS_BANNER} resizeMode="cover" style={styles.championsBannerImage} />\n        ) : (\n          <Image source={TROPHY[trophyKey]} resizeMode="contain" style={styles.trophyImage} />\n        )}\n      </View>`;
  if (!cabinet.includes(oldStage)) throw new Error('Trophy cabinet: trophy image stage anchor not found.');
  cabinet = cabinet.replace(oldStage, newStage);
}

if (!cabinet.includes('championsBannerStage: {')) {
  const anchor = `  trophyStage: {`;
  if (!cabinet.includes(anchor)) throw new Error('Trophy cabinet: trophyStage style anchor not found.');
  const styles = `  championsBannerStage: {\n    width: '100%',\n    aspectRatio: 800 / 335,\n    backgroundColor: '#03070c',\n    borderBottomWidth: 1,\n    borderBottomColor: 'rgba(255,255,255,0.07)',\n    overflow: 'hidden',\n  },\n  championsBannerImage: { width: '100%', height: '100%' },\n`;
  cabinet = cabinet.replace(anchor, `${styles}${anchor}`);
}

if (!cabinet.includes("const CHAMPIONS_BANNER = require('../assets/trophies/champions-ajpa-banner.jpg');")
  || !cabinet.includes('styles.championsBannerStage')
  || !cabinet.includes('championsBannerImage:')) {
  throw new Error('Trophy cabinet: Champions banner validation failed.');
}

fs.writeFileSync(cabinetFile, cabinet);
console.log(`AJPA trophy cabinet: full-screen scrollable modal + approved Champions AJPA banner; Europa trophy rebuilt (${europaBytes.length} bytes).`);