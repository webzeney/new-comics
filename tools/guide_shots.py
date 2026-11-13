"""「このサイトの使い方」に載せる画面写真を撮る（手動の確認用）。

ローカルで表示した dist のページを、スマホの幅で部分ごとに撮る。
書影（楽天・Amazon の画像）は写真に残さないよう、隠してから撮る。
"""
import json
import re
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

DIST = Path(sys.argv[1] if len(sys.argv) > 1 else "dist")
OUT = Path("shots")
BASE = "http://127.0.0.1:8099/"
HIDE_COVERS = "img.cover_photo,.book__cover img,.slider img,.sameday img,.works img{visibility:hidden!important}"


def pick_book():
    """発売前で、「この本について」に次の巻か見込みが書かれている本。"""
    for f in sorted(DIST.glob("book/*/index.html")):
        html = f.read_text(encoding="utf-8")
        if "で予約" in html and ("見込まれます" in html or "次の巻（" in html) and "前の巻（" in html:
            return f.parent.name
    for f in sorted(DIST.glob("book/*/index.html")):
        if "で予約" in f.read_text(encoding="utf-8"):
            return f.parent.name
    return None


def pick_month_page():
    best = None
    for f in DIST.glob("publisher/*/20??-??/index.html"):
        m = re.search(r'stat__num">(\d+)<', f.read_text(encoding="utf-8"))
        n = int(m.group(1)) if m else 0
        if 8 <= n <= 40 and (best is None or n > best[0]):
            best = (n, f.parent)
    return str(best[1].relative_to(DIST)) + "/" if best else None


def series_name(sid, fallback):
    f = DIST / "series" / str(sid) / "index.html"
    if f.exists():
        m = re.search(r"<h1[^>]*>(.*?)</h1>", f.read_text(encoding="utf-8"), re.S)
        if m:
            name = re.sub(r"<[^>]+>", "", m.group(1)).strip()
            return re.sub(r"の(新刊|既刊).*$", "", name)
    return fallback


def pick_favorites():
    items = json.loads((DIST / "search" / "index.json").read_text(encoding="utf-8"))["items"]
    favs, seen = [], set()
    for it in items:
        if it.get("ch") and it.get("sr") and it["sr"] not in seen and it.get("d"):
            seen.add(it["sr"])
            favs.append({"id": it["sr"], "name": series_name(it["sr"], it["t"]), "url": f"/series/{it['sr']}/"})
        if len(favs) == 2:
            break
    for it in items:
        if len(favs) >= 3:
            break
        if it.get("sr") and it["sr"] not in seen and it.get("d"):
            seen.add(it["sr"])
            favs.append({"id": it["sr"], "name": series_name(it["sr"], it["t"]), "url": f"/series/{it['sr']}/"})
    return favs


def shot(page, name, selector, pad=12, until=None, height=None):
    page.add_style_tag(content=HIDE_COVERS)
    page.wait_for_timeout(300)
    el = page.locator(selector).first
    el.evaluate("e => { e.scrollIntoView({block: 'start'}); scrollBy(0, -80); }")
    page.wait_for_timeout(300)
    box = el.bounding_box()
    if not box:
        print("NOT FOUND", name, selector)
        return
    bottom = box["y"] + box["height"]
    if until:
        b2 = page.locator(until).first.bounding_box()
        if b2:
            bottom = b2["y"] + b2["height"]
    if height:
        bottom = box["y"] + height
    box = el.bounding_box()
    bottom = box["y"] + box["height"]
    if until:
        b2 = page.locator(until).first.bounding_box()
        if b2:
            bottom = b2["y"] + b2["height"]
    if height:
        bottom = box["y"] + height
    y = max(0, box["y"] - pad)
    page.screenshot(path=str(OUT / f"guide_{name}.png"), clip={"x": 0, "y": y, "width": 390, "height": min(bottom + pad, 2400) - y})
    print("SHOT", name)


def main():
    OUT.mkdir(exist_ok=True)
    book = pick_book()
    month = pick_month_page()
    favs = pick_favorites()
    print("BOOK", book, "MONTH", month, "FAVS", len(favs))
    with sync_playwright() as p:
        b = p.chromium.launch()
        ctx = b.new_context(viewport={"width": 390, "height": 2400}, device_scale_factor=2)
        page = ctx.new_page()

        page.goto(BASE + "calendar/", wait_until="networkidle")
        shot(page, "calendar", ".calendar__grid", pad=16)

        if month:
            pub = month.split("/")[1]
            page.goto(BASE + f"publisher/{pub}/", wait_until="networkidle")
            page.add_style_tag(content=HIDE_COVERS)
            page.evaluate("document.querySelector('.monthpanel__more').scrollIntoView({block:'center'})")
            shot(page, "month_link", ".monthpanel:not([hidden]) .group:last-of-type .booklist > li:last-child", until=".monthpanel:not([hidden]) .monthpanel__more")
            page.goto(BASE + month, wait_until="networkidle")
            shot(page, "month_page", ".panel--head", pad=0)

        page.goto(BASE + "search/", wait_until="networkidle")
        page.wait_for_timeout(1000)
        pubs = page.eval_on_selector_all("[name=pub] option", "os => os.map(o => o.value)")
        page.select_option("[name=pub]", "講談社" if "講談社" in pubs else pubs[1])
        shot(page, "search", ".search_form", until=".conditions")

        if book:
            page.goto(BASE + f"book/{book}/", wait_until="networkidle")
            shot(page, "buy", ".book__buy")
            shot(page, "about", "section:has(.book_about)", pad=0)
            shot(page, "follow", ".follow")

        page.goto(BASE + "today/", wait_until="networkidle")
        shot(page, "cart", ".cart_intro", until=".booklist > li:first-child")

        page.goto(BASE + "favorites/", wait_until="networkidle")
        page.evaluate("f => localStorage.setItem('nc_favorites', JSON.stringify(f))", favs)
        page.reload(wait_until="networkidle")
        page.wait_for_timeout(1200)
        shot(page, "favorites_list", "[data-fav-list]")
        if page.locator("[data-fav-changes]:not([hidden])").count():
            shot(page, "favorites_changes", "[data-fav-changes]", until="[data-fav-books] > li:first-child")
        page.click("[data-fav-transfer-open]")
        page.wait_for_timeout(1000)
        page.evaluate("""() => {
            const i = document.querySelector('[data-fav-transfer-url]');
            i.value = i.value.replace(location.origin, 'https://new-comics.jp');
            const qr = window.qrcode(0, 'L'); qr.addData(i.value, 'Byte'); qr.make();
            document.querySelector('[data-fav-transfer-qr]').innerHTML = qr.createSvgTag({cellSize: 4, margin: 2, scalable: true});
        }""")
        page.set_viewport_size({"width": 390, "height": 844})
        page.wait_for_timeout(300)
        page.screenshot(path=str(OUT / "guide_transfer.png"))
        print("SHOT transfer")
        b.close()


if __name__ == "__main__":
    main()
