"""取得した投稿を原文のまま静的サイト（このリポジトリ）にする。commit / push は GitHub Actions が行う。

リポジトリの中身:
  data/posts/YYYY-MM.json  … 投稿データ（月ごと。これを元に毎回HTMLを作り直す）
  index.html               … 最新7日分
  u/<アカウント>.html       … アカウントごとの最新投稿
  m/YYYY-MM.html           … 月ごとのアーカイブ
"""
from __future__ import annotations

import html
import json
import re
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .xapi import Post

JST = timezone(timedelta(hours=9))
URL_RE = re.compile(r"https?://[^\s<>\"]+")

LATEST_DAYS = 7
PER_ACCOUNT = 300
WEEKDAYS = "月火水木金土日"

CSS = """
:root { --bg:#fff; --fg:#16181c; --muted:#6b7280; --line:#e5e7eb; --card:#f7f8fa; --link:#1d6fd8; --chip:#eef2f7; }
@media (prefers-color-scheme: dark) {
  :root { --bg:#0f1115; --fg:#e7e9ea; --muted:#9aa0a6; --line:#2a2f37; --card:#171a20; --link:#6aa8ff; --chip:#1f242c; }
}
* { box-sizing: border-box; }
body { margin:0; background:var(--bg); color:var(--fg); line-height:1.7;
       font-family: -apple-system, BlinkMacSystemFont, "Hiragino Sans", "Noto Sans JP", "Yu Gothic UI", sans-serif; }
main { max-width: 680px; margin: 0 auto; padding: 16px; }
a { color: var(--link); text-decoration: none; overflow-wrap: anywhere; }
header h1 { font-size: 1.4rem; margin: 8px 0 4px; }
header h1 a { color: var(--fg); }
.meta { color: var(--muted); font-size: .85rem; }
nav.chips { display:flex; flex-wrap:wrap; gap:6px; margin: 12px 0; }
nav.chips a { background: var(--chip); padding: 2px 10px; border-radius: 999px; font-size: .9rem; }
nav.chips a.on { background: var(--link); color: var(--bg); }
h2.day { font-size: 1rem; margin: 24px 0 4px; padding-bottom: 4px; border-bottom: 2px solid var(--line);
         position: sticky; top: 0; background: var(--bg); }
.post { border-bottom: 1px solid var(--line); padding: 12px 0; }
.post .who { font-weight: 600; }
.post .text { white-space: pre-wrap; overflow-wrap: anywhere; margin-top: 2px; }
.post .foot { color: var(--muted); font-size: .8rem; margin-top: 4px; }
.quoted { border: 1px solid var(--line); border-radius: 10px; padding: 8px 12px; margin-top: 8px;
          font-size: .92rem; background: var(--card); }
.quoted .text { white-space: pre-wrap; overflow-wrap: anywhere; }
.imgs { display:grid; grid-template-columns: repeat(auto-fill, minmax(140px, 1fr)); gap:6px; margin-top:8px; }
.imgs img { width:100%; max-height: 320px; object-fit: cover; border-radius: 8px; }
.empty { color: var(--muted); }
footer { margin: 32px 0 16px; }
footer .months a { margin-right: 10px; }
"""


def _linkify(text: str) -> str:
    out, pos = [], 0
    for m in URL_RE.finditer(text):
        out.append(html.escape(text[pos:m.start()]))
        url = m.group(0)
        out.append(f'<a href="{html.escape(url)}">{html.escape(url)}</a>')
        pos = m.end()
    out.append(html.escape(text[pos:]))
    return "".join(out)


def _time(dt: datetime) -> str:
    return dt.astimezone(JST).strftime("%m/%d %H:%M")


# ---- データ ---------------------------------------------------------------

def _month(p: Post) -> str:
    return p.created_at.astimezone(JST).strftime("%Y-%m")


def load_all(repo: Path) -> list[Post]:
    posts = []
    for f in sorted((repo / "data" / "posts").glob("*.json")):
        try:
            posts.extend(Post.from_json(d) for d in json.loads(f.read_text(encoding="utf-8")))
        except (OSError, ValueError, KeyError, TypeError) as e:
            print(f"{f} を読めませんでした: {e}")
    return posts


