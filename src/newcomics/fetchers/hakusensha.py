"""白泉社：月ごとの新刊情報ページと書籍ページから取得する。

新刊情報（/shinkan?shinkan_year=YYYY&shinkan_month=M）にはレーベルごとの表があり、書名・著者・発売日が取れる。
コミックス（/comicslist/ID/）だけを使い、書籍（/booklist/）は除く。
ISBN・定価・レーベル（シリーズ名）は書籍ページから取る。一度取った本は書籍ページを開き直さない。
"""
import re

from bs4 import BeautifulSoup

from ..normalize import clean_title, isbn13, parse_date, parse_price
from ..store import BookRecord

SLUG = "hakusensha"
NAME = "白泉社"
BASE = "https://www.hakusensha.co.jp"
SOURCE_URL = BASE + "/shinkan"
FETCH_METHOD = "HTML"
LIST_URL = BASE + "/shinkan?shinkan_year={y}&shinkan_month={m}"
COMIC = re.compile(r"/comicslist/(\d+)/?$")


def parse_list(html):
    soup = BeautifulSoup(html, "lxml")
    items, seen = [], set()
    for table in soup.select("table.table1"):
        for tr in table.find_all("tr"):
            tds = tr.find_all("td")
            if len(tds) < 3:
                continue
            a = tds[0].find("a", href=True)
            m = COMIC.search(a["href"]) if a else None
            if not m or m.group(1) in seen:
                continue
            seen.add(m.group(1))
            authors = [{"name": clean_title(x.get_text()), "role": None} for x in tds[1].find_all("a")]
            items.append({
                "id": m.group(1),
                "url": f"{BASE}/comicslist/{m.group(1)}/",
                "title": clean_title(a.get_text()),
                "authors": authors,
                "release_date": parse_date(tds[2].get_text()),
            })
    return items


def parse_detail(html):
    soup = BeautifulSoup(html, "lxml")
    box = soup.select_one(".detailInnerTxt")
    if box is None:
        return None
    data = {}
    for p in box.select("p.txt5"):
        text = clean_title(p.get_text()).lstrip("■")
        key, sep, value = text.partition("：")
        if sep:
            data[key.strip()] = value.strip()
    return {
        "isbn13": isbn13(data.get("ISBNコード", "")),
        "label": data.get("シリーズ名") or None,
        "price": parse_price(data.get("定価", "")),
        "release_date": parse_date(data.get("発売日", "")),
    }


def fetch(client, conn, publisher_id, months, log, known=None):
    known = known or {}
    items = []
    for y, m in months:
        page = parse_list(client.get(LIST_URL.format(y=y, m=m)))
        log(f"{NAME}: {y}年{m}月 {len(page)} 件")
        items.extend(page)
    out = []
    for item in items:
        key = f"{SLUG}:{item['id']}"
        prev = known.get(key)
        rec = BookRecord(
            source_key=key, title_raw=item["title"], release_date=item["release_date"],
            authors=item["authors"], source_url=item["url"],
        )
        if prev is not None and prev["isbn13"]:
            rec.isbn13, rec.price = prev["isbn13"], prev["price"]
        else:
            detail = parse_detail(client.get(item["url"]))
            if detail:
                rec.isbn13, rec.price, rec.label = detail["isbn13"], detail["price"], detail["label"]
                rec.release_date = detail["release_date"] or rec.release_date
        out.append(rec)
    log(f"{NAME}: 取得 {len(out)} 件")
    return out
