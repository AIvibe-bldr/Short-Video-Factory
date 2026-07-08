"""Claude によるトレンド動画の要点抽出."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import anthropic
from pydantic import BaseModel, Field

from svf.models import TrendInsights, TrendItem

SYSTEM_PROMPT = """\
あなたはショート動画マーケティングの分析専門家です。
YouTube Shorts / TikTok / Instagram リールでいま再生数を伸ばしている動画群の
メタデータ(タイトル・説明・統計・字幕)から、「なぜ伸びているのか」を構造的に
分解し、これから商品紹介ショート動画を作る人がそのまま使える形で要点を抽出します。

分析の観点:
- フック: 冒頭0〜2秒で視聴者を止める仕掛け(言葉・映像・音)
- 構成: 動画全体の流れのパターン(問題提起→解決、Before/After、リスト形式 など)
- 映像表現: カット割り、テロップの使い方、画角、色味などの傾向
- 音: BGM・効果音・話し方のテンポの傾向
- エンゲージメント: コメント・保存・シェアを誘発している仕掛け
- ハッシュタグ: 付け方のパターン

推測で埋めず、与えられたデータから読み取れる範囲で具体的に書いてください。
各項目は「そのまま台本制作の指示として使える」粒度で書いてください。
"""


def select_curated(items: list[TrendItem]) -> list[TrendItem]:
    """人間がgood評価した動画のみを分析対象として返す.

    インプレッション数・再生数だけを基準に学習すると炎上・釣り構成が
    「勝ちパターン」として強化されてしまうため、`svf curate` で
    参考にしてよいか判定されていない動画は分析に使わせない。
    """
    reviewed = [i for i in items if i.human_rating is not None]
    if not reviewed:
        raise RuntimeError(
            "トレンド動画がまだ評価されていません。炎上・釣り構成を学習しないために、"
            "先に `svf curate` で参考にしてよい動画かどうかを判定してください。"
        )
    usable = [i for i in reviewed if i.human_rating == "good"]
    if not usable:
        raise RuntimeError(
            "good判定の動画がありません。bad判定の動画からは学習しません。"
            "`svf research` で対象を広げるか、判定を見直してください。"
        )
    return usable


class _InsightsOutput(BaseModel):
    """Claudeに出力させる構造 (structured outputs 用)."""

    hooks: list[str] = Field(description="冒頭の引きのパターン。具体的な言い回し例も含める")
    structures: list[str] = Field(description="動画構成のパターン")
    visual_styles: list[str] = Field(description="映像表現の傾向")
    audio_trends: list[str] = Field(description="音・話し方の傾向")
    engagement_tactics: list[str] = Field(description="コメント・保存を促す仕掛け")
    hashtag_patterns: list[str] = Field(description="ハッシュタグの付け方のパターン")
    summary: str = Field(description="全体の傾向の要約 (300字以内)")


class TrendAnalyzer:
    def __init__(self, api_key: str = "", model: str = "claude-opus-4-8"):
        self.client = anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()
        self.model = model

    def analyze(self, items: list[TrendItem]) -> TrendInsights:
        """トレンド動画群から勝ちパターンを抽出する."""
        if not items:
            raise ValueError("分析対象のトレンドデータがありません。")

        usable = select_curated(items)
        payload = [self._item_summary(i) for i in usable]
        response = self.client.messages.parse(
            model=self.model,
            max_tokens=16000,
            thinking={"type": "adaptive"},
            system=SYSTEM_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": (
                        "以下は現在再生数を伸ばしているショート動画のデータです。"
                        "要点を抽出してください。\n\n"
                        + json.dumps(payload, ensure_ascii=False, indent=1)
                    ),
                }
            ],
            output_format=_InsightsOutput,
        )
        out: _InsightsOutput = response.parsed_output
        return TrendInsights(
            source_count=len(usable),
            platforms=sorted({i.platform for i in usable}),
            **out.model_dump(),
        )

    @staticmethod
    def _item_summary(item: TrendItem) -> dict:
        return {
            "platform": item.platform,
            "title": item.title,
            "description": item.description[:300],
            "views": item.view_count,
            "likes": item.like_count,
            "comments": item.comment_count,
            "duration_sec": item.duration_seconds,
            "hashtags": item.hashtags[:10],
            "transcript": (item.transcript or "")[:1500],
        }


def save_insights(insights: TrendInsights, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = out_dir / f"insights_{stamp}.json"
    path.write_text(insights.model_dump_json(indent=2), encoding="utf-8")
    return path


def load_latest_insights(insights_dir: Path) -> TrendInsights:
    files = sorted(insights_dir.glob("insights_*.json"))
    if not files:
        raise FileNotFoundError(
            f"{insights_dir} に分析結果がありません。先に `svf analyze` を実行してください。"
        )
    return TrendInsights(**json.loads(files[-1].read_text(encoding="utf-8")))
