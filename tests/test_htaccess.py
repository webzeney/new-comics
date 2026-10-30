import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from newcomics import htaccess  # noqa: E402


class HtaccessTest(unittest.TestCase):
    def test_append_keeps_existing(self):
        before = b"RewriteEngine On\nRewriteRule ^x$ /y [R=301,L]"
        after = htaccess.patched(before)
        self.assertTrue(after.startswith(before + b"\n"))
        self.assertIn(b"AddHandler php-script .php .html", after)

    def test_no_change_when_marked(self):
        once = htaccess.patched(b"Options -Indexes\n")
        self.assertIsNone(htaccess.patched(once))

    def test_empty(self):
        self.assertTrue(htaccess.patched(None).startswith(htaccess.MARK.encode()))


if __name__ == "__main__":
    unittest.main()
