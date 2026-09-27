import fs from 'node:fs';

const uiPath = new URL('../src/BotParityAppV2.tsx', import.meta.url);
let ui = fs.readFileSync(uiPath, 'utf8');

function replaceBlock(startMarker, endMarker, replacement, label) {
  const start = ui.indexOf(startMarker);
  if (start < 0) throw new Error('Mercado approved UI: no encontré inicio de ' + label);
  const end = ui.indexOf(endMarker, start + startMarker.length);
  if (end < 0) throw new Error('Mercado approved UI: no encontré fin de ' + label);
  ui = ui.slice(0, start) + replacement + '\n\n' + ui.slice(end);
}

const visualsImport = "import { MARKET_STATUS_BG, MARKET_SEARCH_BG, MARKET_HISTORY_BG, MARKET_CLAUSE_BG, MarketIconName, MarketIconTile } from './MarketVisuals';";
if (!ui.includes(visualsImport)) {
  const miClubImport = "import { MI_CLUB_CARD_BG_DATA_URI, MiClubIcon, MiClubIconName, MiClubIconTile } from './MiClubVisuals';";
  const iconImport = "import { AjpaIcon, AjpaIconName, AjpaIconTile } from './AjpaIcon';";
  if (ui.includes(miClubImport)) ui = ui.replace(miClubImport, miClubImport + '\n' + visualsImport);
  else if (ui.includes(iconImport)) ui = ui.replace(iconImport, iconImport + '\n' + visualsImport);
  else throw new Error('Mercado approved UI: no encontré punto de import');
}

const components = String.raw`
const marketStyles = StyleSheet.create({
  status: {
    minHeight: 116, borderRadius: 20, borderWidth: 1.2, overflow: 'hidden',
    backgroundColor: '#0A2233', paddingHorizontal: 13, paddingVertical: 12,
    flexDirection: 'row', alignItems: 'center',
  },
  statusOpen: { borderColor: '#237B59' },
  statusClosed: { borderColor: '#873A45' },
  background: { ...StyleSheet.absoluteFillObject },
  statusShade: { ...StyleSheet.absoluteFillObject, backgroundColor: 'rgba(3, 18, 30, 0.48)' },
  statusCopy: { flex: 1, minWidth: 0, marginLeft: 13 },
  eyebrow: { color: '#9CB2C2', fontSize: 8.8, fontWeight: '900', letterSpacing: 1.35 },
  statusValue: { fontSize: 18.5, lineHeight: 22, fontWeight: '900', marginTop: 5 },
  statusMeta: { color: '#9AAEBD', fontSize: 10.2, lineHeight: 14, marginTop: 6 },

  grid: { flexDirection: 'row', flexWrap: 'wrap', justifyContent: 'space-between', rowGap: 10 },
  tile: {
    width: '48.4%', minHeight: 121, borderRadius: 18, borderWidth: 1, borderColor: '#24506D',
    backgroundColor: '#0A2233', padding: 11, overflow: 'hidden',
  },
  tileTop: { flexDirection: 'row', alignItems: 'flex-start', justifyContent: 'space-between' },
  chevron: { color: '#28A5F5', fontSize: 23, lineHeight: 27, fontWeight: '900', marginLeft: 6 },
  tileTitle: { color: '#F5FAFE', fontSize: 15.5, lineHeight: 18.5, fontWeight: '900', marginTop: 10 },
  tileSubtitle: { color: '#91A6B6', fontSize: 9.2, lineHeight: 13.1, marginTop: 5 },

  tool: {
    minHeight: 78, borderRadius: 18, borderWidth: 1, borderColor: '#24506D',
    backgroundColor: '#0A2233', overflow: 'hidden', paddingHorizontal: 12, paddingVertical: 10,
    flexDirection: 'row', alignItems: 'center',
  },
  toolShade: { ...StyleSheet.absoluteFillObject, backgroundColor: 'rgba(4, 19, 31, 0.40)' },
  toolCopy: { flex: 1, minWidth: 0, marginLeft: 11 },
  toolTitle: { color: '#F5FAFE', fontSize: 15, lineHeight: 18, fontWeight: '900' },
  toolSubtitle: { color: '#A1B1BE', fontSize: 9.4, lineHeight: 13.3, marginTop: 3 },
  arrowCircle: {
    width: 36, height: 36, borderRadius: 18, borderWidth: 1, borderColor: '#287BAE',
    backgroundColor: 'rgba(3, 18, 30, 0.68)', alignItems: 'center', justifyContent: 'center', marginLeft: 8,
  },
  arrowText: { color: '#28A5F5', fontSize: 23, lineHeight: 26, fontWeight: '900', marginTop: -1 },
  danger: { borderColor: '#A83A45', backgroundColor: '#2A1017' },
  dangerShade: { ...StyleSheet.absoluteFillObject, backgroundColor: 'rgba(35, 5, 11, 0.34)' },
  dangerTitle: { color: '#F26470' },
  dangerArrow: { borderColor: '#A83A45' },
  dangerArrowText: { color: '#F26470' },
});

function MarketStatusCard({
  marketOpen,
  publications,
  freeAgents,
}: {
  marketOpen: boolean;
  publications: number;
  freeAgents: number;
}) {
  return (
    <View style={[marketStyles.status, marketOpen ? marketStyles.statusOpen : marketStyles.statusClosed]}>
      <ImageBackground source={MARKET_STATUS_BG} resizeMode="cover" style={marketStyles.background} imageStyle={{ opacity: 0.66 }} />
      <View style={marketStyles.statusShade} />
      <MarketIconTile name="status" tileSize={58} size={29} tone={marketOpen ? '#0C5B4B' : '#63303A'} iconColor={marketOpen ? '#48E6B0' : '#FF7180'} />
      <View style={marketStyles.statusCopy}>
        <Text style={marketStyles.eyebrow}>ESTADO ACTUAL</Text>
        <Text style={[marketStyles.statusValue, { color: marketOpen ? C.green : C.red }]}>
          {marketOpen ? 'Mercado abierto' : 'Mercado cerrado'}
        </Text>
        <Text style={marketStyles.statusMeta}>{publications} publicaciones · {freeAgents} agentes libres</Text>
      </View>
    </View>
  );
}

function MarketMenuTile({
  icon,
  title,
  subtitle,
  onPress,
}: {
  icon: MarketIconName;
  title: string;
  subtitle: string;
  onPress: () => void;
}) {
  return (
    <Pressable onPress={onPress} style={({ pressed }) => [marketStyles.tile, pressed && { opacity: 0.74, transform: [{ scale: 0.992 }] }]}>
      <View style={marketStyles.tileTop}>
        <MarketIconTile name={icon} tileSize={48} size={24} />
        <Text style={marketStyles.chevron}>›</Text>
      </View>
      <Text style={marketStyles.tileTitle} numberOfLines={2}>{title}</Text>
      <Text style={marketStyles.tileSubtitle} numberOfLines={3}>{subtitle}</Text>
    </Pressable>
  );
}

function MarketToolTile({
  icon,
  title,
  subtitle,
  background,
  onPress,
  danger = false,
}: {
  icon: MarketIconName;
  title: string;
  subtitle: string;
  background: any;
  onPress: () => void;
  danger?: boolean;
}) {
  return (
    <Pressable
      onPress={onPress}
      style={({ pressed }) => [marketStyles.tool, danger && marketStyles.danger, pressed && { opacity: 0.76, transform: [{ scale: 0.993 }] }]}
    >
      <ImageBackground source={background} resizeMode="cover" style={marketStyles.background} imageStyle={{ opacity: danger ? 0.72 : 0.58 }} />
      <View style={danger ? marketStyles.dangerShade : marketStyles.toolShade} />
      <MarketIconTile
        name={icon}
        tileSize={48}
        size={24}
        tone={danger ? '#6B1722' : '#0A3859'}
        iconColor={danger ? '#FF6573' : '#F5FAFE'}
      />
      <View style={marketStyles.toolCopy}>
        <Text style={[marketStyles.toolTitle, danger && marketStyles.dangerTitle]}>{title}</Text>
        <Text style={marketStyles.toolSubtitle} numberOfLines={2}>{subtitle}</Text>
      </View>
      <View style={[marketStyles.arrowCircle, danger && marketStyles.dangerArrow]}>
        <Text style={[marketStyles.arrowText, danger && marketStyles.dangerArrowText]}>›</Text>
      </View>
    </Pressable>
  );
}
`;

