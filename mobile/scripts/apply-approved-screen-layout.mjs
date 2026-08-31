import fs from 'node:fs';

const uiPath = new URL('../src/BotParityAppV2.tsx', import.meta.url);
let ui = fs.readFileSync(uiPath, 'utf8');

function replaceBlock(startMarker, endMarker, replacement, label) {
  const start = ui.indexOf(startMarker);
  if (start < 0) throw new Error(`AJPA approved layout: no encontré inicio de ${label}`);
  const end = ui.indexOf(endMarker, start + startMarker.length);
  if (end < 0) throw new Error(`AJPA approved layout: no encontré fin de ${label}`);
  ui = ui.slice(0, start) + replacement + '\n\n' + ui.slice(end);
}

const titleMarker = `function Title({ eyebrow, title, subtitle }: { eyebrow: string; title: string; subtitle?: string }) {`;
if (!ui.includes(titleMarker)) throw new Error('AJPA approved layout: no encontré Title');

const approvedComponents = String.raw`
function HeroClubCard({
  club,
  budget,
  players,
  marketOpen,
  onPress,
}: {
  club: string;
  budget: string;
  players: number;
  marketOpen: boolean;
  onPress: () => void;
}) {
  return (
    <Pressable onPress={onPress} style={({ pressed }) => [s.heroClubCard, pressed && { opacity: 0.76 }]}>
      <View style={s.heroIconWrap}><Text style={s.heroIcon}>🛡️</Text></View>
      <View style={s.heroBody}>
        <Text style={s.heroClubName}>{club}</Text>
        <View style={s.heroStatsRow}>
          <View style={s.heroStat}><Text style={s.heroStatLabel}>PRESUPUESTO</Text><Text style={s.heroStatValue}>{budget}</Text></View>
          <View style={s.heroDivider} />
          <View style={s.heroStat}><Text style={s.heroStatLabel}>PLANTILLA</Text><Text style={s.heroStatValue}>{players} jugadores</Text></View>
        </View>
        <View style={s.heroStatusRow}>
          <View style={[s.heroStatusDot, { backgroundColor: marketOpen ? C.green : C.red }]} />
          <Text style={[s.heroStatusText, { color: marketOpen ? C.green : C.red }]}>{marketOpen ? 'Mercado abierto' : 'Mercado cerrado'}</Text>
        </View>
      </View>
      <View style={s.wideArrow}><Text style={s.wideArrowText}>›</Text></View>
    </Pressable>
  );
}

function WideTile({
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
      style={({ pressed }) => [s.wideTile, danger && s.wideTileDanger, pressed && { opacity: 0.74, transform: [{ scale: 0.992 }] }]}
    >
      <View style={[s.wideIconWrap, danger && s.wideIconDanger]}><Text style={s.wideEmoji}>{emoji}</Text></View>
      <View style={s.wideBody}>
        <Text style={[s.wideTitle, danger && { color: C.red }]}>{title}</Text>
        {subtitle ? <Text style={s.wideSubtitle}>{subtitle}</Text> : null}
      </View>
      <View style={[s.wideArrow, danger && { borderColor: '#8b3741' }]}><Text style={[s.wideArrowText, danger && { color: C.red }]}>›</Text></View>
    </Pressable>
  );
}

`;
ui = ui.replace(titleMarker, approvedComponents + titleMarker);

