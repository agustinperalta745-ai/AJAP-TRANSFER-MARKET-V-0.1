import crypto from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';

const chunkDir = path.resolve('assets/xi_ideal_splash_chunks');
const outDir = path.resolve('assets/generated');
const outPath = path.join(outDir, 'xi-ideal-splash.webp');
const expectedSha = '8c40df5fbe20e517e5fdd4cb9dddec2b202c617c072785d508b70807d18b06ac';
const expectedBytes = 158124;

const names = Array.from({ length: 18 }, (_, i) => `${String(i).padStart(2, '0')}.txt`);
const base64 = names
  .map((name) => fs.readFileSync(path.join(chunkDir, name), 'utf8').replace(/\s+/g, ''))
  .join('');

if (!/^[A-Za-z0-9+/=]+$/.test(base64)) {
  throw new Error('XI Ideal splash: invalid base64');
}

const bytes = Buffer.from(base64, 'base64');
if (bytes.length !== expectedBytes) {
  throw new Error(`XI Ideal splash: unexpected size ${bytes.length}; expected ${expectedBytes}`);
}

const sha = crypto.createHash('sha256').update(bytes).digest('hex');
if (sha !== expectedSha) {
  throw new Error(`XI Ideal splash: SHA mismatch ${sha}`);
}

if (
  bytes.subarray(0, 4).toString('ascii') !== 'RIFF' ||
  bytes.subarray(8, 12).toString('ascii') !== 'WEBP'
) {
  throw new Error('XI Ideal splash: invalid WEBP');
}

fs.mkdirSync(outDir, { recursive: true });
fs.writeFileSync(outPath, bytes);
console.log(`XI Ideal splash ready: ${outPath} (${bytes.length} bytes) sha=${sha}`);
