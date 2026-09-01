import fs from 'node:fs';
import crypto from 'node:crypto';
import zlib from 'node:zlib';

const chunkDir = 'assets/team_badges_hq256_chunks';
const outputDir = 'assets/team_badge_hq256';
const expectedArchiveSha = 'a8715a1829cfd34754e4d1488826ec4d3df8290ec40e6c2dca31f58b056ba9cc';

const expectedFiles = [
  'ajax.png',
  'as_monaco.png',
  'aston_villa.png',
  'atletico_madrid.png',
  'benfica.png',
  'bolton_wanderers.png',
  'everton.png',
  'feyenoord.png',
  'fiorentina.png',
  'fulham.png',
  'galatasaray.png',
  'lazio.png',
  'manchester_city.png',
  'middlesbrough.png',
  'olympique_lyon.png',
  'olympique_marseille.png',
  'porto.png',
  'psg.png',
  'real_betis.png',
  'sevilla.png',
  'tottenham_hotspur.png',
  'villarreal.png',
  'west_ham_united.png',
];

if (!fs.existsSync(chunkDir)) {
  throw new Error('HQ badges: no encontré el directorio de fragmentos');
}

const chunkNames = Array.from({ length: 23 }, (_, index) => `${String(index).padStart(2, '0')}.txt`);
for (const name of chunkNames) {
  if (!fs.existsSync(`${chunkDir}/${name}`)) throw new Error(`HQ badges: falta ${name}`);
}

const base64 = chunkNames
  .map((name) => fs.readFileSync(`${chunkDir}/${name}`, 'utf8'))
  .join('')
  .replace(/\s+/g, '');
if (!base64 || !/^[A-Za-z0-9+/=]+$/.test(base64)) throw new Error('HQ badges: base64 inválido');

const archive = Buffer.from(base64, 'base64');
const archiveSha = crypto.createHash('sha256').update(archive).digest('hex');
if (archiveSha !== expectedArchiveSha) {
  throw new Error(`HQ badges: SHA-256 del paquete inesperado ${archiveSha}`);
}
if (archive[0] !== 0x1f || archive[1] !== 0x8b) throw new Error('HQ badges: el paquete no es gzip');

const tar = zlib.gunzipSync(archive);
const files = new Map();
let offset = 0;
while (offset + 512 <= tar.length) {
  const header = tar.subarray(offset, offset + 512);
  if (header.every((byte) => byte === 0)) break;

  const name = header.subarray(0, 100).toString('utf8').replace(/\0.*$/, '');
  const sizeText = header.subarray(124, 136).toString('ascii').replace(/\0.*$/, '').trim();
  const size = Number.parseInt(sizeText || '0', 8);
  if (!Number.isFinite(size) || size < 0) throw new Error(`HQ badges: tamaño TAR inválido para ${name}`);

  const start = offset + 512;
  const end = start + size;
  if (end > tar.length) throw new Error(`HQ badges: TAR truncado en ${name}`);
  if (expectedFiles.includes(name)) files.set(name, Buffer.from(tar.subarray(start, end)));
  offset = start + Math.ceil(size / 512) * 512;
}

for (const name of expectedFiles) {
  if (!files.has(name)) throw new Error(`HQ badges: falta ${name} dentro del paquete`);
}

fs.mkdirSync(outputDir, { recursive: true });
const pngSignature = Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]);
let written = 0;
for (const name of expectedFiles) {
  // Monaco conserva el PNG RGBA ya validado por apply-monaco-badge-test.mjs.
  if (name === 'as_monaco.png') continue;
  const badge = files.get(name);
  if (!badge.subarray(0, 8).equals(pngSignature)) throw new Error(`HQ badges: ${name} no es PNG válido`);
  if (badge.length < 24 || badge.subarray(12, 16).toString('ascii') !== 'IHDR') {
    throw new Error(`HQ badges: ${name} no tiene IHDR válido`);
  }
  const width = badge.readUInt32BE(16);
  const height = badge.readUInt32BE(20);
  if (width !== 256 || height !== 256) throw new Error(`HQ badges: ${name} mide ${width}x${height}, esperaba 256x256`);
  fs.writeFileSync(`${outputDir}/${name}`, badge);
  written += 1;
}

if (written !== 22) throw new Error(`HQ badges: esperaba escribir 22 escudos y escribí ${written}`);
console.log(`HQ badges listos: ${written} PNG 256x256 + Monaco HD preservado + Zaragoza existente preservado + Torino excluido.`);
