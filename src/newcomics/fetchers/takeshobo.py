import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup, NavigableString

from ..normalize import clean_title, isbn13, parse_date, parse_price
from ..store import BookRecord

SLUG = "takeshobo"
NAME = "竹書房"
BASE = "https://www.takeshobo.co.jp"
SOURCE_URL = BASE + "/search/g106010.html"
FETCH_METHOD = "HTML"
LIST_URL = BASE + "/search/?page={page}&search_genre=106010&search_label=106010&amount=120&order=book_date_desc"
MAX_PAGES = 10


def parse_list(html):
    soup = BeautifulSoup(html, "lxml")
    items = []
    for item in soup.select(".booklist .item"):
        a = item.select_one(".ttl a")
        date_el = item.select_one(".date")
        if a is None or date_el is None:
            continue
        m = re.search(r"/book/(b\d+)\.html", a.get("href", ""))
        if not m:
            continue
        items.append(
            {
                "id": m.group(1),
                "url": urljoin(BASE, a["href"]),
                "title": clean_title(a.get_text()),
                "release_date": parse_date(date_el.get_text()),
            }
        )
    return items


def parse_detail(html):
    soup = BeautifulSoup(html, "lxml")
    table = None
    for t in soup.select(".data table"):
        if any(th.get_text(strip=True) == "ISBN" for th in t.find_all("th")):
            table = t
            break
    if table is None:
        return None
    data = {}
    for th in table.find_all("th"):
        td = th.find_next_sibling("td")
        if td is not None:
            data[th.get_text(strip=True)] = td
    authors = []
    if "著者" in data:
        current = None
        for node in data["著者"].children:
            if getattr(node, "name", None) == "a":
                current = {"name": clean_title(node.get_text()), "role": None}
                authors.append(current)
            elif isinstance(node, NavigableString) and current is not None and node.strip():
                current["role"] = clean_title(node)
    title_el = soup.select_one("h1.pagetitle")
    label = None
    if "レーベル" in data:
        label = clean_title(data["レーベル"].get_text(" "))
    return {
        "title": clean_title(title_el.get_text()) if title_el else None,
        "isbn13": isbn13(data["ISBN"].get_text()) if "ISBN" in data else None,
        "release_date": parse_date(data["出版年月日"].get_text()) if "出版年月日" in data else None,
        "price": parse_price(data["定価"].get_text()) if "定価" in data else None,
        "label": label,
        "authors": authors,
    }


def fetch(client, conn, publisher_id, months, log, known=None):
    known = known or {}
    start = f"{months[0][0]:04d}-{months[0][1]:02d}-01"
    targets = []
    for page in range(1, MAX_PAGES + 1):
        items = parse_list(client.get(LIST_URL.format(page=page)))
        if not items:
            break
        targets.extend(i for i in items if i["release_date"] and i["release_date"] >= start)
        if any(i["release_date"] and i["release_date"] < start for i in items):
            break
    log(f"{NAME}: 一覧から {len(targets)} 件（{start} 以降）")
    out, skipped = [], 0
    for item in targets:
        key = f"{SLUG}:{item['id']}"
        prev = known.get(key)
        if prev is not None and prev["isbn13"] and prev["release_date"] == item["release_date"]:
            out.append(
                BookRecord(
                    source_key=key,
                    title_raw=item["title"],
                    release_date=item["release_date"],
                    isbn13=prev["isbn13"],
                    price=prev["price"],
                    source_url=item["url"],
                )
            )
            continue
        detail = parse_detail(client.get(item["url"]))
        if detail is None or not detail["isbn13"]:
            skipped += 1
            continue
        out.append(
            BookRecord(
                source_key=key,
                title_raw=detail["title"] or item["title"],
                release_date=detail["release_date"] or item["release_date"],
                isbn13=detail["isbn13"],
                price=detail["price"],
                label=detail["label"],
                authors=detail["authors"],
                source_url=item["url"],
            )
        )
    log(f"{NAME}: 取得 {len(out)} 件（ISBNなしで除外 {skipped} 件）")
    return out
