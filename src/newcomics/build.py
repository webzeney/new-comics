"""データベースから静的ページを生成する。

使い方: PYTHONPATH=src python3 -m newcomics.build [--out dist]
"""
import argparse
import calendar as calmod
import hashlib
import html
import json
import os
import re
import shutil
import sqlite3
import time
import unicodedata
from collections import Counter, OrderedDict, defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote
from xml.sax.saxutils import escape as xml_escape

import holidays as holidays_lib

from . import db, yomi
from .normalize import isbn13_to_10, series_name
from .render import Writer, page_defaults

DOWS = ["月", "火", "水", "木", "金", "土", "日"]
SITE_NAME = "漫画新刊JP"
UPDATES_PER_PAGE = 40
UPDATE_KINDS = [
    ("", None, "すべての更新", "発売日の変更・決定は、今のところありません。"),
    ("change", "日付変更", "発売日の変更", "発売日が変更された本は、今のところありません。"),
    ("fixed", "日付決定", "発売日の決定", "発売日が決定した本は、今のところありません。"),
]
TOP_BOOKS = 20  # PC は幅に合わせて「1段の数×2」だけ表示する（JavaScript で調整）
TOP_BOOKS_BASE = 8  # スマホと JavaScript が動かないときに表示する数
TAG_INFO = {
    "new-series": ("新シリーズ1巻", "シリーズの1巻として発売される新刊です。"),
    "final": ("完結巻", "最終巻・完結巻として発売される新刊です。"),
    "special-edition": ("特装版・限定版", "特装版・限定版として発売される新刊です。"),
    "ebook": ("電子同時配信", "紙の単行本と同時に電子版も配信される新刊です。"),
}


def dow(d):
    return DOWS[d.weekday()]


def md(d):
    return f"{d.month}/{d.day}"


def jst_today():
    return datetime.now(db.JST).date()


def parse(d):
    return date.fromisoformat(d) if d else None


AFFILIATE_HGC = re.compile(r"^https://hb\.afl\.rakuten\.co\.jp/hgc/([^/?#]+)/")
RAKUTEN_AFFILIATE_LINK = re.compile(r"^(https://hb\.afl\.rakuten\.co\.jp/(?:hgc|ichiba)/[^/?#]+/)(?:_RTLink\d+)?(\?.*)$")


def rakuten_link(url, link_id):
    """楽天アフィリエイトのリンクに計測ID（_RTLink + 番号）を入れる。アフィリエイトのリンクでないものはそのまま返す。"""
    m = RAKUTEN_AFFILIATE_LINK.match(url or "")
    if not m or not re.fullmatch(r"_RTLink\d+", link_id or ""):
        return url
    return f"{m.group(1)}{link_id}{m.group(2)}"


UTC_TZ = timezone.utc


class Book:
    __slots__ = (
        "id", "isbn13", "title", "volume", "series_id", "publisher", "publisher_slug", "label", "label_id", "authors",
        "release", "price", "has_ebook", "edition", "is_final", "asin", "rakuten_url", "origin", "image", "cover_url", "seven_ok", "first_seen", "tags", "key", "title_kana", "kobo_url", "updated", "kindle_asin", "amazon_isbn_ok", "amazon_image", "amazon_image_at",
    )

    def __init__(self, row, tags):
        self.id = row["id"]
        self.isbn13 = row["isbn13"]
        self.title = row["title"]
        self.volume = row["volume"]
        self.series_id = row["series_id"]
        self.publisher = row["publisher"]
        self.publisher_slug = row["publisher_slug"]
        self.label = row["label"]
        self.label_id = row["label_id"]
        self.authors = json.loads(row["authors"] or "[]")
        self.release = parse(row["release_date"])
        self.price = row["price"]
        self.has_ebook = None if row["has_ebook"] is None else bool(row["has_ebook"])
        self.edition = row["edition"]
        self.is_final = bool(row["is_final"])
        self.asin = row["asin"]
        self.amazon_isbn_ok = row["amazon_isbn_ok"] if "amazon_isbn_ok" in row.keys() else None
        self.amazon_image = row["amazon_image_url"] if "amazon_image_url" in row.keys() else None
        self.amazon_image_at = row["amazon_image_at"] if "amazon_image_at" in row.keys() else None
        self.rakuten_url = row["rakuten_url"] if "rakuten_url" in row.keys() else None
        self.origin = row["origin"] if "origin" in row.keys() else "publisher"
        image = row["image_url"] if "image_url" in row.keys() else None
        # 楽天の書影は、楽天の商品ページへのリンクがあるときだけ使う（書籍詳細ページのメインの書影のリンク先になる。出版社サイトの本は楽天へのリンクがあるときだけ書影を出す）
        if self.origin == "rakuten":
            self.image, self.cover_url = image, (self.rakuten_url if image else None)
        elif image and self.rakuten_url:
            self.image, self.cover_url = image, self.rakuten_url
        else:
            self.image, self.cover_url = None, None
        self.seven_ok = row["seven_ok"] if "seven_ok" in row.keys() else None
        self.title_kana = row["title_kana"] if "title_kana" in row.keys() else None
        self.kobo_url = row["kobo_url"] if "kobo_url" in row.keys() else None
        self.kindle_asin = row["kindle_asin"] if "kindle_asin" in row.keys() else None
        self.first_seen = row["first_seen_at"]
        self.updated = row["updated_at"] if "updated_at" in row.keys() else None
        self.tags = tags
        self.key = self.isbn13 or f"b{self.id}"

    @property
    def is_first(self):
        return self.volume == 1


class Site:
    def __init__(self, conn, today, env):
        self.conn = conn
        self.today = today
        self.env = env
        self.jp_holidays = holidays_lib.Japan(years=range(today.year - 1, today.year + 3))
        tag_rows = defaultdict(set)
        for r in conn.execute("SELECT bt.book_id, t.slug FROM book_tags bt JOIN tags t ON t.id = bt.tag_id"):
            tag_rows[r["book_id"]].add(r["slug"])
        rows = conn.execute(
            "SELECT b.*, p.name AS publisher, p.slug AS publisher_slug, l.name AS label "
            "FROM books b JOIN publishers p ON p.id = b.publisher_id LEFT JOIN labels l ON l.id = b.label_id "
            "WHERE (l.is_adult IS NULL OR l.is_adult = 0) AND p.is_adult = 0"
        ).fetchall()
        self.books = [Book(r, tag_rows[r["id"]]) for r in rows]
        # 楽天の検索ページを楽天アフィリエイトのリンクにするための ID（取り込んだ本のリンクで一番多いもの）
        hgc = Counter(m.group(1) for m in (AFFILIATE_HGC.match(r["rakuten_url"] or "") for r in rows) if m)
        self.rakuten_hgc = hgc.most_common(1)[0][0] if hgc else None
        link_id = env.get("RAKUTEN_LINK_ID")
        if link_id:
            for b in self.books:
                b.rakuten_url = rakuten_link(b.rakuten_url, link_id)
                b.cover_url = rakuten_link(b.cover_url, link_id)
                b.kobo_url = rakuten_link(b.kobo_url, link_id)
        self.by_id = {b.id: b for b in self.books}
        self.series = {r["id"]: dict(r) for r in conn.execute("SELECT * FROM series")}
        self.dated = sorted([b for b in self.books if b.release], key=lambda b: (b.release, b.publisher, b.title))
        self.by_date = OrderedDict()
        for b in self.dated:
            self.by_date.setdefault(b.release, []).append(b)
        self.publishers = self._publishers()
        self.series_books = defaultdict(list)
        for b in self.dated:
            if b.series_id:
                self.series_books[b.series_id].append(b)

    def _publishers(self):
        counts = defaultdict(int)
        slugs = {}
        for b in self.books:
            counts[b.publisher] += 1
            slugs[b.publisher] = b.publisher_slug
        return [{"name": n, "slug": slugs[n], "count": counts[n]} for n in sorted(counts, key=lambda n: (-counts[n], n))]

    # ---- 共通の値 ----
    def book_url(self, root, b):
        return f"{root}book/{b.key}/"

    def amazon_asin(self, b):
        """Amazon の紙の本の ASIN。ISBN-10 の商品ページがないと分かった本は、照らし合わせで見つけた ASIN にする。"""
        if b.isbn13 and b.amazon_isbn_ok == 0:
            return b.asin or None
        return isbn13_to_10(b.isbn13) or b.asin or None

    def amazon_url(self, asin=None, search=None, index="stripbooks"):
        """Amazon の商品ページ（asin）か検索結果のページ（search）のアドレス。アソシエイトのタグを付ける。"""
        tag = self.env.get("AMAZON_TAG")
        if asin:
            return f"https://www.amazon.co.jp/dp/{asin}" + (f"?tag={quote(tag)}" if tag else "")
        return f"https://www.amazon.co.jp/s?k={quote(search)}&i={index}" + (f"&tag={quote(tag)}" if tag else "")

    def rakuten_search_url(self, query, extra=""):
        """楽天ブックスの検索結果のページ。取り込んだ本の楽天アフィリエイトの ID が分かれば、アフィリエイトのリンクにする。"""
        url = f"https://books.rakuten.co.jp/search?sitem={quote(query)}{extra}"
        if not self.rakuten_hgc:
            return url
        return rakuten_link(f"https://hb.afl.rakuten.co.jp/hgc/{self.rakuten_hgc}/?pc={quote(url, safe='')}", self.env.get("RAKUTEN_LINK_ID"))

    def main_cover(self, b):
        """書籍詳細ページのメインの書影とリンク先。Amazon の書影（取得から24時間以内）があれば Amazon の商品ページへ、
        なければ楽天の書影と楽天の商品ページ。Amazon の書影はここでだけ使う（一覧などは楽天の書影のまま）。"""
        asin = self.amazon_asin(b)
        if b.amazon_image and asin and b.amazon_image_at:
            try:
                fresh = datetime.now(db.JST) - datetime.fromisoformat(b.amazon_image_at) < timedelta(hours=AMAZON_IMAGE_HOURS)
            except ValueError:
                fresh = False
            if fresh:
                return b.amazon_image, self.amazon_url(asin)
        return b.image, b.cover_url

    def cart(self):
        """「まとめてAmazonのカートへ」のバーに渡す値。"""
        return {"tag": self.env.get("AMAZON_TAG") or ""}

    def stores(self, b):
        q = b.isbn13 or b.title
        # ISBN が分かる本は Amazon・セブンネットとも商品ページへ（Amazon に ISBN-10 のページがない本は、ISBN-13 で見つけた ASIN。
        # それもなければ ISBN の検索ページ）。ISBN が分からない本は、Amazon の照らし合わせで見つかった ASIN、
        # それもなければ書名の検索ページにする（ISBN をあとから取り込んだときは、照らし合わせの結果より ISBN を優先する）
        asin = self.amazon_asin(b)
        amazon = self.amazon_url(asin) if asin else self.amazon_url(search=q)
        rakuten = b.rakuten_url or self.rakuten_search_url(q)
        seven = f"https://7net.omni7.jp/detail_isbn/{b.isbn13}" if b.isbn13 else f"https://7net.omni7.jp/search/?keyword={quote(q)}"
        out = [
            {"name": "Amazon", "short": "Amazon", "kind": "amazon", "button": "Amazon", "url": amazon},
            {"name": "楽天ブックス", "short": "楽天", "kind": "rakuten", "button": "楽天ブックス", "url": rakuten},
        ]
        # 以前の確認（2026-11 まで毎晩行っていた）でセブンネットに取り扱いがないと分かった本は、セブンネットのボタンを出さない
        if b.seven_ok != 0:
            out.append({"name": "セブンネットショッピング", "short": "セブンネット", "words": ["セブン", "ネット"], "kind": "seven", "button": "セブンネット", "url": seven})
        return out

    def ebook_stores(self, b):
        """電子版のボタン。電子版ありと分かっている本には Kindle と楽天Kobo、
        電子版の有無が分からない本には、照らし合わせで見つかったストアだけを出す（2026-11-06 運営者の判断）。

        Kindle・楽天Kobo とも、照らし合わせで見つかった本は商品ページ、それ以外は検索結果のページ。
        """
        if b.has_ebook is False:
            return []
        if b.has_ebook is None and not (b.kindle_asin or b.kobo_url):
            return []
        q = unicodedata.normalize("NFKC", b.title)
        kindle = self.amazon_url(b.kindle_asin) if b.kindle_asin else self.amazon_url(search=q, index="digital-text")
        kobo = b.kobo_url or self.rakuten_search_url(q, "&g=101")
        out = []
        if b.has_ebook or b.kindle_asin:
            out.append({"name": "Kindle", "url": kindle})
        if b.has_ebook or b.kobo_url:
            out.append({"name": "楽天Kobo", "url": kobo})
        return out

    @staticmethod
    def author_text(b):
        parts = []
        for a in b.authors:
            parts.append(f"{a['role']}：{a['name']}" if a.get("role") and a["role"] != "著" else a["name"])
        return "／".join(parts)

    @staticmethod
    def price_text(b):
        return f"定価 ¥{b.price:,}" if b.price else ""

    def meta(self, b, keys):
        values = {"author": self.author_text(b), "label": b.label or "", "price": self.price_text(b)}
        return "・".join(values[k] for k in keys if values[k])

    @staticmethod
    def alt(b):
        main, vol = title_parts(b)
        return f"{main} {vol}巻" if vol else b.title

    def row(self, root, b, keys=("author", "label", "price")):
        return {
            "url": self.book_url(root, b), "title": b.title, "pub": b.publisher, "label": b.label, "ebook": b.has_ebook,
            "first": b.is_first, "meta": self.meta(b, keys), "stores": self.stores(b), "image": b.image, "alt": self.alt(b),
            "asin": self.amazon_asin(b),
        }

    def holiday(self, d):
        return self.jp_holidays.get(d) or ""

    def day_color(self, d):
        if d.weekday() == 6 or self.holiday(d):
            return "red"
        if d.weekday() == 5:
            return "blue"
        return None

    def months(self):
        months = sorted({(d.year, d.month) for d in self.by_date})
        return months

    def tags_for_menu(self):
        # タグのページは発売日の分かる本で作るので、メニューも同じ本で決める（ページのないタグへリンクしない）
        tags = [{"key": f"tag:{slug}", "label": TAG_INFO[slug][0], "path": f"tag/{slug}/"} for slug in TAG_INFO if any(slug in b.tags for b in self.dated)]
        for p in self.publishers[:2]:
            tags.append({"key": f"pub:{p['slug']}", "label": p["name"], "path": f"publisher/{p['slug']}/"})
        return tags


