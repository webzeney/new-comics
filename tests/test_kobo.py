import unittest

from newcomics import kobo


class PickTest(unittest.TestCase):
    def test_exact_title_first(self):
        items = [{"title": "作品名 13"}, {"title": "作品名（３）"}, {"title": "作品名 3"}]
        self.assertEqual(kobo.pick(items, "作品名", "作品名 3", 3)["title"], "作品名（３）")

    def test_skip_episode_and_variants(self):
        items = [{"title": "作品名【単話版】 第3話"}, {"title": "作品名 モノクロ版 3"}, {"title": "作品名 第3話"}]
        self.assertIsNone(kobo.pick(items, "作品名", "作品名 3", 3))

    def test_variant_when_paper_has_it(self):
        items = [{"title": "作品名 カラー版 3"}]
        self.assertIsNotNone(kobo.pick(items, "作品名", "作品名 カラー版 3", 3))

    def test_skip_bara(self):
        items = [{"title": "作品名。［ばら売り］第8話［黒蜜］"}, {"title": "作品名。 1"}]
        self.assertEqual(kobo.pick(items, "作品名。", "作品名。 1", 1)["title"], "作品名。 1")

    def test_no_volume_needs_same_title(self):
        items = [{"title": "テラリウムの恋 番外編"}, {"title": "テラリウムの恋"}]
        self.assertEqual(kobo.pick(items, "テラリウムの恋", "テラリウムの恋", None)["title"], "テラリウムの恋")
        self.assertIsNone(kobo.pick([{"title": "テラリウムの恋 番外編"}], "テラリウムの恋", "テラリウムの恋", None))

    def test_series_name_fallback(self):
        self.assertEqual(kobo.series_name({"series": None, "title": "作品名（１２）"}), "作品名")


if __name__ == "__main__":
    unittest.main()
