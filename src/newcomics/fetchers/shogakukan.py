import re

from bs4 import BeautifulSoup

from ..normalize import clean_title, isbn13, parse_date, parse_price
from ..store import BookRecord

SLUG = "shogakukan"
NAME = "小学館"
BASE = "https://shogakukan-comic.jp"
SOURCE_URL = BASE + "/release"
FETCH_METHOD = "HTML"
LIST_URLS = [BASE + "/release", BASE + "/release?month=next"]
DETAIL_URL = BASE + "/book?isbn={isbn}"
EXCLUDED_SECTIONS = {"light_novel"}


def parse_list(html):
    soup = BeautifulSoup(html, "lxml")
    first = soup.select_one("ul.new_comic")
    if first is None:
        return [], 0
    section = first.find_parent("section")
    items, excluded = [], 0
    seen = set()
    for block in section.find_all("div", recursive=False):
        lis = block.select("ul.new_comic > li")
        if block.get("id") in EXCLUDED_SECTIONS:
            excluded += len(lis)
            continue
        for li in lis:
            code = None
            for a in li.find_all("a"):
                m = re.search(r"isbn=(\d{13})|/(97[89]\d{10})(?:$|[/?#])", a.get("href", ""))
                if m:
                    code = isbn13(m.group(1) or m.group(2))
                    break
            if not code or code in seen:
                continue
            seen.add(code)
            title_el = next((p for p in li.find_all("p") if not p.get("class")), None)
            items.append({"isbn13": code, "title": clean_title(title_el.get_text()) if title_el else None})
    return items, excluded


def parse_detail(html):
    soup = BeautifulSoup(html, "lxml")
    paper, has_ebook = None, False
    for table in soup.select("table.volume"):
        heading = table.find_previous_sibling()
        label = heading.get_text(strip=True) if heading else ""
        if "紙" in label and paper is None:
            paper = table
        elif "電子" in label:
            has_ebook = True
    if paper is None:
        return None
    data = {}
    for th in paper.find_all("th"):
        td = th.find_next_sibling("td")
        if td is not None:
            data[th.get_text(strip=True)] = td.get_text(" ", strip=True)
    title_el = soup.select_one("div.title h1")
    authors = []
    author_box = soup.select_one("div.title .author_list")
    if author_box is not None:
        names = [clean_title(e.get_text()) for e in author_box.find_all(["a", "span"]) if clean_title(e.get_text())]
        if not names:
            names = [n for n in re.split(r"[\s　／/]+", author_box.get_text(" ", strip=True)) if n]
        authors = [{"name": n, "role": None} for n in dict.fromkeys(names)]
    return {
        "title": clean_title(title_el.get_text()) if title_el else None,
        "isbn13": isbn13(data.get("ISBN", "")),
        "release_date": parse_date(data.get("発売日", "")),
        "price": parse_price(data.get("定価", "")),
        "has_ebook": has_ebook,
        "authors": authors,
    }


def fetch(client, conn, publisher_id, months, log, known=None):
    targets = {}
    for url in LIST_URLS:
        items, excluded = parse_list(client.get(url))
        log(f"{NAME} {url.rsplit('/', 1)[-1]}: 一覧 {len(items)} 件（ラノベ・小説で除外 {excluded} 件）")
        for item in items:
            targets.setdefault(item["isbn13"], item)
    out, skipped = [], 0
    for code, item in targets.items():
        url = DETAIL_URL.format(isbn=code)
        detail = parse_detail(client.get(url))
        if detail is None or not detail["isbn13"]:
            skipped += 1
            continue
        out.append(
            BookRecord(
                source_key=f"{SLUG}:{detail['isbn13']}",
                title_raw=detail["title"] or item["title"],
                release_date=detail["release_date"],
                isbn13=detail["isbn13"],
                price=detail["price"],
                has_ebook=detail["has_ebook"],
                authors=detail["authors"],
                source_url=url,
            )
        )
    log(f"{NAME}: 取得 {len(out)} 件（紙版なしで除外 {skipped} 件）")
    return out
