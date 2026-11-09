"""楽天ブックス・楽天Kobo を ISBN か書名で調べる（特集記事を書くときの手動の調査用）。

楽天への問い合わせは、毎晩の取得と同じクライアント（1秒に1回以下）を使う。
"""
import argparse
import os
import re
import sys

from .fetchers import rakuten
from .kobo import KoboApi


def show(items, limit):
    for it in items[:limit]:
        print(" ", it.get("isbn") or it.get("itemNumber"), "|", it.get("title"), "|", it.get("publisherName"), "|", it.get("seriesName"), "|",
              it.get("salesDate"), "|", it.get("itemPrice"), "|", it.get("largeImageUrl"), "|", it.get("itemUrl"))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("query", help="ISBN（カンマ区切り）か書名（| 区切り）")
    ap.add_argument("--kobo", action="store_true", help="楽天Kobo（電子書籍）で調べる")
    ap.add_argument("--sort", default="-releaseDate", help="並び順（-releaseDate は新しい順、+releaseDate は古い順）")
    args = ap.parse_args(argv)
    keys = (os.environ.get("RAKUTEN_APP_ID"), os.environ.get("RAKUTEN_ACCESS_KEY"))
    if not all(keys):
        raise SystemExit("RAKUTEN_APP_ID / RAKUTEN_ACCESS_KEY が未設定です")
    api = KoboApi(*keys) if args.kobo else rakuten.Api(*keys)
    isbns = re.findall(r"97[89]\d{10}", args.query)
    if isbns:
        for isbn in isbns:
            items = (api.search(isbn=isbn).get("Items") or [])
            print("=====", isbn, len(items))
            show(items, 1)
        return 0
    extra = {} if args.kobo else {"outOfStockFlag": 1}
    for title in [t.strip() for t in args.query.split("|") if t.strip()]:
        rows = []
        for page in (1, 2, 3):
            data = api.search(title=title, sort=args.sort, hits=30, page=page, **extra)
            rows += data.get("Items") or []
            if page >= (data.get("pageCount") or 1):
                break
        print("=====", title, len(rows))
        show(rows, len(rows))
    return 0


if __name__ == "__main__":
    sys.exit(main())
