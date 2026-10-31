"""楽天ブックス書籍検索API からコミックの新刊を取得する。

出版社をまたいで取れるので、1件ごとに出版社を決める（MULTI）。
API の決まり：1ページ30件・100ページまで。発売日の新しい順に並べ、対象期間より前の日付が
出たところで止める。100ページで足りないジャンルは、下位ジャンルに分けて取り直す。
"""
import os
import re
import time
from collections import Counter
from datetime import datetime

import requests

from .. import db
from .. import rakuten_select as sel
from ..http import USER_AGENT
from ..normalize import clean_title, isbn13, nfkc
from ..store import BookRecord

SLUG = "rakuten"
NAME = "楽天ブックス"
MULTI = True
SOURCE_URL = "https://books.rakuten.co.jp/"
FETCH_METHOD = "API"
ENDPOINT = "https://openapi.rakuten.co.jp/services/api/BooksBook/Search/20170404"
ROOT_GENRE = "001001"
HITS = 30
MAX_PAGE = 100
INTERVAL = 1.2
TIMEOUT = 30
ORIGIN = "https://new-comics.jp"
COMIC_SIZES = {9, "9", "コミック"}

DATE_FULL = re.compile(r"(\d{4})年(\d{1,2})月(\d{1,2})日")
DATE_MONTH = re.compile(r"(\d{4})年(\d{1,2})月")
DATE_YEAR = re.compile(r"(\d{4})年")


class RakutenError(Exception):
    pass


def parse_sales_date(text):
    """salesDate を (YYYY-MM-DD または None, 並べ替え用の YYYY-MM) にする。"""
    t = nfkc(text)
    m = DATE_FULL.search(t)
    if m and not re.search(r"以降|上旬|中旬|下旬", t):
        return f"{int(m.group(1)):04d}-{int(m.group(2)):02d}-{int(m.group(3)):02d}", f"{int(m.group(1)):04d}-{int(m.group(2)):02d}"
    m = DATE_MONTH.search(t)
    if m:
        return None, f"{int(m.group(1)):04d}-{int(m.group(2)):02d}"
    m = DATE_YEAR.search(t)
    if m:
        return None, f"{int(m.group(1)):04d}-12"
    return None, None


def label_name(series):
    """楽天の seriesName はレーベル名。末尾にレーベル内の通し番号が付くことがあるので外す。"""
    t = clean_title(nfkc(series))
    # 末尾の通し番号（「457」「CM1511」「CMPTH50」「F35」「シリーズ069」の数字など）を外す
    t = re.sub(r"\s+[A-Z]{0,6}\d+$", "", t)
    t = re.sub(r"(?<=シリーズ)\d+$", "", t)
    # 「ハーレクインコミックス ハーレクインコミックス」のように同じ名前が2回続くときは1つにする
    m = re.fullmatch(r"(.+?)\s+\1", t)
    if m:
        t = m.group(1)
    return clean_title(t) or None


def parse_authors(text):
    names = [clean_title(a) for a in re.split(r"[/／]", text or "")]
    return [{"name": n, "role": None} for n in names if n]


def to_record(item, affiliate):
    """載せると決めた項目を BookRecord にする。どの本を載せるかは rakuten_select で決める。"""
    isbn = isbn13(item.get("isbn"))
    if not isbn:
        return None
    title = clean_title(item.get("title"))
    sub = clean_title(item.get("subTitle"))
    if sub and sub not in title:
        title = f"{title} {sub}"
    release, _ = parse_sales_date(item.get("salesDate"))
    rec = BookRecord(
        source_key=f"{SLUG}:{isbn}",
        title_raw=title,
        release_date=release,
        isbn13=isbn,
        authors=parse_authors(item.get("author")),
        label=label_name(item.get("seriesName")),
        price=int(item["itemPrice"]) if item.get("itemPrice") else None,
        source_url=item.get("itemUrl"),
    )
    if release and "頃" in nfkc(item.get("salesDate")):
        rec.date_status = "予定"
    rec.rakuten_url = (item.get("affiliateUrl") if affiliate else None) or item.get("itemUrl")
    rec.image_url = re.sub(r"\?_ex=\d+x\d+$", "", item.get("largeImageUrl") or "") or None
    rec.publisher_name = item.get("publisherName")
    return rec


