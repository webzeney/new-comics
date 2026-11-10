"""確認用：電子版のみの本だけ、楽天Kobo・Kindle版を探し、Kindle版の書影を取り直す（データベースは保存しない）。"""
import time
from datetime import datetime

from newcomics import amazonlink, db, kobo
from newcomics.amazon import Api

conn = db.connect()
print("電子版のみの本：", conn.execute("SELECT COUNT(*) FROM books WHERE ebook_only = 1").fetchone()[0], "冊")
kobo.main(["--ebook-only", "--max", "120"])
api = Api()
rows = [r for r in amazonlink.targets(conn, datetime.now(db.JST), "kindle", 400) if conn.execute("SELECT ebook_only FROM books WHERE id = ?", (r["id"],)).fetchone()[0]]
print("Kindle版：", amazonlink.run(conn, api, "kindle", rows, time.monotonic() + 8 * 60))
for r in conn.execute("SELECT id, kindle_asin FROM books WHERE ebook_only = 1 AND kindle_asin IS NOT NULL").fetchall():
    items = api.get([r["kindle_asin"]], resources=["images.primary.large"])
    url = amazonlink.image_url(items[0]) if items else None
    conn.execute("UPDATE books SET amazon_image_url = ?, amazon_image_at = ? WHERE id = ?", (url, db.now_iso() if url else None, r["id"]))
conn.commit()
print("Kobo あり", conn.execute("SELECT COUNT(*) FROM books WHERE ebook_only = 1 AND kobo_url IS NOT NULL").fetchone()[0],
      "／書影あり", conn.execute("SELECT COUNT(*) FROM books WHERE ebook_only = 1 AND image_url IS NOT NULL").fetchone()[0],
      "／紹介文あり", conn.execute("SELECT COUNT(*) FROM books WHERE ebook_only = 1 AND rakuten_caption IS NOT NULL").fetchone()[0],
      "／Kindle あり", conn.execute("SELECT COUNT(*) FROM books WHERE ebook_only = 1 AND kindle_asin IS NOT NULL").fetchone()[0])
for r in conn.execute("SELECT id, title, kobo_url IS NOT NULL k, kindle_asin FROM books WHERE ebook_only = 1 AND release_date >= '2026-11-01' ORDER BY release_date"):
    print(" ", r["id"], r["title"], "Kobo" if r["k"] else "-", r["kindle_asin"] or "-")
