import fs from 'node:fs';

const uiPath = new URL('../src/BotParityAppV2.tsx', import.meta.url);
const matchPath = new URL('../src/MatchSearchShell.tsx', import.meta.url);
let ui = fs.readFileSync(uiPath, 'utf8');
let match = fs.readFileSync(matchPath, 'utf8');

function mustReplace(source, search, replacement, label) {
  if (!source.includes(search)) throw new Error(`AJPA organized UI: no encontré ${label}`);
  return source.replace(search, replacement);
}

function replaceBlock(source, startMarker, endMarker, replacement, label) {
  const start = source.indexOf(startMarker);
  if (start < 0) throw new Error(`AJPA organized UI: no encontré inicio de ${label}`);
  const end = source.indexOf(endMarker, start + startMarker.length);
  if (end < 0) throw new Error(`AJPA organized UI: no encontré fin de ${label}`);
  return source.slice(0, start) + replacement + '\n\n' + source.slice(end);
}

// Match Search now opens from the fourth main dashboard panel, so the home
// screen can keep the clean 2x2 hierarchy instead of a floating action overlay.
ui = mustReplace(
  ui,
  `export default function BotParityAppV2() {`,
  `export default function BotParityAppV2({ onOpenMatchSearch }: { onOpenMatchSearch?: () => void } = {}) {`,
  'firma BotParityAppV2',
);

const titleMarker = `function Title({ eyebrow, title, subtitle }: { eyebrow: string; title: string; subtitle?: string }) {`;
if (!ui.includes(titleMarker)) throw new Error('AJPA organized UI: no encontré Title');
const organizedComponents = String.raw`
function SectionLabel({ title, badge }: { title: string; badge?: string }) {
  return (
    <View style={s.sectionLabelRow}>
      <Text style={s.sectionLabel}>{title}</Text>
      {badge ? <Text style={s.sectionBadge}>{badge}</Text> : null}
    </View>
  );
}

function FeatureTile({
  emoji,
  title,
  subtitle,
  onPress,
  danger = false,
}: {
  emoji: string;
  title: string;
  subtitle?: string;
  onPress: () => void;
  danger?: boolean;
}) {
  return (
    <Pressable
      onPress={onPress}
      style={({ pressed }) => [
        s.featureTile,
        danger && s.featureTileDanger,
        pressed && { opacity: 0.72, transform: [{ scale: 0.985 }] },
      ]}
    >
      <View style={[s.featureIconWrap, danger && s.featureIconDanger]}>
        <Text style={s.featureEmoji}>{emoji}</Text>
      </View>
      <View style={s.featureTextWrap}>
        <Text style={[s.featureTitle, danger && { color: C.red }]}>{title}</Text>
        {subtitle ? <Text style={s.featureSubtitle}>{subtitle}</Text> : null}
      </View>
      <View style={[s.featureArrow, danger && { borderColor: '#74323a' }]}>
        <Text style={[s.featureArrowText, danger && { color: C.red }]}>›</Text>
      </View>
    </Pressable>
  );
}

function QuickAction({
  emoji,
  title,
  onPress,
  danger = false,
}: {
  emoji: string;
  title: string;
  onPress: () => void;
  danger?: boolean;
}) {
  return (
    <Pressable
      onPress={onPress}
      style={({ pressed }) => [s.quickAction, danger && s.quickActionDanger, pressed && { opacity: 0.72 }]}
    >
      <Text style={s.quickEmoji}>{emoji}</Text>
      <Text style={[s.quickTitle, danger && { color: C.red }]} numberOfLines={2}>{title}</Text>
      <Text style={[s.quickChevron, danger && { color: C.red }]}>›</Text>
    </Pressable>
  );
}

`;
ui = ui.replace(titleMarker, organizedComponents + titleMarker);

