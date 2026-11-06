import json
import re
import unicodedata
from collections import Counter
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
    rakuten_url: str = None
    image_url: str = None
    publisher_name: str = None
    title_kana: str = None

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


RAKUTEN_PREFIX = "rakuten:"


def origin_of(source_key):
    """データの出どころ。楽天ウェブサービスで取った本は "rakuten"、出版社サイトで取った本は "publisher"。"""
    return "rakuten" if source_key.startswith(RAKUTEN_PREFIX) else "publisher"


def link_rakuten(conn, existing, rec, run_at):
    """出版社サイトの本には、楽天の情報を混ぜず、楽天の商品ページへのリンクと書影だけを付ける。

    書影は楽天の商品ページへのリンクとして表示する（楽天ウェブサービス規約 第8条4項）。
    読み仮名は画面に出さず、検索のためだけに使う（CLAUDE.md の例外）。
    """
    image = rec.image_url or existing["image_url"]
    kana = rec.title_kana or existing["title_kana"]
    changed = existing["rakuten_url"] != rec.rakuten_url or existing["image_url"] != image
    conn.execute(
        f"UPDATE books SET rakuten_url = ?, image_url = ?, title_kana = ?, last_seen_at = ?{', updated_at = ?' if changed else ''} WHERE id = ?",
        [rec.rakuten_url, image, kana, run_at] + ([run_at] if changed else []) + [existing["id"]],
    )
    return "updated" if changed else "same"


def find_publisher_copy(conn, publisher_id, series_id, rec, exclude_id=None):
    """楽天の本と同じ本を、出版社サイトから取った本の中から探す。"""
    if rec.isbn13:
        row = conn.execute("SELECT * FROM books WHERE isbn13 = ? AND origin = 'publisher'", (rec.isbn13,)).fetchone()
        if row is not None:
            return row
    return db.find_same_volume(conn, publisher_id, series_id, rec.volume, rec.edition, rec.isbn13, origin="publisher", exclude_id=exclude_id)


def save(conn, publisher_id, rec, run_at):
    rec.finalize()
    label_id = db.ensure_label(conn, publisher_id, rec.label)
    series_id = db.ensure_series(conn, publisher_id, series_name(rec.title_raw), normalized_series(rec.title_raw))
    origin = origin_of(rec.source_key)
    if origin == "rakuten":
        own = conn.execute("SELECT * FROM books WHERE source_key = ?", (rec.source_key,)).fetchone()
        copy = find_publisher_copy(conn, publisher_id, series_id, rec, exclude_id=own["id"] if own else None)
        if copy is not None:
            if own is not None:
                db.delete_book(conn, own["id"])
            return link_rakuten(conn, copy, rec, run_at)
        existing = own
    else:
        existing = conn.execute("SELECT * FROM books WHERE source_key = ?", (rec.source_key,)).fetchone()
        if existing is None and rec.isbn13:
            existing = conn.execute("SELECT * FROM books WHERE isbn13 = ?", (rec.isbn13,)).fetchone()
        if existing is None:
            existing = db.find_same_volume(conn, publisher_id, series_id, rec.volume, rec.edition, rec.isbn13)
        if rec.isbn13:
            other = conn.execute(
                "SELECT * FROM books WHERE isbn13 = ? AND id != ?", (rec.isbn13, existing["id"] if existing else -1)
            ).fetchone()
            if other is not None:
                if other["origin"] == "rakuten":
                    if rec.rakuten_url is None:
                        rec.rakuten_url = other["rakuten_url"]
                    if rec.image_url is None:
                        rec.image_url = other["image_url"]
                    if rec.title_kana is None:
                        rec.title_kana = other["title_kana"]
                    db.delete_book(conn, other["id"])
                else:
                    rec.isbn13 = None
        if existing is not None and existing["origin"] == "publisher":
            dup = db.find_same_volume(conn, publisher_id, series_id, rec.volume, rec.edition, rec.isbn13 or existing["isbn13"], origin="rakuten", exclude_id=existing["id"])
            if dup is not None:
                if rec.rakuten_url is None and existing["rakuten_url"] is None:
                    rec.rakuten_url = dup["rakuten_url"]
                if rec.image_url is None and existing["image_url"] is None:
                    rec.image_url = dup["image_url"]
                if rec.title_kana is None and existing["title_kana"] is None:
                    rec.title_kana = dup["title_kana"]
                db.delete_book(conn, dup["id"])
    takeover = existing is not None and origin == "publisher" and existing["origin"] == "rakuten"
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
        "rakuten_url": rec.rakuten_url,
        "image_url": rec.image_url,
        "title_kana": rec.title_kana,
        "origin": origin,
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
        keep = ("rakuten_url", "image_url", "title_kana") if takeover else ("isbn13", "price", "has_ebook", "label_id", "volume", "rakuten_url", "image_url", "title_kana")
        for key in keep:
            if values[key] is None:
                values[key] = existing[key]
        if values["authors"] == "[]" and not takeover:
            values["authors"] = existing["authors"]
        changed = [k for k in values if k != "title_kana" and values[k] != existing[k]]
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
        "SELECT isbn13, source_key, release_date, price, title_raw, authors FROM books WHERE publisher_id = ?", (publisher_id,)
    ).fetchall()
    return {r["source_key"]: r for r in rows}


AFFILIATE_LINK = re.compile(r"^(https://hb\.afl\.rakuten\.co\.jp/(?:hgc|ichiba)/)([^/?#]+)(/.*)$")


