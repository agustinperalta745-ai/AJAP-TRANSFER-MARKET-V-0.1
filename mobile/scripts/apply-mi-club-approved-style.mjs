import fs from 'node:fs';

const uiPath = new URL('../src/BotParityAppV2.tsx', import.meta.url);
let ui = fs.readFileSync(uiPath, 'utf8');

function replaceBlock(startMarker, endMarker, replacement, label) {
  const start = ui.indexOf(startMarker);
  if (start < 0) throw new Error('Mi Club approved UI: no encontré inicio de ' + label);
  const end = ui.indexOf(endMarker, start + startMarker.length);
  if (end < 0) throw new Error('Mi Club approved UI: no encontré fin de ' + label);
  ui = ui.slice(0, start) + replacement + '\n\n' + ui.slice(end);
}

const visualsImport = "import { MI_CLUB_CARD_BG_DATA_URI, MiClubIcon, MiClubIconName, MiClubIconTile } from './MiClubVisuals';";
if (!ui.includes(visualsImport)) {
  const anchor = "import { AjpaIcon, AjpaIconName, AjpaIconTile } from './AjpaIcon';";
  if (ui.includes(anchor)) {
    ui = ui.replace(anchor, anchor + '\n' + visualsImport);
  } else {
    const apiAnchor = "import { clearStoredSession, loadStoredSession, saveStoredSession } from './session';";
    if (!ui.includes(apiAnchor)) throw new Error('Mi Club approved UI: no encontré punto de import');
    ui = ui.replace(apiAnchor, apiAnchor + '\n' + visualsImport);
  }
}

if (!ui.includes("import { ClubBadge } from './teamBadges';") && !ui.includes("ClubBadge,") && !ui.includes("{ ClubBadge")) {
  ui = ui.replace(visualsImport, visualsImport + "\nimport { ClubBadge } from './teamBadges';");
}

