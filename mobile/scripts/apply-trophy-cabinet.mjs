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

const file = 'App.tsx';
let source = fs.readFileSync(file, 'utf8');

const importLine = "import TrophyCabinetFab from './src/TrophyCabinetFab';";
if (!source.includes(importLine)) {
  const anchor = "import SeasonHistoryFab from './src/SeasonHistoryFab';";
  if (!source.includes(anchor)) throw new Error('Trophy cabinet: SeasonHistoryFab import anchor not found.');
  source = source.replace(anchor, `${anchor}\n${importLine}`);
}

if (!source.includes('<TrophyCabinetFab />')) {
  const anchor = '        <SeasonHistoryFab />';
  if (!source.includes(anchor)) throw new Error('Trophy cabinet: SeasonHistoryFab mount anchor not found.');
  source = source.replace(anchor, `${anchor}\n        <TrophyCabinetFab />`);
}

if (!source.includes(importLine) || !source.includes('<TrophyCabinetFab />')) {
  throw new Error('Trophy cabinet: final App.tsx validation failed.');
}

fs.writeFileSync(file, source);
console.log(`AJPA trophy cabinet preserved; Europa trophy rebuilt (${europaBytes.length} bytes).`);
