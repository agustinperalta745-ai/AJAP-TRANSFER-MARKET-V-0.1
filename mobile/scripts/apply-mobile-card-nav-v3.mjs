import fs from 'node:fs';

const uiPath = new URL('../src/BotParityAppV2.tsx', import.meta.url);
let ui = fs.readFileSync(uiPath, 'utf8');

function replaceStyle(name, body) {
  const re = new RegExp(`  ${name}: \\{[^\\n]*\\},`);
  if (!re.test(ui)) return false;
  ui = ui.replace(re, `  ${name}: { ${body} },`);
  return true;
}

function replaceFunction(startMarker, endMarker, replacement, label) {
  const start = ui.indexOf(startMarker);
  const end = ui.indexOf(endMarker, start + startMarker.length);
  if (start < 0 || end < 0) throw new Error(`AJPA broadcast UI: no pude aislar ${label}.`);
  ui = ui.slice(0, start) + replacement + '\n\n' + ui.slice(end);
}

const iconHelper = String.raw`function broadcastIcon(label: string, fallback = '•') {
  const value = label.toLowerCase();
  if (value.includes('buscar jugador')) return '⌕';
  if (value.includes('buscar partido')) return '●';
  if (value.includes('resultado')) return '▦';
  if (value.includes('mercado') || value.includes('transfer')) return '↔';
  if (value.includes('oferta')) return '⇄';
  if (value.includes('publicar')) return '↑';
  if (value.includes('agente') || value.includes('libre')) return '○';
  if (value.includes('liga')) return '★';
  if (value.includes('copa') || value.includes('vitrina') || value.includes('campe')) return '✦';
  if (value.includes('club') || value.includes('plantilla') || value.includes('equipo')) return '◆';
  if (value.includes('econom') || value.includes('presupuesto')) return '$';
  if (value.includes('valor') || value.includes('estad')) return '▥';
  if (value.includes('historial')) return '≡';
  if (value.includes('admin') || value.includes('gestión')) return '⚙';
  if (value.includes('perfil') || value.includes('cuenta')) return '◎';
  return fallback;
}`;

const featureTile = String.raw`function FeatureTile({
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
        pressed && { opacity: 0.76, transform: [{ scale: 0.988 }] },
      ]}
    >
      <View style={[s.featureAccent, danger && s.featureAccentDanger]} />
      <View style={[s.featureIconWrap, danger && s.featureIconDanger]}>
        <Text style={[s.featureEmoji, danger && { color: C.red }]}>{broadcastIcon(title, emoji)}</Text>
      </View>
      <View style={s.featureTextWrap}>
        <Text style={[s.featureTitle, danger && { color: C.red }]}>{title}</Text>
        {subtitle ? <Text style={s.featureSubtitle}>{subtitle}</Text> : null}
      </View>
      <Text style={[s.featureArrowText, danger && { color: C.red }]}>›</Text>
    </Pressable>
  );
}`;

const quickAction = String.raw`function QuickAction({
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
      <View style={[s.quickIconWrap, danger && s.quickIconWrapDanger]}>
        <Text style={[s.quickEmoji, danger && { color: C.red }]}>{broadcastIcon(title, emoji)}</Text>
      </View>
      <Text style={[s.quickTitle, danger && { color: C.red }]} numberOfLines={2}>{title}</Text>
      <Text style={[s.quickChevron, danger && { color: C.red }]}>›</Text>
    </Pressable>
  );
}`;

const heroClubCard = String.raw`function HeroClubCard({
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
    <Pressable onPress={onPress} style={({ pressed }) => [s.heroClubCard, pressed && { opacity: 0.78 }]}>
      <View style={s.heroAccent} />
      <View style={s.heroIconWrap}><Text style={s.heroIcon}>◆</Text></View>
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
      <Text style={s.heroChevron}>›</Text>
    </Pressable>
  );
}`;

const wideTile = String.raw`function WideTile({
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
      style={({ pressed }) => [s.wideTile, danger && s.wideTileDanger, pressed && { opacity: 0.74 }]}
    >
      <View style={[s.wideIconWrap, danger && s.wideIconDanger]}><Text style={[s.wideEmoji, danger && { color: C.red }]}>{broadcastIcon(title, emoji)}</Text></View>
      <View style={s.wideBody}>
        <Text style={[s.wideTitle, danger && { color: C.red }]}>{title}</Text>
        {subtitle ? <Text style={s.wideSubtitle}>{subtitle}</Text> : null}
      </View>
      <Text style={[s.wideArrowText, danger && { color: C.red }]}>›</Text>
    </Pressable>
  );
}`;

