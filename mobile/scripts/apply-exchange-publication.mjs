import fs from 'node:fs';

const uiPath = new URL('../src/BotParityAppV2.tsx', import.meta.url);
let ui = fs.readFileSync(uiPath, 'utf8');

const PATCH_MARKER = 'AJPA_EXCHANGE_PUBLICATION_V1';
if (ui.includes(PATCH_MARKER)) {
  console.log('AJPA intercambio: la pantalla de publicación ya estaba actualizada.');
  process.exit(0);
}

function requireMarker(condition, label) {
  if (!condition) throw new Error(`AJPA intercambio: no encontré ${label}`);
}

// Estado específico del intercambio. Reutilizamos allPlayers para que el DT pueda
// pedir un jugador concreto de cualquier club, pero también dejar "Cualquier propuesta".
const purchaseState = "  const [purchaseValue, setPurchaseValue] = useState('');";
requireMarker(ui.includes(purchaseState), 'estado purchaseValue');
ui = ui.replace(
  purchaseState,
  `${purchaseState}\n  // ${PATCH_MARKER}\n  const [exchangeTargetPlayerId, setExchangeTargetPlayerId] = useState<number | null>(null);\n  const [exchangeCashDifference, setExchangeCashDifference] = useState('');\n  const [exchangeSearchText, setExchangeSearchText] = useState('');\n  const [exchangeLoadingPlayers, setExchangeLoadingPlayers] = useState(false);`,
);

const startReset = "    setPurchaseValue('');\n    setScreen('publish');";
requireMarker(ui.includes(startReset), 'reinicio de startPublish');
ui = ui.replace(
  startReset,
  "    setPurchaseValue('');\n    setExchangeTargetPlayerId(null);\n    setExchangeCashDifference('');\n    setExchangeSearchText('');\n    setScreen('publish');",
);

const submitMarker = '  const submitPublication = () => {';
const submitPos = ui.indexOf(submitMarker);
requireMarker(submitPos >= 0, 'submitPublication');

const exchangeLoader = String.raw`  const loadExchangePlayers = async () => {
    if (allPlayers.length > 0 || !snapshot || exchangeLoadingPlayers) return;
    setExchangeLoadingPlayers(true);
    try {
      const chunks = await Promise.all(snapshot.clubs.map((club) => fetchRoster(club.name)));
      setAllPlayers(chunks.flat());
    } catch (error) {
      Alert.alert('Intercambio', apiError(error));
    } finally {
      setExchangeLoadingPlayers(false);
    }
  };

`;
ui = ui.slice(0, submitPos) + exchangeLoader + ui.slice(submitPos);

const priceValidation = String.raw`    if (!publishPrice.trim()) {
      Alert.alert('Precio requerido', 'Indicá el precio o cargo de la operación.');
      return;
    }`;
requireMarker(ui.includes(priceValidation), 'validación de precio');
ui = ui.replace(
  priceValidation,
  String.raw`    if (publishType !== 'INTERCAMBIO' && !publishPrice.trim()) {
      Alert.alert('Precio requerido', 'Indicá el precio o cargo de la operación.');
      return;
    }`,
);

const mutateMarker = String.raw`    mutate(
      () => publishPlayer({
        player_id: publishTarget.id!,
        operation_type: publishType,
        price: publishPrice,
        detail: publishDetail,`;
requireMarker(ui.includes(mutateMarker), 'payload de publicación');
ui = ui.replace(
  mutateMarker,
  String.raw`    const exchangeTarget = exchangeTargetPlayerId
      ? allPlayers.find((player) => player.id === exchangeTargetPlayerId) ?? null
      : null;
    const cashDifferenceDigits = exchangeCashDifference.replace(/[^0-9]/g, '');
    const exchangeDetail = [
      exchangeTarget ? 'Busca: ' + exchangeTarget.name + ' (' + exchangeTarget.club + ')' : 'Cualquier propuesta',
      cashDifferenceDigits
        ? 'Diferencia en dinero: $' + Number(cashDifferenceDigits).toLocaleString('es-AR')
        : null,
      publishDetail.trim() ? 'Observación: ' + publishDetail.trim() : null,
    ].filter(Boolean).join(' · ');

    mutate(
      () => publishPlayer({
        player_id: publishTarget.id!,
        operation_type: publishType,
        // El backend histórico exige un precio numérico. En intercambio se guarda 0,
        // pero la app no lo muestra como precio: las condiciones quedan en el detalle.
        price: publishType === 'INTERCAMBIO' ? '0' : publishPrice,
        detail: publishType === 'INTERCAMBIO' ? exchangeDetail : publishDetail,`,
);

