"""一覧ページの上に出す説明の文章（2026-11-11 運営者の判断）。

データベースの事実（点数・出版社・新シリーズの1巻・完結巻・発売日など）から、そのページならではの短い文章を作る。
紹介文やあらすじなど、ほかのサイトの文章は使わない。
"""
from collections import Counter

from .normalize import series_name

DOWS = "月火水木金土日"
NAMES_MAX = 3  # 文章の中に書名を挙げる数


def _dow(d):
    return DOWS[d.weekday()]


def _md(d):
    return f"{d.month}月{d.day}日（{_dow(d)}）"


def _work(b, with_volume=True):
    """『作品名』N巻 の形。巻数のない本は『書名』。"""
    if b.volume is None:
        return f"『{b.title}』"
    name = series_name(b.title) or b.title
    return f"『{name}』{b.volume}巻" if with_volume else f"『{name}』"


def _names(books, with_volume=True):
    seen, out = set(), []
    for b in books:
        w = _work(b, with_volume)
        if w not in seen:
            seen.add(w)
            out.append(w)
        if len(out) == NAMES_MAX:
            break
    return "、".join(out)


def _count(names, n):
    """『A』、『B』など5点 ／ 1点だけのときは『A』。"""
    if n == 1:
        return names
    return f"{names}など{n}点" if n > NAMES_MAX else f"{names}の{n}点"


def _top(counter, n=3):
    return "、".join(f"{k}（{v}点）" for k, v in counter.most_common(n))


def _first_final(books, prefix=""):
    """新シリーズの1巻と完結巻の文。"""
    out = []
    firsts = [b for b in books if b.is_first]
    finals = [b for b in books if b.is_final]
    if firsts:
        out.append(f"{prefix}新シリーズの1巻は{_count(_names(firsts, False), len(firsts))}")
    if finals:
        out.append(f"完結巻は{_count(_names(finals), len(finals))}")
    if not out:
        return ""
    return "、".join(out) + "です。"


def _ebook(books):
    n = sum(1 for b in books if b.has_ebook and not b.ebook_only)
    return f"電子版の同時配信が予定されている本は{n}点あります。" if n else ""


def day(d, books, today):
    """日ごと・今日発売のページ。books はその日の本（並び順のまま）。"""
    if not books:
        return ""
    pubs = Counter(b.publisher for b in books)
    # 点数は見出しの下に出ているので、ここでは出版社から書き始める
    s = []
    if len(pubs) > 1:
        s.append(f"この日は{len(pubs)}社から{len(books)}点が発売され、点数が多いのは{_top(pubs)}です。")
    else:
        s.append(f"この日の新刊は、すべて{next(iter(pubs))}の本です。")
    s.append(_first_final(books))
    s.append(_ebook(books))
    return "".join(x for x in s if x)


def week(start, end, days_books):
    """今週発売のページ。days_books は [(日付, その日の本)]。"""
    total = sum(len(v) for _, v in days_books)
    if not total:
        return f"{start.month}月{start.day}日から{end.month}月{end.day}日までの1週間に発売される漫画の新刊は、まだ登録されていません。"
    peak_d, peak = max(days_books, key=lambda x: len(x[1]))
    all_books = [b for _, v in days_books for b in v]
    pubs = Counter(b.publisher for b in all_books)
    s = [f"{start.month}月{start.day}日から{end.month}月{end.day}日までの1週間に発売される漫画・コミックの新刊は{total}点です。",
         f"いちばん多いのは{_md(peak_d)}の{len(peak)}点で、出版社別では{_top(pubs)}が多くなっています。",
         _first_final(all_books, "今週の")]
    return "".join(x for x in s if x)


def month(y, m, books):
    """月ごとのカレンダー。books はその月に発売される本。"""
    if not books:
        return ""
    by_day = Counter(b.release for b in books)
    peak_d, peak_n = by_day.most_common(1)[0]
    pubs = Counter(b.publisher for b in books)
    s = [f"{y}年{m}月に発売される漫画・コミックの新刊は{len(books)}点で、発売日は{len(by_day)}日あります。",
         f"いちばん多いのは{_md(peak_d)}の{peak_n}点です。",
         f"出版社別では{_top(pubs)}が多くなっています。",
         _first_final(books)]
    return "".join(x for x in s if x) + "日付を選ぶと、その日の新刊が見られます。"


