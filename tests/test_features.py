import unittest
from unittest import mock

from newcomics import build


class Resp:
    def __init__(self, data, ok=True):
        self.data, self.ok = data, ok

    def raise_for_status(self):
        if not self.ok:
            raise RuntimeError("bad")

    def json(self):
        return self.data


POST = [{"title": {"rendered": "記事"}, "link": "https://new-comics.jp/feature/archives/1", "_embedded": {"wp:term": [[{"taxonomy": "category", "name": "特集"}]]}}]
CACHED = [{"no": "01", "tag": "特集", "title": "前回の記事", "url": "https://new-comics.jp/feature/archives/9"}]


class FeaturesTest(unittest.TestCase):
    def setUp(self):
        self.sleep = mock.patch("time.sleep").start()
        self.addCleanup(mock.patch.stopall)

    def test_retries_then_succeeds(self):
        calls = [ConnectionError("x"), Resp(POST)]
        with mock.patch("requests.get", side_effect=lambda *a, **k: (lambda c: (_ for _ in ()).throw(c) if isinstance(c, Exception) else c)(calls.pop(0))):
            out = build.load_features({"FEATURE_API": "https://example.test/wp-json"}, base="https://new-comics.jp")
        self.assertEqual(out[0]["title"], "記事")

    def test_falls_back_to_last_published(self):
        def fake(url, **kw):
            if url.endswith("features.json"):
                return Resp(CACHED)
            raise ConnectionError("down")
        with mock.patch("requests.get", side_effect=fake):
            out = build.load_features({"FEATURE_API": "https://example.test/wp-json"}, base="https://new-comics.jp")
        self.assertEqual(out[0]["title"], "前回の記事")


if __name__ == "__main__":
    unittest.main()