const publishScreenMarker = '  const publishScreen = (';
const publishScreenPos = ui.indexOf(publishScreenMarker);
requireMarker(publishScreenPos >= 0, 'publishScreen');
const exchangeComputed = String.raw`  const selectedExchangeTarget = exchangeTargetPlayerId
    ? allPlayers.find((player) => player.id === exchangeTargetPlayerId) ?? null
    : null;
  const exchangeSearchKey = exchangeSearchText.trim().toLowerCase();
  const exchangeCandidates = allPlayers.filter((player) => {
    if (!player.id || player.id === publishTarget?.id) return false;
    if (profile?.club && player.club.toLowerCase() === profile.club.toLowerCase()) return false;
    if (!exchangeSearchKey) return true;
    return (player.name + ' ' + player.club + ' ' + player.position).toLowerCase().includes(exchangeSearchKey);
  });

`;
ui = ui.slice(0, publishScreenPos) + exchangeComputed + ui.slice(publishScreenPos);

const operationButton = "              <Button key={type} label={type} kind={publishType === type ? 'blue' : 'ghost'} onPress={() => setPublishType(type)} />";
requireMarker(ui.includes(operationButton), 'botones de tipo de operación');
ui = ui.replace(
  operationButton,
  String.raw`              <Button
                key={type}
                label={type}
                kind={publishType === type ? 'blue' : 'ghost'}
                onPress={() => {
                  setPublishType(type);
                  if (type === 'INTERCAMBIO') void loadExchangePlayers();
                }}
              />`,
);

const oldPriceBlock = String.raw`          <Text style={s.inputLabel}>{publishType === 'PRÉSTAMO' ? 'CARGO / PRECIO' : 'PRECIO PEDIDO'}</Text>
          <TextInput style={s.input} keyboardType="numeric" value={publishPrice} onChangeText={setPublishPrice} placeholder="Ej: 5000000" placeholderTextColor="#657382" />`;
requireMarker(ui.includes(oldPriceBlock), 'campo Precio pedido');
const exchangeBlock = String.raw`          {publishType === 'INTERCAMBIO' ? (
            <>
              <Text style={s.inputLabel}>JUGADOR QUE BUSCÁS</Text>
              <Button
                label="CUALQUIER PROPUESTA"
                kind={exchangeTargetPlayerId === null ? 'blue' : 'ghost'}
                onPress={() => setExchangeTargetPlayerId(null)}
              />

              <TextInput
                style={s.input}
                value={exchangeSearchText}
                onChangeText={setExchangeSearchText}
                placeholder="Buscar jugador o club"
                placeholderTextColor="#657382"
              />

              {exchangeLoadingPlayers ? <ActivityIndicator color={C.blue} /> : null}
              {!exchangeLoadingPlayers && exchangeCandidates.length > 0 ? (
                <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={s.horizontalChoices}>
                  {exchangeCandidates.slice(0, 60).map((player) => (
                    <Button
                      key={player.club + '-' + player.id}
                      label={player.name + ' · ' + player.club}
                      kind={exchangeTargetPlayerId === player.id ? 'blue' : 'ghost'}
                      onPress={() => setExchangeTargetPlayerId(player.id)}
                    />
                  ))}
                </ScrollView>
              ) : null}

              <Text style={s.detail}>
                {selectedExchangeTarget
                  ? 'Buscás a ' + selectedExchangeTarget.name + ' (' + selectedExchangeTarget.club + ').'
                  : 'Aceptás cualquier propuesta de jugador.'}
              </Text>

              <Text style={s.inputLabel}>DIFERENCIA EN DINERO · OPCIONAL</Text>
              <TextInput
                style={s.input}
                keyboardType="numeric"
                value={exchangeCashDifference}
                onChangeText={(value) => setExchangeCashDifference(value.replace(/[^0-9]/g, ''))}
                placeholder="0"
                placeholderTextColor="#657382"
              />
            </>
          ) : (
            <>
              <Text style={s.inputLabel}>{publishType === 'PRÉSTAMO' ? 'CARGO / PRECIO' : 'PRECIO PEDIDO'}</Text>
              <TextInput style={s.input} keyboardType="numeric" value={publishPrice} onChangeText={setPublishPrice} placeholder="Ej: 5000000" placeholderTextColor="#657382" />
            </>
          )}`;
ui = ui.replace(oldPriceBlock, exchangeBlock);

// En el listado del mercado un intercambio no debe aparecer visualmente como "$0".
const marketPrice = '<Text style={[s.price, item.is_free_agent && { color: C.green }]}>{item.price}</Text>';
if (ui.includes(marketPrice)) {
  ui = ui.replace(
    marketPrice,
    "{String(item.operation_type || '').toUpperCase() === 'INTERCAMBIO' ? null : <Text style={[s.price, item.is_free_agent && { color: C.green }]}>{item.price}</Text>}",
  );
}

fs.writeFileSync(uiPath, ui);
console.log('AJPA intercambio listo: jugador buscado, cualquier propuesta, diferencia opcional y observación.');