def refresh_affiliate_links(conn, records):
    """楽天アフィリエイトのリンクのIDを、今回の取得で楽天が返したIDにそろえる。

    今回の取得の範囲に入らなかった本（発売済みの本など）は、前のIDのリンクのまま残るため。
    今回のリンクのほとんど（9割以上）が同じIDのときだけ書き換える。書き換えた件数を返す。
    """
    ids = Counter(m.group(2) for r in records if (m := AFFILIATE_LINK.match(r.rakuten_url or "")))
    if not ids:
        return 0
    current, count = ids.most_common(1)[0]
    if count < sum(ids.values()) * 0.9:
        return 0
    changed = 0
    for row in conn.execute("SELECT id, rakuten_url FROM books WHERE rakuten_url LIKE 'https://hb.afl.rakuten.co.jp/%'").fetchall():
        m = AFFILIATE_LINK.match(row["rakuten_url"])
        if m and m.group(2) != current:
            conn.execute("UPDATE books SET rakuten_url = ? WHERE id = ?", (m.group(1) + current + m.group(3), row["id"]))
            changed += 1
    return changed


def title_key(text):
    """書名を比べるための形（全角半角・大文字小文字・空白の違いをなくす）。"""
    return re.sub(r"\s+", "", unicodedata.normalize("NFKC", text or "")).lower()


def isbnless_title_duplicates(conn, publisher_id=None):
    """出版社サイトの本で、ISBN のない本と、同じ出版社・同じ発売日・同じ書名で ISBN のある本の組を返す。

    出版社のカレンダーのページ（ISBN なし）と書籍の詳細ページ（ISBN あり）から同じ本を取り込み、
    巻数が読み取れなかったなどの理由で、シリーズ・巻・版での照らし合わせ（merge_isbnless_duplicates）から漏れたものを拾う。
    同じ書名の ISBN のある本が1冊だけのときに限る。
    """
    where = "AND publisher_id = ?" if publisher_id is not None else ""
    args = (publisher_id,) if publisher_id is not None else ()
    rows = conn.execute(
        f"SELECT * FROM books WHERE origin = 'publisher' AND release_date IS NOT NULL {where}", args
    ).fetchall()
    with_isbn = {}
    for r in rows:
        if r["isbn13"]:
            with_isbn.setdefault((r["publisher_id"], r["release_date"], title_key(r["title"])), []).append(r)
    pairs = []
    for r in rows:
        if r["isbn13"]:
            continue
        cands = with_isbn.get((r["publisher_id"], r["release_date"], title_key(r["title"])), [])
        if len(cands) == 1:
            pairs.append((cands[0], r))
    return pairs


def merge_isbnless_by_title(conn, publisher_id=None):
    """isbnless_title_duplicates の組をまとめる（著者・完結・タグを ISBN のある本に移し、ISBN のない本は消す）。まとめた件数を返す。"""
    merged = 0
    for main, r in isbnless_title_duplicates(conn, publisher_id):
        authors = main["authors"]
        if not json.loads(authors or "[]") and json.loads(r["authors"] or "[]"):
            authors = r["authors"]
        is_final = int(bool(main["is_final"]) or bool(r["is_final"]))
        conn.execute("UPDATE books SET authors = ?, is_final = ? WHERE id = ?", (authors, is_final, main["id"]))
        conn.execute("INSERT OR IGNORE INTO book_tags (book_id, tag_id) SELECT ?, tag_id FROM book_tags WHERE book_id = ?", (main["id"], r["id"]))
        db.delete_book(conn, r["id"])
        merged += 1
    return merged


def merge_isbnless_duplicates(conn, publisher_id):
    """出版社サイトの本で、ISBN のある本と、同じ本（同じシリーズ・巻・版）で ISBN のない本が両方あるとき、1冊にまとめる。

    ISBN のない本にしかない著者・完結の情報は ISBN のある本に移し、ISBN のない本は消す。まとめた件数を返す。
    """
    groups = conn.execute(
        "SELECT series_id, volume, edition FROM books WHERE publisher_id = ? AND origin = 'publisher' AND series_id IS NOT NULL AND volume IS NOT NULL "
        "GROUP BY series_id, volume, edition HAVING COUNT(*) > 1",
        (publisher_id,),
    ).fetchall()
    merged = 0
    for g in groups:
        rows = conn.execute(
            "SELECT * FROM books WHERE publisher_id = ? AND origin = 'publisher' AND series_id = ? AND volume = ? AND edition = ?",
            (publisher_id, g["series_id"], g["volume"], g["edition"]),
        ).fetchall()
        keep = [r for r in rows if r["isbn13"]]
        drop = [r for r in rows if not r["isbn13"]]
        if len(keep) != 1 or not drop:
            continue
        main = keep[0]
        authors = main["authors"]
        if not json.loads(authors or "[]"):
            authors = next((r["authors"] for r in drop if json.loads(r["authors"] or "[]")), authors)
        is_final = int(bool(main["is_final"]) or any(r["is_final"] for r in drop))
        conn.execute("UPDATE books SET authors = ?, is_final = ? WHERE id = ?", (authors, is_final, main["id"]))
        for r in drop:
            conn.execute("INSERT OR IGNORE INTO book_tags (book_id, tag_id) SELECT ?, tag_id FROM book_tags WHERE book_id = ?", (main["id"], r["id"]))
            db.delete_book(conn, r["id"])
            merged += 1
    return merged
