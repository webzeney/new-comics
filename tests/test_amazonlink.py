import unittest
from datetime import date

from newcomics import amazonlink


def item(asin, title, release, binding="Kindle版", adult=False):
    return {"asin": asin, "itemInfo": {
        "title": {"displayValue": title},
        "classifications": {"binding": {"displayValue": binding}},
        "contentInfo": {"publicationDate": {"displayValue": f"{release}T00:00:00.000Z"}},
        "productInfo": {"isAdultProduct": {"displayValue": adult}}}}


class PickTest(unittest.TestCase):
    def test_kindle_same_volume(self):
        items = [item("A", "作品名（２） (少年コミックス)", "2026-11-18"), item("B", "作品名（３） (少年コミックス)", "2026-11-18")]
        self.assertEqual(amazonlink.pick(items, "作品名", "作品名 3", 3, date(2026, 11, 18), True)["asin"], "B")

    def test_kindle_old_edition_is_skipped(self):
        items = [item("OLD", "作品名(3)", "2004-11-26")]
        self.assertIsNone(amazonlink.pick(items, "作品名", "作品名 3", 3, date(2026, 12, 25), True))

    def test_kindle_skips_paper_and_split(self):
        items = [item("P", "作品名 3", "2026-11-18", binding="コミック"), item("S", "作品名 3【単話版】", "2026-11-18")]
        self.assertIsNone(amazonlink.pick(items, "作品名", "作品名 3", 3, date(2026, 11, 18), True))

    def test_paper_needs_close_release_date(self):
        items = [item("K", "作品名 3", "2026-12-25"), item("OLD", "作品名(3)", "2015-12-17", binding="コミック"),
                 item("NEW", "作品名 新装版 3巻", "2026-12-24", binding="コミック")]
        self.assertEqual(amazonlink.pick(items, "作品名", "作品名 3", 3, date(2026, 12, 25), False)["asin"], "NEW")

    def test_adult_is_skipped(self):
        items = [item("X", "作品名 3", "2026-11-18", adult=True)]
        self.assertIsNone(amazonlink.pick(items, "作品名", "作品名 3", 3, date(2026, 11, 18), True))



class Isbn10Test(unittest.TestCase):
    def test_isbn10_to_13(self):
        from newcomics.normalize import isbn10_to_13
        self.assertEqual(isbn10_to_13("4301008675"), "9784301008675")
        self.assertEqual(isbn10_to_13("409855011X"[:9] + "3"), "9784098550111")
        self.assertIsNone(isbn10_to_13("B0ABCDEFGH"))


if __name__ == "__main__":
    unittest.main()


class FakeApi:
    def __init__(self, pages, search):
        self.pages, self.results = pages, search

    def get(self, asins):
        return [{"asin": a} for a in asins if a in self.pages]

    def search(self, words, **kw):
        return self.results.get(words, [])


class IsbnCheckTest(unittest.TestCase):
    def setUp(self):
        from newcomics import db
        self.conn = db.connect(":memory:")

    def test_isbn_page_or_other_asin(self):
        import time
        from datetime import datetime
        from newcomics import db
        c = self.conn
        pid = db.ensure_publisher(c, "pub", "出版社", None, "test")
        for i, isbn in enumerate(("9784040766379", "9784088845678", "9784091234567"), start=1):
            c.execute("INSERT INTO books (id, source_key, isbn13, title, title_raw, publisher_id, release_date, first_seen_at, last_seen_at, updated_at, authors) "
                      "VALUES (?, ?, ?, ?, ?, ?, '2026-11-09', 'x', 'x', 'x', '[]')", (i, f"k{i}", isbn, f"本 {i}", f"本 {i}", pid))
        other = item("B0H4SJNFN9", "本 1", "2026-11-09", binding="コミック")
        other["itemInfo"]["externalIds"] = {"eans": {"displayValues": ["9784040766379"]}}
        kindle = item("B0HP8QXSB2", "本 1", "2026-11-09")
        kindle["itemInfo"]["externalIds"] = {"eans": {"displayValues": ["9784040766379"]}}
        api = FakeApi({"4088845676"}, {"9784040766379": [kindle], "4040766377": [other]})
        rows = amazonlink.isbn_targets(c, datetime.now(db.JST), 100)
        counts = amazonlink.check_isbn(c, api, rows, time.monotonic() + 60)
        self.assertEqual(counts, {"ok": 1, "asin": 1, "missing": 1, "error": 0})
        got = {r[0]: (r[1], r[2]) for r in c.execute("SELECT id, amazon_isbn_ok, asin FROM books")}
        self.assertEqual(got, {1: (0, "B0H4SJNFN9"), 2: (1, None), 3: (0, None)})
        self.assertEqual(len(amazonlink.isbn_targets(c, datetime.now(db.JST), 100)), 0)


class SalesRankTest(unittest.TestCase):
    def test_comic_node_first(self):
        item = {"browseNodeInfo": {"browseNodes": [{"id": "2430812051", "salesRank": 298}, {"id": amazonlink.COMIC_NODE, "salesRank": 1110}]}}
        self.assertEqual(amazonlink.sales_rank(item), 1110)

    def test_other_node_or_none(self):
        self.assertEqual(amazonlink.sales_rank({"browseNodeInfo": {"browseNodes": [{"id": "1", "salesRank": 50}, {"id": "2", "salesRank": 20}]}}), 20)
        self.assertIsNone(amazonlink.sales_rank({}))
