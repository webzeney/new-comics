import os
import tempfile
import unittest
from unittest import mock
from pathlib import Path

from newcomics import db, publishers, store
from newcomics import rakuten_select as sel
from newcomics.fetchers import rakuten


def item(isbn, title, sales, publisher="小学館", series="少年サンデーコミックス", size="コミック"):
    return {
        "title": title, "subTitle": "", "seriesName": series, "author": "作者A/作者B", "publisherName": publisher,
        "size": size, "isbn": isbn, "salesDate": sales, "itemPrice": 594, "itemUrl": f"https://books.rakuten.co.jp/rb/{isbn}/",
        "affiliateUrl": f"https://hb.afl.rakuten.co.jp/x/{isbn}", "largeImageUrl": f"https://thumbnail.image.rakuten.co.jp/{isbn}.jpg?_ex=200x200",
    }


class FakeApi:
    def __init__(self, pages):
        self.pages = pages
        self.calls = []

    def search(self, **params):
        self.calls.append(params)
        return {"Items": self.pages.get(params.get("page"), []), "pageCount": len(self.pages)}


class RakutenTest(unittest.TestCase):
    def test_sales_date(self):
        self.assertEqual(rakuten.parse_sales_date("2026年11月04日"), ("2026-11-04", "2026-11"))
        self.assertEqual(rakuten.parse_sales_date("2026年11月上旬"), (None, "2026-11"))
        self.assertEqual(rakuten.parse_sales_date("2026年11月04日頃"), ("2026-11-04", "2026-11"))
        self.assertEqual(rakuten.label_name("ヴァルキリーコミックス　457"), "ヴァルキリーコミックス")
        self.assertEqual(rakuten.label_name("ハーレクインコミックス　ハーレクインコミックス　CM1511"), "ハーレクインコミックス")
        self.assertEqual(rakuten.label_name("ハーレクインコミックス・キララ ハーレクインコミックス・キララ CMK1242"), "ハーレクインコミックス・キララ")
        self.assertEqual(rakuten.label_name("ハーパーコリンズ・フィクション ハーパーコリンズ・フィクション F35"), "ハーパーコリンズ・フィクション")
        self.assertEqual(rakuten.label_name("H&C Comics iHertZシリーズ069"), "H&C Comics iHertZシリーズ")
        self.assertEqual(rakuten.label_name("ちゃおコミックス スペシャル"), "ちゃおコミックス スペシャル")
        self.assertEqual(rakuten.label_name("ガンガンコミックスUP!"), "ガンガンコミックスUP!")
        self.assertEqual(rakuten.parse_sales_date("2027年"), (None, "2027-12"))

    def test_record(self):
        rec = rakuten.to_record(item("9784098000001", "作品（3）", "2026年11月04日"), True)
        self.assertEqual(rec.source_key, "rakuten:9784098000001")
        self.assertEqual(rec.label, "少年サンデーコミックス")
        self.assertEqual(rec.date_status, "確定")
        self.assertEqual(rakuten.to_record(item("9784098000003", "作品（4）", "2026年11月04日頃"), True).date_status, "予定")
        self.assertEqual([a["name"] for a in rec.authors], ["作者A", "作者B"])
        self.assertEqual(rec.rakuten_url, "https://hb.afl.rakuten.co.jp/x/9784098000001")
        self.assertEqual(rec.image_url, "https://thumbnail.image.rakuten.co.jp/9784098000001.jpg")
        self.assertIsNone(rakuten.to_record(item("", "作品", "2026年11月04日"), True))

    def test_collect_stops_before_start(self):
        api = FakeApi({
            1: [item("9784000000011", "未来", "2027年02月01日"), item("9784000000012", "A 1", "2026年12月01日")],
            2: [item("9784000000013", "B 1", "2026年10月01日"), item("9784000000014", "古い", "2026年09月30日")],
            3: [item("9784000000015", "もっと古い", "2026年08月01日")],
        })
        rows = rakuten.collect(api, "001001", "2026-10", "2026-12", print)
        self.assertEqual([r["isbn"] for r in rows], ["9784000000012", "9784000000013"])
        self.assertEqual(len(api.calls), 2)

    def test_collect_splits_when_pages_run_out(self):
        class Split:
            calls = []

            def search(self, **params):
                self.calls.append(params)
                if params.get("genreInformationFlag"):
                    return {"GenreInformation": [{"children": [{"booksGenreId": "001001001"}, {"booksGenreId": "001001002"}]}]}
                if params["booksGenreId"] == "001001":
                    return {"Items": [item(f"97840000{params['page']:05d}", "新 1", "2026年12月01日")], "pageCount": 100}
                rows = {"001001001": [item("9784000099001", "A 1", "2026年11月01日"), item("9784000099002", "古", "2026年09月01日")],
                        "001001002": [item("9784000099003", "B 1", "2026年10月01日")]}[params["booksGenreId"]]
                return {"Items": rows, "pageCount": 1}
        api = Split()
        rows = rakuten.collect(api, "001001", "2026-10", "2026-12", lambda m: None)
        self.assertEqual(sorted(r["isbn"] for r in rows), ["9784000099001", "9784000099003"])

    def test_collect_reports_gaps(self):
        class Capped:
            def search(self, **params):
                if params.get("genreInformationFlag"):
                    children = {"001001": [{"booksGenreId": "001001001"}], "001001001": [{"booksGenreId": "001001001001"}]}.get(params["booksGenreId"], [])
                    return {"GenreInformation": [{"children": children}]}
                count = {"001001": 5000, "001001001": 4000, "001001001001": 3000}[params["booksGenreId"]]
                return {"Items": [item("9784000000001", "新 1", "2026年12月01日")], "pageCount": 100, "count": count}
        report = {}
        rakuten.collect(Capped(), "001001", "2026-10", "2026-12", lambda m: None, report=report)
        self.assertEqual(len(report["gaps"]), 3)
        self.assertIn("001001001001", report["gaps"][0])
        self.assertIn("1000 件", report["gaps"][1])
        self.assertIn("1000 件", report["gaps"][2])

    def test_collect_no_gaps(self):
        report = {}
        api = FakeApi({1: [item("9784000000012", "A 1", "2026年12月01日")]})
        rakuten.collect(api, "001001", "2026-10", "2026-12", lambda m: None, report=report)
        self.assertEqual(report["gaps"], [])

    def test_write_summary(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "s.md"
            with mock.patch.dict(os.environ, {"GITHUB_STEP_SUMMARY": str(path)}), mock.patch("builtins.print") as out:
                rakuten.write_summary("2026-11", "2027-01", 10, 20, [])
                rakuten.write_summary("2026-11", "2027-01", 10, 20, ["ジャンル 001001001 は"])
            text = path.read_text(encoding="utf-8")
            self.assertIn("すべてたどりました", text)
            self.assertIn("取りこぼしのおそれ", text)
            out.assert_called_once_with("::warning title=楽天ブックス::ジャンル 001001001 は")

    def test_classify(self):
        def c(title, size="単行本", series="", publisher="小学館", isbn="9784000000001"):
            return sel.classify({"isbn": isbn, "title": title, "size": size, "seriesName": series, "publisherName": publisher})[0]
        self.assertEqual(c("作品 1", size="コミック", series=""), sel.ADOPT)
        self.assertEqual(c("作品 1", isbn="2100000000001"), sel.EXCLUDE)
        self.assertEqual(c("作品 1", isbn=""), sel.EXCLUDE)
        self.assertEqual(c("〇〇 ART WORKS"), sel.EXCLUDE)
        self.assertEqual(c("画業70周年 記念本", series="ビッグ コミックス"), sel.EXCLUDE)
        self.assertEqual(c("名探偵コナン手帳2027", size="カセット、ＣＤ等"), sel.EXCLUDE)
        self.assertEqual(c("作品 23 ポストカードブック付特装版", size="カセット、ＣＤ等", series="サンデーGXコミックス"), sel.ADOPT)
        self.assertEqual(c("作品", series="原画集・イラストブック"), sel.EXCLUDE)
        self.assertEqual(c("ドラえもん 287 〇〇編", size="ムックその他", series="My First BIG"), sel.ADOPT)
        self.assertEqual(c("こち亀 10月", size="ムックその他", series="集英社リミックス"), sel.ADOPT)
        self.assertEqual(c("〇〇ジャンプ", size="ムックその他", series="集英社ムック"), sel.REVIEW)
        self.assertEqual(c("作品 1", series="ビッグ コミックス"), sel.ADOPT)
        self.assertEqual(c("〇〇大事典", size="図鑑", series="ビッグ・コロタン"), sel.EXCLUDE)
        self.assertEqual(c("文庫版 作品 1", size="文庫", series="講談社文庫"), sel.ADOPT)
        self.assertEqual(c("小説 作品", size="文庫", series="講談社文庫"), sel.REVIEW)
        self.assertEqual(c("作品 1", publisher="文藝春秋"), sel.ADOPT)
        self.assertEqual(c("作品 15巻", publisher="三栄"), sel.ADOPT)
        self.assertEqual(c("コミックエッセイ 〇〇入門", publisher="宝島社"), sel.ADOPT)
        self.assertEqual(c("作品", publisher="小学館クリエイティブ"), sel.REVIEW)
        self.assertEqual(c("麻雀の戦術", series="近代麻雀戦術シリーズ", publisher="竹書房"), sel.REVIEW)

    def test_select_and_review_file(self):
        with tempfile.TemporaryDirectory() as d:
            conn = db.connect(Path(d) / "newcomics.sqlite")
            rows = [
                item("9784000000101", "作品 1", "2026年11月04日"),
                item("9784000000102", "作品 2", "2026年11月04日", publisher="文藝春秋", series="", size="単行本"),
                item("9784000000103", "迷う本", "2026年11月10日", publisher="某社", series="", size="単行本"),
                item("9784000000104", "〇〇 ART WORKS", "2026年11月10日", publisher="某社", series="", size="単行本"),
                item("2100000000105", "【楽天ブックス限定特典】作品 1", "2026年11月04日", size="単行本", series=""),
            ]
            chosen, stats = rakuten.select(conn, rows, "2026-11", "2026-11-01")
            self.assertEqual([r["isbn"] for r in chosen], ["9784000000101", "9784000000102"])
            self.assertEqual((stats["auto"], stats["pending"], stats["excluded"], stats["pending_new"]), (1, 1, 1, 1))
            path = Path(d) / sel.REVIEW_FILE
            lines = path.read_text(encoding="utf-8").splitlines()
            self.assertEqual(lines[0].split("\t"), sel.COLUMNS)
            self.assertEqual([l.split("\t")[3] for l in lines[1:]], ["9784000000103", "9784000000102", "9784000000104"])
            self.assertNotIn("2100000000105", path.read_text(encoding="utf-8"))
            pid = db.ensure_publisher(conn, "bunshun", "文藝春秋", None, "楽天ブックス")
            store.save(conn, pid, rakuten.to_record(rows[1], True), "t1")
            text = path.read_text(encoding="utf-8").replace("\n\t確認待ち", "\n載せる\t確認待ち").replace("\n\t自動で採用", "\n載せない\t自動で採用")
            text = text.replace("\n\t自動で除外", "\nのせる\t自動で除外")
            path.write_text("\ufeff" + text, encoding="utf-8")
            chosen, stats = rakuten.select(conn, rows, "2026-11", "2026-11-02")
            self.assertEqual([r["isbn"] for r in chosen], ["9784000000101", "9784000000103"])
            self.assertEqual((stats["yes"], stats["no"], stats["deleted"], stats["invalid"], stats["pending_new"]), (1, 1, 1, 1, 0))
            self.assertIsNone(conn.execute("SELECT id FROM books WHERE isbn13 = '9784000000102'").fetchone())
            again = sel.load(path)[0]
            self.assertEqual(again["9784000000103"]["初めて見た日"], "2026-11-01")
            self.assertEqual(again["9784000000104"]["判定"], "のせる")
            chosen, stats = rakuten.select(conn, rows[:1], "2026-12", "2026-12-01")
            self.assertEqual(set(sel.load(path)[0]), {"9784000000102", "9784000000103", "9784000000104"})
            conn.close()

    def test_rakuten_link_id(self):
        from newcomics.build import rakuten_link
        base = "https://hb.afl.rakuten.co.jp/hgc/a.b.c.d/?pc=https%3A%2F%2Fbooks.rakuten.co.jp%2Frb%2F1%2F"
        self.assertEqual(rakuten_link(base, "_RTLink153451"), "https://hb.afl.rakuten.co.jp/hgc/a.b.c.d/_RTLink153451?pc=https%3A%2F%2Fbooks.rakuten.co.jp%2Frb%2F1%2F")
        self.assertEqual(rakuten_link("https://hb.afl.rakuten.co.jp/hgc/a/_RTLink1?pc=x", "_RTLink153451"), "https://hb.afl.rakuten.co.jp/hgc/a/_RTLink153451?pc=x")
        self.assertEqual(rakuten_link("https://books.rakuten.co.jp/search?sitem=a", "_RTLink153451"), "https://books.rakuten.co.jp/search?sitem=a")
        self.assertEqual(rakuten_link(base, "new-comics"), base)
        self.assertIsNone(rakuten_link(None, "_RTLink153451"))

    def test_publisher_resolve(self):
        self.assertEqual(publishers.resolve("株式会社 小学館")[:2], ("shogakukan", "小学館"))
        self.assertEqual(publishers.resolve("スクウェア・エニックス")[0], "square-enix")
        slug, name, listed = publishers.resolve("未知の出版社")
        self.assertFalse(listed)
        self.assertTrue(slug.startswith("p"))


class MergeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.conn = db.connect(Path(self.tmp.name) / "t.sqlite")
        self.pid = db.ensure_publisher(self.conn, "shogakukan", "小学館", "", "HTML")

    def tearDown(self):
        self.conn.close()
        self.tmp.cleanup()

    def test_publisher_book_gets_only_rakuten_link(self):
        own = store.BookRecord(source_key="shogakukan:1", title_raw="作品 3", release_date="2026-11-18", isbn13="9784098000001", has_ebook=True)
        store.save(self.conn, self.pid, own, "t1")
        rec = rakuten.to_record(item("9784098000001", "作品（3）", "2026年11月20日"), True)
        self.assertEqual(store.save(self.conn, self.pid, rec, "t2"), "updated")
        b = self.conn.execute("SELECT * FROM books").fetchone()
        self.assertEqual(b["source_key"], "shogakukan:1")
        self.assertEqual(b["release_date"], "2026-11-18")
        self.assertIsNone(b["price"])
        self.assertEqual(b["origin"], "publisher")
        self.assertEqual(b["rakuten_url"], "https://hb.afl.rakuten.co.jp/x/9784098000001")
        self.assertEqual(b["image_url"], "https://thumbnail.image.rakuten.co.jp/9784098000001.jpg")
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM books").fetchone()[0], 1)
        self.assertEqual([r["kind"] for r in self.conn.execute("SELECT kind FROM change_log")], ["NEW"])

    def test_match_without_isbn(self):
        own = store.BookRecord(source_key="shonengahosha:1", title_raw="サンプル作品A 第11巻", release_date="2026-11-09")
        store.save(self.conn, self.pid, own, "t1")
        rec = rakuten.to_record(item("9784785900001", "サンプル作品A 11", "2026年11月09日"), False)
        store.save(self.conn, self.pid, rec, "t2")
        rows = self.conn.execute("SELECT * FROM books").fetchall()
        self.assertEqual(len(rows), 1)
        self.assertIsNone(rows[0]["isbn13"])
        self.assertEqual(rows[0]["source_key"], "shonengahosha:1")
        self.assertEqual(rows[0]["rakuten_url"], "https://books.rakuten.co.jp/rb/9784785900001/")

    def test_publisher_takes_over_rakuten_book(self):
        rec = rakuten.to_record(item("9784785900002", "サンプル作品B 4", "2026年11月09日"), False)
        store.save(self.conn, self.pid, rec, "t1")
        own = store.BookRecord(source_key="shonengahosha:2", title_raw="サンプル作品B 第4巻", release_date="2026-11-10")
        store.save(self.conn, self.pid, own, "t2")
        b = self.conn.execute("SELECT * FROM books").fetchone()
        self.assertEqual(b["origin"], "publisher")
        self.assertIsNone(b["isbn13"])
        self.assertIsNone(b["price"])
        self.assertEqual(b["authors"], "[]")
        self.assertEqual(b["rakuten_url"], "https://books.rakuten.co.jp/rb/9784785900002/")
        self.assertEqual(b["image_url"], "https://thumbnail.image.rakuten.co.jp/9784785900002.jpg")
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM books").fetchone()[0], 1)

    def test_isbn_found_later_merges_rakuten_copy(self):
        rec = rakuten.to_record(item("9784045002953", "別題名の本（3）", "2026年10月01日"), False)
        store.save(self.conn, self.pid, rec, "t1")
        own = store.BookRecord(source_key="kadokawa:1", title_raw="呪われた仮面公爵 3", release_date="2026-10-01")
        store.save(self.conn, self.pid, own, "t2")
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM books").fetchone()[0], 2)
        own2 = store.BookRecord(source_key="kadokawa:1", title_raw="呪われた仮面公爵 3", release_date="2026-10-01", isbn13="9784045002953")
        store.save(self.conn, self.pid, own2, "t3")
        rows = self.conn.execute("SELECT * FROM books").fetchall()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["origin"], "publisher")
        self.assertEqual(rows[0]["isbn13"], "9784045002953")
        self.assertEqual(rows[0]["rakuten_url"], "https://books.rakuten.co.jp/rb/9784045002953/")
        again = rakuten.to_record(item("9784045002953", "別題名の本（3）", "2026年10月01日"), False)
        self.assertEqual(store.save(self.conn, self.pid, again, "t4"), "same")
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM books").fetchone()[0], 1)

    def test_existing_rakuten_row_removed_when_publisher_copy_exists(self):
        rec = rakuten.to_record(item("9784098000009", "作品X（5）", "2026年11月01日"), False)
        store.save(self.conn, self.pid, rec, "t1")
        own = store.BookRecord(source_key="shogakukan:x", title_raw="作品X 5", release_date="2026-11-01")
        store.save(self.conn, self.pid, own, "t2")
        rows = self.conn.execute("SELECT * FROM books").fetchall()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["origin"], "publisher")

    def test_rakuten_only_book(self):
        rec = rakuten.to_record(item("9784098000002", "新作（1）", "2026年12月01日"), False)
        self.assertEqual(store.save(self.conn, self.pid, rec, "t1"), "new")
        later = rakuten.to_record(item("9784098000002", "新作（1）", "2026年12月05日"), False)
        store.save(self.conn, self.pid, later, "t2")
        kinds = [r["kind"] for r in self.conn.execute("SELECT kind FROM change_log ORDER BY id")]
        self.assertEqual(kinds, ["NEW", "日付変更"])


if __name__ == "__main__":
    unittest.main()