const home = String.raw`  const home = (
    <ScrollView contentContainerStyle={s.content} refreshControl={refreshControl}>
      <Title
        eyebrow="AJPA · MENÚ"
        title="Accesos principales"
        subtitle={profile?.club ? profile.club + ' · Todo lo importante en un solo vistazo' : 'Todo lo importante en un solo vistazo'}
      />

      <View style={s.featureGrid}>
        <FeatureTile
          emoji="🛡️"
          title="Mi Club"
          subtitle={profile?.club ? 'Plantilla, economía, valor e información' : 'Necesitás un club asignado'}
          onPress={() => requireClub('club')}
        />
        <FeatureTile
          emoji="🛒"
          title="Mercado"
          subtitle="Transferibles, publicaciones, ofertas y clausulazo"
          onPress={() => openScreen('market')}
        />
        <FeatureTile
          emoji="🏆"
          title="Liga"
          subtitle="Tabla, goleadores y estado de la competencia"
          onPress={() => openScreen('league')}
        />
        <FeatureTile
          emoji="⚽"
          title="Buscar partido"
          subtitle="Encontrá un rival disponible y organizá la sala"
          onPress={() => onOpenMatchSearch ? onOpenMatchSearch() : Alert.alert('Buscar Partido', 'Abrí Buscar Partido desde el acceso principal de la app.')}
        />
      </View>

      <SectionLabel title="⚡ ACCIONES RÁPIDAS" />
      <View style={s.quickGrid}>
        <QuickAction emoji="📤" title="Publicar jugador" onPress={() => requireClub('publish')} />
        <QuickAction emoji="📩" title="Ver ofertas" onPress={() => openScreen('offers')} />
        <QuickAction emoji="🆓" title="Agentes libres" onPress={() => openScreen('transferibles')} />
      </View>

      <View style={s.homeStatusRow}>
        <View style={s.homeStatusCard}>
          <Text style={s.homeStatusLabel}>MERCADO</Text>
          <Text style={[s.homeStatusValue, { color: snapshot.status.market_open ? C.green : C.red }]}>
            {snapshot.status.market_open ? 'ABIERTO' : 'CERRADO'}
          </Text>
        </View>
        <View style={s.homeStatusCard}>
          <Text style={s.homeStatusLabel}>PRESUPUESTO</Text>
          <Text style={s.homeStatusValue}>{money(profile?.balance)}</Text>
        </View>
      </View>

      {profile?.is_staff ? (
        <>
          <SectionLabel title="🔒 STAFF" badge="SOLO ADMIN" />
          <View style={s.quickGrid}>
            <QuickAction emoji="⚙️" title="Administración" onPress={() => openScreen('admin')} />
            <QuickAction emoji="🛠️" title="Operaciones pendientes" onPress={() => openScreen('adminOperations')} />
            <QuickAction emoji="💥" title="Clausulazos pendientes" onPress={() => openScreen('adminClauses')} />
          </View>
        </>
      ) : null}
    </ScrollView>
  );`;
ui = replaceBlock(ui, `  const home = (`, `  const clubMenu = (`, home, 'Inicio');

const clubMenu = String.raw`  const clubMenu = (
    <ScrollView contentContainerStyle={s.content} refreshControl={refreshControl}>
      <Title eyebrow="MI CLUB" title={profile?.club ?? 'Mi Club'} subtitle="Tu equipo, ordenado por áreas." />

      <SectionLabel title="GESTIÓN DEL CLUB" />
      <View style={s.featureGrid}>
        <FeatureTile emoji="👥" title="Plantilla" subtitle={roster.length + ' jugadores · publicar y liberar'} onPress={() => openScreen('roster')} />
        <FeatureTile emoji="💰" title="Economía" subtitle="Presupuesto, valor de plantilla y cupos" onPress={() => openScreen('economy')} />
        <FeatureTile emoji="📊" title="Valor del Club" subtitle="Valor total y promedio por jugador" onPress={() => openScreen('clubValue')} />
        <FeatureTile emoji="ℹ️" title="Información" subtitle="Estado del club, mercado y presupuesto" onPress={() => openScreen('clubInfo')} />
      </View>

      <SectionLabel title="ACCIONES" />
      <View style={s.quickGrid}>
        <QuickAction emoji="📤" title="Publicar jugador" onPress={() => openScreen('publish')} />
        <QuickAction emoji="📩" title="Mis ofertas" onPress={() => openScreen('offers')} />
        <QuickAction emoji="🔎" title="Buscar jugador" onPress={() => openScreen('search')} />
      </View>

      <SectionLabel title="ZONA DEL DT" />
      <MenuTile emoji="🚪" title="RENUNCIAR AL CLUB" subtitle="Liberar tu asignación sin borrar plantel ni economía" onPress={() => openScreen('resign')} danger />
    </ScrollView>
  );`;