def chunk_months(today, count=3):
    out = []
    y, m = today.year, today.month
    for _ in range(count):
        out.append((y, m))
        m += 1
        if m > 12:
            y, m = y + 1, 1
    return out


def build(conn, out_dir, today, env):
    site = Site(conn, today, env)
    w = Writer(out_dir, site.tags_for_menu(), today.year, ga4_id=env.get("GA4_ID"), adsense_client=env.get("ADSENSE_CLIENT"), site_url=env.get("SITE_URL"), rakuten_credit=any(b.origin == "rakuten" or b.rakuten_url for b in site.books))
    w.ranking = ranking_items(site)
    w.copy_assets()
    AUTHOR_KEYS.clear()
    AUTHOR_KEYS.update(author_key(a["name"]) for b in site.dated for a in b.authors)
    build_top(site, w)
    build_calendars(site, w)
    build_dates(site, w)
    build_today(site, w)
    build_week(site, w)
    build_books(site, w)
    build_series(site, w)
    build_listings(site, w)
    build_authors(site, w)
    build_series_feeds(site, w, env.get("SITE_URL"))
    build_series_calendars(site, w, env.get("SITE_URL"))
    build_favorites(site, w)
    build_search(site, w)
    build_updates(site, w)
    build_static(site, w)
    build_sitemap(site, w, env.get("SITE_URL"))
    build_llms(site, w)
    build_partials(site, w)
    return w.count


FEATURE_TRIES = 3
FEATURE_WAIT = 5
FEATURE_CACHE = "assets/features.json"


def fetch_features(api, limit):
    """WordPress の REST API から特集の新しい記事を取る。失敗したら間をあけて FEATURE_TRIES 回までやり直す。"""
    import requests
    last = None
    for attempt in range(FEATURE_TRIES):
        if attempt:
            time.sleep(FEATURE_WAIT * attempt)
        try:
            res = requests.get(api, params={"per_page": limit, "_embed": "wp:term", "_fields": "title,link,_embedded,_links"}, timeout=20)
            res.raise_for_status()
            return res.json()
        except Exception as exc:
            last = exc
    raise last


def load_features(env, limit=3, base=None):
    """特集（WordPress）の新しい記事を、REST API から取る。

    取れたときは公開しているサイトに assets/features.json として書き出しておき、
    やり直しても取れないときは、前回の公開分（公開中の features.json）を使う。それも取れなければ空にする。
    """
    api = env.get("FEATURE_API")
    if not api:
        return []
    try:
        posts = fetch_features(api, limit)
    except Exception as exc:
        print(f"特集記事を取得できませんでした：{exc}")
        if base:
            try:
                import requests
                res = requests.get(f"{base}/{FEATURE_CACHE}", timeout=20)
                res.raise_for_status()
                cached = res.json()
                if isinstance(cached, list) and cached:
                    print(f"前回の公開分の特集記事 {len(cached)} 件を使います")
                    return cached[:limit]
            except Exception as exc2:
                print(f"前回の公開分の特集記事も取得できませんでした：{exc2}")
        return []
    out = []
    for i, post in enumerate(posts[:limit], 1):
        terms = [t for group in (post.get("_embedded") or {}).get("wp:term", []) for t in group if t.get("taxonomy") == "category"]
        out.append({
            "no": f"{i:02d}",
            "tag": terms[0]["name"] if terms else "特集",
            "title": html.unescape((post.get("title") or {}).get("rendered", "")),
            "url": post.get("link"),
        })
    return out


def build_partials(site, w):
    """特集（WordPress）のテーマで使う、サイドメニューとフッターの部品を書き出す。"""
    from .render import site_context
    ctx = {
        "root": "/",
        "page": {"menu": "feature", "tag": None, "footer": None},
        "site": site_context("/", w.tags, w.year, w.rakuten_credit, w.ranking),
    }
    dest = Path(w.out) / "assets" / "partials"
    dest.mkdir(parents=True, exist_ok=True)
    for name in ("sidemenu", "footer"):
        (dest / f"{name}.html").write_text(w.env.get_template(f"_{name}.html").render(**ctx), encoding="utf-8")
    ga = w.env.get_template("_analytics.html").render(ga4_id=w.ga4_id, adsense_client=w.adsense_client)
    (dest / "analytics.html").write_text(ga, encoding="utf-8")
    build_bookrows(site, w, dest / "bookrow")


def build_bookrows(site, w, dest):
    """特集記事の [books isbn="…"] で使う、本1冊分の欄を本ごとに書き出す（ファイル名は詳細ページと同じキー）。"""
    dest.mkdir(parents=True, exist_ok=True)
    tpl = w.env.from_string('{% from "_parts.html" import bookrow %}{{ bookrow(b, b.pub, b.meta, final_badge=final) }}')
    for book in site.books:
        html_text = tpl.render(b=site.row("/", book), final=book.is_final)
        (dest / f"{book.key}.html").write_text(re.sub(r"\n{2,}", "\n", html_text).strip() + "\n", encoding="utf-8")


PAGER_SIZE = 4


def pager_items(current, last):
    """ページ送りの並び。番号は最大4つ。「最初」は1ページ目が番号にないとき、「前へ」は1ページ目以外、「次へ」は最後のページ以外、「最後」は最後のページが番号にないときに出す。"""
    if last <= 1:
        return []
    start = max(1, min(current - 1, last - PAGER_SIZE + 1))
    end = min(last, start + PAGER_SIZE - 1)
    items = []
    if start > 1:
        items.append(("first", 1, "« 最初"))
    if current > 1:
        items.append(("prev", current - 1, "‹ 前へ"))
    for k in range(start, end + 1):
        items.append(("num", k, str(k)))
    if current < last:
        items.append(("next", current + 1, "次へ ›"))
    if end < last:
        items.append(("last", last, "最後 »"))
    return items


# ---- 構造化データ（JSON-LD） ----
def site_base(site):
    return (site.env.get("SITE_URL") or "https://new-comics.jp").rstrip("/")


def jsonld(*objs):
    """検索エンジンや AI 向けに、ページの中身を機械が読める形（schema.org）で書く。"""
    data = [dict({"@context": "https://schema.org"}, **o) for o in objs]
    text = json.dumps(data[0] if len(data) == 1 else data, ensure_ascii=False, separators=(",", ":"))
    return text.replace("</", "<\\/")