const featureStart = ui.indexOf('function FeatureTile({');
if (featureStart < 0) throw new Error('AJPA broadcast UI: falta FeatureTile.');
if (!ui.includes('function broadcastIcon(')) ui = ui.slice(0, featureStart) + iconHelper + '\n\n' + ui.slice(featureStart);
replaceFunction('function FeatureTile({', 'function QuickAction({', featureTile, 'FeatureTile');
replaceFunction('function QuickAction({', 'function HeroClubCard({', quickAction, 'QuickAction');
replaceFunction('function HeroClubCard({', 'function WideTile({', heroClubCard, 'HeroClubCard');
replaceFunction('function WideTile({', 'function Title({', wideTile, 'WideTile');

const titleMarker = 'function Title({ eyebrow, title, subtitle }: { eyebrow: string; title: string; subtitle?: string }) {';
if (!ui.includes('function RadioPasilloStrip(')) {
  const radioComponent = String.raw`function RadioPasilloStrip({ marketOpen, onPress }: { marketOpen: boolean; onPress: () => void }) {
  return (
    <Pressable onPress={onPress} style={({ pressed }) => [s.radioStrip, pressed && { opacity: 0.78 }]}>
      <View style={s.radioIconWrap}><Text style={s.radioIcon}>◉</Text></View>
      <View style={s.flex}>
        <Text style={s.radioEyebrow}>RADIO PASILLO</Text>
        <Text style={s.radioHeadline}>{marketOpen ? 'Mercado abierto · últimas novedades AJPA' : 'Mercado cerrado · noticias de la liga'}</Text>
      </View>
      <Text style={s.radioChevron}>›</Text>
    </Pressable>
  );
}`;
  if (!ui.includes(titleMarker)) throw new Error('AJPA broadcast UI: no encontré Title.');
  ui = ui.replace(titleMarker, radioComponent + '\n\n' + titleMarker);
}

const homeStart = ui.indexOf('  const home = (');
const homeEnd = ui.indexOf('  const clubMenu = (', homeStart);
if (homeStart < 0 || homeEnd < 0) throw new Error('AJPA broadcast UI: no pude aislar Inicio.');
let home = ui.slice(homeStart, homeEnd);
if (!home.includes('<RadioPasilloStrip')) {
  const heroIndex = home.indexOf('      <HeroClubCard');
  if (heroIndex < 0) throw new Error('AJPA broadcast UI: no encontré HeroClubCard en Inicio.');
  home = home.slice(0, heroIndex) + `      <RadioPasilloStrip marketOpen={snapshot.status.market_open} onPress={() => openScreen('market')} />\n\n` + home.slice(heroIndex);
  ui = ui.slice(0, homeStart) + home + ui.slice(homeEnd);
}

