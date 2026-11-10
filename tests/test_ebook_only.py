import sqlite3
import unittest
from datetime import date

from datetime import datetime

from newcomics import amazonlink, db, kobo
from newcomics.build import Site


class EbookOnlyTest(unittest.TestCase):
    def setUp(self):
        self.conn = db.connect(":memory:")
        pub = db.ensure_publisher(self.conn, "hakusensha", "白泉社", "https://example.com", "HTML")
        label = db.ensure_label(self.conn, pub, db.EBOOK_ONLY_LABEL)
        self.conn.execute(
            """INSERT INTO books (source_key, title, title_raw, volume, publisher_id, label_id, authors, release_date, has_ebook, edition, is_final,
            first_seen_at, last_seen_at, updated_at, ebook_only, kindle_asin, kobo_url, image_url)
            VALUES ('hakusensha:1', '作品 1', '作品 1', 1, ?, ?, '[]', '2026-11-11', 1, '通常', 0, 'x', 'x', 'x', 1, 'B0TESTTEST', 'https://books.rakuten.co.jp/rk/abc/', 'https://thumbnail.image.rakuten.co.jp/a.jpg')""",
            (pub, label))
        self.site = Site(self.conn, date(2026, 11, 10), {"AMAZON_TAG": "t-22"})
        self.book = self.site.books[0]

    def test_stores(self):
        stores = self.site.stores(self.book)
        self.assertEqual([s["kind"] for s in stores], ["kindle", "kobo"])
        self.assertEqual(stores[0]["url"], "https://www.amazon.co.jp/dp/B0TESTTEST?tag=t-22")
        self.assertEqual(stores[1]["url"], "https://books.rakuten.co.jp/rk/abc/")
        self.assertEqual(self.site.ebook_stores(self.book), [])
        self.assertIsNone(self.site.amazon_asin(self.book))

    def test_cover(self):
        self.assertEqual(self.book.image, "https://thumbnail.image.rakuten.co.jp/a.jpg")
        self.assertEqual(self.book.cover_url, "https://books.rakuten.co.jp/rk/abc/")

    def test_not_comic_hidden(self):
        self.conn.execute("UPDATE books SET title = '【アニマルデジタルフォトブック】名前「題」'")
        self.assertEqual(Site(self.conn, date(2026, 11, 10), {}).books, [])

    def test_targets(self):
        now = datetime.now(db.JST)
        self.conn.execute("UPDATE books SET kindle_asin = NULL, kobo_url = NULL")
        self.assertEqual(len(amazonlink.targets(self.conn, now, "kindle", 10)), 1)
        self.assertEqual(len(amazonlink.targets(self.conn, now, "paper", 10)), 0)
        self.assertEqual(len(kobo.targets(self.conn, now, 10)), 1)


if __name__ == "__main__":
    unittest.main()