def breadcrumb_ld(base, items):
    """items は（名前, サイト内のパス）の並び。最後はそのページ自身。"""
    return {"@type": "BreadcrumbList", "itemListElement": [
        {"@type": "ListItem", "position": i, "name": name, "item": base + path} for i, (name, path) in enumerate(items, start=1)
    ]}


def book_ld(site, b):
    base = site_base(site)
    url = f"{base}/book/{b.key}/"
    data = {"@type": "Book", "@id": url, "url": url, "name": b.title, "inLanguage": "ja", "genre": "漫画",
            "publisher": {"@type": "Organization", "name": b.publisher, "url": f"{base}/publisher/{b.publisher_slug}/"}}
    if b.isbn13:
        data["isbn"] = b.isbn13
    if b.authors:
        data["author"] = [{"@type": "Person", "name": a["name"]} for a in b.authors]
    if b.release:
        data["datePublished"] = b.release.isoformat()
    if b.volume:
        data["volumeNumber"] = str(b.volume)
    if b.series_id in site.series:
        data["isPartOf"] = {"@type": "BookSeries", "name": site.series[b.series_id]["name"], "url": f"{base}/series/{b.series_id}/"}
    return data


def series_ld(site, sid, name, vols, latest):
    base = site_base(site)
    url = f"{base}/series/{sid}/"
    data = {"@type": "BookSeries", "@id": url, "url": url, "name": name, "inLanguage": "ja", "genre": "漫画",
            "publisher": {"@type": "Organization", "name": latest.publisher, "url": f"{base}/publisher/{latest.publisher_slug}/"},
            "hasPart": [{"@type": "Book", "@id": f"{base}/book/{b.key}/", "url": f"{base}/book/{b.key}/", "name": b.title}
                        | ({"isbn": b.isbn13} if b.isbn13 else {}) | ({"datePublished": b.release.isoformat()} if b.release else {})
                        | {"volumeNumber": str(b.volume)} for b in vols]}
    if latest.authors:
        data["author"] = [{"@type": "Person", "name": a["name"]} for a in latest.authors]
    return data


def date_ld(site, d, books):
    """日付ページ：その日に発売される本の一覧（ItemList）。"""
    base = site_base(site)
    return {"@type": "ItemList", "name": f"{d.year}年{d.month}月{d.day}日発売の漫画・コミック新刊", "numberOfItems": len(books),
            "itemListElement": [{"@type": "ListItem", "position": i, "url": f"{base}/book/{b.key}/", "name": b.title} for i, b in enumerate(books, start=1)]}


ZEN_DIGITS = str.maketrans("０１２３４５６７８９", "0123456789")


def display_title(b, main=None, vol=None):
    """ページのタイトル（title タグ）用の書名。巻数が読み取れた本は「作品名 N巻」、全角の数字は半角にそろえる。"""
    if main and vol and b.title.translate(ZEN_DIGITS).replace(" ", "").endswith(str(vol)):
        return f"{main} {vol}巻".translate(ZEN_DIGITS)
    return b.title.translate(ZEN_DIGITS)


def jp_day(d):
    return f"{d.year}年{d.month}月{d.day}日"


def series_title(site, name, latest, vol):
    """作品ページのタイトル。「（作品名） 最新刊 発売日」で探す人に合わせる。"""
    if vol and latest.release:
        if latest.release > site.today:
            return f"{name}の最新刊{vol}巻はいつ発売？ 発売日・既刊一覧｜{SITE_NAME}"
        return f"{name}の最新刊は{vol}巻（{jp_day(latest.release)}発売） 既刊一覧｜{SITE_NAME}"
    return f"{name}の新刊・既刊一覧（{latest.publisher}）｜{SITE_NAME}"


def series_description(site, name, latest, vol, count):
    """作品ページの説明文。最初に答え（最新刊の巻数と発売日）を書く。"""
    if vol and latest.release:
        verb = "発売予定です" if latest.release > site.today else ("発売されます" if latest.release == site.today else "発売されました")
        known = f"既刊{count}冊" if str(vol).isdigit() and count == int(vol) else "既刊"
        return f"{name}（{latest.publisher}）の最新刊は{vol}巻で、{jp_day(latest.release)}に{verb}。{known}の発売日をまとめています。"
    return f"{name}（{latest.publisher}）の最新刊と既刊の発売日をまとめています。"


def crumbs(root, *items):
    out = [{"label": "トップ", "url": root or "./"}]
    for label, url in items:
        out.append({"label": label, "url": url} if url else {"label": label})
    return out


# ---- トップ ----
def tomorrow_card(site, tomorrow):
    """トップの「TOMORROW」。明日発売の本がない日は、リンクにせず「ありません」と出し、次の発売日へ案内する。"""
    card = {"label": f"{md(tomorrow)}（{dow(tomorrow)}）", "url": None, "next": None}
    if tomorrow in site.by_date:
        card["url"] = f"date/{tomorrow.isoformat()}/"
    else:
        nxt = min((d for d in site.by_date if d > tomorrow), default=None)
        if nxt:
            card["next"] = {"label": f"{md(nxt)}（{dow(nxt)}）", "url": f"date/{nxt.isoformat()}/"}
    return card


def build_top(site, w):
    root = ""
    today, tomorrow = site.today, site.today + timedelta(days=1)

    def release(d, word):
        books = site.by_date.get(d, [])
        cards = []
        for b in books[:TOP_BOOKS]:
            bubble, kind = ("今日発売！", None) if word == "今日" else ("明日発売", "tomorrow")
            if b.is_first:
                bubble, kind = "新シリーズ", "first"
            if b.is_final:
                bubble, kind = "完結", "final"
            label_price = "・".join(x for x in (b.label, site.price_text(b)) if x)
            cards.append({
                "url": site.book_url(root, b), "title": b.title, "pub": b.publisher, "ebook": b.has_ebook,
                "author": site.author_text(b), "label_price": label_price, "bubble": bubble, "bubble_kind": kind, "stores": site.stores(b),
                "image": b.image, "alt": site.alt(b),
            })
        more = f"date/{d.isoformat()}/" if books else None
        empty = "本日発売の新刊はありません" if word == "今日" else f"{word}発売の新刊はありません"
        return {"word": word, "date": md(d), "books": cards, "more_url": more, "empty": empty, "base": TOP_BOOKS_BASE}

    ticker = [b.title for b in site.by_date.get(today, [])]
    updates = latest_updates(site, root, 8)
    ctx = {
        "ticker": ticker + ticker if ticker else ["本日発売の新刊はありません"] * 2,
        "ticker_static": not ticker,
        "search": search_options(site),
        "calendar": {"url": f"calendar/{today.year}/{today.month:02d}/", "month": today.month},
        "tomorrow": tomorrow_card(site, tomorrow),
        "releases": [release(today, "今日"), release(tomorrow, "明日")],
        "updates": updates,
        "features": load_features(site.env, base=site_base(site)),
    }
    if ctx["features"]:
        cache = Path(w.out) / FEATURE_CACHE
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(json.dumps(ctx["features"], ensure_ascii=False), encoding="utf-8")
    page = page_defaults(
        title=f"{SITE_NAME}｜漫画・コミックの新刊発売日カレンダー",
        description="漫画・コミックの新刊発売日を、カレンダーや出版社・作品ごとに探せる情報サイト。今日・明日発売の漫画新刊から来月の発売予定まで、毎日自動で更新しています。",
        menu="top", is_top=True, lastmod=site.today.isoformat(),
        jsonld=jsonld({
            "@type": "WebSite", "name": SITE_NAME, "url": site_base(site) + "/", "inLanguage": "ja",
            "description": "漫画・コミックの新刊発売日を、出版社の公式サイトの情報をもとに毎日自動で更新している情報サイト。",
            "potentialAction": {"@type": "SearchAction", "target": site_base(site) + "/search/?q={search_term_string}", "query-input": "required name=search_term_string"},
        }),
    )
    w.write("index.html", "index.html", page, **ctx)


def search_options(site):
    labels = sorted({b.label for b in site.books if b.label})
    months = [{"value": f"{y}-{m:02d}", "label": f"{y}年{m}月"} for y, m in site.months()]
    return {"publishers": [p["name"] for p in site.publishers], "labels": labels, "months": months}


def update_detail(kind, old, new):
    def short(v):
        return md(date.fromisoformat(v)) if v else "未定"
    if kind == "NEW":
        return f"{short(new)} 発売" if new else "発売日未定"
    return f"{short(old)} → {short(new)}"


def change_rows(site, kind=None):
    rows = site.conn.execute("SELECT * FROM change_log WHERE kind IN ('日付変更', '日付決定') ORDER BY detected_at DESC, id DESC").fetchall()
    return [r for r in rows if r["book_id"] in site.by_id and (kind is None or r["kind"] == kind)]


def latest_updates(site, root, limit):
    out = []
    for r in change_rows(site)[:limit]:
        b = site.by_id[r["book_id"]]
        d = datetime.fromisoformat(r["detected_at"]).date()
        out.append({"date": md(d), "kind": r["kind"], "title": b.title, "url": site.book_url(root, b), "detail": update_detail(r["kind"], r["old_value"], r["new_value"])})
    return out


# ---- カレンダー ----
def build_calendars(site, w):
    months = site.months()
    for i, (y, m) in enumerate(months):
        rel = f"calendar/{y}/{m:02d}/index.html"
        root = "../../../"
        page, ctx = calendar_context(site, root, y, m, months)
        if (y, m) == (site.today.year, site.today.month) and w.site_url:
            page["canonical"] = f"{w.site_url}/calendar/"
        w.write(rel, "calendar.html", page, **ctx)
    y, m = site.today.year, site.today.month
    if (y, m) in months:
        page, ctx = calendar_context(site, "../", y, m, months)
        page["canonical"] = None
        w.write("calendar/index.html", "calendar.html", page, **ctx)


