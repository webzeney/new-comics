"""Amazon の商品ページへの直リンクを付ける（Amazon Creators API）。

1. 電子版ありの本と、電子版の有無が分からない本：Kindle版を作品名で探し、書名に作品名と同じ巻数が入っている Kindle版を同じ本とみなす（books.kindle_asin）。
2. ISBN の分からない本：紙の本を書名で探し、作品名・巻数・発売日が合う本を同じ本とみなす（books.asin）。
3. ISBN の分かる本：ISBN-10 の商品ページ（/dp/ISBN-10）が Amazon にあるかを確かめる（books.amazon_isbn_ok）。
   ない本（Amazon が ISBN-10 ではない ASIN で登録している本）は、ISBN-13 で探して EAN が同じ紙の本を同じ本とみなす（books.asin）。
   商品ページがあった本は確かめ直さない。見つからなかった本は ISBN_RECHECK_DAYS 日たったら確かめ直す。
4. 書影：紙の本の ASIN が分かる本は、Amazon の書影のアドレスを毎晩取り直す（books.amazon_image_url）。
   書籍詳細ページのメインの書影にだけ使い、Amazon の商品ページにリンクする。画像は保存せず、アドレスも24時間以内のものだけを使う
   （Amazon.co.jp Product Advertising API ライセンス契約 利用要件(d)(n)）。
Kindle版は、ISBN の分かる本は ISBN で探し、見つからなければ作品名で探す。
付けるのは Amazon の商品ページへのリンク（ASIN）だけで、書名や価格などは変えない。
単話・分冊・カラー版などは、こちらの書名に同じ言葉がないかぎり選ばない。成人向けの商品は選ばない。
見つからなかった本は RECHECK_DAYS 日たったら（毎晩）探し直す。
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
from .normalize import isbn13_to_10

MAX_KINDLE = 400
MAX_PAPER = 150
TIME_LIMIT = 30 * 60
RECHECK_DAYS = 1
MAX_ISBN = 3000   # 1晩に確かめる ISBN の数（10冊ずつまとめて問い合わせる）
ISBN_RECHECK_DAYS = 1
ISBN_TIME = 6 * 60  # ISBN の確認に使う時間の上限（Kindle版などの照らし合わせの時間を残す）
IMAGE_TIME = 15 * 60  # 書影の取り直しに使う時間の上限
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
        f"""SELECT b.id, b.title, b.volume, b.release_date, b.isbn13, s.name AS series FROM books b LEFT JOIN series s ON s.id = b.series_id
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
        if kind == "kindle":
            queries = ([r["isbn13"]] if r["isbn13"] else []) + [name]
        else:
            queries = [f"{name} {r['volume']}" if r["volume"] is not None else r["title"]]
        hit, failed = None, False
        for words in queries:
            try:
                items = api.search(words, index="KindleStore" if kind == "kindle" else "Books", availability="IncludeOutOfStock")
            except (requests.RequestException, AmazonError, ValueError):
                failed = True
                continue
            hit = pick(items, name, r["title"], r["volume"], to_date(r["release_date"]), kind == "kindle")
            if hit:
                break
        if failed and not hit:
            counts["error"] += 1
            continue
        counts["found" if hit else "missing"] += 1
        conn.execute(f"UPDATE books SET {col} = ?, {checked} = ? WHERE id = ?", (hit.get("asin") if hit else None, db.now_iso(), r["id"]))
        if i % 50 == 0:
            conn.commit()
    conn.commit()
    return counts


def eans(item):
    ids = (item.get("itemInfo") or {}).get("externalIds") or {}
    return set((ids.get("eans") or {}).get("displayValues") or [])


def isbn_targets(conn, now, limit, recheck=False):
    since = (now if recheck else now - timedelta(days=ISBN_RECHECK_DAYS)).isoformat(timespec="seconds")
    return conn.execute(
        """SELECT id, isbn13 FROM books WHERE COALESCE(isbn13, '') <> ''
        AND (amazon_isbn_ok IS NULL OR (amazon_isbn_ok = 0 AND COALESCE(asin, '') = '' AND (isbn_checked_at IS NULL OR isbn_checked_at < ?)))
        ORDER BY amazon_isbn_ok IS NOT NULL, release_date IS NULL, release_date DESC, id LIMIT ?""",
        (since, limit),
    ).fetchall()


