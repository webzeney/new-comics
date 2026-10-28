import json
import sqlite3
from datetime import datetime, timezone, timedelta
from pathlib import Path

JST = timezone(timedelta(hours=9))
DEFAULT_PATH = Path(__file__).resolve().parents[2] / "db" / "newcomics.sqlite"

SCHEMA = """
CREATE TABLE IF NOT EXISTS publishers (
  id INTEGER PRIMARY KEY,
  slug TEXT NOT NULL UNIQUE,
  name TEXT NOT NULL,
  source_url TEXT,
  fetch_method TEXT
);
CREATE TABLE IF NOT EXISTS labels (
  id INTEGER PRIMARY KEY,
  publisher_id INTEGER NOT NULL REFERENCES publishers(id),
  name TEXT NOT NULL,
  slug TEXT,
  is_adult INTEGER NOT NULL DEFAULT 0,
  UNIQUE (publisher_id, name)
);
CREATE TABLE IF NOT EXISTS series (
  id INTEGER PRIMARY KEY,
  publisher_id INTEGER NOT NULL REFERENCES publishers(id),
  name TEXT NOT NULL,
  normalized_name TEXT NOT NULL,
  latest_volume INTEGER,
  latest_release_date TEXT,
  UNIQUE (publisher_id, normalized_name)
);
CREATE TABLE IF NOT EXISTS books (
  id INTEGER PRIMARY KEY,
  source_key TEXT NOT NULL UNIQUE,
  isbn13 TEXT UNIQUE,
  title TEXT NOT NULL,
  title_raw TEXT NOT NULL,
  volume INTEGER,
  series_id INTEGER REFERENCES series(id),
  publisher_id INTEGER NOT NULL REFERENCES publishers(id),
  label_id INTEGER REFERENCES labels(id),
  authors TEXT NOT NULL DEFAULT '[]',
  release_date TEXT,
  date_status TEXT NOT NULL DEFAULT '確定',
  price INTEGER,
  has_ebook INTEGER,
  edition TEXT NOT NULL DEFAULT '通常',
  is_final INTEGER NOT NULL DEFAULT 0,
  asin TEXT,
  rakuten_code TEXT,
  source_url TEXT,
  first_seen_at TEXT NOT NULL,
  last_seen_at TEXT NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_books_release ON books(release_date);
CREATE INDEX IF NOT EXISTS idx_books_series ON books(series_id);
CREATE TABLE IF NOT EXISTS tags (
  id INTEGER PRIMARY KEY,
  name TEXT NOT NULL UNIQUE,
  slug TEXT NOT NULL UNIQUE
);
CREATE TABLE IF NOT EXISTS book_tags (
  book_id INTEGER NOT NULL REFERENCES books(id),
  tag_id INTEGER NOT NULL REFERENCES tags(id),
  PRIMARY KEY (book_id, tag_id)
);
CREATE TABLE IF NOT EXISTS change_log (
  id INTEGER PRIMARY KEY,
  book_id INTEGER NOT NULL REFERENCES books(id),
  kind TEXT NOT NULL,
  old_value TEXT,
  new_value TEXT,
  detected_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_change_log_detected ON change_log(detected_at);
CREATE TABLE IF NOT EXISTS fetch_runs (
  id INTEGER PRIMARY KEY,
  source TEXT NOT NULL,
  started_at TEXT NOT NULL,
  finished_at TEXT,
  item_count INTEGER,
  status TEXT NOT NULL DEFAULT 'running',
  error TEXT
);
"""


def now_iso():
    return datetime.now(JST).isoformat(timespec="seconds")


def connect(path=DEFAULT_PATH):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    return conn


def ensure_publisher(conn, slug, name, source_url, fetch_method):
    conn.execute(
        "INSERT INTO publishers (slug, name, source_url, fetch_method) VALUES (?, ?, ?, ?) "
        "ON CONFLICT(slug) DO UPDATE SET name = excluded.name, source_url = excluded.source_url, fetch_method = excluded.fetch_method",
        (slug, name, source_url, fetch_method),
    )
    return conn.execute("SELECT id FROM publishers WHERE slug = ?", (slug,)).fetchone()["id"]


def ensure_label(conn, publisher_id, name):
    if not name:
        return None
    conn.execute("INSERT OR IGNORE INTO labels (publisher_id, name) VALUES (?, ?)", (publisher_id, name))
    return conn.execute("SELECT id FROM labels WHERE publisher_id = ? AND name = ?", (publisher_id, name)).fetchone()["id"]


def ensure_series(conn, publisher_id, name, normalized_name):
    if not normalized_name:
        return None
    conn.execute(
        "INSERT OR IGNORE INTO series (publisher_id, name, normalized_name) VALUES (?, ?, ?)",
        (publisher_id, name, normalized_name),
    )
    return conn.execute(
        "SELECT id FROM series WHERE publisher_id = ? AND normalized_name = ?", (publisher_id, normalized_name)
    ).fetchone()["id"]


def ensure_tag(conn, name, slug):
    conn.execute("INSERT OR IGNORE INTO tags (name, slug) VALUES (?, ?)", (name, slug))
    return conn.execute("SELECT id FROM tags WHERE name = ?", (name,)).fetchone()["id"]


def find_book(conn, source_key, isbn13):
    row = conn.execute("SELECT * FROM books WHERE source_key = ?", (source_key,)).fetchone()
    if row is None and isbn13:
        row = conn.execute("SELECT * FROM books WHERE isbn13 = ?", (isbn13,)).fetchone()
    return row


def log_change(conn, book_id, kind, old_value, new_value, detected_at):
    conn.execute(
        "INSERT INTO change_log (book_id, kind, old_value, new_value, detected_at) VALUES (?, ?, ?, ?, ?)",
        (book_id, kind, old_value, new_value, detected_at),
    )


def dumps(value):
    return json.dumps(value, ensure_ascii=False)
