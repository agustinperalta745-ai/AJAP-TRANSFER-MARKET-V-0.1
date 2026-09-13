import fs from 'node:fs';
import path from 'node:path';

const trophyDir = path.join('assets', 'trophies');
const chunksDir = path.join(trophyDir, 'liga_banner_chunks');
const bannerFile = path.join(trophyDir, 'liga-ajpa-banner.jpg');

const chunkFiles = fs.readdirSync(chunksDir)
  .filter(name => name.endsWith('.txt'))
  .sort();

if (chunkFiles.length !== 3) {
  throw new Error(`Liga vitrina banner: expected 3 chunks, found ${chunkFiles.length}.`);
}

const encoded = chunkFiles
  .map(name => fs.readFileSync(path.join(chunksDir, name), 'utf8').trim())
  .join('');

const bytes = Buffer.from(encoded, 'base64');
const isJpeg = bytes.length > 1000
  && bytes[0] === 0xff
  && bytes[1] === 0xd8
  && bytes[bytes.length - 2] === 0xff
  && bytes[bytes.length - 1] === 0xd9;

if (!isJpeg) {
  throw new Error(`Liga vitrina banner: reconstructed JPEG is invalid (${bytes.length} bytes).`);
}

fs.writeFileSync(bannerFile, bytes);

const file = 'src/TrophyCabinetFab.tsx';
let source = fs.readFileSync(file, 'utf8');

const ligaRequire = "const LIGA_BANNER = require('../assets/trophies/liga-ajpa-banner.jpg');";
const championsRequire = "const CHAMPIONS_BANNER = require('../assets/trophies/champions-ajpa-banner.jpg');";
const europaRequire = "const EUROPA_BANNER = require('../assets/trophies/europa-ajpa-banner.jpg');";

if (!source.includes(ligaRequire)) {
  if (source.includes(championsRequire)) {
    source = source.replace(championsRequire, `${ligaRequire}\n${championsRequire}`);
  } else {
    const anchor = `} as const;\n\nconst META:`;
    if (!source.includes(anchor)) throw new Error('Liga vitrina banner: TROPHY map anchor not found.');
    source = source.replace(anchor, `} as const;\n\n${ligaRequire}\n${championsRequire}\n${europaRequire}\n\nconst META:`);
  }
}

const dualBannerStage = `      <View style={trophyKey === 'league' ? styles.trophyStage : styles.competitionBannerStage}>\n        {trophyKey === 'league' ? (\n          <Image source={TROPHY[trophyKey]} resizeMode="contain" style={styles.trophyImage} />\n        ) : (\n          <Image\n            source={trophyKey === 'champions' ? CHAMPIONS_BANNER : EUROPA_BANNER}\n            resizeMode="cover"\n            fadeDuration={0}\n            style={styles.competitionBannerImage}\n          />\n        )}\n      </View>`;

const allBannerStage = `      <View style={styles.competitionBannerStage}>\n        <Image\n          source={trophyKey === 'league' ? LIGA_BANNER : trophyKey === 'champions' ? CHAMPIONS_BANNER : EUROPA_BANNER}\n          resizeMode="cover"\n          fadeDuration={0}\n          style={styles.competitionBannerImage}\n        />\n      </View>`;

const rawStage = `      <View style={styles.trophyStage}>\n        <Image source={TROPHY[trophyKey]} resizeMode="contain" style={styles.trophyImage} />\n      </View>`;

if (source.includes(dualBannerStage)) {
  source = source.replace(dualBannerStage, allBannerStage);
} else if (source.includes(rawStage)) {
  source = source.replace(rawStage, allBannerStage);
} else if (!source.includes("source={trophyKey === 'league' ? LIGA_BANNER")) {
  throw new Error('Liga vitrina banner: card image stage anchor not found.');
}

if (!source.includes('competitionBannerStage: {')) {
  const styleAnchor = `  trophyStage: {`;
  const styles = `  competitionBannerStage: {\n    width: '100%',\n    aspectRatio: 3,\n    backgroundColor: '#03070c',\n    borderBottomWidth: 1,\n    borderBottomColor: 'rgba(255,255,255,0.07)',\n    overflow: 'hidden',\n  },\n  competitionBannerImage: { width: '100%', height: '100%' },\n`;
  if (!source.includes(styleAnchor)) throw new Error('Liga vitrina banner: style anchor not found.');
  source = source.replace(styleAnchor, `${styles}${styleAnchor}`);
}

if (!source.includes(ligaRequire)
  || !source.includes("source={trophyKey === 'league' ? LIGA_BANNER")
  || !source.includes('competitionBannerImage:')) {
  throw new Error('Liga vitrina banner: final validation failed.');
}

fs.writeFileSync(file, source);
console.log(`AJPA trophy cabinet: Liga AJPA banner active (${bytes.length} bytes).`);