def check_isbn(conn, api, rows, deadline):
    """ISBN-10 の商品ページがあるかを10冊ずつ確かめ、ない本は ISBN-13 で紙の本を探す。"""
    counts = {"ok": 0, "asin": 0, "missing": 0, "error": 0}
    # 979 で始まる ISBN には ISBN-10 がないので、商品ページの確認をせずに ISBN-13 で探す
    batch = [(r["id"], r["isbn13"], isbn13_to_10(r["isbn13"])) for r in rows]
    for i in range(0, len(batch), 10):
        if time.monotonic() > deadline:
            break
        chunk = batch[i:i + 10]
        asins = [c[2] for c in chunk if c[2]]
        try:
            found = {it.get("asin") for it in api.get(asins)} if asins else set()
        except (requests.RequestException, AmazonError, ValueError):
            counts["error"] += len(chunk)
            continue
        for book_id, isbn13, isbn10 in chunk:
            if isbn10 and isbn10 in found:
                counts["ok"] += 1
                conn.execute("UPDATE books SET amazon_isbn_ok = 1, isbn_checked_at = ? WHERE id = ?", (db.now_iso(), book_id))
                continue
            if time.monotonic() > deadline:
                break
            # ISBN-13 で探すと Kindle版しか出ないことがあるため、ISBN-10 → ISBN-13 の順に探す
            hit, failed = None, False
            for words in (w for w in (isbn10, isbn13) if w):
                try:
                    items = api.search(words, index="Books", availability="IncludeOutOfStock",
                                       resources=["itemInfo.title", "itemInfo.classifications", "itemInfo.productInfo", "itemInfo.externalIds"])
                except (requests.RequestException, AmazonError, ValueError):
                    failed = True
                    continue
                hit = next((it for it in items if isbn13 in eans(it) and binding(it) != "Kindle版" and not adult(it)), None)
                if hit:
                    break
            if failed and not hit:
                counts["error"] += 1
                continue
            counts["asin" if hit else "missing"] += 1
            conn.execute("UPDATE books SET amazon_isbn_ok = 0, asin = ?, isbn_checked_at = ? WHERE id = ?",
                         (hit.get("asin") if hit else None, db.now_iso(), book_id))
        conn.commit()
    return counts


def paper_asin(r):
    """書影を取る紙の本の ASIN。ISBN の分かる本は、商品ページを確かめ終えた本だけ（ISBN-10 のページがあれば ISBN-10、なければ見つけた ASIN）。"""
    if r["isbn13"]:
        if r["amazon_isbn_ok"] == 1:
            return isbn13_to_10(r["isbn13"])
        return r["asin"] if r["amazon_isbn_ok"] == 0 else None
    return r["asin"]


def image_url(item):
    p = ((item.get("images") or {}).get("primary") or {})
    return ((p.get("large") or p.get("medium") or {}).get("url")) or None


