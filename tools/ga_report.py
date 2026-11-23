"""アナリティクス（GA4）の操作の記録から、先月のレポートを作る（2026-11-16 運営者の判断）。

毎月1日に GitHub Actions から動かし、非公開リポジトリ（new-comics-data）の reports/YYYY-MM.md に保存する
（前は Issue にしていたが、保存に使う鍵に Issue を作る権限がないため、ファイルにした。2026-11-22）。
認証情報は、毎晩の読み込み（newcomics.ga）と同じ Secrets の GA_SERVICE_ACCOUNT_JSON（サービスアカウントの鍵 JSON）と、
Variables の GA_PROPERTY_ID から読む（前の名前 GA4_SA_KEY・GA4_PROPERTY_ID も読める）。

  python tools/ga_report.py --out-dir data/reports   先月のレポートを作ってファイルに保存する
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
    ("place", "ボタンの場所"),
]
STORE = {"amazon": "Amazon", "rakuten": "楽天ブックス", "seven": "セブンネット", "kindle": "Kindle", "kobo": "楽天Kobo"}
BUY = {"reserve": "予約", "purchase": "購入"}
PAGE = {"top": "トップ", "book": "書籍", "date": "日ごと", "today": "今日発売", "week": "今週発売", "calendar": "カレンダー", "publisher": "出版社",
        "label": "レーベル", "genre": "ジャンル", "tag": "タグ", "author": "著者", "series": "作品", "search": "検索", "favorites": "お気に入り",
        "publisher_month": "出版社の月別", "label_month": "レーベルの月別", "genre_month": "ジャンルの月別", "updates": "発売日の変更・決定", "feature": "特集"}
PLACE = {"main": "本のページの購入ボタン", "buy_bar": "スマホの下の帯", "collect": "1巻からそろえる", "now_read": "電子版で今すぐ読む", "list": "一覧の本"}
FAV = {"add": "追加", "remove": "削除", "import": "引き継ぎで追加", "bulk_add": "特集記事でまとめて追加"}
SERVICE = {"apple": "iPhone・Mac", "google": "Googleカレンダー", "google_one_book": "この巻だけ（Google）", "ics_one_book": "この巻だけ（iPhone・その他）"}
SCOPES = ["https://www.googleapis.com/auth/analytics.readonly", "https://www.googleapis.com/auth/analytics.edit"]


def env_key():
    return os.environ.get("GA_SERVICE_ACCOUNT_JSON") or os.environ.get("GA4_SA_KEY")


def env_prop():
    return os.environ.get("GA_PROPERTY_ID") or os.environ.get("GA4_PROPERTY_ID")


def credentials():
    info = json.loads(env_key())
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


def run(client, prop, start, end, dims, metric="eventCount", event=None, limit=50, path=None):
    from google.analytics.data_v1beta.types import (DateRange, Dimension, Filter, FilterExpression, Metric, OrderBy, RunReportRequest)
    req = RunReportRequest(
        property=f"properties/{prop}", date_ranges=[DateRange(start_date=start, end_date=end)],
        dimensions=[Dimension(name=d) for d in dims], metrics=[Metric(name=metric)], limit=limit,
        order_bys=[OrderBy(metric=OrderBy.MetricOrderBy(metric_name=metric), desc=True)],
    )
    if event:
        req.dimension_filter = FilterExpression(filter=Filter(field_name="eventName", string_filter=Filter.StringFilter(value=event)))
    if path:
        req.dimension_filter = FilterExpression(filter=Filter(field_name="pagePath", string_filter=Filter.StringFilter(
            value=path, match_type=Filter.StringFilter.MatchType.CONTAINS)))
    res = client.run_report(req)
    return [([v.value for v in r.dimension_values], int(float(r.metric_values[0].value))) for r in res.rows]


def safe(client, prop, start, end, dims, metric="eventCount", event=None, limit=50):
    """項目（カスタムディメンション）が GA4 に登録されていないときなどは、その欄だけ空にして続ける。"""
    try:
        return run(client, prop, start, end, dims, metric, event, limit), None
    except Exception as exc:  # noqa: BLE001
        print(f"取れなかった欄：{dims} {event or ''}（{type(exc).__name__}）")
        return [], "（この欄は取れませんでした。GA4 に項目が登録されていない可能性があります。ga-report の setup を動かしてください）"


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
    # 操作ごとの人数（同じブラウザを1人と数える。GA4 の totalUsers）
    people = dict((d[0], n) for d, n in run(client, prop, s, e, ["eventName"], "totalUsers"))
    fav_page = run(client, prop, s, e, [], "screenPageViews", path="/favorites")
    fav_page = fav_page[0][1] if fav_page else 0
    stores, err_store = safe(client, prop, s, e, ["customEvent:store", "customEvent:buy_type"], event="store_click")
    pages, err_page = safe(client, prop, s, e, ["customEvent:page_type"], event="store_click", limit=20)
    places, err_place = safe(client, prop, s, e, ["customEvent:place"], event="store_click", limit=20)
    favs, err_fav = safe(client, prop, s, e, ["customEvent:fav_action"], event="favorite")
    fav_people, _ = safe(client, prop, s, e, ["customEvent:fav_action"], "totalUsers", event="favorite")
    fav_people = dict((d[0], n) for d, n in fav_people)
    cals, err_cal = safe(client, prop, s, e, ["customEvent:service"], event="calendar_subscribe")
    feeds, err_feed = safe(client, prop, s, e, ["customEvent:feed"], event="rss_subscribe", limit=20)
    # 項目を GA4 に登録する前（2026-11-22 より前）の記録は (not set) になる
    name = lambda table_, v: "（登録前の記録）" if v == "(not set)" else table_.get(v, v or "（不明）")
    both = lambda ev: f"{events.get(ev, 0)}回（{people.get(ev, 0)}人）"
    lines = [
        f"# {y}年{m}月のレポート（{s}〜{e}）", "",
        "## 全体",
        table(["項目", "数"], [
            ["ページが見られた回数", total[0][1] if total else 0],
            ["見た人の数（アクティブユーザー）", users[0][1] if users else 0],
            ["書店のボタンが押された", both("store_click")],
            ["お気に入りの操作", both("favorite")],
            ["お気に入りのページが見られた回数", fav_page],
            ["カレンダー登録", both("calendar_subscribe")],
            ["RSS の登録", both("rss_subscribe")],
            ["まとめてカートに入れる", both("cart_add")],
            ["サイト内の検索", both("view_search_results")],
        ]), "",
        "## 書店のボタン（書店・予約か購入か）",
        err_store or table(["書店", "予約か購入か", "回数"], [[name(STORE, d[0]), name(BUY, d[1]), n] for d, n in stores]), "",
        "## 書店のボタンが押されたページ",
        err_page or table(["ページの種類", "回数"], [[name(PAGE, d[0]), n] for d, n in pages]), "",
        "## 書店のボタンの場所（2026-11-24 から）",
        err_place or table(["場所", "回数"], [[name(PLACE, d[0]), n] for d, n in places]), "",
        "## お気に入り",
        err_fav or table(["操作", "回数", "人数"], [[name(FAV, d[0]), n, fav_people.get(d[0], 0)] for d, n in favs]), "",
        "## カレンダー登録",
        err_cal or table(["種類", "回数"], [[name(SERVICE, d[0]), n] for d, n in cals]), "",
        "## RSS の登録（多い順に20件）",
        err_feed or table(["RSS", "回数"], [[name({}, d[0]), n] for d, n in feeds]), "",
        "※ 人数は、同じブラウザを1人として数えたものです（GA4 の総ユーザー数）。",
        "※ ブラウザの広告ブロックなどで記録されない操作があるため、実際の数より少なめに出ます。",
        "※ 書店・お気に入りの操作などの内訳は、GA4 に項目を登録した日からの記録だけが数えられます。",
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
    ap.add_argument("--print", action="store_true", help="保存せず表示だけする")
    ap.add_argument("--out-dir", help="レポートを {月}.md として保存するフォルダ")
    ap.add_argument("--setup", action="store_true", help="カスタムディメンションを登録する")
    args = ap.parse_args()
    prop = env_prop()
    if not prop or not env_key():
        raise SystemExit("GA_PROPERTY_ID と GA_SERVICE_ACCOUNT_JSON が登録されていません")
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
    elif args.out_dir:
        from pathlib import Path
        path = Path(args.out_dir) / f"{month}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body + "\n", encoding="utf-8")
        print("保存しました：", path.name)
    else:
        post_issue(title, body)


if __name__ == "__main__":
    sys.exit(main())
