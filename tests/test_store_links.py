import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from newcomics.normalize import isbn13_to_10  # noqa: E402


class Isbn10Test(unittest.TestCase):
    def test_convert(self):
        self.assertEqual(isbn13_to_10("9784801991330"), "4801991335")
        self.assertEqual(isbn13_to_10("9784301008385"), "4301008381")
        self.assertEqual(isbn13_to_10("9784088820071"), "408882007X")

    def test_none(self):
        self.assertIsNone(isbn13_to_10("9791234567896"))
        self.assertIsNone(isbn13_to_10(None))


if __name__ == "__main__":
    unittest.main()
