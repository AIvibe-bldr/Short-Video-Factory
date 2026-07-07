"""パイプライン全体で使うデータモデル."""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field

Platform = Literal["youtube", "tiktok", "instagram"]


class TrendItem(BaseModel):
    """収集したトレンド動画1件のメタデータ."""

    platform: Platform
    video_id: str
    url: str
    title: str = ""
    description: str = ""
    channel: str = ""
    view_count: int = 0
    like_count: int = 0
    comment_count: int = 0
    published_at: Optional[str] = None
    duration_seconds: Optional[int] = None
    hashtags: list[str] = Field(default_factory=list)
    transcript: Optional[str] = None  # 取得できた場合のみ
    fetched_at: str = Field(default_factory=lambda: datetime.now().isoformat())


class TrendInsights(BaseModel):
    """Claudeがトレンド動画群から抽出した「勝ちパターン」."""

    analyzed_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    source_count: int = 0
    platforms: list[str] = Field(default_factory=list)
    hooks: list[str] = Field(default_factory=list)  # 冒頭2秒で使われている引きのパターン
    structures: list[str] = Field(default_factory=list)  # 動画全体の構成パターン
    visual_styles: list[str] = Field(default_factory=list)  # 映像表現の傾向
    audio_trends: list[str] = Field(default_factory=list)  # 音・BGM・話し方の傾向
    engagement_tactics: list[str] = Field(default_factory=list)  # コメント/保存を促す仕掛け
    hashtag_patterns: list[str] = Field(default_factory=list)
    summary: str = ""  # 全体の要約


class Scene(BaseModel):
    """台本の1シーン."""

    index: int
    start_seconds: float
    end_seconds: float
    narration: str = ""  # ナレーション/セリフ (空なら無音・環境音)
    on_screen_text: str = ""  # 画面に載せるテロップ
    visual_direction: str = ""  # 映像の指示 (撮影/生成/素材選択の指針)
    product_visibility: Literal["none", "subtle", "featured"] = "none"


class VideoScript(BaseModel):
    """生成された1本分のショート動画台本."""

    script_id: str
    style: str  # 使用したスタイルプリセット名
    language: str = "ja"
    title: str = ""  # 投稿タイトル案
    hook: str = ""  # 冒頭の引き (どのトレンドフックを使ったか)
    total_seconds: float = 30.0
    scenes: list[Scene] = Field(default_factory=list)
    caption: str = ""  # 投稿キャプション案
    hashtags: list[str] = Field(default_factory=list)
    trend_basis: str = ""  # どのトレンド要素を組み込んだかの説明
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())


class ProduceResult(BaseModel):
    """動画生成の結果."""

    script_id: str
    video_path: str
    audio_path: Optional[str] = None
    duration_seconds: float = 0.0
