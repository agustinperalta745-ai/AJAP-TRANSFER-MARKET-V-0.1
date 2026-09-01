import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';

// Reconstruye la capa de escudos que se veía nítida: fuentes grandes PNG con
// transparencia, embebidas en el APK. No toca assets/teams (las miniaturas
// históricas que provocaron la regresión de calidad y fondos negros).
const OUT = 'assets/teams_hq';
const USER_AGENT = 'AJPA-Transfer-Market/0.1 mobile-build (club badge assets)';

// Mónaco se genera desde el vector ya guardado por apply-monaco-badge-test.mjs.
// Atlético usa el render 512x512 del EPS original desde src/atleticoBadge.ts.
// Feyenoord conserva EXACTAMENTE el PNG HQ transparente que ya habíamos dejado
// bien en el commit histórico 3b9b21fd..., en lugar de volver a buscar otro logo.
const FEYENOORD_HQ = 'https://raw.githubusercontent.com/agustinperalta745-ai/AJAP-TRANSFER-MARKET-V-0.1/3b9b21fd38a5e5514c6453a65aeb938c533af5b7/mobile/assets/teams/feyenoord.png';

const wikipediaBadges = {
  ajax: ['AFC Ajax'],
  aston_villa: ['Aston Villa F.C.', 'Aston Villa FC'],
  benfica: ['S.L. Benfica', 'SL Benfica'],
  bolton_wanderers: ['Bolton Wanderers F.C.', 'Bolton Wanderers FC'],
  everton: ['Everton F.C.', 'Everton FC'],
  fiorentina: ['ACF Fiorentina'],
  fulham: ['Fulham F.C.', 'Fulham FC'],
  galatasaray: ['Galatasaray S.K. (football)', 'Galatasaray S.K.'],
  lazio: ['S.S. Lazio', 'SS Lazio'],
  manchester_city: ['Manchester City F.C.', 'Manchester City FC'],
  middlesbrough: ['Middlesbrough F.C.', 'Middlesbrough FC'],
  olympique_lyon: ['Olympique Lyonnais'],
  olympique_marseille: ['Olympique de Marseille'],
  porto: ['FC Porto'],
  psg: ['Paris Saint-Germain F.C.', 'Paris Saint-Germain FC'],
  real_betis: ['Real Betis'],
  sevilla: ['Sevilla FC'],
  torino: ['Torino FC'],
  tottenham_hotspur: ['Tottenham Hotspur F.C.', 'Tottenham Hotspur FC'],
  villarreal: ['Villarreal CF'],
  west_ham_united: ['West Ham United F.C.', 'West Ham United FC'],
  zaragoza: ['Real Zaragoza'],
};

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
  if (bytes.length < 33 || !bytes.subarray(0, 8).equals(signature)) {
    throw new Error('no es PNG');
  }
  const width = bytes.readUInt32BE(16);
  const height = bytes.readUInt32BE(20);
  const bitDepth = bytes[24];
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
  const hasAlpha = colorType === 4 || colorType === 6 || hasTrns;
  return { width, height, bitDepth, colorType, hasAlpha };
}

function validateBadge(name, bytes, { minSide = 256 } = {}) {
  const info = pngInfo(bytes);
  if (Math.max(info.width, info.height) < minSide) {
    throw new Error(`${name}: resolución insuficiente ${info.width}x${info.height}`);
  }
  if (!info.hasAlpha) {
    throw new Error(`${name}: PNG sin transparencia (type=${info.colorType}); se rechaza para evitar fondos negros/blancos`);
  }
  if (bytes.length < 5000) {
    throw new Error(`${name}: archivo sospechosamente pequeño (${bytes.length} bytes)`);
  }
  return info;
}

async function wikipediaThumbnail(title) {
  const api = `https://en.wikipedia.org/w/api.php?action=query&format=json&redirects=1&prop=pageimages&piprop=thumbnail&pithumbsize=1024&titles=${encodeURIComponent(title)}`;
  const meta = await fetchWithRetry(api, { headers: { Accept: 'application/json' } });
  const payload = await meta.json();
  const pages = payload?.query?.pages ? Object.values(payload.query.pages) : [];
  return pages[0]?.thumbnail?.source || null;
}

async function downloadWikipediaBadge(name, titles) {
  let last;
  for (const title of titles) {
    try {
      const uri = await wikipediaThumbnail(title);
      if (!uri) throw new Error(`Wikipedia no devolvió imagen para ${title}`);
      const image = await fetchWithRetry(uri);
      const bytes = Buffer.from(await image.arrayBuffer());
      const info = validateBadge(name, bytes);
      return { bytes, info, title, uri };
    } catch (error) {
      last = error;
    }
  }
  throw new Error(`${name}: no se pudo obtener fuente HQ transparente: ${last}`);
}

function validateAtleticoDataUri() {
  const src = fs.readFileSync('src/atleticoBadge.ts', 'utf8');
  const match = src.match(/data:image\/png;base64,([A-Za-z0-9+/=]+)/);
  if (!match) throw new Error('Atlético HQ: no encontré el PNG embebido generado desde EPS');
  const bytes = Buffer.from(match[1], 'base64');
  const info = validateBadge('atletico_madrid', bytes, { minSide: 512 });
  const sha = crypto.createHash('sha256').update(bytes).digest('hex');
  console.log(`HQ badge OK atletico_madrid: ${info.width}x${info.height}, alpha, ${bytes.length} bytes, sha256=${sha}`);
}

fs.rmSync(OUT, { recursive: true, force: true });
fs.mkdirSync(OUT, { recursive: true });
validateAtleticoDataUri();

for (const [name, titles] of Object.entries(wikipediaBadges)) {
  const { bytes, info, title } = await downloadWikipediaBadge(name, titles);
  fs.writeFileSync(path.join(OUT, `${name}.png`), bytes);
  console.log(`HQ badge OK ${name}: ${info.width}x${info.height}, alpha, ${bytes.length} bytes <- ${title}`);
  await sleep(120);
}

{
  const response = await fetchWithRetry(FEYENOORD_HQ);
  const bytes = Buffer.from(await response.arrayBuffer());
  const info = validateBadge('feyenoord', bytes);
  fs.writeFileSync(path.join(OUT, 'feyenoord.png'), bytes);
  console.log(`HQ badge OK feyenoord: ${info.width}x${info.height}, alpha, ${bytes.length} bytes <- vector export histórico AJPA`);
}

const expected = [...Object.keys(wikipediaBadges), 'feyenoord'].sort();
const produced = fs.readdirSync(OUT).filter((name) => name.endsWith('.png')).map((name) => name.replace(/\.png$/, '')).sort();
if (JSON.stringify(expected) !== JSON.stringify(produced)) {
  throw new Error(`HQ badges incompletos. Esperados=${expected.join(',')} producidos=${produced.join(',')}`);
}

console.log(`Escudos HQ preparados: ${produced.length} PNG transparentes + Monaco vector + Atletico EPS. Miniaturas assets/teams intactas.`);
