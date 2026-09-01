import fs from 'node:fs';
import crypto from 'node:crypto';

const generatedDir = new URL('../assets/generated/', import.meta.url);
const premiumPath = new URL('./apply-premium-depth-v2.mjs', import.meta.url);
const uiPath = new URL('../src/BotParityAppV2.tsx', import.meta.url);

function readWebpParts(partNames, expectedSha256, label) {
  const encoded = partNames
    .map((name) => {
      const path = new URL(`../assets/background-parts/${name}`, import.meta.url);
      return fs.readFileSync(path, 'utf8').replace(/\s+/g, '');
    })
    .join('');

  if (!encoded || !/^[A-Za-z0-9+/=]+$/.test(encoded)) {
    throw new Error(`AJPA fondos locales: base64 inválido para ${label}`);
  }

  const bytes = Buffer.from(encoded, 'base64');
  const sha = crypto.createHash('sha256').update(bytes).digest('hex');
  if (sha !== expectedSha256) {
    throw new Error(`AJPA fondos locales: hash incorrecto para ${label}: ${sha}`);
  }
  if (bytes.subarray(0, 4).toString('ascii') !== 'RIFF' || bytes.subarray(8, 12).toString('ascii') !== 'WEBP') {
    throw new Error(`AJPA fondos locales: ${label} no es WebP válido`);
  }

  return { bytes, sha, encoded };
}

const league = readWebpParts(
  ['league-01.b64', 'league-02.b64', 'league-03.b64', 'league-04.b64', 'league-05.b64'],
  '0e299a6bace9f76013430b8bfd65c8735566938f522b825c697541aa81af1b39',
  'Liga',
);
const market = readWebpParts(
  ['market-01.b64', 'market-02.b64', 'market-03.b64', 'market-04.b64', 'market-05.b64'],
  'b1b740927eb8e12904218c9a91218d2266348f29b285d583949299d089ccf951',
  'Mercado',
);

fs.mkdirSync(generatedDir, { recursive: true });
fs.writeFileSync(new URL('league-maradona.webp', generatedDir), league.bytes);
fs.writeFileSync(new URL('market-mbappe.webp', generatedDir), market.bytes);

// El script de profundidad existente consume este nombre. Lo reconstruimos en
// el workspace desde bloques validados para evitar truncados de Base64 en GitHub.
fs.writeFileSync(
  new URL('../assets/background-parts/league-maradona.b64', import.meta.url),
  league.encoded,
);

fs.writeFileSync(
  new URL('../src/bg_liga.ts', import.meta.url),
  `export const BG_LIGA = require('../assets/generated/league-maradona.webp');\n`,
);
fs.writeFileSync(
  new URL('../src/bg_mercado.ts', import.meta.url),
  `export const BG_MERCADO = require('../assets/generated/market-mbappe.webp');\n`,
);

// El script de profundidad valida el hash del fondo de Liga. Lo sincronizamos
// con el asset reconstruido para que CI falle sólo ante corrupción real.
let premium = fs.readFileSync(premiumPath, 'utf8');
const hashPattern = /if \(leagueSha !== '[0-9a-f]{64}'\)/;
if (!hashPattern.test(premium)) {
  throw new Error('AJPA fondos locales: no encontré validación hash de Liga');
}
premium = premium.replace(hashPattern, `if (leagueSha !== '${league.sha}')`);
fs.writeFileSync(premiumPath, premium);

// Los fondos remotos son strings, mientras Liga/Mercado son require() locales.
// ImageBackground debe admitir ambos formatos.
let ui = fs.readFileSync(uiPath, 'utf8');
const legacySource = `source={{ uri: screenBackground }}`;
const nativeSource = `source={typeof screenBackground === 'string' ? { uri: screenBackground } : screenBackground}`;
if (ui.includes(legacySource)) {
  ui = ui.replace(legacySource, nativeSource);
}
if (!ui.includes(nativeSource)) {
  throw new Error('AJPA fondos locales: ImageBackground principal no acepta assets locales');
}
fs.writeFileSync(uiPath, ui);

console.log(
  `AJPA fondos locales listos: Liga ${league.bytes.length} bytes | Mercado ${market.bytes.length} bytes`,
);