def calendar_context(site, root, y, m, months):
    days_in_month = calmod.monthrange(y, m)[1]
    first = date(y, m, 1)
    lead = (first.weekday() + 1) % 7
    days = {d: site.by_date.get(date(y, m, d), []) for d in range(1, days_in_month + 1)}
    total = sum(len(v) for v in days.values())
    active = [d for d, v in days.items() if v]
    peak = max(active, key=lambda d: (len(days[d]), -d)) if active else None
    cells = [{"blank": True} for _ in range(lead)]
    for d in range(1, days_in_month + 1):
        dt = date(y, m, d)
        books = days[d]
        cells.append({
            "blank": False, "day": d, "count": len(books), "holiday": site.holiday(dt), "titles": [b.title for b in books[:2]],
            "aria": f"{m}月{d}日（{dow(dt)}）{len(books)}点", "color": site.day_color(dt),
        })
    while len(cells) % 7:
        cells.append({"blank": True})
    list_days = []
    for d in active:
        dt = date(y, m, d)
        list_days.append({
            "date": md(dt), "dow": dow(dt), "holiday": site.holiday(dt), "count": len(days[d]), "color": site.day_color(dt),
            "titles": [{"url": site.book_url(root, b), "title": b.title} for b in days[d]],
        })
    if site.today.year == y and site.today.month == m and site.today.day in active:
        sel = site.today.day
    else:
        future = [d for d in active if date(y, m, d) >= site.today]
        sel = future[0] if future else (active[0] if active else 1)
    sel_date = date(y, m, sel)
    idx = months.index((y, m))
    nav = []
    for j in range(max(0, idx - 1), min(len(months), idx + 2)):
        yy, mm = months[j]
        nav.append({"no": mm, "url": f"{root}calendar/{yy}/{mm:02d}/", "current": j == idx})
    data = {
        "days": {str(d): [compact_row(site, root, b) for b in v] for d, v in days.items() if v},
        "labels": {str(d): f"{m}/{d}（{dow(date(y, m, d))}）" for d in days},
    }
    ctx = {
        "crumbs": crumbs(root, ("新刊カレンダー", f"{root}calendar/"), (f"{y}年{m}月", None)),
        "month": {"no": m, "title": f"{y}年{m}月の漫画新刊カレンダー", "lead": f"{m}月に発売される漫画・コミックの新刊は{total:,}点。日付を選ぶと、その日の新刊が見られます。"},
        "month_nav": nav,
        "stats": {
            "total": f"{total:,}", "active_days": len(active),
            "peak_date": md(date(y, m, peak)) if peak else "—",
            "peak_suffix": f"（{dow(date(y, m, peak))}）{len(days[peak])}点" if peak else "",
        },
        "publishers": [p["name"] for p in site.publishers if any(b.publisher == p["name"] for v in days.values() for b in v)],
        "cells": cells,
        "list_days": list_days,
        "selected": {"day": sel, "label": f"{md(sel_date)}（{dow(sel_date)}）", "books": [site.row(root, b) for b in days.get(sel, [])]},
        "calendar_json": json.dumps(data, ensure_ascii=False).replace("</", "<\\/"),
        "cart": site.cart(),
    }
    page = page_defaults(
        title=f"{y}年{m}月発売の漫画・コミック新刊一覧（発売日カレンダー）｜{SITE_NAME}",
        description=f"{y}年{m}月に発売される漫画・コミックの新刊{total:,}点を、発売日カレンダーと一覧で紹介しています。出版社の発売情報をもとに毎日更新。",
        menu="calendar",
        lastmod=lastmod(site, [b for v in days.values() for b in v]),
    )
    return page, ctx


def compact_row(site, root, b):
    stores = {s["kind"]: s["url"] for s in site.stores(b)}
    return {"url": site.book_url(root, b), "title": b.title, "pub": b.publisher, "meta": site.meta(b, ("author", "label", "price")), "ebook": bool(b.has_ebook), "first": b.is_first, "stores": stores, "i": b.image, "ia": site.alt(b)}


# ---- 日別一覧 ----
def build_dates(site, w):
    dates = list(site.by_date)
    root = "../../"
    for i, d in enumerate(dates):
        books = site.by_date[d]
        groups = OrderedDict()
        for p in site.publishers:
            g = [b for b in books if b.publisher == p["name"]]
            if g:
                groups[p["name"]] = g
        prev_d = dates[i - 1] if i > 0 else None
        next_d = dates[i + 1] if i + 1 < len(dates) else None
        ctx = {
            "crumbs": crumbs(root, ("新刊カレンダー", f"{root}calendar/"), (f"{d.year}年{d.month}月", f"{root}calendar/{d.year}/{d.month:02d}/"), (f"{md(d)}（{dow(d)}）", None)),
            "day": {"md": md(d), "dow": dow(d), "long": f"{d.year}年{d.month}月{d.day}日（{dow(d)}）", "month": d.month},
            "prev": {"md": md(prev_d), "dow": dow(prev_d), "url": f"{root}date/{prev_d.isoformat()}/"} if prev_d else None,
            "next": {"md": md(next_d), "dow": dow(next_d), "url": f"{root}date/{next_d.isoformat()}/"} if next_d else None,
            "stats": {"total": len(books), "first": sum(1 for b in books if b.is_first), "publishers": len(groups)},
            "groups": [{"name": n, "books": [dict(site.row(root, b, ("author", "price")), label=b.label or n) for b in g]} for n, g in groups.items()],
            "cart": site.cart(),
            "calendar_url": f"{root}calendar/{d.year}/{d.month:02d}/",
        }
        page = page_defaults(
            title=f"{d.year}年{d.month}月{d.day}日（{dow(d)}）発売の漫画・コミック新刊{len(books)}点｜{SITE_NAME}",
            description=f"{d.year}年{d.month}月{d.day}日（{dow(d)}）に発売される漫画・コミックの新刊{len(books)}点を出版社別に紹介しています。",
            jsonld=jsonld(date_ld(site, d, books), breadcrumb_ld(site_base(site), [
                ("トップ", "/"), (f"{d.year}年{d.month}月の漫画新刊カレンダー", f"/calendar/{d.year}/{d.month:02d}/"), (f"{d.year}年{d.month}月{d.day}日発売の漫画新刊", f"/date/{d.isoformat()}/")])),
            menu="calendar",
            lastmod=lastmod(site, books),
        )
        w.write(f"date/{d.isoformat()}/index.html", "date.html", page, **ctx)


# ---- 今日発売・今週発売 ----
WEEK_DAY_BOOKS = 8   # 「今週発売」で1日に並べる冊数（残りはその日のページで見る）
TODAY_NEXT_BOOKS = 6  # 「今日発売」の下に並べる、次の発売日の冊数


def popular_first(site, books):
    """よく見られている本 → 新シリーズ1巻 → もとの順。"""
    try:
        views = {r["book_key"]: r["views"] for r in site.conn.execute("SELECT book_key, views FROM page_views")}
    except sqlite3.OperationalError:
        views = {}
    return sorted(books, key=lambda b: (-views.get(b.key, 0), not b.is_first))


def pub_groups(site, root, books):
    groups = OrderedDict()
    for p in site.publishers:
        g = [b for b in books if b.publisher == p["name"]]
        if g:
            groups[p["name"]] = g
    return [{"name": n, "books": [dict(site.row(root, b, ("author", "price")), label=b.label or n) for b in g]} for n, g in groups.items()]


def week_range(today):
    start = today - timedelta(days=today.weekday())
    return start, start + timedelta(days=6)


def build_today(site, w):
    root = "../"
    d = site.today
    books = site.by_date.get(d, [])
    groups = pub_groups(site, root, books)
    nxt = min((x for x in site.by_date if x > d), default=None)
    next_books = popular_first(site, site.by_date.get(nxt, []))[:TODAY_NEXT_BOOKS] if nxt else []
    ctx = {
        "crumbs": crumbs(root, ("今日発売の漫画新刊", None)),
        "day": {"md": md(d), "dow": dow(d), "long": f"{d.year}年{d.month}月{d.day}日（{dow(d)}）"},
        "stats": {"total": len(books), "first": sum(1 for b in books if b.is_first), "publishers": len(groups)},
        "groups": groups,
        "next": {"md": md(nxt), "dow": dow(nxt), "word": "明日" if nxt == d + timedelta(days=1) else None, "url": f"{root}date/{nxt.isoformat()}/", "total": len(site.by_date[nxt]),
                 "books": [site.row(root, b, ("author", "price")) for b in next_books]} if nxt else None,
        "date_url": f"{root}date/{d.isoformat()}/" if books else None,
        "week_url": f"{root}week/",
        "cart": site.cart(),
    }
    page = page_defaults(
        title=f"今日発売の漫画・コミック新刊{len(books)}点（{d.month}月{d.day}日・{dow(d)}）｜{SITE_NAME}" if books else f"今日発売の漫画・コミック新刊（{d.month}月{d.day}日・{dow(d)}）｜{SITE_NAME}",
        description=(f"今日{d.month}月{d.day}日（{dow(d)}）に発売される漫画・コミックの新刊{len(books)}点を出版社別に紹介しています。毎日自動で更新しています。" if books
                     else f"今日{d.month}月{d.day}日（{dow(d)}）に発売される漫画・コミックの新刊はありません。次の発売日の新刊を紹介しています。"),
        jsonld=jsonld(date_ld(site, d, books), breadcrumb_ld(site_base(site), [("トップ", "/"), ("今日発売の漫画新刊", "/today/")])) if books else None,
        menu="today", lastmod=d.isoformat(),
    )
    w.write("today/index.html", "today.html", page, **ctx)


def build_week(site, w):
    root = "../"
    start, end = week_range(site.today)
    days = []
    total = first = 0
    for i in range(7):
        d = start + timedelta(days=i)
        books = site.by_date.get(d, [])
        total += len(books)
        first += sum(1 for b in books if b.is_first)
        picks = popular_first(site, books)[:WEEK_DAY_BOOKS]
        days.append({
            "id": f"d{d.isoformat()}", "md": md(d), "day": d.day, "dow": dow(d), "color": site.day_color(d), "count": len(books),
            "state": "today" if d == site.today else ("past" if d < site.today else "future"),
            "url": f"{root}date/{d.isoformat()}/" if books else None,
            "books": [site.row(root, b, ("author", "label", "price")) for b in picks],
            "rest": len(books) - len(picks),
        })
    peak = max(days, key=lambda x: x["count"])
    ctx = {
        "crumbs": crumbs(root, ("今週発売の漫画新刊", None)),
        "week": {"range": f"{md(start)}（{dow(start)}）〜{md(end)}（{dow(end)}）", "long": f"{start.month}月{start.day}日〜{end.month}月{end.day}日"},
        "stats": {"total": total, "first": first, "peak": peak["md"] if peak["count"] else "－", "peak_dow": f"（{peak['dow']}）" if peak["count"] else ""},
        "days": days,
        "per_day": WEEK_DAY_BOOKS,
        "today_url": f"{root}today/",
        "calendar_url": f"{root}calendar/{site.today.year}/{site.today.month:02d}/",
        "cart": site.cart(),
    }
    page = page_defaults(
        title=f"今週発売の漫画・コミック新刊{total}点（{start.month}月{start.day}日〜{end.month}月{end.day}日）｜{SITE_NAME}",
        description=f"今週（{start.month}月{start.day}日〜{end.month}月{end.day}日）に発売される漫画・コミックの新刊{total}点を、発売日ごとに紹介しています。毎日自動で更新しています。",
        jsonld=jsonld(breadcrumb_ld(site_base(site), [("トップ", "/"), ("今週発売の漫画新刊", "/week/")])),
        menu="week", lastmod=site.today.isoformat(),
    )
    w.write("week/index.html", "week.html", page, **ctx)


