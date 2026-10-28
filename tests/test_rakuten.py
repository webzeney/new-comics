import tempfile
import unittest
from pathlib import Path

from newcomics import db, publishers, store
from newcomics.fetchers import rakuten


def item(isbn, title, sales, publisher="小学館", series="少年サンデーコミックス", size="コミック"):
    return {
        "title": title, "subTitle": "", "seriesName": series, "author": "作者A/作者B", "publisherName": publisher,
        "size": size, "isbn": isbn, "salesDate": sales, "itemPrice": 594, "itemUrl": f"https://books.rakuten.co.jp/rb/{isbn}/",
        "affiliateUrl": f"https://hb.afl.rakuten.co.jp/x/{isbn}", "largeImageUrl": f"https://thumbnail.image.rakuten.co.jp/{isbn}.jpg?_ex=200x200",
    }


class FakeApi:
    def __init__(self, pages):
        self.pages = pages
        self.calls = []

    def search(self, **params):
        self.calls.append(params)
        return {"Items": self.pages.get(params.get("page"), []), "pageCount": len(self.pages)}


class RakutenTest(unittest.TestCase):
    def test_sales_date(self):
        self.assertEqual(rakuten.parse_sales_date("2026年11月04日"), ("2026-11-04", "2026-11"))
        self.assertEqual(rakuten.parse_sales_date("2026年11月上旬"), (None, "2026-11"))
        self.assertEqual(rakuten.parse_sales_date("2026年11月04日頃"), (None, "2026-11"))
        self.assertEqual(rakuten.parse_sales_date("2027年"), (None, "2027-12"))

    def test_record(self):
        rec = rakuten.to_record(item("9784098000001", "作品（3）", "2026年11月04日"), True)
        self.assertEqual(rec.source_key, "rakuten:9784098000001")
        self.assertEqual(rec.label, "少年サンデーコミックス")
        self.assertEqual([a["name"] for a in rec.authors], ["作者A", "作者B"])
        self.assertEqual(rec.rakuten_url, "https://hb.afl.rakuten.co.jp/x/9784098000001")
        self.assertEqual(rec.image_url, "https://thumbnail.image.rakuten.co.jp/9784098000001.jpg")
        self.assertIsNone(rakuten.to_record(item("9784098000001", "画集", "2026年11月04日", size="単行本"), True))
        self.assertIsNone(rakuten.to_record(item("", "作品", "2026年11月04日"), True))

    def test_collect_stops_before_start(self):
        api = FakeApi({
            1: [item("9784000000011", "未来", "2027年02月01日"), item("9784000000012", "A 1", "2026年12月01日")],
            2: [item("9784000000013", "B 1", "2026年10月01日"), item("9784000000014", "古い", "2026年09月30日")],
            3: [item("9784000000015", "もっと古い", "2026年08月01日")],
        })
        rows = rakuten.collect(api, "001001", "2026-10", "2026-12", print)
        self.assertEqual([r["isbn"] for r in rows], ["9784000000012", "9784000000013"])
        self.assertEqual(len(api.calls), 2)

    def test_publisher_resolve(self):
        self.assertEqual(publishers.resolve("株式会社 小学館")[:2], ("shogakukan", "小学館"))
        self.assertEqual(publishers.resolve("スクウェア・エニックス")[0], "square-enix")
        slug, name, listed = publishers.resolve("未知の出版社")
        self.assertFalse(listed)
        self.assertTrue(slug.startswith("p"))


class MergeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.conn = db.connect(Path(self.tmp.name) / "t.sqlite")
        self.pid = db.ensure_publisher(self.conn, "shogakukan", "小学館", "", "HTML")

    def tearDown(self):
        self.conn.close()
        self.tmp.cleanup()

    def test_supplement_keeps_publisher_data(self):
        own = store.BookRecord(source_key="shogakukan:1", title_raw="作品 3", release_date="2026-11-18", isbn13="9784098000001", has_ebook=True)
        store.save(self.conn, self.pid, own, "t1")
        rec = rakuten.to_record(item("9784098000001", "作品（3）", "2026年11月20日"), True)
        self.assertEqual(store.save(self.conn, self.pid, rec, "t2"), "updated")
        b = self.conn.execute("SELECT * FROM books").fetchone()
        self.assertEqual(b["source_key"], "shogakukan:1")
        self.assertEqual(b["release_date"], "2026-11-18")
        self.assertEqual(b["price"], 594)
        self.assertEqual(b["rakuten_url"], "https://hb.afl.rakuten.co.jp/x/9784098000001")
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM books").fetchone()[0], 1)
        self.assertEqual([r["kind"] for r in self.conn.execute("SELECT kind FROM change_log")], ["NEW"])

    def test_match_without_isbn(self):
        own = store.BookRecord(source_key="shonengahosha:1", title_raw="サンプル作品A 第11巻", release_date="2026-11-09")
        store.save(self.conn, self.pid, own, "t1")
        rec = rakuten.to_record(item("9784785900001", "サンプル作品A 11", "2026年11月09日"), False)
        store.save(self.conn, self.pid, rec, "t2")
        rows = self.conn.execute("SELECT * FROM books").fetchall()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["isbn13"], "9784785900001")
        self.assertEqual(rows[0]["source_key"], "shonengahosha:1")

    def test_rakuten_only_book(self):
        rec = rakuten.to_record(item("9784098000002", "新作（1）", "2026年12月01日"), False)
        self.assertEqual(store.save(self.conn, self.pid, rec, "t1"), "new")
        later = rakuten.to_record(item("9784098000002", "新作（1）", "2026年12月05日"), False)
        store.save(self.conn, self.pid, later, "t2")
        kinds = [r["kind"] for r in self.conn.execute("SELECT kind FROM change_log ORDER BY id")]
        self.assertEqual(kinds, ["NEW", "日付変更"])


if __name__ == "__main__":
    unittest.main()
