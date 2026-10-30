import re
import shutil
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined

ROOT = Path(__file__).resolve().parents[2]
TEMPLATES = ROOT / "templates"
STATIC = ROOT / "static"

MENU = [
    ("top", "トップ", ""),
    ("calendar", "新刊カレンダー", "calendar/"),
    ("publisher", "出版社から探す", "publisher/"),
    ("label", "レーベルから探す", "label/"),
    ("favorites", "お気に入り", "favorites/"),
    ("feature", "特集", "feature/"),
    ("updates", "発売日の変更・決定", "updates/"),
]
FOOTER = [
    ("about", "運営者情報", "about/"),
    ("privacy", "プライバシーポリシー", "privacy/"),
    ("disclaimer", "免責事項", "disclaimer/"),
    ("contact", "お問い合わせ（掲載内容の修正・削除のご依頼）", "contact/"),
]


def environment():
    env = Environment(
        loader=FileSystemLoader(str(TEMPLATES)),
        autoescape=True,
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
    )
    return env


def site_context(root, tags, year, rakuten_credit=False):
    return {
        "rakuten_credit": rakuten_credit,
        "menu": [{"key": k, "label": label, "url": (root + path) or "./"} for k, label, path in MENU],
        "footer": [{"key": k, "label": label, "url": root + path} for k, label, path in FOOTER],
        "tags": [{"key": t["key"], "label": t["label"], "url": root + t["path"]} for t in tags],
        "year": year,
    }


def safe_name(text):
    """ファイル名に使えるよう、英数字とハイフン以外をハイフンにする。"""
    return re.sub(r"[^A-Za-z0-9-]+", "-", str(text)).strip("-") or "x"


def page_defaults(**kw):
    base = {"title": "", "description": "", "canonical": None, "menu": None, "footer": None, "tag": None, "is_top": False}
    base.update(kw)
    return base


class Writer:
    def __init__(self, out_dir, tags, year, ga4_id=None, site_url=None, rakuten_credit=False):
        self.out = Path(out_dir)
        self.env = environment()
        self.tags = tags
        self.year = year
        self.ga4_id = ga4_id
        self.site_url = (site_url or "").rstrip("/")
        self.rakuten_credit = rakuten_credit
        self.count = 0
        self.partials = {}

    def partial(self, name, template, page=None):
        """全ページ共通の部品を assets/partials/ に一度だけ書き出し、ファイル名を返す。

        ページ側は PHP の readfile で読み込むので、部品を変えたときに転送するのはこのファイルだけで済む。
        リンクは「/」から始まる書き方にして、どの階層のページから読み込んでも同じ内容になるようにする。
        """
        if name in self.partials:
            return name
        ctx = {
            "root": "/",
            "page": page_defaults(**(page or {})),
            "site": site_context("/", self.tags, self.year, self.rakuten_credit),
            "ga4_id": self.ga4_id,
        }
        html = self.env.get_template(template).render(**ctx)
        dest = self.out / "assets" / "partials" / name
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(html, encoding="utf-8")
        self.partials[name] = True
        return name

    def includes(self, page):
        menu, tag, footer = page.get("menu"), page.get("tag"), page.get("footer")
        side = "sidemenu--" + (menu or "none") + ("--tag-" + safe_name(tag) if tag else "") + ("--contact" if footer == "contact" else "") + ".html"
        foot = "footer--" + (footer or "none") + ".html"
        return {
            "head": self.partial("head.html", "_head.html"),
            "sidemenu": self.partial(side, "_sidemenu.html", {"menu": menu, "tag": tag, "footer": footer}),
            "footer": self.partial(foot, "_footer.html", {"footer": footer}),
        }

    def write(self, rel_path, template, page, **context):
        depth = rel_path.count("/")
        root = "../" * depth
        if self.site_url and page.get("canonical") is None:
            page["canonical"] = f"{self.site_url}/{rel_path[:-len('index.html')] if rel_path.endswith('index.html') else rel_path}"
        html = self.env.get_template(template).render(
            root=root,
            page=page,
            site=site_context(root, self.tags, self.year, self.rakuten_credit),
            ga4_id=self.ga4_id,
            inc=self.includes(page),
            **context,
        )
        target = self.out / rel_path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(html, encoding="utf-8")
        self.count += 1
        return target

    def copy_assets(self):
        dest = self.out / "assets"
        if dest.exists():
            shutil.rmtree(dest)
        shutil.copytree(STATIC, dest)