def listing(subject, books, today, kind):
    """出版社・レーベル・タグ・著者のページ。subject は「集英社」「ジャンプコミックス」など。"""
    noun = subject if kind == "tag" else f"{subject}の漫画の新刊"
    upcoming = sorted((b for b in books if b.release and b.release >= today), key=lambda b: b.release)
    past = [b for b in books if b.release and b.release < today]
    s = []
    if upcoming:
        nxt = upcoming[0].release
        n_next = sum(1 for b in upcoming if b.release == nxt)
        last = upcoming[-1].release
        s.append(f"これから発売が予定されている{noun}は、{last.year}年{last.month}月までに{len(upcoming)}点です。")
        s.append(f"次の発売日は{_md(nxt)}で、{_count(_names([b for b in upcoming if b.release == nxt]), n_next)}が出ます。")
    elif past:
        s.append(f"これから発売される{noun}は、今のところ登録されていません。")
    if kind == "publisher":
        labels = Counter(b.label for b in upcoming if b.label)
        if len(labels) > 1:
            s.append(f"レーベル別では{_top(labels)}が多くなっています。")
    elif kind in ("tag", "author"):
        pubs = Counter(b.publisher for b in upcoming)
        if len(pubs) > 1:
            s.append(f"出版社別では{_top(pubs)}が多くなっています。")
        elif len(pubs) == 1:
            s.append(f"出版社は{next(iter(pubs))}です。")
    if kind != "tag":
        s.append(_first_final(upcoming, "これから発売される"))
    if past:
        s.append("これまでに発売された本も、下にまとめています。")
    return "".join(x for x in s if x)


def listing_month(subject, y, m, books, today, kind):
    """出版社・レーベルの月別ページ。books はその月に発売される本（発売日の順）。"""
    if not books:
        return ""
    by_day = Counter(b.release for b in books)
    peak_d, peak_n = max(by_day.items(), key=lambda x: (x[1], -x[0].toordinal()))
    on_sale = sum(1 for b in books if b.release <= today)
    s = [f"{subject}から{y}年{m}月に発売される漫画の新刊は{len(books)}点で、発売日は{len(by_day)}日あります。"]
    if len(by_day) > 1:
        s.append(f"いちばん多いのは{_md(peak_d)}の{peak_n}点です。")
    if kind == "publisher":
        labels = Counter(b.label for b in books if b.label)
        if len(labels) > 1:
            s.append(f"レーベル別では{_top(labels)}が多くなっています。")
    s.append(_first_final(books))
    s.append(_ebook(books))
    if 0 < on_sale < len(books):
        s.append(f"このうち{on_sale}点はすでに発売されています。")
    elif on_sale == len(books):
        s.append("この月の新刊は、すべて発売されています。")
    return "".join(x for x in s if x)


def series(name, vols, latest, status, today, authors, forecast=None):
    """作品ごとのページ。vols は巻数のある本（巻数の順）。"""
    who = "・".join(a["name"] for a in authors[:2] if a.get("name"))
    where = f"{latest.publisher}の{latest.label}" if latest.label else latest.publisher
    s = [f"『{name}』は{who + 'による' if who else ''}漫画で、{where}から刊行されています。"]
    if latest.release:
        if latest.release > today:
            s.append(f"最新刊の{latest.volume}巻は{latest.release.year}年{_md(latest.release)}に発売予定です。")
        elif latest.volume == 1:
            s.append(f"1巻は{latest.release.year}年{_md(latest.release)}に発売されました。")
        else:
            s.append(f"既刊は{latest.volume}巻で、最新刊の{latest.volume}巻は{latest.release.year}年{_md(latest.release)}に発売されました。")
    if status == "完結":
        s.append(f"{latest.volume}巻で完結しています。")
    elif forecast:
        s.append(f"これまでの刊行の間隔から、次の{forecast['volume']}巻は{forecast['year']}年{forecast['month']}月ごろの発売と予想しています（発売日が決まりしだい、このページに載せます）。")
    if vols[0].volume == 1 and vols[0].release and latest.volume and latest.volume > 1:
        f = vols[0].release
        s.append(f"1巻の発売は{f.year}年{f.month}月です。")
    return "".join(x for x in s if x)
