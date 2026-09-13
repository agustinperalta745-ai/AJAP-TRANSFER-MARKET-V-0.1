import fs from 'node:fs';

const uiPath = new URL('../src/BotParityAppV2.tsx', import.meta.url);
let ui = fs.readFileSync(uiPath, 'utf8');

function replaceStyle(name, body) {
  const re = new RegExp(`  ${name}: \\{[^\\n]*\\},`);
  if (!re.test(ui)) return false;
  ui = ui.replace(re, `  ${name}: { ${body} },`);
  return true;
}

// Primary dashboard cards: the image now lives inside the card instead of
// competing with the entire screen. Existing routes and business logic stay intact.
const featureStart = ui.indexOf('function FeatureTile({');
const featureEnd = ui.indexOf('function QuickAction({', featureStart);
if (featureStart < 0 || featureEnd < 0) {
  throw new Error('AJPA mobile v3: no pude aislar FeatureTile.');
}

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
  const normalizedTitle = title.toLowerCase();
  const featureBackground =
    normalizedTitle.includes('buscar partido') ? BG_INICIO :
    normalizedTitle.includes('liga') ||
    normalizedTitle.includes('copa') ||
    normalizedTitle.includes('vitrina') ||
    normalizedTitle.includes('champions') ||
    normalizedTitle.includes('europa') ||
    normalizedTitle.includes('trofeo') ||
    normalizedTitle.includes('campe') ? BG_LIGA :
    normalizedTitle.includes('mercado') ||
    normalizedTitle.includes('transfer') ||
    normalizedTitle.includes('publicar') ||
    normalizedTitle.includes('oferta') ||
    normalizedTitle.includes('clausul') ||
    normalizedTitle.includes('agente') ||
    normalizedTitle.includes('fich') ? BG_MERCADO :
    normalizedTitle.includes('club') ||
    normalizedTitle.includes('plantilla') ||
    normalizedTitle.includes('econom') ||
    normalizedTitle.includes('valor') ||
    normalizedTitle.includes('inform') ? BG_EQUIPOS :
    null;

  const visualIcon =
    normalizedTitle.includes('buscar') ? '⌖' :
    normalizedTitle.includes('liga') || normalizedTitle.includes('copa') || normalizedTitle.includes('vitrina') ? '★' :
    normalizedTitle.includes('mercado') || normalizedTitle.includes('transfer') || normalizedTitle.includes('oferta') || normalizedTitle.includes('publicar') ? '⇄' :
    normalizedTitle.includes('club') || normalizedTitle.includes('plantilla') || normalizedTitle.includes('econom') ? '◆' :
    emoji;

  const contents = (
    <>
      <View style={[s.featureIconWrap, danger && s.featureIconDanger]}>
        <Text style={s.featureEmoji}>{visualIcon}</Text>
      </View>
      <View style={s.featureTextWrap}>
        <Text style={[s.featureTitle, danger && { color: C.red }]}>{title}</Text>
        {subtitle ? <Text style={s.featureSubtitle}>{subtitle}</Text> : null}
      </View>
      <View style={[s.featureArrow, danger && { borderColor: '#74323a' }]}>
        <Text style={[s.featureArrowText, danger && { color: C.red }]}>›</Text>
      </View>
    </>
  );

  return (
    <Pressable
      onPress={onPress}
      style={({ pressed }) => [
        s.featureTile,
        danger && s.featureTileDanger,
        pressed && { opacity: 0.78, transform: [{ scale: 0.985 }] },
      ]}
    >
      {featureBackground ? (
        <ImageBackground
          source={typeof featureBackground === 'string' ? { uri: featureBackground } : featureBackground}
          style={s.featureImage}
          imageStyle={s.featureImageAsset}
          resizeMode="cover"
        >
          <View style={[s.featureImageShade, danger && s.featureImageShadeDanger]}>
            <SurfaceDepth danger={danger} />
            {contents}
          </View>
        </ImageBackground>
      ) : (
        <View style={[s.featureTilePlain, danger && s.featureTilePlainDanger]}>
          <SurfaceDepth danger={danger} />
          {contents}
        </View>
      )}
    </Pressable>
  );
}

