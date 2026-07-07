"""トレンドショート動画の収集."""

from svf.trends.base import TrendCollector
from svf.trends.youtube import YouTubeCollector
from svf.trends.tiktok import TikTokCollector
from svf.trends.instagram import InstagramCollector

__all__ = [
    "TrendCollector",
    "YouTubeCollector",
    "TikTokCollector",
    "InstagramCollector",
]