# ---- 書籍 ----
AMAZON_IMAGE_HOURS = 24  # Amazon の書影のアドレスを使ってよい時間（ライセンス契約 利用要件(n)）


def bubble_for(site, d):
    if d is None:
        return "発売日未定", False
    diff = (d - site.today).days
    if diff > 0:
        return f"あと{diff}日で発売", False
    if diff == 0:
        return "本日発売", False
    return "発売中", True


def title_parts(b):
    """書名を（作品名, 巻数）に分ける。巻数のない本は（書名, None）。"""
    if b.volume is None:
        return b.title, None
    return series_name(b.title) or b.title, b.volume


def author_key(name):
    """著者ページの URL に使う識別子（表記ゆれのうち空白と全角半角だけを吸収する）。"""
    norm = re.sub(r"\s+", "", unicodedata.normalize("NFKC", name or ""))
    return hashlib.sha1(norm.encode("utf-8")).hexdigest()[:10]


AUTHOR_KEYS = set()


def authors_ctx(root, b):
    out = []
    for a in b.authors:
        k = author_key(a["name"])
        url = f"{root}author/{k}/" if k in AUTHOR_KEYS else f"{root}search/?q={quote(a['name'])}"
        out.append({"role": a.get("role") if a.get("role") and a.get("role") != "著" else None, "name": a["name"], "url": url})
    return out


def gcal_url(b):
    """Google カレンダーに終日の予定として登録する URL。"""
    if not b.release:
        return None
    start = b.release.strftime("%Y%m%d")
    end = (b.release + timedelta(days=1)).strftime("%Y%m%d")
    text = f"『{b.title}』発売日"
    details = f"{b.publisher}　漫画新刊JP"
    return f"https://calendar.google.com/calendar/render?action=TEMPLATE&text={quote(text)}&dates={start}/{end}&details={quote(details)}"


def last_change(site, b):
    r = site.conn.execute(
        "SELECT * FROM change_log WHERE book_id = ? AND kind = '日付変更' ORDER BY detected_at DESC, id DESC LIMIT 1", (b.id,)
    ).fetchone()
    if not r:
        return None
    return {"old": md(date.fromisoformat(r["old_value"])), "new": md(date.fromisoformat(r["new_value"]))}


def forecast_for(volumes):
    dated = [b for b in volumes if b.release and b.volume]
    if len(dated) < 3:
        return None
    dated.sort(key=lambda b: b.volume)
    gaps = [(b2.release - b1.release).days / 30.44 for b1, b2 in zip(dated, dated[1:]) if b2.release > b1.release]
    if len(gaps) < 2:
        return None
    avg = sum(gaps) / len(gaps)
    last = dated[-1]
    nxt = last.release + timedelta(days=round(avg * 30.44))
    return {"volume": last.volume + 1, "year": nxt.year, "month": nxt.month, "ym": f"{nxt.year}.{nxt.month}", "interval": max(1, round(avg))}


def jp_date(d):
    return f"{d.year}年{d.month}月{d.day}日（{dow(d)}）"


def book_summary(site, b, main, vol, volumes):
    """書籍ページの「この本について」。表示している事実情報だけを文章にまとめる（あらすじなどは書かない）。"""
    name = f"『{main}』{vol}巻" if vol else f"『{b.title}』"
    where = f"{b.publisher}の「{b.label}」から" if b.label else f"{b.publisher}から"
    out = []
    if b.release:
        diff = (b.release - site.today).days
        verb = "発売される予定です" if diff > 0 else ("発売されます" if diff == 0 else "発売されました")
        out.append(f"{name}は、{where}{jp_date(b.release)}に{verb}。")
    else:
        out.append(f"{name}は、{where}発売される予定です。発売日はまだ決まっていません。")
    if b.price:
        out.append(f"定価は{b.price:,}円（税込）です。")
    if b.has_ebook:
        out.append("電子書籍版もあります。")
    if vol == 1:
        out.append("シリーズの1巻目です。")
    prev = next((x for x in volumes if x.volume == (vol or 0) - 1 and x.release), None) if vol else None
    if prev and b.release and b.release > prev.release:
        days = (b.release - prev.release).days
        gap = f"約{round(days / 30.44)}か月" if days >= 28 else f"{days}日"
        out.append(f"前の巻（{prev.volume}巻）は{jp_date(prev.release)}の発売で、{gap}ぶりの新刊です。")
    if b.is_final:
        out.append("この巻で完結します。" if b.release and b.release > site.today else "この巻で完結しています。")
    return "".join(out)


WORKS_COUNT = 6


def author_works(site, root, b):
    """同じ作者のほかの作品（作品ごとに一番新しい巻を1冊）。"""
    keys = {author_key(a["name"]) for a in b.authors}
    if not keys:
        return None
    if not hasattr(site, "by_author"):
        site.by_author = defaultdict(list)
        for x in site.dated:
            for k in {author_key(a["name"]) for a in x.authors}:
                site.by_author[k].append(x)
    works = {}
    for x in {x.id: x for k in sorted(keys) for x in site.by_author.get(k, [])}.values():
        if x.id == b.id or (b.series_id and x.series_id == b.series_id):
            continue
        k = ("s", x.series_id) if x.series_id else ("b", x.id)
        if k not in works or x.release > works[k].release:
            works[k] = x
    if not works:
        return None
    # 同じ発売日の作品は id の順にして、生成のたびに並びが変わらないようにする（変わると毎回転送し直しになる）
    items = sorted(works.values(), key=lambda x: (x.release, -x.id), reverse=True)
    names = [a["name"] for a in b.authors]
    one = len(names) == 1 and author_key(names[0]) in AUTHOR_KEYS
    out = []
    for x in items[:WORKS_COUNT]:
        m, v = title_parts(x)
        out.append({"title": m, "sub": (f"{v}巻・" if v else "") + f"{md(x.release)}発売", "url": site.book_url(root, x), "image": x.image, "alt": site.alt(x)})
    return {
        "title": f"{names[0]}さんのほかの作品" if len(names) == 1 else "この本の作者のほかの作品",
        "books": out,
        "url": f"{root}author/{author_key(names[0])}/" if one else None,
    }


def build_books(site, w):
    root = "../../"
    for b in site.books:
        main, vol = title_parts(b)
        bubble, on_sale = bubble_for(site, b.release)
        series = None
        volumes = sorted([x for x in site.series_books.get(b.series_id, []) if x.volume], key=lambda x: x.volume)
        if b.series_id and len(volumes) >= 2:
            latest = volumes[-1]
            slider = [x for x in volumes if x.id != latest.id]
            start = 0
            for i, x in enumerate(slider):
                if x.id == b.id:
                    start = max(0, i - 1)
            info = site.series[b.series_id]
            series = {
                "name": info["name"], "count": latest.volume, "url": f"{root}series/{b.series_id}/", "start": start,
                "volumes": [{"label": f"{x.volume}巻", "url": site.book_url(root, x), "image": x.image, "cover_url": x.cover_url, "alt": site.alt(x)} for x in slider] if len(slider) >= 2 else [],
                "forecast": forecast_for(volumes),
            }
        sameday = None
        if b.release:
            others = [x for x in site.by_date.get(b.release, []) if x.id != b.id]
            if others:
                sameday = {"md": md(b.release), "dow": dow(b.release), "url": f"{root}date/{b.release.isoformat()}/", "count": len(others) + 1,
                           "books": [{"title": x.title, "pub": x.publisher, "url": site.book_url(root, x), "image": x.image, "cover_url": x.cover_url, "alt": site.alt(x)} for x in others[:6]]}
        crumb = [(b.publisher, f"{root}publisher/{b.publisher_slug}/")]
        if b.series_id and vol:
            crumb.append((main, f"{root}series/{b.series_id}/"))
            crumb.append((f"{vol}巻", None))
        else:
            crumb.append((b.title, None))
        cover = site.main_cover(b)
        ctx = {
            "crumbs": crumbs(root, *crumb),
            "book": {
                "bubble": bubble, "on_sale": on_sale, "release_iso": b.release.isoformat() if b.release else None, "pub": b.publisher, "pub_url": f"{root}publisher/{b.publisher_slug}/",
                "label": b.label, "label_url": f"{root}label/{b.label_id}/" if b.label_id else "", "ebook": b.has_ebook,
                "title_main": main, "volume": vol, "authors": authors_ctx(root, b),
                "date": f"{b.release.year}.{b.release.month}.{b.release.day}" if b.release else None, "dow": dow(b.release) if b.release else "",
                "price": f"{b.price:,}" if b.price else None, "change": last_change(site, b), "stores": site.stores(b), "ebook_stores": site.ebook_stores(b), "isbn": b.isbn13,
                "image": cover[0], "cover_url": cover[1], "alt": site.alt(b),
                "gcal": gcal_url(b), "ics_date": b.release.strftime("%Y%m%d") if b.release else None,
                "ics_end": (b.release + timedelta(days=1)).strftime("%Y%m%d") if b.release else None, "ics_name": f"『{b.title}』発売日",
                "fav": {"id": b.series_id, "name": site.series[b.series_id]["name"], "url": f"/series/{b.series_id}/"} if b.series_id in site.series else None,
                "follow": dict(calendar_links(site, b.series_id), name=site.series[b.series_id]["name"], released=bool(b.release and b.release <= site.today),
                               next_vol=(int(b.volume) + 1) if str(b.volume or "").isdigit() else None) if b.series_id in site.series else None,
            },
            "series": series,
            "sameday": sameday,
            "summary": book_summary(site, b, main, vol, volumes),
            "works": author_works(site, root, b),
        }
        when = f"{b.release.year}年{b.release.month}月{b.release.day}日発売" if b.release else "発売日未定"
        ld_crumbs = [("トップ", "/"), (b.publisher, f"/publisher/{b.publisher_slug}/")]
        if b.series_id and vol:
            ld_crumbs.append((main, f"/series/{b.series_id}/"))
        ld_crumbs.append((b.title, f"/book/{b.key}/"))
        page = page_defaults(
            title=f"{display_title(b, main, vol)}（{b.publisher}）{when}｜{SITE_NAME}",
            description=f"{display_title(b, main, vol)}（{b.publisher}）は{when}。{site.price_text(b)}。予約・購入はAmazon・楽天ブックス・セブンネットで。".replace("。。", "。"),
            jsonld=jsonld(book_ld(site, b), breadcrumb_ld(site_base(site), ld_crumbs)),
            lastmod=lastmod(site, [b]),
        )
        w.write(f"book/{b.key}/index.html", "book.html", page, **ctx)


