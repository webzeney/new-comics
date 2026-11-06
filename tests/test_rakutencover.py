import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from newcomics import db, rakutencover, store


class FakeApi:
    affiliate = False

    def __init__(self, items):
        self.items = items
        self.request_count = 0

    def search(self, **params):
        self.request_count += 1
        return {"Items": [i for i in self.items if i["isbn"] == params["isbn"]]}


class RakutenCoverTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.conn = db.connect(Path(self.tmp.name) / "t.sqlite")
        pid = db.ensure_publisher(self.conn, "shogakukan", "小学館", "", "HTML")
        for isbn, title in (("9784091000011", "作品 1"), ("9784091000028", "作品 2")):
            store.save(self.conn, pid, store.BookRecord(source_key=f"shogakukan:{isbn}", title_raw=title, isbn13=isbn, price=500, release_date="2020-01-01"), "t1")

    def tearDown(self):
        self.conn.close()
        self.tmp.cleanup()

    def test_fill_cover_only(self):
        api = FakeApi([{"isbn": "9784091000011", "title": "別の書名 1", "titleKana": "サクヒン 1", "itemPrice": 999, "salesDate": "2021年05月01日",
                        "itemUrl": "https://books.rakuten.co.jp/rb/1/", "largeImageUrl": "https://thumbnail.image.rakuten.co.jp/a.jpg?_ex=200x200"}])
        rows = rakutencover.targets(self.conn, datetime.now(db.JST), 10)
        self.assertEqual(len(rows), 2)
        for book_id, isbn in rows:
            rec = rakutencover.lookup(api, isbn)
            if rec is None:
                self.conn.execute("UPDATE books SET rakuten_checked_at = ? WHERE id = ?", ("2026-11-02T00:00:00+09:00", book_id))
            else:
                rakutencover.apply(self.conn, book_id, rec, "2026-11-02T00:00:00+09:00")
        hit = self.conn.execute("SELECT * FROM books WHERE isbn13 = '9784091000011'").fetchone()
        self.assertEqual(hit["image_url"], "https://thumbnail.image.rakuten.co.jp/a.jpg")
        self.assertEqual(hit["rakuten_url"], "https://books.rakuten.co.jp/rb/1/")
        self.assertEqual(hit["title_kana"], "サクヒン 1")
        self.assertEqual((hit["title"], hit["price"], hit["release_date"]), ("作品 1", 500, "2020-01-01"))
        self.assertEqual(rakutencover.targets(self.conn, datetime(2026, 11, 3, tzinfo=db.JST), 10), [])

    def test_isbnless_book_uses_amazon_asin(self):
        pid = self.conn.execute("SELECT id FROM publishers").fetchone()["id"]
        store.save(self.conn, pid, store.BookRecord(source_key="shogakukan:cal:1", title_raw="作品 3 特装版", release_date="2020-01-01"), "t1")
        self.conn.execute("UPDATE books SET asin = '4301008675' WHERE source_key = 'shogakukan:cal:1'")
        rows = dict((isbn, book_id) for book_id, isbn in rakutencover.targets(self.conn, datetime.now(db.JST), 10))
        self.assertIn("9784301008675", rows)
        self.assertIsNone(self.conn.execute("SELECT isbn13 FROM books WHERE source_key = 'shogakukan:cal:1'").fetchone()["isbn13"])


if __name__ == "__main__":
    unittest.main()
