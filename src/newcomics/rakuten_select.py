"""楽天のコミックのジャンルの本から、載せる本を選ぶ。

判型が「コミック」の本はそのまま載せる。判型がそれ以外の本（単行本・文庫・ムックなど）は
決まりに沿って「自動で採用」「確認待ち」「自動で除外」に分ける。
判型が「コミック」以外の本は、非公開リポジトリのデータと同じ場所の rakuten-review.tsv に一覧で残す。
一覧の「判定」の欄に「載せる」「載せない」と書くと、次の取得からその判定が決まりより優先される。
"""
import csv
import os
import re
import unicodedata
from pathlib import Path

ADOPT, REVIEW, EXCLUDE = "自動で採用", "確認待ち", "自動で除外"
YES, NO = "載せる", "載せない"
REVIEW_FILE = "rakuten-review.tsv"
COLUMNS = ["判定", "区分", "理由", "ISBN", "発売日", "出版社", "シリーズ", "判型", "書名", "楽天のページ", "初めて見た日"]

COMIC_SIZES = {9, "9", "コミック"}
YEAR = r"(?:19|20)\d\d"
EXCLUDE_TITLE = re.compile(
    r"画集|画業|図録|art ?works|art ?book|art collection|the art of|イラスト集|イラストブック|イラストコミック|"
    r"設定資料集|フォトエッセイ|ポストカードブック|ポスター|大事典|"
    rf"{YEAR}.*(?:カレンダー|手帳|ダイアリー|めくり)|(?:カレンダー|手帳|ダイアリー|めくり).*{YEAR}",
    re.I,
)
SPECIAL = re.compile(r"特装版|限定版|同梱版|特別版")
EXCLUDE_SERIES = re.compile(r"画集|イラストブック|設定資料")
NOVEL = re.compile(r"小説|ノベライズ|ノベル版")
REPRINT_SERIES = re.compile(r"my ?first ?big|リミックス|remix", re.I)
COMIC_SERIES = re.compile(r"コミック|comic|ハヤコミ", re.I)
EXCLUDE_SIZES = {"図鑑", "絵本", "全集・双書"}
ADOPT_PUBLISHERS = {"文藝春秋", "三栄", "マガジンハウス"}
COMIC_TITLE = re.compile(r"コミックエッセイ|アニメコミック|映画コミック")


def nfkc(text):
    return unicodedata.normalize("NFKC", str(text or "")).strip()


def has_isbn(value):
    digits = re.sub(r"\D", "", nfkc(value))
    return len(digits) == 13 and digits.startswith(("978", "979"))


def classify(item):
    """楽天の項目を (区分, 理由) に分ける。判型が「コミック」の本は (ADOPT, "判型がコミック")。"""
    if not has_isbn(item.get("isbn")):
        return EXCLUDE, "ISBNがない（楽天限定特典付きの出品など）"
    size = item.get("size")
    if size in COMIC_SIZES:
        return ADOPT, "判型がコミック"
    size = nfkc(size)
    title = nfkc(f"{item.get('title') or ''} {item.get('subTitle') or ''}")
    series = nfkc(item.get("seriesName"))
    publisher = nfkc(item.get("publisherName"))
    if EXCLUDE_TITLE.search(title) and not SPECIAL.search(title):
        return EXCLUDE, "書名が画集・カレンダーなど"
    if EXCLUDE_SERIES.search(series):
        return EXCLUDE, "シリーズ名が画集・イラストブックなど"
    if NOVEL.search(title):
        return REVIEW, "書名に小説・ノベライズ"
    if size == "ムックその他":
        if REPRINT_SERIES.search(series):
            return ADOPT, "コンビニ向けの再録本のシリーズ"
        return REVIEW, "判型がムック"
    if COMIC_SERIES.search(series):
        return ADOPT, "シリーズ名にコミック"
    if size in EXCLUDE_SIZES:
        return EXCLUDE, f"判型が{size}"
    if size == "文庫":
        return ADOPT, "判型が文庫"
    if publisher in ADOPT_PUBLISHERS:
        return ADOPT, "自動で採用する出版社"
    if COMIC_TITLE.search(title):
        return ADOPT, "書名にコミックエッセイなど"
    return REVIEW, "決まりに当たらない"


def review_path(conn):
    """データベースと同じ場所の一覧ファイル。メモリ上のデータベースのときは None。"""
    for row in conn.execute("PRAGMA database_list"):
        if row[1] == "main" and row[2]:
            return Path(row[2]).parent / REVIEW_FILE
    return None


def load(path):
    """一覧を読む。{ISBN: 行} と、判定の欄の書き方が正しくない行の ISBN を返す。"""
    rows, invalid = {}, []
    if path is None or not path.exists():
        return rows, invalid
    with open(path, encoding="utf-8-sig", newline="") as f:
        reader = csv.reader(f, delimiter="\t")
        header = next(reader, None)
        if header is None:
            return rows, invalid
        index = {name: i for i, name in enumerate(nfkc(h) for h in header)}
        for values in reader:
            if not any(v.strip() for v in values):
                continue
            row = {name: (values[index[name]] if name in index and index[name] < len(values) else "") for name in COLUMNS}
            isbn = re.sub(r"\D", "", nfkc(row["ISBN"]))
            if not isbn:
                continue
            row["ISBN"] = isbn
            row["判定"] = nfkc(row["判定"])
            if row["判定"] not in ("", YES, NO):
                invalid.append(isbn)
            rows[isbn] = row
    return rows, invalid


def mark(row):
    """判定の欄。「載せる」「載せない」以外の書き方は、判定なしとして扱う（書いた文字は一覧に残す）。"""
    return row["判定"] if row["判定"] in (YES, NO) else ""


def save(path, rows, start_month):
    """一覧を書く。判定のない行のうち、対象期間より前に発売された本は外す。"""
    if path is None:
        return
    keep = [r for r in rows.values() if r["判定"] or not r["発売日"] or r["発売日"][:7] >= start_month]
    order = {REVIEW: 0, ADOPT: 1, EXCLUDE: 2}
    keep.sort(key=lambda r: (order.get(r["区分"], 3), r["発売日"], r["出版社"], r["書名"]))
    tmp = path.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f, delimiter="\t", lineterminator="\n")
        w.writerow(COLUMNS)
        for r in keep:
            w.writerow([r.get(c, "") for c in COLUMNS])
    os.replace(tmp, path)
