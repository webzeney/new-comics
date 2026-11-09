"""確認用：ローカルで表示したページの画面写真を撮る。"""
import sys

from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    b = p.chromium.launch()
    for key in sys.argv[1:]:
        for name, w, h in (("pc", 1280, 900), ("sp", 390, 844)):
            page = b.new_page(viewport={"width": w, "height": h}, device_scale_factor=2)
            path = key if "/" in key else f"book/{key}/"
            page.goto(f"http://127.0.0.1:8099/{path}", wait_until="networkidle")
            page.wait_for_timeout(800)
            page.screenshot(path=f"shots/{key.strip('/').replace('/', '_')}_{name}.png", full_page="/" in key)
            page.close()
    b.close()
