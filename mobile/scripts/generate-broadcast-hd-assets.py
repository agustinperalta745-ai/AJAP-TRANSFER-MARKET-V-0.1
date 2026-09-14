from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter
import math, random

OUT = Path('assets/generated-broadcast')
OUT.mkdir(parents=True, exist_ok=True)


def gradient(size, top, bottom):
    w, h = size
    img = Image.new('RGB', size)
    d = ImageDraw.Draw(img)
    for y in range(h):
        t = y / max(1, h - 1)
        t = t * t * (3 - 2 * t)
        c = tuple(int(top[i] * (1 - t) + bottom[i] * t) for i in range(3))
        d.line((0, y, w, y), fill=c)
    return img.convert('RGBA')


def glow(img, x, y, radius, color, alpha=150, blur=40):
    layer = Image.new('RGBA', img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    d.ellipse((x-radius, y-radius, x+radius, y+radius), fill=(*color, alpha))
    img.alpha_composite(layer.filter(ImageFilter.GaussianBlur(blur)))


def stadium(size, seed=1, horizon=.63):
    random.seed(seed)
    w, h = size
    img = gradient(size, (4, 16, 29), (1, 4, 10))
    d = ImageDraw.Draw(img, 'RGBA')
    hy = int(h * horizon)
    d.polygon([(0, hy-140), (w, hy-100), (w, hy+160), (0, hy+210)], fill=(3, 18, 31, 255))
    for _ in range(max(450, int(w*h/4000))):
        x = random.randrange(w)
        y = random.randrange(max(0, hy-110), min(h, hy+120))
        a = random.randint(22, 75)
        c = random.choice([(70,130,180,a),(130,160,185,a),(30,90,140,a)])
        r = random.randint(1,3)
        d.ellipse((x-r,y-r,x+r,y+r), fill=c)
    d.polygon([(0, hy+150), (w, hy+120), (w,h), (0,h)], fill=(2,24,25,255))
    for lx in [int(w*.12), int(w*.36), int(w*.64), int(w*.88)]:
        glow(img, lx, int(h*.17), int(min(w,h)*.055), (110,195,255), 170, 36)
        for j in range(-3,4):
            glow(img, lx+j*15, int(h*.16), 5, (225,248,255), 220, 7)
    return img


def ball(img, center, radius, accent=(70,160,230)):
    cx, cy = center
    glow(img, cx, cy, radius, (25,100,180), 75, 85)
    s = Image.new('RGBA', (radius*2, radius*2), (0,0,0,0))
    sd = ImageDraw.Draw(s, 'RGBA')
    for r in range(radius, 0, -2):
        t = r / radius
        base = int(11 + 25 * (1-t))
        sd.ellipse((radius-r, radius-r, radius+r, radius+r), fill=(base,base+8,base+14,255))
    sd.ellipse((7,7,radius*2-7,radius*2-7), outline=(*accent,155), width=max(4,radius//36))
    pts=[]
    pr=radius*.22
    for i in range(5):
        a=-math.pi/2+i*2*math.pi/5
        pts.append((radius+pr*math.cos(a), radius+pr*math.sin(a)))
    sd.polygon(pts, fill=(7,11,18,255), outline=(70,95,120,170))
    for p in pts:
        ex=radius+(p[0]-radius)*3
        ey=radius+(p[1]-radius)*3
        sd.line((p[0],p[1],ex,ey), fill=(75,105,135,155), width=max(3,radius//45))
    img.alpha_composite(s, (cx-radius, cy-radius))


def save(img, name, quality=90):
    img.convert('RGB').save(OUT/name, 'JPEG', quality=quality, optimize=True, progressive=True)

# Hero 1920x1080: stadium + original ball artwork, no baked text.
img = stadium((1920,1080), 4, .62)
ball(img, (1430,560), 360, (65,170,255))
d = ImageDraw.Draw(img, 'RGBA')
d.polygon([(0,930),(780,720),(1120,1080),(0,1080)], fill=(0,55,90,78))
for x in range(0,900,180): d.line((x,900,x+450,770), fill=(70,170,235,30), width=6)
save(img, 'hero.jpg')

# Mercado 1600x1600: transfer arrows over stadium.
img = stadium((1600,1600), 7, .67)
d = ImageDraw.Draw(img, 'RGBA')
d.polygon([(260,610),(850,610),(850,460),(1180,790),(850,1120),(850,970),(260,970)], fill=(55,170,240,95))
d.polygon([(1340,1030),(750,1030),(750,1180),(420,850),(750,520),(750,670),(1340,670)], fill=(190,225,245,45))
glow(img,1200,350,220,(40,130,255),120,100)
save(img, 'market.jpg')

# Liga 1600x1600: illuminated competition plate.
img = stadium((1600,1600), 11, .58)
d = ImageDraw.Draw(img, 'RGBA')
glow(img,800,580,220,(40,135,240),120,100)
d.rounded_rectangle((565,330,1035,960), radius=130, fill=(0,18,34,95), outline=(90,185,255,115), width=7)
for y,wid in [(1020,460),(1110,620),(1200,780)]: d.rounded_rectangle((800-wid//2,y,800+wid//2,y+35), radius=18, fill=(80,160,220,60))
save(img, 'league.jpg')

# Vitrina 1600x1600: trophy artwork.
img = stadium((1600,1600), 21, .69)
spot = Image.new('RGBA', img.size, (0,0,0,0))
sd = ImageDraw.Draw(spot, 'RGBA')
sd.polygon([(520,0),(1080,0),(1000,1350),(600,1350)], fill=(90,150,210,38))
img.alpha_composite(spot.filter(ImageFilter.GaussianBlur(70)))
d = ImageDraw.Draw(img, 'RGBA')
gold=(200,165,90,235)
d.ellipse((570,330,1030,760), outline=gold, width=30)
d.rectangle((740,680,860,1110), fill=(125,108,75,225))
d.rounded_rectangle((540,1080,1060,1205), radius=45, fill=(90,80,65,235), outline=(215,180,110,185), width=8)
d.arc((380,400,700,880),60,300,fill=gold,width=28)
d.arc((900,400,1220,880),240,120,fill=gold,width=28)
glow(img,800,640,330,(190,155,85),70,130)
save(img, 'vitrina.jpg')

# Copa 1600x1600: faceted ball under blue lights.
img = stadium((1600,1600), 31, .68)
ball(img, (800,700), 430, (50,125,255))
d = ImageDraw.Draw(img, 'RGBA')
for ang in range(0,360,45):
    x2=800+math.cos(math.radians(ang))*500; y2=700+math.sin(math.radians(ang))*500
    d.line((800,700,x2,y2), fill=(80,150,255,20), width=5)
save(img, 'cup.jpg')

# Results 1920x700: broadcast scoreboard.
img = stadium((1920,700), 44, .66)
d = ImageDraw.Draw(img, 'RGBA')
d.rounded_rectangle((620,120,1300,520), radius=45, fill=(2,14,26,190), outline=(70,160,225,120), width=5)
d.rounded_rectangle((700,200,900,440), radius=25, fill=(10,35,55,185))
d.rounded_rectangle((1020,200,1220,440), radius=25, fill=(10,35,55,185))
glow(img,960,150,130,(60,170,255),95,80)
save(img, 'results.jpg')

# Countdown 1920x600: stadium tunnel, safe for live text overlay.
img = stadium((1920,600), 55, .58)
d = ImageDraw.Draw(img, 'RGBA')
d.polygon([(0,0),(520,0),(780,600),(0,600)], fill=(0,7,14,185))
d.polygon([(1920,0),(1400,0),(1140,600),(1920,600)], fill=(0,7,14,185))
glow(img,960,240,180,(70,170,255),100,100)
save(img, 'countdown.jpg')

print('AJPA broadcast HD assets generated:', ', '.join(sorted(p.name for p in OUT.glob('*.jpg'))))
