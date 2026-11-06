"""Amazon Creators API の呼び出し。

認証情報は環境変数 AMAZON_CREATORS_ID・AMAZON_CREATORS_SECRET（GitHub の Secrets）から読む。
リクエストは 1 秒に 1 回以下にする。
"""
import json
import os
import time

import requests

TOKEN_URL = "https://api.amazon.co.jp/auth/o2/token"
API_URL = "https://creatorsapi.amazon/catalog/v1/"
MARKETPLACE = "www.amazon.co.jp"
INTERVAL = 1.1


class AmazonError(Exception):
    pass


class Api:
    def __init__(self, cid=None, secret=None, tag=None, session=None):
        self.cid = cid or os.environ.get("AMAZON_CREATORS_ID", "")
        self.secret = secret or os.environ.get("AMAZON_CREATORS_SECRET", "")
        self.tag = tag or os.environ.get("AMAZON_TAG") or "newcomicsjp-22"
        self.http = session or requests.Session()
        self.token = None
        self.token_until = 0
        self.last = 0.0
        self.calls = 0

    def ready(self):
        return bool(self.cid and self.secret)

    def _token(self):
        if self.token and time.time() < self.token_until - 60:
            return self.token
        r = self.http.post(TOKEN_URL, json={"grant_type": "client_credentials", "client_id": self.cid, "client_secret": self.secret, "scope": "creatorsapi::default"}, timeout=30)
        data = r.json() if r.content else {}
        if r.status_code != 200 or not data.get("access_token"):
            raise AmazonError(f"トークンを取得できませんでした（HTTP {r.status_code} {data.get('error', '')}）")
        self.token = data["access_token"]
        self.token_until = time.time() + int(data.get("expires_in") or 3600)
        return self.token

    def _post(self, op, body):
        for attempt in range(4):
            wait = self.last + INTERVAL - time.time()
            if wait > 0:
                time.sleep(wait)
            self.last = time.time()
            self.calls += 1
            r = self.http.post(API_URL + op, data=json.dumps({"partnerTag": self.tag, "marketplace": MARKETPLACE, **body}),
                               headers={"Content-Type": "application/json", "Authorization": f"Bearer {self._token()}", "x-marketplace": MARKETPLACE}, timeout=30)
            if r.status_code == 429 or r.status_code >= 500:
                time.sleep(5 * (attempt + 1))
                continue
            data = r.json() if r.content else {}
            if r.status_code != 200:
                errs = data.get("errors") or [data]
                raise AmazonError(f"HTTP {r.status_code} " + "; ".join(str(e.get("code") or e.get("type") or "") for e in errs))
            return data
        raise AmazonError(f"{op} が混み合っていて取得できませんでした")

    def search(self, keywords, index="Books", resources=None, **extra):
        body = {"keywords": keywords, "searchIndex": index, "itemCount": 10,
                "resources": resources or ["itemInfo.title", "itemInfo.contentInfo", "itemInfo.productInfo", "itemInfo.classifications"], **extra}
        try:
            data = self._post("searchItems", body)
        except AmazonError as e:
            if "NoResults" in str(e):
                return []
            raise
        return (data.get("searchResult") or {}).get("items") or []

    def get(self, asins, resources=None):
        data = self._post("getItems", {"itemIds": list(asins), "itemIdType": "ASIN",
                                       "resources": resources or ["itemInfo.title", "itemInfo.contentInfo", "itemInfo.productInfo"]})
        return (data.get("itemsResult") or {}).get("items") or []


def title_of(item):
    return ((item.get("itemInfo") or {}).get("title") or {}).get("displayValue") or ""


def release_of(item):
    """発売日（YYYY-MM-DD）。分からなければ None。"""
    info = item.get("itemInfo") or {}
    for path in (("contentInfo", "publicationDate"), ("productInfo", "releaseDate")):
        v = ((info.get(path[0]) or {}).get(path[1]) or {}).get("displayValue")
        if v:
            return str(v)[:10]
    return None
