import fs from 'node:fs';
import { execFileSync } from 'node:child_process';

// Los PNG históricos de algunos clubes contienen chunks/perfiles que AAPT2
// rechaza aunque Metro pueda leerlos. Los regrabamos como RGBA estándar antes
// del prebuild. Así preservamos los escudos reales en vez de caer al 🛡️.
execFileSync('python', ['-m', 'pip', 'install', '--quiet', 'Pillow'], { stdio: 'inherit' });
const sanitizer = String.raw`
from pathlib import Path
from PIL import Image, ImageDraw, ImageFile, UnidentifiedImageError

# Algunos PNG viejos (p. ej. Benfica/Lazio/Tottenham) están truncados pero
# conservan suficientes datos para reconstruirse. Pillow los abre en modo
# tolerante y luego los volvemos a guardar como PNG RGBA limpio para AAPT2.
ImageFile.LOAD_TRUNCATED_IMAGES = True

root = Path('assets/teams')
if not root.exists():
    raise SystemExit('Team badges: no existe assets/teams')

files = sorted(root.glob('*.png'))
if not files:
    raise SystemExit('Team badges: no hay PNG para sanear')

sanitized = 0
for path in files:
    # Este archivo histórico de Mónaco está roto y ya no se usa. La app toma
    # assets/team_badge_test/as_monaco_hd.png, reconstruido y validado después.
    if path.stem == 'as_monaco':
        print('Badge obsoleto omitido: as_monaco.png (se usa Monaco HD)')
        continue

    try:
        with Image.open(path) as src:
            src.load()
            img = src.convert('RGBA')
    except (UnidentifiedImageError, OSError) as exc:
        raise SystemExit(f'Team badge imposible de recuperar: {path.name}: {exc}') from exc

    # Ajax necesita conservar su campo blanco: en la tarjeta oscura el PNG
    # transparente hacía desaparecer esa parte del escudo.
    if path.stem == 'ajax':
        w, h = img.size
        base = Image.new('RGBA', (w, h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(base)
        inset = max(1, int(min(w, h) * 0.035))
        draw.ellipse((inset, inset, w - inset - 1, h - inset - 1), fill=(255, 255, 255, 255))
        base.alpha_composite(img)
        img = base

    # Guardado limpio, sin perfiles ICC ni metadatos problemáticos.
    img.save(path, format='PNG', optimize=False, compress_level=6)
    with Image.open(path) as check:
        check.verify()
    sanitized += 1
    print(f'Badge saneado: {path.name} | {img.size[0]}x{img.size[1]} RGBA')

print(f'Escudos saneados: {sanitized}')
`;
execFileSync('python', ['-c', sanitizer], { stdio: 'inherit' });

const uiPath = 'src/BotParityAppV2.tsx';
let ui = fs.readFileSync(uiPath, 'utf8');

// La pantalla Perfiles de equipo se genera en un paso previo. Ese generador
// todavía dejaba el emoji genérico 🛡️; acá lo sustituimos por ClubBadge sin
// tocar las tarjetas, textos, fondos ni la lógica de navegación.
if (!ui.includes("import { ClubBadge } from './teamBadges';") && !ui.includes("import { ClubBadge, ClubMatchup } from './teamBadges';")) {
  const anchor = "import { BG_PERFIL } from './bg_perfil';";
  if (!ui.includes(anchor)) throw new Error('Profile badges: no encontré import BG_PERFIL');
  ui = ui.replace(anchor, `${anchor}\nimport { ClubBadge } from './teamBadges';`);
}

const listOld = `            <View style={s.heroIconWrap}><Text style={s.heroIcon}>🛡️</Text></View>\n            <View style={s.flex}>\n              <Text style={s.playerName}>{club.club}</Text>`;
const listNew = `            <View style={s.heroIconWrap}><ClubBadge club={club.club} size={74} /></View>\n            <View style={s.flex}>\n              <Text style={s.playerName}>{club.club}</Text>`;
if (ui.includes(listOld)) ui = ui.replace(listOld, listNew);

const profileOld = `      <View style={s.heroClubCard}>\n        <View style={s.heroIconWrap}><Text style={s.heroIcon}>🛡️</Text></View>\n        <View style={s.flex}>\n          <Text style={s.heroClubName}>{selectedClubProfile.club}</Text>`;
const profileNew = `      <View style={s.heroClubCard}>\n        <View style={s.heroIconWrap}><ClubBadge club={selectedClubProfile.club} size={78} /></View>\n        <View style={s.flex}>\n          <Text style={s.heroClubName}>{selectedClubProfile.club}</Text>`;
if (ui.includes(profileOld)) ui = ui.replace(profileOld, profileNew);

if (!ui.includes('<ClubBadge club={club.club} size={74} />')) {
  throw new Error('Profile badges: la lista de clubes no quedó conectada a los escudos reales');
}
if (!ui.includes('<ClubBadge club={selectedClubProfile.club} size={78} />')) {
  throw new Error('Profile badges: el perfil individual no quedó conectado al escudo real');
}

fs.writeFileSync(uiPath, ui);
console.log('Perfiles de equipo: escudos reales restaurados + PNGs compatibles con Android.');
