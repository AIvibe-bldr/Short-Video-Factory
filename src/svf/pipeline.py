"""収集 → 分析 → 台本 → 動画生成 のパイプライン統括."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from svf.analysis.analyzer import TrendAnalyzer, load_latest_insights, save_insights
from svf.config import (
    ASSETS_DIR,
    DATA_DIR,
    OUTPUT_DIR,
    Product,
    Settings,
    StylePreset,
    load_product,
    load_style,
)
from svf.media.assemble import VideoAssembler
from svf.media.visuals import VisualPicker
from svf.models import ProduceResult, TrendInsights, TrendItem, VideoScript
from svf.script.generator import ScriptGenerator, save_scripts
from svf.trends import InstagramCollector, TikTokCollector, YouTubeCollector
from svf.trends.base import load_latest_trends, save_trends

TRENDS_DIR = DATA_DIR / "trends"
INSIGHTS_DIR = DATA_DIR / "insights"
SCRIPTS_DIR = DATA_DIR / "scripts"
AUDIO_DIR = DATA_DIR / "audio"
SOURCES_DIR = DATA_DIR / "sources"


class Pipeline:
    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings or Settings.load()

    # ---- 1. トレンド収集 ----
    def research(
        self, platforms: list[str], query: str = "", limit: int = 20
    ) -> tuple[list[TrendItem], Path]:
        items: list[TrendItem] = []
        errors: list[str] = []
        for platform in platforms:
            try:
                items.extend(self._collector(platform).collect(query=query, limit=limit))
            except Exception as e:
                errors.append(f"{platform}: {e}")
        if not items:
            raise RuntimeError(
                "トレンドを1件も収集できませんでした。\n" + "\n".join(errors)
            )
        path = save_trends(items, TRENDS_DIR)
        if errors:
            print("一部プラットフォームでエラー:", *errors, sep="\n  ")
        return items, path

    def _collector(self, platform: str):
        s = self.settings
        if platform == "youtube":
            return YouTubeCollector(s.youtube_api_key, region_code=s.region_code)
        if platform == "tiktok":
            return TikTokCollector(SOURCES_DIR / "tiktok_urls.txt")
        if platform == "instagram":
            return InstagramCollector(
                s.instagram_access_token, s.instagram_business_account_id
            )
        raise ValueError(f"未対応のプラットフォーム: {platform}")

    # ---- 2. 要点抽出 ----
    def analyze(self, items: Optional[list[TrendItem]] = None) -> tuple[TrendInsights, Path]:
        if items is None:
            items = load_latest_trends(TRENDS_DIR)
        analyzer = TrendAnalyzer(
            api_key=self.settings.anthropic_api_key, model=self.settings.claude_model
        )
        insights = analyzer.analyze(items)
        path = save_insights(insights, INSIGHTS_DIR)
        return insights, path

    # ---- 3. 台本生成 ----
    def write_scripts(
        self,
        style_name: str,
        count: int = 1,
        product: Optional[Product] = None,
        insights: Optional[TrendInsights] = None,
    ) -> tuple[list[VideoScript], list[Path]]:
        product = product or load_product()
        insights = insights or load_latest_insights(INSIGHTS_DIR)
        style = load_style(style_name)
        generator = ScriptGenerator(
            api_key=self.settings.anthropic_api_key, model=self.settings.claude_model
        )
        scripts = generator.generate(product, style, insights, count=count)
        paths = save_scripts(scripts, SCRIPTS_DIR)
        return scripts, paths

    # ---- 4. 動画生成 ----
    def produce(
        self, script: VideoScript, tts_provider: str = "edge"
    ) -> ProduceResult:
        style = load_style(script.style)
        s = self.settings
        assembler = VideoAssembler(
            width=s.video_width,
            height=s.video_height,
            fps=s.fps,
            tts_provider=tts_provider,
            tts_settings=self._tts_settings(tts_provider),
        )
        picker = VisualPicker(ASSETS_DIR / "broll", ASSETS_DIR / "images")
        return assembler.produce(
            script,
            picker,
            audio_dir=AUDIO_DIR,
            output_dir=OUTPUT_DIR,
            tts_voice=style.tts_voice,
        )

    def _tts_settings(self, provider: str) -> dict:
        if provider == "voicevox":
            return {"voicevox_url": self.settings.voicevox_url}
        if provider == "elevenlabs":
            return {"elevenlabs_api_key": self.settings.elevenlabs_api_key}
        return {}

    # ---- 一括実行 ----
    def run_all(
        self,
        platforms: list[str],
        query: str,
        style_name: str,
        count: int,
        limit: int = 20,
        tts_provider: str = "edge",
    ) -> list[ProduceResult]:
        items, _ = self.research(platforms, query=query, limit=limit)
        insights, _ = self.analyze(items)
        scripts, _ = self.write_scripts(style_name, count=count, insights=insights)
        return [self.produce(s, tts_provider=tts_provider) for s in scripts]
