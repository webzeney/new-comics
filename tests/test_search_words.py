import tempfile
import unittest
from pathlib import Path

from newcomics import db, store
from newcomics.build import load_aliases, search_key, search_words
from newcomics.fetchers import rakuten


class Fake:
    def __init__(self, id, title, series_id, title_kana=None):
        self.id, self.title, self.series_id, self.title_kana = id, title, series_id, title_kana


class SearchKeyTest(unittest.TestCase):
    def test_normalize(self):
        self.assertEqual(search_key("じゅじゅつ　カイセン"), "ジュジュツカイセン")
        self.assertEqual(search_key("SPY×FAMILY"), "spyfamily")
        self.assertEqual(search_key("ぼっち・ざ・ろっく！"), "ボッチザロック")
        self.assertEqual(search_key("怪獣８号"), "怪獣8号")


class SearchWordsTest(unittest.TestCase):
    def test_series_kana_and_alias(self):
        books = [Fake(1, "ONE PIECE 115", 7, "ワンピース 115"), Fake(2, "ONE PIECE 116", 7), Fake(3, "呪術廻戦 30", 8, "ジュジュツカイセン 30")]
        words = search_words(books, load_aliases())
        self.assertEqual(words[1], "ワンピース")
        self.assertEqual(words[2], "ワンピース")
        self.assertEqual(words[3], "ジュジュツカイセン")

    def test_no_extra_words(self):
        self.assertEqual(search_words([Fake(1, "テスト 1", 1, "テスト 1")], []), {})

    def test_alias_file(self):
        aliases = dict(load_aliases())
        self.assertIn("ヒロアカ", aliases[search_key("僕のヒーローアカデミア")])


class KanaStoreTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.conn = db.connect(Path(self.tmp.name) / "t.sqlite")
        self.pid = db.ensure_publisher(self.conn, "shueisha", "集英社", "", "HTML")

    def tearDown(self):
        self.conn.close()
        self.tmp.cleanup()

    def test_to_record_kana(self):
        rec = rakuten.to_record({"isbn": "9784088852348", "title": "ONE PIECE 116", "titleKana": "ワンピース 116", "salesDate": "2026年12月04日"}, False)
        self.assertEqual(rec.title_kana, "ワンピース 116")

    def test_publisher_book_gets_kana_only(self):
        pub = store.BookRecord(source_key="shueisha:9784088852348", title_raw="ONE PIECE 116", isbn13="9784088852348", price=572, release_date="2026-12-04")
        store.save(self.conn, self.pid, pub, "t1")
        rak = store.BookRecord(source_key="rakuten:9784088852348", title_raw="ONE PIECE 116", isbn13="9784088852348", price=999, release_date="2026-12-05", title_kana="ワンピース 116", rakuten_url="https://books.rakuten.co.jp/rb/1/")
        store.save(self.conn, self.pid, rak, "t2")
        row = self.conn.execute("SELECT * FROM books").fetchone()
        self.assertEqual(row["title_kana"], "ワンピース 116")
        self.assertEqual(row["price"], 572)
        self.assertEqual(row["release_date"], "2026-12-04")
        store.save(self.conn, self.pid, store.BookRecord(source_key="shueisha:9784088852348", title_raw="ONE PIECE 116", isbn13="9784088852348", price=572, release_date="2026-12-04"), "t3")
        self.assertEqual(self.conn.execute("SELECT title_kana FROM books").fetchone()[0], "ワンピース 116")


if __name__ == "__main__":
    unittest.main()
