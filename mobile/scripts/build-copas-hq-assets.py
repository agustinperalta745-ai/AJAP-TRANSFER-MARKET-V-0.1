from __future__ import annotations

import base64
import io
from pathlib import Path

from PIL import Image, ImageEnhance, ImageFilter, ImageOps, ImageFile

ImageFile.LOAD_TRUNCATED_IMAGES = True

ROOT = Path(__file__).resolve().parents[1]
TROPHIES = ROOT / "assets" / "trophies"
OUT = ROOT / "assets" / "copas"
OUT.mkdir(parents=True, exist_ok=True)


def read_chunked(paths: list[Path]) -> Image.Image:
    raw = "".join(p.read_text(encoding="utf-8").strip() for p in paths)
    raw = "".join(raw.split())
    raw += "=" * ((4 - len(raw) % 4) % 4)
    data = base64.b64decode(raw)
    image = Image.open(io.BytesIO(data)).convert("RGB")
    image.load()
    return image


def soften_background(source: Image.Image, size: tuple[int, int], tint=(4, 18, 31), blur=13) -> Image.Image:
    bg = ImageOps.fit(source, size, method=Image.Resampling.LANCZOS)
    bg = bg.filter(ImageFilter.GaussianBlur(blur))
    bg = ImageEnhance.Contrast(bg).enhance(1.08)
    overlay = Image.new("RGB", size, tint)
    return Image.blend(bg, overlay, 0.50)


def crop_trophy(source: Image.Image, fraction: float) -> Image.Image:
    w, h = source.size
    crop = source.crop((0, 0, max(1, int(w * fraction)), h)).convert("RGBA")
    crop = ImageEnhance.Sharpness(crop).enhance(1.8)
    crop = ImageEnhance.Contrast(crop).enhance(1.08)
    return crop


def edge_mask(size: tuple[int, int], fade=52) -> Image.Image:
    w, h = size
    mask = Image.new("L", (w, h), 255)
    px = mask.load()
    for x in range(w):
        edge = min(x, w - 1 - x)
        a = 255 if edge >= fade else int(255 * edge / max(1, fade))
        for y in range(h):
            px[x, y] = a
    return mask


def paste_trophy(canvas: Image.Image, trophy: Image.Image, box: tuple[int, int, int, int]) -> None:
    x, y, w, h = box
    item = ImageOps.contain(trophy, (w, h), method=Image.Resampling.LANCZOS)
    mask = edge_mask(item.size, max(18, item.size[0] // 10))
    alpha = item.getchannel("A")
    alpha = ImageChops.multiply(alpha, mask)
    item.putalpha(alpha)
    canvas.paste(item, (x + (w-item.width)//2, y + (h-item.height)//2), item)


# local import kept after function definitions so the script still fails clearly if Pillow is incomplete.
from PIL import ImageChops

liga = read_chunked([
    TROPHIES / "liga_banner_chunks" / "00.txt",
    TROPHIES / "liga_banner_chunks" / "01.txt",
    TROPHIES / "liga_banner_chunks" / "02.txt",
])
champions = read_chunked([
    TROPHIES / "champions_banner_chunks" / "00.txt",
    TROPHIES / "champions_banner_chunks" / "01.txt",
    TROPHIES / "champions_banner_chunks" / "02.txt",
    TROPHIES / "champions_banner_chunks" / "03.txt",
])
europa = read_chunked([
    TROPHIES / "europa_banner_small_chunks" / "b00.txt",
    TROPHIES / "europa_banner_small_chunks" / "b01.txt",
    TROPHIES / "europa_banner_small_chunks" / "b02.txt",
])

liga_trophy = crop_trophy(liga, 0.38)
champ_trophy = crop_trophy(champions, 0.36)
europa_trophy = crop_trophy(europa, 0.36)


def save_jpg(image: Image.Image, name: str, quality=93) -> None:
    image = image.convert("RGB")
    image.save(OUT / name, "JPEG", quality=quality, optimize=True, progressive=True, subsampling=0)


# Main hero: dark blue stadium ambience, Liga AJPA trophy on the right and clean left area for UI copy.
hero = soften_background(liga, (1600, 540), tint=(2, 18, 31), blur=18).convert("RGBA")
left_dark = Image.new("RGBA", hero.size, (2, 16, 28, 0))
grad = Image.new("L", hero.size, 0)
gp = grad.load()
for x in range(hero.width):
    a = int(205 * max(0, 1 - x / (hero.width * 0.72)))
    for y in range(hero.height):
        gp[x, y] = a
left_dark.putalpha(grad)
hero = Image.alpha_composite(hero, left_dark)
paste_trophy(hero, liga_trophy, (1010, 28, 520, 500))
save_jpg(hero, "copas-hero.jpg", 94)

# Competition cards: portrait, trophy central/bottom, strong blue/gold ambience.
def competition_card(source: Image.Image, trophy: Image.Image, tint, name: str) -> None:
    card = soften_background(source, (900, 1120), tint=tint, blur=16).convert("RGBA")
    top = Image.new("RGBA", card.size, (3, 12, 22, 70))
    card = Image.alpha_composite(card, top)
    paste_trophy(card, trophy, (65, 210, 770, 860))
    save_jpg(card, name, 94)

competition_card(champions, champ_trophy, (2, 23, 48), "copas-champions.jpg")
competition_card(europa, europa_trophy, (42, 24, 7), "copas-europa.jpg")

# Ranking: warm gold trophy crop on right, clean dark left.
ranking = soften_background(liga, (1500, 430), tint=(13, 18, 27), blur=20).convert("RGBA")
paste_trophy(ranking, liga_trophy, (1010, -35, 440, 500))
ranking = ImageEnhance.Contrast(ranking.convert("RGB")).enhance(1.07).convert("RGBA")
save_jpg(ranking, "copas-ranking.jpg", 93)

# Trophy cabinet: three official AJPA cups in a blue glass-like ambience.
vitrina = soften_background(champions, (1500, 430), tint=(2, 19, 34), blur=20).convert("RGBA")
paste_trophy(vitrina, liga_trophy, (780, 18, 250, 385))
paste_trophy(vitrina, champ_trophy, (1010, 10, 250, 400))
paste_trophy(vitrina, europa_trophy, (1240, 18, 230, 385))
save_jpg(vitrina, "copas-vitrina.jpg", 93)

# History: wide, dark stadium background without a foreground trophy.
history = soften_background(champions, (1500, 430), tint=(2, 20, 36), blur=9)
history = ImageEnhance.Contrast(history).enhance(1.12)
history = ImageEnhance.Sharpness(history).enhance(1.18)
save_jpg(history, "copas-historial.jpg", 93)

for path in sorted(OUT.glob("copas-*.jpg")):
    print(path.name, path.stat().st_size)
