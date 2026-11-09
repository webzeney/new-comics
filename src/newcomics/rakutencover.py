"""書影のない本に、楽天の書影と商品ページへのリンクを付ける。

毎晩の楽天の取り込みは「今月から数か月分」の発売予定だけを見るので、それより前に発売された本は楽天と照らし合わせていない。
ここでは、ISBN が分かっていて書影がない本を 1 冊ずつ ISBN で楽天に問い合わせ、見つかれば書影・楽天の商品ページへのリンク・読み仮名を付ける。
ISBN が分からない本でも、Amazon の照らし合わせで紙の本の ASIN（= ISBN の10桁）が見つかっていれば、それを13桁に直して問い合わせる
（書影を付けることを優先する。2026-11-06 運営者の判断）。この ISBN は問い合わせに使うだけで、books.isbn13 には入れない。
出版社サイトの本の書名・価格などは変えない（CLAUDE.md の楽天ブックスAPIのルール）。
まだ問い合わせていない本を、発売日の新しい順に 1 回あたり MAX_CHECKS 冊まで問い合わせる。
見つからなかった本は RECHECK_DAYS 日たったら問い合わせ直す。

あわせて、紹介文（itemCaption）のない本も ISBN で問い合わせ、楽天の紹介文を付ける（books.rakuten_caption。
書籍詳細ページに出す。2026-11-09 運営者の判断）。書影の補完が終わったあとの残りの時間で行う。
"""
import argparse
import os
import sys
import time
from datetime import datetime, timedelta

import requests

from . import db
from .fetchers import rakuten
from .normalize import isbn10_to_13

MAX_CHECKS = 600
MAX_CAPTIONS = 1500
TIME_LIMIT = 25 * 60
RECHECK_DAYS = 30
PAPER_ASIN = "[0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9][0-9X]"  # ISBN-10 の形の ASIN（B0… の ASIN は楽天に問い合わせられない）


def targets(conn, now, limit):
    """問い合わせる本と、問い合わせに使う ISBN の組。"""
    since = (now - timedelta(days=RECHECK_DAYS)).isoformat(timespec="seconds")
    rows = conn.execute(
        """SELECT id, isbn13, asin FROM books
        WHERE (isbn13 IS NOT NULL OR asin GLOB ?) AND image_url IS NULL AND (rakuten_checked_at IS NULL OR rakuten_checked_at < ?)
        ORDER BY (rakuten_checked_at IS NOT NULL), release_date DESC, id
        LIMIT ?""",
        (PAPER_ASIN, since, limit),
    ).fetchall()
    out = []
    for r in rows:
        isbn = r["isbn13"] or isbn10_to_13(r["asin"])
        if isbn:
            out.append((r["id"], isbn))
    return out


def apply(conn, book_id, rec, checked_at):
    """見つかった本に書影・リンク・読み仮名を付ける。もとから入っている値は変えない。"""
    conn.execute(
        "UPDATE books SET image_url = COALESCE(image_url, ?), rakuten_url = COALESCE(rakuten_url, ?), "
        "title_kana = COALESCE(title_kana, ?), rakuten_caption = COALESCE(rakuten_caption, ?), rakuten_checked_at = ?, caption_checked_at = ? WHERE id = ?",
        (rec.image_url, rec.rakuten_url, rec.title_kana, rec.caption, checked_at, checked_at, book_id),
    )


def caption_targets(conn, now, limit):
    """紹介文のない本（ISBN の分かる本）と、問い合わせに使う ISBN の組。発売日の新しい順。"""
    since = (now - timedelta(days=RECHECK_DAYS)).isoformat(timespec="seconds")
    rows = conn.execute(
        """SELECT id, isbn13 FROM books
        WHERE isbn13 IS NOT NULL AND rakuten_caption IS NULL AND (caption_checked_at IS NULL OR caption_checked_at < ?)
        ORDER BY (caption_checked_at IS NOT NULL), release_date DESC, id LIMIT ?""",
        (since, limit),
    ).fetchall()
    return [(r["id"], r["isbn13"]) for r in rows]


def lookup(api, isbn):
    """楽天で ISBN が一致する本を BookRecord で返す。なければ None。"""
    data = api.search(isbn=isbn)
    for row in data.get("Items") or []:
        row = row.get("Item", row) if isinstance(row, dict) else row
        rec = rakuten.to_record(row, api.affiliate)
        if rec is not None and rec.isbn13 == isbn:
            return rec
    return None


def run(conn, api, rows, deadline, counts):
    for i, (book_id, isbn) in enumerate(rows, start=1):
        if time.monotonic() > deadline:
            break
        try:
            rec = lookup(api, isbn)
        except (requests.RequestException, rakuten.RakutenError, ValueError):
            counts["error"] += 1
            continue
        now = db.now_iso()
        if rec is None:
            counts["missing"] += 1
            conn.execute("UPDATE books SET rakuten_checked_at = ?, caption_checked_at = ? WHERE id = ?", (now, now, book_id))
        else:
            counts["found"] += 1
            counts["image"] += 1 if rec.image_url else 0
            counts["caption"] += 1 if rec.caption else 0
            apply(conn, book_id, rec, now)
        if i % 50 == 0:
            conn.commit()
    conn.commit()


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--max", type=int, default=MAX_CHECKS)
    ap.add_argument("--max-captions", type=int, default=MAX_CAPTIONS)
    ap.add_argument("--minutes", type=int, help="使う時間の上限（分）")
    args = ap.parse_args(argv)
    app_id, access_key = os.environ.get("RAKUTEN_APP_ID"), os.environ.get("RAKUTEN_ACCESS_KEY")
    if not app_id or not access_key:
        print("楽天の書影の補完：RAKUTEN_APP_ID / RAKUTEN_ACCESS_KEY が未設定のため省略します")
        return 0
    conn = db.connect()
    api = rakuten.Api(app_id, access_key, os.environ.get("RAKUTEN_AFFILIATE_ID"))
    now = datetime.now(db.JST)
    deadline = time.monotonic() + (args.minutes * 60 if args.minutes else TIME_LIMIT)
    covers = {"found": 0, "image": 0, "caption": 0, "missing": 0, "error": 0}
    run(conn, api, targets(conn, now, args.max), deadline, covers)
    captions = {"found": 0, "image": 0, "caption": 0, "missing": 0, "error": 0}
    run(conn, api, caption_targets(conn, now, args.max_captions), deadline, captions)
    left = conn.execute("SELECT COUNT(*) FROM books WHERE isbn13 IS NOT NULL AND image_url IS NULL AND rakuten_checked_at IS NULL").fetchone()[0]
    left_caption = conn.execute("SELECT COUNT(*) FROM books WHERE isbn13 IS NOT NULL AND rakuten_caption IS NULL AND caption_checked_at IS NULL").fetchone()[0]
    print(f"楽天の書影の補完：見つかった {covers['found']}（書影あり {covers['image']}）／見つからない {covers['missing']}／"
          f"エラー {covers['error']}（まだ問い合わせていない本 残り {left} 冊）")
    print(f"楽天の紹介文の補完：紹介文あり {captions['caption']}／紹介文なし {captions['found'] - captions['caption'] + captions['missing']}／"
          f"エラー {captions['error']}（API {api.request_count} 回、まだ問い合わせていない本 残り {left_caption} 冊）")
    # すべてエラーだったとき（認証情報が切れたときなど）は、実行を失敗にして気づけるようにする
    done = covers["found"] + covers["missing"] + captions["found"] + captions["missing"]
    return 1 if (covers["error"] or captions["error"]) and not done else 0


if __name__ == "__main__":
    sys.exit(main())
