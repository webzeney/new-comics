"""Amazon の商品ページへの直リンクを付ける（Amazon Creators API）。

1. 電子版ありの本と、電子版の有無が分からない本：Kindle版を作品名で探し、書名に作品名と同じ巻数が入っている Kindle版を同じ本とみなす（books.kindle_asin）。
2. ISBN の分からない本：紙の本を書名で探し、作品名・巻数・発売日が合う本を同じ本とみなす（books.asin）。
付けるのは Amazon の商品ページへのリンク（ASIN）だけで、書名や価格などは変えない。
単話・分冊・カラー版などは、こちらの書名に同じ言葉がないかぎり選ばない。成人向けの商品は選ばない。
見つからなかった本は RECHECK_DAYS 日たったら探し直す。
"""
import argparse
import re
import sys
import time
import unicodedata
from datetime import date, datetime, timedelta

import requests

from . import db
from .amazon import AmazonError, Api, release_of, title_of
from .kobo import SKIP_WORDS, has_volume, key, series_name

MAX_KINDLE = 400
MAX_PAPER = 150
TIME_LIMIT = 14 * 60
RECHECK_DAYS = 7
PAPER_DAYS = 14   # 紙の本：発売日の差がこの日数以内なら同じ本とみなす
KINDLE_EARLY = 14  # Kindle版：紙の本の発売日よりこの日数より前に出ているものは、昔の版とみなして選ばない


def binding(item):
    c = (item.get("itemInfo") or {}).get("classifications") or {}
    return (c.get("binding") or {}).get("displayValue") or ""


def adult(item):
    p = (item.get("itemInfo") or {}).get("productInfo") or {}
    return bool((p.get("isAdultProduct") or {}).get("displayValue"))


def to_date(text):
    try:
        return date.fromisoformat(str(text)[:10])
    except (TypeError, ValueError):
        return None


def pick(items, series, title, volume, release, kindle):
    """候補の中から同じ本を選ぶ。書名がそのまま同じものを先に選ぶ。"""
    nt = unicodedata.normalize("NFKC", title or "")
    ok = []
    for it in items:
        if adult(it) or (binding(it) == "Kindle版") != kindle:
            continue
        t = title_of(it)
        nk = unicodedata.normalize("NFKC", t)
        if any(w in nk and w not in nt for w in SKIP_WORDS):
            continue
        if key(series) not in key(t):
            continue
        if volume is not None and not has_volume(t, volume):
            continue
        if volume is None and key(title) not in key(t):
            continue
        d = to_date(release_of(it))
        if release:
            if d is None:
                continue
            if kindle and d < release - timedelta(days=KINDLE_EARLY):
                continue
            if not kindle and abs((d - release).days) > PAPER_DAYS:
                continue
        elif not kindle:
            continue
        ok.append(it)
    for it in ok:
        if key(re.sub(r"\s*[(（][^()（）]*[)）]\s*$", "", unicodedata.normalize("NFKC", title_of(it)))) == key(title):
            return it
    return ok[0] if ok else None


def targets(conn, now, kind, limit):
    since = (now - timedelta(days=RECHECK_DAYS)).isoformat(timespec="seconds")
    if kind == "kindle":
        where = "(b.has_ebook = 1 OR b.has_ebook IS NULL) AND b.kindle_asin IS NULL AND (b.kindle_checked_at IS NULL OR b.kindle_checked_at < ?)"
        order = "b.kindle_checked_at IS NOT NULL, b.has_ebook IS NULL"
    else:
        where = "COALESCE(b.isbn13, '') = '' AND COALESCE(b.asin, '') = '' AND b.release_date IS NOT NULL AND (b.amazon_checked_at IS NULL OR b.amazon_checked_at < ?)"
        order = "b.amazon_checked_at IS NOT NULL"
    return conn.execute(
        f"""SELECT b.id, b.title, b.volume, b.release_date, s.name AS series FROM books b LEFT JOIN series s ON s.id = b.series_id
        WHERE {where} ORDER BY ({order}), b.release_date DESC, b.id LIMIT ?""",
        (since, limit),
    ).fetchall()


def run(conn, api, kind, rows, deadline):
    counts = {"found": 0, "missing": 0, "error": 0}
    col, checked = ("kindle_asin", "kindle_checked_at") if kind == "kindle" else ("asin", "amazon_checked_at")
    for i, r in enumerate(rows, start=1):
        if time.monotonic() > deadline:
            break
        name = series_name(r)
        words = name if kind == "kindle" else (f"{name} {r['volume']}" if r["volume"] is not None else r["title"])
        try:
            items = api.search(words, index="KindleStore" if kind == "kindle" else "Books", availability="IncludeOutOfStock")
        except (requests.RequestException, AmazonError, ValueError):
            counts["error"] += 1
            continue
        hit = pick(items, name, r["title"], r["volume"], to_date(r["release_date"]), kind == "kindle")
        counts["found" if hit else "missing"] += 1
        conn.execute(f"UPDATE books SET {col} = ?, {checked} = ? WHERE id = ?", (hit.get("asin") if hit else None, db.now_iso(), r["id"]))
        if i % 50 == 0:
            conn.commit()
    conn.commit()
    return counts


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--max-kindle", type=int, default=MAX_KINDLE)
    ap.add_argument("--max-paper", type=int, default=MAX_PAPER)
    args = ap.parse_args(argv)
    api = Api()
    if not api.ready():
        print("Amazon の照らし合わせ：AMAZON_CREATORS_ID / AMAZON_CREATORS_SECRET が未設定のため省略します")
        return 0
    conn = db.connect()
    now = datetime.now(db.JST)
    deadline = time.monotonic() + TIME_LIMIT
    paper = run(conn, api, "paper", targets(conn, now, "paper", args.max_paper), deadline)
    kindle = run(conn, api, "kindle", targets(conn, now, "kindle", args.max_kindle), deadline)
    left = conn.execute("SELECT COUNT(*) FROM books WHERE (has_ebook = 1 OR has_ebook IS NULL) AND kindle_asin IS NULL AND kindle_checked_at IS NULL").fetchone()[0]
    print(f"Amazon の照らし合わせ：ISBN の分からない本 見つかった {paper['found']}／見つからない {paper['missing']}／エラー {paper['error']}、"
          f"Kindle版 見つかった {kindle['found']}／見つからない {kindle['missing']}／エラー {kindle['error']}"
          f"（API {api.calls} 回、Kindle版をまだ探していない本 残り {left} 冊）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
