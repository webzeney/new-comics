import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from newcomics.fetchers import squareenix  # noqa: E402

CALENDAR = """<div class="calendarArea"><ul class="calendarList fo15">
<li><span class="dates">2026.11.6</span>
<div class="cont fo13">
<span class="tit01 fo11">マンガＵＰ！</span>
<p class="tit02 fo15">そうだ、売国しよう～天才王子の赤字国家再生術～　20</p>
<div class="moreTxt"><p>
	原作：鳥羽徹（ＧＡ文庫／ＳＢクリエイティブ）　構成：栗元健太郎　漫画：えむだ	</p></div>
<p>
	定価		：792円（税込）
</p>
</div>
</li>
<li><span class="dates">2026.11.6</span>
<div class="cont fo13">
<span class="tit01 fo11">マンガＵＰ！</span>
<p class="tit02 fo15">見捨てられた最弱テイマー、封印されていた美少女ドラゴンと契約して最強に至る　4(完)</p>
<div class="moreTxt"><p>原作：岸本和葉　漫画：冨田洋一郎</p></div>
<p>定価 ：792円（税込）</p>
</div>
</li>
<li><span class="dates">2026.11.13</span>
<div class="cont fo13">
<span class="tit01 fo11">SQEXノベル</span>
<p class="tit02 fo15">小説の本　2</p>
<p>定価 ：1,430円（税込）</p>
</div>
</li>
</ul></div>"""

MONTH = """<ul class="listComics">
<li class="comic_article">
<p class="tit fo11">ビッグガンガン</p>
<p class="img01"><a href="/top/comics/detail/9784301008385/"><img src="/x.jpg" alt=""></a></p>
<span class="dates fo15">2026.10.23</span>
<p class="txt fo15"><span class="numCol">ルビー・オンザ・ケーキ ー人喰い魔女の晩餐会ー</span><span class="numCol2">4(完)</span></p>
</li>
<li class="comic_article">
<p class="tit fo11">ヤングガンガン</p>
<p class="img01"><a href="/top/comics/detail/1000000000138/"><img src="/y.jpg" alt=""></a></p>
<span class="dates fo15">2026.10.23</span>
<p class="txt fo15"><span class="numCol">【フルカラー版】ゆうべはお楽しみでしたね</span><span class="numCol2">12</span></p>
</li>
</ul>
<p class="btnMore"><a href="#">もっと見る</a></p>"""

MORE_LAST = """<ul><li class="comic_article more2">
<p class="tit fo11">マンガＵＰ！</p>
<p class="img01"><a href="/top/comics/detail/9784301007906/"><img src="/z.jpg" alt=""></a></p>
<span class="dates fo15">2026.10.7</span>
<p class="txt fo15"><span class="numCol">劣等職の回復術師</span><span class="numCol2">3</span></p>
</li></ul><div id="data" data-nextlink="0"></div>"""

DETAIL = """<div class="comDetail clearfix">
<div class="cont fo15">
<p class="tit01 fo11">ビッグガンガン</p>
<p class="tit02 fo25">ルビー・オンザ・ケーキ ー人喰い魔女の晩餐会ー 4(完)</p>
<p class="tit03">
著者：森永ミキ<br>発売日：2026年10月23日
</p>
<p class="txt02">
定価790円（税込）　　<br class="spon">
判型：B6判　　<br class="spon">
ISBN：9784301008385<br>
</p>
</div>
</div>"""


class SquareEnixTest(unittest.TestCase):
    def test_calendar(self):
        items = squareenix.parse_calendar(CALENDAR)
        self.assertEqual(len(items), 3)
        a, b, c = items
        self.assertEqual(a["title"], "そうだ、売国しよう~天才王子の赤字国家再生術~ 20".replace("~", "～"))
        self.assertEqual(a["volume"], 20)
        self.assertEqual(a["release_date"], "2026-11-06")
        self.assertEqual(a["price"], 792)
        self.assertEqual(a["magazine"], "マンガUP!")
        self.assertEqual([x["role"] for x in a["authors"]], ["原作", "構成", "漫画"])
        self.assertEqual(b["volume"], 4)
        self.assertTrue(b["final"])
        self.assertTrue(b["title"].endswith(" 4"))
        self.assertEqual(c["magazine"], "SQEXノベル")

    def test_month(self):
        items, has_next = squareenix.parse_month(MONTH)
        self.assertTrue(has_next)
        self.assertEqual(items[0]["isbn13"], "9784301008385")
        self.assertEqual(items[0]["volume"], 4)
        self.assertTrue(items[0]["final"])
        self.assertIsNone(items[1]["isbn13"])
        self.assertEqual(items[1]["volume"], 12)
        more, has_next = squareenix.parse_month(MORE_LAST)
        self.assertFalse(has_next)
        self.assertEqual(len(more), 1)

    def test_detail(self):
        d = squareenix.parse_detail(DETAIL)
        self.assertEqual(d["price"], 790)
        self.assertEqual(d["isbn13"], "9784301008385")
        self.assertEqual(d["authors"], [{"name": "森永ミキ", "role": None}])

    def test_record_label(self):
        item = squareenix.parse_calendar(CALENDAR)[0]
        rec = squareenix.record(item, item["price"], item["authors"]).finalize()
        self.assertEqual(rec.label, "ガンガンコミックスUP!")
        self.assertEqual(rec.volume, 20)
        self.assertTrue(rec.source_key.startswith("square-enix:t:"))


if __name__ == "__main__":
    unittest.main()
