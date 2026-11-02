"""書影のない本に、楽天の書影と商品ページへのリンクを付ける。

毎晩の楽天の取り込みは「今月から数か月分」の発売予定だけを見るので、それより前に発売された本は楽天と照らし合わせていない。
ここでは、ISBN が分かっていて書影がない本を 1 冊ずつ ISBN で楽天に問い合わせ、見つかれば書影・楽天の商品ページへのリンク・読み仮名を付ける。
出版社サイトの本の書名・価格などは変えない（CLAUDE.md の楽天ブックスAPIのルール）。
まだ問い合わせていない本を、発売日の新しい順に 1 回あたり MAX_CHECKS 冊まで問い合わせる。
見つからなかった本は RECHECK_DAYS 日たったら問い合わせ直す。
"""
import argparse
import os
import sys
import time
from datetime import datetime, timedelta

import requests

from . import db
from .fetchers import rakuten

MAX_CHECKS = 600
TIME_LIMIT = 15 * 60
RECHECK_DAYS = 30


def targets(conn, now, limit):
    since = (now - timedelta(days=RECHECK_DAYS)).isoformat(timespec="seconds")
    return conn.execute(
        """SELECT id, isbn13 FROM books
        WHERE isbn13 IS NOT NULL AND image_url IS NULL AND (rakuten_checked_at IS NULL OR rakuten_checked_at < ?)
        ORDER BY (rakuten_checked_at IS NOT NULL), release_date DESC, id
        LIMIT ?""",
        (since, limit),
    ).fetchall()


def apply(conn, book_id, rec, checked_at):
    """見つかった本に書影・リンク・読み仮名を付ける。もとから入っている値は変えない。"""
    conn.execute(
        "UPDATE books SET image_url = COALESCE(image_url, ?), rakuten_url = COALESCE(rakuten_url, ?), "
        "title_kana = COALESCE(title_kana, ?), rakuten_checked_at = ? WHERE id = ?",
        (rec.image_url, rec.rakuten_url, rec.title_kana, checked_at, book_id),
    )


def lookup(api, isbn):
    """楽天で ISBN が一致する本を BookRecord で返す。なければ None。"""
    data = api.search(isbn=isbn)
    for row in data.get("Items") or []:
        row = row.get("Item", row) if isinstance(row, dict) else row
        rec = rakuten.to_record(row, api.affiliate)
        if rec is not None and rec.isbn13 == isbn:
            return rec
    return None


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--max", type=int, default=MAX_CHECKS)
    args = ap.parse_args(argv)
    app_id, access_key = os.environ.get("RAKUTEN_APP_ID"), os.environ.get("RAKUTEN_ACCESS_KEY")
    if not app_id or not access_key:
        print("楽天の書影の補完：RAKUTEN_APP_ID / RAKUTEN_ACCESS_KEY が未設定のため省略します")
        return 0
    conn = db.connect()
    api = rakuten.Api(app_id, access_key, os.environ.get("RAKUTEN_AFFILIATE_ID"))
    rows = targets(conn, datetime.now(db.JST), args.max)
    start = time.monotonic()
    counts = {"found": 0, "image": 0, "missing": 0, "error": 0}
    for i, r in enumerate(rows, start=1):
        if time.monotonic() - start > TIME_LIMIT:
            break
        try:
            rec = lookup(api, r["isbn13"])
        except (requests.RequestException, rakuten.RakutenError, ValueError):
            counts["error"] += 1
            continue
        now = db.now_iso()
        if rec is None:
            counts["missing"] += 1
            conn.execute("UPDATE books SET rakuten_checked_at = ? WHERE id = ?", (now, r["id"]))
        else:
            counts["found"] += 1
            counts["image"] += 1 if rec.image_url else 0
            apply(conn, r["id"], rec, now)
        if i % 50 == 0:
            conn.commit()
    conn.commit()
    left = conn.execute("SELECT COUNT(*) FROM books WHERE isbn13 IS NOT NULL AND image_url IS NULL AND rakuten_checked_at IS NULL").fetchone()[0]
    print(f"楽天の書影の補完：見つかった {counts['found']}（書影あり {counts['image']}）／見つからない {counts['missing']}／"
          f"エラー {counts['error']}（API {api.request_count} 回、まだ問い合わせていない本 残り {left} 冊）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
