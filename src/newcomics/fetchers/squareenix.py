"""スクウェア・エニックス：「発売予定情報」と「新刊情報」（発売月で検索）、書籍ページから取得する。

発売予定情報には ISBN がないので、書名・巻数・発売日・価格・著者だけを取る。
新刊情報は書籍ページの URL の数字が ISBN（13桁）なので、ISBN はそこから取る。
小説・ゲーム関連の本は対象外にする。レーベル名は掲載誌から決まるもの（下の表）だけを入れる。
"""
import json
import re
import unicodedata

from bs4 import BeautifulSoup

from ..normalize import clean_title, isbn13, normalized_series, parse_date, parse_price
from ..store import BookRecord

SLUG = "square-enix"
NAME = "スクウェア・エニックス"
BASE = "https://magazine.jp.square-enix.com"
SOURCE_URL = BASE + "/top/calendar/"
FETCH_METHOD = "HTML"
CALENDAR_URL = BASE + "/top/calendar/"
MONTH_URL = BASE + "/top/comics/?search=s&year={year}&month={month}&label="
MORE_URL = BASE + "/top/ajax/more/comics/?sword=&year={year}&month={month}&label=&search=s&p={page}"
MAX_PAGES = 20
MAX_DETAILS = 80
DETAIL = re.compile(r"/top/comics/detail/(\d+)/")
EXCLUDED = {"SQEXノベル", "SQUARE ENIX NOVELS", "ガンガンノベルズ", "ゲーム関連", "書籍情報"}
LABELS = {
    "少年ガンガン": "ガンガンコミックス",
    "ガンガンONLINE": "ガンガンコミックスONLINE",
    "ガンガンJOKER": "ガンガンコミックスJOKER",
    "ガンガンpixiv": "ガンガンコミックスpixiv",
    "マンガUP!": "ガンガンコミックスUP!",
    "ヤングガンガン": "ヤングガンガンコミックス",
    "ビッグガンガン": "ビッグガンガンコミックス",
    "Gファンタジー": "Gファンタジーコミックス",
}
TAIL = re.compile(r"[\s　]+(\d+)\s*(?:[(（]完[)）])?\s*$")
FINAL = re.compile(r"[(（]完[)）]\s*$")


def nfkc_label(text):
    return unicodedata.normalize("NFKC", clean_title(text))


def split_title(text):
    """「書名　4(完)」を「書名 4」と完結の有無に分ける。"""
    raw = clean_title(text)
    final = bool(FINAL.search(raw))
    m = TAIL.search(raw)
    if m:
        return f"{raw[:m.start()].strip()} {m.group(1)}", int(m.group(1)), final
    return FINAL.sub("", raw).strip(), None, final


def parse_authors(text):
    out = []
    for part in re.split(r"[\s　]{1,}(?=[^\s　：:]+[：:])", clean_title(text)):
        role, sep, name = part.partition("：")
        if not sep:
            role, sep, name = part.partition(":")
        if sep:
            name = re.sub(r"[（(][^）)]*[）)]", "", name)
            for n in re.split(r"[、,／/]", name):
                if clean_title(n):
                    out.append({"name": clean_title(n), "role": clean_title(role) if clean_title(role) != "著者" else None})
        elif clean_title(part):
            out.append({"name": clean_title(part), "role": None})
    return out


def parse_calendar(html):
    soup = BeautifulSoup(html, "lxml")
    items = []
    for li in soup.select("ul.calendarList > li"):
        date_el, mag_el, title_el = li.select_one(".dates"), li.select_one(".tit01"), li.select_one(".tit02")
        if not (date_el and title_el):
            continue
        magazine = nfkc_label(mag_el.get_text()) if mag_el else ""
        title, volume, final = split_title(title_el.get_text())
        more = li.select_one(".moreTxt")
        price = None
        for p in li.select(".cont > p"):
            if "定価" in p.get_text():
                price = parse_price(p.get_text())
        items.append({
            "magazine": magazine, "title": title, "volume": volume, "final": final,
            "release_date": parse_date(date_el.get_text()), "price": price,
            "authors": parse_authors(more.get_text()) if more else [],
        })
    return items