replaceStyle('screenBackgroundImage', `opacity: 0.18`);
replaceStyle('screenShade', `flex: 1, backgroundColor: 'rgba(2,6,10,0.72)'`);
replaceStyle('content', `padding: 14, paddingTop: 12, paddingBottom: 22, gap: 10`);
replaceStyle('topBar', `height: 56, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: 14, borderBottomWidth: 1, borderBottomColor: 'rgba(75,124,158,0.30)', backgroundColor: 'rgba(2,7,12,0.99)'`);
replaceStyle('screenTitle', `color: C.white, fontSize: 25, fontWeight: '900', letterSpacing: -0.4`);
replaceStyle('eyebrow', `color: '#76a9cf', fontSize: 9, fontWeight: '900', letterSpacing: 1.8, marginBottom: 4`);
replaceStyle('featureTile', `width: '48.5%', minHeight: 142, borderRadius: 18, borderWidth: 1, borderColor: 'rgba(58,88,109,0.72)', backgroundColor: 'rgba(5,14,22,0.97)', padding: 14, overflow: 'hidden', shadowColor: '#000', shadowOpacity: 0.16, shadowRadius: 8, shadowOffset: { width: 0, height: 5 }, elevation: 0`);
replaceStyle('featureTileDanger', `borderColor: 'rgba(128,58,66,0.72)', backgroundColor: 'rgba(24,8,12,0.97)', shadowColor: '#000', shadowOpacity: 0.14, shadowRadius: 7, shadowOffset: { width: 0, height: 4 }, elevation: 0`);
replaceStyle('featureIconWrap', `width: 42, height: 42, borderRadius: 13, borderWidth: 1, borderColor: 'rgba(76,125,160,0.55)', backgroundColor: 'rgba(8,23,34,0.96)', alignItems: 'center', justifyContent: 'center', marginBottom: 12`);
replaceStyle('featureEmoji', `fontSize: 20, color: '#dceaf4', fontWeight: '900'`);
replaceStyle('featureTitle', `color: C.white, fontSize: 17, fontWeight: '900', lineHeight: 21`);
replaceStyle('featureSubtitle', `color: '#889aa8', fontSize: 11, lineHeight: 15, marginTop: 5`);
replaceStyle('featureArrowText', `color: '#78a9cc', fontSize: 25, fontWeight: '600'`);
replaceStyle('quickAction', `flexGrow: 1, flexBasis: '30%', minWidth: 96, minHeight: 58, flexDirection: 'row', alignItems: 'center', borderRadius: 15, borderWidth: 1, borderColor: 'rgba(54,82,102,0.72)', backgroundColor: 'rgba(5,14,22,0.96)', paddingHorizontal: 10, paddingVertical: 9, shadowColor: '#000', shadowOpacity: 0.10, shadowRadius: 5, shadowOffset: { width: 0, height: 3 }, elevation: 0`);
replaceStyle('quickActionDanger', `borderColor: 'rgba(128,58,66,0.72)', backgroundColor: 'rgba(24,8,12,0.96)', shadowColor: '#000', shadowOpacity: 0.10, shadowRadius: 5, shadowOffset: { width: 0, height: 3 }, elevation: 0`);
replaceStyle('quickEmoji', `fontSize: 16, color: '#b9cfde', fontWeight: '900'`);
replaceStyle('quickTitle', `flex: 1, color: C.white, fontSize: 11.5, fontWeight: '800', lineHeight: 15`);
replaceStyle('quickChevron', `color: '#6e9cbd', fontSize: 18, fontWeight: '700'`);
replaceStyle('heroClubCard', `minHeight: 118, flexDirection: 'row', alignItems: 'center', borderRadius: 20, borderWidth: 1, borderColor: 'rgba(61,95,119,0.76)', backgroundColor: 'rgba(5,14,22,0.98)', padding: 14, overflow: 'hidden', shadowColor: '#000', shadowOpacity: 0.15, shadowRadius: 8, shadowOffset: { width: 0, height: 5 }, elevation: 0`);
replaceStyle('heroIconWrap', `width: 48, height: 48, borderRadius: 15, borderWidth: 1, borderColor: 'rgba(82,137,176,0.56)', backgroundColor: 'rgba(8,24,36,0.96)', alignItems: 'center', justifyContent: 'center', marginRight: 13`);
replaceStyle('heroIcon', `fontSize: 20, color: '#dceaf4', fontWeight: '900'`);
replaceStyle('heroClubName', `color: C.white, fontSize: 20, fontWeight: '900', lineHeight: 23`);
replaceStyle('wideTile', `minHeight: 82, flexDirection: 'row', alignItems: 'center', borderRadius: 18, borderWidth: 1, borderColor: 'rgba(57,88,109,0.72)', backgroundColor: 'rgba(5,14,22,0.97)', padding: 12, overflow: 'hidden', shadowColor: '#000', shadowOpacity: 0.12, shadowRadius: 6, shadowOffset: { width: 0, height: 4 }, elevation: 0`);
replaceStyle('wideIconWrap', `width: 46, height: 46, borderRadius: 14, borderWidth: 1, borderColor: 'rgba(76,125,160,0.52)', backgroundColor: 'rgba(8,23,34,0.96)', alignItems: 'center', justifyContent: 'center', marginRight: 12`);
replaceStyle('wideEmoji', `fontSize: 20, color: '#dceaf4', fontWeight: '900'`);
replaceStyle('wideTitle', `color: C.white, fontSize: 16, fontWeight: '900'`);
replaceStyle('wideSubtitle', `color: '#889aa8', fontSize: 11.5, lineHeight: 16, marginTop: 3`);
replaceStyle('wideArrowText', `color: '#78a9cc', fontSize: 25, fontWeight: '600'`);
replaceStyle('profileButton', `width: 36, height: 36, borderRadius: 18, borderWidth: 1, borderColor: 'rgba(75,124,158,0.52)', alignItems: 'center', justifyContent: 'center', backgroundColor: 'rgba(6,17,26,0.98)'`);

