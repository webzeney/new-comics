import tempfile
import unittest
from datetime import date
from pathlib import Path

from newcomics import db
from newcomics.build import Site


class TopSeriesTest(unittest.TestCase):
    def test_onepiece_first(self):
        conn = db.connect(Path(tempfile.mkdtemp()) / "t.sqlite")
        conn.execute("INSERT INTO publishers (id, name, slug) VALUES (1, '講談社', 'kodansha')")
        conn.execute("INSERT INTO publishers (id, name, slug) VALUES (2, '集英社', 'shueisha')")
        conn.execute("INSERT INTO series (id, name, normalized_name, publisher_id) VALUES (1, 'ONE PIECE', 'onepiece', 2)")
        conn.execute("INSERT INTO series (id, name, normalized_name, publisher_id) VALUES (2, 'あかね噺', 'あかね噺', 2)")
        conn.execute("INSERT INTO series (id, name, normalized_name, publisher_id) VALUES (3, 'ONE PIECE episode A', 'onepieceepisodea', 2)")
        rows = [
            (1, "ONE PIECE 116", 116, 1, 2, None),
            (2, "あかね噺 25", 25, 2, 2, 10),
            (3, "講談社の本 3", 3, None, 1, 5),
            (4, "ONE PIECE episode A 3", 3, 3, 2, 20),
        ]
        for i, t, v, s, p, r in rows:
            conn.execute("INSERT INTO books (id, source_key, title, title_raw, volume, series_id, publisher_id, release_date, amazon_rank, "
                         "first_seen_at, last_seen_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, '2026-12-04', ?, 'x', 'x', 'x')",
                         (i, f"k{i}", t, t, v, s, p, r))
        conn.commit()
        site = Site(conn, date(2026, 12, 4), {})
        titles = [b.title for b in site.by_date[date(2026, 12, 4)]]
        self.assertEqual(titles[0], "ONE PIECE 116")
        self.assertEqual(titles[1:3], ["あかね噺 25", "ONE PIECE episode A 3"])
        from newcomics.build import listing_past
        later = Site(conn, date(2027, 1, 10), {})
        past = listing_past(later, "../", [b for b in later.dated if b.publisher == "集英社"], ())
        self.assertEqual(past["dates"][0]["books"][0]["title"], "ONE PIECE 116")


if __name__ == "__main__":
    unittest.main()
