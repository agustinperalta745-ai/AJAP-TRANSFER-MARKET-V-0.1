import fs from 'node:fs';

const uiPath = new URL('../src/BotParityAppV2.tsx', import.meta.url);
let ui = fs.readFileSync(uiPath, 'utf8');

function mustReplace(search, replacement, label) {
  if (!ui.includes(search)) throw new Error(`AJPA redesign shell: no encontré ${label}`);
  ui = ui.replace(search, replacement);
}

if (ui.includes("import React, { ReactNode, useCallback, useEffect, useMemo, useState } from 'react';")) {
  ui = ui.replace(
    "import React, { ReactNode, useCallback, useEffect, useMemo, useState } from 'react';",
    "import React, { ReactNode, useCallback, useEffect, useLayoutEffect, useMemo, useState } from 'react';",
  );
}

if (!/^export type Screen =/m.test(ui)) {
  ui = ui.replace(/^type Screen =/m, 'export type Screen =');
}

const organizedSignature = `export default function BotParityAppV2({ onOpenMatchSearch }: { onOpenMatchSearch?: () => void } = {}) {`;
const plainSignature = `export default function BotParityAppV2() {`;
const replacementSignature = `export type BotParityAppV2Props = {
  initialScreen?: Screen;
  initialSnapshot?: LeagueSnapshot | null;
  initialProfile?: MobileProfile | null;
  embedded?: boolean;
  onExit?: () => void;
  onOpenMatchSearch?: () => void;
};

export default function BotParityAppV2({
  initialScreen = 'home',
  initialSnapshot = null,
  initialProfile = null,
  embedded = false,
  onExit,
  onOpenMatchSearch,
}: BotParityAppV2Props = {}) {`;

if (ui.includes(organizedSignature)) {
  ui = ui.replace(organizedSignature, replacementSignature);
} else if (ui.includes(plainSignature)) {
  ui = ui.replace(plainSignature, replacementSignature);
} else {
  throw new Error('AJPA redesign shell: no encontré firma del componente');
}

mustReplace(
  "  const [screen, setScreen] = useState<Screen>('home');",
  "  const [screen, setScreen] = useState<Screen>(initialScreen);",
  'pantalla inicial',
);

if (ui.includes("  const [snapshot, setSnapshot] = useState<LeagueSnapshot | null>(null);")) {
  ui = ui.replace(
    "  const [snapshot, setSnapshot] = useState<LeagueSnapshot | null>(null);",
    "  const [snapshot, setSnapshot] = useState<LeagueSnapshot | null>(initialSnapshot);",
  );
}
if (ui.includes("  const [profile, setProfile] = useState<MobileProfile | null>(null);")) {
  ui = ui.replace(
    "  const [profile, setProfile] = useState<MobileProfile | null>(null);",
    "  const [profile, setProfile] = useState<MobileProfile | null>(initialProfile);",
  );
}

const stateSyncAnchor = "  const [offeredPlayerId, setOfferedPlayerId] = useState<number | null>(null);";
if (ui.includes(stateSyncAnchor) && !ui.includes("setScreen(initialScreen);\n  }, [embedded, initialScreen]")) {
  ui = ui.replace(
    stateSyncAnchor,
    stateSyncAnchor + `

  useLayoutEffect(() => {
    if (!embedded) return;
    setScreenHistory([]);
    setScreen(initialScreen);
  }, [embedded, initialScreen]);

  useEffect(() => {
    if (initialSnapshot) setSnapshot(initialSnapshot);
  }, [initialSnapshot]);

  useEffect(() => {
    if (initialProfile) setProfile(initialProfile);
  }, [initialProfile]);
`,
  );
}

if (ui.includes("  const [loading, setLoading] = useState(true);")) {
  ui = ui.replace(
    "  const [loading, setLoading] = useState(true);",
    "  const [loading, setLoading] = useState(!embedded);",
  );
}

if (ui.includes("      manual ? setRefreshing(true) : setLoading(true);")) {
  ui = ui.replace(
    "      manual ? setRefreshing(true) : setLoading(true);",
    "      if (manual) setRefreshing(true); else if (!embedded) setLoading(true);",
  );
}