# ---- 作品 ----
def calendar_links(site, sid):
    """作品のカレンダーを購読するリンク。iPhone・Mac は webcal、Google カレンダーは購読の画面へ送る。"""
    base = site_base(site)
    webcal = "webcal://" + base.split("://", 1)[-1] + f"/series/{sid}/calendar.ics"
    return {"webcal": webcal, "google": "https://calendar.google.com/calendar/r?cid=" + quote(webcal, safe=""),
            "endpoint": "webcal://" + base.split("://", 1)[-1] + f"/series/calendar.php?s={sid}"}


def build_series(site, w):
    root = "../../"
    for sid, books in site.series_books.items():
        vols = sorted([b for b in books if b.volume], key=lambda b: b.volume)
        if len(vols) < 1:
            continue
        info = site.series[sid]
        latest = vols[-1]
        bubble, on_sale = bubble_for(site, latest.release)
        main, vol = title_parts(latest)
        prices = [b.price for b in vols if b.price]
        lt_meta = "".join(f"・{x}" for x in (site.price_text(latest), "電子版あり" if latest.has_ebook else "") if x)
        status = "完結" if any(b.is_final for b in vols) else "刊行中"
        fc = forecast_for(vols)
        ctx = {
            "crumbs": crumbs(root, (latest.publisher, f"{root}publisher/{latest.publisher_slug}/"), (info["name"], None)),
            "series": {
                "pub": latest.publisher, "pub_url": f"{root}publisher/{latest.publisher_slug}/", "label": latest.label,
                "label_url": f"{root}label/{latest.label_id}/" if latest.label_id else "", "status": status, "name": info["name"],
                "authors": authors_ctx(root, latest), "count": latest.volume,
                "total_price": f"{sum(prices):,}" if prices and len(prices) == len(vols) and len(vols) == latest.volume else None,
            },
            "latest": {
                "md": md(latest.release) if latest.release else "未定", "dow": dow(latest.release) if latest.release else "", "url": site.book_url(root, latest),
                "bubble": bubble, "on_sale": on_sale, "release_iso": latest.release.isoformat() if latest.release else None, "title_main": main, "volume": vol,
                "date": f"{latest.release.year}.{latest.release.month}.{latest.release.day}" if latest.release else "未定",
                "meta": lt_meta, "stores": site.stores(latest), "image": latest.image, "alt": site.alt(latest),
            },
            "fav": {"id": sid, "name": info["name"], "url": f"/series/{sid}/"},
            "feed_url": f"{root}series/{sid}/feed.xml",
            "ical": calendar_links(site, sid),
            "forecast": fc if status != "完結" else None,
            "volumes": [{"no": b.volume, "date": f"{b.release.year}.{b.release.month}.{b.release.day}" if b.release else "未定", "latest": b.id == latest.id, "url": site.book_url(root, b), "image": b.image, "cover_url": b.cover_url, "alt": site.alt(b), "asin": site.amazon_asin(b)} for b in reversed(vols)],
            "cart": site.cart(),
        }
        page = page_defaults(
            title=series_title(site, info["name"], latest, vol),
            description=series_description(site, info["name"], latest, vol, len(vols)),
            feed={"title": f"{info['name']}の新刊（{SITE_NAME}）", "url": f"{root}series/{sid}/feed.xml"},
            jsonld=jsonld(series_ld(site, sid, info["name"], vols, latest), breadcrumb_ld(site_base(site), [
                ("トップ", "/"), (latest.publisher, f"/publisher/{latest.publisher_slug}/"), (info["name"], f"/series/{sid}/")])),
            lastmod=lastmod(site, vols),
            noindex=len(vols) < 2,
        )
        w.write(f"series/{sid}/index.html", "series.html", page, **ctx)


# ---- 出版社別・レーベル別・タグ別 ----
def date_groups(site, root, books, keys):
    """本を発売日ごとにまとめる（books の並び順のまま）。"""
    dates = OrderedDict()
    for b in books:
        dates.setdefault(b.release, []).append(b)
    return [{"md": md(d), "dow": dow(d), "on_sale": d <= site.today, "books": [site.row(root, b, keys) for b in v]} for d, v in dates.items()]


def listing_months(site, root, books, keys):
    out = []
    for i, (y, m) in enumerate(chunk_months(site.today)):
        month = sorted((b for b in books if b.release and b.release.year == y and b.release.month == m), key=lambda b: b.release)
        groups = date_groups(site, root, month, keys)
        out.append({"no": m, "count": sum(len(g["books"]) for g in groups), "current": i == 0, "dates": groups})
    return out


def listing_ctx(site, root, books, keys, crumb, listing, label_links=(), others=None):
    """出版社・レーベル・タグ・著者のページ（listing.html）に渡す値。"""
    return {
        "crumbs": crumb, "listing": listing, "label_links": list(label_links), "others": others,
        "months": listing_months(site, root, books, keys),
        "past": listing_past(site, root, books, keys),
        **listing_common(site, books),
    }


def listing_common(site, books):
    upcoming = [b for b in books if b.release and b.release >= site.today]
    months = chunk_months(site.today)
    until_y, until_m = months[-1]
    next_day = min((b.release for b in upcoming), default=None)
    within = [b for b in upcoming if (b.release.year, b.release.month) <= (until_y, until_m)]
    return {
        "next_release": {"md": md(next_day), "dow": dow(next_day), "count": sum(1 for b in books if b.release == next_day)} if next_day else None,
        "upcoming": {"until": until_m, "count": len(within)},
    }


PAST_COUNT = 30


def listing_past(site, root, books, keys):
    """今月より前に発売された本を新しい順に並べる（発売日が過ぎてもページが空にならないようにする）。"""
    start = date(site.today.year, site.today.month, 1)
    past = sorted([b for b in books if b.release and b.release < start], key=lambda b: (b.release, b.publisher, b.title), reverse=True)
    return {"count": len(past), "limited": len(past) > PAST_COUNT, "limit": PAST_COUNT, "dates": date_groups(site, root, past[:PAST_COUNT], keys)}


def lastmod(site, books):
    """サイトマップの lastmod：本の情報が変わった日と、発売日（発売中になって表示が変わる日）の新しいほう。"""
    days = []
    for b in books:
        if b.updated:
            try:
                days.append(datetime.fromisoformat(b.updated).date())
            except ValueError:
                pass
        if b.release and b.release <= site.today:
            days.append(b.release)
    return max(days).isoformat() if days else None


def build_listings(site, w):
    root = "../../"
    # 出版社
    for p in site.publishers:
        books = [b for b in site.dated if b.publisher == p["name"]]
        labels = OrderedDict()
        for b in books:
            if b.label_id and b.label not in labels:
                labels[b.label] = b.label_id
        ctx = listing_ctx(
            site, root, books, ("author", "price"),
            crumbs(root, ("出版社から探す", f"{root}publisher/"), (p["name"], None)),
            {"en": "PUBLISHER", "title": f"{p['name']}の新刊発売予定", "lead": None, "kind": "publisher", "final_badge": False},
            label_links=[{"name": n, "url": f"{root}label/{i}/"} for n, i in labels.items()],
            others={"title": "ほかの出版社の新刊", "links": [{"name": o["name"], "url": f"{root}publisher/{o['slug']}/"} for o in site.publishers if o["name"] != p["name"]]},
        )
        page = page_defaults(title=f"{p['name']}の漫画新刊発売予定｜{SITE_NAME}", description=f"{p['name']}から発売される漫画（コミック）の新刊を、発売日順に紹介しています。", menu="publisher", lastmod=lastmod(site, books))
        w.write(f"publisher/{p['slug']}/index.html", "listing.html", page, **ctx)
    # レーベル
    label_rows = site.conn.execute("SELECT l.id, l.name, p.name AS pub, p.slug FROM labels l JOIN publishers p ON p.id = l.publisher_id WHERE l.is_adult = 0 AND p.is_adult = 0").fetchall()
    for l in label_rows:
        books = [b for b in site.dated if b.label_id == l["id"]]
        if not books:
            continue
        ctx = listing_ctx(
            site, root, books, ("author", "price"),
            crumbs(root, ("レーベルから探す", f"{root}label/"), (l["pub"], f"{root}publisher/{l['slug']}/"), (l["name"], None)),
            {"en": "LABEL", "title": f"{l['name']}の新刊発売予定", "lead": None, "kind": "label", "final_badge": False},
        )
        page = page_defaults(title=f"{l['name']}（{l['pub']}）の漫画新刊発売予定｜{SITE_NAME}", description=f"{l['pub']}のレーベル「{l['name']}」から発売される漫画の新刊の発売予定と、これまでに発売された本をまとめています。", menu="label", lastmod=lastmod(site, books))
        w.write(f"label/{l['id']}/index.html", "listing.html", page, **ctx)
    # タグ
    for slug, (name, lead) in TAG_INFO.items():
        books = [b for b in site.dated if slug in b.tags]
        if not books:
            continue
        ctx = listing_ctx(
            site, root, books, ("author", "label", "price"),
            crumbs(root, ("タグ", f"{root}tag/"), (f"#{name}", None)),
            {"en": "TAG", "title": f"#{name}の新刊発売予定", "lead": lead, "kind": "tag", "final_badge": slug == "final"},
        )
        page = page_defaults(title=f"#{name}の漫画新刊発売予定｜{SITE_NAME}", description=lead, tag=f"tag:{slug}", lastmod=lastmod(site, books))
        w.write(f"tag/{slug}/index.html", "listing.html", page, **ctx)
    # 一覧ページ
    root1 = "../"
    pub_groups = OrderedDict((row, []) for row, _ in yomi.ROWS)
    pub_groups[yomi.OTHER] = []
    for p in sorted(site.publishers, key=lambda p: yomi.sort_key(p["name"])):
        pub_groups[yomi.row_of(p["name"])].append({"name": f"{p['name']}（{p['count']}）", "url": f"{root1}publisher/{p['slug']}/"})
    w.write("publisher/index.html", "index_list.html", page_defaults(title=f"出版社から探す｜{SITE_NAME}", description="出版社ごとの漫画新刊発売予定。", menu="publisher"),
            crumbs=crumbs(root1, ("出版社から探す", None)), heading={"en": "PUBLISHER", "title": "出版社から探す", "lead": "出版社を選ぶと、その出版社の新刊発売予定を一覧で見られます。"},
            groups=[{"title": k, "links": v} for k, v in pub_groups.items() if v])
    label_groups = OrderedDict()
    counts = defaultdict(int)
    for b in site.dated:
        if b.label_id:
            counts[b.label_id] += 1
    for l in label_rows:
        if counts[l["id"]]:
            label_groups.setdefault(l["pub"], []).append({"name": f"{l['name']}（{counts[l['id']]}）", "url": f"{root1}label/{l['id']}/"})
    w.write("label/index.html", "index_list.html", page_defaults(title=f"レーベルから探す｜{SITE_NAME}", description="レーベルごとの漫画新刊発売予定。", menu="label"),
            crumbs=crumbs(root1, ("レーベルから探す", None)), heading={"en": "LABEL", "title": "レーベルから探す", "lead": "レーベルを選ぶと、そのレーベルの新刊発売予定を一覧で見られます。"},
            groups=[{"title": k, "links": v} for k, v in label_groups.items()])
    tag_links = [{"name": f"#{TAG_INFO[s][0]}", "url": f"{root1}tag/{s}/"} for s in TAG_INFO if any(s in b.tags for b in site.dated)]
    w.write("tag/index.html", "index_list.html", page_defaults(title=f"タグから探す｜{SITE_NAME}", description="タグごとの漫画新刊発売予定。"),
            crumbs=crumbs(root1, ("タグ", None)), heading={"en": "TAG", "title": "タグから探す", "lead": "タグを選ぶと、そのタグが付いた新刊発売予定を一覧で見られます。"},
            groups=[{"title": "タグ", "links": tag_links}])