def parse_month(html):
    soup = BeautifulSoup(html, "lxml")
    items = []
    for li in soup.select("li.comic_article"):
        a = li.find("a", href=DETAIL)
        mag_el, date_el = li.select_one(".tit"), li.select_one(".dates")
        if not (a and date_el):
            continue
        code = DETAIL.search(a["href"]).group(1)
        name = li.select_one(".numCol")
        num = li.select_one(".numCol2")
        text = clean_title((name.get_text() if name else "") + " " + (num.get_text() if num else ""))
        title, volume, final = split_title(text)
        items.append({
            "code": code, "isbn13": isbn13(code), "url": BASE + f"/top/comics/detail/{code}/",
            "magazine": nfkc_label(mag_el.get_text()) if mag_el else "", "title": title, "volume": volume, "final": final,
            "release_date": parse_date(date_el.get_text()),
        })
    has_next = False
    data = soup.select_one("#data")
    if data is not None:
        has_next = data.get("data-nextlink") not in (None, "", "0")
    elif soup.select_one(".btnMore"):
        has_next = True
    return items, has_next


def parse_detail(html):
    soup = BeautifulSoup(html, "lxml")
    box = soup.select_one(".comDetail")
    if box is None:
        return None
    info = box.select_one(".tit03")
    authors = []
    if info is not None:
        for line in info.get_text("\n").split("\n"):
            line = clean_title(line)
            if line.startswith("著者"):
                authors = parse_authors(line)
    txt = box.select_one(".txt02")
    t = txt.get_text(" ") if txt else ""
    m = re.search(r"ISBN[：:]\s*([\d-]+)", t)
    return {"price": parse_price(t), "isbn13": isbn13(m.group(1)) if m else None, "authors": authors}


def key_for(title, volume):
    return f"{SLUG}:t:{normalized_series(title)}:{volume if volume is not None else ''}"


def record(item, price=None, authors=None, isbn=None, url=None):
    return BookRecord(
        source_key=f"{SLUG}:{isbn}" if isbn else key_for(item["title"], item["volume"]),
        title_raw=item["title"], title=item["title"], volume=item["volume"], is_final=item["final"],
        release_date=item["release_date"], isbn13=isbn, price=price, authors=authors or [],
        label=LABELS.get(item["magazine"]), source_url=url or CALENDAR_URL,
    )


def fetch(client, conn, publisher_id, months, log, known=None):
    known = known or {}
    start = f"{months[0][0]:04d}-{months[0][1]:02d}-01"
    end = f"{months[-1][0]:04d}-{months[-1][1]:02d}-31"
    out, seen, excluded, details = [], set(), 0, 0

    for y, m in months:
        page, items = 1, []
        html = client.get(MONTH_URL.format(year=y, month=m))
        found, has_next = parse_month(html)
        items.extend(found)
        while has_next and page < MAX_PAGES:
            page += 1
            found, has_next = parse_month(client.get(MORE_URL.format(year=y, month=m, page=page)))
            if not found:
                break
            items.extend(found)
        for item in items:
            if item["magazine"] in EXCLUDED:
                excluded += 1
                continue
            if not item["release_date"] or not (start <= item["release_date"] <= end) or item["code"] in seen:
                continue
            seen.add(item["code"])
            isbn = item["isbn13"]
            key = f"{SLUG}:{isbn}" if isbn else f"{SLUG}:{item['code']}"
            prev = known.get(key)
            if prev is not None and prev["title_raw"]:
                out.append(record(item, prev["price"], json.loads(prev["authors"] or "[]"), isbn, item["url"]))
                seen.add(("t", normalized_series(item["title"]), item["volume"]))
                continue
            detail = None
            if details < MAX_DETAILS:
                detail = parse_detail(client.get(item["url"]))
                details += 1
            isbn = isbn or (detail or {}).get("isbn13")
            out.append(record(item, (detail or {}).get("price"), (detail or {}).get("authors"), isbn, item["url"]))
            seen.add(("t", normalized_series(item["title"]), item["volume"]))

    for item in parse_calendar(client.get(CALENDAR_URL)):
        if item["magazine"] in EXCLUDED:
            excluded += 1
            continue
        if not item["release_date"] or not (start <= item["release_date"] <= end):
            continue
        tkey = ("t", normalized_series(item["title"]), item["volume"])
        if tkey in seen:
            continue
        seen.add(tkey)
        out.append(record(item, item["price"], item["authors"]))

    log(f"{NAME}: 取得 {len(out)} 件（対象外 {excluded} 件・書籍ページ {details} 件）")
    return out
