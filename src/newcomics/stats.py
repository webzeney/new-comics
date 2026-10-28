"""発売日の範囲ごとに、出版社別・出どころ別の冊数を出す（取得結果の確認用）。

ログに出すのは件数だけ。書名などの個々のデータは出さない。
"""
import argparse
import sys

from . import db


def main(argv=None):
    parser = argparse.ArgumentParser(description="出版社別の冊数")
    parser.add_argument("--db", default=str(db.DEFAULT_PATH))
    parser.add_argument("--from", dest="start", required=True)
    parser.add_argument("--to", dest="end", required=True)
    args = parser.parse_args(argv)
    conn = db.connect(args.db)
    rows = conn.execute(
        "SELECT p.name, b.origin, COUNT(*) AS n FROM books b JOIN publishers p ON p.id = b.publisher_id "
        "WHERE b.release_date BETWEEN ? AND ? GROUP BY p.name, b.origin",
        (args.start, args.end),
    ).fetchall()
    totals = {}
    for r in rows:
        totals.setdefault(r["name"], {})[r["origin"]] = r["n"]
    undated = conn.execute("SELECT COUNT(*) FROM books WHERE release_date IS NULL").fetchone()[0]
    print(f"発売日 {args.start}〜{args.end}：{sum(r['n'] for r in rows)} 冊（出版社 {len(totals)} 社）／発売日未定 {undated} 冊")
    for name, by in sorted(totals.items(), key=lambda kv: -sum(kv[1].values())):
        print(f"{name}\t{sum(by.values())}\t出版社サイト {by.get('publisher', 0)}\t楽天 {by.get('rakuten', 0)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
