import unittest

from newcomics.fetchers import kadokawa, kodansha

KODANSHA_LIST = """
<section data-scroll-anchor="shonenmagazine"><header><h3>週刊少年マガジン</h3></header>
<ul><li><div><a href="https://www.kodansha.co.jp/comic/products/0000434254">
<p> 2026年11月17日発売 </p><p> 千仙戦記（２） </p><p> 原作：エーテン，著：川崎 りゅうが </p><p> 定価：594円（本体540円） </p><span><svg></svg></span></a></div></li>
<li><div><a href="https://www.kodansha.co.jp/comic/products/0000433571">
<p> 2026年11月17日発売 </p><p> ドリーム☆ジャンボ☆ガール（７） </p><p> 著：ヒロユキ </p><p> 定価：594円（本体540円） </p></a></div></li></ul></section>
<section data-scroll-anchor="morning"><ul><li><div><a href="https://www.kodansha.co.jp/comic/products/0000434254"><p>2026年11月17日発売</p><p>千仙戦記（２）</p></a></div></li></ul></section>
"""

KODANSHA_DETAIL = """
<div><h4>紙版</h4><div><section><h5> 発売日 </h5><p> 2026年11月17日 </p></section>
<section><h5> ISBN </h5><p> 9784065460047 </p></section><section><h5> 価格 </h5><p> 定価：594円（本体540円） </p></section>
<section><h5> シリーズ </h5><p> 講談社コミックス </p></section></div></div>
<div><h4>電子版</h4><div><section><h5>配信日</h5><p>2026年11月17日</p></section></div></div>
"""

KADOKAWA_LIST = """
<h1>コミック  2026年10月の新刊カレンダー</h1>
<div class="calendar-main date-1"><div class="calendar-day"><span><p>1</p><p>(木)</p></span></div>
<div class="calendar-date-wrapper">
<div class="calendar-result-list"><div class="calendar-book-details"><div class="calendar-book-face"><a href="/product/322607000025/"><img alt=""></a></div>
<div class="calendar-book-detail"><div class="large-genre"><span class="book-info-label">コミック</span></div>
<div class="book-btn-wrap"><span><a href="/product/322607000025/#book-type">電子版</a></span></div>
<h2 class="book-title">呪われた仮面公爵に嫁いだ薄幸令嬢の掴んだ幸せ 3</h2>
<ul class="book-auther"><li>著者&nbsp;うさ沢 妹子</li><li>原作&nbsp;花宵</li></ul>
<div class="book-sub-info-wrap"><p class="book-info-text"><span class="book-info-price">定価&nbsp;<span class="money">924</span>円（本体<span class="money">840</span>円＋税）</span> <span class="book-info-label">レーベル：B's-LOG COMICS</span></p></div></div></div></div>
<div class="calendar-result-list"><div class="calendar-book-details"><div class="calendar-book-face"><a href="/product/322407001805/"><img alt=""></a></div>
<div class="calendar-book-detail"><div class="large-genre"><span class="book-info-label">コミック</span></div>
<h2 class="book-title">デスチューバースズキ【タテスク】</h2><ul class="book-auther"><li>作&nbsp;手持 望</li></ul>
<div class="book-sub-info-wrap"><p class="book-info-text"><span class="book-info-label">レーベル：タテスクコミック</span></p></div></div></div></div>
</div></div>
<div class="calendar-main date-15"><div class="calendar-date-wrapper">
<div class="calendar-result-list"><div class="calendar-book-details"><div class="calendar-book-face"><a href="/product/322606000088/"><img alt=""></a></div>
<div class="calendar-book-detail"><h2 class="book-title">F.S.S. EPISODES</h2><ul class="book-auther"><li>著者&nbsp;永野 護</li></ul>
<div class="book-sub-info-wrap"><p class="book-info-text"><span class="book-info-price">定価&nbsp;<span class="money">3,630</span>円（本体<span class="money">3,300</span>円＋税）</span></p></div></div></div></div>
</div></div>
"""


class KodanshaTest(unittest.TestCase):
    def test_list(self):
        items = kodansha.parse_list(KODANSHA_LIST)
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0]["id"], "0000434254")
        self.assertEqual(items[0]["release_date"], "2026-11-17")
        self.assertEqual(items[0]["title"], "千仙戦記（２）")
        self.assertEqual(items[0]["authors"], [{"name": "エーテン", "role": "原作"}, {"name": "川崎 りゅうが", "role": "著"}])
        self.assertEqual(items[0]["price"], 594)

    def test_detail(self):
        d = kodansha.parse_detail(KODANSHA_DETAIL)
        self.assertEqual(d["isbn13"], "9784065460047")
        self.assertEqual(d["label"], "講談社コミックス")
        self.assertTrue(d["has_ebook"])


class KadokawaTest(unittest.TestCase):
    def test_list(self):
        ym, items = kadokawa.parse_list(KADOKAWA_LIST)
        self.assertEqual(ym, (2026, 10))
        self.assertEqual([i["id"] for i in items], ["322607000025", "322606000088"])
        first = items[0]
        self.assertEqual(first["release_date"], "2026-10-01")
        self.assertEqual(first["price"], 924)
        self.assertEqual(first["label"], "B's-LOG COMICS")
        self.assertTrue(first["has_ebook"])
        self.assertEqual(first["authors"][0], {"name": "うさ沢 妹子", "role": "著者"})
        self.assertEqual(items[1]["release_date"], "2026-10-15")
        self.assertEqual(items[1]["price"], 3630)
        self.assertFalse(items[1]["has_ebook"])

    def test_detail(self):
        self.assertEqual(kadokawa.parse_detail("<p>判型：Ｂ６判 ページ数：178 ISBN：9784045002953</p>"), "9784045002953")


if __name__ == "__main__":
    unittest.main()
