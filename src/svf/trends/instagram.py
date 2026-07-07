"""Instagram リールのトレンド収集 (Instagram Graph API 使用).

ハッシュタグ検索でトップメディアを取得する。利用には
Instagram ビジネス/クリエイターアカウントと Graph API のアクセストークンが必要。
"""

from __future__ import annotations

import httpx

from svf.models import TrendItem
from svf.trends.base import TrendCollector, extract_hashtags

API_BASE = "https://graph.facebook.com/v21.0"


class InstagramCollector(TrendCollector):
    platform = "instagram"

    def __init__(self, access_token: str, business_account_id: str):
        if not access_token or not business_account_id:
            raise ValueError(
                "INSTAGRAM_ACCESS_TOKEN と INSTAGRAM_BUSINESS_ACCOUNT_ID を設定してください。"
            )
        self.token = access_token
        self.account_id = business_account_id

    def collect(self, query: str = "", limit: int = 20) -> list[TrendItem]:
        if not query:
            raise ValueError("Instagram はハッシュタグ検索のため query (キーワード) が必須です。")
        hashtag_id = self._find_hashtag_id(query)
        return self._top_media(hashtag_id, limit)

    def _find_hashtag_id(self, name: str) -> str:
        r = httpx.get(
            f"{API_BASE}/ig_hashtag_search",
            params={
                "user_id": self.account_id,
                "q": name.lstrip("#"),
                "access_token": self.token,
            },
            timeout=30,
        )
        r.raise_for_status()
        data = r.json().get("data", [])
        if not data:
            raise ValueError(f"ハッシュタグ '{name}' が見つかりません。")
        return data[0]["id"]

    def _top_media(self, hashtag_id: str, limit: int) -> list[TrendItem]:
        r = httpx.get(
            f"{API_BASE}/{hashtag_id}/top_media",
            params={
                "user_id": self.account_id,
                "fields": "id,caption,media_type,permalink,like_count,comments_count,timestamp",
                "limit": limit,
                "access_token": self.token,
            },
            timeout=30,
        )
        r.raise_for_status()
        items = []
        for m in r.json().get("data", []):
            if m.get("media_type") not in ("VIDEO", "REELS"):
                continue
            caption = m.get("caption", "") or ""
            items.append(
                TrendItem(
                    platform="instagram",
                    video_id=m["id"],
                    url=m.get("permalink", ""),
                    title=caption[:100],
                    description=caption[:500],
                    like_count=int(m.get("like_count", 0)),
                    comment_count=int(m.get("comments_count", 0)),
                    published_at=m.get("timestamp"),
                    hashtags=extract_hashtags(caption),
                )
            )
        items.sort(key=lambda i: i.like_count, reverse=True)
        return items
