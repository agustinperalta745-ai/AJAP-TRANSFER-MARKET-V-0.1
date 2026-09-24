import crypto from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';

const chunkDir = path.resolve('assets/xi_ideal_fixed_chunks');
const outDir = path.resolve('assets/generated');
const outPath = path.join(outDir, 'xi-ideal-splash.webp');
const expectedSize = 122312;
const expectedSha = '23adf2c7b667096d35b2410ecf19536353a3c264b10e61cdfab0984a041abd69';

const names = Array.from({ length: 12 }, (_, i) => `${String(i).padStart(2, '0')}.txt`);
const pieces = names.map((name) => {
  const base64 = fs.readFileSync(path.join(chunkDir, name), 'utf8').replace(/\s+/g, '');
  if (!/^[A-Za-z0-9+/=]+$/.test(base64)) {
    throw new Error(`XI Ideal splash: invalid base64 in ${name}`);
  }
  return Buffer.from(base64, 'base64');
});

const bytes = Buffer.concat(pieces);
const sha = crypto.createHash('sha256').update(bytes).digest('hex');

if (
  bytes.length !== expectedSize ||
  bytes.subarray(0, 4).toString('ascii') !== 'RIFF' ||
  bytes.subarray(8, 12).toString('ascii') !== 'WEBP' ||
  sha !== expectedSha
) {
  throw new Error(
    `XI Ideal splash validation failed: size=${bytes.length}, sha=${sha}`,
  );
}

fs.mkdirSync(outDir, { recursive: true });
fs.writeFileSync(outPath, bytes);
console.log(`XI Ideal splash verified: ${outPath} (${bytes.length} bytes) sha=${sha}`);
