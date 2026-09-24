import crypto from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';

const chunkDir = path.resolve('assets/xi_ideal_splash_chunks');
const outDir = path.resolve('assets/generated');
const outPath = path.join(outDir, 'xi-ideal-splash.webp');

const names = Array.from({ length: 17 }, (_, i) => `${String(i).padStart(2, '0')}.txt`);
const pieces = names.map((name) => {
  const base64 = fs.readFileSync(path.join(chunkDir, name), 'utf8').replace(/\s+/g, '');
  if (!/^[A-Za-z0-9+/=]+$/.test(base64)) {
    throw new Error(`XI Ideal splash: invalid base64 in ${name}`);
  }
  return Buffer.from(base64, 'base64');
});

const bytes = Buffer.concat(pieces);

if (
  bytes.subarray(0, 4).toString('ascii') !== 'RIFF' ||
  bytes.subarray(8, 12).toString('ascii') !== 'WEBP'
) {
  throw new Error('XI Ideal splash: invalid WEBP');
}

const sha = crypto.createHash('sha256').update(bytes).digest('hex');
fs.mkdirSync(outDir, { recursive: true });
fs.writeFileSync(outPath, bytes);
console.log(`XI Ideal splash ready: ${outPath} (${bytes.length} bytes) sha=${sha}`);
