import fs from 'node:fs';
import crypto from 'node:crypto';

const generatedDir = new URL('../assets/generated/', import.meta.url);
const premiumPath = new URL('./apply-premium-depth-v2.mjs', import.meta.url);
const uiPath = new URL('../src/BotParityAppV2.tsx', import.meta.url);

function readWebpBase64(filename, expectedSha256, label) {
  const path = new URL(`../assets/background-parts/${filename}`, import.meta.url);
  const encoded = fs.readFileSync(path, 'utf8').replace(/\s+/g, '');
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
  return { bytes, sha };
}

const league = readWebpBase64(
  'league-maradona.b64',
  '151224c7d70d755a0c8dba18628085227d3398223802b280ee232f80f538c7b1',
  'Liga',
);
const market = readWebpBase64(
  'market-mbappe.b64',
  '83311eccab2263af28ea9455bf2d2b644fba05824bea962319d6ae6f187525d6',
  'Mercado',
);

fs.mkdirSync(generatedDir, { recursive: true });
fs.writeFileSync(new URL('league-maradona.webp', generatedDir), league.bytes);
fs.writeFileSync(new URL('market-mbappe.webp', generatedDir), market.bytes);

fs.writeFileSync(
  new URL('../src/bg_liga.ts', import.meta.url),
  `export const BG_LIGA = require('../assets/generated/league-maradona.webp');\n`,
);
fs.writeFileSync(
  new URL('../src/bg_mercado.ts', import.meta.url),
  `export const BG_MERCADO = require('../assets/generated/market-mbappe.webp');\n`,
);

// El script de profundidad valida el hash del fondo de Liga. Lo sincronizamos
// con el asset local aprobado para que no haya conversiones ni Pillow en CI.
let premium = fs.readFileSync(premiumPath, 'utf8');
const hashPattern = /if \(leagueSha !== '[0-9a-f]{64}'\)/;
if (!hashPattern.test(premium)) {
  throw new Error('AJPA fondos locales: no encontré validación hash de Liga');
}
premium = premium.replace(hashPattern, `if (leagueSha !== '${league.sha}')`);
fs.writeFileSync(premiumPath, premium);

// Los fondos remotos son strings, mientras Liga/Mercado ahora son require().
// ImageBackground debe aceptar ambas formas sin envolver un asset local en uri.
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

console.log(`AJPA fondos locales listos: Liga ${league.bytes.length} bytes | Mercado ${market.bytes.length} bytes`);
