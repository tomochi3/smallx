import io
import json
import urllib.parse
from datetime import datetime, timezone

import pytest

from xdigest import pipeline, site
from xdigest.config import load_config
from xdigest.xapi import Post, XClient, build_posts, expand_text

NOW = datetime(2026, 11, 6, 22, 0, tzinfo=timezone.utc)

TIMELINE = {
    "data": [
        {"id": "200", "created_at": "2026-11-06T10:00:00.000Z", "text": "新しい論文 https://t.co/abc https://t.co/pic",
         "entities": {"urls": [
             {"url": "https://t.co/abc", "expanded_url": "https://arxiv.org/abs/2611.00001"},
             {"url": "https://t.co/pic", "expanded_url": "https://x.com/hillbig/status/200/photo/1"}]},
         "attachments": {"media_keys": ["3_1"]},
         "public_metrics": {"like_count": 120, "retweet_count": 30},
         "referenced_tweets": [{"type": "quoted", "id": "150"}]},
        {"id": "201", "created_at": "2026-11-06T12:00:00.000Z", "text": "短い本文…",
         "note_tweet": {"text": "長文の全文 <script>"}, "public_metrics": {}},
    ],
    "includes": {
        "media": [{"media_key": "3_1", "type": "photo", "url": "https://pbs.twimg.com/media/a.jpg"}],
        "tweets": [{"id": "150", "created_at": "2026-11-05T00:00:00.000Z", "text": "引用元", "author_id": "9"}],
        "users": [{"id": "9", "username": "someone"}],
    },
    "meta": {"result_count": 2},
}


class FakeResp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *a):
        self.close()


class FakeX:
    def __init__(self, status=None):
        self.calls = []
        self.status = status

    def __call__(self, req, timeout=None):
        import urllib.error
        url = urllib.parse.urlsplit(req.full_url)
        self.calls.append((url.path, urllib.parse.parse_qs(url.query)))
        if url.path.endswith("/users/by"):
            return FakeResp(json.dumps({"data": [{"id": "42", "username": "hillbig"}]}).encode())
        if self.status:
            raise urllib.error.HTTPError(req.full_url, self.status, "x", {}, io.BytesIO(b"credits depleted"))
        return FakeResp(json.dumps(TIMELINE).encode())


def make_cfg(tmp_path, accounts='["hillbig"]'):
    (tmp_path / "xdigest.toml").write_text(f"accounts = {accounts}\n", encoding="utf-8")
    return load_config(tmp_path / "xdigest.toml")


def test_expand_text_restores_urls_and_drops_media_links():
    assert expand_text(TIMELINE["data"][0]) == "新しい論文 https://arxiv.org/abs/2611.00001"
    assert expand_text(TIMELINE["data"][1]) == "長文の全文 <script>"


def test_build_posts_images_and_quotes():
    posts = build_posts(TIMELINE, "hillbig")
    assert posts[0].images == ["https://pbs.twimg.com/media/a.jpg"]
    assert posts[0].quoted.username == "someone"
    assert posts[0].url == "https://x.com/hillbig/status/200"


def test_post_json_roundtrip():
    p = build_posts(TIMELINE, "hillbig")[0]
    assert Post.from_json(json.loads(json.dumps(p.to_json()))) == p


def test_run_builds_site_and_uses_since_id(tmp_path):
    cfg = make_cfg(tmp_path)
    fake = FakeX()
    assert pipeline.run(cfg, client=XClient("t", opener=fake), now=NOW) == 2
    first = [c for c in fake.calls if "tweets" in c[0]][0][1]
    assert "start_time" in first and "since_id" not in first
    assert first["exclude"] == ["replies,retweets"]

    state = json.loads((tmp_path / "data/state.json").read_text())
    assert state["user_ids"] == {"hillbig": "42"} and state["since_id"] == {"hillbig": "201"}
    data = json.loads((tmp_path / "data/posts/2026-11.json").read_text())
    assert [d["id"] for d in data] == ["201", "200"]

    index = (tmp_path / "index.html").read_text()
    assert "長文の全文 &lt;script&gt;" in index and "<script>" not in index
    assert 'href="u/hillbig.html"' in index and "noindex" in index
    assert '<a href="https://arxiv.org/abs/2611.00001">' in index
    assert "引用元" in (tmp_path / "m/2026-11.html").read_text()

    fake2 = FakeX()
    assert pipeline.run(cfg, client=XClient("t", opener=fake2), now=NOW) == 0   # 同じ投稿は増えない
    assert not any(c[0].endswith("/users/by") for c in fake2.calls)            # ユーザー検索は初回だけ
    second = [c for c in fake2.calls if "tweets" in c[0]][0][1]
    assert second["since_id"] == ["201"] and "start_time" not in second
    assert len(json.loads((tmp_path / "data/posts/2026-11.json").read_text())) == 2


def test_api_error_saves_pages_then_fails(tmp_path):
    cfg = make_cfg(tmp_path)
    with pytest.raises(SystemExit):
        pipeline.run(cfg, client=XClient("t", opener=FakeX(status=402)), now=NOW)
    assert (tmp_path / "index.html").exists()
    assert json.loads((tmp_path / "data/state.json").read_text())["user_ids"] == {"hillbig": "42"}


def test_empty_account_page(tmp_path):
    cfg = make_cfg(tmp_path, '["hillbig", "Other"]')
    site.build(cfg.root, cfg.accounts, now=NOW)
    assert "投稿はまだありません" in (tmp_path / "u/other.html").read_text()


def test_config_requires_accounts_and_token(tmp_path, monkeypatch):
    with pytest.raises(SystemExit):
        make_cfg(tmp_path, "[]")
    cfg = make_cfg(tmp_path, '["@hillbig", " "]')
    assert cfg.accounts == ["hillbig"]
    monkeypatch.delenv("X_BEARER_TOKEN", raising=False)
    with pytest.raises(SystemExit):
        pipeline.run(cfg, now=NOW)
