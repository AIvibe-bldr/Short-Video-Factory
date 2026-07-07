"""YouTube Shorts のトレンド収集 (YouTube Data API v3 使用)."""

from __future__ import annotations

import re

import httpx

from svf.models import TrendItem
from svf.trends.base import TrendCollector, extract_hashtags

API_BASE = "https://www.googleapis.com/youtube/v3"


def _parse_iso8601_duration(duration: str) -> int:
    """ISO 8601 の動画長 (PT1M30S など) を秒に変換する."""
    m = re.match(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", duration or "")
    if not m:
        return 0
    hours, minutes, seconds = (int(g) if g else 0 for g in m.groups())
    return hours * 3600 + minutes * 60 + seconds


class YouTubeCollector(TrendCollector):
    platform = "youtube"

    def __init__(self, api_key: str, region_code: str = "JP", fetch_transcripts: bool = True):
        if not api_key:
            raise ValueError("YOUTUBE_API_KEY が設定されていません。")
        self.api_key = api_key
        self.region_code = region_code
        self.fetch_transcripts = fetch_transcripts

    def collect(self, query: str = "", limit: int = 20) -> list[TrendItem]:
        video_ids = self._search_short_ids(query, limit)
        if not video_ids:
            return []
        items = self._fetch_details(video_ids)
        # ショート動画 (3分以内) のみ・再生数順
        items = [i for i in items if (i.duration_seconds or 0) <= 180]
        items.sort(key=lambda i: i.view_count, reverse=True)
        items = items[:limit]
        if self.fetch_transcripts:
            for item in items:
                item.transcript = self._try_transcript(item.video_id)
        return items

    def _search_short_ids(self, query: str, limit: int) -> list[str]:
        """検索APIで直近の人気ショート動画IDを取得する."""
        params = {
            "key": self.api_key,
            "part": "id",
            "type": "video",
            "videoDuration": "short",  # 4分未満
            "order": "viewCount",
            "publishedAfter": self._recent_window(),
            "regionCode": self.region_code,
            "maxResults": min(limit * 2, 50),
            "q": query or "shorts",
        }
        r = httpx.get(f"{API_BASE}/search", params=params, timeout=30)
        r.raise_for_status()
        return [item["id"]["videoId"] for item in r.json().get("items", [])]

    def _fetch_details(self, video_ids: list[str]) -> list[TrendItem]:
        params = {
            "key": self.api_key,
            "part": "snippet,statistics,contentDetails",
            "id": ",".join(video_ids),
        }
        r = httpx.get(f"{API_BASE}/videos", params=params, timeout=30)
        r.raise_for_status()
        items = []
        for v in r.json().get("items", []):
            snippet = v.get("snippet", {})
            stats = v.get("statistics", {})
            desc = snippet.get("description", "")
            items.append(
                TrendItem(
                    platform="youtube",
                    video_id=v["id"],
                    url=f"https://www.youtube.com/shorts/{v['id']}",
                    title=snippet.get("title", ""),
                    description=desc[:500],
                    channel=snippet.get("channelTitle", ""),
                    view_count=int(stats.get("viewCount", 0)),
                    like_count=int(stats.get("likeCount", 0)),
                    comment_count=int(stats.get("commentCount", 0)),
                    published_at=snippet.get("publishedAt"),
                    duration_seconds=_parse_iso8601_duration(
                        v.get("contentDetails", {}).get("duration", "")
                    ),
                    hashtags=extract_hashtags(snippet.get("title", "") + " " + desc),
                )
            )
        return items

    def _try_transcript(self, video_id: str) -> str | None:
        """字幕が取得できれば返す (分析の精度が大きく上がる)."""
        try:
            from youtube_transcript_api import YouTubeTranscriptApi

            transcripts = YouTubeTranscriptApi.get_transcript(
                video_id, languages=["ja", "en"]
            )
            text = " ".join(t["text"] for t in transcripts)
            return text[:2000]
        except Exception:
            return None

    @staticmethod
    def _recent_window() -> str:
        """直近14日をトレンドの対象期間とする."""
        from datetime import datetime, timedelta, timezone

        dt = datetime.now(timezone.utc) - timedelta(days=14)
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
