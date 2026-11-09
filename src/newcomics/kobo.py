"""電子版ありの本に、楽天Kobo の電子書籍の商品ページへのリンクを付ける。

紙の本と電子書籍は ISBN が違うので、楽天Kobo電子書籍検索API を作品名で探し、書名に作品名と同じ巻数が入っている電子書籍を同じ本とみなす。
単話・分冊・モノクロ版などは、紙の本の書名に同じ言葉がないかぎり選ばない。
付けるのは楽天Kobo の商品ページへのリンクだけで、書名や価格などは変えない（CLAUDE.md の楽天ブックスAPIのルール）。
まだ探していない本を、発売日の新しい順に 1 回あたり MAX_CHECKS 冊まで探す。
見つからなかった本は RECHECK_DAYS 日たったら探し直す（電子版は紙より遅れて出ることがあるため）。
"""
import argparse
import os
import re
import sys
import time
import unicodedata
from datetime import datetime, timedelta

import requests

from . import db
from .fetchers import rakuten

ENDPOINT = "https://openapi.rakuten.co.jp/services/api/Kobo/EbookSearch/20170426"
MAX_CHECKS = 400
TIME_LIMIT = 12 * 60
RECHECK_DAYS = 7
SKIP_WORDS = ("単話", "分冊", "話売り", "モノクロ版", "カラー版", "フルカラー", "合本", "セット", "試し読み", "特装版", "限定版", "ノベライズ")


def key(text):
    t = unicodedata.normalize("NFKC", text or "").lower()
    return "".join(c for c in t if unicodedata.category(c)[0] in "LN")


def has_volume(title, volume):
    t = unicodedata.normalize("NFKC", title or "")
    if re.search(r"第\s*\d+\s*話", t):
        return False
    return re.search(rf"(?<!\d){volume}(?!\d)", t) is not None


def pick(items, series, title, volume):
    """候補の中から同じ本を選ぶ。書名がそのまま同じものを先に選ぶ。"""
    nt = unicodedata.normalize("NFKC", title or "")
    ok = []
    for it in items:
        kt = it.get("title") or ""
        nk = unicodedata.normalize("NFKC", kt)
        if any(w in nk and w not in nt for w in SKIP_WORDS):
            continue
        if key(series) in key(kt) and has_volume(kt, volume):
            ok.append(it)
    for it in ok:
        if key(it.get("title")) == key(title):
            return it
    return ok[0] if ok else None


class KoboApi(rakuten.Api):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.endpoint = ENDPOINT


def targets(conn, now, limit):
    since = (now - timedelta(days=RECHECK_DAYS)).isoformat(timespec="seconds")
    return conn.execute(
        """SELECT b.id, b.title, b.volume, s.name AS series FROM books b LEFT JOIN series s ON s.id = b.series_id
        WHERE b.has_ebook = 1 AND b.volume IS NOT NULL AND b.kobo_url IS NULL AND (b.kobo_checked_at IS NULL OR b.kobo_checked_at < ?)
        ORDER BY (b.kobo_checked_at IS NOT NULL), b.release_date DESC, b.id
        LIMIT ?""",
        (since, limit),
    ).fetchall()


def series_name(row):
    return row["series"] or re.sub(r"[\s(（]*\d+[)）]?\s*$", "", unicodedata.normalize("NFKC", row["title"]))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--max", type=int, default=MAX_CHECKS)
    args = ap.parse_args(argv)
    app_id, access_key = os.environ.get("RAKUTEN_APP_ID"), os.environ.get("RAKUTEN_ACCESS_KEY")
    if not app_id or not access_key:
        print("楽天Kobo の照らし合わせ：RAKUTEN_APP_ID / RAKUTEN_ACCESS_KEY が未設定のため省略します")
        return 0
    conn = db.connect()
    api = KoboApi(app_id, access_key, os.environ.get("RAKUTEN_AFFILIATE_ID"))
    rows = targets(conn, datetime.now(db.JST), args.max)
    start = time.monotonic()
    counts = {"found": 0, "missing": 0, "error": 0}
    for i, r in enumerate(rows, start=1):
        if time.monotonic() - start > TIME_LIMIT:
            break
        try:
            data = api.search(title=series_name(r), hits=30)
        except (requests.RequestException, rakuten.RakutenError, ValueError):
            counts["error"] += 1
            continue
        items = [x.get("Item", x) if isinstance(x, dict) else x for x in (data.get("Items") or [])]
        hit = pick(items, series_name(r), r["title"], r["volume"])
        url = (hit.get("affiliateUrl") or hit.get("itemUrl")) if hit else None
        counts["found" if url else "missing"] += 1
        conn.execute("UPDATE books SET kobo_url = ?, kobo_checked_at = ? WHERE id = ?", (url, db.now_iso(), r["id"]))
        if i % 50 == 0:
            conn.commit()
    conn.commit()
    left = conn.execute("SELECT COUNT(*) FROM books WHERE has_ebook = 1 AND kobo_url IS NULL AND kobo_checked_at IS NULL").fetchone()[0]
    print(f"楽天Kobo の照らし合わせ：見つかった {counts['found']}／見つからない {counts['missing']}／エラー {counts['error']}"
          f"（API {api.request_count} 回、まだ探していない本 残り {left} 冊）")
    # すべてエラーだったとき（認証情報が切れたときなど）は、実行を失敗にして気づけるようにする
    return 1 if counts["error"] and not (counts["found"] or counts["missing"]) else 0


if __name__ == "__main__":
    sys.exit(main())
