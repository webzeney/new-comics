"""秋田書店：「これから発売予定」と「コミックス一覧」、書籍ページから取得する。

一覧の書名は途中で省略されるので、書名・著者・定価・レーベルは書籍ページから取る。
書籍ページの URL の数字は ISBN-10 なので、ISBN はそこから求める。一度取った本は書籍ページを開き直さない。
"""
import json
import re

import requests

from bs4 import BeautifulSoup

from ..normalize import clean_title, isbn13, isbn10_to_13, parse_date, parse_price
from ..store import BookRecord

SLUG = "akitashoten"
NAME = "秋田書店"
BASE = "https://www.akitashoten.co.jp"
SOURCE_URL = BASE + "/comics/comingsoon"
FETCH_METHOD = "HTML"
COMING_URL = BASE + "/comics/comingsoon/1?page={page}"
RELEASED_URL = BASE + "/comics?type=0&page={page}"
MAX_PAGES = 30
BOOK = re.compile(r"/comics/(\d{9}[\dXx])$")
EXCLUDED_KINDS = {"マルチメディア"}


def parse_list(html):
    soup = BeautifulSoup(html, "lxml")
    items = []
    for book in soup.select("div.book"):
        a = book.find("a", href=True)
        m = BOOK.search(a["href"]) if a else None
        date_el = book.select_one(".date")
        if not m or date_el is None:
            continue
        kinds = [clean_title(s.get_text()) for s in book.select(".bookInfo span") if "date" not in (s.get("class") or []) and "authorName" not in (s.get("class") or [])]
        items.append({
            "code": m.group(1),
            "url": BASE + "/comics/" + m.group(1),
            "release_date": parse_date(date_el.get_text()),
            "excluded": any(k in EXCLUDED_KINDS for k in kinds),
        })
    return items


def parse_detail(html):
    soup = BeautifulSoup(html, "lxml")
    side = soup.select_one(".detailSide")
    if side is None or soup.title is None:
        return None
    title = clean_title(re.sub(r"\s*[|｜]\s*秋田書店\s*$", "", soup.title.get_text()))
    data = {}
    for li in side.select("ul > li"):
        text = clean_title(li.get_text())
        key, sep, value = text.partition("：")
        if sep:
            data[key] = value.strip()
    authors = [{"name": clean_title(n), "role": None} for n in re.split(r"[/／]", data.get("著者", "")) if clean_title(n)]
    date_el = soup.select_one(".imageSide .date")
    return {
        "title": title or None,
        "authors": authors,
        "price": parse_price(data.get("定価", "")),
        "isbn13": isbn13(data.get("ISBN", "")),
        "label": data.get("レーベル") or None,
        "release_date": parse_date(date_el.get_text()) if date_el else None,
    }


def collect(client, url, start, end, log):
    found = []
    for page in range(1, MAX_PAGES + 1):
        try:
            html = client.get(url.format(page=page))
        except requests.HTTPError as exc:
            if exc.response is not None and exc.response.status_code == 404:
                break
            raise
        items = parse_list(html)
        if not items:
            break
        found.extend(i for i in items if i["release_date"] and start <= i["release_date"] <= end)
        if all(i["release_date"] and i["release_date"] < start for i in items):
            break
    return found


def fetch(client, conn, publisher_id, months, log, known=None):
    known = known or {}
    start = f"{months[0][0]:04d}-{months[0][1]:02d}-01"
    end = f"{months[-1][0]:04d}-{months[-1][1]:02d}-31"
    items = collect(client, COMING_URL, start, end, log) + collect(client, RELEASED_URL, start, end, log)
    seen, out, excluded = set(), [], 0
    for item in sorted(items, key=lambda i: i["release_date"]):
        if item["code"] in seen:
            continue
        seen.add(item["code"])
        if item["excluded"]:
            excluded += 1
            continue
        key = f"{SLUG}:{item['code']}"
        prev = known.get(key)
        if prev is not None and prev["title_raw"]:
            out.append(BookRecord(
                source_key=key, title_raw=prev["title_raw"], release_date=item["release_date"],
                isbn13=prev["isbn13"] or isbn10_to_13(item["code"]), price=prev["price"],
                authors=json.loads(prev["authors"] or "[]"), source_url=item["url"],
            ))
            continue
        detail = parse_detail(client.get(item["url"]))
        if detail is None or not detail["title"]:
            continue
        out.append(BookRecord(
            source_key=key, title_raw=detail["title"], release_date=detail["release_date"] or item["release_date"],
            isbn13=detail["isbn13"] or isbn10_to_13(item["code"]), price=detail["price"], label=detail["label"],
            authors=detail["authors"], source_url=item["url"],
        ))
    log(f"{NAME}: 取得 {len(out)} 件（対象外 {excluded} 件）")
    return out
