"""X API v2 から投稿を取ってくる。

課金（従量課金）を抑えるため、
- ユーザー名→ユーザーIDの変換結果は state に保存して、2回目以降は呼ばない
- 前回取得した最新の投稿ID（since_id）以降だけを取る
- 1アカウントあたりの件数に上限を付ける
"""
from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

API = "https://api.x.com/2"
TWEET_FIELDS = "created_at,public_metrics,note_tweet,entities,referenced_tweets,attachments,author_id"
EXPANSIONS = "attachments.media_keys,referenced_tweets.id,referenced_tweets.id.author_id"
MEDIA_FIELDS = "url,preview_image_url,type,width,height"
USER_FIELDS = "name,username,profile_image_url"


class XApiError(RuntimeError):
    def __init__(self, status: int, message: str):
        self.status = status
        super().__init__(f"X API エラー {status}: {message}")


@dataclass
class Post:
    id: str
    username: str
    created_at: datetime
    text: str
    url: str
    likes: int = 0
    reposts: int = 0
    replies: int = 0
    quotes: int = 0
    images: list[str] = field(default_factory=list)
    quoted: "Post | None" = None
    is_reply: bool = False

    def to_json(self) -> dict:
        d = {k: getattr(self, k) for k in ("id", "username", "text", "url", "likes", "reposts",
                                             "replies", "quotes", "images", "is_reply")}
        d["created_at"] = self.created_at.isoformat()
        d["quoted"] = self.quoted.to_json() if self.quoted else None
        return d

    @classmethod
    def from_json(cls, d: dict) -> "Post":
        d = dict(d)
        d["created_at"] = datetime.fromisoformat(d["created_at"])
        d["quoted"] = cls.from_json(d["quoted"]) if d.get("quoted") else None
        known = set(cls.__dataclass_fields__)
        return cls(**{k: v for k, v in d.items() if k in known})


def _get(path: str, params: dict, token: str, opener=urllib.request.urlopen) -> dict:
    url = f"{API}{path}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}",
                                               "User-Agent": "xdigest/0.1"})
    try:
        with opener(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")[:500]
        raise XApiError(e.code, body) from None


def expand_text(tweet: dict) -> str:
    """長文投稿（note_tweet）を優先し、t.co の短縮URLを元のURLに戻す。"""
    note = tweet.get("note_tweet") or {}
    text = note.get("text") or tweet.get("text", "")
    entities = note.get("entities") if note.get("text") else tweet.get("entities")
    for u in (entities or {}).get("urls", []):
        short, expanded = u.get("url"), u.get("expanded_url") or u.get("unwound_url")
        if not short:
            continue
        # 画像・動画の t.co はPDFには画像で載せるので本文からは消す
        if "/photo/" in (expanded or "") or "/video/" in (expanded or ""):
            text = text.replace(short, "")
        elif expanded:
            text = text.replace(short, expanded)
    return text.strip()


def _parse_time(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def build_posts(data: dict, username: str) -> list[Post]:
    includes = data.get("includes") or {}
    media = {m["media_key"]: m for m in includes.get("media", [])}
    users = {u["id"]: u["username"] for u in includes.get("users", [])}
    ref_tweets = {t["id"]: t for t in includes.get("tweets", [])}

    def make(t: dict, uname: str) -> Post:
        m = t.get("public_metrics") or {}
        imgs = []
        for key in (t.get("attachments") or {}).get("media_keys", []):
            item = media.get(key) or {}
            src = item.get("url") or item.get("preview_image_url")
            if src:
                imgs.append(src)
        refs = t.get("referenced_tweets") or []
        return Post(id=t["id"], username=uname, created_at=_parse_time(t["created_at"]),
                    text=expand_text(t), url=f"https://x.com/{uname}/status/{t['id']}",
                    likes=m.get("like_count", 0), reposts=m.get("retweet_count", 0),
                    replies=m.get("reply_count", 0), quotes=m.get("quote_count", 0),
                    images=imgs, is_reply=any(r.get("type") == "replied_to" for r in refs))

    posts = []
    for t in data.get("data", []):
        post = make(t, username)
        for r in t.get("referenced_tweets") or []:
            q = ref_tweets.get(r.get("id"))
            if r.get("type") == "quoted" and q and q.get("created_at"):
                post.quoted = make(q, users.get(q.get("author_id"), "i"))
        posts.append(post)
    return posts


class XClient:
    def __init__(self, token: str, opener=urllib.request.urlopen):
        self.token = token
        self.opener = opener
        self.reads = 0          # 課金の目安（返ってきた投稿数）
        self.user_lookups = 0

    def lookup_users(self, usernames: list[str]) -> dict[str, str]:
        """ユーザー名 → ユーザーID。見つからない名前は含めない。"""
        out = {}
        for i in range(0, len(usernames), 100):
            chunk = usernames[i:i + 100]
            data = _get("/users/by", {"usernames": ",".join(chunk), "user.fields": USER_FIELDS},
                        self.token, self.opener)
            for u in data.get("data", []):
                out[u["username"].lower()] = u["id"]
                self.user_lookups += 1
        return out

    def user_posts(self, user_id: str, username: str, *, since_id: str | None, lookback_hours: int,
                   max_posts: int, include_replies: bool, include_retweets: bool,
                   now: datetime | None = None) -> list[Post]:
        exclude = [x for x, inc in (("replies", include_replies), ("retweets", include_retweets)) if not inc]
        params = {"max_results": max(5, min(100, max_posts)), "tweet.fields": TWEET_FIELDS,
                  "expansions": EXPANSIONS, "media.fields": MEDIA_FIELDS, "user.fields": "username"}
        if exclude:
            params["exclude"] = ",".join(exclude)
        if since_id:
            params["since_id"] = since_id
        else:
            now = now or datetime.now(timezone.utc)
            start = now - timedelta(hours=lookback_hours)
            params["start_time"] = start.strftime("%Y-%m-%dT%H:%M:%SZ")
        posts: list[Post] = []
        while len(posts) < max_posts:
            data = _get(f"/users/{user_id}/tweets", params, self.token, self.opener)
            page = build_posts(data, username)
            self.reads += len(page)
            posts.extend(page)
            token = (data.get("meta") or {}).get("next_token")
            if not token or not page:
                break
            params["pagination_token"] = token
        return posts[:max_posts]
