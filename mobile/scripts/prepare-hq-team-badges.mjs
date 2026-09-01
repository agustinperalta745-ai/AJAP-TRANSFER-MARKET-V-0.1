import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';

// Ajax se prepara localmente porque necesitaba recuperar correctamente su
// interior blanco. El resto queda fijado en teamBadges.tsx al snapshot AJPA
// anterior a la regresión, para no volver a leer assets degradados desde main.
const OUT = 'assets/team_badge_ajax_hq';
const USER_AGENT = 'AJPA-Transfer-Market/0.1 mobile-build (club badge assets)';

const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

async function fetchWithRetry(url, options = {}) {
  let last;
  for (let attempt = 1; attempt <= 5; attempt += 1) {
    try {
      const response = await fetch(url, {
        ...options,
        headers: { 'User-Agent': USER_AGENT, ...(options.headers || {}) },
      });
      if (response.ok) return response;
      last = new Error(`HTTP ${response.status} ${response.statusText}`);
    } catch (error) {
      last = error;
    }
    await sleep(attempt * 700);
  }
  throw last;
}

function pngInfo(bytes) {
  const signature = Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]);
  if (bytes.length < 33 || !bytes.subarray(0, 8).equals(signature)) throw new Error('no es PNG');
  const width = bytes.readUInt32BE(16);
  const height = bytes.readUInt32BE(20);
  const colorType = bytes[25];
  let hasTrns = false;
  let offset = 8;
  while (offset + 12 <= bytes.length) {
    const length = bytes.readUInt32BE(offset);
    const type = bytes.toString('ascii', offset + 4, offset + 8);
    if (type === 'tRNS') hasTrns = true;
    offset += 12 + length;
    if (type === 'IEND') break;
  }
  return { width, height, colorType, hasAlpha: colorType === 4 || colorType === 6 || hasTrns };
}

function validate(name, bytes, minSide) {
  const info = pngInfo(bytes);
  if (Math.max(info.width, info.height) < minSide) throw new Error(`${name}: resolución ${info.width}x${info.height}`);
  if (!info.hasAlpha) throw new Error(`${name}: no tiene transparencia`);
  return info;
}

async function wikipediaAjax() {
  const api = 'https://en.wikipedia.org/w/api.php?action=query&format=json&redirects=1&prop=pageimages&piprop=thumbnail&pithumbsize=1024&titles=AFC%20Ajax';
  const meta = await fetchWithRetry(api, { headers: { Accept: 'application/json' } });
  const payload = await meta.json();
  const page = Object.values(payload?.query?.pages || {})[0];
  const uri = page?.thumbnail?.source;
  if (!uri) throw new Error('Ajax HQ: Wikipedia no devolvió imagen');
  const response = await fetchWithRetry(uri);
  return Buffer.from(await response.arrayBuffer());
}

fs.rmSync(OUT, { recursive: true, force: true });
fs.mkdirSync(OUT, { recursive: true });

const ajax = await wikipediaAjax();
const ajaxInfo = validate('Ajax HQ', ajax, 512);
fs.writeFileSync(path.join(OUT, 'ajax.png'), ajax);
console.log(`Ajax HQ OK: ${ajaxInfo.width}x${ajaxInfo.height}, transparencia real, ${ajax.length} bytes`);

const atleticoSrc = fs.readFileSync('src/atleticoBadge.ts', 'utf8');
const match = atleticoSrc.match(/data:image\/png;base64,([A-Za-z0-9+/=]+)/);
if (!match) throw new Error('Atlético HQ: no encontré el PNG generado desde EPS');
const atletico = Buffer.from(match[1], 'base64');
const atletiInfo = validate('Atlético HQ', atletico, 512);
const atletiSha = crypto.createHash('sha256').update(atletico).digest('hex');
console.log(`Atlético HQ OK: ${atletiInfo.width}x${atletiInfo.height}, transparencia real, EPS render, sha256=${atletiSha}`);

console.log('Preparación HQ OK: Ajax local + Atlético EPS. El resto queda fijado al snapshot AJPA bueno y Mónaco al vector validado.');