`;
ui = ui.slice(0, featureStart) + featureTile + ui.slice(featureEnd);

// Radio Pasillo becomes a compact editorial strip on Inicio. It opens Mercado,
// so it is useful rather than decorative.
const titleMarker = 'function Title({ eyebrow, title, subtitle }: { eyebrow: string; title: string; subtitle?: string }) {';
if (!ui.includes('function RadioPasilloStrip(')) {
  if (!ui.includes(titleMarker)) throw new Error('AJPA mobile v3: no encontré Title.');
  const radioComponent = String.raw`function RadioPasilloStrip({ marketOpen, onPress }: { marketOpen: boolean; onPress: () => void }) {
  return (
    <Pressable onPress={onPress} style={({ pressed }) => [s.radioStrip, pressed && { opacity: 0.78 }]}>
      <View style={s.radioIconWrap}><Text style={s.radioIcon}>◉</Text></View>
      <View style={s.flex}>
        <Text style={s.radioEyebrow}>RADIO PASILLO</Text>
        <Text style={s.radioHeadline}>{marketOpen ? 'Mercado abierto · AJPA está en movimiento' : 'Mercado cerrado · seguí toda la actualidad'}</Text>
      </View>
      <Text style={s.radioChevron}>›</Text>
    </Pressable>
  );
}

