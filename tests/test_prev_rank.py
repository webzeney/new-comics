import tempfile
import unittest
from datetime import date, datetime, timedelta
from pathlib import Path

from newcomics import amazonlink, db


def item(asin, title, binding="コミック", rank=None):
    it = {"asin": asin, "itemInfo": {"title": {"displayValue": title}, "classifications": {"binding": {"displayValue": binding}}}}
    if rank:
        it["browseNodeInfo"] = {"browseNodes": [{"id": amazonlink.COMIC_NODE, "salesRank": rank}]}
    return it


class FakeApi:
    def __init__(self):
        self.calls = 0

    def search(self, words, **kw):
        self.calls += 1
        return [item("K1", "ONE PIECE 115 (ジャンプコミックスDIGITAL)", "Kindle版"), item("4088000115", "ONE PIECE 115 (ジャンプコミックス)")] if "115" in words else []

    def get(self, asins, resources=None):
        return [item(a, "x", rank=3) for a in asins]


class PrevRankTest(unittest.TestCase):
    def test_find_and_refresh(self):
        conn = db.connect(Path(tempfile.mkdtemp()) / "t.sqlite")
        conn.execute("INSERT INTO publishers (id, name, slug) VALUES (1, '集英社', 'shueisha')")
        conn.execute("INSERT INTO series (id, name, normalized_name, publisher_id) VALUES (1, 'ONE PIECE', 'onepiece', 1)")
        release = (date.today() + timedelta(days=10)).isoformat()
        conn.execute("INSERT INTO books (id, source_key, title, title_raw, volume, series_id, publisher_id, release_date, first_seen_at, last_seen_at, updated_at) "
                     "VALUES (1, 'k1', 'ONE PIECE 116', 'ONE PIECE 116', 116, 1, 1, ?, 'x', 'x', 'x')", (release,))
        conn.commit()
        now = datetime.now(db.JST)
        rows = amazonlink.prev_targets(conn, now, 10)
        self.assertEqual([r["id"] for r in rows], [1])
        api = FakeApi()
        c = amazonlink.find_prev(conn, api, rows, 10 ** 12)
        self.assertEqual(c["found"], 1)
        self.assertEqual(conn.execute("SELECT prev_asin FROM books WHERE id = 1").fetchone()[0], "4088000115")
        amazonlink.refresh_prev_ranks(conn, api, 10 ** 12)
        self.assertEqual(conn.execute("SELECT prev_rank FROM books WHERE id = 1").fetchone()[0], 3)
        self.assertEqual(amazonlink.prev_targets(conn, now, 10), [])


class FakeRakuten:
    def search(self, **kw):
        return {"Items": [{"title": "死んだ石井の大群（2）", "isbn": "9784065400000"}, {"title": "死んだ石井の大群（3）", "isbn": "9784065400017"}]}


class RakutenFallbackTest(unittest.TestCase):
    def test_rakuten_prev(self):
        self.assertEqual(amazonlink.rakuten_prev(FakeRakuten(), "死んだ石井の大群", 2), "4065400007")


if __name__ == "__main__":
    unittest.main()
