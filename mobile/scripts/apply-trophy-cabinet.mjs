import fs from 'node:fs';

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
console.log('AJPA trophy cabinet preserved in final App.tsx');