class Api:
    def __init__(self, app_id, access_key, affiliate_id=None):
        self.params = {"applicationId": app_id, "accessKey": access_key, "format": "json", "formatVersion": 2}
        if affiliate_id:
            self.params["affiliateId"] = affiliate_id
        self.affiliate = bool(affiliate_id)
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT, "Origin": ORIGIN, "Referer": ORIGIN + "/"})
        self._last = 0.0
        self.request_count = 0

    def search(self, **params):
        for attempt in range(4):
            wait = INTERVAL - (time.monotonic() - self._last)
            if wait > 0:
                time.sleep(wait)
            self._last = time.monotonic()
            res = self.session.get(ENDPOINT, params={**self.params, **params}, timeout=TIMEOUT)
            self.request_count += 1
            if res.status_code == 429 or res.status_code >= 500:
                time.sleep(5 * (attempt + 1))
                continue
            if res.status_code == 404:
                return {"Items": [], "count": 0, "pageCount": 0}
            if res.status_code != 200:
                raise RakutenError(f"HTTP {res.status_code}: {res.text[:200]}")
            return res.json()
        raise RakutenError("再試行しても応答がありません")


def collect(api, genre, start_month, end_month, log, depth=0, report=None):
    """genre を発売日の新しい順にたどり、start_month〜end_month の項目を返す。

    report に dict を渡すと、たどりきれなかったジャンルを report["gaps"] に入れる。
    """
    if report is None:
        report = {}
    report.setdefault("gaps", [])
    report.setdefault("totals", {})
    items = []
    for page in range(1, MAX_PAGE + 1):
        data = api.search(booksGenreId=genre, sort="-releaseDate", hits=HITS, page=page, outOfStockFlag=1)
        if page == 1 and isinstance(data.get("count"), int):
            report["totals"][genre] = data["count"]
        rows = data.get("Items") or data.get("items") or []
        if not rows:
            return items
        reached = False
        for row in rows:
            row = row.get("Item", row) if isinstance(row, dict) else row
            _, month = parse_sales_date(row.get("salesDate"))
            if month is None or month > end_month:
                continue
            if month < start_month:
                reached = True
                continue
            items.append(row)
        page_count = data.get("pageCount") or 0
        if reached or (page >= page_count and page_count < MAX_PAGE):
            return items
    if depth >= 2:
        log(f"{NAME}: ジャンル {genre} は100ページで対象期間をたどりきれませんでした")
        report["gaps"].append(f"ジャンル {genre} は100ページの上限で対象期間をたどりきれませんでした")
        return items
    info = api.search(booksGenreId=genre, hits=1, genreInformationFlag=1)
    children = [c.get("booksGenreId") or c.get("child", {}).get("booksGenreId") for c in (info.get("GenreInformation") or [{}])[0].get("children", [])]
    children = [c for c in children if c]
    if not children:
        log(f"{NAME}: ジャンル {genre} は100ページで足りず、下位ジャンルもありません")
        report["gaps"].append(f"ジャンル {genre} は100ページの上限で対象期間をたどりきれず、下位ジャンルもありません")
        return items
    log(f"{NAME}: ジャンル {genre} を下位ジャンル {len(children)} 件に分けて取得します")
    items = []
    for child in children:
        items.extend(collect(api, child, start_month, end_month, log, depth + 1, report))
    totals = report["totals"]
    if genre in totals and all(c in totals for c in children):
        rest = totals[genre] - sum(totals[c] for c in children)
        if rest > 0:
            log(f"{NAME}: ジャンル {genre} には下位ジャンルに入っていない本が {rest} 件あります")
            report["gaps"].append(f"ジャンル {genre} には下位ジャンルに入っていない本が {rest} 件あり、分けて取得したときにたどれていません")
    return items


def write_summary(start_month, end_month, count, request_count, gaps, stats=None):
    """Actions の実行結果のまとめに、楽天の取得がたどりきれたかと、本の選び分けの件数を書く。書名は書かない。"""
    for gap in gaps:
        print(f"::warning title={NAME}::{gap}")
    stats = stats or {}
    if stats.get("invalid"):
        print(f"::warning title={NAME}::{sel.REVIEW_FILE} の判定の欄に「{sel.YES}」「{sel.NO}」以外が書かれた行が {stats['invalid']} 行あります（判定なしとして扱いました）")
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not path:
        return
    lines = [f"### {NAME}", "", f"- 対象期間：{start_month}〜{end_month}", f"- 取得件数：{count} 件（API {request_count} 回）"]
    if gaps:
        lines.append("- **たどりきれなかった部分があります（取りこぼしのおそれ）**")
        lines += [f"  - {g}" for g in gaps]
    else:
        lines.append("- 100ページの上限に当たらず、対象期間をすべてたどりました")
    if stats:
        lines += [
            f"- 判型がコミック以外の本（一覧は非公開リポジトリの {sel.REVIEW_FILE}）",
            f"  - 確認待ち（判定なし）：{stats.get('pending', 0)} 件（うち今回新しく加わった本 {stats.get('pending_new', 0)} 件）",
            f"  - 自動で採用：{stats.get('auto', 0)} 件（うち今回新しく加わった本 {stats.get('auto_new', 0)} 件）",
            f"  - 自動で除外：{stats.get('excluded', 0)} 件",
            f"  - 「{sel.YES}」の印で載せた本：{stats.get('yes', 0)} 件",
            f"  - 「{sel.NO}」の印で外した本：{stats.get('no', 0)} 件（データベースから消した本 {stats.get('deleted', 0)} 件）",
        ]
        if stats.get("invalid"):
            lines.append(f"  - **判定の欄の書き方が正しくない行：{stats['invalid']} 行（判定なしとして扱いました）**")
    with open(path, "a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n\n")


