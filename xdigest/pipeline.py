"""1回分の処理: X API から新しい投稿を取得 → data/ に追記 → 全ページを作り直す。"""
from __future__ import annotations

import json
import os
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from . import site
from .config import Config, bearer_token
from .xapi import XApiError, XClient

POST_PRICE_USD = 0.005   # 他人の投稿1件あたりの目安（X API 従量課金）。正確な単価は developer console で確認


def load_state(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def save_state(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def notify(message: str, *, title: str = "smallx", opener=urllib.request.urlopen) -> None:
    """環境変数 NTFY_TOPIC があれば ntfy でスマホに通知する（任意）。"""
    topic = os.environ.get("NTFY_TOPIC", "").strip()
    if not topic:
        return
    server = os.environ.get("NTFY_SERVER", "https://ntfy.sh").rstrip("/")
    headers = {"Title": title.encode("utf-8"), "Tags": "newspaper"}
    if os.environ.get("SITE_URL"):
        headers["Click"] = os.environ["SITE_URL"]
    try:
        opener(urllib.request.Request(f"{server}/{topic}", data=message.encode("utf-8"), headers=headers),
               timeout=30).close()
    except Exception as e:  # 通知の失敗で本体を止めない
        print(f"通知に失敗しました: {e}")


def run(cfg: Config, *, client: XClient | None = None, now: datetime | None = None) -> int:
    """新しく追加した投稿数を返す。X API のエラーがあれば最後に SystemExit で失敗させる（Actions で気づけるように）。"""
    now = now or datetime.now(timezone.utc)
    state = load_state(cfg.state_file)
    client = client or XClient(bearer_token())

    ids: dict = state.setdefault("user_ids", {})
    missing = [a for a in cfg.accounts if a.lower() not in ids]
    errors = []
    if missing:
        try:
            found = client.lookup_users(missing)
        except XApiError as e:
            raise SystemExit(f"ユーザー検索に失敗しました: {e}") from None
        ids.update(found)
        for a in missing:
            if a.lower() not in found:
                errors.append(f"@{a} が見つかりませんでした（名前の綴りを確認してください）")

    since: dict = state.setdefault("since_id", {})
    posts = []
    for name in cfg.accounts:
        uid = ids.get(name.lower())
        if not uid:
            continue
        try:
            got = client.user_posts(uid, name, since_id=since.get(name.lower()),
                                    lookback_hours=cfg.lookback_hours, max_posts=cfg.max_posts_per_account,
                                    include_replies=cfg.include_replies, include_retweets=cfg.include_retweets,
                                    now=now)
        except XApiError as e:
            errors.append(f"@{name}: {e}")
            if e.status in (401, 402, 403, 429):
                break   # 認証切れ・クレジット切れ・レート制限は他のアカウントでも同じなので止める
            continue
        print(f"@{name}: {len(got)}件")
        posts.extend(got)
        if got:
            since[name.lower()] = max(got, key=lambda p: int(p.id)).id

    print(f"取得した投稿 {client.reads}件（概算 ${client.reads * POST_PRICE_USD:.3f}）")
    added = site.merge(cfg.root, posts)
    site.build(cfg.root, cfg.accounts, now=now, site_title=cfg.site_title)
    state["last_run"] = now.isoformat()
    save_state(cfg.state_file, state)
    print(f"サイトを更新しました（+{added}件）")

    if errors:
        for e in errors:
            print(e)
        notify("\n".join(errors), title="smallx: エラー")
        raise SystemExit(1)   # 取れた分は保存済み。ワークフローは commit してから失敗として表示する
    if added:
        notify(f"{added}件の新しい投稿")
    return added
