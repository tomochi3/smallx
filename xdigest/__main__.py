"""使い方:  X_BEARER_TOKEN=... python -m xdigest [--config xdigest.toml] [--build-only]"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone

from . import site
from .config import load_config
from .pipeline import run


def main(argv=None) -> None:
    ap = argparse.ArgumentParser(prog="xdigest", description="Xの投稿を原文のまま集めてサイトを更新する")
    ap.add_argument("--config", default="xdigest.toml")
    ap.add_argument("--build-only", action="store_true", help="X API を呼ばず、data/ からページだけ作り直す")
    args = ap.parse_args(argv)
    cfg = load_config(args.config)
    if args.build_only:
        site.build(cfg.root, cfg.accounts, now=datetime.now(timezone.utc), site_title=cfg.site_title)
        print("ページを作り直しました")
    else:
        run(cfg)


if __name__ == "__main__":
    main()
