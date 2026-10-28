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
    ("feature", "特集", "feature/"),
    ("updates", "新着・更新情報", "updates/"),
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
