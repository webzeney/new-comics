import unittest

from newcomics import db, store


class TitleDedupeTest(unittest.TestCase):
    def setUp(self):
        self.conn = db.connect(":memory:")
        pid = db.ensure_publisher(self.conn, "pub", "出版社", None, "test")
        self.pid = pid
        def add(key, title, isbn, date, vol=None):
            self.conn.execute(
                "INSERT INTO books (source_key, isbn13, title, title_raw, volume, publisher_id, release_date, first_seen_at, last_seen_at, updated_at, authors) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, 'x', 'x', 'x', '[]')", (key, isbn, title, title, vol, pid, date))
        add("a", "作品 4 特装版 小冊子付き", "9784301008675", "2026-11-06", 4)
        add("b", "作品 4 特装版 小冊子付き", None, "2026-11-06")
        add("c", "作品 4", "9784301008668", "2026-11-06", 4)
        add("d", "別の本 1", None, "2026-11-06")
        add("e", "作品 4 特装版 小冊子付き", None, "2026-12-01")

    def test_merges_only_same_title_and_date(self):
        self.assertEqual(store.merge_isbnless_by_title(self.conn, self.pid), 1)
        keys = {r["source_key"] for r in self.conn.execute("SELECT source_key FROM books")}
        self.assertEqual(keys, {"a", "c", "d", "e"})


if __name__ == "__main__":
    unittest.main()
