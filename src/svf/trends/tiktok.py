"""TikTok のトレンド収集.

TikTok にはサードパーティ向けの公式トレンドAPIがないため、次の方針を取る:

1. TikTok Creative Center (https://ads.tiktok.com/business/creativecenter/) で
   トレンド動画のURLを目視で選び、`data/sources/tiktok_urls.txt` に1行1URLで貼る。
2. このコレクターが公式 oEmbed API (認証不要) でタイトル・作者などの
   メタデータを取得する。

再生数などの数値は oEmbed では取れないため、URLリストに
`<URL>\t<再生数>` の形式で任意に併記できる。
"""

from __future__ import annotations

import re
from pathlib import Path

import httpx

from svf.models import TrendItem
from svf.trends.base import TrendCollector, extract_hashtags

OEMBED_URL = "https://www.tiktok.com/oembed"


class TikTokCollector(TrendCollector):
    platform = "tiktok"

    def __init__(self, urls_file: Path):
        self.urls_file = urls_file

    def collect(self, query: str = "", limit: int = 20) -> list[TrendItem]:
        if not self.urls_file.exists():
            raise FileNotFoundError(
                f"{self.urls_file} がありません。TikTok Creative Center などで見つけた"
                "トレンド動画のURLを1行1件で記入してください。"
            )
        entries = self._read_entries()[:limit]
        items = []
        for url, view_count in entries:
            item = self._fetch_oembed(url)
            if item:
                item.view_count = view_count
                items.append(item)
        items.sort(key=lambda i: i.view_count, reverse=True)
        return items

    def _read_entries(self) -> list[tuple[str, int]]:
        entries = []
        for line in self.urls_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            parts = line.split("\t")
            url = parts[0].strip()
            views = int(parts[1].replace(",", "")) if len(parts) > 1 and parts[1].strip() else 0
            entries.append((url, views))
        return entries

    def _fetch_oembed(self, url: str) -> TrendItem | None:
        try:
            r = httpx.get(OEMBED_URL, params={"url": url}, timeout=20)
            r.raise_for_status()
            data = r.json()
        except Exception:
            return None
        title = data.get("title", "")
        m = re.search(r"/video/(\d+)", url)
        return TrendItem(
            platform="tiktok",
            video_id=m.group(1) if m else url,
            url=url,
            title=title,
            channel=data.get("author_name", ""),
            hashtags=extract_hashtags(title),
        )