# ---- 著者 ----
def build_authors(site, w):
    root = "../../"
    by_key = OrderedDict()
    names = {}
    for b in site.dated:
        for a in b.authors:
            k = author_key(a["name"])
            by_key.setdefault(k, [])
            if b not in by_key[k]:
                by_key[k].append(b)
            names.setdefault(k, a["name"])
    for k, books in by_key.items():
        name = names[k]
        ctx = listing_ctx(
            site, root, books, ("label", "price"),
            crumbs(root, (f"{name}", None)),
            {"en": "AUTHOR", "title": f"{name}の新刊発売予定", "lead": f"{name}さんが関わる漫画の新刊の発売予定と、これまでに発売された本をまとめています。", "kind": "author", "final_badge": False},
        )
        page = page_defaults(title=f"{name}の漫画新刊発売予定｜{SITE_NAME}", description=f"{name}さんの漫画（コミック）の新刊の発売予定と、これまでに発売された本をまとめています。", lastmod=lastmod(site, books))
        w.write(f"author/{k}/index.html", "listing.html", page, **ctx)


# ---- 作品ごとの RSS ----
def build_series_feeds(site, w, site_url):
    base = (site_url or "https://new-comics.jp").rstrip("/")
    for sid, books in site.series_books.items():
        if sid not in site.series:
            continue
        name = site.series[sid]["name"]
        items = sorted(books, key=lambda b: (b.first_seen or "", b.id), reverse=True)[:20]
        entries = []
        for b in items:
            when = f"{b.release.year}年{b.release.month}月{b.release.day}日発売" if b.release else "発売日未定"
            try:
                pub = datetime.fromisoformat(b.first_seen).strftime("%a, %d %b %Y %H:%M:%S %z")
            except (TypeError, ValueError):
                pub = None
            entries.append(
                "<item>"
                f"<title>{xml_escape(b.title)}（{when}）</title>"
                f"<link>{base}/book/{b.key}/</link>"
                f"<guid isPermaLink=\"true\">{base}/book/{b.key}/</guid>"
                f"<description>{xml_escape(f'{b.publisher}・{when}')}</description>"
                + (f"<pubDate>{pub}</pubDate>" if pub else "")
                + "</item>"
            )
        xml = (
            '<?xml version="1.0" encoding="UTF-8"?>'
            '<rss version="2.0"><channel>'
            f"<title>{xml_escape(name)}の新刊（{SITE_NAME}）</title>"
            f"<link>{base}/series/{sid}/</link>"
            f"<description>{xml_escape(name)}の新刊が載ったらお知らせします。</description>"
            "<language>ja</language>"
            + "".join(entries)
            + "</channel></rss>"
        )
        target = Path(w.out) / "series" / str(sid) / "feed.xml"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(xml, encoding="utf-8")


# ---- よく見られている新刊（サイドメニュー） ----
RANKING_COUNT = 5
RANKING_PAST_DAYS = 30


def ranking_items(site):
    """直近の書籍ページの表示回数（page_views）から、これから発売の本と発売から1か月以内の本を多い順に選ぶ。"""
    try:
        views = {r["book_key"]: r["views"] for r in site.conn.execute("SELECT book_key, views FROM page_views")}
    except sqlite3.OperationalError:
        return []
    since = site.today - timedelta(days=RANKING_PAST_DAYS)
    books = [b for b in site.books if b.key in views and b.release and b.release >= since]
    books.sort(key=lambda b: (-views[b.key], b.release, b.id))
    return [{
        "no": i, "url": f"/book/{b.key}/", "title": b.title, "image": b.image, "alt": site.alt(b),
        "date": f"{b.release.month}.{b.release.day}発売", "price": f"¥{b.price:,}" if b.price else "",
    } for i, b in enumerate(books[:RANKING_COUNT], start=1)]


# ---- 作品ごとのカレンダー（iCalendar） ----
def ics_text(text):
    return text.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def ics_fold(line):
    """1行を75バイト以内で折り返す（RFC 5545）。文字の途中では切らない。"""
    out, cur = [], ""
    for c in line:
        limit = 75 if not out else 74
        if len((cur + c).encode("utf-8")) > limit:
            out.append(cur)
            cur = c
        else:
            cur += c
    out.append(cur)
    return "\r\n ".join(out)


def ics_stamp(value):
    try:
        return datetime.fromisoformat(value).astimezone(UTC_TZ).strftime("%Y%m%dT%H%M%SZ")
    except (TypeError, ValueError):
        return "20260101T000000Z"


def series_calendar(name, books, base, amazon_url=None):
    """作品の発売日を終日の予定にする。前日の21時と当日の9時に通知する（通知を使うかはカレンダーアプリ側の設定による）。

    amazon_url（本 → Amazon のアフィリエイトリンク）を渡すと、予定のリンク先を Amazon にし、説明にも入れる（2026-11-05 運営者の判断）。
    """
    lines = [
        "BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//new-comics.jp//series//JA", "CALSCALE:GREGORIAN", "METHOD:PUBLISH",
        f"X-WR-CALNAME:{ics_text(name)}の新刊（{SITE_NAME}）", "X-WR-TIMEZONE:Asia/Tokyo",
        "REFRESH-INTERVAL;VALUE=DURATION:PT12H", "X-PUBLISHED-TTL:PT12H",
    ]
    for b in sorted(books, key=lambda b: (b.release, b.id)):
        url = f"{base}/book/{b.key}/"
        amazon = amazon_url(b) if amazon_url else None
        about = b.publisher + (("・" + b.label) if b.label else "")
        desc = f"{about}\nAmazonで見る：{amazon}\n漫画新刊JPで見る：{url}" if amazon else f"{about}\n{url}"
        lines += [
            "BEGIN:VEVENT",
            f"UID:{b.key}@new-comics.jp",
            f"DTSTAMP:{ics_stamp(b.first_seen)}",
            f"DTSTART;VALUE=DATE:{b.release.strftime('%Y%m%d')}",
            f"DTEND;VALUE=DATE:{(b.release + timedelta(days=1)).strftime('%Y%m%d')}",
            f"SUMMARY:{ics_text(b.title)} 発売日",
            f"DESCRIPTION:{ics_text(desc)}",
            f"URL:{amazon or url}",
            "TRANSP:TRANSPARENT",
            "BEGIN:VALARM", "ACTION:DISPLAY", f"DESCRIPTION:明日発売：{ics_text(b.title)}", "TRIGGER:-PT3H", "END:VALARM",
            "BEGIN:VALARM", "ACTION:DISPLAY", f"DESCRIPTION:今日発売：{ics_text(b.title)}", "TRIGGER:PT9H", "END:VALARM",
            "END:VEVENT",
        ]
    lines.append("END:VCALENDAR")
    return "".join(ics_fold(l) + "\r\n" for l in lines)


def build_series_calendars(site, w, site_url):
    base = (site_url or "https://new-comics.jp").rstrip("/")
    since = site.today - timedelta(days=365)
    for sid, books in site.series_books.items():
        if sid not in site.series:
            continue
        dated = [b for b in books if b.release and b.release >= since]
        target = Path(w.out) / "series" / str(sid) / "calendar.ics"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(series_calendar(site.series[sid]["name"], dated, base, amazon_url=lambda b: next(
            (s["url"] for s in site.stores(b) if s["kind"] == "amazon"), None)).encode("utf-8"))


# ---- お気に入り ----
def build_favorites(site, w):
    root = "../"
    ctx = {"crumbs": crumbs(root, ("お気に入り", None)), "favorites_js": True, "cart": site.cart()}
    page = page_defaults(title=f"お気に入り｜{SITE_NAME}", description="お気に入りに登録した作品の新刊をまとめて見られます。", menu="favorites", noindex=True)
    w.write("favorites/index.html", "favorites.html", page, **ctx)


# ---- 検索 ----
ALIASES_PATH = Path(__file__).resolve().parent / "aliases.tsv"


def search_key(text):
    """検索で比べるための形。全角・半角、大文字・小文字、ひらがな・カタカナ、空白・記号の違いをなくす（search.js の normalize と同じ）。"""
    t = unicodedata.normalize("NFKC", text or "").lower()
    t = "".join(chr(ord(c) + 0x60) if "\u3041" <= c <= "\u3096" else c for c in t)
    return "".join(c for c in t if unicodedata.category(c)[0] in "LN")


def load_aliases(path=ALIASES_PATH):
    """略称の対応表。1行目は見出し。「書名に含まれる文字」が書名にあれば、その本は「呼び方」でも見つかる。"""
    pairs = []
    for line in Path(path).read_text(encoding="utf-8").splitlines()[1:]:
        if "\t" not in line:
            continue
        key, names = line.split("\t", 1)
        names = [n.strip() for n in re.split(r"[、,]", names) if n.strip()]
        if search_key(key) and names:
            pairs.append((search_key(key), names))
    return pairs


