"""X（旧Twitter）に、その日発売の漫画新刊を投稿する。

毎朝 GitHub Actions から動かす。発売のない日は投稿しない。
書名は、サイトの一覧と同じ順（出版社の順 → 売れている順）に、文字数の上限まで並べる。
リンクはサイトの日ごとの新刊ページ。書影は付けない（楽天の書影はサイトの中だけで使う）。
画像は、日付・点数と看板キャラクター（こはる）の絵を組み合わせたもの（ximage.py）。
画像のアップロードに失敗したときは、文面だけで投稿する。
認証情報は環境変数 X_API_KEY・X_API_SECRET・X_ACCESS_TOKEN・X_ACCESS_SECRET（GitHub の Secrets）から読む。
"""
import argparse
import base64
import tempfile
import hashlib
import hmac
import os
import re
import secrets
import sys
import time
import unicodedata
from datetime import date, datetime
from pathlib import Path
from urllib.parse import quote

import requests

from . import db, ximage
from .build import Site, dow, md, title_parts

POST_URL = "https://api.x.com/2/tweets"
MEDIA_URL = "https://api.x.com/2/media/upload"
LIMIT = 280      # X の文字数の上限（全角は2、URL は23として数える）
URL_WEIGHT = 23
HASHTAGS = "#新刊"
TAG_WORKS = 2    # その日の人気の作品（投稿の並びの上から）を、作品名のハッシュタグにする数（2026-11-20 運営者の判断）
TAG_MAX = 16     # 作品名のハッシュタグがこれより長いときは付けない
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


EDITION = re.compile(r"(永久愛蔵版|愛蔵版|新装版|完全版|文庫版|ワイド版|特装版|限定版|通常版|豪華版|上巻|中巻|下巻|コミック)")


def load_xtags():
    """ハッシュタグの対応表（xtags.tsv）。書名に含まれる文字 → ハッシュタグ。"""
    out = []
    path = Path(__file__).with_name("xtags.tsv")
    for line in path.read_text(encoding="utf-8").splitlines()[1:]:
        cols = line.split("\t")
        if len(cols) >= 2 and cols[0].strip() and cols[1].strip().startswith("#"):
            out.append((cols[0].strip(), cols[1].strip()))
    return out


XTAGS = load_xtags()


def work_tag(b):
    """作品名のハッシュタグ。対応表（xtags.tsv）にあればそれを使う。なければ巻数・~副題~・版の名前・空白・記号を外して作る。
    作れないとき・長すぎるときは None。"""
    for key, tag in XTAGS:
        if key in b.title:
            return tag
    main, _ = title_parts(b)
    name = re.sub(r"\s*[~〜～][^~〜～]+[~〜～]\s*", " ", main or b.title)
    name = re.sub(r"[（(【\[].*?[）)】\]]", "", name)
    name = unicodedata.normalize("NFKC", name)
    name = re.split(r"(?<=\D)\s*\d+(?:\s|$)", name)[0]  # 巻数より後ろ（副題など）は外す
    tag = re.sub(r"(?<=\D)\d+$", "", "".join(re.findall(r"\w", EDITION.sub("", name))))
    if not tag or tag.isdigit() or len(tag) > TAG_MAX:
        return None
    return "#" + tag


def hashtags(books):
    """「#新刊」と、その日の人気の作品（投稿の並びの上から）の作品名のハッシュタグ。"""
    tags = []
    for b in books:
        t = work_tag(b)
        if t and t not in tags and t != "#新刊":
            tags.append(t)
        if len(tags) >= TAG_WORKS:
            break
    return " ".join([HASHTAGS] + tags)


def compose(site, day, base):
    books = site.by_date.get(day) or []
    if not books:
        return None
    head = f"【今日{md(day)}（{dow(day)}）発売の漫画新刊】{len(books)}点"
    url = f"{base}/date/{day.isoformat()}/"
    tags = hashtags(books)
    lines = []
    seen = set()
    for b in books:  # サイトと同じ並び（出版社の順 → 売れている順）
        name = short(b)
        if name in seen:
            continue
        rest = len(books) - len(lines) - 1
        trial = lines + [f"・{name}"]
        tail = [f"ほか{rest}点"] if rest > 0 else []
        text = "\n".join([head, ""] + trial + tail + ["", url, tags])
        if weight(text) > LIMIT:
            continue
        lines = trial
        seen.add(name)
    rest = len(books) - len(lines)
    return "\n".join([head, ""] + lines + ([f"ほか{rest}点"] if rest > 0 else []) + ["", url, tags])


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


def upload(path, keys):
    """画像をアップロードして、投稿に付ける番号（media id）を返す。"""
    media = base64.b64encode(open(path, "rb").read()).decode()
    r = requests.post(MEDIA_URL, json={"media": media, "media_category": "tweet_image"},
                      headers={"Authorization": oauth_header("POST", MEDIA_URL, keys)}, timeout=60)
    if r.status_code not in (200, 201):
        raise RuntimeError(f"HTTP {r.status_code}：{r.text[:300]}")
    media_id = (r.json().get("data") or {}).get("id")
    if not media_id:
        raise RuntimeError(f"番号が返ってきませんでした：{r.text[:300]}")
    return media_id


def post(text, keys, media_id=None):
    body = {"text": text}
    if media_id:
        body["media"] = {"media_ids": [media_id]}
    r = requests.post(POST_URL, json=body, headers={"Authorization": oauth_header("POST", POST_URL, keys)}, timeout=30)
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
    ap.add_argument("--text", help="新刊の代わりに、この文面を投稿する（お知らせ用）")
    ap.add_argument("--no-image", action="store_true", help="画像を付けずに投稿する")
    ap.add_argument("--image-out", help="作った画像をこの場所に保存する（確認用）")
    args = ap.parse_args(argv)
    keys = {"api_key": os.environ.get("X_API_KEY"), "api_secret": os.environ.get("X_API_SECRET"),
            "token": os.environ.get("X_ACCESS_TOKEN"), "token_secret": os.environ.get("X_ACCESS_SECRET")}
    if args.check:
        missing = [k for k, v in keys.items() if not v]
        if missing:
            raise SystemExit("登録されていない認証情報があります：" + ", ".join(missing))
        check(keys)
        return 0
    if args.text:
        text = args.text.replace("\\n", "\n")
        print(text)
        print(f"（文字数の目安 {weight(text)}／{LIMIT}）")
        if weight(text) > LIMIT:
            raise SystemExit("文字数が多すぎます")
        if args.dry_run or not all(keys.values()):
            print("（投稿していません）")
            return 0
        print("投稿しました：", post(text, keys))
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
    image = None
    if not args.no_image:
        image = args.image_out or str(Path(tempfile.mkdtemp()) / "x.png")
        try:
            ximage.make(day, len(site.by_date[day]), image)
            print("画像を作りました：", image)
        except Exception as e:  # 画像が作れなくても、文面だけで投稿する
            print(f"画像を作れませんでした（文面だけで投稿します）：{e}")
            image = None
    if args.dry_run:
        print("（確認だけのため投稿していません）")
        return 0
    if not all(keys.values()):
        print("X の認証情報が登録されていないため投稿していません")
        return 0
    media_id = None
    if image:
        try:
            media_id = upload(image, keys)
        except Exception as e:  # アップロードに失敗しても、文面だけで投稿する
            print(f"画像をアップロードできませんでした（文面だけで投稿します）：{e}")
    print("投稿しました：", post(text, keys, media_id), "（画像あり）" if media_id else "（画像なし）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