const styleMarker = '\nconst s = StyleSheet.create({';
const styleStart = ui.lastIndexOf(styleMarker);
const finalReturnStart = ui.lastIndexOf('  return (', styleStart);
if (styleStart < 0 || finalReturnStart < 0) throw new Error('AJPA broadcast UI: no encontré el shell final.');

const finalReturn = String.raw`  const bottomActive =
    screen === 'home' ? 'home' :
    ['club', 'roster', 'economy', 'clubValue', 'clubInfo', 'resign'].includes(screen) ? 'club' :
    ['market', 'publish', 'transferibles', 'clausulazo', 'offers', 'search', 'history'].includes(screen) ? 'market' :
    screen === 'league' ? 'league' :
    screen === 'profile' ? 'profile' :
    'home';

  const bottomNav = (
    <View style={s.bottomNav}>
      <Pressable onPress={goHome} style={[s.bottomNavItem, bottomActive === 'home' && s.bottomNavItemActive]}><Text style={[s.bottomNavIcon, bottomActive === 'home' && s.bottomNavIconActive]}>⌂</Text><Text style={[s.bottomNavLabel, bottomActive === 'home' && s.bottomNavLabelActive]}>Inicio</Text></Pressable>
      <Pressable onPress={() => requireClub('club')} style={[s.bottomNavItem, bottomActive === 'club' && s.bottomNavItemActive]}><Text style={[s.bottomNavIcon, bottomActive === 'club' && s.bottomNavIconActive]}>◆</Text><Text style={[s.bottomNavLabel, bottomActive === 'club' && s.bottomNavLabelActive]}>Club</Text></Pressable>
      <Pressable onPress={() => void openScreen('market')} style={[s.bottomNavItem, bottomActive === 'market' && s.bottomNavItemActive]}><Text style={[s.bottomNavIcon, bottomActive === 'market' && s.bottomNavIconActive]}>↔</Text><Text style={[s.bottomNavLabel, bottomActive === 'market' && s.bottomNavLabelActive]}>Mercado</Text></Pressable>
      <Pressable onPress={() => void openScreen('league')} style={[s.bottomNavItem, bottomActive === 'league' && s.bottomNavItemActive]}><Text style={[s.bottomNavIcon, bottomActive === 'league' && s.bottomNavIconActive]}>★</Text><Text style={[s.bottomNavLabel, bottomActive === 'league' && s.bottomNavLabelActive]}>Liga</Text></Pressable>
      <Pressable onPress={() => void openScreen('profile')} style={[s.bottomNavItem, bottomActive === 'profile' && s.bottomNavItemActive]}><Text style={[s.bottomNavIcon, bottomActive === 'profile' && s.bottomNavIconActive]}>◎</Text><Text style={[s.bottomNavLabel, bottomActive === 'profile' && s.bottomNavLabelActive]}>Perfil</Text></Pressable>
    </View>
  );

  return (
    <View style={s.root}>
      <View style={s.topBar}>
        {screen !== 'home' ? (
          <View style={s.topNavActions}><Pressable onPress={goBack} style={s.topAction}><Text style={s.topActionText}>‹ VOLVER</Text></Pressable><Pressable onPress={goHome} style={s.topAction}><Text style={s.topActionText}>⌂ MENÚ</Text></Pressable></View>
        ) : (
          <View><Text style={s.brand}>AJPA</Text><Text style={s.brandSub}>LIGA · MERCADO · COMUNIDAD</Text></View>
        )}
        <Pressable onPress={() => void openScreen('profile')} style={s.profileButton}><Text style={s.profileButtonText}>◎</Text></Pressable>
      </View>
      <View style={s.main}>
        <ImageBackground source={typeof screenBackground === 'string' ? { uri: screenBackground } : screenBackground} style={s.screenBackground} imageStyle={s.screenBackgroundImage} resizeMode="cover">
          <View style={[s.screenShade, screen === 'clausulazo' && s.clausulazoShade, screen === 'league' && s.leagueShade]}>{body}</View>
        </ImageBackground>
      </View>
      {bottomNav}
    </View>
  );
}
`;
ui = ui.slice(0, finalReturnStart) + finalReturn + ui.slice(styleStart);

