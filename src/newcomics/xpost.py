"""X（旧Twitter）に、その日発売の漫画新刊を投稿する。

毎朝 GitHub Actions から動かす。発売のない日は投稿しない。
書名は、サイトの一覧と同じ順（出版社の順 → 売れている順）に、文字数の上限まで並べる。
リンクはサイトの日ごとの新刊ページ。書影は付けない（楽天の書影はサイトの中だけで使う）。
認証情報は環境変数 X_API_KEY・X_API_SECRET・X_ACCESS_TOKEN・X_ACCESS_SECRET（GitHub の Secrets）から読む。
"""
import argparse
import base64
import hashlib
import hmac
import os
import re
import secrets
import sys
import time
from datetime import date, datetime
from urllib.parse import quote

import requests

from . import db
from .build import Site, dow, md, title_parts

POST_URL = "https://api.x.com/2/tweets"
LIMIT = 280      # X の文字数の上限（全角は2、URL は23として数える）
URL_WEIGHT = 23
HASHTAGS = "#漫画 #新刊"
NAME_MAX = 24   # 書名がこれより長いときは「…」で切る（1件で枠を使い切らないように）


def weight(text):
    """X の数え方：全角（日本語など）は2、半角は1、URL は23。"""
    n = 0
    for word in text.split("\n"):
        for part in word.split(" "):
            if part.startswith("https://"):
                n += URL_WEIGHT
            else:
                n += sum(1 if (ord(c) <= 0x10FF or 0x2000 <= ord(c) <= 0x200D or 0x2010 <= ord(c) <= 0x201F or 0x2032 <= ord(c) <= 0x2037) else 2 for c in part)
            n += 1
    return n - 1


def short(b):
    """投稿用の短い書名。~副題~ や 〜副題〜 は省く。"""
    main, vol = title_parts(b)
    name = main if vol else b.title
    name = re.sub(r"\s*[~〜～][^~〜～]+[~〜～]\s*", " ", name).strip() or name
    if len(name) > NAME_MAX:
        name = name[:NAME_MAX - 1].rstrip() + "…"
    return f"{name} {vol}巻" if vol else name


def compose(site, day, base):
    books = site.by_date.get(day) or []
    if not books:
        return None
    head = f"【今日{md(day)}（{dow(day)}）発売の漫画新刊】{len(books)}点"
    url = f"{base}/date/{day.isoformat()}/"
    lines = []
    seen = set()
    for b in books:  # サイトと同じ並び（出版社の順 → 売れている順）
        name = short(b)
        if name in seen:
            continue
        rest = len(books) - len(lines) - 1
        trial = lines + [f"・{name}"]
        tail = [f"ほか{rest}点"] if rest > 0 else []
        text = "\n".join([head, ""] + trial + tail + ["", url, HASHTAGS])
        if weight(text) > LIMIT:
            continue
        lines = trial
        seen.add(name)
    rest = len(books) - len(lines)
    return "\n".join([head, ""] + lines + ([f"ほか{rest}点"] if rest > 0 else []) + ["", url, HASHTAGS])


def oauth_header(method, url, keys):
    """OAuth 1.0a の署名（本文が JSON なので、署名に含めるのは oauth_* だけ）。"""
    params = {
        "oauth_consumer_key": keys["api_key"], "oauth_nonce": secrets.token_hex(16), "oauth_signature_method": "HMAC-SHA1",
        "oauth_timestamp": str(int(time.time())), "oauth_token": keys["token"], "oauth_version": "1.0",
    }
    enc = lambda s: quote(str(s), safe="~")
    base = "&".join([method, enc(url), enc("&".join(f"{enc(k)}={enc(v)}" for k, v in sorted(params.items())))])
    key = f"{enc(keys['api_secret'])}&{enc(keys['token_secret'])}"
    params["oauth_signature"] = base64.b64encode(hmac.new(key.encode(), base.encode(), hashlib.sha1).digest()).decode()
    return "OAuth " + ", ".join(f'{enc(k)}="{enc(v)}"' for k, v in sorted(params.items()))


def post(text, keys):
    r = requests.post(POST_URL, json={"text": text}, headers={"Authorization": oauth_header("POST", POST_URL, keys)}, timeout=30)
    if r.status_code not in (200, 201):
        raise SystemExit(f"X への投稿に失敗しました（HTTP {r.status_code}）：{r.text[:300]}")
    return (r.json().get("data") or {}).get("id")


def check(keys):
    """認証情報で投稿先のアカウント名を確かめる（投稿はしない）。"""
    url = "https://api.x.com/2/users/me"
    r = requests.get(url, headers={"Authorization": oauth_header("GET", url, keys)}, timeout=30)
    if r.status_code != 200:
        raise SystemExit(f"認証を確かめられませんでした（HTTP {r.status_code}）：{r.text[:300]}")
    print("投稿先のアカウント：@" + ((r.json().get("data") or {}).get("username") or "?"))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--date", help="投稿する日（YYYY-MM-DD）。省略すると今日（日本時間）")
    ap.add_argument("--dry-run", action="store_true", help="投稿せずに文面だけを表示する")
    ap.add_argument("--check", action="store_true", help="認証情報と投稿先のアカウントだけを確かめる")
    args = ap.parse_args(argv)
    keys = {"api_key": os.environ.get("X_API_KEY"), "api_secret": os.environ.get("X_API_SECRET"),
            "token": os.environ.get("X_ACCESS_TOKEN"), "token_secret": os.environ.get("X_ACCESS_SECRET")}
    if args.check:
        missing = [k for k, v in keys.items() if not v]
        if missing:
            raise SystemExit("登録されていない認証情報があります：" + ", ".join(missing))
        check(keys)
        return 0
    day = date.fromisoformat(args.date) if args.date else datetime.now(db.JST).date()
    base = (os.environ.get("SITE_URL") or "https://new-comics.jp").rstrip("/")
    conn = db.connect(os.environ.get("NEWCOMICS_DB") or db.DEFAULT_PATH)
    site = Site(conn, day, dict(os.environ))
    text = compose(site, day, base)
    if not text:
        print(f"{day} は発売の新刊がないため投稿しません")
        return 0
    print(text)
    print(f"（文字数の目安 {weight(text)}／{LIMIT}）")
    if args.dry_run:
        print("（確認だけのため投稿していません）")
        return 0
    if not all(keys.values()):
        print("X の認証情報が登録されていないため投稿していません")
        return 0
    print("投稿しました：", post(text, keys))
    return 0


if __name__ == "__main__":
    sys.exit(main())
