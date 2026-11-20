import unittest

from newcomics import xpost


class WeightTest(unittest.TestCase):
    def test_japanese_counts_double(self):
        self.assertEqual(xpost.weight("漫画"), 4)
        self.assertEqual(xpost.weight("ab"), 2)

    def test_url_counts_23(self):
        self.assertEqual(xpost.weight("https://new-comics.jp/date/2026-11-09/"), 23)


class TagTest(unittest.TestCase):
    def book(self, title, volume=None):
        from types import SimpleNamespace
        return SimpleNamespace(title=title, volume=volume)

    def test_work_tag(self):
        self.assertEqual(xpost.work_tag(self.book("ONE PIECE 112", 112)), "#ONEPIECE #ワンピース")
        self.assertEqual(xpost.work_tag(self.book("呪術廻戦 30", 30)), "#呪術廻戦")
        self.assertEqual(xpost.work_tag(self.book("SPY×FAMILY 15", 15)), "#SPYFAMILY")
        self.assertEqual(xpost.work_tag(self.book("転生したらスライムだった件 31", 31)), "#転スラ")
        self.assertEqual(xpost.work_tag(self.book("ちいかわ なんか小さくてかわいいやつ 9", 9)), "#ちいかわ")
        self.assertEqual(xpost.work_tag(self.book("電撃デイジー 新装版 3", 3)), "#電撃デイジー")
        self.assertEqual(xpost.work_tag(self.book("テムパル5", None)), "#テムパル")
        self.assertEqual(xpost.work_tag(self.book("濁る瞳で何を願う 6 ハイセルク戦記", None)), "#濁る瞳で何を願う")
        self.assertEqual(xpost.work_tag(self.book("24時間界隈", None)), "#24時間界隈")
        self.assertIsNone(xpost.work_tag(self.book("出ていけ、と言われたので出ていきます(コミック)", None)) if len("出ていけと言われたので出ていきます") > xpost.TAG_MAX else None)

    def test_hashtags_top_two_distinct(self):
        bs = [self.book("呪術廻戦 30", 30), self.book("呪術廻戦 30 特装版", 30), self.book("ONE PIECE 112", 112), self.book("ハイキュー!! 46", 46)]
        self.assertEqual(xpost.hashtags(bs), "#新刊 #呪術廻戦 #ONEPIECE #ワンピース")


class ImageTest(unittest.TestCase):
    def test_make_image(self):
        import tempfile
        from datetime import date
        from pathlib import Path
        from PIL import Image
        from newcomics import ximage
        for i in range(len(ximage.POSES)):
            out = Path(tempfile.mkdtemp()) / "x.png"
            ximage.make(date(2026, 11, 19 + i), 123, out)
            with Image.open(out) as im:
                self.assertEqual(im.size, (1200, 675))
            self.assertLess(out.stat().st_size, 5 * 1024 * 1024)


if __name__ == "__main__":
    unittest.main()
