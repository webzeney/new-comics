"""アナリティクス（GA4）の操作の記録から、先月のレポートを作る（2026-11-16 運営者の判断）。

毎月1日に GitHub Actions から動かし、非公開リポジトリ（new-comics-data）の Issue にする。
認証情報は Secrets の GA4_SA_KEY（サービスアカウントの鍵 JSON）と、Variables の GA4_PROPERTY_ID から読む。

  python tools/ga_report.py              先月のレポートを作って Issue にする
  python tools/ga_report.py --month 2026-11 --print   指定の月のレポートを表示だけする
  python tools/ga_report.py --setup      レポートに使う項目（カスタムディメンション）を GA4 に登録する（最初に1回）
"""
import argparse
import json
import os
import sys
from datetime import date, timedelta

import requests
from google.oauth2 import service_account

# サイトの JS（static/js/main.js の track）が送る項目
DIMENSIONS = [
    ("store", "書店"),
    ("buy_type", "予約か購入か"),
    ("page_type", "ページの種類"),
    ("fav_action", "お気に入りの操作"),
    ("service", "カレンダーの種類"),
    ("feed", "RSS の種類"),
]
STORE = {"amazon": "Amazon", "rakuten": "楽天ブックス", "seven": "セブンネット", "kindle": "Kindle", "kobo": "楽天Kobo"}
BUY = {"reserve": "予約", "purchase": "購入"}
PAGE = {"top": "トップ", "book": "書籍", "date": "日ごと", "today": "今日発売", "week": "今週発売", "calendar": "カレンダー", "publisher": "出版社",
        "label": "レーベル", "genre": "ジャンル", "tag": "タグ", "author": "著者", "series": "作品", "search": "検索", "favorites": "お気に入り",
        "publisher_month": "出版社の月別", "label_month": "レーベルの月別", "genre_month": "ジャンルの月別", "updates": "発売日の変更・決定", "feature": "特集"}
FAV = {"add": "追加", "remove": "削除", "import": "引き継ぎで追加"}
SERVICE = {"apple": "iPhone・Mac", "google": "Googleカレンダー", "google_one_book": "この巻だけ（Google）", "ics_one_book": "この巻だけ（iPhone・その他）"}
SCOPES = ["https://www.googleapis.com/auth/analytics.readonly", "https://www.googleapis.com/auth/analytics.edit"]


def credentials():
    info = json.loads(os.environ["GA4_SA_KEY"])
    return service_account.Credentials.from_service_account_info(info, scopes=SCOPES)


def setup(prop):
    """カスタムディメンションを登録する（すでにあるものは飛ばす）。"""
    from google.analytics.admin_v1beta import AnalyticsAdminServiceClient
    from google.analytics.admin_v1beta.types import CustomDimension
    client = AnalyticsAdminServiceClient(credentials=credentials())
    parent = f"properties/{prop}"
    have = {d.parameter_name for d in client.list_custom_dimensions(parent=parent)}
    for name, label in DIMENSIONS:
        if name in have:
            print("登録済み：", name)
            continue
        client.create_custom_dimension(parent=parent, custom_dimension=CustomDimension(
            parameter_name=name, display_name=label, scope=CustomDimension.DimensionScope.EVENT))
        print("登録しました：", name)


def run(client, prop, start, end, dims, metric="eventCount", event=None, limit=50):
    from google.analytics.data_v1beta.types import (DateRange, Dimension, Filter, FilterExpression, Metric, OrderBy, RunReportRequest)
    req = RunReportRequest(
        property=f"properties/{prop}", date_ranges=[DateRange(start_date=start, end_date=end)],
        dimensions=[Dimension(name=d) for d in dims], metrics=[Metric(name=metric)], limit=limit,
        order_bys=[OrderBy(metric=OrderBy.MetricOrderBy(metric_name=metric), desc=True)],
    )
    if event:
        req.dimension_filter = FilterExpression(filter=Filter(field_name="eventName", string_filter=Filter.StringFilter(value=event)))
    res = client.run_report(req)
    return [([v.value for v in r.dimension_values], int(float(r.metric_values[0].value))) for r in res.rows]