const marker = 'function WideTile(';
if (!ui.includes('const marketStyles = StyleSheet.create({')) {
  if (!ui.includes(marker)) throw new Error('Mercado approved UI: no encontré WideTile');
  ui = ui.replace(marker, components + '\n' + marker);
}

const marketMenu = String.raw`  const marketMenu = (
    <ScrollView contentContainerStyle={s.content} refreshControl={refreshControl}>
      <Title eyebrow="MERCADO" title="Mercado" subtitle="Transferencias, publicaciones y ofertas en un mismo panel." />

      <MarketStatusCard
        marketOpen={snapshot.status.market_open}
        publications={normalMarket.length}
        freeAgents={freeAgents.length}
      />

      <SectionLabel title="MERCADO" />
      <View style={marketStyles.grid}>
        <MarketMenuTile icon="transfer" title="Transferibles" subtitle="Jugadores publicados por otros clubes" onPress={() => openScreen('transferibles')} />
        <MarketMenuTile icon="offers" title="Mis ofertas" subtitle="Recibidas, enviadas y decisiones" onPress={() => openScreen('offers')} />
        <MarketMenuTile icon="publish" title="Publicar jugador" subtitle="Transferencia, préstamo o intercambio" onPress={() => requireClub('publish')} />
        <MarketMenuTile icon="freeAgents" title="Agentes libres" subtitle="Jugadores sin club listos para fichar" onPress={() => openScreen('freeAgents')} />
      </View>

      <SectionLabel title="HERRAMIENTAS DEL MERCADO" />
      <MarketToolTile
        icon="search"
        title="Buscar jugador"
        subtitle="Buscá por nombre, club o posición."
        background={MARKET_SEARCH_BG}
        onPress={() => openScreen('search')}
      />
      <MarketToolTile
        icon="history"
        title="Historial"
        subtitle="Revisá movimientos y operaciones anteriores."
        background={MARKET_HISTORY_BG}
        onPress={() => openScreen('history')}
      />
      <MarketToolTile
        icon="clause"
        title="Clausulazo"
        subtitle="Ejecutá una cláusula de rescisión con las reglas AJPA."
        background={MARKET_CLAUSE_BG}
        onPress={() => openScreen('clausulazo')}
        danger
      />
    </ScrollView>
  );`;

replaceBlock('  const marketMenu = (', '  const publishScreen = (', marketMenu, 'menú Mercado');

fs.writeFileSync(uiPath, ui);
console.log('AJPA UI Lab: Mercado aprobado aplicado con fondos locales y Lucide.');