const styleClose = '\n});';
const stylePos = ui.lastIndexOf(styleClose);
if (stylePos < 0) throw new Error('AJPA broadcast UI: no encontré cierre de estilos.');
const extraStyles = String.raw`
  featureAccent: { position: 'absolute', top: 0, left: 14, width: 42, height: 2, borderRadius: 2, backgroundColor: '#5e9bc6' },
  featureAccentDanger: { backgroundColor: '#b25d67' },
  quickIconWrap: { width: 28, height: 28, borderRadius: 9, borderWidth: 1, borderColor: 'rgba(71,111,139,0.50)', backgroundColor: 'rgba(8,23,34,0.92)', alignItems: 'center', justifyContent: 'center', marginRight: 7 },
  quickIconWrapDanger: { borderColor: 'rgba(151,69,79,0.52)', backgroundColor: 'rgba(31,10,14,0.92)' },
  heroAccent: { position: 'absolute', top: 0, bottom: 0, left: 0, width: 3, backgroundColor: '#5e9bc6' },
  heroChevron: { color: '#78a9cc', fontSize: 28, fontWeight: '600', marginLeft: 8 },
  radioStrip: { minHeight: 66, flexDirection: 'row', alignItems: 'center', gap: 10, borderRadius: 17, borderWidth: 1, borderColor: 'rgba(57,88,109,0.72)', backgroundColor: 'rgba(5,14,22,0.97)', paddingHorizontal: 12, paddingVertical: 10 },
  radioIconWrap: { width: 38, height: 38, borderRadius: 12, alignItems: 'center', justifyContent: 'center', borderWidth: 1, borderColor: 'rgba(76,125,160,0.52)', backgroundColor: 'rgba(8,23,34,0.96)' },
  radioIcon: { color: '#89b9da', fontSize: 17, fontWeight: '900' },
  radioEyebrow: { color: '#7faac8', fontSize: 8.5, fontWeight: '900', letterSpacing: 1.5 },
  radioHeadline: { color: C.white, fontSize: 12.5, fontWeight: '800', marginTop: 2, lineHeight: 16 },
  radioChevron: { color: '#78a9cc', fontSize: 24, fontWeight: '600' },
  topNavActions: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  bottomNav: { minHeight: 62, flexDirection: 'row', alignItems: 'stretch', paddingHorizontal: 6, paddingTop: 5, paddingBottom: 4, borderTopWidth: 1, borderTopColor: 'rgba(57,88,109,0.58)', backgroundColor: 'rgba(2,7,12,0.995)' },
  bottomNavItem: { flex: 1, minWidth: 0, borderRadius: 11, alignItems: 'center', justifyContent: 'center', paddingVertical: 4 },
  bottomNavItemActive: { backgroundColor: 'rgba(60,103,134,0.15)' },
  bottomNavIcon: { color: '#647581', fontSize: 17, fontWeight: '900', lineHeight: 19 },
  bottomNavIconActive: { color: '#9dc3dc' },
  bottomNavLabel: { color: '#667783', fontSize: 8, fontWeight: '800', marginTop: 2 },
  bottomNavLabelActive: { color: C.white },
`;
const knownExtraStart = ui.indexOf('  featureImage: {');
if (knownExtraStart >= 0) {
  const knownExtraEnd = ui.indexOf('\n});', knownExtraStart);
  if (knownExtraEnd < 0) throw new Error('AJPA broadcast UI: bloque v3 anterior incompleto.');
  ui = ui.slice(0, knownExtraStart) + extraStyles.trimStart() + ui.slice(knownExtraEnd);
} else {
  ui = ui.slice(0, stylePos) + extraStyles + ui.slice(stylePos);
}

if (!ui.includes('RADIO PASILLO')) throw new Error('AJPA broadcast UI: Radio Pasillo no quedó aplicado.');
if (!ui.includes('const bottomNav = (')) throw new Error('AJPA broadcast UI: navegación inferior no quedó aplicada.');
if (ui.includes('featureImageAsset')) throw new Error('AJPA broadcast UI: todavía quedan fondos fotográficos dentro de tarjetas.');

fs.writeFileSync(uiPath, ui);
console.log('AJPA broadcast UI: tarjetas limpias, iconografía monocroma, menor brillo y navegación inferior aplicados.');
