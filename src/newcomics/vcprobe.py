"""バリューコマースの商品API（Webサービス）の確認用（手動）。

トークンは環境変数 VC_TOKEN（GitHub の Secrets）から読み、ログには出さない。
キーワード（ISBN や書名）で探し、見つかった商品の店名・書名・JAN コード・商品ページのアドレスを表示する。
"""
import argparse
import os
import sys
import time

import requests

SEARCH_URL = "https://webservice.valuecommerce.ne.jp/productdb/search"


def search(token, keyword, ec_code=None, per_page=10):
    params = {"token": token, "keyword": keyword, "format": "json", "results_per_page": per_page}
    if ec_code:
        params["ecCode"] = ec_code
    r = requests.get(SEARCH_URL, params=params, timeout=30)
    if r.status_code != 200:
        raise SystemExit(f"商品API の問い合わせに失敗しました（HTTP {r.status_code}）")
    return r.json()


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("query", help="キーワード（カンマ区切り）")
    ap.add_argument("--ec", help="広告主の ecCode（カンマ区切り）")
    args = ap.parse_args(argv)
    token = os.environ.get("VC_TOKEN")
    if not token:
        raise SystemExit("VC_TOKEN が未設定です")
    for i, q in enumerate(x.strip() for x in args.query.split(",") if x.strip()):
        if i:
            time.sleep(1.5)
        data = search(token, q, args.ec)
        items = data.get("items") or []
        print("=====", q, "→", data.get("resultCount", len(items)), "件")
        for j, it in enumerate(items[:10]):
            print(" ", it.get("merchantName"), "|", it.get("ecCode"), "|", it.get("title"), "|", it.get("janCode"), "|", it.get("guid"))
            if j == 0:
                # どの項目に何が入っているかを見る（リンクの中の ID は公開されるリンクと同じもの）
                print("    項目:", ", ".join(f"{k}={str(v)[:60]}" for k, v in sorted(it.items()) if k not in ("link", "description")))
        if not items:
            print("  （応答の項目）", sorted(data.keys()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
