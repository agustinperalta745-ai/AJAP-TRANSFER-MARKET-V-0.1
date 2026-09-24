import crypto from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';

const chunkDir = path.resolve('assets/xi_ideal_splash_chunks');
const outDir = path.resolve('assets/generated');
const outPath = path.join(outDir, 'xi-ideal-splash.jpg');
const expectedSha = 'dd4d4a3a6bd9c5dfe71422e73a210b4982003865801f032978934af7456643f6';
const expectedBytes = 82717;

const names = Array.from({ length: 10 }, (_, i) => `${String(i).padStart(2, '0')}.txt`);
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

if (!(bytes[0] === 0xff && bytes[1] === 0xd8 && bytes.at(-2) === 0xff && bytes.at(-1) === 0xd9)) {
  throw new Error('XI Ideal splash: invalid JPEG');
}

fs.mkdirSync(outDir, { recursive: true });
fs.writeFileSync(outPath, bytes);
console.log(`XI Ideal splash ready: ${outPath} (${bytes.length} bytes) sha=${sha}`);
