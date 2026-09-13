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

if (!source.includes("screen === 'trophyCabinet'")) {
  const leagueBodyLine = source.match(/^[ \t]*else if \(screen === 'league'\)[^\n]*$/m)?.[0];
  if (!leagueBodyLine) throw new Error('Trophy cabinet: Liga body anchor not found.');
  const indent = leagueBodyLine.match(/^[ \t]*/)?.[0] ?? '  ';
  source = source.replace(leagueBodyLine, `${leagueBodyLine}\n${indent}else if (screen === 'trophyCabinet') body = <TrophyCabinetScreen />;`);
}

if (!source.includes(importLine)
  || !source.includes("| 'trophyCabinet'")
  || !source.includes('title="Vitrina de campeones"')
  || !source.includes("screen === 'trophyCabinet'")) {
  throw new Error('Trophy cabinet: final main-menu validation failed.');
}

fs.writeFileSync(file, source);
console.log(`AJPA trophy cabinet moved into main menu; floating button removed; Europa trophy rebuilt (${europaBytes.length} bytes).`);