const home = String.raw`  const home = (
    <ScrollView contentContainerStyle={s.content} refreshControl={refreshControl}>
      <Title
        eyebrow="AJPA · INICIO"
        title={profile?.club ? 'Este es tu mercado' : 'AJPA Transfer Market'}
        subtitle={profile?.club ? 'Todo lo importante de tu club y el mercado, sin llenar la pantalla de menús.' : 'Mercado, liga y herramientas principales en un solo lugar.'}
      />

      <HeroClubCard
        club={profile?.club ?? 'Sin club asignado'}
        budget={money(profile?.balance)}
        players={profile?.roster_count ?? roster.length}
        marketOpen={snapshot.status.market_open}
        onPress={() => requireClub('club')}
      />

      <SectionLabel title="⚡ ACCIONES RÁPIDAS" />
      <View style={s.quickGrid}>
        <QuickAction emoji="📤" title="Publicar jugador" onPress={() => requireClub('publish')} />
        <QuickAction emoji="🏷️" title="Mis ofertas" onPress={() => openScreen('offers')} />
        <QuickAction emoji="👥" title="Agentes libres" onPress={() => openScreen('transferibles')} />
        <QuickAction emoji="🔎" title="Buscar jugador" onPress={() => openScreen('search')} />
      </View>

      <View style={s.featureGrid}>
        <FeatureTile emoji="🛒" title="Mercado" subtitle="Transferibles, ofertas, publicaciones y clausulazo" onPress={() => openScreen('market')} />
        <FeatureTile emoji="🏆" title="Liga" subtitle="Tabla, goleadores y actividad competitiva" onPress={() => openScreen('league')} />
      </View>

      <WideTile
        emoji="⚽"
        title="Buscar partido"
        subtitle="Encontrá un rival disponible y organizá la sala."
        onPress={() => onOpenMatchSearch ? onOpenMatchSearch() : Alert.alert('Buscar Partido', 'Abrí Buscar Partido desde el acceso principal de la app.')}
      />
    </ScrollView>
  );`;
replaceBlock(`  const home = (`, `  const clubMenu = (`, home, 'Inicio personalizado');

const clubMenu = String.raw`  const clubMenu = (
    <ScrollView contentContainerStyle={s.content} refreshControl={refreshControl}>
      <Title eyebrow="MI CLUB" title="Mi Club" subtitle="Todo lo de tu club, ordenado en un solo lugar." />

      <HeroClubCard
        club={profile?.club ?? 'Mi Club'}
        budget={money(myClubData?.balance ?? profile?.balance)}
        players={roster.length}
        marketOpen={snapshot.status.market_open}
        onPress={() => openScreen('clubInfo')}
      />

      <WideTile emoji="👕" title="Plantilla" subtitle="Gestioná jugadores, publicaciones y liberaciones." onPress={() => openScreen('roster')} />
      <WideTile emoji="💰" title="Economía" subtitle="Revisá presupuesto, valor de plantilla y cupos." onPress={() => openScreen('economy')} />
      <WideTile emoji="📊" title="Valor del Club" subtitle="Valor total y promedio de tu plantel." onPress={() => openScreen('clubValue')} />
      <WideTile emoji="🛡️" title="Información del club" subtitle="Estado del club, mercado y datos principales." onPress={() => openScreen('clubInfo')} />
      <WideTile emoji="🕘" title="Historial" subtitle="Consultá movimientos y operaciones recientes." onPress={() => openScreen('history')} />

      <SectionLabel title="⚡ ACCIONES RÁPIDAS" />
      <View style={s.quickGrid}>
        <QuickAction emoji="📤" title="Publicar jugador" onPress={() => openScreen('publish')} />
        <QuickAction emoji="🏷️" title="Ver ofertas" onPress={() => openScreen('offers')} />
        <QuickAction emoji="🔎" title="Buscar jugador" onPress={() => openScreen('search')} />
      </View>

      <WideTile emoji="⚠️" title="Renunciar al club" subtitle="Liberá tu asignación. Esta acción requiere confirmación." onPress={() => openScreen('resign')} danger />
    </ScrollView>
  );`;
replaceBlock(`  const clubMenu = (`, `  const rosterScreen = (`, clubMenu, 'Mi Club');

