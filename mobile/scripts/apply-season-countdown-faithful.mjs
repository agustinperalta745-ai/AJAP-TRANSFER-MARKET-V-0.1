import fs from 'node:fs';

const file = new URL('../src/SeasonCountdownBanner.tsx', import.meta.url);
let src = fs.readFileSync(file, 'utf8');

// v1 already wraps the banner in ImageBackground. This pass only changes the
// source and proportions; it must not wrap the JSX a second time.
if (!src.includes("import { BG_INICIO } from './bg_inicio';")) {
  src = src.replace("import { apiRequest } from './api';", "import { apiRequest } from './api';\nimport { BG_INICIO } from './bg_inicio';");
}

src = src.replace(
  'source={REF_COUNTDOWN}',
  "source={typeof BG_INICIO === 'string' ? { uri: BG_INICIO } : BG_INICIO}",
);

src = src.replace(
  /  bannerShell: \{[\s\S]*?\n  \},\n  bannerImage: \{[^\n]*\},/,
  `  bannerShell: {\n    height: 94,\n    marginHorizontal: 20,\n    marginTop: 10,\n    marginBottom: 6,\n    borderRadius: 17,\n    overflow: 'hidden',\n    borderWidth: 1,\n    borderColor: 'rgba(58,166,239,0.68)',\n    backgroundColor: '#06121d',\n  },\n  bannerImage: { opacity: 0.60, borderRadius: 17 },`,
);

src = src.replace(`    minHeight: 88,`, `    minHeight: 94,`);
src = src.replace(`    paddingHorizontal: 18,`, `    paddingHorizontal: 20,`);
src = src.replace(`    paddingVertical: 13,`, `    paddingVertical: 8,`);
src = src.replace(`countValue: { color: '#f7fbff', fontSize: 22,`, `countValue: { color: '#f7fbff', fontSize: 20,`);
src = src.replace(`eyebrow: { color: '#7fbfff', fontSize: 9,`, `eyebrow: { color: '#76c2f7', fontSize: 8.5,`);
src = src.replace(`deadline: { color: '#879aaa', fontSize: 9,`, `deadline: { color: '#a2b3c1', fontSize: 8.5,`);
src = src.replace(`    minHeight: 52,`, `    minHeight: 46,`);
src = src.replace(`    minWidth: 92,`, `    minWidth: 104,`);
src = src.replace(`    borderRadius: 17,`, `    borderRadius: 13,`);
src = src.replace(`    backgroundColor: 'rgba(3,24,40,0.92)',`, `    backgroundColor: 'rgba(3,20,34,0.72)',`);
src = src.replace(`    borderColor: '#35aaff',`, `    borderColor: '#36a6f4',`);
src = src.replace(`editText: { color: '#58baff',`, `editText: { color: '#5fc2ff',`);

if (!src.includes('<ImageBackground')) throw new Error('AJPA countdown faithful: ImageBackground de v1 no encontrado');
if (!src.includes('height: 94')) throw new Error('AJPA countdown faithful: altura final no aplicada');

fs.writeFileSync(file, src);
console.log('AJPA countdown faithful: v1 reutilizado, estadio y proporción 94px aplicados sin doble wrapper.');