const components = String.raw\`
const miClubStyles = StyleSheet.create({
  hero: {
    minHeight: 154, flexDirection: 'row', alignItems: 'center', borderRadius: 22,
    borderWidth: 1.2, borderColor: '#2C789F', backgroundColor: '#0A2233',
    padding: 14, overflow: 'hidden',
  },
  heroImage: { ...StyleSheet.absoluteFillObject },
  heroOverlay: { ...StyleSheet.absoluteFillObject, backgroundColor: 'rgba(4, 18, 29, 0.50)' },
  badgeWrap: {
    width: 72, height: 72, borderRadius: 20, borderWidth: 1.2, borderColor: '#2B8BC3',
    backgroundColor: 'rgba(5, 28, 45, 0.80)', alignItems: 'center', justifyContent: 'center', marginRight: 14,
  },
  heroBody: { flex: 1, minWidth: 0 },
  heroName: { color: '#F5FAFE', fontSize: 20, lineHeight: 23, fontWeight: '900' },
  statsRow: { flexDirection: 'row', alignItems: 'center', marginTop: 12 },
  stat: { flex: 1, minWidth: 0 },
  statLabel: { color: '#91A6B6', fontSize: 8, fontWeight: '900', letterSpacing: 1.1 },
  statValue: { color: '#F5FAFE', fontSize: 13.5, fontWeight: '900', marginTop: 4 },
  divider: { width: 1, height: 35, backgroundColor: '#24516D', marginHorizontal: 10 },
  statusRow: { flexDirection: 'row', alignItems: 'center', marginTop: 11 },
  statusDot: { width: 7, height: 7, borderRadius: 4, marginRight: 7 },
  statusText: { fontSize: 10.5, fontWeight: '800' },
  arrowCircle: {
    width: 38, height: 38, borderRadius: 19, borderWidth: 1, borderColor: '#2B739F',
    backgroundColor: 'rgba(5, 22, 35, 0.76)', alignItems: 'center', justifyContent: 'center', marginLeft: 9,
  },
  arrow: { color: '#28A5F5', fontSize: 25, lineHeight: 27, fontWeight: '900', marginTop: -2 },

  grid: { flexDirection: 'row', flexWrap: 'wrap', justifyContent: 'space-between', rowGap: 10 },
  tile: {
    width: '48.4%', minHeight: 108, borderRadius: 18, borderWidth: 1, borderColor: '#244B66',
    backgroundColor: '#0B2233', padding: 11, flexDirection: 'row', alignItems: 'center',
  },
  tileCopy: { flex: 1, minWidth: 0, marginLeft: 10 },
  tileTitle: { color: '#F5FAFE', fontSize: 13.5, lineHeight: 16.5, fontWeight: '900' },
  tileSubtitle: { color: '#91A6B6', fontSize: 8.8, lineHeight: 12.4, marginTop: 4 },
  tileChevron: { color: '#28A5F5', fontSize: 21, fontWeight: '900', marginLeft: 4 },

  wide: {
    minHeight: 79, borderRadius: 18, borderWidth: 1, borderColor: '#244B66', backgroundColor: '#0B2233',
    paddingHorizontal: 12, paddingVertical: 10, flexDirection: 'row', alignItems: 'center',
  },
  wideCopy: { flex: 1, minWidth: 0, marginLeft: 11 },
  wideTitle: { color: '#F5FAFE', fontSize: 14.5, lineHeight: 18, fontWeight: '900' },
  wideSubtitle: { color: '#91A6B6', fontSize: 9.3, lineHeight: 13.2, marginTop: 3 },

  quickRow: { flexDirection: 'row', gap: 8 },
  quick: {
    flex: 1, minHeight: 59, borderRadius: 15, borderWidth: 1, borderColor: '#244B66', backgroundColor: '#0B2233',
    paddingHorizontal: 9, paddingVertical: 8, flexDirection: 'row', alignItems: 'center',
  },
  quickText: { flex: 1, minWidth: 0, color: '#F5FAFE', fontSize: 9.4, lineHeight: 11.5, fontWeight: '900', marginLeft: 7 },
  quickChevron: { color: '#28A5F5', fontSize: 17, fontWeight: '900', marginLeft: 3 },

  danger: {
    minHeight: 78, borderRadius: 18, borderWidth: 1, borderColor: '#A83A45', backgroundColor: '#2A1017',
    paddingHorizontal: 12, paddingVertical: 10, flexDirection: 'row', alignItems: 'center',
  },
  dangerCopy: { flex: 1, minWidth: 0, marginLeft: 11 },
  dangerTitle: { color: '#F26470', fontSize: 15.5, lineHeight: 19, fontWeight: '900' },
  dangerSubtitle: { color: '#C8AEB3', fontSize: 9.2, lineHeight: 13, marginTop: 3 },
  dangerArrow: {
    width: 36, height: 36, borderRadius: 18, borderWidth: 1, borderColor: '#A83A45',
    alignItems: 'center', justifyContent: 'center', marginLeft: 8,
  },
  dangerChevron: { color: '#F26470', fontSize: 23, fontWeight: '900' },
});

function HeroClubCard({
  club, budget, players, marketOpen, onPress,
}: {
  club: string; budget: string; players: number; marketOpen: boolean; onPress: () => void;
}) {
  return (
    <Pressable onPress={onPress} style={({ pressed }) => [miClubStyles.hero, pressed && { opacity: 0.82 }]}>
      <ImageBackground
        pointerEvents="none"
        source={{ uri: MI_CLUB_CARD_BG_DATA_URI }}
        resizeMode="cover"
        style={miClubStyles.heroImage}
        imageStyle={{ opacity: 0.46 }}
      />
      <View pointerEvents="none" style={miClubStyles.heroOverlay} />
      <View style={miClubStyles.badgeWrap}><ClubBadge club={club} size={60} /></View>
      <View style={miClubStyles.heroBody}>
        <Text style={miClubStyles.heroName} numberOfLines={1}>{club}</Text>
        <View style={miClubStyles.statsRow}>
          <View style={miClubStyles.stat}>
            <Text style={miClubStyles.statLabel}>PRESUPUESTO</Text>
            <Text style={miClubStyles.statValue} numberOfLines={1}>{budget}</Text>
          </View>
          <View style={miClubStyles.divider} />
          <View style={miClubStyles.stat}>
            <Text style={miClubStyles.statLabel}>PLANTILLA</Text>
            <Text style={miClubStyles.statValue}>{players} jugadores</Text>
          </View>
        </View>
        <View style={miClubStyles.statusRow}>
          <View style={[miClubStyles.statusDot, { backgroundColor: marketOpen ? C.green : C.red }]} />
          <Text style={[miClubStyles.statusText, { color: marketOpen ? C.green : C.red }]}>
            {marketOpen ? 'Mercado abierto' : 'Mercado cerrado'}
          </Text>
        </View>
      </View>
      <View style={miClubStyles.arrowCircle}><Text style={miClubStyles.arrow}>›</Text></View>
    </Pressable>
  );
}

function MiClubMenuTile({ icon, title, subtitle, onPress }: {
  icon: MiClubIconName; title: string; subtitle: string; onPress: () => void;
}) {
  return (
    <Pressable onPress={onPress} style={({ pressed }) => [miClubStyles.tile, pressed && { opacity: 0.74 }]}>
      <MiClubIconTile name={icon} tileSize={49} size={25} />
      <View style={miClubStyles.tileCopy}>
        <Text style={miClubStyles.tileTitle} numberOfLines={2}>{title}</Text>
        <Text style={miClubStyles.tileSubtitle} numberOfLines={3}>{subtitle}</Text>
      </View>
      <Text style={miClubStyles.tileChevron}>›</Text>
    </Pressable>
  );
}

function MiClubWideTile({ icon, title, subtitle, onPress }: {
  icon: MiClubIconName; title: string; subtitle: string; onPress: () => void;
}) {
  return (
    <Pressable onPress={onPress} style={({ pressed }) => [miClubStyles.wide, pressed && { opacity: 0.74 }]}>
      <MiClubIconTile name={icon} tileSize={48} size={24} />
      <View style={miClubStyles.wideCopy}>
        <Text style={miClubStyles.wideTitle}>{title}</Text>
        <Text style={miClubStyles.wideSubtitle} numberOfLines={2}>{subtitle}</Text>
      </View>
      <Text style={miClubStyles.tileChevron}>›</Text>
    </Pressable>
  );
}

function MiClubQuickAction({ icon, title, onPress }: {
  icon: MiClubIconName; title: string; onPress: () => void;
}) {
  return (
    <Pressable onPress={onPress} style={({ pressed }) => [miClubStyles.quick, pressed && { opacity: 0.74 }]}>
      <MiClubIcon name={icon} size={21} color="#39AFFF" />
      <Text style={miClubStyles.quickText} numberOfLines={2}>{title}</Text>
      <Text style={miClubStyles.quickChevron}>›</Text>
    </Pressable>
  );
}

function MiClubDangerTile({ onPress }: { onPress: () => void }) {
  return (
    <Pressable onPress={onPress} style={({ pressed }) => [miClubStyles.danger, pressed && { opacity: 0.74 }]}>
      <MiClubIconTile name="resign" tileSize={48} size={25} />
      <View style={miClubStyles.dangerCopy}>
        <Text style={miClubStyles.dangerTitle}>Renunciar al club</Text>
        <Text style={miClubStyles.dangerSubtitle}>Liberá tu asignación. Esta acción requiere confirmación.</Text>
      </View>
      <View style={miClubStyles.dangerArrow}><Text style={miClubStyles.dangerChevron}>›</Text></View>
    </Pressable>
  );
}
\`;

replaceBlock('function HeroClubCard(', 'function WideTile(', components, 'componentes Mi Club');

const clubMenu = String.raw\`  const clubMenu = (
    <ScrollView contentContainerStyle={s.content} refreshControl={refreshControl}>
      <Title eyebrow="MI CLUB" title="Mi Club" subtitle="Todo lo de tu club, ordenado en un solo lugar." />

      <HeroClubCard
        club={profile?.club ?? 'Mi Club'}
        budget={money(myClubData?.balance ?? profile?.balance)}
        players={roster.length}
        marketOpen={snapshot.status.market_open}
        onPress={() => openScreen('clubInfo')}
      />

      <View style={miClubStyles.grid}>
        <MiClubMenuTile icon="roster" title="Plantilla" subtitle="Gestioná jugadores, publicaciones y liberaciones." onPress={() => openScreen('roster')} />
        <MiClubMenuTile icon="economy" title="Economía" subtitle="Revisá presupuesto, valor de plantilla y cupos." onPress={() => openScreen('economy')} />
        <MiClubMenuTile icon="treasury" title="Tesorería" subtitle="Ingresos, egresos y premios acreditados al club." onPress={() => void openTreasury()} />
        <MiClubMenuTile
          icon="classic"
          title="Clásico"
          subtitle={classicState?.classic
            ? 'Clásico: ' + classicState.classic.opponent + ' · ' + classicState.classic.opponent_manager.name
            : 'Elegí, aceptá o consultá tu clásico rival.'}
          onPress={() => void openClassic()}
        />
        <MiClubMenuTile icon="clubValue" title="Valor del Club" subtitle="Valor total y promedio de tu plantel." onPress={() => openScreen('clubValue')} />
        <MiClubMenuTile icon="clubInfo" title="Información del club" subtitle="Estado del club, mercado y datos principales." onPress={() => openScreen('clubInfo')} />
      </View>

      <MiClubWideTile icon="history" title="Historial" subtitle="Consultá movimientos y operaciones recientes." onPress={() => openScreen('history')} />

      <SectionLabel title="ACCIONES RÁPIDAS" />
      <View style={miClubStyles.quickRow}>
        <MiClubQuickAction icon="publish" title="Publicar jugador" onPress={() => openScreen('publish')} />
        <MiClubQuickAction icon="offers" title="Ver ofertas" onPress={() => openScreen('offers')} />
        <MiClubQuickAction icon="search" title="Buscar jugador" onPress={() => openScreen('search')} />
      </View>

      <MiClubDangerTile onPress={() => openScreen('resign')} />
    </ScrollView>
  );\`;

replaceBlock('  const clubMenu = (', '  const rosterScreen = (', clubMenu, 'menú Mi Club');

fs.writeFileSync(uiPath, ui);
console.log('AJPA UI Lab: Mi Club aprobado aplicado con fondo, iconografía y organización final.');
