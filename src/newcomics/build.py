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
import unicodedata
from collections import OrderedDict, defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import quote
from xml.sax.saxutils import escape as xml_escape

import holidays as holidays_lib

from . import db, yomi
from .normalize import isbn13_to_10
from .render import Writer, page_defaults

DOWS = ["月", "火", "水", "木", "金", "土", "日"]
SITE_NAME = "漫画新刊JP"
UPDATES_PER_PAGE = 40
UPDATE_KINDS = [
    ("", None, "すべての更新", "発売日の変更・決定は、今のところありません。"),
    ("change", "日付変更", "発売日の変更", "発売日が変更された本は、今のところありません。"),
    ("fixed", "日付決定", "発売日の決定", "発売日が決定した本は、今のところありません。"),
]
KIND_LABELS = {"日付変更": "発売日の変更", "日付決定": "発売日の決定"}
TOP_BOOKS = 8
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


class Book:
    __slots__ = (
        "id", "isbn13", "title", "volume", "series_id", "publisher", "publisher_slug", "label", "label_id", "authors",
        "release", "price", "has_ebook", "edition", "is_final", "asin", "rakuten_url", "origin", "image", "cover_url", "seven_ok", "first_seen", "tags", "key",
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
        self.rakuten_url = row["rakuten_url"] if "rakuten_url" in row.keys() else None
        self.origin = row["origin"] if "origin" in row.keys() else "publisher"
        image = row["image_url"] if "image_url" in row.keys() else None
        # 楽天の書影は、リンク先を必ず楽天の商品ページにする（出版社サイトの本は楽天へのリンクがあるときだけ書影を出す）
        if self.origin == "rakuten":
            self.image, self.cover_url = image, (self.rakuten_url if image else None)
        elif image and self.rakuten_url:
            self.image, self.cover_url = image, self.rakuten_url
        else:
            self.image, self.cover_url = None, None
        self.seven_ok = row["seven_ok"] if "seven_ok" in row.keys() else None
        self.first_seen = row["first_seen_at"]
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
        self.by_key = {b.key: b for b in self.books}
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

    def stores(self, b):
        tag = self.env.get("AMAZON_TAG")
        q = b.isbn13 or b.title
        # ISBN が分かる本は Amazon・セブンネットとも商品ページへ。分からない本だけ書名の検索ページにする
        asin = b.asin or isbn13_to_10(b.isbn13)
        if asin:
            amazon = f"https://www.amazon.co.jp/dp/{asin}"
            if tag:
                amazon += f"?tag={quote(tag)}"
        else:
            amazon = f"https://www.amazon.co.jp/s?k={quote(q)}&i=stripbooks"
            if tag:
                amazon += f"&tag={quote(tag)}"
        rakuten = b.rakuten_url or f"https://books.rakuten.co.jp/search?sitem={quote(q)}"
        seven = f"https://7net.omni7.jp/detail_isbn/{b.isbn13}" if b.isbn13 else f"https://7net.omni7.jp/search/?keyword={quote(q)}"
        out = [
            {"name": "Amazon", "short": "Amazon", "kind": "amazon", "button": "Amazon", "url": amazon},
            {"name": "楽天ブックス", "short": "楽天", "kind": "rakuten", "button": "楽天ブックス", "url": rakuten},
        ]
        # セブンネットで取り扱いがないと確認できた本は、セブンネットのボタンを出さない
        if b.seven_ok != 0:
            out.append({"name": "セブンネットショッピング", "short": "セブン\nネット", "kind": "seven", "button": "セブンネット", "url": seven})
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
        main, vol, _ = title_parts(b)
        return f"{main} {vol}巻" if vol else b.title

    def row(self, root, b, keys=("author", "label", "price")):
        return {
            "url": self.book_url(root, b), "title": b.title, "pub": b.publisher, "label": b.label, "ebook": b.has_ebook,
            "first": b.is_first, "meta": self.meta(b, keys), "stores": self.stores(b), "image": b.image, "cover_url": b.cover_url, "alt": self.alt(b),
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
        tags = [{"key": f"tag:{slug}", "label": TAG_INFO[slug][0], "path": f"tag/{slug}/"} for slug in TAG_INFO if any(slug in b.tags for b in self.books)]
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
    w = Writer(out_dir, site.tags_for_menu(), today.year, ga4_id=env.get("GA4_ID"), site_url=env.get("SITE_URL"), rakuten_credit=any(b.origin == "rakuten" or b.rakuten_url for b in site.books))
    w.copy_assets()
    AUTHOR_KEYS.clear()
    AUTHOR_KEYS.update(author_key(a["name"]) for b in site.dated for a in b.authors)
    build_top(site, w)
    build_calendars(site, w)
    build_dates(site, w)
    build_books(site, w)
    build_series(site, w)
    build_listings(site, w)
    build_authors(site, w)
    build_series_feeds(site, w, env.get("SITE_URL"))
    build_favorites(site, w)
    build_search(site, w)
    build_updates(site, w)
    build_static(site, w)
    build_sitemap(site, w, env.get("SITE_URL"))
    build_partials(site, w)
    return w.count


def load_features(env, limit=3):
    """特集（WordPress）の新しい記事を、REST API から取る。取れないときは空にする。"""
    api = env.get("FEATURE_API")
    if not api:
        return []
    try:
        import requests
        res = requests.get(api, params={"per_page": limit, "_embed": "wp:term", "_fields": "title,link,_embedded,_links"}, timeout=20)
        res.raise_for_status()
        posts = res.json()
    except Exception as exc:
        print(f"特集記事を取得できませんでした：{exc}")
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
        "site": site_context("/", w.tags, w.year, w.rakuten_credit),
    }
    dest = Path(w.out) / "assets" / "partials"
    dest.mkdir(parents=True, exist_ok=True)
    for name in ("sidemenu", "footer"):
        (dest / f"{name}.html").write_text(w.env.get_template(f"_{name}.html").render(**ctx), encoding="utf-8")
    ga = ""
    if w.ga4_id:
        ga = (f'<script async src="https://www.googletagmanager.com/gtag/js?id={w.ga4_id}"></script>\n'
              f"<script>window.dataLayer=window.dataLayer||[];function gtag(){{dataLayer.push(arguments);}}gtag('js',new Date());gtag('config','{w.ga4_id}');</script>\n")
    (dest / "analytics.html").write_text(ga, encoding="utf-8")


def crumbs(root, *items):
    out = [{"label": "トップ", "url": root or "./"}]
    for label, url in items:
        out.append({"label": label, "url": url} if url else {"label": label})
    return out


# ---- トップ ----
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
                "image": b.image, "cover_url": b.cover_url, "alt": site.alt(b),
            })
        more = f"date/{d.isoformat()}/" if books else f"calendar/{d.year}/{d.month:02d}/"
        return {"word": word, "date": md(d), "books": cards, "more_url": more}

    ticker = [b.title for b in site.by_date.get(today, [])] or ["本日発売の新刊はありません"]
    updates = latest_updates(site, root, 8)
    ctx = {
        "ticker": ticker + ticker,
        "search": search_options(site),
        "calendar": {"url": f"calendar/{today.year}/{today.month:02d}/", "month": today.month},
        "tomorrow": {"url": f"date/{tomorrow.isoformat()}/" if tomorrow in site.by_date else f"calendar/{tomorrow.year}/{tomorrow.month:02d}/", "label": f"{md(tomorrow)}（{dow(tomorrow)}）"},
        "releases": [release(today, "今日"), release(tomorrow, "明日")],
        "updates": updates,
        "features": load_features(site.env),
    }
    page = page_defaults(
        title=f"{SITE_NAME}｜漫画の新刊発売日カレンダー",
        description="漫画（コミック）の新刊発売日を、カレンダーや出版社・作品ごとに探せる情報サイト。発売予定を毎日自動で更新しています。",
        menu="top", is_top=True,
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
        "month": {"no": m, "title": f"{y}年{m}月の新刊カレンダー"},
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
    }
    page = page_defaults(
        title=f"{y}年{m}月の漫画新刊発売日カレンダー｜{SITE_NAME}",
        description=f"{y}年{m}月に発売される漫画（コミック）の新刊{total:,}点を、発売日ごとのカレンダーで紹介しています。",
        menu="calendar",
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
            "calendar_url": f"{root}calendar/{d.year}/{d.month:02d}/",
        }
        page = page_defaults(
            title=f"{d.year}年{d.month}月{d.day}日（{dow(d)}）発売の漫画新刊{len(books)}点｜{SITE_NAME}",
            description=f"{d.year}年{d.month}月{d.day}日（{dow(d)}）に発売される漫画（コミック）の新刊{len(books)}点を出版社別に紹介しています。",
            menu="calendar",
        )
        w.write(f"date/{d.isoformat()}/index.html", "date.html", page, **ctx)