ui = replaceBlock(ui, `  const clubMenu = (`, `  const rosterScreen = (`, clubMenu, 'Mi Club');

const marketMenu = String.raw`  const marketMenu = (
    <ScrollView contentContainerStyle={s.content} refreshControl={refreshControl}>
      <Title eyebrow="MERCADO" title="Mercado de Pases" subtitle="Operaciones principales arriba; consulta y seguimiento debajo." />

      <SectionLabel title="OPERACIONES" />
      <View style={s.featureGrid}>
        <FeatureTile emoji="📋" title="Transferibles" subtitle="Otros equipos, tus publicaciones y agentes libres" onPress={() => openScreen('transferibles')} />
        <FeatureTile emoji="📤" title="Publicar" subtitle="Transferencia, préstamo o intercambio" onPress={() => requireClub('publish')} />
        <FeatureTile emoji="📩" title="Ofertas" subtitle="Recibidas, enviadas y decisiones" onPress={() => openScreen('offers')} />
        <FeatureTile emoji="💥" title="Clausulazo" subtitle="Ejecutar cláusula de rescisión" onPress={() => openScreen('clausulazo')} danger />
      </View>

      <SectionLabel title="CONSULTA Y SEGUIMIENTO" />
      <View style={s.quickGrid}>
        <QuickAction emoji="🔎" title="Buscar jugador" onPress={() => openScreen('search')} />
        <QuickAction emoji="📜" title="Historial" onPress={() => openScreen('history')} />
        <QuickAction emoji="🆓" title="Agentes libres" onPress={() => openScreen('transferibles')} />
      </View>
    </ScrollView>
  );`;
ui = replaceBlock(ui, `  const marketMenu = (`, `  const publishScreen = (`, marketMenu, 'Mercado');

const adminMenu = String.raw`  const adminMenu = (
    <ScrollView contentContainerStyle={s.content} refreshControl={refreshControl}>
      <Title eyebrow="STAFF" title="Administración" subtitle="Herramientas exclusivas del Staff, separadas por función." />
      <SectionLabel title="ACCESOS STAFF" badge="SOLO ADMIN" />
      <View style={s.featureGrid}>
        <FeatureTile emoji="⚙️" title="Panel administrativo" subtitle="Mercado, planteles, economía y gestión" onPress={() => openScreen('adminTools')} />
        <FeatureTile emoji="👥" title="Asignaciones" subtitle="Clubes vinculados a usuarios" onPress={() => openScreen('assignments')} />
      </View>
      <SectionLabel title="PENDIENTES" />
      <View style={s.quickGrid}>
        <QuickAction emoji="🛠️" title="Operaciones" onPress={() => openScreen('adminOperations')} />
        <QuickAction emoji="💥" title="Clausulazos" onPress={() => openScreen('adminClauses')} />
        <QuickAction emoji="↩️" title="Deshacer pase" onPress={() => openScreen('adminUndo')} danger />
      </View>
    </ScrollView>
  );`;
ui = replaceBlock(ui, `  const adminMenu = (`, `  const leagueScreen = (`, adminMenu, 'Administración principal');

