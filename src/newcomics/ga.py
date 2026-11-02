"""Google アナリティクス（GA4）から、書籍ページがよく見られている本を読み込む。

サービスアカウントの鍵（環境変数 GA_SERVICE_ACCOUNT_JSON）とプロパティID（GA_PROPERTY_ID）を使い、
直近 DAYS 日の /book/ で始まるページの表示回数を Data API で取り出す。鍵の中身はログに出さない。
"""
import json
import os
import re
import sys

import requests
from google.auth.transport.requests import Request
from google.oauth2 import service_account

SCOPE = "https://www.googleapis.com/auth/analytics.readonly"
DAYS = 30
LIMIT = 1000
BOOK_PATH = re.compile(r"^/book/([0-9A-Za-z]+)/")


def credentials():
    raw = os.environ.get("GA_SERVICE_ACCOUNT_JSON")
    prop = os.environ.get("GA_PROPERTY_ID")
    if not raw or not prop:
        return None, None
    creds = service_account.Credentials.from_service_account_info(json.loads(raw), scopes=[SCOPE])
    creds.refresh(Request())
    return creds, prop


def book_views(creds, prop, days=DAYS, limit=LIMIT):
    """{書籍のキー（ISBN など）: 表示回数} を返す。"""
    body = {
        "dateRanges": [{"startDate": f"{days}daysAgo", "endDate": "yesterday"}],
        "dimensions": [{"name": "pagePath"}],
        "metrics": [{"name": "screenPageViews"}],
        "dimensionFilter": {"filter": {"fieldName": "pagePath", "stringFilter": {"matchType": "BEGINS_WITH", "value": "/book/"}}},
        "orderBys": [{"metric": {"metricName": "screenPageViews"}, "desc": True}],
        "limit": limit,
    }
    res = requests.post(f"https://analyticsdata.googleapis.com/v1beta/properties/{prop}:runReport",
                        headers={"Authorization": f"Bearer {creds.token}"}, json=body, timeout=60)
    res.raise_for_status()
    views = {}
    for row in res.json().get("rows", []):
        m = BOOK_PATH.match(row["dimensionValues"][0]["value"])
        if m:
            views[m.group(1)] = views.get(m.group(1), 0) + int(row["metricValues"][0]["value"])
    return views


def save(conn, views, now):
    """ランキング用に、書籍ページの表示回数を入れ替える。"""
    conn.execute("DELETE FROM page_views")
    conn.executemany("INSERT INTO page_views (book_key, views, updated_at) VALUES (?, ?, ?)", [(k, n, now) for k, n in views.items()])
    conn.commit()


def main():
    from . import db
    creds, prop = credentials()
    if creds is None:
        print("アナリティクス：GA_SERVICE_ACCOUNT_JSON / GA_PROPERTY_ID が未設定のため省略します")
        return 0
    views = book_views(creds, prop)
    save(db.connect(), views, db.now_iso())
    print(f"アナリティクス：直近{DAYS}日に見られた書籍ページ {len(views)} 件、表示回数の合計 {sum(views.values())}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
