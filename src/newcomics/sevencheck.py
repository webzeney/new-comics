"""セブンネットに本があるかを確認する。

ISBN が分かる本について、セブンネットの商品ページ（/detail_isbn/ISBN）が開けるかを 1 冊ずつ確かめ、
books.seven_ok に 1（ある）か 0（ない）を記録する。ない本はページにセブンネットのボタンを出さない。
まだ確かめていない本を、発売日が近い順に 1 回あたり MAX_CHECKS 冊まで確かめる。
「ない」だった本は RECHECK_DAYS 日たったら確かめ直す（あとから登録されることがあるため）。
"""
import argparse
import sys
import time
from datetime import datetime, timedelta
from urllib.parse import urlsplit

import requests

from . import db
from .http import USER_AGENT, PoliteClient, RobotsDisallowed, TIMEOUT

BASE = "https://7net.omni7.jp"
URL = BASE + "/detail_isbn/{isbn}"
MAX_CHECKS = 600
TIME_LIMIT = 35 * 60
RECHECK_DAYS = 7


def check(client, isbn):
    """1（ある）・0（ない）・None（分からない）を返す。"""
    url = URL.format(isbn=isbn)
    if not client._robots_for(url).can_fetch(USER_AGENT, url):
        raise RobotsDisallowed(url)
    client._wait(urlsplit(url).netloc)
    res = client.session.get(url, timeout=TIMEOUT, allow_redirects=True)
    client.request_count += 1
    if res.status_code == 404:
        return 0
    if res.status_code == 200 and "/detail/" in res.url:
        return 1
    return None


def targets(conn, now, limit):
    today = now.date().isoformat()
    since = (now - timedelta(days=RECHECK_DAYS)).isoformat(timespec="seconds")
    return conn.execute(
        """SELECT id, isbn13 FROM books
        WHERE isbn13 IS NOT NULL AND (seven_checked_at IS NULL OR (seven_ok = 0 AND seven_checked_at < ?))
        ORDER BY (seven_checked_at IS NOT NULL), ABS(julianday(COALESCE(release_date, ?)) - julianday(?)), id
        LIMIT ?""",
        (since, today, today, limit),
    ).fetchall()


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--max", type=int, default=MAX_CHECKS)
    args = ap.parse_args(argv)
    conn = db.connect()
    client = PoliteClient()
    now = datetime.now(db.JST)
    rows = targets(conn, now, args.max)
    start = time.monotonic()
    counts = {1: 0, 0: 0, None: 0}
    for i, r in enumerate(rows, start=1):
        if time.monotonic() - start > TIME_LIMIT:
            break
        try:
            ok = check(client, r["isbn13"])
        except (requests.RequestException, RobotsDisallowed):
            ok = None
        counts[ok] += 1
        if ok is not None:
            conn.execute("UPDATE books SET seven_ok = ?, seven_checked_at = ? WHERE id = ?", (ok, db.now_iso(), r["id"]))
        if i % 50 == 0:
            conn.commit()
    conn.commit()
    left = conn.execute("SELECT COUNT(*) FROM books WHERE isbn13 IS NOT NULL AND seven_checked_at IS NULL").fetchone()[0]
    print(f"セブンネットの確認：あり {counts[1]}／なし {counts[0]}／不明 {counts[None]}（未確認 残り {left} 冊）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
