"""ISBN のない重複の本を数える・まとめる（手動で実行する）。

ふだんは夜間の取得のあとに出版社ごとにまとめている。これは、すでにたまっている分を一度にまとめるためのもの。
"""
import argparse
import os
import sys
from collections import Counter

from . import db, store


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true", help="実際にまとめる（指定しなければ数えるだけ）")
    args = ap.parse_args(argv)
    conn = db.connect(os.environ.get("NEWCOMICS_DB") or db.DEFAULT_PATH)
    pairs = store.isbnless_title_duplicates(conn)
    by_pub = Counter(conn.execute("SELECT name FROM publishers WHERE id = ?", (r["publisher_id"],)).fetchone()["name"] for _, r in pairs)
    print(f"ISBN のない重複：{len(pairs)} 件")
    for name, n in by_pub.most_common():
        print(f"  {name}: {n} 件")
    for main, r in pairs[:10]:
        print(f"  例：{r['title']}（{r['release_date']}）→ ISBN {main['isbn13']}")
    if args.apply:
        merged = store.merge_isbnless_by_title(conn)
        conn.commit()
        print(f"まとめました：{merged} 件")
    return 0


if __name__ == "__main__":
    sys.exit(main())
