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
from svf.feedback.tracker import (
    latest_decision,
    load_pattern_stats,
    load_performance_history,
    record_performance,
    record_publish_decision,
    recompute_pattern_stats,
    save_pattern_stats,
)
from svf.media.assemble import VideoAssembler
from svf.media.visuals import VisualPicker
from svf.models import (
    PatternStat,
    PerformanceRecord,
    ProduceResult,
    PublishDecision,
    TrendInsights,
    TrendItem,
    VideoScript,
)
from svf.script.generator import ScriptGenerator, load_script, save_scripts
from svf.trends import InstagramCollector, TikTokCollector, YouTubeCollector
from svf.trends.base import load_latest_trends, save_trends

TRENDS_DIR = DATA_DIR / "trends"
INSIGHTS_DIR = DATA_DIR / "insights"
SCRIPTS_DIR = DATA_DIR / "scripts"
AUDIO_DIR = DATA_DIR / "audio"
SOURCES_DIR = DATA_DIR / "sources"
FEEDBACK_DIR = DATA_DIR / "feedback"


def resolve_script_path(script_id: str) -> Path:
    """script_id を検証して台本ファイルのパスを返す.

    script_id はファイルパスに連結されるため、パス区切りや `..` を含む
    値は拒否する (タイポや不正な値で意図しないファイルを読み書きしないため)。
    """
    if (
        not script_id
        or "/" in script_id
        or "\\" in script_id
        or ".." in script_id
        or script_id.startswith(".")
    ):
        raise ValueError(f"不正な台本ID: {script_id!r}")
    path = SCRIPTS_DIR / f"{script_id}.json"
    if not path.exists():
        raise FileNotFoundError(f"台本 {script_id} が見つかりません。")
    return path


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
        brief: str = "",
        must_texts: Optional[list[str]] = None,
    ) -> tuple[list[VideoScript], list[Path]]:
        """台本を生成する.

        Args:
            brief: 人間が指定する動画の雰囲気・方向性 (任意)。
            must_texts: 動画に必ず入れるテキスト (任意・複数可)。
        """
        product = product or load_product()
        insights = insights or load_latest_insights(INSIGHTS_DIR)
        style = load_style(style_name)
        generator = ScriptGenerator(
            api_key=self.settings.anthropic_api_key, model=self.settings.claude_model
        )
        pattern_stats = load_pattern_stats(FEEDBACK_DIR)
        scripts = generator.generate(
            product, style, insights, count=count, pattern_stats=pattern_stats,
            brief=brief, must_texts=must_texts,
        )
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
        picker = VisualPicker(
            ASSETS_DIR / "broll",
            ASSETS_DIR / "images",
            product_dir=ASSETS_DIR / "product",
        )
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

    # ---- 5. 公開判断 (人間が最終決定。ツールは自動投稿しない) ----
    def publish_decision(
        self, script_id: str, decision: str, note: str = ""
    ) -> PublishDecision:
        path = self._find_script_path(script_id)
        script = load_script(path)
        script.status = decision  # "published" または "rejected"
        path.write_text(script.model_dump_json(indent=2), encoding="utf-8")
        return record_publish_decision(FEEDBACK_DIR, script_id, decision, note)

    # ---- 6. 実績記録 (投稿後、人間が数値+quality評価を記録) ----
    def report_performance(
        self,
        script_id: str,
        platform: str,
        quality_rating: str,
        **metrics,
    ) -> PerformanceRecord:
        decision = latest_decision(FEEDBACK_DIR, script_id)
        if decision is None or decision.decision != "published":
            raise RuntimeError(
                f"{script_id} はまだ `svf publish` で公開決定が記録されていません。"
                "実際に投稿した動画のみ実績を記録してください。"
            )
        record = record_performance(FEEDBACK_DIR, script_id, platform, quality_rating, **metrics)
        stats = recompute_pattern_stats(load_performance_history(FEEDBACK_DIR), self._load_all_scripts())
        save_pattern_stats(stats, FEEDBACK_DIR)
        return record

    def import_performance_csv(self, csv_path: Path):
        """CSVから実績を一括取り込みする (TikTok Shop等の数値の転記用)."""
        from svf.feedback.importer import import_performance_csv

        return import_performance_csv(
            csv_path, SCRIPTS_DIR, FEEDBACK_DIR, self._load_all_scripts()
        )

    def leaderboard(self) -> list[PatternStat]:
        """実績 (good評価のみ) から見えている、スタイルごとの「勝ちパターン」一覧."""
        return load_pattern_stats(FEEDBACK_DIR)

    def _find_script_path(self, script_id: str) -> Path:
        return resolve_script_path(script_id)

    def _load_all_scripts(self) -> dict[str, VideoScript]:
        scripts = (load_script(p) for p in SCRIPTS_DIR.glob("*.json"))
        return {s.script_id: s for s in scripts}

    # ---- 一括実行 ----
    def run_all(
        self,
        platforms: list[str],
        query: str,
        style_name: str,
        count: int,
        limit: int = 20,
        tts_provider: str = "edge",
        brief: str = "",
        must_texts: Optional[list[str]] = None,
    ) -> list[ProduceResult]:
        """収集 → (人間によるgood/bad判定) → 分析 → 台本 → 動画 を一括実行する.

        インプレッション数だけを基準に学習しないよう、収集したトレンドは
        必ず人間が確認・判定してから分析に使われる (対話式)。
        """
        items, path = self.research(platforms, query=query, limit=limit)

        from svf.curation import curate_interactive
        from svf.trends.base import overwrite_trends

        items = curate_interactive(items)
        overwrite_trends(items, path)

        insights, _ = self.analyze(items)
        scripts, _ = self.write_scripts(
            style_name, count=count, insights=insights,
            brief=brief, must_texts=must_texts,
        )
        return [self.produce(s, tts_provider=tts_provider) for s in scripts]