const adminTools = String.raw`  const adminToolsScreen = (
    <ScrollView contentContainerStyle={s.content} refreshControl={refreshControl}>
      <Title eyebrow="STAFF · ADMINISTRACIÓN" title="Panel administrativo" subtitle="Cuatro áreas principales, con las acciones ordenadas dentro de cada una." />
      <View style={s.featureGrid}>
        <FeatureTile emoji="🔁" title="Mercado" subtitle="Estado, pendientes, clausulazos y reversión" onPress={() => openScreen('adminMarket')} />
        <FeatureTile emoji="👥" title="Planteles" subtitle="Altas, bajas, movimientos y consulta" onPress={() => openScreen('adminRosters')} />
        <FeatureTile emoji="💰" title="Economía" subtitle="Presupuestos, ingresos y egresos" onPress={() => openScreen('adminEconomy')} />
        <FeatureTile emoji="⚙️" title="Gestión" subtitle="Asignaciones, temporada y exportación" onPress={() => openScreen('adminManagement')} />
      </View>
    </ScrollView>
  );`;
ui = replaceBlock(ui, `  const adminToolsScreen = (`, `  const adminMarketScreen = (`, adminTools, 'Panel Staff');

const adminMarket = String.raw`  const adminMarketScreen = (
    <ScrollView contentContainerStyle={s.content} refreshControl={refreshControl}>
      <Title eyebrow="STAFF · ADMINISTRACIÓN" title="Mercado" subtitle="Control del mercado y revisión de operaciones." />

      <View style={[s.marketControlCard, snapshot.status.market_open ? s.marketControlOpen : s.marketControlClosed]}>
        <View style={s.flex}>
          <Text style={s.marketControlLabel}>ESTADO ACTUAL</Text>
          <Text style={s.marketControlValue}>{snapshot.status.market_open ? '🟢 MERCADO ABIERTO' : '🔒 MERCADO CERRADO'}</Text>
        </View>
        <Button
          label={snapshot.status.market_open ? 'CERRAR' : 'ABRIR'}
          kind={snapshot.status.market_open ? 'red' : 'green'}
          onPress={() => mutate(
            () => setAdminMarketOpen(!snapshot.status.market_open),
            snapshot.status.market_open ? 'Mercado cerrado por Staff.' : 'Mercado abierto por Staff.',
          )}
        />
      </View>

      <SectionLabel title="REVISIÓN STAFF" />
      <View style={s.featureGrid}>
        <FeatureTile emoji="🛠️" title="Operaciones pendientes" subtitle="Aprobar, rechazar y marcar carga en PES" onPress={() => openScreen('adminOperations')} />
        <FeatureTile emoji="💥" title="Clausulazos" subtitle="Solicitudes pendientes de aprobación" onPress={() => openScreen('adminClauses')} danger />
        <FeatureTile emoji="↩️" title="Deshacer pase" subtitle="Revertir una operación aplicada" onPress={() => openScreen('adminUndo')} danger />
      </View>
    </ScrollView>
  );`;
ui = replaceBlock(ui, `  const adminMarketScreen = (`, `  const adminOperationsScreen = (`, adminMarket, 'Staff Mercado');

const adminRosters = String.raw`  const adminRostersScreen = (
    <ScrollView contentContainerStyle={s.content} refreshControl={refreshControl}>
      <Title eyebrow="STAFF · ADMINISTRACIÓN" title="Planteles" subtitle="Herramientas ordenadas por tipo de modificación." />
      <SectionLabel title="MODIFICAR PLANTEL" />
      <View style={s.featureGrid}>
        <FeatureTile emoji="➕" title="Agregar jugador" subtitle="Alta manual con posición, estadísticas y OVR" onPress={() => Alert.alert('Agregar jugador', 'La alta conserva posición, estadísticas y OVR automático del bot. El formulario móvil se habilita cuando esté conectado su endpoint Staff.')} />
        <FeatureTile emoji="🔁" title="Mover jugador" subtitle="Transferir un jugador entre planteles" onPress={() => Alert.alert('Mover jugador', 'La herramienta ya está reflejada; la mutación queda bloqueada hasta usar el endpoint Staff seguro.')} />
        <FeatureTile emoji="🗑️" title="Quitar jugador" subtitle="Eliminar un jugador con confirmación" onPress={() => Alert.alert('Quitar jugador', 'La eliminación necesita la misma confirmación destructiva del bot antes de habilitarse desde la app.')} danger />
        <FeatureTile emoji="📋" title="Ver plantel" subtitle="Consultar jugadores y clubes" onPress={() => openScreen('search')} />
      </View>
    </ScrollView>
  );`;
