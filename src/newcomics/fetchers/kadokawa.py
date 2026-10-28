"""KADOKAWA：コミックの新刊カレンダーと書籍ページから取得する。

カレンダー（/calendar/?target=N&largeGenre=13）は当月（0）と翌月（2）が見られる。
発売日・書名・著者・価格・レーベル・電子版の有無はカレンダーで取れる。定価のない項目は電子版のみなので除外する。
ISBN は書籍ページにしかないので、まだ取っていない本だけ開く。robots.txt の Crawl-delay（20秒）に従うため、
1回の実行で開く書籍ページの数には上限を設け、残りは次回以降に回す。
"""
import re

from bs4 import BeautifulSoup

from ..normalize import clean_title, isbn13, parse_price
from ..store import BookRecord

SLUG = "kadokawa"
NAME = "KADOKAWA"
BASE = "https://www.kadokawa.co.jp"
SOURCE_URL = BASE + "/calendar/?largeGenre=13"
FETCH_METHOD = "HTML"
LIST_URL = BASE + "/calendar/?target={target}&largeGenre=13"
TARGETS = ("0", "2")
MAX_DETAILS = 80
PRODUCT = re.compile(r"/product/(\d+)/")
MONTH = re.compile(r"(\d{4})年(\d{1,2})月の新刊カレンダー")


def parse_list(html):
    soup = BeautifulSoup(html, "lxml")
    heading = soup.find(string=MONTH)
    if heading is None:
        return None, []
    m = MONTH.search(heading)
    year, month = int(m.group(1)), int(m.group(2))
    items, seen = [], set()
    for day in soup.select("div.calendar-main"):
        dm = re.search(r"\bdate-(\d{1,2})\b", " ".join(day.get("class", [])))
        if not dm:
            continue
        date = f"{year:04d}-{month:02d}-{int(dm.group(1)):02d}"
        for detail in day.select("div.calendar-book-detail"):
            price_el = detail.select_one(".book-info-price")
            if price_el is None:
                continue
            box = detail.find_parent("div", class_="calendar-book-details") or detail
            link = next((a for a in box.find_all("a", href=True) if PRODUCT.search(a["href"])), None)
            title_el = detail.select_one("h2.book-title")
            if link is None or title_el is None:
                continue
            pid = PRODUCT.search(link["href"]).group(1)
            if pid in seen:
                continue
            seen.add(pid)
            authors = []
            for li in detail.select("ul.book-auther li"):
                text = li.get_text().replace("\xa0", " ")
                role, _, name = clean_title(text).partition(" ")
                authors.append({"name": clean_title(name) or role, "role": role if name else None})
            label = None
            for span in detail.select(".book-info-label"):
                t = clean_title(span.get_text())
                if t.startswith("レーベル："):
                    label = t[len("レーベル："):].strip() or None
            items.append({
                "id": pid,
                "url": f"{BASE}/product/{pid}/",
                "release_date": date,
                "title": clean_title(title_el.get_text()),
                "authors": authors,
                "price": parse_price(price_el.get_text()),
                "label": label,
                "has_ebook": "電子版" in detail.select_one(".book-btn-wrap").get_text() if detail.select_one(".book-btn-wrap") else False,
            })
    return (year, month), items


def parse_detail(html):
    text = BeautifulSoup(html, "lxml").get_text(" ")
    m = re.search(r"ISBN[：:]\s*(97[89][\d-]{10,14})", text)
    return isbn13(m.group(1)) if m else None


def fetch(client, conn, publisher_id, months, log, known=None):
    known = known or {}
    wanted = {(y, m) for y, m in months}
    items = []
    for target in TARGETS:
        ym, page = parse_list(client.get(LIST_URL.format(target=target)))
        if ym is None:
            raise RuntimeError("カレンダーの年月が読み取れません")
        if ym not in wanted:
            continue
        log(f"{NAME}: {ym[0]}年{ym[1]}月 {len(page)} 件")
        items.extend(page)
    items.sort(key=lambda i: i["release_date"])
    out, opened, pending = [], 0, 0
    for item in items:
        key = f"{SLUG}:{item['id']}"
        prev = known.get(key)
        rec = BookRecord(
            source_key=key,
            title_raw=item["title"],
            release_date=item["release_date"],
            authors=item["authors"],
            price=item["price"],
            label=item["label"],
            has_ebook=item["has_ebook"],
            source_url=item["url"],
        )
        if prev is not None and prev["isbn13"]:
            rec.isbn13 = prev["isbn13"]
        elif opened < MAX_DETAILS:
            opened += 1
            rec.isbn13 = parse_detail(client.get(item["url"]))
        else:
            pending += 1
        out.append(rec)
    log(f"{NAME}: 取得 {len(out)} 件（書籍ページ {opened} 件、次回以降に回した {pending} 件）")
    return out
