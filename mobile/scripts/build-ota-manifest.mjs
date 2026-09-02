import crypto from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';

const [exportDirArg, stageDirArg, releaseArg, runtimeArg = '1'] = process.argv.slice(2);
if (!exportDirArg || !stageDirArg || !releaseArg) {
  throw new Error(
    'Uso: node scripts/build-ota-manifest.mjs <expo-export> <stage-dir> <release> [runtime]',
  );
}

const exportDir = path.resolve(exportDirArg);
const stageDir = path.resolve(stageDirArg);
const runtimeVersion = String(runtimeArg);
const release = String(releaseArg);
const repository = 'agustinperalta745-ai/AJAP-TRANSFER-MARKET-V-0.1';
const branch = 'ota-updates';

function findFile(root, fileName) {
  const stack = [root];
  while (stack.length) {
    const current = stack.pop();
    for (const entry of fs.readdirSync(current, { withFileTypes: true })) {
      const full = path.join(current, entry.name);
      if (entry.isDirectory()) stack.push(full);
      else if (entry.name === fileName) return full;
    }
  }
  return null;
}

const metadataPath = findFile(exportDir, 'metadata.json');
if (!metadataPath) throw new Error('OTA: expo export no generó metadata.json');
const exportRoot = path.dirname(metadataPath);
const metadata = JSON.parse(fs.readFileSync(metadataPath, 'utf8'));
const platformMetadata = metadata?.fileMetadata?.android;
if (!platformMetadata?.bundle) {
  throw new Error('OTA: metadata.json no contiene bundle Android');
}

const releaseDir = path.join(stageDir, 'releases', runtimeVersion, release);
fs.rmSync(stageDir, { recursive: true, force: true });
fs.mkdirSync(releaseDir, { recursive: true });
fs.cpSync(exportRoot, releaseDir, { recursive: true });

const appConfig = JSON.parse(
  fs.readFileSync(path.resolve('app.json'), 'utf8'),
).expo ?? {};

function fileBytes(relativePath) {
  const normalized = String(relativePath).replaceAll('\\', '/');
  const full = path.resolve(releaseDir, normalized);
  const base = path.resolve(releaseDir) + path.sep;
  if (!full.startsWith(base)) throw new Error(`OTA: ruta fuera del release: ${relativePath}`);
  if (!fs.existsSync(full) || !fs.statSync(full).isFile()) {
    throw new Error(`OTA: archivo referenciado inexistente: ${relativePath}`);
  }
  return { full, normalized, bytes: fs.readFileSync(full) };
}

function base64UrlSha256(bytes) {
  return crypto
    .createHash('sha256')
    .update(bytes)
    .digest('base64')
    .replaceAll('+', '-')
    .replaceAll('/', '_')
    .replace(/=+$/g, '');
}

function md5Key(bytes) {
  return crypto.createHash('md5').update(bytes).digest('hex');
}

function uuidFromSeed(seed) {
  const bytes = crypto.createHash('sha256').update(seed).digest().subarray(0, 16);
  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;
  const hex = bytes.toString('hex');
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

function contentType(ext) {
  switch (String(ext || '').toLowerCase().replace(/^\./, '')) {
    case 'png': return 'image/png';
    case 'jpg':
    case 'jpeg': return 'image/jpeg';
    case 'webp': return 'image/webp';
    case 'gif': return 'image/gif';
    case 'svg': return 'image/svg+xml';
    case 'json': return 'application/json';
    case 'ttf': return 'font/ttf';
    case 'otf': return 'font/otf';
    case 'woff': return 'font/woff';
    case 'woff2': return 'font/woff2';
    case 'mp3': return 'audio/mpeg';
    case 'mp4': return 'video/mp4';
    default: return 'application/octet-stream';
  }
}

function rawUrl(relativePath) {
  const encoded = String(relativePath)
    .replaceAll('\\', '/')
    .split('/')
    .map((part) => encodeURIComponent(part))
    .join('/');
  return `https://raw.githubusercontent.com/${repository}/${branch}/mobile/ota/releases/${encodeURIComponent(runtimeVersion)}/${encodeURIComponent(release)}/${encoded}`;
}

function regularAsset(asset) {
  const { normalized, bytes } = fileBytes(asset.path);
  const ext = String(asset.ext || path.extname(normalized).slice(1));
  return {
    hash: base64UrlSha256(bytes),
    key: md5Key(bytes),
    contentType: contentType(ext),
    ...(ext ? { fileExtension: `.${ext.replace(/^\./, '')}` } : {}),
    url: rawUrl(normalized),
  };
}

const launch = fileBytes(platformMetadata.bundle);
const launchHash = base64UrlSha256(launch.bytes);
const id = uuidFromSeed(`${runtimeVersion}:${release}:${launchHash}`);
const numericRelease = Number(release);
const createdAt = Number.isFinite(numericRelease)
  ? new Date(numericRelease * 1000).toISOString()
  : new Date().toISOString();

const manifest = {
  id,
  createdAt,
  runtimeVersion,
  launchAsset: {
    hash: launchHash,
    key: md5Key(launch.bytes),
    contentType: 'application/javascript',
    url: rawUrl(launch.normalized),
  },
  assets: (platformMetadata.assets ?? []).map(regularAsset),
  metadata: {},
  extra: {
    expoClient: appConfig,
    ajpa: {
      release,
      source: 'github-actions-self-hosted-ota',
    },
  },
};

fs.writeFileSync(
  path.join(releaseDir, 'manifest.android.json'),
  `${JSON.stringify(manifest, null, 2)}\n`,
);
fs.writeFileSync(
  path.join(stageDir, `latest-${runtimeVersion}-android.json`),
  `${JSON.stringify(manifest)}\n`,
);

console.log(
  `AJPA OTA listo: runtime=${runtimeVersion} release=${release} id=${id} assets=${manifest.assets.length}`,
);
