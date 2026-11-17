"""確認用：ローカルで表示したページの画面写真を撮る。"""
import re
import sys

from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    b = p.chromium.launch()
    for key in sys.argv[1:]:
        search = key.startswith("search/")
        for name, w, h in (("pc", 1280, 900), ("sp", 390, 844)):
            if search:
                h = 2400 if name == "pc" else 3000
            page = b.new_page(viewport={"width": w, "height": h}, device_scale_factor=1 if search else 2)
            path = key if "/" in key else f"book/{key}/"
            page.goto(f"http://127.0.0.1:8099/{path}", wait_until="networkidle")
            page.wait_for_timeout(2500 if search else 800)
            fname = re.sub(r"[^0-9A-Za-z_-]+", "_", key.strip("/"))[:60]
            page.screenshot(path=f"shots/{fname}_{name}.png", full_page=("/" in key and not search))
            page.close()
    b.close()
