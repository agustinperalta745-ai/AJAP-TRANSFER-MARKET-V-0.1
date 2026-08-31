import fs from 'node:fs';

const uiPath = new URL('../src/BotParityAppV2.tsx', import.meta.url);
let ui = fs.readFileSync(uiPath, 'utf8');

function mustReplace(search, replacement, label) {
  if (!ui.includes(search)) throw new Error(`AJPA resignation mobile patch: no encontré ${label}`);
  ui = ui.replace(search, replacement);
}

if (!ui.includes('  resignClub,')) {
  mustReplace(
    `  releasePlayer,\n  sendOffer,`,
    `  releasePlayer,\n  resignClub,\n  sendOffer,`,
    'import de releasePlayer/sendOffer',
  );
}

const profileMarker = `  const profileScreen = (`;
if (!ui.includes('const resignScreen = (')) {
  if (!ui.includes(profileMarker)) throw new Error('AJPA resignation mobile patch: no encontré profileScreen');
  const resignScreen = String.raw`  const resignScreen = (
    <ScrollView contentContainerStyle={s.content} refreshControl={refreshControl}>
      <Title eyebrow="MI CLUB · RENUNCIA" title="Renunciar al Club" subtitle="La renuncia libera tu asignación sin borrar el plantel ni la economía del club." />
      <View style={s.card}>
        <Text style={s.infoLabel}>CLUB ACTUAL</Text>
        <Text style={s.infoValue}>{profile?.club ?? 'Sin club'}</Text>
        <View style={s.separator} />
        <Text style={s.playerName}>⚠️ Esta acción es definitiva</Text>
        <Text style={s.detail}>Tu cuenta dejará de estar vinculada al club y el equipo quedará libre para una nueva asignación. Los jugadores, presupuesto e historial del club se conservan.</Text>
        <View style={s.actionRow}>
          <Button
            label={busy ? 'PROCESANDO…' : 'CONFIRMAR RENUNCIA'}
            kind="red"
            disabled={busy || !profile?.club}
            onPress={() => Alert.alert(
              'Renunciar al Club',
              '¿Confirmás que querés renunciar a ' + (profile?.club ?? 'tu club') + '?',
              [
                { text: 'Cancelar', style: 'cancel' },
                {
                  text: 'RENUNCIAR',
                  style: 'destructive',
                  onPress: () => mutate(
                    async () => { await resignClub(); setScreen('home'); },
                    'Renuncia confirmada. El club quedó libre y conserva su plantel y economía.',
                  ),
                },
              ],
            )}
          />
        </View>
      </View>
    </ScrollView>
  );

`;
  ui = ui.replace(profileMarker, resignScreen + profileMarker);
}

mustReplace(
  `  else if (screen === 'resign') body = placeholder('Renunciar al Club', 'Renuncia con la misma validación administrativa del bot.');`,
  `  else if (screen === 'resign') body = resignScreen;`,
  'despacho placeholder de renuncia',
);

fs.writeFileSync(uiPath, ui);
console.log('AJPA Mobile: renuncia al club operativa aplicada');
