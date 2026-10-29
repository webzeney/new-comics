"""双葉社：公式サイトの新刊発売カレンダーが使っているデータ（JSON）から取得する。

紙版のコミックだけを使う（publication_form=2 かつ紙版の発売日 release_dt があるもの）。
カレンダーのデータに定価がないので、まだ取っていない本だけ書籍詳細のデータを開いて本体価格を取り、税込（10%、端数切り捨て）にする。
成人向けの印（age_verification）が付いたものは除外する。
"""
import json

from ..normalize import clean_title, isbn13
from ..store import BookRecord

SLUG = "futabasha"
NAME = "双葉社"
BASE = "https://www.futabasha.co.jp"
API = "https://book-api.futabasha.co.jp"
SOURCE_URL = BASE + "/new-release-calendar"
FETCH_METHOD = "API"
CALENDAR_URL = API + "/calendar_books?request_ym={y:04d}{m:02d}&display_order=1&age_verification=3&image_size=330"
DETAIL_URL = API + "/book_details?media=1&jdcn_code={code}&image_size=330"
COMIC = 2


def parse_calendar(text):
    data = json.loads(text)
    books = (data.get("books") or {}).get("book_informations") or []
    items, ebooks = [], set()
    for b in books:
        if b.get("publication_form") != COMIC:
            continue
        if b.get("web_ebooks_id") and b.get("isbn_code"):
            ebooks.add(b["isbn_code"])
        if not b.get("web_rbooks_id") or not b.get("release_dt") or not isbn13(b.get("isbn_code") or ""):
            continue
        if b.get("age_verification"):
            continue
        authors = [
            {"name": clean_title(a.get("author_name")), "role": a.get("web_author_type_overwrite") or a.get("author_type_name")}
            for a in sorted(b.get("book_authors") or [], key=lambda a: a.get("author_number") or 0)
            if a.get("author_name")
        ]
        items.append({
            "code": b["jdcn_code"],
            "isbn13": isbn13(b["isbn_code"]),
            "title": clean_title(b.get("book_name")),
            "release_date": b["release_dt"],
            "label": clean_title(b.get("label_name")) or None,
            "authors": authors,
            "url": f"{BASE}/book/{b['jdcn_code']}",
        })
    for item in items:
        item["has_ebook"] = item["isbn13"] in ebooks
    return items


def parse_price(text):
    data = json.loads(text)
    details = data.get("book_details")
    if isinstance(details, list):
        details = details[0] if details else {}
    base = (details or {}).get("rbook_price")
    return int(base * 110 // 100) if isinstance(base, int) and base > 0 else None


def fetch(client, conn, publisher_id, months, log, known=None):
    known = known or {}
    items, seen = [], set()
    for y, m in months:
        page = parse_calendar(client.get(CALENDAR_URL.format(y=y, m=m)))
        log(f"{NAME}: {y}年{m}月 {len(page)} 件")
        for item in page:
            if item["isbn13"] not in seen:
                seen.add(item["isbn13"])
                items.append(item)
    out = []
    for item in items:
        key = f"{SLUG}:{item['isbn13']}"
        prev = known.get(key)
        price = prev["price"] if prev is not None and prev["price"] else parse_price(client.get(DETAIL_URL.format(code=item["code"])))
        out.append(BookRecord(
            source_key=key, title_raw=item["title"], release_date=item["release_date"], isbn13=item["isbn13"],
            price=price, label=item["label"], authors=item["authors"], has_ebook=item["has_ebook"], source_url=item["url"],
        ))
    log(f"{NAME}: 取得 {len(out)} 件")
    return out