`;
  ui = ui.replace(titleMarker, radioComponent + titleMarker);
}

const homeStart = ui.indexOf('  const home = (');
const homeEnd = ui.indexOf('  const clubMenu = (', homeStart);
if (homeStart < 0 || homeEnd < 0) throw new Error('AJPA mobile v3: no pude aislar Inicio.');
let home = ui.slice(homeStart, homeEnd);
if (!home.includes('<RadioPasilloStrip')) {
  const heroIndex = home.indexOf('      <HeroClubCard');
  if (heroIndex < 0) throw new Error('AJPA mobile v3: no encontré HeroClubCard en Inicio.');
  home = home.slice(0, heroIndex) + `      <RadioPasilloStrip marketOpen={snapshot.status.market_open} onPress={() => openScreen('market')} />\n\n` + home.slice(heroIndex);
  ui = ui.slice(0, homeStart) + home + ui.slice(homeEnd);
}

// The screen background becomes atmosphere; visual identity moves to the cards.
replaceStyle('screenBackgroundImage', `opacity: 0.34`);
replaceStyle('screenShade', `flex: 1, backgroundColor: 'rgba(2,6,10,0.54)'`);
replaceStyle('content', `padding: 15, paddingTop: 14, paddingBottom: 24, gap: 12`);
replaceStyle('topBar', `height: 58, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: 13, borderBottomWidth: 1, borderBottomColor: 'rgba(57,128,181,0.36)', backgroundColor: 'rgba(2,7,12,0.985)'`);
replaceStyle('featureTile', `width: '48.4%', minHeight: 184, borderRadius: 23, borderWidth: 1, borderTopWidth: 1.45, borderBottomWidth: 1.9, borderTopColor: 'rgba(115,194,248,0.72)', borderBottomColor: 'rgba(6,52,86,0.98)', borderLeftColor: 'rgba(42,113,164,0.58)', borderRightColor: 'rgba(42,113,164,0.58)', backgroundColor: 'rgba(3,14,24,0.98)', padding: 0, overflow: 'hidden', shadowColor: '#000', shadowOpacity: 0.20, shadowRadius: 11, shadowOffset: { width: 0, height: 7 }, elevation: 0`);
replaceStyle('featureTileDanger', `borderColor: '#8e3943', backgroundColor: 'rgba(30,7,12,0.96)', shadowColor: '#000', shadowOpacity: 0.18, shadowRadius: 9, shadowOffset: { width: 0, height: 6 }, elevation: 0`);
replaceStyle('featureIconWrap', `width: 52, height: 52, borderRadius: 17, borderWidth: 1, borderColor: 'rgba(117,198,255,0.56)', backgroundColor: 'rgba(2,12,20,0.76)', alignItems: 'center', justifyContent: 'center', marginBottom: 15`);
replaceStyle('featureEmoji', `fontSize: 26, color: C.white, fontWeight: '900'`);
replaceStyle('profileButton', `width: 38, height: 38, borderRadius: 19, borderWidth: 1, borderColor: 'rgba(72,151,207,0.54)', alignItems: 'center', justifyContent: 'center', backgroundColor: 'rgba(3,15,25,0.96)'`);

// Replace only the final app shell. All screen bodies and endpoints remain untouched.
const styleMarker = '\nconst s = StyleSheet.create({';
const styleStart = ui.lastIndexOf(styleMarker);
const finalReturnStart = ui.lastIndexOf('  return (', styleStart);
if (styleStart < 0 || finalReturnStart < 0) throw new Error('AJPA mobile v3: no encontré el shell final.');

const finalReturn = String.raw`  const bottomActive =
    screen === 'home' ? 'home' :
    ['club', 'roster', 'economy', 'clubValue', 'clubInfo', 'resign'].includes(screen) ? 'club' :
    ['market', 'publish', 'transferibles', 'clausulazo', 'offers', 'search', 'history'].includes(screen) ? 'market' :
    screen === 'league' ? 'league' :
    screen === 'profile' ? 'profile' :
    'home';

  const bottomNav = (
    <View style={s.bottomNav}>
      <Pressable onPress={goHome} style={[s.bottomNavItem, bottomActive === 'home' && s.bottomNavItemActive]}>
        <Text style={[s.bottomNavIcon, bottomActive === 'home' && s.bottomNavIconActive]}>⌂</Text>
        <Text style={[s.bottomNavLabel, bottomActive === 'home' && s.bottomNavLabelActive]}>Inicio</Text>
      </Pressable>
      <Pressable onPress={() => requireClub('club')} style={[s.bottomNavItem, bottomActive === 'club' && s.bottomNavItemActive]}>
        <Text style={[s.bottomNavIcon, bottomActive === 'club' && s.bottomNavIconActive]}>◆</Text>
        <Text style={[s.bottomNavLabel, bottomActive === 'club' && s.bottomNavLabelActive]}>Club</Text>
      </Pressable>
      <Pressable onPress={() => void openScreen('market')} style={[s.bottomNavItem, bottomActive === 'market' && s.bottomNavItemActive]}>
        <Text style={[s.bottomNavIcon, bottomActive === 'market' && s.bottomNavIconActive]}>⇄</Text>
        <Text style={[s.bottomNavLabel, bottomActive === 'market' && s.bottomNavLabelActive]}>Mercado</Text>
      </Pressable>
      <Pressable onPress={() => void openScreen('league')} style={[s.bottomNavItem, bottomActive === 'league' && s.bottomNavItemActive]}>
        <Text style={[s.bottomNavIcon, bottomActive === 'league' && s.bottomNavIconActive]}>★</Text>
        <Text style={[s.bottomNavLabel, bottomActive === 'league' && s.bottomNavLabelActive]}>Liga</Text>
      </Pressable>
      <Pressable onPress={() => void openScreen('profile')} style={[s.bottomNavItem, bottomActive === 'profile' && s.bottomNavItemActive]}>
        <Text style={[s.bottomNavIcon, bottomActive === 'profile' && s.bottomNavIconActive]}>◎</Text>
        <Text style={[s.bottomNavLabel, bottomActive === 'profile' && s.bottomNavLabelActive]}>Perfil</Text>
      </Pressable>
    </View>
  );

  return (
    <View style={s.root}>
      <View style={s.topBar}>
        {screen !== 'home' ? (
          <View style={s.topNavActions}>
            <Pressable onPress={goBack} style={s.topAction}><Text style={s.topActionText}>‹ VOLVER</Text></Pressable>
            <Pressable onPress={goHome} style={s.topAction}><Text style={s.topActionText}>⌂ MENÚ</Text></Pressable>
          </View>
        ) : (
          <View><Text style={s.brand}>AJPA</Text><Text style={s.brandSub}>LIGA · MERCADO · COMUNIDAD</Text></View>
        )}
        <Pressable onPress={() => void openScreen('profile')} style={s.profileButton}><Text style={s.profileButtonText}>◎</Text></Pressable>
      </View>
      <View style={s.main}>
        <ImageBackground
          source={typeof screenBackground === 'string' ? { uri: screenBackground } : screenBackground}
          style={s.screenBackground}
          imageStyle={s.screenBackgroundImage}
          resizeMode="cover"
        >
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
if (stylePos < 0) throw new Error('AJPA mobile v3: no encontré cierre de estilos.');
if (!ui.includes('  featureImage: {')) {
  const extraStyles = String.raw`
  featureImage: { flex: 1, minHeight: 184 },
  featureImageAsset: { opacity: 0.64 },
  featureImageShade: { flex: 1, minHeight: 184, padding: 15, backgroundColor: 'rgba(2,8,14,0.48)' },
  featureImageShadeDanger: { backgroundColor: 'rgba(24,4,9,0.60)' },
  featureTilePlain: { flex: 1, minHeight: 184, padding: 15, backgroundColor: 'rgba(3,16,27,0.96)' },
  featureTilePlainDanger: { backgroundColor: 'rgba(31,7,13,0.94)' },
  radioStrip: { minHeight: 78, flexDirection: 'row', alignItems: 'center', gap: 12, borderRadius: 20, borderWidth: 1, borderColor: 'rgba(58,140,199,0.50)', backgroundColor: 'rgba(3,13,22,0.94)', paddingHorizontal: 14, paddingVertical: 12, overflow: 'hidden' },
  radioIconWrap: { width: 44, height: 44, borderRadius: 15, alignItems: 'center', justifyContent: 'center', borderWidth: 1, borderColor: 'rgba(83,170,229,0.50)', backgroundColor: 'rgba(6,28,45,0.90)' },
  radioIcon: { color: '#6bc0ff', fontSize: 22, fontWeight: '900' },
  radioEyebrow: { color: C.blueSoft, fontSize: 9, fontWeight: '900', letterSpacing: 1.5 },
  radioHeadline: { color: C.white, fontSize: 13, fontWeight: '800', marginTop: 3, lineHeight: 17 },
  radioChevron: { color: C.blueSoft, fontSize: 27, fontWeight: '700' },
  topNavActions: { flexDirection: 'row', alignItems: 'center', gap: 7 },
  bottomNav: { minHeight: 68, flexDirection: 'row', alignItems: 'stretch', gap: 3, paddingHorizontal: 6, paddingTop: 6, paddingBottom: 5, borderTopWidth: 1, borderTopColor: 'rgba(55,125,176,0.38)', backgroundColor: 'rgba(2,7,12,0.99)' },
  bottomNavItem: { flex: 1, minWidth: 0, borderRadius: 14, borderWidth: 1, borderColor: 'transparent', alignItems: 'center', justifyContent: 'center', paddingVertical: 5 },
  bottomNavItemActive: { borderColor: 'rgba(72,157,219,0.42)', backgroundColor: 'rgba(37,124,190,0.13)' },
  bottomNavIcon: { color: '#6e7f8e', fontSize: 20, fontWeight: '900', lineHeight: 22 },
  bottomNavIconActive: { color: C.blueSoft },
  bottomNavLabel: { color: '#718190', fontSize: 8.5, fontWeight: '800', marginTop: 2 },
  bottomNavLabelActive: { color: C.white },
`;
  ui = ui.slice(0, stylePos) + extraStyles + ui.slice(stylePos);
}

if (!ui.includes('RADIO PASILLO')) throw new Error('AJPA mobile v3: Radio Pasillo no quedó aplicado.');
if (!ui.includes('const bottomNav = (')) throw new Error('AJPA mobile v3: navegación inferior no quedó aplicada.');
if (!ui.includes('featureImageShade')) throw new Error('AJPA mobile v3: fondos internos de tarjetas no quedaron aplicados.');

fs.writeFileSync(uiPath, ui);
console.log('AJPA mobile v3: fondos dentro de tarjetas + panel oscuro + Radio Pasillo + navegación inferior aplicados.');