const marketMenu = String.raw`  const marketMenu = (
    <ScrollView contentContainerStyle={s.content} refreshControl={refreshControl}>
      <Title eyebrow="MERCADO" title="Mercado" subtitle="Transferencias, publicaciones y ofertas en un mismo panel." />

      <View style={[s.marketControlCard, snapshot.status.market_open ? s.marketControlOpen : s.marketControlClosed]}>
        <View style={s.heroIconWrap}><Text style={s.heroIcon}>📈</Text></View>
        <View style={s.flex}>
          <Text style={s.marketControlLabel}>ESTADO ACTUAL</Text>
          <Text style={[s.marketControlValue, { color: snapshot.status.market_open ? C.green : C.red }]}>{snapshot.status.market_open ? 'Mercado abierto' : 'Mercado cerrado'}</Text>
          <Text style={s.muted}>{normalMarket.length} publicaciones · {freeAgents.length} agentes libres</Text>
        </View>
      </View>

      <SectionLabel title="🛒 MERCADO" />
      <View style={s.featureGrid}>
        <FeatureTile emoji="🛡️" title="Transferibles" subtitle="Jugadores publicados por otros clubes" onPress={() => openScreen('transferibles')} />
        <FeatureTile emoji="🏷️" title="Mis ofertas" subtitle="Recibidas, enviadas y decisiones" onPress={() => openScreen('offers')} />
        <FeatureTile emoji="📤" title="Publicar jugador" subtitle="Transferencia, préstamo o intercambio" onPress={() => requireClub('publish')} />
        <FeatureTile emoji="👥" title="Agentes libres" subtitle="Jugadores sin club listos para fichar" onPress={() => openScreen('transferibles')} />
      </View>

      <SectionLabel title="⚡ HERRAMIENTAS DEL MERCADO" />
      <WideTile emoji="🔎" title="Buscar jugador" subtitle="Buscá por nombre, club o posición." onPress={() => openScreen('search')} />
      <WideTile emoji="🕘" title="Historial" subtitle="Revisá movimientos y operaciones anteriores." onPress={() => openScreen('history')} />
      <WideTile emoji="💥" title="Clausulazo" subtitle="Ejecutá una cláusula de rescisión con las reglas AJPA." onPress={() => openScreen('clausulazo')} danger />
    </ScrollView>
  );`;
replaceBlock(`  const marketMenu = (`, `  const publishScreen = (`, marketMenu, 'Mercado');

const adminMenu = String.raw`  const adminMenu = (
    <ScrollView contentContainerStyle={s.content} refreshControl={refreshControl}>
      <Title eyebrow="SOLO ADMINISTRADORES" title="Panel Staff" subtitle="Herramientas de control y gestión interna." />
      <View style={s.adminRestrictedCard}>
        <Text style={s.adminRestrictedIcon}>🔒</Text>
        <View style={s.flex}><Text style={s.playerName}>Acceso restringido</Text><Text style={s.muted}>Este panel solo existe para cuentas Staff.</Text></View>
      </View>

      <SectionLabel title="MÓDULOS DE ADMINISTRACIÓN" badge="SOLO ADMIN" />
      <WideTile emoji="🛒" title="Mercado" subtitle="Estado, operaciones, clausulazos y reversión." onPress={() => openScreen('adminMarket')} />
      <WideTile emoji="👥" title="Planteles" subtitle="Altas, bajas, movimientos y consulta." onPress={() => openScreen('adminRosters')} />
      <WideTile emoji="💰" title="Economía" subtitle="Presupuestos, ingresos y egresos auditados." onPress={() => openScreen('adminEconomy')} />
      <WideTile emoji="⚙️" title="Gestión" subtitle="Asignaciones y configuración general." onPress={() => openScreen('adminManagement')} />

      <SectionLabel title="⚡ ACCIONES RÁPIDAS" />
      <View style={s.quickGrid}>
        <QuickAction emoji="🛠️" title="Operaciones pendientes" onPress={() => openScreen('adminOperations')} />
        <QuickAction emoji="💥" title="Clausulazos" onPress={() => openScreen('adminClauses')} />
        <QuickAction emoji="💵" title="Dar dinero" onPress={() => openEconomyAdjustment('ADD')} />
        <QuickAction emoji="➖" title="Quitar dinero" onPress={() => openEconomyAdjustment('REMOVE')} danger />
      </View>
    </ScrollView>
  );`;