def sales_key(item):
    full, month = parse_sales_date(item.get("salesDate"))
    return full or month or nfkc(item.get("salesDate"))


def select(conn, rows, start_month, today):
    """載せる項目を選ぶ。判型がコミック以外の本は一覧に残し、一覧の判定を決まりより優先する。"""
    path = sel.review_path(conn)
    review, invalid = sel.load(path)
    chosen, seen, stats = [], set(), Counter(invalid=len(invalid))
    for item in rows:
        kind, reason = sel.classify(item)
        isbn = isbn13(item.get("isbn"))
        if isbn and isbn in seen:
            continue
        if isbn:
            seen.add(isbn)
        if item.get("size") in COMIC_SIZES or not sel.has_isbn(isbn):
            if kind == sel.ADOPT:
                chosen.append(item)
            continue
        entry = review.get(isbn)
        new = entry is None
        if new:
            entry = {c: "" for c in sel.COLUMNS}
            entry["ISBN"], entry["初めて見た日"] = isbn, today
            review[isbn] = entry
        entry.update({
            "区分": kind, "理由": reason, "発売日": sales_key(item), "出版社": nfkc(item.get("publisherName")),
            "シリーズ": nfkc(item.get("seriesName")), "判型": nfkc(item.get("size")),
            "書名": clean_title(nfkc(f"{item.get('title') or ''} {item.get('subTitle') or ''}")), "楽天のページ": item.get("itemUrl") or "",
        })
        mark = sel.mark(entry)
        if mark == sel.YES:
            stats["yes"] += 1
            chosen.append(item)
        elif mark == sel.NO:
            stats["no"] += 1
        elif kind == sel.ADOPT:
            stats["auto"] += 1
            stats["auto_new"] += new
            chosen.append(item)
        elif kind == sel.REVIEW:
            stats["pending"] += 1
            stats["pending_new"] += new
        else:
            stats["excluded"] += 1
    refused = [i for i, r in review.items() if sel.mark(r) == sel.NO]
    for i in refused:
        for row in conn.execute("SELECT id, series_id FROM books WHERE isbn13 = ? AND origin = 'rakuten'", (i,)).fetchall():
            db.delete_book(conn, row["id"])
            stats["deleted"] += 1
            if row["series_id"]:
                conn.execute(
                    "UPDATE series SET latest_volume = (SELECT MAX(volume) FROM books WHERE series_id = ?), "
                    "latest_release_date = (SELECT MAX(release_date) FROM books WHERE series_id = ?) WHERE id = ?",
                    (row["series_id"], row["series_id"], row["series_id"]),
                )
    sel.save(path, review, start_month)
    return chosen, stats


def fetch(client, conn, publisher_id, months, log, known=None):
    app_id = os.environ.get("RAKUTEN_APP_ID")
    access_key = os.environ.get("RAKUTEN_ACCESS_KEY")
    if not app_id or not access_key:
        raise RakutenError("RAKUTEN_APP_ID と RAKUTEN_ACCESS_KEY が設定されていません")
    api = Api(app_id, access_key, os.environ.get("RAKUTEN_AFFILIATE_ID"))
    start_month = f"{months[0][0]:04d}-{months[0][1]:02d}"
    end_month = f"{months[-1][0]:04d}-{months[-1][1]:02d}"
    report = {}
    rows = collect(api, ROOT_GENRE, start_month, end_month, log, report=report)
    rows, stats = select(conn, rows, start_month, datetime.now(db.JST).date().isoformat())
    out, seen = [], set()
    for row in rows:
        rec = to_record(row, api.affiliate)
        if rec is None or rec.isbn13 in seen:
            continue
        seen.add(rec.isbn13)
        out.append(rec)
    client.request_count += api.request_count
    log(f"{NAME}: {start_month}〜{end_month} の {len(out)} 件（API {api.request_count} 回）")
    log(f"{NAME}: 判型がコミック以外の本 自動で採用 {stats['auto']} / 確認待ち {stats['pending']} / 自動で除外 {stats['excluded']} / "
        f"「{sel.YES}」{stats['yes']} / 「{sel.NO}」{stats['no']}（消した本 {stats['deleted']}）")
    write_summary(start_month, end_month, len(out), api.request_count, report["gaps"], stats)
    return out
