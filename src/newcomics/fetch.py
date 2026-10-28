import argparse
import sys
import traceback
from datetime import datetime

from . import db, store
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
        publisher_id = db.ensure_publisher(conn, module.SLUG, module.NAME, module.SOURCE_URL, module.FETCH_METHOD)
        known = store.known_isbn_dates(conn, publisher_id)
        records = module.fetch(client, conn, publisher_id, months, log, known=known)
        prev = previous_count(conn, module.SLUG)
        if prev and len(records) < prev * DROP_RATIO:
            raise RuntimeError(f"取得件数が前回の半分未満（前回 {prev} 件、今回 {len(records)} 件）。構造変更の疑いがあるため保存しません")
        counts = {"new": 0, "updated": 0, "same": 0}
        for rec in records:
            counts[store.save(conn, publisher_id, rec, run_at)] += 1
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
    ok = all([run_one(conn, client, FETCHERS[s], months, print) for s in slugs])
    print(f"リクエスト数: {client.request_count}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
