import re
import unicodedata

EDITION_PATTERNS = [
    ("特装版", re.compile(r"特装版")),
    ("限定版", re.compile(r"限定版|特別限定版|初回限定")),
    ("特別版", re.compile(r"特別版|豪華版")),
]
FINAL_PATTERN = re.compile(r"最終巻|完結巻|〈完〉|（完）|\(完\)")
VOLUME_PATTERNS = [
    re.compile(r"第\s*(\d+)\s*巻"),
    re.compile(r"[（(]\s*(\d+)\s*[）)]\s*$"),
    re.compile(r"\s(\d+)\s*$"),
    re.compile(r"(\d+)\s*巻\s*$"),
    re.compile(r"[〜~!」』]\s*(\d+)\s*$"),
]
EDITION_STRIP = re.compile(r"[\s　]*[（(【\[]?[^（(【\[）)】\]\s　]*(特装版|限定版|特別版|豪華版).*$")
SPACE = re.compile(r"[\s　]+")


def nfkc(text):
    return unicodedata.normalize("NFKC", text or "")


def clean_title(text):
    return SPACE.sub(" ", (text or "").replace("　", " ")).strip()


def parse_volume(title):
    t = nfkc(title)
    t = EDITION_STRIP.sub("", t)
    for pattern in VOLUME_PATTERNS:
        m = pattern.search(t)
        if m:
            return int(m.group(1))
    return None


def detect_edition(title):
    t = nfkc(title)
    for name, pattern in EDITION_PATTERNS:
        if pattern.search(t):
            return name
    return "通常"


def detect_final(title):
    return bool(FINAL_PATTERN.search(nfkc(title)))


def series_name(title):
    t = nfkc(title)
    t = EDITION_STRIP.sub("", t)
    t = re.sub(r"[\s]*第\s*\d+\s*巻.*$", "", t)
    t = re.sub(r"[\s]*[（(]\s*\d+\s*[）)]\s*$", "", t)
    t = re.sub(r"\s+\d+\s*$", "", t)
    t = re.sub(r"\d+\s*巻\s*$", "", t)
    t = re.sub(r"(?<=[〜~!」』])\s*\d+\s*$", "", t)
    return clean_title(t)


def normalized_series(title):
    t = series_name(title).lower()
    return re.sub(r"[\s・:：!！?？~〜～\-ー―「」『』【】]", "", t)


def isbn13(value):
    digits = re.sub(r"\D", "", nfkc(value))
    if len(digits) == 13 and digits.startswith(("978", "979")):
        return digits
    return None


def isbn10_to_13(value):
    """ISBN-10（9桁＋チェック）から ISBN-13 を作る。"""
    digits = re.sub(r"[^\dXx]", "", nfkc(value))
    if len(digits) == 10:
        digits = digits[:9]
    if len(digits) != 9 or not digits.isdigit():
        return None
    core = "978" + digits
    total = sum(int(c) * (1 if i % 2 == 0 else 3) for i, c in enumerate(core))
    return core + str((10 - total % 10) % 10)


def parse_price(text):
    m = re.search(r"([\d,]+)\s*円", nfkc(text))
    return int(m.group(1).replace(",", "")) if m else None


def parse_date(text):
    m = re.search(r"(\d{4})[/年.-](\d{1,2})[/月.-](\d{1,2})", nfkc(text))
    if not m:
        return None
    return f"{int(m.group(1)):04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"