# ---- 書籍 ----
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
    import re
    if b.volume is None:
        return b.title, None, ""
    from .normalize import series_name
    return series_name(b.title) or b.title, b.volume, ""


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


def build_books(site, w):
    root = "../../"
    for b in site.books:
        main, vol, rest = title_parts(b)
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
        ctx = {
            "crumbs": crumbs(root, *crumb),
            "book": {
                "bubble": bubble, "on_sale": on_sale, "release_iso": b.release.isoformat() if b.release else None, "pub": b.publisher, "pub_url": f"{root}publisher/{b.publisher_slug}/",
                "label": b.label, "label_url": f"{root}label/{b.label_id}/" if b.label_id else "", "ebook": b.has_ebook,
                "title_main": main, "volume": vol, "title_rest": rest, "authors": authors_ctx(root, b),
                "date": f"{b.release.year}.{b.release.month}.{b.release.day}" if b.release else None, "dow": dow(b.release) if b.release else "",
                "price": f"{b.price:,}" if b.price else None, "change": last_change(site, b), "stores": site.stores(b), "isbn": b.isbn13,
                "image": b.image, "cover_url": b.cover_url, "alt": site.alt(b),
                "gcal": gcal_url(b), "ics_date": b.release.strftime("%Y%m%d") if b.release else None,
                "ics_end": (b.release + timedelta(days=1)).strftime("%Y%m%d") if b.release else None, "ics_name": f"『{b.title}』発売日",
                "fav": {"id": b.series_id, "name": site.series[b.series_id]["name"], "url": f"/series/{b.series_id}/"} if b.series_id in site.series else None,
            },
            "series": series,
            "sameday": sameday,
        }
        when = f"{b.release.year}年{b.release.month}月{b.release.day}日発売" if b.release else "発売日未定"
        page = page_defaults(
            title=f"{b.title}（{b.publisher}）{when}｜{SITE_NAME}",
            description=f"{b.title}（{b.publisher}）は{when}。{site.price_text(b)}。予約・購入はAmazon・楽天ブックス・セブンネットで。".replace("。。", "。"),
        )
        w.write(f"book/{b.key}/index.html", "book.html", page, **ctx)