const transientProfileCatch = `      } catch {
        setProfile(null);
        setRoster([]);
      }`;
if (ui.includes(transientProfileCatch)) {
  ui = ui.replace(
    transientProfileCatch,
    `      } catch (error) {
        const status = (error as { status?: number } | null)?.status;
        // A temporary network failure must not make a linked account look unlinked.
        // Only a confirmed 401 clears the visible identity.
        if (status === 401) {
          setProfile(null);
          setRoster([]);
        }
      }`,
  );
}

const disconnectedBlock = `  if (!snapshot) {
    return (
      <SafeAreaView style={s.root}>
        <Text style={s.screenTitle}>Sin conexión</Text>
        <Button label="REINTENTAR" onPress={() => loadAll()} />
      </SafeAreaView>
    );
  }`;
if (ui.includes(disconnectedBlock)) {
  ui = ui.replace(
    disconnectedBlock,
    `  if (!snapshot) {
    return (
      <SafeAreaView style={s.root}>
        <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center', paddingHorizontal: 28 }}>
          {loading ? (
            <>
              <ActivityIndicator color={C.blue} />
              <Text style={[s.screenTitle, { marginTop: 12 }]}>Cargando AJPA</Text>
              <Text style={s.muted}>Sincronizando datos reales…</Text>
            </>
          ) : (
            <>
              <Text style={s.screenTitle}>No se pudo conectar</Text>
              <Text style={s.muted}>Se mantiene oculto el estado hasta poder verificarlo.</Text>
              <Button label="REINTENTAR" onPress={() => loadAll()} />
            </>
          )}
        </View>
      </SafeAreaView>
    );
  }`,
  );
}

if (ui.includes('<SeasonCountdownBanner />')) {
  ui = ui.replace('<SeasonCountdownBanner />', '{embedded ? null : <SeasonCountdownBanner />}');
}

if (!ui.includes('const embeddedScreenTitle =')) {
  const anchor = '  const screenBackground = (() => {';
  if (!ui.includes(anchor)) throw new Error('AJPA redesign shell: no encontré screenBackground para título embebido');
  const titleMap = `  const embeddedScreenTitle = (() => {
    const labels: Partial<Record<Screen, string>> = {
      club: 'Mi Club',
      roster: 'Plantilla',
      economy: 'Economía',
      clubValue: 'Valor del Club',
      clubInfo: 'Información del club',
      market: 'Mercado',
      publish: 'Publicar jugador',
      transferibles: 'Transferibles',
      freeAgents: 'Agentes libres',
      clausulazo: 'Clausulazo',
      offers: 'Ofertas',
      search: 'Buscar jugador',
      history: 'Historial',
      league: 'Liga',
      titles: 'Copas',
      admin: 'Staff / Admin',
      adminTools: 'Administración',
      assignments: 'Asignaciones',
      resign: 'Renunciar al club',
      profile: 'Perfil',
    };
    return labels[screen] || 'AJPA';
  })();

`;
  ui = ui.replace(anchor, titleMap + anchor);
}

const oldTopBar = `      <View style={s.topBar}>
        {screen !== 'home' ? (
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 7 }}>
            <Pressable onPress={goBack} style={s.topAction}><Text style={s.topActionText}>‹ VOLVER</Text></Pressable>
            <Pressable onPress={goHome} style={s.topAction}><Text style={s.topActionText}>⌂ MENÚ</Text></Pressable>
          </View>
        ) : (
          <View><Text style={s.brand}>AJPA</Text><Text style={s.brandSub}>TRANSFER MARKET · MOBILE</Text></View>
        )}
        <Pressable onPress={() => void openScreen('profile')} style={s.profileButton}><Text style={s.profileButtonText}>MI PERFIL</Text></Pressable>
      </View>`;

