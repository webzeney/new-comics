"""Amazon Creators API の動作確認（手動で実行する）。書名は数件だけ出し、ほかは件数と日付だけを出す。"""
import collections
import json
import sys

from .amazon import Api, AmazonError, release_of, title_of


def show(items, n=5):
    for it in items[:n]:
        c = (it.get("itemInfo") or {}).get("classifications") or {}
        print(" ", it.get("asin"), release_of(it), (c.get("binding") or {}).get("displayValue"), title_of(it)[:60])


def lookup(api, query):
    """ASIN（ISBN-10）と書名・ISBN で、商品ページがあるかを確かめる。"""
    for q in query.split(","):
        q = q.strip()
        if len(q) == 10:
            try:
                items = api.get([q])
                print("getItems", q, "→", len(items), "件"); show(items)
            except AmazonError as e:
                print("getItems", q, "→ エラー", e)
        for index in ("Books", "KindleStore"):
            try:
                items = api.search(q, index=index, resources=["itemInfo.title", "itemInfo.contentInfo", "itemInfo.productInfo", "itemInfo.classifications", "itemInfo.externalIds"])
            except AmazonError as e:
                print("search", index, q, "→ エラー", e); continue
            print("search", index, q, "→", len(items), "件"); show(items)
            for it in items[:3]:
                print("   ", json.dumps((it.get("itemInfo") or {}).get("externalIds"), ensure_ascii=False)[:300])


def main():
    api = Api()
    if not api.ready():
        raise SystemExit("認証情報が登録されていません")
    if len(sys.argv) > 1 and sys.argv[1]:
        lookup(api, sys.argv[1])
        print("呼び出し回数：", api.calls)
        return
    print("== Kindle版を探す ==")
    items = api.search("史上最強の弟子ケンイチ 愛蔵版", index="KindleStore")
    print("件数", len(items)); show(items)
    if items:
        print("項目の形：", json.dumps(items[0], ensure_ascii=False)[:1500])
    print("== 紙の本を書名で探す ==")
    items = api.search("ギャングキング 3", index="Books")
    print("件数", len(items)); show(items)
    print("== どのくらい先まで載っているか（コミック・新着順） ==")
    months = collections.Counter()
    latest = []
    for node in ("2278488051",):
        for page in range(1, 11):
            try:
                items = api.search("コミック", index="Books", sortBy="NewestArrivals", itemPage=page, browseNodeId=node, availability="IncludeOutOfStock")
            except AmazonError as e:
                print("エラー", page, e); break
            for it in items:
                d = release_of(it)
                if d:
                    months[d[:7]] += 1
                    latest.append(d)
    print("発売月ごとの件数：", sorted(months.items()))
    if latest:
        print("一番先の発売日：", max(latest))
    print("呼び出し回数：", api.calls)


if __name__ == "__main__":
    main()