# ---- 作品 ----
def build_series(site, w):
    root = "../../"
    for sid, books in site.series_books.items():
        vols = sorted([b for b in books if b.volume], key=lambda b: b.volume)
        if len(vols) < 1:
            continue
        info = site.series[sid]
        latest = vols[-1]
        bubble, on_sale = bubble_for(site, latest.release)
        main, vol, _ = title_parts(latest)
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
                "meta": lt_meta, "stores": site.stores(latest), "image": latest.image, "cover_url": latest.cover_url, "alt": site.alt(latest),
            },
            "fav": {"id": sid, "name": info["name"], "url": f"/series/{sid}/"},
            "feed_url": f"{root}series/{sid}/feed.xml",
            "forecast": fc if status != "完結" else None,
            "volumes": [{"no": b.volume, "date": f"{b.release.year}.{b.release.month}.{b.release.day}" if b.release else "未定", "latest": b.id == latest.id, "url": site.book_url(root, b), "image": b.image, "cover_url": b.cover_url, "alt": site.alt(b)} for b in reversed(vols)],
        }
        page = page_defaults(
            title=f"{info['name']}の新刊・既刊一覧（{latest.publisher}）｜{SITE_NAME}",
            description=f"{info['name']}（{latest.publisher}）の最新刊と既刊の発売日をまとめています。",
            feed={"title": f"{info['name']}の新刊（{SITE_NAME}）", "url": f"{root}series/{sid}/feed.xml"},
        )
        w.write(f"series/{sid}/index.html", "series.html", page, **ctx)