if (ui.includes(oldTopBar)) {
  ui = ui.replace(oldTopBar, `      {embedded ? (
        screen === 'profile' ? (
          <View style={s.topBar}>
            <Pressable
              onPress={() => {
                if (screen === initialScreen && onExit) onExit();
                else goBack();
              }}
              style={s.topAction}
            >
              <Text style={s.topActionText}>‹ VOLVER</Text>
            </Pressable>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
              <Image source={require('../assets/ajpa-league-logo.png')} style={{ width: 34, height: 34, borderRadius: 17 }} resizeMode="contain" />
              <Text style={s.brand}>AJPA</Text>
            </View>
          </View>
        ) : screen === 'transferibles' ? (
          <View style={s.transferApprovedHeader}>
            <View style={s.transferBrandRow}>
              <Pressable onPress={goBack} style={s.transferBrandPressable}>
                <Image source={require('../assets/ajpa-league-logo.png')} style={s.transferBrandLogo} resizeMode="contain" />
                <View style={s.transferBrandCopy}>
                  <Text style={s.transferBrandTitle}>AJPA</Text>
                  <Text style={s.transferBrandSubtitle}>ASOCIACIÓN DE JUGADORES DE PES ARGENTINA</Text>
                </View>
              </Pressable>
              <View style={s.transferLiveDot} />
            </View>
            <Pressable onPress={() => void openScreen('profile')} style={s.transferHelloCard}>
              <View>
                <Text style={s.transferHelloTitle}>Hola, DT</Text>
                <Text style={s.transferHelloSub}>{profile ? 'Conectado a AJPA' : 'Conectá tu cuenta'}</Text>
              </View>
              <Text style={s.transferHelloChevron}>›</Text>
            </Pressable>
          </View>
        ) : (
          <View style={s.topBar}>
            <Pressable
              onPress={() => {
                if (screen === initialScreen && onExit) onExit();
                else goBack();
              }}
              style={s.topAction}
            >
              <Text style={s.topActionText}>‹ VOLVER</Text>
            </Pressable>
            <View style={{ flex: 1, minWidth: 0, marginLeft: 10 }}>
              <Text style={s.brandSub}>AJPA</Text>
              <Text style={s.embeddedHeaderTitle} numberOfLines={1}>{embeddedScreenTitle}</Text>
            </View>
          </View>
        )
      ) : (
        <View style={s.topBar}>
          {screen !== 'home' ? (
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 7 }}>
              <Pressable onPress={goBack} style={s.topAction}><Text style={s.topActionText}>‹ VOLVER</Text></Pressable>
              <Pressable onPress={goHome} style={s.topAction}><Text style={s.topActionText}>⌂ MENÚ</Text></Pressable>
            </View>
          ) : (
            <View><Text style={s.brand}>AJPA</Text><Text style={s.brandSub}>TRANSFER MARKET · MOBILE</Text></View>
          )}
          <Pressable onPress={() => void openScreen('profile')} style={s.profileButton}><Text style={s.profileButtonText}>MI PERFIL</Text></Pressable>
        </View>
      )}`);
}

ui = ui.replace(
  `{screen === 'titles' ? <TrophyCabinetScreen onClose={() => setScreen('home')} /> : null}`,
  `{screen === 'titles' ? <TrophyCabinetScreen onClose={() => embedded && onExit ? onExit() : setScreen('home')} /> : null}`,
);

