"""앱 아이콘(1024): 굽은 산책길 + 가로등 불빛 + 안심 방패 핀. make_assets.py가 불러 쓴다."""
import math
from PIL import Image, ImageDraw, ImageFilter

S = 4096
TOP = (37, 99, 235)      # 밝은 파랑
BOT = (30, 58, 138)      # 남색
WHITE = (255, 255, 255)
ROAD = (191, 219, 254)
LAMP = (253, 224, 71)
BLUE = (29, 78, 216)


def bezier(p0, p1, p2, p3, n=400):
    pts = []
    for i in range(n + 1):
        t = i / n
        a = (1 - t) ** 3; b = 3 * (1 - t) ** 2 * t; c = 3 * (1 - t) * t * t; d = t ** 3
        pts.append((a * p0[0] + b * p1[0] + c * p2[0] + d * p3[0], a * p0[1] + b * p1[1] + c * p2[1] + d * p3[1]))
    return pts


def thick(draw, pts, w, fill):
    r = w / 2
    for x, y in pts:
        draw.ellipse([x - r, y - r, x + r, y + r], fill=fill)


def make(out):
    # 대각 그라데이션 배경
    g = Image.new("RGB", (2, 2))
    g.putpixel((0, 0), TOP); g.putpixel((1, 0), TOP); g.putpixel((0, 1), BOT); g.putpixel((1, 1), BOT)
    im = g.resize((S, S), Image.BILINEAR).convert("RGBA")

    # 길: 아래 왼쪽에서 올라와 핀까지 이어지는 S자
    path = bezier((900, 4400), (700, 3200), (3100, 3350), (2700, 2550), 1500)
    path += bezier((2700, 2550), (2450, 2100), (2048, 2250), (2048, 2000), 600)[1:]
    layer = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    thick(d, path, 560, ROAD + (255,))
    # 가운데 점선
    acc = 0
    for (x0, y0), (x1, y1) in zip(path, path[1:]):
        seg = math.hypot(x1 - x0, y1 - y0)
        if (acc // 190) % 2 == 0:
            d.ellipse([x0 - 42, y0 - 42, x0 + 42, y0 + 42], fill=WHITE + (255,))
        acc += seg
    im.alpha_composite(layer)

    # 가로등 불빛 3개 (길 옆)
    glow = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    gd = ImageDraw.Draw(glow)
    lamps = [(520, 3300), (3250, 3150), (1450, 2700)]
    for x, y in lamps:
        gd.ellipse([x - 330, y - 330, x + 330, y + 330], fill=LAMP + (120,))
    glow = glow.filter(ImageFilter.GaussianBlur(120))
    im.alpha_composite(glow)
    d = ImageDraw.Draw(im)
    for x, y in lamps:
        d.ellipse([x - 120, y - 120, x + 120, y + 120], fill=LAMP + (255,))

    # 핀 그림자
    cx, cy, r = 2048, 1250, 820
    sh = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    sd = ImageDraw.Draw(sh)
    sd.ellipse([cx - 380, 2220, cx + 380, 2380], fill=(0, 0, 40, 110))
    im.alpha_composite(sh.filter(ImageFilter.GaussianBlur(60)))

    # 지도 핀(원 + 뾰족한 끝)
    d = ImageDraw.Draw(im)
    tip = (cx, 2300)
    dist = tip[1] - cy
    ang = math.asin(r / dist)
    a = math.pi / 2 - ang  # tangent point angle from vertical
    left = (cx - r * math.sin(math.pi/2 - a) , cy + r * math.cos(math.pi/2 - a))
    right = (cx + r * math.sin(math.pi/2 - a), cy + r * math.cos(math.pi/2 - a))
    d.polygon([left, right, tip], fill=WHITE)
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=WHITE)

    # 핀 안의 방패 + 체크
    k = 2.35
    P = lambda pts: [(cx + (x - 256) * k, cy - 40 + (y - 256) * k) for x, y in pts]
    d.polygon(P([(96, 110), (256, 62), (416, 110), (416, 270), (256, 440), (96, 270)]), fill=BLUE)
    w = 34 * k
    pts = P([(176, 262), (236, 322), (342, 196)])
    d.line(pts, fill=WHITE, width=int(w), joint="curve")
    for x, y in (pts[0], pts[-1]):
        d.ellipse([x - w / 2, y - w / 2, x + w / 2, y + w / 2], fill=WHITE)

    im.convert("RGB").resize((1024, 1024), Image.LANCZOS).save(out)