replaceBlock(`  const adminMenu = (`, `  const leagueScreen = (`, adminMenu, 'Panel Staff');

const profileScreen = String.raw`  const profileScreen = (
    <ScrollView contentContainerStyle={s.content} refreshControl={refreshControl} keyboardShouldPersistTaps="handled">
      <Title eyebrow="PERFIL" title={profile ? (profile.user.global_name || profile.user.username || 'Perfil') : 'Perfil'} subtitle="Cuenta, club y vinculación con Discord." />
      {profile ? (
        <>
          <View style={s.profileHeroCard}>
            <View style={s.profileAvatar}><Text style={s.profileAvatarText}>AJ</Text></View>
            <View style={s.flex}>
              <Text style={s.heroClubName}>{profile.user.global_name || profile.user.username || profile.user.id}</Text>
              <Text style={s.heroStatusText}>✓ Cuenta vinculada</Text>
              <Text style={s.muted}>{profile.club ?? 'Sin club asignado'}</Text>
            </View>
          </View>

          <WideTile emoji="🛡️" title="Mi Club" subtitle={profile.club ?? 'Sin club asignado'} onPress={() => requireClub('club')} />
          <WideTile emoji="💬" title="Cuenta de Discord" subtitle={profile.user.username || profile.user.id} onPress={() => Alert.alert('Discord', 'Esta cuenta está vinculada con AJPA Transfer Market.')} />

          {profile.is_staff ? (
            <>
              <SectionLabel title="🔒 ADMINISTRACIÓN" badge="SOLO ADMIN" />
              <WideTile emoji="⚙️" title="Panel Staff" subtitle="Mercado, planteles, economía y gestión interna." onPress={() => openScreen('admin')} />
            </>
          ) : null}

          <WideTile emoji="🚪" title="Cerrar sesión" subtitle="Desvincular esta sesión del dispositivo." onPress={logout} danger />
        </>
      ) : (
        <View style={s.editorCard}>
          <Text style={s.playerName}>Vincular Discord</Text>
          <Text style={s.muted}>Ejecutá /app_codigo en Discord y escribí el código privado de 8 caracteres.</Text>
          <TextInput style={[s.input, s.codeInput]} value={pairCode} onChangeText={(value) => setPairCode(value.toUpperCase().replace(/[^A-Z0-9]/g, '').slice(0, 8))} maxLength={8} autoCapitalize="characters" placeholder="XXXXXXXX" placeholderTextColor="#657382" />
          <Button label={busy ? 'VINCULANDO…' : 'VINCULAR DISCORD'} onPress={pair} disabled={busy} />
        </View>
      )}
    </ScrollView>
  );`;
replaceBlock(`  const profileScreen = (`, `  const screenBackground = (() => {`, profileScreen, 'Perfil');

