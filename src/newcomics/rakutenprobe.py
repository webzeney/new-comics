"""楽天ブックスで、指定した出版社の本がどのジャンル・判型で登録されているかを調べる（一回きりの調査用）。

出版社名で検索し、発売日の新しい順にたどって、対象期間の本を一覧にする。
結果は TSV に書き出し、Actions の成果物として受け取る。書影・あらすじは書き出さない。
"""
import argparse
import csv
import os
import sqlite3
import sys

from collections import Counter

from .fetchers.rakuten import COMIC_SIZES, HITS, ROOT_GENRE, Api, collect, parse_sales_date
from .normalize import isbn13

MAX_PAGE = 10
COLUMNS = ["検索した出版社", "楽天の出版社名", "発売日", "書名", "シリーズ", "判型", "ジャンルID", "ISBN", "判型がコミック", "データベースに登録済み"]


def known_isbns(db):
    if not db or not os.path.exists(db):
        return set()
    conn = sqlite3.connect(db)
    try:
        return {r[0] for r in conn.execute("select isbn13 from books where isbn13 is not null")}
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


def genre_mode(api, args, known):
    """コミックのジャンル全体をたどり、判型がコミック以外の本を一覧にする。出版社・シリーズ別の件数も書き出す。"""
    rows = collect(api, ROOT_GENRE, args.start, args.end, print)
    seen, out = set(), []
    for it in rows:
        isbn = isbn13(it.get("isbn") or "") or (it.get("isbn") or "")
        if isbn in seen:
            continue
        seen.add(isbn)
        out.append((it, isbn))
    sizes = Counter(it.get("size") or "（なし）" for it, _ in out)
    others = [(it, isbn) for it, isbn in out if it.get("size") not in COMIC_SIZES]
    with open(args.out, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, delimiter="\t")
        w.writerow(COLUMNS)
        for it, isbn in sorted(others, key=lambda x: (x[0].get("publisherName") or "", x[0].get("seriesName") or "", x[0].get("title") or "")):
            w.writerow(["（コミックのジャンル全体）", it.get("publisherName", ""), it.get("salesDate", ""), it.get("title", ""), it.get("seriesName", ""),
                        it.get("size", ""), it.get("booksGenreId", ""), isbn, "いいえ", "はい" if isbn in known else "いいえ"])
    base = args.out.rsplit(".", 1)[0]
    with open(base + "-summary.tsv", "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, delimiter="\t")
        w.writerow(["区分", "名前", "件数"])
        for k, v in sizes.most_common():
            w.writerow(["判型（コミックのジャンル全体）", k, v])
        for k, v in Counter(it.get("publisherName") or "" for it, _ in others).most_common():
            w.writerow(["出版社（判型がコミック以外）", k, v])
        for k, v in Counter((it.get("publisherName") or "") + "｜" + (it.get("seriesName") or "（シリーズなし）") for it, _ in others).most_common():
            w.writerow(["出版社｜シリーズ（判型がコミック以外）", k, v])
    print(f"コミックのジャンル全体：{len(out)} 件、うち判型がコミック以外 {len(others)} 件")
    print(f"楽天へのリクエスト：{api.request_count} 回")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--publishers", default="", help="カンマ区切りの出版社名")
    ap.add_argument("--genre", action="store_true", help="コミックのジャンル全体を調べる")
    ap.add_argument("--from", dest="start", required=True, help="YYYY-MM")
    ap.add_argument("--to", dest="end", required=True, help="YYYY-MM")
    ap.add_argument("--db")
    ap.add_argument("--out", required=True)
    args = ap.parse_args(argv)
    api = Api(os.environ["RAKUTEN_APP_ID"], os.environ["RAKUTEN_ACCESS_KEY"])
    known = known_isbns(args.db)
    os.makedirs(os.path.dirname(args.out) or ".", exist_ok=True)
    if args.genre:
        return genre_mode(api, args, known)
    with open(args.out, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, delimiter="\t")
        w.writerow(COLUMNS)
        for name in [p.strip() for p in args.publishers.split(",") if p.strip()]:
            try:
                items = probe(api, name, args.start, args.end)
            except Exception as e:
                w.writerow([name, "（エラー）", "", f"{type(e).__name__}: {str(e)[:300]}"] + [""] * (len(COLUMNS) - 4))
                print(f"{name}：エラー（{type(e).__name__}）")
                continue
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