# ---- 出版社別・レーベル別・タグ別 ----
def listing_months(site, root, books, keys, kind):
    out = []
    months = chunk_months(site.today)
    for i, (y, m) in enumerate(months):
        dates = OrderedDict()
        for b in books:
            if b.release and b.release.year == y and b.release.month == m:
                dates.setdefault(b.release, []).append(b)
        groups = [{"md": md(d), "dow": dow(d), "on_sale": d <= site.today, "books": [site.row(root, b, keys) for b in v]} for d, v in sorted(dates.items())]
        out.append({"no": m, "count": sum(len(g["books"]) for g in groups), "current": i == 0, "dates": groups})
    return out


def listing_common(site, root, books):
    upcoming = [b for b in books if b.release and b.release >= site.today]
    months = chunk_months(site.today)
    until_y, until_m = months[-1]
    next_day = min((b.release for b in upcoming), default=None)
    within = [b for b in upcoming if (b.release.year, b.release.month) <= (until_y, until_m)]
    return {
        "next_release": {"md": md(next_day), "dow": dow(next_day), "count": sum(1 for b in books if b.release == next_day)} if next_day else None,
        "upcoming": {"until": until_m, "count": len(within)},
    }


def build_listings(site, w):
    root = "../../"
    # 出版社
    for p in site.publishers:
        books = [b for b in site.dated if b.publisher == p["name"]]
        labels = OrderedDict()
        for b in books:
            if b.label_id and b.label not in labels:
                labels[b.label] = b.label_id
        ctx = {
            "crumbs": crumbs(root, ("出版社から探す", f"{root}publisher/"), (p["name"], None)),
            "listing": {"en": "PUBLISHER", "title": f"{p['name']}の新刊発売予定", "lead": None, "kind": "publisher", "final_badge": False},
            "label_links": [{"name": n, "url": f"{root}label/{i}/"} for n, i in labels.items()],
            "months": listing_months(site, root, books, ("author", "price"), "publisher"),
            "others": {"title": "ほかの出版社の新刊", "links": [{"name": o["name"], "url": f"{root}publisher/{o['slug']}/"} for o in site.publishers if o["name"] != p["name"]]},
            **listing_common(site, root, books),
        }
        page = page_defaults(title=f"{p['name']}の漫画新刊発売予定｜{SITE_NAME}", description=f"{p['name']}から発売される漫画（コミック）の新刊を、発売日順に紹介しています。", menu="publisher")
        w.write(f"publisher/{p['slug']}/index.html", "listing.html", page, **ctx)
    # レーベル
    label_rows = site.conn.execute("SELECT l.id, l.name, p.name AS pub, p.slug FROM labels l JOIN publishers p ON p.id = l.publisher_id WHERE l.is_adult = 0 AND p.is_adult = 0").fetchall()
    for l in label_rows:
        books = [b for b in site.dated if b.label_id == l["id"]]
        if not books:
            continue
        ctx = {
            "crumbs": crumbs(root, ("レーベルから探す", f"{root}label/"), (l["pub"], f"{root}publisher/{l['slug']}/"), (l["name"], None)),
            "listing": {"en": "LABEL", "title": f"{l['name']}の新刊発売予定", "lead": None, "kind": "label", "final_badge": False},
            "label_links": [],
            "months": listing_months(site, root, books, ("author", "price"), "label"),
            "others": None,
            **listing_common(site, root, books),
        }
        page = page_defaults(title=f"{l['name']}（{l['pub']}）の漫画新刊発売予定｜{SITE_NAME}", description=f"{l['pub']}のレーベル「{l['name']}」から発売される漫画の新刊を、発売日順に紹介しています。", menu="label")
        w.write(f"label/{l['id']}/index.html", "listing.html", page, **ctx)
    # タグ
    for slug, (name, lead) in TAG_INFO.items():
        books = [b for b in site.dated if slug in b.tags]
        if not books:
            continue
        ctx = {
            "crumbs": crumbs(root, ("タグ", f"{root}tag/"), (f"#{name}", None)),
            "listing": {"en": "TAG", "title": f"#{name}の新刊発売予定", "lead": lead, "kind": "tag", "final_badge": slug == "final"},
            "label_links": [],
            "months": listing_months(site, root, books, ("author", "label", "price"), "tag"),
            "others": None,
            **listing_common(site, root, books),
        }
        page = page_defaults(title=f"#{name}の漫画新刊発売予定｜{SITE_NAME}", description=lead, tag=f"tag:{slug}")
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
        ctx = {
            "crumbs": crumbs(root, (f"{name}", None)),
            "listing": {"en": "AUTHOR", "title": f"{name}の新刊発売予定", "lead": f"{name}さんが関わる漫画の新刊を、発売日順に紹介しています。", "kind": "author", "final_badge": False},
            "label_links": [],
            "months": listing_months(site, root, books, ("label", "price"), "author"),
            "others": None,
            **listing_common(site, root, books),
        }
        page = page_defaults(title=f"{name}の漫画新刊発売予定｜{SITE_NAME}", description=f"{name}さんの漫画（コミック）の新刊を、発売日順に紹介しています。")
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


