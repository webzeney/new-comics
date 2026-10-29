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


from newcomics.fetchers import akitashoten, futabasha, hakusensha  # noqa: E402

AKITA_LIST = """
<div class="releaseDate">11月6日発売</div>
<div class="line soon clear">
<div class="book"><a href="/comics/4253019242" class="clear"><div class="bookInfo"><h2>僕の心のヤバイやつ【特装…</h2><span class="">マルチメディア</span><span class="authorName">桜井のりお</span><span class="date">発売日：2026.11.06</span></div></a></div>
<div class="book"><a href="/comics/4253019234" class="clear"><div class="bookInfo"><h2>僕の心のヤバイやつ 第14…</h2><span class="boys">少年チャンピオン・コミックス…</span><span class="authorName">桜井のりお</span><span class="date">発売日：2026.11.06</span></div></a></div>
</div>
"""

AKITA_DETAIL = """
<html><head><title>僕の心のヤバイやつ 第14巻 | 秋田書店</title></head><body>
<h1><img alt="秋田書店"></h1><h1>僕の心のヤバイやつ 第14巻</h1>
<div class="contents clear"><div class="detailSide"><ul class="clear">
<li> 著者：<a href="#">桜井のりお</a> </li><li> 定価：649円 (10%税込) </li><li> ISBN：978-4-253-01923-1 </li>
<li> レーベル：<a href="#">少年チャンピオン・コミックス（チャンピオンクロス）</a> </li><li> シリーズ：<a href="#">僕の心のヤバイやつ</a> </li></ul></div>
<div class="imageSide"><div class="date"> 発売日：2026.11.06 </div></div></div></body></html>
"""

FUTABA_CAL = """{"books":{"book_informations":[
{"jdcn_code":"97845754254060000000","isbn_code":"9784575425406","book_name":"作品A 9 【コミック】","publication_form":2,"release_dt":"2026-11-10","start_dt":null,"web_rbooks_id":18991,"web_ebooks_id":null,"age_verification":0,"label_name":"モンスターコミックスｆ","book_authors":[{"author_number":2,"author_name":"原作者","author_type_name":"原作"},{"author_number":1,"author_name":"作画者","author_type_name":"画","web_author_type_overwrite":null}]},
{"jdcn_code":"97845754254060000001","isbn_code":"9784575425406","book_name":"作品A 9 【コミック】","publication_form":2,"release_dt":null,"start_dt":"2026-11-10","web_rbooks_id":null,"web_ebooks_id":22766,"age_verification":0,"label_name":"モンスターコミックスｆ","book_authors":[]},
{"jdcn_code":"97800000230390000000","isbn_code":null,"book_name":"電子のみ ： 2","publication_form":2,"release_dt":null,"start_dt":"2026-11-01","web_rbooks_id":null,"web_ebooks_id":22774,"age_verification":0,"label_name":"KoiYui","book_authors":[]},
{"jdcn_code":"97845750000000000000","isbn_code":"9784575000009","book_name":"雑誌","publication_form":1,"release_dt":"2026-11-05","web_rbooks_id":1,"age_verification":0,"book_authors":[]}
]}}"""

HAKU_LIST = """
<h3 class="headingLine1 break">花とゆめコミックス</h3>
<table class="table1"><tr><th>タイトル</th><th>作家</th><th>発売日</th><th>試し読み</th></tr>
<tr><td class="txt3"><a href="https://www.hakusensha.co.jp/comicslist/80475/">ウチの万李がお世話になります 6</a></td><td class="txt3"><a href="#">海道ちとせ</a></td><td class="txt3 releaseDate">2026.11.05</td><td></td></tr></table>
<table class="table1"><tr><th>タイトル</th></tr>
<tr><td class="txt3"><a href="https://www.hakusensha.co.jp/booklist/80470/">画集</a></td><td class="txt3"><a href="#">作家</a></td><td class="txt3 releaseDate">2026.11.02</td><td></td></tr></table>
"""

HAKU_DETAIL = """
<div class="detailInnerTxt"><p class="txt12 color2">ウチの万李がお世話になります 6</p>
<p class="txt5 mtC linkStyle3">■著者名： <a href="#">海道ちとせ</a> </p><p class="txt5">■ISBNコード：9784592231745</p>
<p class="txt5">■シリーズ名：花とゆめコミックス</p><p class="txt5">■定価：594円（本体540円＋税10%）</p>
<p class="txt5">■発売日：<span class="releaseDate">2026.11.05</span></p></div>
"""


class AkitaTest(unittest.TestCase):
    def test_list(self):
        items = akitashoten.parse_list(AKITA_LIST)
        self.assertEqual([i["code"] for i in items], ["4253019242", "4253019234"])
        self.assertTrue(items[0]["excluded"])
        self.assertFalse(items[1]["excluded"])
        self.assertEqual(items[1]["release_date"], "2026-11-06")

    def test_detail(self):
        d = akitashoten.parse_detail(AKITA_DETAIL)
        self.assertEqual(d["title"], "僕の心のヤバイやつ 第14巻")
        self.assertEqual(d["isbn13"], "9784253019231")
        self.assertEqual(d["price"], 649)
        self.assertEqual(d["label"], "少年チャンピオン・コミックス（チャンピオンクロス）")
        self.assertEqual(d["release_date"], "2026-11-06")


class FutabaTest(unittest.TestCase):
    def test_calendar(self):
        items = futabasha.parse_calendar(FUTABA_CAL)
        self.assertEqual(len(items), 1)
        b = items[0]
        self.assertEqual(b["isbn13"], "9784575425406")
        self.assertEqual(b["release_date"], "2026-11-10")
        self.assertTrue(b["has_ebook"])
        self.assertEqual([a["name"] for a in b["authors"]], ["作画者", "原作者"])

    def test_price(self):
        self.assertEqual(futabasha.parse_price('{"book_details":{"rbook_price":740}}'), 814)
        self.assertEqual(futabasha.parse_price('{"book_details":[{"rbook_price":540}]}'), 594)
        self.assertIsNone(futabasha.parse_price('{"book_details":{"rbook_price":null}}'))


class HakusenshaTest(unittest.TestCase):
    def test_list(self):
        items = hakusensha.parse_list(HAKU_LIST)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["id"], "80475")
        self.assertEqual(items[0]["release_date"], "2026-11-05")

    def test_detail(self):
        d = hakusensha.parse_detail(HAKU_DETAIL)
        self.assertEqual(d["isbn13"], "9784592231745")
        self.assertEqual(d["label"], "花とゆめコミックス")
        self.assertEqual(d["price"], 594)
