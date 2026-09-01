import fs from 'node:fs';
import crypto from 'node:crypto';
import zlib from 'node:zlib';

const chunkDir = 'assets/team_badges_hq256_chunks';
const outputDir = 'assets/team_badge_hq256';
const zaragozaPath = 'assets/teams/zaragoza.png';
const expectedArchiveSha = '8a631f103fc5d7debcfead09d31ee70ef6a0c1a33ce730f8992c81902463ccf8';

const expectedChunkBlobShas = new Map([
  ['03.txt', '1ce6056238a51ca905729a9e4ce1312cc145d007'],
  ['04.txt', 'f336805d890418c99bdab8b9a3d8fc46b30101ba'],
  ['06.txt', '3a48f324c0d99d43c3b591bc11333abf655ee687'],
  ['07.txt', '60486b59b858241ccc198576ea43fb53629a4d16'],
  ['10.txt', 'ee048e5caf89e13bf97a52a3f25c23ee824b8322'],
  ['15.txt', '33809c2eb24da67ba2779d6aed550bafe3c5c26d'],
  ['16.txt', 'a053452e16edf6bb182a64bca814eafce679c9d2'],
]);

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

function gitBlobSha(text) {
  const bytes = Buffer.from(text, 'utf8');
  return crypto
    .createHash('sha1')
    .update(Buffer.from(`blob ${bytes.length}\0`, 'utf8'))
    .update(bytes)
    .digest('hex');
}

function repairChunk(name, raw) {
  const targetSha = expectedChunkBlobShas.get(name);
  const clean = raw.replace(/\s+/g, '');
  if (!targetSha) return clean;

  if (gitBlobSha(clean) === targetSha) return clean;

  const alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=';
  const targetLength = 12000;

  // Los fragmentos se cargaron como texto base64. Si hubo un único carácter
  // alterado durante la carga, recuperamos exactamente el original usando su
  // Git blob SHA conocido. Esto evita aceptar silenciosamente un paquete dañado.
  if (clean.length === targetLength) {
    const buffer = Buffer.from(clean, 'ascii');
    const header = Buffer.from(`blob ${buffer.length}\0`, 'utf8');
    for (let i = 0; i < buffer.length; i += 1) {
      const original = buffer[i];
      for (const char of alphabet) {
        const candidate = char.charCodeAt(0);
        if (candidate === original) continue;
        buffer[i] = candidate;
        const sha = crypto.createHash('sha1').update(header).update(buffer).digest('hex');
        if (sha === targetSha) {
          console.log(`HQ badges: ${name} recuperado por sustitución en posición ${i}.`);
          return buffer.toString('ascii');
        }
      }
      buffer[i] = original;
    }
  }

  if (clean.length === targetLength + 1) {
    for (let i = 0; i < clean.length; i += 1) {
      const candidate = clean.slice(0, i) + clean.slice(i + 1);
      if (gitBlobSha(candidate) === targetSha) {
        console.log(`HQ badges: ${name} recuperado eliminando un carácter extra en posición ${i}.`);
        return candidate;
      }
    }
  }

  if (clean.length === targetLength - 1) {
    for (let i = 0; i <= clean.length; i += 1) {
      for (const char of alphabet) {
        const candidate = clean.slice(0, i) + char + clean.slice(i);
        if (gitBlobSha(candidate) === targetSha) {
          console.log(`HQ badges: ${name} recuperado insertando un carácter en posición ${i}.`);
          return candidate;
        }
      }
    }
  }

  throw new Error(`HQ badges: no pude recuperar ${name}; el fragmento tiene más de una alteración`);
}

const crcTable = new Uint32Array(256);
for (let n = 0; n < 256; n += 1) {
  let c = n;
  for (let k = 0; k < 8; k += 1) c = (c & 1) ? (0xedb88320 ^ (c >>> 1)) : (c >>> 1);
  crcTable[n] = c >>> 0;
}

function crc32(buffer) {
  let crc = 0xffffffff;
  for (const byte of buffer) crc = crcTable[(crc ^ byte) & 0xff] ^ (crc >>> 8);
  return (crc ^ 0xffffffff) >>> 0;
}

function repairPngCrcs(filePath) {
  const signature = Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]);
  const png = Buffer.from(fs.readFileSync(filePath));
  if (png.length < 24 || !png.subarray(0, 8).equals(signature)) {
    throw new Error(`HQ badges: ${filePath} no es un PNG válido`);
  }
  if (png.subarray(12, 16).toString('ascii') !== 'IHDR') {
    throw new Error(`HQ badges: ${filePath} no tiene IHDR válido`);
  }

  let offset = 8;
  let repaired = 0;
  let sawIend = false;
  while (offset + 12 <= png.length) {
    const length = png.readUInt32BE(offset);
    const typeStart = offset + 4;
    const dataStart = offset + 8;
    const crcOffset = dataStart + length;
    const nextOffset = crcOffset + 4;
    if (nextOffset > png.length) throw new Error(`HQ badges: ${filePath} está truncado`);

    const type = png.subarray(typeStart, dataStart).toString('ascii');
    const expected = crc32(png.subarray(typeStart, crcOffset));
    const current = png.readUInt32BE(crcOffset);
    if (current !== expected) {
      png.writeUInt32BE(expected, crcOffset);
      repaired += 1;
    }

    offset = nextOffset;
    if (type === 'IEND') {
      sawIend = true;
      break;
    }
  }
  if (!sawIend) throw new Error(`HQ badges: ${filePath} no tiene IEND`);

  if (repaired > 0) {
    // Sólo corrige checksums CRC: no modifica ni reescala los píxeles del escudo.
    fs.writeFileSync(filePath, png);
    console.log(`HQ badges: Zaragoza actual preservado; CRC PNG reparado (${repaired} chunk).`);
  }
}

if (!fs.existsSync(chunkDir)) {
  throw new Error('HQ badges: no encontré el directorio de fragmentos');
}

const chunkNames = Array.from({ length: 23 }, (_, index) => `${String(index).padStart(2, '0')}.txt`);
for (const name of chunkNames) {
  if (!fs.existsSync(`${chunkDir}/${name}`)) throw new Error(`HQ badges: falta ${name}`);
}

const base64 = chunkNames
  .map((name) => repairChunk(name, fs.readFileSync(`${chunkDir}/${name}`, 'utf8')))
  .join('');
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

if (!fs.existsSync(zaragozaPath)) throw new Error('HQ badges: falta el escudo actual de Zaragoza');
repairPngCrcs(zaragozaPath);

if (written !== 22) throw new Error(`HQ badges: esperaba escribir 22 escudos y escribí ${written}`);
console.log(`HQ badges listos: ${written} PNG 256x256 + Monaco HD preservado + Zaragoza existente preservado + Torino excluido.`);
