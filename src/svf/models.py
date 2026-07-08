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

    # 人間によるレビュー (分析対象にしてよいか)。
    # インプレッション数だけで学習すると炎上・釣り構成が強化されてしまうため、
    # `svf curate` でこの動画を参考にしてよいか毎回人間が判定する。
    human_rating: Optional[Literal["good", "bad"]] = None
    human_notes: str = ""  # bad判定の理由など


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

    # フィードバックループ用
    variant: Literal["exploit", "explore"] = "exploit"  # 8割exploit(勝ちパターン踏襲) / 2割explore(新規)
    pattern_tag: str = ""  # フック・構成を表す短いラベル (実績集計のキー)
    status: Literal["draft", "published", "rejected"] = "draft"  # 人間の最終判断


class ProduceResult(BaseModel):
    """動画生成の結果."""

    script_id: str
    video_path: str
    audio_path: Optional[str] = None
    duration_seconds: float = 0.0


class PublishDecision(BaseModel):
    """「実際にこの動画を投稿するか」の人間による最終判断. ツールは自動投稿しない."""

    script_id: str
    decision: Literal["published", "rejected"]
    note: str = ""
    decided_at: str = Field(default_factory=lambda: datetime.now().isoformat())


class PerformanceRecord(BaseModel):
    """投稿後の実績 (インプレッション数など) + 人間による質の評価.

    quality_rating が "bad" (例: 誤解を招く煽り・炎上狙いで伸びただけ) の実績は、
    数値がどれだけ良くても次の台本生成の「勝ちパターン」強化からは除外する。
    """

    id: str
    script_id: str
    platform: Platform
    posted_url: str = ""
    impressions: int = 0
    views: int = 0
    likes: int = 0
    comments: int = 0
    saves: int = 0
    shares: int = 0
    quality_rating: Literal["good", "bad"]
    quality_notes: str = ""
    recorded_at: str = Field(default_factory=lambda: datetime.now().isoformat())

    def engagement_rate(self) -> float:
        """反応数 / (視聴数 or インプレッション数)."""
        base = self.views or self.impressions or 1
        return (self.likes + self.comments + self.saves + self.shares) / base


class PatternStat(BaseModel):
    """スタイル×パターンタグごとの実績集計 (good評価のみで平均を算出)."""

    pattern_tag: str
    style: str
    sample_size: int = 0  # good+bad の総数
    good_count: int = 0
    bad_count: int = 0
    avg_engagement_rate: float = 0.0  # good評価のみの平均
    last_used: str = ""