# ---- お気に入り ----
def build_favorites(site, w):
    root = "../"
    ctx = {"crumbs": crumbs(root, ("お気に入り", None)), "favorites_js": True}
    page = page_defaults(title=f"お気に入り｜{SITE_NAME}", description="お気に入りに登録した作品の新刊をまとめて見られます。", menu="favorites", noindex=True)
    w.write("favorites/index.html", "favorites.html", page, **ctx)


# ---- 検索 ----
def build_search(site, w):
    root = "../"
    items = []
    order = {b.id: i for i, b in enumerate(sorted(site.books, key=lambda b: (b.first_seen, b.id)))}
    for b in site.books:
        stores = {s["kind"]: s["url"] for s in site.stores(b)}
        items.append({
            "t": b.title, "p": b.publisher, "l": b.label or "", "a": site.author_text(b), "d": b.release.isoformat() if b.release else "",
            "e": bool(b.has_ebook), "u": f"../book/{b.key}/", "m": site.meta(b, ("author", "label", "price")), "s": stores, "f": order[b.id], "i": b.image, "ia": site.alt(b), "sr": b.series_id,
        })
    target = Path(w.out) / "search" / "index.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps({"items": items}, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    ctx = {
        "crumbs": crumbs(root, ("検索結果", None)),
        "options": search_options(site),
        "search": {"heading": "検索結果", "total": len(items), "q": "", "pub": "", "label": "", "month": "", "ebook": False, "conditions": [],
                   "range": "", "sort": "date", "results": [], "pages": []},
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
            pager = []
            if len(pages) > 1:
                for k in range(1, len(pages) + 1):
                    url = f"{root}{base}" if k == 1 else f"{root}{base}page/{k}/"
                    pager.append({"label": str(k), "url": url, "current": k == n, "next": False})
                if n < len(pages):
                    pager.append({"label": "次へ ›", "url": f"{root}{base}page/{n + 1}/", "current": False, "next": True})
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


def build_sitemap(site, w, site_url):
    if not site_url:
        return
    base = site_url.rstrip("/")
    urls = []
    for p in sorted(Path(w.out).rglob("index.html")):
        rel = p.relative_to(w.out).as_posix()[: -len("index.html")]
        if rel.startswith(("contact/thanks/", "favorites/")):
            continue
        urls.append(f"{base}/{rel}")
    body = "".join(f"<url><loc>{u}</loc></url>" for u in urls)
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
        import shutil
        shutil.rmtree(out)
    count = build(conn, out, today, dict(os.environ))
    print(f"{count} ページを生成しました（基準日 {today.isoformat()}）")


if __name__ == "__main__":
    main()
