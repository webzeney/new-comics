import hashlib
import re

from bs4 import BeautifulSoup, NavigableString

from ..normalize import clean_title, nfkc
from ..store import BookRecord

SLUG = "shonengahosha"
NAME = "少年画報社"
SOURCE_URL = "https://www.shonengahosha.co.jp/cal.php"
FETCH_METHOD = "HTML"
KIND_COMICS = "コミックス"


def month_url(year, month):
    return f"{SOURCE_URL}?release={year:04d}-{month:02d}"


def _authors(text):
    text = clean_title(text).lstrip("/／").strip()
    if not text:
        return []
    return [{"name": clean_title(n), "role": None} for n in re.split(r"[／/]", text) if clean_title(n)]


def _source_key(title, release_date, links):
    for href in links:
        m = re.search(r"7net\.omni7\.jp/detail/(\d+)", href)
        if m:
            return f"{SLUG}:7net:{m.group(1)}"
    for href in links:
        m = re.search(r"books\.rakuten\.co\.jp/rb/(\d+)", href)
        if m:
            return f"{SLUG}:rb:{m.group(1)}"
    digest = hashlib.sha1(f"{title}|{release_date}".encode()).hexdigest()[:12]
    return f"{SLUG}:t:{digest}"


def parse_month(html, year, month):
    soup = BeautifulSoup(html, "lxml")
    table = soup.find("table")
    if table is None:
        return [], []
    records, skipped = [], []
    for row in table.find_all("tr"):
        th, td = row.find("th"), row.find("td")
        if th is None or td is None:
            continue
        day = re.match(r"\s*(\d{1,2})", nfkc(th.get_text()))
        kind_el = td.find("span")
        kind = kind_el.get_text(strip=True) if kind_el else ""
        title_el = td.find("b")
        if not day or title_el is None:
            continue
        title = clean_title(title_el.get_text())
        if kind != KIND_COMICS:
            skipped.append((kind, title))
            continue
        author_text = ""
        node = title_el.next_sibling
        while node is not None and not (getattr(node, "name", None) == "br"):
            author_text += node if isinstance(node, NavigableString) else node.get_text()
            node = node.next_sibling
        release_date = f"{year:04d}-{month:02d}-{int(day.group(1)):02d}"
        links = [a.get("href", "") for a in td.find_all("a")]
        records.append(
            BookRecord(
                source_key=_source_key(title, release_date, links),
                title_raw=title,
                release_date=release_date,
                authors=_authors(author_text),
                source_url=month_url(year, month),
            )
        )
    return records, skipped


def fetch(client, conn, publisher_id, months, log, known=None):
    out = []
    for year, month in months:
        html = client.get(month_url(year, month))
        records, skipped = parse_month(html, year, month)
        log(f"{NAME} {year}-{month:02d}: コミックス {len(records)} 件（対象外 {len(skipped)} 件）")
        out.extend(records)
    return out
