import fs from 'node:fs';
import crypto from 'node:crypto';

const chunkDir = 'assets/team_badge_hd3k_chunks';
const badgePath = 'assets/team_badge_test/as_monaco_hd.png';
const expectedSha = '7c5f6a3de64725801f500e6a1895a736c26733909b88d73ed6b083ae38ef2e75';

if (!fs.existsSync(chunkDir)) throw new Error('UI Lab: faltan chunks Monaco');
const parts = fs.readdirSync(chunkDir).filter((name) => name.endsWith('.txt')).sort();
if (!parts.length) throw new Error('UI Lab: no hay chunks Monaco');
const base64 = parts.map((name) => fs.readFileSync(chunkDir + '/' + name, 'utf8').trim()).join('').replace(/\s+/g, '');
const badge = Buffer.from(base64, 'base64');
const sha = crypto.createHash('sha256').update(badge).digest('hex');
if (sha !== expectedSha) throw new Error('UI Lab: Monaco SHA inesperado ' + sha);

fs.mkdirSync('assets/team_badge_test', { recursive: true });
fs.writeFileSync(badgePath, badge);
console.log('UI Lab: Monaco HD preparado sin tocar la UI');
