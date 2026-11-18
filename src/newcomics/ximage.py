"""X の投稿に付ける画像（1200x675）を作る。

左に日付と「今日発売の漫画新刊 ◯点」、右に看板キャラクター（こはる）とベタ。
こはるの絵は日ごとに順番に替える。書影は入れない（楽天・Amazon の書影はサイトの中だけで使う）。
フォントは使う文字だけに絞ったもの（Noto Sans JP・Yusei Magic。どちらも SIL Open Font License）。
"""
from datetime import date
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent / "ximage"
W, H = 1200, 675
INK = (34, 34, 34)
RED = (217, 72, 59)
DOW = "月火水木金土日"
# 絵ごとの背景の色
POSES = [
    ("morning", (255, 241, 214)),
    ("books", (253, 230, 238)),
    ("calendar", (227, 241, 251)),
    ("read", (234, 228, 247)),
]


def font(name, size):
    return ImageFont.truetype(str(HERE / name), size)


def jp(size):
    return font("NotoSansJP-Black-subset.otf", size)


def en(size):
    return font("YuseiMagic-subset.ttf", size)


def text_spaced(draw, xy, text, fnt, fill, spacing):
    """文字間をあけて書き、書き終わりの x を返す。"""
    x, y = xy
    for c in text:
        draw.text((x, y), c, font=fnt, fill=fill, anchor="ls")
        x += draw.textlength(c, font=fnt) + spacing
    return x - spacing


def make(day: date, count: int, out):
    name, bg = POSES[day.toordinal() % len(POSES)]
    im = Image.new("RGB", (W, H), bg)
    d = ImageDraw.Draw(im)
    # 白い水玉
    for y in range(-10, H + 40, 44):
        for x in range(-10 + (22 if (y // 44) % 2 else 0), W + 40, 44):
            d.ellipse((x - 6, y - 6, x + 6, y + 6), fill=(255, 255, 255))
    # 文字の枠（サイトと同じ黒い線と影）
    box = (60, 92, 650, 583)
    d.rounded_rectangle((box[0] + 10, box[1] + 10, box[2] + 10, box[3] + 10), 36, fill=INK)
    d.rounded_rectangle(box, 36, fill=(255, 255, 255), outline=INK, width=5)
    left = box[0] + 58
    text_spaced(d, (left, 184), "NEW COMICS JP", en(30), RED, 5)
    x = text_spaced(d, (left, 306), f"{day.month}.{day.day}", en(112), INK, 10)
    d.text((x + 10, 300), f"（{DOW[day.weekday()]}）", font=jp(46), fill=INK, anchor="ls")
    d.text((left, 392), "今日発売の漫画新刊", font=jp(54), fill=INK, anchor="ls")
    x = text_spaced(d, (left, 532), str(count), en(124), RED, 8)
    d.text((x + 12, 526), "点", font=jp(62), fill=RED, anchor="ls")
    # こはる
    ch = Image.open(HERE / f"koharu_{name}.webp").convert("RGBA")
    h = 640
    ch = ch.resize((round(ch.width * h / ch.height), h), Image.LANCZOS)
    cx = 935
    im.paste(ch, (cx - ch.width // 2, H - h + 8), ch)
    im.save(out, "PNG", optimize=True)
    return out
