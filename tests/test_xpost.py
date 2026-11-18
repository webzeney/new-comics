import unittest

from newcomics import xpost


class WeightTest(unittest.TestCase):
    def test_japanese_counts_double(self):
        self.assertEqual(xpost.weight("漫画"), 4)
        self.assertEqual(xpost.weight("ab"), 2)

    def test_url_counts_23(self):
        self.assertEqual(xpost.weight("https://new-comics.jp/date/2026-11-09/"), 23)


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
