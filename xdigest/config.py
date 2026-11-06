"""設定（xdigest.toml）と秘密情報（環境変数）の読み込み。"""
from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Config:
    accounts: list[str]
    root: Path = Path(".")                # サイト（このリポジトリ）のルート
    site_title: str = "smallx"
    lookback_hours: int = 24
    max_posts_per_account: int = 40
    include_replies: bool = False
    include_retweets: bool = False

    @property
    def state_file(self) -> Path:
        return self.root / "data" / "state.json"


def load_config(path: Path | str = "xdigest.toml") -> Config:
    path = Path(path)
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise SystemExit(f"設定ファイルがありません: {path}") from None
    known = set(Config.__dataclass_fields__) - {"root"}
    unknown = set(raw) - known
    if unknown:
        print(f"知らない設定項目は無視します: {', '.join(sorted(unknown))}")
    kwargs = {k: v for k, v in raw.items() if k in known}
    accounts = [a.strip().lstrip("@") for a in kwargs.get("accounts", []) if a.strip()]
    if not accounts:
        raise SystemExit("accounts に1つ以上のXアカウント（@なしのユーザー名）を書いてください。")
    kwargs["accounts"] = accounts
    return Config(**kwargs, root=path.parent)


def bearer_token() -> str:
    token = os.environ.get("X_BEARER_TOKEN", "").strip()
    if not token:
        raise SystemExit("X_BEARER_TOKEN がありません。GitHub の Settings → Secrets and variables → Actions に"
                         " X_BEARER_TOKEN を登録してください。")
    return token