def table(head, rows):
    out = ["| " + " | ".join(head) + " |", "|" + "---|" * len(head)]
    out += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(out) if rows else "（記録なし）"


def report(prop, month):
    from google.analytics.data_v1beta import BetaAnalyticsDataClient
    client = BetaAnalyticsDataClient(credentials=credentials())
    y, m = map(int, month.split("-"))
    start = date(y, m, 1)
    end = (date(y + (m == 12), m % 12 + 1, 1) - timedelta(days=1))
    s, e = start.isoformat(), end.isoformat()
    total = run(client, prop, s, e, [], "screenPageViews")
    users = run(client, prop, s, e, [], "activeUsers")
    events = dict((d[0], n) for d, n in run(client, prop, s, e, ["eventName"]))
    stores = run(client, prop, s, e, ["customEvent:store", "customEvent:buy_type"], event="store_click")
    pages = run(client, prop, s, e, ["customEvent:page_type"], event="store_click", limit=20)
    favs = run(client, prop, s, e, ["customEvent:fav_action"], event="favorite")
    cals = run(client, prop, s, e, ["customEvent:service"], event="calendar_subscribe")
    feeds = run(client, prop, s, e, ["customEvent:feed"], event="rss_subscribe", limit=20)
    name = lambda table_, v: table_.get(v, v or "（不明）")
    lines = [
        f"# {y}年{m}月のレポート（{s}〜{e}）", "",
        "## 全体",
        table(["項目", "数"], [
            ["ページが見られた回数", total[0][1] if total else 0],
            ["見た人の数（アクティブユーザー）", users[0][1] if users else 0],
            ["書店のボタンが押された回数", events.get("store_click", 0)],
            ["お気に入りの操作", events.get("favorite", 0)],
            ["カレンダー登録", events.get("calendar_subscribe", 0)],
            ["RSS の登録", events.get("rss_subscribe", 0)],
            ["まとめてカートに入れる", events.get("cart_add", 0)],
        ]), "",
        "## 書店のボタン（書店・予約か購入か）",
        table(["書店", "予約か購入か", "回数"], [[name(STORE, d[0]), name(BUY, d[1]), n] for d, n in stores]), "",
        "## 書店のボタンが押されたページ",
        table(["ページの種類", "回数"], [[name(PAGE, d[0]), n] for d, n in pages]), "",
        "## お気に入り",
        table(["操作", "回数"], [[name(FAV, d[0]), n] for d, n in favs]), "",
        "## カレンダー登録",
        table(["種類", "回数"], [[name(SERVICE, d[0]), n] for d, n in cals]), "",
        "## RSS の登録（多い順に20件）",
        table(["RSS", "回数"], [[d[0] or "（不明）", n] for d, n in feeds]), "",
        "※ ブラウザの広告ブロックなどで記録されない操作があるため、実際の数より少なめに出ます。",
    ]
    return f"{y}年{m}月のアクセスと操作のレポート", "\n".join(lines)


def post_issue(title, body):
    repo, token = os.environ["DATA_REPO"], os.environ["DATA_REPO_TOKEN"]
    r = requests.post(f"https://api.github.com/repos/{repo}/issues", json={"title": title, "body": body},
                      headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"}, timeout=30)
    if r.status_code not in (200, 201):
        raise SystemExit(f"Issue を作れませんでした（HTTP {r.status_code}）")
    print("Issue を作りました：#", r.json().get("number"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--month", help="YYYY-MM（省略すると先月）")
    ap.add_argument("--print", action="store_true", help="Issue にせず表示だけする")
    ap.add_argument("--setup", action="store_true", help="カスタムディメンションを登録する")
    args = ap.parse_args()
    prop = os.environ.get("GA4_PROPERTY_ID")
    if not prop or not os.environ.get("GA4_SA_KEY"):
        raise SystemExit("GA4_PROPERTY_ID と GA4_SA_KEY が登録されていません")
    if args.setup:
        setup(prop)
        return
    if args.month:
        month = args.month
    else:
        first = date.today().replace(day=1) - timedelta(days=1)
        month = f"{first.year}-{first.month:02d}"
    title, body = report(prop, month)
    if args.print:
        print(body)
    else:
        post_issue(title, body)


if __name__ == "__main__":
    sys.exit(main())
