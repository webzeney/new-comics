from dataclasses import dataclass, field

from . import db
from .normalize import clean_title, detect_edition, detect_final, normalized_series, parse_volume, series_name

TAG_RULES = [
    ("新シリーズ1巻", "new-series", lambda r: r.volume == 1),
    ("完結巻", "final", lambda r: r.is_final),
    ("特装版・限定版", "special-edition", lambda r: r.edition != "通常"),
    ("電子同時配信", "ebook", lambda r: r.has_ebook is True),
]


@dataclass
class BookRecord:
    source_key: str
    title_raw: str
    release_date: str = None
    isbn13: str = None
    authors: list = field(default_factory=list)
    label: str = None
    price: int = None
    has_ebook: bool = None
    source_url: str = None
    date_status: str = "確定"
    volume: int = None
    title: str = None
    edition: str = None
    is_final: bool = None

    def finalize(self):
        self.title = self.title or clean_title(self.title_raw)
        if self.volume is None:
            self.volume = parse_volume(self.title_raw)
        if self.edition is None:
            self.edition = detect_edition(self.title_raw)
        if self.is_final is None:
            self.is_final = detect_final(self.title_raw)
        if not self.release_date:
            self.date_status = "未定"
        return self


def save(conn, publisher_id, rec, run_at):
    rec.finalize()
    label_id = db.ensure_label(conn, publisher_id, rec.label)
    series_id = db.ensure_series(conn, publisher_id, series_name(rec.title_raw), normalized_series(rec.title_raw))
    existing = db.find_book(conn, rec.source_key, rec.isbn13)
    values = {
        "source_key": rec.source_key,
        "isbn13": rec.isbn13,
        "title": rec.title,
        "title_raw": rec.title_raw,
        "volume": rec.volume,
        "series_id": series_id,
        "publisher_id": publisher_id,
        "label_id": label_id,
        "authors": db.dumps(rec.authors),
        "release_date": rec.release_date,
        "date_status": rec.date_status,
        "price": rec.price,
        "has_ebook": None if rec.has_ebook is None else int(rec.has_ebook),
        "edition": rec.edition,
        "is_final": int(bool(rec.is_final)),
        "source_url": rec.source_url,
    }
    if existing is None:
        cols = list(values) + ["first_seen_at", "last_seen_at", "updated_at"]
        args = list(values.values()) + [run_at, run_at, run_at]
        cur = conn.execute(
            f"INSERT INTO books ({', '.join(cols)}) VALUES ({', '.join('?' * len(cols))})", args
        )
        book_id = cur.lastrowid
        db.log_change(conn, book_id, "NEW", None, rec.release_date, run_at)
        status = "new"
    else:
        book_id = existing["id"]
        for key in ("isbn13", "price", "has_ebook", "label_id", "volume"):
            if values[key] is None:
                values[key] = existing[key]
        if values["authors"] == "[]":
            values["authors"] = existing["authors"]
        changed = [k for k in values if values[k] != existing[k]]
        if existing["release_date"] != rec.release_date and rec.release_date:
            kind = "日付決定" if existing["date_status"] == "未定" or not existing["release_date"] else "日付変更"
            db.log_change(conn, book_id, kind, existing["release_date"], rec.release_date, run_at)
        sets = ", ".join(f"{k} = ?" for k in values)
        conn.execute(
            f"UPDATE books SET {sets}, last_seen_at = ?{', updated_at = ?' if changed else ''} WHERE id = ?",
            list(values.values()) + [run_at] + ([run_at] if changed else []) + [book_id],
        )
        status = "updated" if changed else "same"
    for name, slug, rule in TAG_RULES:
        if rule(rec):
            tag_id = db.ensure_tag(conn, name, slug)
            conn.execute("INSERT OR IGNORE INTO book_tags (book_id, tag_id) VALUES (?, ?)", (book_id, tag_id))
    if series_id and rec.release_date:
        conn.execute(
            "UPDATE series SET latest_volume = (SELECT MAX(volume) FROM books WHERE series_id = ?), "
            "latest_release_date = (SELECT MAX(release_date) FROM books WHERE series_id = ?) WHERE id = ?",
            (series_id, series_id, series_id),
        )
    return status


def known_isbn_dates(conn, publisher_id):
    rows = conn.execute(
        "SELECT isbn13, source_key, release_date, price FROM books WHERE publisher_id = ?", (publisher_id,)
    ).fetchall()
    return {r["source_key"]: r for r in rows}