ui = replaceBlock(ui, `  const adminRostersScreen = (`, `  const adminEconomyScreen = (`, adminRosters, 'Staff Planteles');

const adminEconomy = String.raw`  const adminEconomyScreen = (
    <ScrollView contentContainerStyle={s.content} refreshControl={refreshControl}>
      <Title eyebrow="STAFF · ADMINISTRACIÓN" title="Economía" subtitle="Ajustes auditados y consulta de presupuestos." />
      <SectionLabel title="AJUSTES" />
      <View style={s.featureGrid}>
        <FeatureTile emoji="➕" title="Dar dinero" subtitle="Acreditar presupuesto con auditoría" onPress={() => openEconomyAdjustment('ADD')} />
        <FeatureTile emoji="➖" title="Quitar dinero" subtitle="Descontar presupuesto con auditoría" onPress={() => openEconomyAdjustment('REMOVE')} danger />
      </View>
      <SectionLabel title="📊 PRESUPUESTOS DE CLUBES" />
      {snapshot.clubs.map((club) => (
        <View style={s.budgetCard} key={club.name}>
          <View style={s.flex}>
            <Text style={s.playerName}>{club.name}</Text>
            <Text style={s.muted}>{club.roster_count} jugadores</Text>
          </View>
          <Text style={s.budgetValue}>{money(club.balance)}</Text>
        </View>
      ))}
    </ScrollView>
  );`;
ui = replaceBlock(ui, `  const adminEconomyScreen = (`, `  const adminEconomyAdjustScreen = (`, adminEconomy, 'Staff Economía');

const adminManagement = String.raw`  const adminManagementScreen = (
    <ScrollView contentContainerStyle={s.content} refreshControl={refreshControl}>
      <Title eyebrow="STAFF · ADMINISTRACIÓN" title="Gestión" subtitle="Configuración general y herramientas de administración." />
      <SectionLabel title="CONFIGURACIÓN" />
      <View style={s.featureGrid}>
        <FeatureTile emoji="👥" title="Asignaciones" subtitle="Clubes vinculados a usuarios" onPress={() => openScreen('assignments')} />
        <FeatureTile emoji="🗓️" title="Cambiar temporada" subtitle="Seleccionar la temporada activa" onPress={() => Alert.alert('Cambiar temporada', 'La selección de temporada mantiene la validación Staff de Discord y todavía no expone una mutación móvil.')} />
        <FeatureTile emoji="📤" title="Exportar mercado" subtitle="Preparar historial para descarga" onPress={() => Alert.alert('Exportar mercado', 'El historial ya se consulta desde la app. La descarga CSV se mantiene en Discord hasta habilitar archivos desde el endpoint móvil.')} />
      </View>
    </ScrollView>
  );`;
ui = replaceBlock(ui, `  const adminManagementScreen = (`, `  const assignmentsScreen = (`, adminManagement, 'Staff Gestión');

