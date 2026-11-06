import unittest

from newcomics import xpost


class WeightTest(unittest.TestCase):
    def test_japanese_counts_double(self):
        self.assertEqual(xpost.weight("漫画"), 4)
        self.assertEqual(xpost.weight("ab"), 2)

    def test_url_counts_23(self):
        self.assertEqual(xpost.weight("https://new-comics.jp/date/2026-11-09/"), 23)


if __name__ == "__main__":
    unittest.main()
