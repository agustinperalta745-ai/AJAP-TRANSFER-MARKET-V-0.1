import fs from 'node:fs';

const uiPath = new URL('../src/BotParityAppV2.tsx', import.meta.url);
let ui = fs.readFileSync(uiPath, 'utf8');

function mustReplace(search, replacement, label) {
  if (!ui.includes(search)) throw new Error(`AJPA redesign shell: no encontré ${label}`);
  ui = ui.replace(search, replacement);
}

if (!/^export type Screen =/m.test(ui)) {
  ui = ui.replace(/^type Screen =/m, 'export type Screen =');
}

const signatureRe = /export default function BotParityAppV2\([^)]*\)\s*\{/;
if (!signatureRe.test(ui)) throw new Error('AJPA redesign shell: no encontré firma del componente');
ui = ui.replace(
  signatureRe,
  `export type BotParityAppV2Props = {
  initialScreen?: Screen;
  embedded?: boolean;
  onExit?: () => void;
};

export default function BotParityAppV2({
  initialScreen = 'home',
  embedded = false,
  onExit,
}: BotParityAppV2Props) {`,
);

mustReplace(
  "  const [screen, setScreen] = useState<Screen>('home');",
  "  const [screen, setScreen] = useState<Screen>(initialScreen);",
  'pantalla inicial',
);

if (ui.includes('<SeasonCountdownBanner />')) {
  ui = ui.replace('<SeasonCountdownBanner />', '{embedded ? null : <SeasonCountdownBanner />}');
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
