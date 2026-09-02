import fs from 'node:fs';

const path = 'src/BotParityAppV2.tsx';
const lines = fs.readFileSync(path, 'utf8').split('\n');
const markers = ['const exchangeTarget =', 'JUGADOR QUE BUSCÁS', 'AJPA_EXCHANGE_PUBLICATION_V1'];
const seen = new Set();
for (const marker of markers) {
  const index = lines.findIndex((line) => line.includes(marker));
  if (index < 0 || seen.has(index)) continue;
  seen.add(index);
  const start = Math.max(0, index - 8);
  const end = Math.min(lines.length, index + 70);
  console.log(`AJPA DEBUG ${marker} lines ${start + 1}-${end}`);
  for (let i = start; i < end; i += 1) console.log(`${i + 1}: ${lines[i]}`);
}
