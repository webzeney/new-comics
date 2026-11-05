import unittest
from datetime import date

from newcomics.build import ics_fold, ics_text, series_calendar


class FakeBook:
    def __init__(self, id, title, release):
        self.id, self.key, self.title, self.release = id, f"978409{id:07d}", title, release
        self.publisher, self.label, self.first_seen = "集英社", "ジャンプコミックス", "2026-10-28T17:31:50+09:00"


class CalendarTest(unittest.TestCase):
    def test_escape_and_fold(self):
        self.assertEqual(ics_text("a,b;c\nd"), "a\\,b\;c\\nd")
        folded = ics_fold("SUMMARY:" + "あ" * 40)
        self.assertTrue(all(len(part.encode("utf-8")) <= 75 for part in folded.split("\r\n")))
        self.assertEqual(folded.replace("\r\n ", ""), "SUMMARY:" + "あ" * 40)

    def test_series_calendar(self):
        text = series_calendar("作品", [FakeBook(1, "作品 2", date(2026, 12, 4))], "https://new-comics.jp")
        self.assertTrue(text.startswith("BEGIN:VCALENDAR\r\n"))
        self.assertIn("DTSTART;VALUE=DATE:20261204\r\n", text)
        self.assertIn("DTEND;VALUE=DATE:20261205\r\n", text)
        self.assertIn("DTSTAMP:20261028T083150Z\r\n", text)
        self.assertEqual(text.count("BEGIN:VALARM"), 2)
        self.assertIn("TRIGGER:-PT3H\r\n", text)
        self.assertIn("TRIGGER:PT9H\r\n", text)
        self.assertTrue(text.endswith("END:VCALENDAR\r\n"))
        self.assertIn("URL:https://new-comics.jp/book/9784090000001/\r\n", text)

    def test_amazon_link(self):
        amazon = "https://www.amazon.co.jp/dp/4090000001?tag=newcomicsjp-22"
        text = series_calendar("作品", [FakeBook(1, "作品 2", date(2026, 12, 4))], "https://new-comics.jp", amazon_url=lambda b: amazon)
        unfolded = text.replace("\r\n ", "")
        self.assertIn(f"URL:{amazon}\r\n", unfolded)
        self.assertIn("Amazonで見る：" + amazon, unfolded)
        self.assertIn("漫画新刊JPで見る：https://new-comics.jp/book/9784090000001/", unfolded)


if __name__ == "__main__":
    unittest.main()