def merge(repo: Path, new_posts: list[Post]) -> int:
    """新しい投稿を月ごとのJSONに追記する（同じIDは新しい内容で上書き）。追加した件数を返す。"""
    by_month: dict[str, list[Post]] = defaultdict(list)
    for p in new_posts:
        by_month[_month(p)].append(p)
    added = 0
    for month, items in by_month.items():
        path = repo / "data" / "posts" / f"{month}.json"
        current: dict[str, dict] = {}
        if path.exists():
            current = {d["id"]: d for d in json.loads(path.read_text(encoding="utf-8"))}
        for p in items:
            added += p.id not in current
            current[p.id] = p.to_json()
        rows = sorted(current.values(), key=lambda d: int(d["id"]), reverse=True)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(rows, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return added


# ---- HTML -----------------------------------------------------------------

def _post(p: Post, root: str) -> str:
    parts = [f'<article class="post" id="p{p.id}">'
             f'<a class="who" href="{root}u/{html.escape(p.username.lower())}.html">@{html.escape(p.username)}</a>'
             f'<div class="text">{_linkify(p.text)}</div>']
    if p.images:
        parts.append('<div class="imgs">' + "".join(
            f'<a href="{html.escape(src)}"><img loading="lazy" src="{html.escape(src)}" alt=""></a>'
            for src in p.images[:4]) + "</div>")
    if p.quoted:
        q = p.quoted
        parts.append(f'<div class="quoted"><b>@{html.escape(q.username)}</b> '
                     f'<span class="meta">{_time(q.created_at)}</span>'
                     f'<div class="text">{_linkify(q.text)}</div></div>')
    reply = "返信 · " if p.is_reply else ""
    parts.append(f'<div class="foot">{reply}{_time(p.created_at)} · ♥ {p.likes:,} · RT {p.reposts:,} · '
                 f'<a href="{html.escape(p.url)}">Xで開く</a></div></article>')
    return "".join(parts)


def _by_day(posts: list[Post], root: str) -> str:
    if not posts:
        return '<p class="empty">投稿はまだありません。</p>'
    out, day = [], None
    for p in posts:
        d = p.created_at.astimezone(JST)
        key = d.strftime("%Y-%m-%d")
        if key != day:
            day = key
            out.append(f'<h2 class="day">{d:%Y/%m/%d}（{WEEKDAYS[d.weekday()]}）</h2>')
        out.append(_post(p, root))
    return "\n".join(out)


def _page(title: str, body: str, *, root: str, accounts: list[str], months: list[str],
          active: str = "", updated: datetime, site_title: str) -> str:
    chips = [f'<a href="{root}index.html" class="{"on" if active == "" else ""}">最新</a>']
    chips += [f'<a href="{root}u/{html.escape(a.lower())}.html" class="{"on" if active == a.lower() else ""}">'
              f'@{html.escape(a)}</a>' for a in accounts]
    month_links = " ".join(f'<a href="{root}m/{m}.html">{m}</a>' for m in months)
    return f"""<!doctype html>
<html lang="ja"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex, nofollow">
<title>{html.escape(title)}</title>
<link rel="stylesheet" href="{root}style.css">
</head><body><main>
<header><h1><a href="{root}index.html">{html.escape(site_title)}</a></h1>
<div class="meta">{html.escape(title)} · 最終更新 {updated.astimezone(JST):%Y/%m/%d %H:%M}</div></header>
<nav class="chips">{"".join(chips)}</nav>
{body}
<footer class="meta"><div class="months">アーカイブ: {month_links or "なし"}</div>
<p>各投稿の著作権は投稿者にあります。原文は「Xで開く」から確認できます。</p></footer>
</main></body></html>
"""


def build(repo: Path, accounts: list[str], *, now: datetime, site_title: str = "smallx") -> None:
    """data/ から全ページを作り直す。"""
    posts = sorted(load_all(repo), key=lambda p: int(p.id), reverse=True)
    names, seen = [], set()
    for n in accounts + sorted({p.username for p in posts}, key=str.lower):
        if n.lower() not in seen:
            seen.add(n.lower())
            names.append(n)
    months = sorted({_month(p) for p in posts}, reverse=True)
    common = dict(accounts=names, months=months, updated=now, site_title=site_title)

    (repo / "style.css").write_text(CSS.lstrip(), encoding="utf-8")
    (repo / ".nojekyll").write_text("", encoding="utf-8")
    (repo / "robots.txt").write_text("User-agent: *\nDisallow: /\n", encoding="utf-8")

    cutoff = now - timedelta(days=LATEST_DAYS)
    latest = [p for p in posts if p.created_at >= cutoff]
    (repo / "index.html").write_text(_page(f"最新{LATEST_DAYS}日間 · {len(latest)}件", _by_day(latest, ""),
                                           root="", active="", **common), encoding="utf-8")

    (repo / "u").mkdir(exist_ok=True)
    for name in names:
        mine = [p for p in posts if p.username.lower() == name.lower()][:PER_ACCOUNT]
        (repo / "u" / f"{name.lower()}.html").write_text(
            _page(f"@{name} · {len(mine)}件", _by_day(mine, "../"), root="../", active=name.lower(), **common),
            encoding="utf-8")

    (repo / "m").mkdir(exist_ok=True)
    for month in months:
        items = [p for p in posts if _month(p) == month]
        (repo / "m" / f"{month}.html").write_text(
            _page(f"{month} · {len(items)}件", _by_day(items, "../"), root="../", **common), encoding="utf-8")
