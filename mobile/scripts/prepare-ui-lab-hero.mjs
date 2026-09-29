import fs from 'node:fs';

const parts = [1,2,3,4,5,6].map((n) => {
  const path = `src/heroNeutralPart${n}.ts`;
  const text = fs.readFileSync(path, 'utf8');
  const match = text.match(/export default '([^']*)';/s);
  if (!match) throw new Error('No se pudo leer ' + path);
  return match[1];
});

const base64 = parts.join('');
const jpeg = Buffer.from(base64, 'base64');

if (jpeg.length < 10000) throw new Error('Hero neutral demasiado chico');
if (jpeg[0] !== 0xff || jpeg[1] !== 0xd8) throw new Error('Hero neutral no empieza como JPEG');
if (jpeg[jpeg.length - 2] !== 0xff || jpeg[jpeg.length - 1] !== 0xd9) {
  throw new Error('Hero neutral no termina como JPEG');
}

fs.mkdirSync('assets', { recursive: true });
fs.writeFileSync('assets/ajpa-hero-neutral.jpg', jpeg);
console.log('AJPA UI Lab hero neutral preparado:', jpeg.length, 'bytes');
