"""講談社：コミック発売予定表（紙版）と書籍ページから取得する。

一覧（/comic/calendar/YYYYMM）で発売日・書名・著者・価格が取れる。
ISBN とレーベル（シリーズ）は書籍ページにしかないので、まだ取っていない本だけ書籍ページを開く。
1回の実行で開く書籍ページの数には上限を設け、残りは次回以降に回す。
"""
import re

from bs4 import BeautifulSoup

from ..normalize import clean_title, isbn13, parse_date, parse_price
from ..store import BookRecord

SLUG = "kodansha"
NAME = "講談社"
BASE = "https://www.kodansha.co.jp"
SOURCE_URL = BASE + "/comic/calendar"
FETCH_METHOD = "HTML"
LIST_URL = BASE + "/comic/calendar/{y:04d}{m:02d}"
MAX_DETAILS = 200
PRODUCT = re.compile(r"/comic/products/(\d+)")


def parse_authors(text):
    authors = []
    for part in re.split(r"[，,、]", clean_title(text)):
        part = part.strip()
        if not part:
            continue
        role, sep, name = part.partition("：")
        if not sep:
            role, name = None, part
        authors.append({"name": clean_title(name), "role": clean_title(role) if role else None})
    return authors


def parse_list(html):
    soup = BeautifulSoup(html, "lxml")
    items, seen = [], set()
    for section in soup.select("section[data-scroll-anchor]"):
        for a in section.select("li a[href]"):
            m = PRODUCT.search(a["href"])
            if not m or m.group(1) in seen:
                continue
            ps = [clean_title(p.get_text()) for p in a.find_all("p", recursive=False)]
            if len(ps) < 2:
                continue
            seen.add(m.group(1))
            date = parse_date(ps[0])
            price = next((parse_price(p) for p in ps[2:] if p.startswith("定価")), None)
            authors = next((parse_authors(p) for p in ps[2:] if "：" in p and not p.startswith("定価")), [])
            items.append({
                "id": m.group(1),
                "url": BASE + "/comic/products/" + m.group(1),
                "release_date": date,
                "title": ps[1],
                "authors": authors,
                "price": price,
            })
    return items


def parse_detail(html):
    soup = BeautifulSoup(html, "lxml")
    paper, has_ebook = None, False
    for h4 in soup.find_all("h4"):
        label = h4.get_text(strip=True)
        if label == "紙版" and paper is None:
            paper = h4.find_next_sibling()
        elif label == "電子版":
            has_ebook = True
    if paper is None:
        return None
    data = {}
    for sec in paper.find_all("section"):
        h5, p = sec.find("h5"), sec.find("p")
        if h5 and p:
            data[h5.get_text(strip=True)] = clean_title(p.get_text())
    return {
        "isbn13": isbn13(data.get("ISBN", "")),
        "release_date": parse_date(data.get("発売日", "")),
        "price": parse_price(data.get("価格", "")),
        "label": data.get("シリーズ") or None,
        "has_ebook": has_ebook,
    }


def fetch(client, conn, publisher_id, months, log, known=None):
    known = known or {}
    items = []
    for y, m in months:
        page = parse_list(client.get(LIST_URL.format(y=y, m=m)))
        log(f"{NAME}: {y}年{m}月 {len(page)} 件")
        items.extend(page)
    items.sort(key=lambda i: i["release_date"] or "9999")
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
            source_url=item["url"],
        )
        if prev is not None and prev["isbn13"]:
            rec.isbn13 = prev["isbn13"]
        elif opened < MAX_DETAILS:
            opened += 1
            detail = parse_detail(client.get(item["url"]))
            if detail:
                rec.isbn13 = detail["isbn13"]
                rec.label = detail["label"]
                rec.has_ebook = detail["has_ebook"]
                rec.price = detail["price"] or rec.price
        else:
            pending += 1
        out.append(rec)
    log(f"{NAME}: 取得 {len(out)} 件（書籍ページ {opened} 件、次回以降に回した {pending} 件）")
    return out
