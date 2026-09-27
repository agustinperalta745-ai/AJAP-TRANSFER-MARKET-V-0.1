import fs from 'node:fs';

const sourceFile = 'assets/trophies/champions-ajpa-card-icon.png.b64.txt';
const championsIconFile = 'assets/trophies/champions-ajpa-card-icon.png';
const europaIconFile = 'assets/trophies/europa-ajpa-card-icon.png';
const hubFile = 'src/CupHubScreen.tsx';
const centerFile = 'src/CupCenterFab.tsx';

if (!fs.existsSync(sourceFile)) {
  throw new Error('Champions card icon: base64 source file not found.');
}

const base64 = fs.readFileSync(sourceFile, 'utf8').replace(/\s+/g, '');
const championsBytes = Buffer.from(base64, 'base64');
const championsIsPng = championsBytes.length === 1992
  && championsBytes[0] === 0x89
  && championsBytes[1] === 0x50
  && championsBytes[2] === 0x4e
  && championsBytes[3] === 0x47
  && championsBytes[4] === 0x0d
  && championsBytes[5] === 0x0a
  && championsBytes[6] === 0x1a
  && championsBytes[7] === 0x0a;

if (!championsIsPng) {
  throw new Error(`Champions card icon: invalid PNG (${championsBytes.length} bytes).`);
}

fs.writeFileSync(championsIconFile, championsBytes);

if (!fs.existsSync(europaIconFile)) {
  throw new Error('Europa card icon: PNG source file not found.');
}
const europaBytes = fs.readFileSync(europaIconFile);
const europaIsPng = europaBytes.length === 5397
  && europaBytes[0] === 0x89
  && europaBytes[1] === 0x50
  && europaBytes[2] === 0x4e
  && europaBytes[3] === 0x47
  && europaBytes[4] === 0x0d
  && europaBytes[5] === 0x0a
  && europaBytes[6] === 0x1a
  && europaBytes[7] === 0x0a;
if (!europaIsPng) {
  throw new Error(`Europa card icon: invalid PNG (${europaBytes.length} bytes).`);
}

let hub = fs.readFileSync(hubFile, 'utf8');
const championsBannerAnchor = "const CHAMPIONS_BANNER = require('../assets/trophies/champions-ajpa-banner.jpg');";
const championsIconConst = "const CHAMPIONS_CARD_ICON = require('../assets/trophies/champions-ajpa-card-icon.png');";
const europaBannerAnchor = "const EUROPA_BANNER = require('../assets/trophies/europa-ajpa-banner.jpg');";
const europaIconConst = "const EUROPA_CARD_ICON = require('../assets/trophies/europa-ajpa-card-icon.png');";

if (!hub.includes(championsIconConst)) {
  if (!hub.includes(championsBannerAnchor)) {
    throw new Error('Champions card icon: Champions banner anchor not found.');
  }
  hub = hub.replace(championsBannerAnchor, `${championsBannerAnchor}\n${championsIconConst}`);
}

if (!hub.includes(europaIconConst)) {
  if (!hub.includes(europaBannerAnchor)) {
    throw new Error('Europa card icon: Europa banner anchor not found.');
  }
  hub = hub.replace(europaBannerAnchor, `${europaBannerAnchor}\n${europaIconConst}`);
}

if (hub.includes('trophy: CHAMPIONS_TROPHY,')) {
  hub = hub.replace('trophy: CHAMPIONS_TROPHY,', 'trophy: CHAMPIONS_CARD_ICON,');
}
if (hub.includes('trophy: EUROPA_TROPHY,')) {
  hub = hub.replace('trophy: EUROPA_TROPHY,', 'trophy: EUROPA_CARD_ICON,');
}

if (!hub.includes('image: CHAMPIONS_BANNER,')
  || !hub.includes('image: EUROPA_BANNER,')
  || !hub.includes('trophy: CHAMPIONS_CARD_ICON,')
  || !hub.includes('trophy: EUROPA_CARD_ICON,')
  || !hub.includes(championsIconConst)
  || !hub.includes(europaIconConst)) {
  throw new Error('Cup card icons: final CupHub validation failed.');
}

fs.writeFileSync(hubFile, hub);

let center = fs.readFileSync(centerFile, 'utf8');
const oldChampionsCenterIcon = "const CHAMPIONS_TROPHY = require('../assets/trophies/champions-ajpa.jpg');";
const newChampionsCenterIcon = "const CHAMPIONS_TROPHY = require('../assets/trophies/champions-ajpa-card-icon.png');";
const oldEuropaCenterIcon = "const EUROPA_TROPHY = require('../assets/trophies/europa-ajpa.jpg');";
const newEuropaCenterIcon = "const EUROPA_TROPHY = require('../assets/trophies/europa-ajpa-card-icon.png');";

if (center.includes(oldChampionsCenterIcon)) {
  center = center.replace(oldChampionsCenterIcon, newChampionsCenterIcon);
}
if (center.includes(oldEuropaCenterIcon)) {
  center = center.replace(oldEuropaCenterIcon, newEuropaCenterIcon);
}

if (!center.includes(newChampionsCenterIcon)
  || !center.includes(newEuropaCenterIcon)
  || !center.includes("competition === 'champions' ? CHAMPIONS_TROPHY : EUROPA_TROPHY")) {
  throw new Error('Cup header icons: final CupCenter validation failed.');
}

fs.writeFileSync(centerFile, center);
console.log('AJPA Copas: PNG transparentes usados en miniaturas y encabezados de Champions/Europa; banners intactos.');
