"""X の Web 版と同じ方法で、ログイン中のブラウザの Cookie を使って投稿を取る（非公式・無料）。

X の公式 API（有料）の代わり。twscrape（https://github.com/vladkens/twscrape）を使う。
- X の利用規約上は認められていない方法なので、Cookie を使ったアカウントが制限・凍結される可能性がある
- X の仕様変更で突然動かなくなることがある（twscrape の更新を待つ）
- 取得量を抑えるため、1回の実行で読むのは各アカウント最大 max_posts 件、アクセスの間に待ち時間を入れる
"""
from __future__ import annotations

import asyncio
import os
import random
import re
import tempfile
from datetime import datetime, timedelta, timezone

from .xapi import Post, XApiError

TCO_RE = re.compile(r"\s*https://t\.co/\w+\s*$")


def _media_urls(media) -> list[str]:
    urls = [p.url for p in getattr(media, "photos", []) or []]
    urls += [v.thumbnailUrl for v in getattr(media, "videos", []) or []]
    urls += [a.thumbnailUrl for a in getattr(media, "animated", []) or [] if getattr(a, "thumbnailUrl", None)]
    return urls


def to_post(t) -> Post:
    """twscrape の Tweet → Post。短縮URLを元に戻し、画像用の末尾 t.co は消す。"""
    text = t.rawContent or ""
    for link in t.links or []:
        if link.tcourl and link.url:
            text = text.replace(link.tcourl, link.url)
    images = _media_urls(t.media)
    if images or t.quotedTweet:
        text = TCO_RE.sub("", text)   # 画像・引用ポストを指す末尾の t.co
    username = t.user.username
    return Post(id=str(t.id), username=username, created_at=t.date, text=text.strip(),
                url=f"https://x.com/{username}/status/{t.id}", likes=t.likeCount or 0,
                reposts=t.retweetCount or 0, replies=t.replyCount or 0, quotes=t.quoteCount or 0,
                images=images, quoted=to_post(t.quotedTweet) if t.quotedTweet else None,
                is_reply=t.inReplyToTweetId is not None)


class CookieClient:
    """XClient（公式API）と同じ使い方ができるようにしたもの。"""

    def __init__(self, cookies: str, account: str = "me", api=None):
        self.reads = 0
        self.user_lookups = 0
        self._api = api
        self._cookies = cookies
        self._account = account
        self._tmp = None
        self._loop = asyncio.new_event_loop()   # twscrape の内部状態のため、全呼び出しで同じループを使う

    def _run(self, coro):
        return self._loop.run_until_complete(coro)

    async def _get_api(self):
        if self._api is None:
            from twscrape import API
            # アカウント情報は一時ファイルに置く（リポジトリには絶対に入れない）
            self._tmp = tempfile.TemporaryDirectory(prefix="xdigest_")
            self._api = API(os.path.join(self._tmp.name, "accounts.db"), raise_when_no_account=True)
            await self._api.pool.add_account_cookies(self._account, self._cookies)
        return self._api

    @staticmethod
    async def _pause():
        await asyncio.sleep(random.uniform(2, 5))   # 人がブラウザで見るくらいの間隔にする

    def lookup_users(self, usernames: list[str]) -> dict[str, str]:
        async def go():
            api = await self._get_api()
            out = {}
            for name in usernames:
                try:
                    user = await api.user_by_login(name)
                except Exception as e:
                    raise XApiError(0, f"ユーザー @{name} を取得できませんでした: {e}") from None
                if user:
                    out[name.lower()] = str(user.id)
                    self.user_lookups += 1
                await self._pause()
            return out
        return self._run(go())

    def user_posts(self, user_id: str, username: str, *, since_id: str | None, lookback_hours: int,
                   max_posts: int, include_replies: bool, include_retweets: bool,
                   now: datetime | None = None) -> list[Post]:
        now = now or datetime.now(timezone.utc)
        start = now - timedelta(hours=lookback_hours)

        async def go():
            api = await self._get_api()
            posts = []
            try:
                async for t in api.user_tweets(int(user_id), limit=max_posts):
                    self.reads += 1
                    if t.retweetedTweet is not None and not include_retweets:
                        continue
                    if (t.inReplyToUser is not None and t.inReplyToUser.username.lower() != username.lower()
                            and not include_replies):
                        continue   # 他人への返信は除く（自分のスレッドの続きは残す）
                    if since_id and int(t.id) <= int(since_id):
                        continue   # 前回までに取得済み（固定ポストもここで除かれる）
                    if not since_id and t.date < start:
                        continue
                    posts.append(to_post(t))
            except Exception as e:
                raise XApiError(0, f"@{username} の投稿を取得できませんでした: {e}") from None
            await self._pause()
            return posts
        return self._run(go())
