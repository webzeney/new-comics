"""特集記事のアイキャッチ画像（1200×630）を作る。

本の表紙など他者の画像は使わず、サイトの配色（朱赤・黒・黄・白）と文字だけで作る。
"""
import os
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

W, H = 1200, 630
RED = (217, 72, 59)
BLACK = (34, 34, 34)
YELLOW = (255, 209, 92)
WHITE = (255, 255, 255)
ACCENT = (181, 48, 42)
CREAM = (255, 246, 236)

JP_FONT = os.environ.get("NC_FONT_JP", "/usr/share/fonts/opentype/noto/NotoSansCJK-Black.ttc")
EN_FONT = os.environ.get("NC_FONT_EN", str(Path(__file__).resolve().parent / "fonts" / "Fredoka-700.ttf"))


def font_jp(size):
    return ImageFont.truetype(JP_FONT, size, index=0)


def font_en(size):
    return ImageFont.truetype(EN_FONT, size)


def logo(draw, x, y, s):
    k = s / 64
    r = lambda a, b, c, d: (x + a * k, y + b * k, x + c * k, y + d * k)
    draw.rounded_rectangle(r(3, 3, 61, 61), radius=10 * k, fill=WHITE, outline=BLACK, width=max(2, int(3 * k)))
    draw.line([(x + 3 * k, y + 30 * k), (x + 34 * k, y + 30 * k)], fill=BLACK, width=max(2, int(3 * k)))
    draw.line([(x + 34 * k, y + 3 * k), (x + 34 * k, y + 61 * k)], fill=BLACK, width=max(2, int(3 * k)))
    draw.line([(x + 34 * k, y + 40 * k), (x + 61 * k, y + 40 * k)], fill=BLACK, width=max(2, int(3 * k)))
    draw.rounded_rectangle(r(8, 8, 29, 25), radius=3 * k, fill=RED)
    draw.rounded_rectangle(r(39, 8, 56, 35), radius=3 * k, fill=YELLOW)
    draw.rounded_rectangle(r(8, 35, 29, 56), radius=3 * k, fill=YELLOW)
    draw.rounded_rectangle(r(39, 45, 56, 56), radius=3 * k, fill=RED)


def make(title_lines, label, out_path, sub=None):
    """title_lines：見出しを行ごとに分けたもの（最大3行）。行の途中では折り返さない。"""
    img = Image.new("RGB", (W, H), RED)
    d = ImageDraw.Draw(img)
    x0, y0, x1, y1 = 48, 44, W - 60, H - 60
    d.rounded_rectangle((x0 + 12, y0 + 12, x1 + 12, y1 + 12), radius=36, fill=BLACK)
    d.rounded_rectangle((x0, y0, x1, y1), radius=36, fill=WHITE, outline=BLACK, width=5)
    pad = 64
    d.text((x0 + pad, y0 + 52), "FEATURE", font=font_en(30), fill=ACCENT)
    tag_font = font_jp(26)
    tw = d.textlength(label, font=tag_font)
    tx = x0 + pad + d.textlength("FEATURE", font=font_en(30)) + 24
    d.rounded_rectangle((tx, y0 + 48, tx + tw + 36, y0 + 92), radius=22, fill=CREAM)
    d.text((tx + 18, y0 + 52), label, font=tag_font, fill=ACCENT)
    lines = [l for l in title_lines if l][:3]
    top, bottom = y0 + 128, y1 - 140 - (44 if sub else 0)
    size = 76
    while size > 36:
        f = font_jp(size)
        if all(d.textlength(l, font=f) <= x1 - x0 - pad * 2 for l in lines) and len(lines) * size * 1.3 <= bottom - top:
            break
        size -= 2
    y = top
    for line in lines:
        d.text((x0 + pad, y), line, font=f, fill=BLACK)
        y += int(size * 1.3)
    if sub:
        d.text((x0 + pad, y + 16), sub, font=font_jp(28), fill=(90, 81, 72))
    d.rectangle((x0 + pad, y1 - 118, x1 - pad, y1 - 115), fill=YELLOW)
    logo(d, x0 + pad, y1 - 96, 60)
    d.text((x0 + pad + 76, y1 - 98), "漫画新刊JP", font=font_jp(32), fill=BLACK)
    d.text((x0 + pad + 78, y1 - 56), "NEW COMICS JP", font=font_en(20), fill=ACCENT)
    url_font = font_en(24)
    d.text((x1 - pad - d.textlength("new-comics.jp", font=url_font), y1 - 82), "new-comics.jp", font=url_font, fill=BLACK)
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path, "PNG", optimize=True)
    return out_path
