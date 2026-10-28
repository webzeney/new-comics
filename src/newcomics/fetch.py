import argparse
import os
import sys
import traceback
from datetime import datetime

from . import db, publishers, store
from .fetchers import FETCHERS
from .http import PoliteClient

DROP_RATIO = 0.5


def target_months(today, count):
    months = []
    y, m = today.year, today.month
    for _ in range(count):
        months.append((y, m))
        m += 1
        if m > 12:
            y, m = y + 1, 1
    return months


def previous_count(conn, slug):
    row = conn.execute(
        "SELECT item_count FROM fetch_runs WHERE source = ? AND status = 'ok' ORDER BY id DESC LIMIT 1", (slug,)
    ).fetchone()
    return row["item_count"] if row else None


def run_one(conn, client, module, months, log):
    run_at = db.now_iso()
    cur = conn.execute("INSERT INTO fetch_runs (source, started_at) VALUES (?, ?)", (module.SLUG, run_at))
    run_id = cur.lastrowid
    conn.commit()
    try:
        if getattr(module, "MULTI", False):
            publisher_id, known = None, {}
        else:
            publisher_id = db.ensure_publisher(conn, module.SLUG, module.NAME, module.SOURCE_URL, module.FETCH_METHOD)
            known = store.known_isbn_dates(conn, publisher_id)
        records = module.fetch(client, conn, publisher_id, months, log, known=known)
        prev = previous_count(conn, module.SLUG)
        if prev and len(records) < prev * DROP_RATIO:
            raise RuntimeError(f"取得件数が前回の半分未満（前回 {prev} 件、今回 {len(records)} 件）。構造変更の疑いがあるため保存しません")
        counts = {"new": 0, "updated": 0, "same": 0}
        unknown = set()
        for rec in records:
            pid = publisher_id
            if pid is None:
                slug, name, listed = publishers.resolve(rec.publisher_name)
                if not listed:
                    unknown.add(f"{name}（{slug}）")
                row = conn.execute("SELECT id FROM publishers WHERE slug = ?", (slug,)).fetchone()
                pid = row["id"] if row else db.ensure_publisher(conn, slug, name, None, module.NAME)
            counts[store.save(conn, pid, rec, run_at)] += 1
        if unknown:
            log(f"{module.NAME}: 対応表にない出版社 {len(unknown)} 社: " + "、".join(sorted(unknown)))
        conn.execute(
            "UPDATE fetch_runs SET finished_at = ?, item_count = ?, status = 'ok' WHERE id = ?",
            (db.now_iso(), len(records), run_id),
        )
        conn.commit()
        log(f"{module.NAME}: 新規 {counts['new']} / 更新 {counts['updated']} / 変化なし {counts['same']}")
        return True
    except Exception as exc:
        conn.rollback()
        conn.execute(
            "UPDATE fetch_runs SET finished_at = ?, status = 'error', error = ? WHERE id = ?",
            (db.now_iso(), f"{type(exc).__name__}: {exc}", run_id),
        )
        conn.commit()
        log(f"{module.NAME}: 失敗 {type(exc).__name__}: {exc}")
        traceback.print_exc()
        return False


def main(argv=None):
    parser = argparse.ArgumentParser(description="出版社サイトから新刊情報を取得する")
    parser.add_argument("--publisher", action="append", choices=sorted(FETCHERS), help="対象の出版社（省略時はすべて）")
    parser.add_argument("--months", type=int, default=3, help="当月から何か月分を対象にするか")
    parser.add_argument("--db", default=str(db.DEFAULT_PATH))
    args = parser.parse_args(argv)
    conn = db.connect(args.db)
    client = PoliteClient()
    months = target_months(datetime.now(db.JST).date(), args.months)
    slugs = args.publisher or list(FETCHERS)
    if not args.publisher and not (os.environ.get("RAKUTEN_APP_ID") and os.environ.get("RAKUTEN_ACCESS_KEY")):
        print("楽天ブックス: RAKUTEN_APP_ID / RAKUTEN_ACCESS_KEY が未設定のため省略します")
        slugs = [s for s in slugs if s != "rakuten"]
    ok = all([run_one(conn, client, FETCHERS[s], months, print) for s in slugs])
    print(f"リクエスト数: {client.request_count}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
