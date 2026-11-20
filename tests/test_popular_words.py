import tempfile
import unittest
from datetime import date
from pathlib import Path

from newcomics import db
from newcomics.build import Site, popular_words


class PopularWordsTest(unittest.TestCase):
    def test_only_known_names(self):
        conn = db.connect(Path(tempfile.mkdtemp()) / "t.sqlite")
        conn.execute("INSERT INTO publishers (id, name, slug) VALUES (1, '集英社', 'shueisha')")
        conn.execute("INSERT INTO series (id, name, normalized_name, publisher_id) VALUES (1, 'ONE PIECE', 'onepiece', 1)")
        conn.execute("INSERT INTO series (id, name, normalized_name, publisher_id) VALUES (2, 'あかね噺', 'あかね噺', 1)")
        for i, t, v, s in [(1, "ONE PIECE 116", 116, 1), (2, "あかね噺 25", 25, 2)]:
            conn.execute("INSERT INTO books (id, source_key, title, title_raw, volume, series_id, publisher_id, release_date, first_seen_at, last_seen_at, updated_at) "
                         "VALUES (?, ?, ?, ?, ?, ?, 1, '2026-12-04', 'x', 'x', 'x')", (i, f"k{i}", t, t, v, s))
        rows = [("ワンピース", 5), ("one piece", 2), ("関係のない言葉", 50), ("集英社", 3), ("あかね噺", 2)]
        conn.executemany("INSERT INTO search_terms (term, count, updated_at) VALUES (?, ?, 'x')", rows)
        conn.commit()
        site = Site(conn, date(2026, 11, 21), {})
        words = popular_words(site)
        self.assertEqual([w["label"] for w in words], ["ONE PIECE", "集英社"])
        self.assertEqual(words[0]["url"], "search/?k=ONE%20PIECE")


if __name__ == "__main__":
    unittest.main()
