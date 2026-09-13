import fs from 'node:fs';

const sourceFile = 'assets/trophies/champions-ajpa-card-icon.png.b64.txt';
const iconFile = 'assets/trophies/champions-ajpa-card-icon.png';
const hubFile = 'src/CupHubScreen.tsx';

if (!fs.existsSync(sourceFile)) {
  throw new Error('Champions card icon: base64 source file not found.');
}

const base64 = fs.readFileSync(sourceFile, 'utf8').replace(/\s+/g, '');
const bytes = Buffer.from(base64, 'base64');
const isPng = bytes.length === 19038
  && bytes[0] === 0x89
  && bytes[1] === 0x50
  && bytes[2] === 0x4e
  && bytes[3] === 0x47
  && bytes[4] === 0x0d
  && bytes[5] === 0x0a
  && bytes[6] === 0x1a
  && bytes[7] === 0x0a;

if (!isPng) {
  throw new Error(`Champions card icon: invalid PNG (${bytes.length} bytes).`);
}

fs.writeFileSync(iconFile, bytes);

let hub = fs.readFileSync(hubFile, 'utf8');
const bannerAnchor = "const CHAMPIONS_BANNER = require('../assets/trophies/champions-ajpa-banner.jpg');";
const iconConst = "const CHAMPIONS_CARD_ICON = require('../assets/trophies/champions-ajpa-card-icon.png');";

if (!hub.includes(iconConst)) {
  if (!hub.includes(bannerAnchor)) {
    throw new Error('Champions card icon: Champions banner anchor not found.');
  }
  hub = hub.replace(bannerAnchor, `${bannerAnchor}\n${iconConst}`);
}

if (hub.includes('trophy: CHAMPIONS_TROPHY,')) {
  hub = hub.replace('trophy: CHAMPIONS_TROPHY,', 'trophy: CHAMPIONS_CARD_ICON,');
}

if (!hub.includes('image: CHAMPIONS_BANNER,')
  || !hub.includes('trophy: CHAMPIONS_CARD_ICON,')
  || !hub.includes(iconConst)) {
  throw new Error('Champions card icon: final CupHub validation failed.');
}

fs.writeFileSync(hubFile, hub);
console.log('AJPA Champions: PNG transparente usado solo en la miniatura/cuadrado de la tarjeta; banner intacto.');