// Strengthen the visual language globally so lists, forms and nested data
// sections inherit the same glass-panel hierarchy without touching backgrounds.
const styleEnd = `  separator: { height: 1, backgroundColor: '#1b2e3d', marginVertical: 13 },\n});`;
const organizedStyles = String.raw`  separator: { height: 1, backgroundColor: '#1b2e3d', marginVertical: 13 },
  sectionLabelRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginTop: 10, marginBottom: 1 },
  sectionLabel: { color: C.blue, fontSize: 10, fontWeight: '900', letterSpacing: 1.6 },
  sectionBadge: { color: C.blueSoft, fontSize: 8, fontWeight: '900', letterSpacing: 1, borderWidth: 1, borderColor: '#28567a', borderRadius: 999, paddingHorizontal: 9, paddingVertical: 5, backgroundColor: 'rgba(5,21,34,0.88)' },
  featureGrid: { flexDirection: 'row', flexWrap: 'wrap', justifyContent: 'space-between', gap: 10 },
  featureTile: { width: '48.4%', minHeight: 184, borderRadius: 22, borderWidth: 1.2, borderColor: '#2b7fc0', backgroundColor: 'rgba(5,18,30,0.84)', padding: 15, overflow: 'hidden' },
  featureTileDanger: { borderColor: '#6d3038', backgroundColor: 'rgba(28,9,14,0.84)' },
  featureIconWrap: { width: 54, height: 54, borderRadius: 18, borderWidth: 1, borderColor: '#2a6792', backgroundColor: 'rgba(8,31,49,0.88)', alignItems: 'center', justifyContent: 'center', marginBottom: 16 },
  featureIconDanger: { borderColor: '#74323a', backgroundColor: 'rgba(42,12,18,0.88)' },
  featureEmoji: { fontSize: 28 },
  featureTextWrap: { flex: 1 },
  featureTitle: { color: C.white, fontSize: 19, lineHeight: 22, fontWeight: '900' },
  featureSubtitle: { color: '#a8b6c3', fontSize: 11.5, lineHeight: 16, marginTop: 7 },
  featureArrow: { width: 32, height: 32, borderRadius: 16, borderWidth: 1, borderColor: '#285d83', alignItems: 'center', justifyContent: 'center', alignSelf: 'flex-end', backgroundColor: 'rgba(4,17,28,0.8)' },
  featureArrowText: { color: C.blue, fontSize: 25, lineHeight: 27, fontWeight: '900', marginTop: -2 },
  quickGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: 9 },
  quickAction: { flexGrow: 1, flexBasis: '30%', minWidth: 96, minHeight: 64, flexDirection: 'row', alignItems: 'center', borderRadius: 16, borderWidth: 1, borderColor: '#27516f', backgroundColor: 'rgba(6,21,34,0.86)', paddingHorizontal: 11, paddingVertical: 10 },
  quickActionDanger: { borderColor: '#653039', backgroundColor: 'rgba(25,10,14,0.86)' },
  quickEmoji: { fontSize: 20, marginRight: 8 },
  quickTitle: { flex: 1, color: C.white, fontSize: 10.5, lineHeight: 14, fontWeight: '800' },
  quickChevron: { color: C.blue, fontSize: 21, fontWeight: '900', marginLeft: 3 },
  homeStatusRow: { flexDirection: 'row', gap: 10 },
  homeStatusCard: { flex: 1, minHeight: 72, borderRadius: 17, borderWidth: 1, borderColor: '#27475f', backgroundColor: 'rgba(7,20,31,0.82)', padding: 13, justifyContent: 'center' },
  homeStatusLabel: { color: C.muted, fontSize: 8, fontWeight: '900', letterSpacing: 1.2 },
  homeStatusValue: { color: C.white, fontSize: 15, fontWeight: '900', marginTop: 5 },
  marketControlCard: { flexDirection: 'row', alignItems: 'center', gap: 12, borderRadius: 19, borderWidth: 1, padding: 15, backgroundColor: 'rgba(7,20,31,0.86)' },
  marketControlOpen: { borderColor: '#286044' },
  marketControlClosed: { borderColor: '#67333b' },
  marketControlLabel: { color: C.muted, fontSize: 8, fontWeight: '900', letterSpacing: 1.2 },
  marketControlValue: { color: C.white, fontSize: 15, fontWeight: '900', marginTop: 4 },
  budgetCard: { minHeight: 74, flexDirection: 'row', alignItems: 'center', gap: 12, borderRadius: 17, borderWidth: 1, borderColor: '#27475f', backgroundColor: 'rgba(7,20,31,0.84)', padding: 14 },
  budgetValue: { color: C.blueSoft, fontSize: 14, fontWeight: '900' },
});`;
ui = mustReplace(ui, styleEnd, organizedStyles, 'cierre de estilos');

