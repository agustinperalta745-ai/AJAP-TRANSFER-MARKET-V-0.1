import fs from 'node:fs';

const path = new URL('../src/BotParityAppV2.tsx', import.meta.url);
let source = fs.readFileSync(path, 'utf8');
const marker = '// player-pes6-stats applied';

if (source.includes(marker)) {
  process.exit(0);
}

const importLine = "import PlayerPes6StatsButton from './PlayerPes6StatsButton';";
if (!source.includes(importLine)) {
  const typeAnchor = '\ntype Screen =';
  const typeIndex = source.indexOf(typeAnchor);
  if (typeIndex < 0) throw new Error('No se encontró type Screen en BotParityAppV2.tsx');
  source = `${source.slice(0, typeIndex)}\n${importLine}\n${source.slice(typeIndex)}`;
}

const actionsAnchor = '      {actions ? <View style={s.actionRow}>{actions}</View> : null}';

const playerCardStart = source.indexOf('function PlayerCard(');
const marketCardStart = source.indexOf('\nfunction MarketCard(', playerCardStart);
if (playerCardStart < 0 || marketCardStart < 0) {
  throw new Error('No se encontró el bloque PlayerCard');
}

let playerCard = source.slice(playerCardStart, marketCardStart);
if (!playerCard.includes('<PlayerPes6StatsButton player={player} />')) {
  if (!playerCard.includes(actionsAnchor)) {
    throw new Error('No se encontró el ancla de acciones de PlayerCard');
  }
  playerCard = playerCard.replace(
    actionsAnchor,
    `      <PlayerPes6StatsButton player={player} />\n${actionsAnchor}`,
  );
}
source = source.slice(0, playerCardStart) + playerCard + source.slice(marketCardStart);

const marketCardStart2 = source.indexOf('function MarketCard(');
const offerCardStart = source.indexOf('\nfunction OfferCard(', marketCardStart2);
if (marketCardStart2 < 0 || offerCardStart < 0) {
  throw new Error('No se encontró el bloque MarketCard');
}

let marketCard = source.slice(marketCardStart2, offerCardStart);
if (!marketCard.includes('player_id: item.player_id')) {
  if (!marketCard.includes(actionsAnchor)) {
    throw new Error('No se encontró el ancla de acciones de MarketCard');
  }
  marketCard = marketCard.replace(
    actionsAnchor,
    `      <PlayerPes6StatsButton
        player={{
          id: item.player_id,
          code: item.player_code,
          name: item.player,
          position: item.position,
          club: item.club,
          ovr: item.ovr,
          market_value: item.market_value,
        }}
      />
${actionsAnchor}`,
  );
}
source = source.slice(0, marketCardStart2) + marketCard + source.slice(offerCardStart);

source = `${source.trimEnd()}\n${marker}\n`;
fs.writeFileSync(path, source);
console.log('AJPA Mobile: estadísticas PES6 visibles en planteles, búsqueda y todas las tarjetas del mercado.');
