import fs from 'node:fs';

const generatedDir = 'assets/generated';
fs.mkdirSync(generatedDir, { recursive: true });

const names = ['hero', 'mercado', 'liga', 'vitrina', 'copa'];
for (const name of names) {
  const source = `assets/broadcast-reference/${name}.b64`;
  const target = `${generatedDir}/broadcast-${name}.webp`;
  const base64 = fs.readFileSync(source, 'utf8').trim();
  const bytes = Buffer.from(base64, 'base64');
  if (bytes.subarray(0, 4).toString('ascii') !== 'RIFF' || bytes.subarray(8, 12).toString('ascii') !== 'WEBP') {
    throw new Error(`AJPA exact assets: ${name} inválido`);
  }
  fs.writeFileSync(target, bytes);
}

fs.writeFileSync('src/broadcast_reference_assets.ts', [
  "export const REF_HERO = require('../assets/generated/broadcast-hero.webp');",
  "export const REF_MERCADO = require('../assets/generated/broadcast-mercado.webp');",
  "export const REF_LIGA = require('../assets/generated/broadcast-liga.webp');",
  "export const REF_VITRINA = require('../assets/generated/broadcast-vitrina.webp');",
  "export const REF_COPA = require('../assets/generated/broadcast-copa.webp');",
  '',
].join('\n'));

const uiFile = 'src/BotParityAppV2.tsx';
let ui = fs.readFileSync(uiFile, 'utf8');

const importAnchor = "import { BG_LIGA } from './bg_liga';";
const refImport = "import { REF_HERO, REF_MERCADO, REF_LIGA, REF_VITRINA, REF_COPA } from './broadcast_reference_assets';";
if (!ui.includes(refImport)) {
  if (!ui.includes(importAnchor)) throw new Error('AJPA exact assets: import BG_LIGA no encontrado');
  ui = ui.replace(importAnchor, `${importAnchor}\n${refImport}`);
}

function replaceFunction(startMarker, endMarker, replacement, label) {
  const start = ui.indexOf(startMarker);
  const end = ui.indexOf(endMarker, start + startMarker.length);
  if (start < 0 || end < 0) throw new Error(`AJPA exact assets: no pude aislar ${label}`);
  ui = ui.slice(0, start) + replacement + '\n\n' + ui.slice(end);
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
  const key = title.toLowerCase();
  const art = key === 'mercado' ? REF_MERCADO
    : key === 'liga' ? REF_LIGA
    : key.includes('vitrina') ? REF_VITRINA
    : key === 'copa' ? REF_COPA
    : null;

  if (art) {
    return (
      <Pressable onPress={onPress} style={({ pressed }) => [s.featureTileReference, pressed && { opacity: 0.84 }]}>
        <ImageBackground source={art} style={s.featureReferenceImage} imageStyle={s.featureReferenceAsset} resizeMode="cover" />
      </Pressable>
    );
  }

  return (
    <Pressable onPress={onPress} style={({ pressed }) => [s.featureTile, danger && s.featureTileDanger, pressed && { opacity: 0.82 }]}>
      <View style={[s.featureIconWrap, danger && s.featureIconDanger]}><Text style={s.featureEmoji}>{emoji}</Text></View>
      <View style={s.featureTextWrap}>
        <Text style={[s.featureTitle, danger && { color: C.red }]}>{title}</Text>
        {subtitle ? <Text style={s.featureSubtitle}>{subtitle}</Text> : null}
      </View>
      <Text style={[s.featureArrowText, danger && { color: C.red }]}>›</Text>
    </Pressable>
  );
}`;
replaceFunction('function FeatureTile({', 'function QuickAction({', featureTile, 'FeatureTile');

const referenceHero = String.raw`function ReferenceHomeHero() {
  return (
    <View style={s.referenceHero}>
      <ImageBackground source={REF_HERO} style={s.referenceHeroImage} imageStyle={s.referenceHeroAsset} resizeMode="cover" />
    </View>
  );
}`;

const marker = 'function RadioPasilloStrip(';
if (!ui.includes('function ReferenceHomeHero()')) {
  if (!ui.includes(marker)) throw new Error('AJPA exact assets: RadioPasilloStrip no encontrado');
  ui = ui.replace(marker, referenceHero + '\n\n' + marker);
}

const homeStart = ui.indexOf('  const home = (');
const homeEnd = ui.indexOf('  const clubMenu = (', homeStart);
if (homeStart < 0 || homeEnd < 0) throw new Error('AJPA exact assets: no pude aislar Inicio');
let home = ui.slice(homeStart, homeEnd);
const heroStart = home.indexOf('      <HeroClubCard');
if (heroStart >= 0) {
  const heroEnd = home.indexOf('/>', heroStart);
  if (heroEnd < 0) throw new Error('AJPA exact assets: HeroClubCard sin cierre');
  home = home.slice(0, heroStart) + '      <ReferenceHomeHero />' + home.slice(heroEnd + 2);
}
ui = ui.slice(0, homeStart) + home + ui.slice(homeEnd);

const styleClose = '\n});';
const stylePos = ui.lastIndexOf(styleClose);
if (stylePos < 0) throw new Error('AJPA exact assets: cierre de estilos no encontrado');

const extras = [];
if (!ui.includes('  referenceHero: {')) {
  extras.push("  referenceHero: { width: '100%', aspectRatio: 4.32258, borderRadius: 13, overflow: 'hidden', borderWidth: 1, borderColor: 'rgba(51,157,229,0.72)', backgroundColor: '#06101a' },");
  extras.push("  referenceHeroImage: { flex: 1, width: '100%', height: '100%' },");
  extras.push("  referenceHeroAsset: { opacity: 1, borderRadius: 13 },");
}
if (!ui.includes('  featureTileReference: {')) {
  extras.push("  featureTileReference: { width: '49%', aspectRatio: 2.14835, borderRadius: 12, overflow: 'hidden', backgroundColor: '#06101a' },");
  extras.push("  featureReferenceImage: { flex: 1, width: '100%', height: '100%' },");
  extras.push("  featureReferenceAsset: { opacity: 1, borderRadius: 12 },");
}
if (extras.length) ui = ui.slice(0, stylePos) + '\n' + extras.join('\n') + '\n' + ui.slice(stylePos);

if (!ui.includes('<ReferenceHomeHero />')) throw new Error('AJPA exact assets: hero de referencia no quedó en Inicio');
if (!ui.includes('REF_MERCADO') || !ui.includes('featureTileReference')) throw new Error('AJPA exact assets: tarjetas de referencia no quedaron conectadas');
if (!ui.includes("openScreen('admin')") || !ui.includes('const adminMenu = (')) throw new Error('AJPA exact assets: Admin desapareció; cancelo publicación');

fs.writeFileSync(uiFile, ui);
console.log('AJPA exact assets: hero y cuatro tarjetas del Inicio conectados a la referencia aprobada, sin tocar pantallas internas ni Admin.');
