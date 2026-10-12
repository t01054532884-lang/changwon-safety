"""iOS 앱 아이콘(1024)과 시작 화면(2732 정사각) 이미지를 만든다. Windows의 맑은 고딕 기준.

    python scripts/make_assets.py
"""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter

OUT = Path(__file__).resolve().parent.parent / "resources"
OUT.mkdir(exist_ok=True)
BLUE = (29, 78, 216)
NAVY = (30, 58, 138)
WHITE = (255, 255, 255)
LAMP = (253, 224, 71)
FONT_BOLD = "C:/Windows/Fonts/malgunbd.ttf"
FONT = "C:/Windows/Fonts/malgun.ttf"


def shield(draw, cx, cy, size, fg, bg):
    """기존 PWA 아이콘(방패+체크)과 같은 모양을 size 기준으로 그린다(512 좌표계에서 비율 변환)."""
    k = size / 512
    P = lambda pts: [(cx + (x - 256) * k, cy + (y - 256) * k) for x, y in pts]
    draw.polygon(P([(72, 92), (256, 42), (442, 92), (442, 282), (256, 468), (72, 282)]), fill=fg)
    draw.polygon(P([(122, 182), (256, 108), (390, 182), (390, 268), (256, 402), (122, 268)]), fill=bg)
    w = int(24 * k)
    pts = P([(178, 258), (238, 322), (346, 186)])
    draw.line(pts, fill=fg, width=w, joint="curve")
    for x, y in (pts[0], pts[-1]):
        draw.ellipse([x - w / 2, y - w / 2, x + w / 2, y + w / 2], fill=fg)


def make_icon():
    S = 4096
    im = Image.new("RGB", (S, S), BLUE)
    shield(ImageDraw.Draw(im), S / 2, S / 2, S, WHITE, BLUE)
    im.resize((1024, 1024), Image.LANCZOS).save(OUT / "icon-1024.png")


def make_splash():
    S = 2732
    im = Image.new("RGB", (S, S), NAVY)
    # 위→아래 남색→파랑 그라데이션(온보딩 화면 배경과 같은 색)
    top, bot = NAVY, BLUE
    grad = Image.new("RGB", (1, S))
    for y in range(S):
        t = y / (S - 1)
        grad.putpixel((0, y), tuple(int(top[i] + (bot[i] - top[i]) * t) for i in range(3)))
    im = grad.resize((S, S))
    d = ImageDraw.Draw(im)
    cx = S / 2

    # 방패 아이콘
    shield(d, cx, 900, 400, WHITE, NAVY)

    # 귀여운 산책길: 점선 길 + 가로등 3개(노란 불빛) + 작은 발자국
    path_y = 1430
    for x in range(int(cx - 520), int(cx + 521), 64):
        d.rounded_rectangle([x - 18, path_y - 7, x + 18, path_y + 7], radius=7, fill=(147, 197, 253))
    glow = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    g = ImageDraw.Draw(glow)
    for lx in (cx - 380, cx, cx + 380):
        g.ellipse([lx - 95, path_y - 300, lx + 95, path_y - 110], fill=(253, 224, 71, 110))
    glow = glow.filter(ImageFilter.GaussianBlur(28))
    im.paste(glow, (0, 0), glow)
    d = ImageDraw.Draw(im)
    for lx in (cx - 380, cx, cx + 380):
        d.rounded_rectangle([lx - 7, path_y - 200, lx + 7, path_y - 10], radius=7, fill=WHITE)
        d.rounded_rectangle([lx - 34, path_y - 222, lx + 34, path_y - 196], radius=12, fill=WHITE)
        d.ellipse([lx - 22, path_y - 206, lx + 22, path_y - 170], fill=LAMP)
    for i, fx in enumerate((cx - 200, cx - 150, cx + 170, cx + 220)):
        fy = path_y - 52 if i % 2 == 0 else path_y - 28
        d.ellipse([fx - 15, fy - 22, fx + 15, fy + 22], fill=WHITE)
        d.ellipse([fx - 9, fy - 44, fx + 9, fy - 28], fill=WHITE)

    # 문구
    f1 = ImageFont.truetype(FONT_BOLD, 66)
    f2 = ImageFont.truetype(FONT, 46)
    for text, font, y, fill in [
        ("창원시의 안전한 보행경로를 위해", f1, 1560, WHITE),
        ("지도를 불러오고 있습니다", f1, 1650, WHITE),
        ("잠시만 기다려 주세요", f2, 1770, (191, 219, 254)),
    ]:
        w = d.textlength(text, font=font)
        d.text((cx - w / 2, y), text, font=font, fill=fill)
    im.save(OUT / "splash-2732x2732.png", optimize=True)


if __name__ == "__main__":
    make_icon()
    make_splash()
    print("saved to", OUT)
