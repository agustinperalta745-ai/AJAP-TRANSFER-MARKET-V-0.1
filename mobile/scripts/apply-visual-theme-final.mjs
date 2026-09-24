import fs from 'node:fs';

const uiPath = new URL('../src/BotParityAppV2.tsx', import.meta.url);
let ui = fs.readFileSync(uiPath, 'utf8');

const oldImport = "import VisualThemeEditor from './VisualTheme';";
const newImport = `import VisualThemeEditor, {
  useVisualTheme,
  visualButtonStyle,
  visualCardStyle,
  visualContentStyle,
  visualImageStyle,
  visualInputStyle,
  visualRootStyle,
  visualShadeStyle,
  visualTextStyle,
  visualTopBarStyle,
} from './VisualTheme';`;

if (ui.includes(oldImport)) {
  ui = ui.replace(oldImport, newImport);
} else if (!ui.includes('visualCardStyle')) {
  const marker = "import SeasonCountdownBanner from './SeasonCountdownBanner';";
  if (!ui.includes(marker)) throw new Error('AJPA visual theme: no encontré el punto de importación');
  ui = ui.replace(marker, marker + '\n' + newImport);
}

const mainMarker = 'export default function BotParityAppV2() {';
if (!ui.includes(mainMarker)) throw new Error('AJPA visual theme: no encontré BotParityAppV2');
if (!ui.includes('useVisualTheme();\n  const [screen')) {
  ui = ui.replace(
    mainMarker,
    mainMarker + '\n  // Subscribe the full screen tree to global visual-theme changes.\n  useVisualTheme();',
  );
}

function replaceAllLiteral(search, replacement) {
  if (search === replacement) return;
  ui = ui.split(search).join(replacement);
}

// Shared surfaces. These replacements are deliberately done after every legacy
// visual transform, so the editor always has the final say without disrupting
// the existing screen-building scripts.
replaceAllLiteral('contentContainerStyle={s.content}', 'contentContainerStyle={[s.content, visualContentStyle()]}');
replaceAllLiteral('style={s.card}', 'style={[s.card, visualCardStyle()]}');
replaceAllLiteral('style={s.statCard}', 'style={[s.statCard, visualCardStyle()]}');
replaceAllLiteral('style={s.summaryCard}', "style={[s.summaryCard, visualCardStyle('alt')]}");
replaceAllLiteral('style={s.honourCard}', "style={[s.honourCard, visualCardStyle('alt')]}");
replaceAllLiteral('style={s.editorCard}', "style={[s.editorCard, visualCardStyle('alt')]}");
replaceAllLiteral('style={s.budgetCard}', 'style={[s.budgetCard, visualCardStyle()]}');
replaceAllLiteral('style={s.homeStatusCard}', "style={[s.homeStatusCard, visualCardStyle('alt')]}");
replaceAllLiteral('style={s.profileHeroCard}', "style={[s.profileHeroCard, visualCardStyle('alt')]}");
replaceAllLiteral('style={s.adminRestrictedCard}', 'style={[s.adminRestrictedCard, visualCardStyle()]}');
replaceAllLiteral('style={s.input}', 'style={[s.input, visualInputStyle()]}');

replaceAllLiteral('style={[s.marketControlCard,', 'style={[s.marketControlCard, visualCardStyle(),');
replaceAllLiteral('style={[s.menuTile,', 'style={[s.menuTile, visualCardStyle(),');
replaceAllLiteral('style={[s.featureTile,', 'style={[s.featureTile, visualCardStyle(),');
replaceAllLiteral('style={[s.quickAction,', 'style={[s.quickAction, visualCardStyle(),');
replaceAllLiteral('style={[s.wideAction,', 'style={[s.wideAction, visualCardStyle(),');
replaceAllLiteral('style={[s.entryCard,', 'style={[s.entryCard, visualCardStyle(),');

// Button variants keep their semantic green/red/ghost behavior while editable
// radius/border/background rules override the legacy base.
replaceAllLiteral(
  '        disabled && s.disabled,\n        pressed && !disabled && { opacity: 0.72 },',
  '        visualButtonStyle(kind),\n        disabled && s.disabled,\n        pressed && !disabled && { opacity: 0.72 },',
);

// Typography tokens.
for (const name of ['screenTitle', 'playerName', 'infoValue', 'summaryValue', 'statValue', 'editorTitle', 'heroClubName', 'homeStatusValue', 'budgetValue']) {
  replaceAllLiteral(`style={s.${name}}`, `style={[s.${name}, visualTextStyle('text')]}`);
}
for (const name of ['muted', 'detail', 'menuSubtitle', 'featureSubtitle', 'wideSubtitle', 'entrySub', 'honourMeta', 'honourEmpty']) {
  replaceAllLiteral(`style={s.${name}}`, `style={[s.${name}, visualTextStyle('muted')]}`);
}
for (const name of ['eyebrow', 'brandSub']) {
  replaceAllLiteral(`style={s.${name}}`, `style={[s.${name}, visualTextStyle('accent')]}`);
}
for (const name of ['playerValue', 'infoLabel', 'listHeading', 'statLabel', 'inputLabel', 'summaryLabel', 'honoursHeading', 'honourLabel', 'topActionText', 'profileButtonText']) {
  replaceAllLiteral(`style={s.${name}}`, `style={[s.${name}, visualTextStyle('accentSoft')]}`);
}
replaceAllLiteral('style={s.brand}', "style={[s.brand, visualTextStyle('text')]}");
replaceAllLiteral('style={s.buttonText}', "style={[s.buttonText, visualTextStyle('text')]}");
replaceAllLiteral('style={[s.menuTitle,', "style={[s.menuTitle, visualTextStyle('text'),");
replaceAllLiteral('style={[s.featureTitle,', "style={[s.featureTitle, visualTextStyle('text'),");
replaceAllLiteral('style={[s.wideTitle,', "style={[s.wideTitle, visualTextStyle('text'),");
replaceAllLiteral('style={[s.entryTitle,', "style={[s.entryTitle, visualTextStyle('text'),");

// App chrome + backgrounds.
replaceAllLiteral('style={s.root}', 'style={[s.root, visualRootStyle()]}');
replaceAllLiteral('style={[s.root, s.center]}', 'style={[s.root, visualRootStyle(), s.center]}');
replaceAllLiteral('style={s.topBar}', 'style={[s.topBar, visualTopBarStyle()]}');
replaceAllLiteral('style={s.profileButton}', "style={[s.profileButton, visualButtonStyle('ghost')]}");
replaceAllLiteral('imageStyle={s.screenBackgroundImage}', 'imageStyle={[s.screenBackgroundImage, visualImageStyle()]}');
replaceAllLiteral('style={s.screenShade}', 'style={[s.screenShade, visualShadeStyle()]}');
replaceAllLiteral('style={[s.screenShade,', 'style={[s.screenShade, visualShadeStyle(),');

// The editor must survive all layout rewrites.
if (!ui.includes("screen === 'appearance'")) {
  throw new Error('AJPA visual theme: el editor de diseño desapareció durante los transforms');
}
if (!ui.includes("openScreen('appearance')")) {
  throw new Error('AJPA visual theme: falta el acceso al editor de diseño');
}

fs.writeFileSync(uiPath, ui);
console.log('AJPA visual theme final: tema editable aplicado sobre la UI final');
