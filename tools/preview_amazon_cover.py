"""確認用：指定した本だけ Amazon の書影を取り直す（データベースは保存しない）。"""
import sys

from newcomics import amazonlink, db
from newcomics.amazon import Api

conn = db.connect()
api = Api()
for key in sys.argv[1:]:
    r = conn.execute("SELECT id, isbn13, asin, amazon_isbn_ok FROM books WHERE isbn13 = ?", (key,)).fetchone()
    asin = r and amazonlink.paper_asin(r)
    items = api.get([asin], resources=["images.primary.large"]) if asin else []
    url = amazonlink.image_url(items[0]) if items else None
    conn.execute("UPDATE books SET amazon_image_url = ?, amazon_image_at = ? WHERE id = ?", (url, db.now_iso() if url else None, r["id"]))
    print(key, "書影あり" if url else "書影なし")
conn.commit()