def refresh_images(conn, api, deadline):
    """書影のアドレスを取り直す。取り直せなかった本のアドレスは消す（古いアドレスを使わないように）。"""
    rows = conn.execute("""SELECT id, isbn13, asin, amazon_isbn_ok FROM books
        ORDER BY release_date IS NULL, release_date DESC, id""").fetchall()
    todo = [(r["id"], a) for r in rows if (a := paper_asin(r))]
    counts = {"image": 0, "none": 0, "error": 0, "left": 0}
    for i in range(0, len(todo), 10):
        chunk = todo[i:i + 10]
        if time.monotonic() > deadline:
            counts["left"] += len(todo) - i
            break
        try:
            items = {it.get("asin"): it for it in api.get([a for _, a in chunk], resources=["images.primary.large"])}
        except (requests.RequestException, AmazonError, ValueError):
            counts["error"] += len(chunk)
            continue
        now = db.now_iso()
        for book_id, asin in chunk:
            url = image_url(items[asin]) if asin in items else None
            counts["image" if url else "none"] += 1
            conn.execute("UPDATE books SET amazon_image_url = ?, amazon_image_at = ? WHERE id = ?", (url, now if url else None, book_id))
        conn.commit()
    # ASIN の分からなくなった本や、今回取り直せなかった本は、24時間を待たずに使わない
    conn.execute("UPDATE books SET amazon_image_url = NULL, amazon_image_at = NULL WHERE amazon_image_at IS NOT NULL AND amazon_image_at < ?",
                 ((datetime.now(db.JST) - timedelta(hours=23)).isoformat(timespec="seconds"),))
    conn.commit()
    return counts


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--max-kindle", type=int, default=MAX_KINDLE)
    ap.add_argument("--max-paper", type=int, default=MAX_PAPER)
    ap.add_argument("--max-isbn", type=int, default=MAX_ISBN)
    ap.add_argument("--isbn-only", action="store_true", help="ISBN-10 の商品ページの確認だけを行う（全件の確認用）")
    ap.add_argument("--minutes", type=int, help="使う時間の上限（分）")
    ap.add_argument("--recheck", action="store_true", help="見つからなかった本を、日数にかかわらず探し直す")
    ap.add_argument("--images", action="store_true", help="--isbn-only のあと、書影のアドレスも取り直す")
    args = ap.parse_args(argv)
    api = Api()
    if not api.ready():
        print("Amazon の照らし合わせ：AMAZON_CREATORS_ID / AMAZON_CREATORS_SECRET が未設定のため省略します")
        return 0
    conn = db.connect()
    now = datetime.now(db.JST)
    limit = args.minutes * 60 if args.minutes else TIME_LIMIT
    start = time.monotonic()
    isbn = check_isbn(conn, api, isbn_targets(conn, now, args.max_isbn, args.recheck), start + (limit if args.isbn_only else ISBN_TIME))
    rest = conn.execute("SELECT COUNT(*) FROM books WHERE COALESCE(isbn13, '') <> '' AND amazon_isbn_ok IS NULL").fetchone()[0]
    print(f"Amazon の商品ページの確認：ISBN-10 のページあり {isbn['ok']}／別の ASIN で見つかった {isbn['asin']}／見つからない {isbn['missing']}／エラー {isbn['error']}"
          f"（まだ確かめていない本 残り {rest} 冊）")
    if args.isbn_only and not args.images:
        print(f"（API {api.calls} 回）")
        return 0
    img = refresh_images(conn, api, min(start + limit, time.monotonic() + IMAGE_TIME))
    print(f"Amazon の書影：あり {img['image']}／なし {img['none']}／エラー {img['error']}／時間切れで取り直せなかった {img['left']}")
    if args.isbn_only:
        print(f"（API {api.calls} 回）")
        return 0
    deadline = start + limit
    paper = run(conn, api, "paper", targets(conn, now, "paper", args.max_paper), deadline)
    kindle = run(conn, api, "kindle", targets(conn, now, "kindle", args.max_kindle), deadline)
    left = conn.execute("SELECT COUNT(*) FROM books WHERE (has_ebook = 1 OR has_ebook IS NULL) AND kindle_asin IS NULL AND kindle_checked_at IS NULL").fetchone()[0]
    print(f"Amazon の照らし合わせ：ISBN の分からない本 見つかった {paper['found']}／見つからない {paper['missing']}／エラー {paper['error']}、"
          f"Kindle版 見つかった {kindle['found']}／見つからない {kindle['missing']}／エラー {kindle['error']}"
          f"（API {api.calls} 回、Kindle版をまだ探していない本 残り {left} 冊）")
    # すべてエラーだったとき（認証情報が切れたときなど）は、実行を失敗にして気づけるようにする
    done = isbn["ok"] + isbn["asin"] + isbn["missing"] + img["image"] + img["none"] + sum(c["found"] + c["missing"] for c in (paper, kindle))
    errors = isbn["error"] + img["error"] + paper["error"] + kindle["error"]
    return 1 if errors and not done else 0


if __name__ == "__main__":
    sys.exit(main())