if (!ui.includes('  embeddedHeaderTitle: {')) {
  const styleEnd = ui.lastIndexOf('\n});');
  if (styleEnd < 0) throw new Error('AJPA redesign shell: no encontré cierre de estilos');
  ui = ui.slice(0, styleEnd) + `
  embeddedHeaderTitle: { color: C.white, fontSize: 15.5, lineHeight: 18, fontWeight: '900' },
  transferApprovedHeader: { backgroundColor: '#07131F', paddingHorizontal: 14, paddingTop: 10, paddingBottom: 8 },
  transferBrandRow: { minHeight: 68, flexDirection: 'row', alignItems: 'center' },
  transferBrandPressable: { flex: 1, minWidth: 0, flexDirection: 'row', alignItems: 'center' },
  transferBrandLogo: { width: 58, height: 58, borderRadius: 29, marginRight: 10 },
  transferBrandCopy: { flex: 1, minWidth: 0 },
  transferBrandTitle: { color: '#F5FAFE', fontSize: 31, lineHeight: 33, fontWeight: '900', letterSpacing: 1 },
  transferBrandSubtitle: { color: '#58B9F2', fontSize: 8.3, lineHeight: 11, fontWeight: '900', letterSpacing: 1.65 },
  transferLiveDot: { width: 11, height: 11, borderRadius: 6, backgroundColor: '#35DF72', marginLeft: 8 },
  transferHelloCard: { alignSelf: 'flex-end', width: 156, minHeight: 58, marginTop: 5, borderRadius: 16, borderWidth: 1, borderColor: '#245374', backgroundColor: '#0B2030', paddingHorizontal: 12, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  transferHelloTitle: { color: '#F3F7FA', fontSize: 14, fontWeight: '900' },
  transferHelloSub: { color: '#8C9BA8', fontSize: 9.5, marginTop: 2 },
  transferHelloChevron: { color: '#32B7FF', fontSize: 28, lineHeight: 29, fontWeight: '700' },

` + ui.slice(styleEnd);
}

if (ui.includes("require('../assets/generated/xi-ideal-splash.webp')")) {
  ui = ui.replace(
    "require('../assets/generated/xi-ideal-splash.webp')",
    "require('../assets/ajpa-hero-neutral.jpg')",
  );
}

const emptyBack = `      if (previous.length === 0) {
        setScreen('home');
        return [];
      }`;
if (ui.includes(emptyBack)) {
  ui = ui.replace(
    emptyBack,
    `      if (previous.length === 0) {
        if (embedded && onExit) {
          onExit();
        } else {
          setScreen('home');
        }
        return [];
      }`,
  );
}

const goHome = `  const goHome = () => {
    setScreenHistory([]);
    setScreen('home');
  };`;
if (ui.includes(goHome)) {
  ui = ui.replace(
    goHome,
    `  const goHome = () => {
    setScreenHistory([]);
    if (embedded && onExit) {
      onExit();
      return;
    }
    setScreen('home');
  };`,
  );
}

ui = ui.replace(
  /const C = \{[\s\S]*?\n\};/,
  `const C = {
  bg: '#06111B',
  panel: 'rgba(13,34,50,0.96)',
  panel2: 'rgba(16,42,61,0.96)',
  border: '#21435B',
  blue: '#35A7FF',
  blueSoft: '#78C8FF',
  white: '#F5FAFE',
  muted: '#91A6B6',
  green: '#3DDA7A',
  red: '#F26470',
  orange: '#FFC36F',
};`,
);

const styleReplacements = new Map([
  ['root', "flex: 1, backgroundColor: C.bg"],
  ['content', "paddingHorizontal: 14, paddingTop: 12, paddingBottom: 88, gap: 11"],
  ['card', "backgroundColor: C.panel, borderWidth: 1, borderColor: C.border, borderRadius: 16, padding: 14"],
  ['statCard', "backgroundColor: C.panel, borderWidth: 1, borderColor: C.border, borderRadius: 16, padding: 16"],
  ['menuTile', "minHeight: 78, flexDirection: 'row', alignItems: 'center', backgroundColor: C.panel, borderWidth: 1, borderColor: C.border, borderRadius: 16, padding: 14"],
  ['editorCard', "backgroundColor: 'rgba(13,34,50,0.98)', borderWidth: 1, borderColor: '#2D7FBA', borderRadius: 18, padding: 15"],
  ['input', "minHeight: 48, backgroundColor: '#0A1824', borderWidth: 1, borderColor: '#29455C', borderRadius: 12, paddingHorizontal: 13, color: C.white, fontSize: 16"],
]);

for (const [name, body] of styleReplacements) {
  const re = new RegExp(`  ${name}: \\{[^\\n]*\\},`);
  if (re.test(ui)) ui = ui.replace(re, `  ${name}: { ${body} },`);
}

fs.writeFileSync(uiPath, ui);
console.log('AJPA UI Lab: navegación funcional integrada con la estética nueva.');
