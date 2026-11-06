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


if __name__ == "__main__":
    unittest.main()
