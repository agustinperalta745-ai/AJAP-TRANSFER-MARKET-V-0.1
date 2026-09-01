import fs from 'node:fs';
import path from 'node:path';
import { execFileSync } from 'node:child_process';

// IMPORTANTE: no volver a regrabar assets/teams/*.png. Varios de esos PNG son
// miniaturas históricas (48/64 px) y el saneado masivo fue lo que degradó la
// calidad visual. Reconstruimos los escudos desde la lámina HQ original y
// generamos copias limpias de 512 px exclusivamente para el bundle Android.
const chunksDir = 'assets/badges_sprite_chunks';
const chunks = fs.readdirSync(chunksDir)
  .filter((name) => name.endsWith('.txt'))
  .sort()
  .map((name) => fs.readFileSync(path.join(chunksDir, name), 'utf8').replace(/\s+/g, ''));
if (!chunks.length) throw new Error('Team badges HQ: no encontré badges_sprite_chunks');
const sheet = Buffer.from(chunks.join(''), 'base64');
if (sheet[0] !== 0xff || sheet[1] !== 0xd8) throw new Error('Team badges HQ: la lámina no es JPEG');
fs.writeFileSync('assets/team_badges_hq_source.jpg', sheet);

execFileSync('python', ['-m', 'pip', 'install', '--quiet', 'Pillow'], { stdio: 'inherit' });
const generator = String.raw`
from pathlib import Path
from collections import deque
from PIL import Image, ImageDraw, ImageFilter, ImageFile

ImageFile.LOAD_TRUNCATED_IMAGES = True
source = Image.open('assets/team_badges_hq_source.jpg').convert('RGB')
if source.size != (900, 1040):
    raise SystemExit(f'Team badges HQ: tamaño inesperado de lámina: {source.size}')

out_dir = Path('assets/team_badge_hq')
out_dir.mkdir(parents=True, exist_ok=True)

# La lámina original tiene celdas de 180x180 y separadores de 28 px.
# Mónaco y Atlético no salen de acá: usan sus fuentes HD dedicadas.
cells = {
    'olympique_marseille': (0, 0),
    'west_ham_united': (1, 0),
    'everton': (2, 0),
    'lazio': (3, 0),
    'real_betis': (4, 0),
    'psg': (0, 1),
    'aston_villa': (1, 1),
    'middlesbrough': (2, 1),
    'olympique_lyon': (3, 1),
    'fiorentina': (4, 1),
    'villarreal': (0, 2),
    'sevilla': (1, 2),
    'porto': (2, 2),
    'fulham': (4, 2),
    'ajax': (0, 3),
    'galatasaray': (2, 3),
    'bolton_wanderers': (3, 3),
    'manchester_city': (4, 3),
    'benfica': (0, 4),
    'feyenoord': (1, 4),
    'tottenham_hotspur': (2, 4),
}

def transparent_background(crop):
    rgba = crop.convert('RGBA')
    w, h = rgba.size
    px = rgba.load()
    # El fondo de la lámina es gris muy claro. Sólo quitamos píxeles claros y
    # neutros conectados al borde; el blanco interno de los escudos se conserva.
    seen = bytearray(w * h)
    q = deque()
    def bg(x, y):
        r, g, b, a = px[x, y]
        return a > 0 and min(r, g, b) >= 218 and (max(r, g, b) - min(r, g, b)) <= 22
    for x in range(w):
        for y in (0, h - 1):
            idx = y * w + x
            if not seen[idx] and bg(x, y):
                seen[idx] = 1; q.append((x, y))
    for y in range(h):
        for x in (0, w - 1):
            idx = y * w + x
            if not seen[idx] and bg(x, y):
                seen[idx] = 1; q.append((x, y))
    while q:
        x, y = q.popleft()
        for nx, ny in ((x-1,y),(x+1,y),(x,y-1),(x,y+1)):
            if 0 <= nx < w and 0 <= ny < h:
                idx = ny * w + nx
                if not seen[idx] and bg(nx, ny):
                    seen[idx] = 1; q.append((nx, ny))
    for y in range(h):
        off = y * w
        for x in range(w):
            if seen[off + x]:
                r, g, b, _ = px[x, y]
                px[x, y] = (r, g, b, 0)
    return rgba

def fit_512(img, ajax=False):
    alpha = img.getchannel('A')
    bbox = alpha.getbbox()
    if not bbox:
        raise SystemExit('Team badges HQ: escudo vacío')
    img = img.crop(bbox)
    # Ajax: recuperamos el campo blanco que se perdía contra la tarjeta oscura.
    # El logo y sus estrellas quedan arriba de un disco blanco, sin tocar otros clubes.
    if ajax:
        side = max(img.width, img.height)
        pad = max(8, int(side * 0.08))
        base = Image.new('RGBA', (side + pad*2, side + pad*2), (0,0,0,0))
        draw = ImageDraw.Draw(base)
        draw.ellipse((pad, pad, side + pad - 1, side + pad - 1), fill=(255,255,255,255))
        base.alpha_composite(img, ((base.width-img.width)//2, (base.height-img.height)//2))
        img = base
    pad = max(8, int(max(img.size) * 0.08))
    canvas = Image.new('RGBA', (img.width + pad*2, img.height + pad*2), (0,0,0,0))
    canvas.alpha_composite(img, (pad, pad))
    canvas.thumbnail((480, 480), Image.Resampling.LANCZOS)
    # Escalado final desde la fuente ~180 px, con un enfoque mínimo para evitar
    # el aspecto borroso de las miniaturas 48/64 px anteriores.
    if max(canvas.size) < 480:
        scale = min(480 / canvas.width, 480 / canvas.height)
        canvas = canvas.resize((max(1, round(canvas.width*scale)), max(1, round(canvas.height*scale))), Image.Resampling.LANCZOS)
    canvas = canvas.filter(ImageFilter.UnsharpMask(radius=0.7, percent=105, threshold=2))
    out = Image.new('RGBA', (512, 512), (0,0,0,0))
    out.alpha_composite(canvas, ((512-canvas.width)//2, (512-canvas.height)//2))
    return out

for name, (col, row) in cells.items():
    x0 = col * 180
    y0 = row * 208
    crop = source.crop((x0, y0, x0 + 180, y0 + 180))
    badge = fit_512(transparent_background(crop), ajax=(name == 'ajax'))
    dst = out_dir / f'{name}.png'
    badge.save(dst, format='PNG', optimize=True)
    with Image.open(dst) as check:
        check.verify()
    print(f'Badge HQ: {name} -> 512x512')

# Torino y Zaragoza no están en la lámina. Conservamos su fuente original,
# pero sólo estos dos se copian a un PNG 512 válido; jamás se tocan los originales.
for name in ('torino', 'zaragoza'):
    src = Path('assets/teams') / f'{name}.png'
    with Image.open(src) as im:
        im.load()
        rgba = im.convert('RGBA')
    if not rgba.getchannel('A').getbbox():
        raise SystemExit(f'Team badges HQ: {name} quedó vacío')
    rgba.thumbnail((460, 460), Image.Resampling.LANCZOS)
    if max(rgba.size) < 460:
        scale = min(460/rgba.width, 460/rgba.height)
        rgba = rgba.resize((max(1, round(rgba.width*scale)), max(1, round(rgba.height*scale))), Image.Resampling.LANCZOS)
    out = Image.new('RGBA', (512, 512), (0,0,0,0))
    out.alpha_composite(rgba, ((512-rgba.width)//2, (512-rgba.height)//2))
    dst = out_dir / f'{name}.png'
    out.save(dst, format='PNG', optimize=True)
    with Image.open(dst) as check:
        check.verify()
    print(f'Badge HQ: {name} -> 512x512 (fuente histórica preservada)')

expected = set(cells) | {'torino', 'zaragoza'}
produced = {p.stem for p in out_dir.glob('*.png')}
missing = expected - produced
if missing:
    raise SystemExit('Team badges HQ: faltan ' + ', '.join(sorted(missing)))
print(f'Team badges HQ generados: {len(expected)}; originales intactos.')
`;
execFileSync('python', ['-c', generator], { stdio: 'inherit' });

const uiPath = 'src/BotParityAppV2.tsx';
let ui = fs.readFileSync(uiPath, 'utf8');

// La pantalla Perfiles de equipo se genera en un paso previo. Sustituimos sólo
// el placeholder por ClubBadge; no modificamos tarjetas, fondos, estilos ni layout.
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
  throw new Error('Profile badges: la lista de clubes no quedó conectada a ClubBadge');
}
if (!ui.includes('<ClubBadge club={selectedClubProfile.club} size={78} />')) {
  throw new Error('Profile badges: el perfil individual no quedó conectado a ClubBadge');
}

fs.writeFileSync(uiPath, ui);
console.log('Perfiles de equipo: fuente HQ restaurada; sin recomprimir los escudos originales.');
