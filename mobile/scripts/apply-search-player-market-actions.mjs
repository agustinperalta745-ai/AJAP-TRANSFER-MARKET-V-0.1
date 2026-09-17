import fs from 'node:fs';

const path = new URL('../src/BotParityAppV2.tsx', import.meta.url);
let ui = fs.readFileSync(path, 'utf8');
const marker = '// search-player-market-actions applied';
if (ui.includes(marker)) process.exit(0);

const filteredAnchor = `  const filteredPlayers = searchText.trim()
    ? allPlayers.filter((player) => \`\${player.name} \${player.club} \${player.position}\`.toLowerCase().includes(searchText.trim().toLowerCase()))
    : [];

`;

if (!ui.includes(filteredAnchor)) {
  throw new Error('Buscar jugador: no encontré el filtro actual de jugadores.');
}

const helpers = `  const searchIdentity = (value: string | null | undefined) =>
    String(value ?? '').trim().toLocaleLowerCase('es');

  const publicationForSearchPlayer = (player: RosterPlayer) =>
    normalMarket.find((item) =>
      searchIdentity(item.player) === searchIdentity(player.name)
      && searchIdentity(item.club) === searchIdentity(player.club),
    ) ?? null;

  const startSearchOffer = (player: RosterPlayer) => {
    if (!snapshot.status.market_open) return;
    const publication = publicationForSearchPlayer(player);
    if (!publication) return;
    if (!profile?.club) {
      Alert.alert('Sin club', 'Necesitás un club asignado para realizar una oferta.');
      return;
    }
    if (searchIdentity(publication.club) === searchIdentity(profile.club)) {
      Alert.alert('Tu jugador', 'No podés ofertar por una publicación de tu propio club.');
      return;
    }
    setOfferTarget(publication);
    setOfferAmount('');
    setOfferMessage('');
    setOfferedPlayerId(null);
    setScreen('transferibles');
  };

  const startSearchClause = async (player: RosterPlayer) => {
    if (!snapshot.status.market_open) return;
    if (!profile?.club) {
      Alert.alert('Sin club', 'Necesitás un club asignado para ejecutar una cláusula.');
      return;
    }
    if (searchIdentity(player.club) === searchIdentity(profile.club)) {
      Alert.alert('Tu jugador', 'No podés ejecutar una cláusula sobre un jugador de tu propio club.');
      return;
    }

    try {
      setBusy(true);
      const clauseData = await fetchClausulazo();
      const target = (clauseData.players ?? []).find((candidate) =>
        (player.id !== null && player.id !== undefined && candidate.id === player.id)
        || (
          searchIdentity(candidate.name) === searchIdentity(player.name)
          && searchIdentity(candidate.club) === searchIdentity(player.club)
        ),
      );

      if (!target) {
        Alert.alert('Cláusula no disponible', 'Ese jugador no está habilitado para clausulazo.');
        return;
      }

      setClausulazoData(clauseData);
      setClausulazoQuery(player.name);
      setClausulazoTarget(target);
      setScreen('clausulazo');
    } catch (error) {
      Alert.alert('Clausulazo', apiError(error));
    } finally {
      setBusy(false);
    }
  };

`;

ui = ui.replace(filteredAnchor, helpers + filteredAnchor);

const oldMap = `      {filteredPlayers.slice(0, 60).map((player) => <PlayerCard key={\`\${player.club}-\${player.id ?? player.name}\`} player={player} />)}`;
const newMap = `      {filteredPlayers.slice(0, 60).map((player) => {
        const publication = publicationForSearchPlayer(player);
        const marketOpen = Boolean(snapshot.status.market_open);
        const isOwnPlayer = Boolean(profile?.club && searchIdentity(player.club) === searchIdentity(profile.club));
        const canOffer = Boolean(marketOpen && publication && profile?.club && !isOwnPlayer);
        const canClause = Boolean(marketOpen && profile?.club && !isOwnPlayer);

        return (
          <PlayerCard
            key={\`\${player.club}-\${player.id ?? player.name}\`}
            player={player}
            actions={(canOffer || canClause) ? (
              <>
                {canOffer ? (
                  <Button
                    label="💰 OFERTAR"
                    kind="blue"
                    disabled={busy}
                    onPress={() => startSearchOffer(player)}
                  />
                ) : null}
                {canClause ? (
                  <Button
                    label="💥 CLÁUSULA"
                    kind="red"
                    disabled={busy}
                    onPress={() => { void startSearchClause(player); }}
                  />
                ) : null}
              </>
            ) : null}
          />
        );
      })}`;

if (!ui.includes(oldMap)) {
  throw new Error('Buscar jugador: no encontré el render actual de PlayerCard.');
}
ui = ui.replace(oldMap, newMap);

for (const required of [
  'publicationForSearchPlayer',
  'startSearchOffer',
  'startSearchClause',
  'label="💰 OFERTAR"',
  'label="💥 CLÁUSULA"',
  'marketOpen && publication',
  'marketOpen && profile?.club',
]) {
  if (!ui.includes(required)) throw new Error(`Buscar jugador: falta ${required}`);
}

ui = `${ui.trimEnd()}\n${marker}\n`;
fs.writeFileSync(path, ui);
console.log('AJPA Buscar jugador: estadísticas + oferta condicional + cláusula condicional aplicadas.');
