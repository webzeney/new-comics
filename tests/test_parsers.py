import json
import tempfile
import unittest
from pathlib import Path

from newcomics import db, store
from newcomics.fetchers import shogakukan, shonengahosha, takeshobo
from newcomics.normalize import normalized_series, parse_volume, series_name

SHONENGAHOSHA = """
<table>
<tr><th>02（月）</th><td><div><span class="ico-zas">雑誌</span></div><b>サンプル雑誌 2026年23号</b><br><p><a href="https://7net.omni7.jp/detail/1"><img></a></p></td></tr>
<tr><th>09（月）</th><td><div><span class="ico-comi">コミックス</span></div><b>サンプル作品A 第11巻</b>　/　著者A<br>紹介文。<p><a href="https://7net.omni7.jp/detail/1107773374.html"><img></a><a href="https://books.rakuten.co.jp/rb/18813351/"><img></a></p></td></tr>
<tr><th>09（月）</th><td><div><span class="ico-comi">コミックス</span></div><b>サンプル作品B　第４巻</b>　/　著者B／著者C<br>紹介文。<p><a href="https://books.rakuten.co.jp/rb/18813352/"><img></a></p></td></tr>
<tr><th>09（月）</th><td><div><span class="ico-conv">コンビニコミックス</span></div><b>サンプル作品C No.69</b><br><p></p></td></tr>
</table>
"""

TAKESHOBO_LIST = """
<form><div class="resultWrap"><div class="booklist">
<div class="item"><div class="image"><a href="/book/b10193521.html"><img></a></div><div class="cont"><div class="tags"><span>バンブーコミックス</span></div><div class="ttl"><a href="/book/b10193521.html">サンプル作品D  3</a></div><div class="author"></div><div class="date">[ 2026/12/07 発売 ]</div></div></div>
<div class="item"><div class="image"><a href="/book/b10000001.html"><img></a></div><div class="cont"><div class="ttl"><a href="/book/b10000001.html">古い作品</a></div><div class="date">[ 2026/09/30 発売 ]</div></div></div>
</div></div></form>
"""

TAKESHOBO_DETAIL = """
<h1 class="pagetitle">サンプル作品D 3</h1>
<form><table><tr><th>ISBN</th><td><input></td></tr></table></form>
<div class="data"><table class="tableType1">
<tr><th>著者</th><td><a href="/author/a1.html">著者D</a>原作<br><a href="/author/a2.html">著者E</a>漫画</td></tr>
<tr><th>レーベル</th><td><a>バンブーコミックス</a> <a>異世界ＢＣ</a></td></tr>
<tr><th>出版年月日</th><td>2026/12/07</td></tr>
<tr><th>ISBN</th><td>9784801991088</td></tr>
<tr><th>定価</th><td>924円（税込）</td></tr>
</table></div>
"""

SHOGAKUKAN_LIST = """
<main><section><h2>発売予定</h2><ul class="month"><li>9月</li></ul><ul><li>少女・女性</li></ul>
<div id="female_comics"><h3>ちゃおの発売予定</h3><ul class="new_comic">
<li><a class="mh" href="/book?isbn=9784098735976"><p class="c1"><strong>キャッチ</strong></p><img><p>サンプル作品E</p><span>著者F</span></a><div><a href="/9784098735976">試し読み</a></div></li>
</ul></div>
<div id="light_novel"><ul class="new_comic"><li><a class="mh" href="/book?isbn=9784090000000"><p>ラノベ</p></a></li></ul></div>
</section></main>
"""

SHOGAKUKAN_DETAIL = """
<div class="title"><h1>サンプル作品E</h1><div class="author_list"><a>著者F</a></div></div>
<p>紙のコミックス</p><table class="volume"><tr><th>定価</th><td>594円(税込)</td></tr><tr><th>発売日</th><td>2026/10/26</td></tr><tr><th>ISBN</th><td>9784098735976</td></tr></table>
<p>電子版</p><table class="volume"><tr><th>配信日</th><td>2026/10/26</td></tr></table>
"""