def search_words(books, aliases):
    """本ごとに、書名には出てこない検索用の言葉（作品の読み仮名と略称）を作る。画面には出さない。"""
    series_kana = {}
    for b in books:
        if b.title_kana and b.series_id not in series_kana:
            series_kana[b.series_id] = re.sub(r"[\d\s]+$", "", b.title_kana)
    words = {}
    for b in books:
        found = [series_kana.get(b.series_id) or b.title_kana or ""]
        title = search_key(b.title)
        for key, names in aliases:
            if key in title:
                found.extend(names)
        hay = title
        extra = []
        for f in found:
            if f and search_key(f) not in hay:
                extra.append(f)
                hay += search_key(f)
        if extra:
            words[b.id] = " ".join(extra)
    return words


def build_search(site, w):
    root = "../"
    items = []
    order = {b.id: i for i, b in enumerate(sorted(site.books, key=lambda b: (b.first_seen, b.id)))}
    words = search_words(site.books, load_aliases())
    for b in site.books:
        stores = {s["kind"]: s["url"] for s in site.stores(b)}
        item = {
            "t": b.title, "p": b.publisher, "l": b.label or "", "a": site.author_text(b), "d": b.release.isoformat() if b.release else "",
            "e": bool(b.has_ebook), "u": f"../book/{b.key}/", "m": site.meta(b, ("author", "label", "price")), "s": stores, "f": order[b.id], "i": b.image, "ia": site.alt(b), "sr": b.series_id,
        }
        if b.id in words:
            item["k"] = words[b.id]
        items.append(item)
    target = Path(w.out) / "search" / "index.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps({"items": items}, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    ctx = {
        "crumbs": crumbs(root, ("検索結果", None)),
        "options": search_options(site),
        "search": {"heading": "検索結果", "total": len(items), "q": "", "pub": "", "label": "", "month": "", "ebook": False,
                   "range": "", "sort": "date"},
        "search_js": True,
    }
    page = page_defaults(title=f"検索結果｜{SITE_NAME}", description="漫画の新刊を作品名・出版社・レーベル・発売月で検索できます。")
    w.write("search/index.html", "search.html", page, **ctx)


# ---- 発売日の変更・決定 ----
def updates_dir(slug):
    return f"updates/{slug}/" if slug else "updates/"


def build_updates(site, w):
    last = site.conn.execute("SELECT MAX(finished_at) AS t FROM fetch_runs WHERE status = 'ok'").fetchone()["t"]
    updated_at = datetime.fromisoformat(last).strftime("%Y.%m.%d %-H:%M") if last else "—"
    for slug, kind, heading, empty in UPDATE_KINDS:
        rows = change_rows(site, kind)
        pages = [rows[i:i + UPDATES_PER_PAGE] for i in range(0, len(rows), UPDATES_PER_PAGE)] or [[]]
        base = updates_dir(slug)
        for n, chunk in enumerate(pages, start=1):
            rel = base + ("index.html" if n == 1 else f"page/{n}/index.html")
            root = "../" * (rel.count("/"))
            groups = OrderedDict()
            for r in chunk:
                b = site.by_id[r["book_id"]]
                d = datetime.fromisoformat(r["detected_at"]).date()
                groups.setdefault(d, []).append({"kind": r["kind"], "title": b.title, "pub": b.publisher, "detail": update_detail(r["kind"], r["old_value"], r["new_value"]), "url": site.book_url(root, b)})
            pager = [{"label": label, "url": f"{root}{base}" if k == 1 else f"{root}{base}page/{k}/", "current": kind == "num" and k == n, "text": kind != "num"} for kind, k, label in pager_items(n, len(pages))]
            tabs = [{"label": "すべて" if not s else h, "url": f"{root}{updates_dir(s)}", "current": s == slug} for s, _, h, _ in UPDATE_KINDS]
            ctx = {
                "crumbs": crumbs(root, ("発売日の変更・決定", None)),
                "updated_at": updated_at,
                "heading": heading,
                "total": len(rows),
                "empty": empty,
                "tabs": tabs,
                "groups": [{"md": md(d), "dow": dow(d), "items": v} for d, v in groups.items()],
                "pager": pager,
            }
            title = "発売日の変更・決定" if not slug else f"{heading}｜発売日の変更・決定"
            page = page_defaults(title=f"{title}｜{SITE_NAME}", description="漫画の新刊の発売日の変更・決定をお知らせします。", menu="updates")
            w.write(rel, "updates.html", page, **ctx)


# ---- 固定ページ ----
def build_static(site, w):
    root = "../"
    pages = [
        ("about", "運営者情報", "about.html", {}),
        ("privacy", "プライバシーポリシー", "privacy.html", {"established": site.env.get("PRIVACY_DATE") or site.today.strftime("%Y.%m.%d")}),
        ("disclaimer", "免責事項", "disclaimer.html", {}),
        ("contact", "お問い合わせ", "contact.html", {"form_action": "confirm.php"}),
    ]
    for slug, label, template, extra in pages:
        page = page_defaults(title=f"{label}｜{SITE_NAME}", description=f"{SITE_NAME}の{label}です。", footer=slug)
        w.write(f"{slug}/index.html", template, page, crumbs=crumbs(root, (label, None)), **extra)
    build_contact(w)


def build_contact(w):
    contact_crumb = ("お問い合わせ", "./")
    page = page_defaults(title=f"お問い合わせ内容の確認｜{SITE_NAME}", description=f"{SITE_NAME}のお問い合わせです。", footer="contact")
    page["noindex"] = True
    w.write("contact/confirm.php", "contact_confirm.html", page, crumbs=crumbs("../", contact_crumb, ("内容の確認", None)))
    page = page_defaults(title=f"お問い合わせを受け付けました｜{SITE_NAME}", description=f"{SITE_NAME}のお問い合わせです。", footer="contact")
    page["noindex"] = True
    w.write("contact/thanks/index.html", "contact_thanks.html", page, crumbs=crumbs("../../", ("お問い合わせ", "../"), ("受付完了", None)))
    php = Path(__file__).resolve().parent / "php"
    dest = Path(w.out) / "contact"
    shutil.copyfile(php / "lib.php", dest / "lib.php")
    shutil.copyfile(php / "send.php", dest / "send.php")
    shutil.copyfile(php / "htaccess", dest / ".htaccess")
    (Path(w.out) / "series").mkdir(parents=True, exist_ok=True)
    shutil.copyfile(php / "calendar.php", Path(w.out) / "series" / "calendar.php")


def build_llms(site, w):
    """AI 向けの案内（llms.txt）。サイトの内容と主なページを短く書く。"""
    base = site_base(site)
    t = site.today
    months = []
    for k in range(3):
        y, m = t.year + (t.month - 1 + k) // 12, (t.month - 1 + k) % 12 + 1
        months.append(f"- [{y}年{m}月発売の漫画・コミック新刊一覧]({base}/calendar/{y}/{m:02d}/)")
    lines = [
        f"# {SITE_NAME}（NEW COMICS JP）",
        "",
        "> 漫画・コミックの新刊発売日を、出版社の公式サイトなどの情報をもとに毎日自動で更新している日本語の情報サイトです。発売日カレンダー、出版社・レーベル・作品・作者ごとの新刊一覧、各書籍の発売日・価格・ISBN・電子版の有無を掲載しています。成人向けの作品は掲載していません。",
        "",
        "## 主なページ",
        f"- [トップ（今日・明日発売の漫画新刊）]({base}/)",
        f"- [漫画新刊カレンダー（今月）]({base}/calendar/)",
        *months,
        f"- [出版社から探す]({base}/publisher/)",
        f"- [レーベルから探す]({base}/label/)",
        f"- [発売日の変更・決定]({base}/updates/)",
        f"- [特集記事]({base}/feature/)",
        "",
        "## ページの種類",
        f"- 日付ごとの新刊：{base}/date/YYYY-MM-DD/ （その日に発売される漫画・コミックの一覧）",
        f"- 書籍：{base}/book/ISBN/ （発売日・価格・出版社・レーベル・著者・電子版の有無）",
        f"- 作品：{base}/series/ID/ （最新刊と既刊の発売日、次の巻の発売予定）",
        "",
        "## 情報について",
        "- 発売日・価格などは出版社の公式サイトの情報をもとにしています。発売日は変更されることがあるため、最新の情報は各ページの「発売日の変更・決定」や出版社の発表をご確認ください。",
        f"- 情報は毎日自動で更新しています（最終更新：{t.year}年{t.month}月{t.day}日）。",
        "",
    ]
    (Path(w.out) / "llms.txt").write_text("\n".join(lines), encoding="utf-8")


def build_sitemap(site, w, site_url):
    if w.adsense_client:
        pub = w.adsense_client.replace("ca-pub-", "pub-")
        (Path(w.out) / "ads.txt").write_text(f"google.com, {pub}, DIRECT, f08c47fec0942fa0\n", encoding="utf-8")
    if not site_url:
        return
    base = site_url.rstrip("/")
    body = ""
    for p in sorted(Path(w.out).rglob("index.html")):
        rel_file = p.relative_to(w.out).as_posix()
        if rel_file in w.noindex:
            continue
        rel = rel_file[: -len("index.html")]
        mod = w.lastmod.get(rel_file)
        body += f"<url><loc>{base}/{rel}</loc>" + (f"<lastmod>{mod}</lastmod>" if mod else "") + "</url>"
    (Path(w.out) / "sitemap.xml").write_text(f'<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{body}</urlset>', encoding="utf-8")
    (Path(w.out) / "robots.txt").write_text(f"User-agent: *\nAllow: /\nSitemap: {base}/sitemap.xml\n", encoding="utf-8")


def main(argv=None):
    parser = argparse.ArgumentParser(description="静的ページを生成する")
    parser.add_argument("--db", default=str(db.DEFAULT_PATH))
    parser.add_argument("--out", default=str(Path(__file__).resolve().parents[2] / "dist"))
    parser.add_argument("--today", help="基準日（YYYY-MM-DD、確認用）")
    args = parser.parse_args(argv)
    conn = db.connect(args.db)
    today = date.fromisoformat(args.today) if args.today else jst_today()
    out = Path(args.out)
    if out.exists():
        shutil.rmtree(out)
    count = build(conn, out, today, dict(os.environ))
    print(f"{count} ページを生成しました（基準日 {today.isoformat()}）")


if __name__ == "__main__":
    main()
