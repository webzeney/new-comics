"""楽天ブックスで、指定した出版社の本がどのジャンル・判型で登録されているかを調べる（一回きりの調査用）。

出版社名で検索し、発売日の新しい順にたどって、対象期間の本を一覧にする。
結果は TSV に書き出し、Actions の成果物として受け取る。書影・あらすじは書き出さない。
"""
import argparse
import csv
import os
import sqlite3
import sys

from .fetchers.rakuten import COMIC_SIZES, HITS, Api, parse_sales_date
from .normalize import isbn13

MAX_PAGE = 10
COLUMNS = ["検索した出版社", "楽天の出版社名", "発売日", "書名", "シリーズ", "判型", "ジャンルID", "ISBN", "判型がコミック", "データベースに登録済み"]


def known_isbns(db):
    if not db or not os.path.exists(db):
        return set()
    conn = sqlite3.connect(db)
    try:
        return {r[0] for r in conn.execute("select isbn from books where isbn is not null")}
    finally:
        conn.close()


def probe(api, publisher, start, end):
    rows = []
    for page in range(1, MAX_PAGE + 1):
        data = api.search(publisherName=publisher, sort="-releaseDate", hits=HITS, page=page, outOfStockFlag=1)
        items = data.get("Items") or data.get("items") or []
        if not items:
            break
        older = False
        for item in items:
            item = item.get("Item", item)
            key = parse_sales_date(item.get("salesDate") or "")[1] or ""
            if key and key < start:
                older = True
                continue
            if key and key > end:
                continue
            rows.append(item)
        if older or page >= (data.get("pageCount") or 0):
            break
    return rows


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--publishers", required=True, help="カンマ区切りの出版社名")
    ap.add_argument("--from", dest="start", required=True, help="YYYY-MM")
    ap.add_argument("--to", dest="end", required=True, help="YYYY-MM")
    ap.add_argument("--db")
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    api = Api(os.environ["RAKUTEN_APP_ID"], os.environ["RAKUTEN_ACCESS_KEY"])
    known = known_isbns(args.db)
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    with open(args.out, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, delimiter="\t")
        w.writerow(COLUMNS)
        for name in [p.strip() for p in args.publishers.split(",") if p.strip()]:
            items = probe(api, name, args.start, args.end)
            comic = 0
            for it in items:
                isbn = isbn13(it.get("isbn") or "") or (it.get("isbn") or "")
                is_comic = it.get("size") in COMIC_SIZES
                comic += is_comic
                w.writerow([name, it.get("publisherName", ""), it.get("salesDate", ""), it.get("title", ""), it.get("seriesName", ""),
                            it.get("size", ""), it.get("booksGenreId", ""), isbn, "はい" if is_comic else "いいえ", "はい" if isbn in known else "いいえ"])
            print(f"{name}：{len(items)} 件（判型がコミック {comic} 件）")
    print(f"楽天へのリクエスト：{api.request_count} 回")
    return 0


if __name__ == "__main__":
    sys.exit(main())