class NormalizeTest(unittest.TestCase):
    def test_volume(self):
        self.assertEqual(parse_volume("サンプル作品A 第11巻"), 11)
        self.assertEqual(parse_volume("サンプル作品B　第４巻"), 4)
        self.assertEqual(parse_volume("サンプル作品D  3"), 3)
        self.assertEqual(parse_volume("サンプル作品（12）"), 12)
        self.assertEqual(parse_volume("サンプル作品 5 特装版"), 5)
        self.assertIsNone(parse_volume("サンプル作品E"))

    def test_series(self):
        self.assertEqual(series_name("サンプル作品A 第11巻"), "サンプル作品A")
        self.assertEqual(normalized_series("サンプル作品D  3"), normalized_series("サンプル作品D 4"))


class ParserTest(unittest.TestCase):
    def test_shonengahosha(self):
        records, skipped = shonengahosha.parse_month(SHONENGAHOSHA, 2026, 11)
        self.assertEqual(len(records), 2)
        self.assertEqual(len(skipped), 2)
        self.assertEqual(records[0].title_raw, "サンプル作品A 第11巻")
        self.assertEqual(records[0].release_date, "2026-11-09")
        self.assertEqual(records[0].authors, [{"name": "著者A", "role": None}])
        self.assertEqual(records[0].source_key, "shonengahosha:7net:1107773374")
        self.assertEqual(records[1].source_key, "shonengahosha:rb:18813352")
        self.assertEqual([a["name"] for a in records[1].authors], ["著者B", "著者C"])

    def test_takeshobo(self):
        items = takeshobo.parse_list(TAKESHOBO_LIST)
        self.assertEqual([i["id"] for i in items], ["b10193521", "b10000001"])
        self.assertEqual(items[0]["release_date"], "2026-12-07")
        detail = takeshobo.parse_detail(TAKESHOBO_DETAIL)
        self.assertEqual(detail["isbn13"], "9784801991088")
        self.assertEqual(detail["price"], 924)
        self.assertEqual(detail["release_date"], "2026-12-07")
        self.assertEqual(detail["label"], "バンブーコミックス 異世界BC".replace("BC", "ＢＣ"))
        self.assertEqual(detail["authors"], [{"name": "著者D", "role": "原作"}, {"name": "著者E", "role": "漫画"}])

    def test_shogakukan(self):
        items, excluded = shogakukan.parse_list(SHOGAKUKAN_LIST)
        self.assertEqual(items, [{"isbn13": "9784098735976", "title": "サンプル作品E"}])
        self.assertEqual(excluded, 1)
        detail = shogakukan.parse_detail(SHOGAKUKAN_DETAIL)
        self.assertEqual(detail["release_date"], "2026-10-26")
        self.assertEqual(detail["price"], 594)
        self.assertTrue(detail["has_ebook"])
        self.assertEqual(detail["authors"], [{"name": "著者F", "role": None}])


class StoreTest(unittest.TestCase):
    def test_change_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            conn = db.connect(Path(tmp) / "t.sqlite")
            pid = db.ensure_publisher(conn, "x", "X", "", "HTML")
            rec = store.BookRecord(source_key="x:1", title_raw="作品 第1巻", release_date="2026-11-01", isbn13="9784000000001")
            self.assertEqual(store.save(conn, pid, rec, "t1"), "new")
            rec2 = store.BookRecord(source_key="x:1", title_raw="作品 第1巻", release_date="2026-11-15")
            self.assertEqual(store.save(conn, pid, rec2, "t2"), "updated")
            kinds = [r["kind"] for r in conn.execute("SELECT kind FROM change_log ORDER BY id")]
            self.assertEqual(kinds, ["NEW", "日付変更"])
            book = conn.execute("SELECT * FROM books").fetchone()
            self.assertEqual(book["isbn13"], "9784000000001")
            self.assertEqual(book["volume"], 1)
            tags = [r["name"] for r in conn.execute("SELECT t.name FROM tags t JOIN book_tags bt ON bt.tag_id = t.id")]
            self.assertIn("新シリーズ1巻", tags)


if __name__ == "__main__":
    unittest.main()