const styleClose = '\n});';
const stylePos = ui.lastIndexOf(styleClose);
if (stylePos < 0) throw new Error('AJPA approved layout: no encontré cierre de estilos');
const extraStyles = String.raw`
  heroClubCard: { minHeight: 154, flexDirection: 'row', alignItems: 'center', borderRadius: 25, borderWidth: 1.25, borderColor: '#2f8fd2', backgroundColor: 'rgba(3,17,29,0.72)', padding: 17, shadowColor: '#168cff', shadowOpacity: 0.27, shadowRadius: 13, shadowOffset: { width: 0, height: 5 }, elevation: 8 },
  heroIconWrap: { width: 66, height: 66, borderRadius: 22, borderWidth: 1.2, borderColor: '#2d82bd', backgroundColor: 'rgba(4,28,47,0.72)', alignItems: 'center', justifyContent: 'center', marginRight: 14 },
  heroIcon: { fontSize: 34 },
  heroBody: { flex: 1, minWidth: 0 },
  heroClubName: { color: C.white, fontSize: 22, fontWeight: '900' },
  heroStatsRow: { flexDirection: 'row', alignItems: 'center', marginTop: 13 },
  heroStat: { flex: 1, minWidth: 0 },
  heroStatLabel: { color: C.muted, fontSize: 8, fontWeight: '900', letterSpacing: 1 },
  heroStatValue: { color: C.white, fontSize: 13.5, fontWeight: '900', marginTop: 4 },
  heroDivider: { width: 1, height: 34, backgroundColor: '#22506f', marginHorizontal: 10 },
  heroStatusRow: { flexDirection: 'row', alignItems: 'center', marginTop: 12 },
  heroStatusDot: { width: 7, height: 7, borderRadius: 4, marginRight: 7 },
  heroStatusText: { color: C.blueSoft, fontSize: 10.5, fontWeight: '800' },
  wideTile: { minHeight: 106, flexDirection: 'row', alignItems: 'center', borderRadius: 22, borderWidth: 1.15, borderColor: '#2c75a8', backgroundColor: 'rgba(3,17,29,0.74)', padding: 15, shadowColor: '#168cff', shadowOpacity: 0.19, shadowRadius: 9, shadowOffset: { width: 0, height: 4 }, elevation: 5 },
  wideTileDanger: { borderColor: '#963943', backgroundColor: 'rgba(29,7,12,0.76)', shadowColor: '#ff4f5d', shadowOpacity: 0.16 },
  wideIconWrap: { width: 56, height: 56, borderRadius: 19, borderWidth: 1, borderColor: '#2d7fb6', backgroundColor: 'rgba(4,28,47,0.70)', alignItems: 'center', justifyContent: 'center', marginRight: 14 },
  wideIconDanger: { borderColor: '#8b3741', backgroundColor: 'rgba(40,10,16,0.72)' },
  wideEmoji: { fontSize: 29 },
  wideBody: { flex: 1, minWidth: 0 },
  wideTitle: { color: C.white, fontSize: 18, fontWeight: '900' },
  wideSubtitle: { color: '#a8b6c3', fontSize: 11.5, lineHeight: 16, marginTop: 5 },
  wideArrow: { width: 34, height: 34, borderRadius: 17, borderWidth: 1, borderColor: '#2b658f', alignItems: 'center', justifyContent: 'center', backgroundColor: 'rgba(4,17,28,0.72)', marginLeft: 10 },
  wideArrowText: { color: C.blue, fontSize: 26, lineHeight: 28, fontWeight: '900', marginTop: -2 },
  adminRestrictedCard: { minHeight: 88, flexDirection: 'row', alignItems: 'center', borderRadius: 20, borderWidth: 1, borderColor: '#2b668f', backgroundColor: 'rgba(4,18,30,0.72)', padding: 15 },
  adminRestrictedIcon: { fontSize: 28, marginRight: 14 },
  profileHeroCard: { minHeight: 130, flexDirection: 'row', alignItems: 'center', borderRadius: 24, borderWidth: 1.2, borderColor: '#2f8fd2', backgroundColor: 'rgba(3,17,29,0.72)', padding: 17, shadowColor: '#168cff', shadowOpacity: 0.22, shadowRadius: 10, shadowOffset: { width: 0, height: 4 }, elevation: 6 },
  profileAvatar: { width: 76, height: 76, borderRadius: 38, borderWidth: 2, borderColor: C.blue, backgroundColor: 'rgba(5,25,41,0.78)', alignItems: 'center', justifyContent: 'center', marginRight: 16 },
  profileAvatarText: { color: C.white, fontSize: 24, fontWeight: '900', letterSpacing: 1 },
`;
ui = ui.slice(0, stylePos) + extraStyles + ui.slice(stylePos);

fs.writeFileSync(uiPath, ui);
console.log('AJPA approved layout: Inicio personalizado + submenús premium + Staff oculto en Inicio');