// Refine the existing common components too: every nested screen (players,
// offers, history, league, forms) keeps the same background but inherits the
// cleaner glass-card language.
ui = ui.replace(
  `  content: { padding: 16, paddingBottom: 34, gap: 11 },`,
  `  content: { padding: 16, paddingBottom: 38, gap: 12 },`,
);
ui = ui.replace(
  `  menuTile: { minHeight: 76, flexDirection: 'row', alignItems: 'center', backgroundColor: C.panel, borderWidth: 1, borderColor: C.border, borderRadius: 18, padding: 14 },`,
  `  menuTile: { minHeight: 82, flexDirection: 'row', alignItems: 'center', backgroundColor: 'rgba(6,20,32,0.86)', borderWidth: 1, borderColor: '#28516e', borderRadius: 20, padding: 15 },`,
);
ui = ui.replace(
  `  card: { backgroundColor: C.panel, borderWidth: 1, borderColor: C.border, borderRadius: 18, padding: 14 },`,
  `  card: { backgroundColor: 'rgba(6,20,32,0.84)', borderWidth: 1, borderColor: '#27475f', borderRadius: 19, padding: 15 },`,
);
ui = ui.replace(
  `  statCard: { backgroundColor: C.panel, borderWidth: 1, borderColor: C.border, borderRadius: 18, padding: 16 },`,
  `  statCard: { backgroundColor: 'rgba(6,20,32,0.84)', borderWidth: 1, borderColor: '#28516e', borderRadius: 20, padding: 17 },`,
);
ui = ui.replace(
  `  editorCard: { backgroundColor: 'rgba(9,25,40,0.86)', borderWidth: 1, borderColor: C.blue, borderRadius: 19, padding: 15 },`,
  `  editorCard: { backgroundColor: 'rgba(7,23,37,0.90)', borderWidth: 1, borderColor: '#2d7fb7', borderRadius: 21, padding: 16 },`,
);
ui = ui.replace(
  `  listHeading: { color: C.blueSoft, fontWeight: '900', fontSize: 10, letterSpacing: 1.4, marginTop: 8 },`,
  `  listHeading: { color: C.blue, fontWeight: '900', fontSize: 10, letterSpacing: 1.5, marginTop: 12, marginBottom: 1 },`,
);

match = mustReplace(
  match,
  `      <BotParityAppV2 />`,
  `      <BotParityAppV2 onOpenMatchSearch={() => setOpen(true)} />`,
  'conexión de Buscar Partido',
);

const floatingEntry = String.raw`
      {!open ? (
        <Pressable style={({ pressed }) => [s.entry, pressed && { opacity: 0.76 }]} onPress={() => setOpen(true)}>
          <Text style={s.entryEmoji}>⚽</Text>
          <View style={{ flex: 1 }}>
            <Text style={s.entryTitle}>BUSCAR PARTIDO</Text>
            <Text style={s.entrySub}>Encontrá un rival disponible</Text>
          </View>
          <Text style={s.chevron}>›</Text>
        </Pressable>
      ) : null}
`;
if (!match.includes(floatingEntry)) throw new Error('AJPA organized UI: no encontré acceso flotante Buscar Partido');
match = match.replace(floatingEntry, '\n');

fs.writeFileSync(uiPath, ui);
fs.writeFileSync(matchPath, match);
console.log('AJPA Mobile: orden completo + estilo de paneles aplicado; fondos preservados');
