"""Claude によるショート動画台本の生成 (スタイル × トレンド × 商品)."""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Literal

import anthropic
from pydantic import BaseModel, Field

from svf.config import Product, StylePreset
from svf.feedback.tracker import top_pattern_for_style
from svf.models import PatternStat, Scene, TrendInsights, VideoScript
from svf.tracking import make_short_code

SYSTEM_PROMPT = """\
あなたはショート動画 (YouTube Shorts / TikTok / Instagram リール) の
放送作家兼ディレクターです。与えられた「トレンド分析」「商品情報」「スタイル指定」から、
そのまま制作に入れる精密な台本を書きます。

守るべき原則:
- 冒頭0〜2秒のフックが最重要。トレンド分析のフックパターンを必ず活用する
- スタイル指定の product_placement を厳守する:
  - featured: 商品を主役として堂々と紹介する
  - subtle: 生活シーンの中でさりげなく商品を使う・映す。宣伝色を出さない
  - background: 日常のワンシーンとして撮り、商品は画面の中に「ただ写っている」だけ。
    ナレーションで商品に言及しない
- シーンごとに秒数を割り、合計がスタイル指定の尺に収まるようにする
- ナレーションは口語で、読み上げたときに自然な長さにする (1秒あたり約6〜7文字)
- visual_direction は撮影者・映像生成AIへの指示としてそのまま使える具体性で書く
  (構図、被写体、動き、明るさ、商品がどう映るか)
- テロップは短く、スマホ画面で読める文字数にする
- 誇大表現・断定的な効果効能の主張はしない。NG表現リストを厳守する
- 指定された言語で書く

pattern_tag について:
台本の「フック+構成」の型を表す短い英数字ラベル (snake_case) を付けてください。
例: before_after, myth_busting, pov_daily_routine, listicle_tips, problem_agitate_solve
この動画の実績が後で記録され、同じ型が高い実績を出せば、次回以降その型を
再利用するよう指示されます。したがって、同じ構成の型には毎回同じラベルを使ってください。

pinned_comment (固定コメント) について:
投稿直後に投稿者自身がコメント欄に書き込み、固定するためのコメント文を書いてください。
- 動画の内容・フックに合わせて、台本ごとに文面を変えること
  (この文面の違いとリンクの計測パラメータで、どの動画から商品ページに
  来たかを後から特定します)
- 商品リンクを入れる位置に、プレースホルダ {LINK} を必ず1回だけ入れること
  (実際のURLは後からツールが差し込むので、URL自体は書かないこと)
- 宣伝色を出しすぎず、動画の補足や視聴者への一言 + 自然なリンク誘導にすること
- product_placement が background のスタイルでは、商品の宣伝はせず
  「概要欄/コメントに載せておきます」程度のさりげない一言にすること
"""


class _SceneOutput(BaseModel):
    start_seconds: float = Field(description="シーン開始秒")
    end_seconds: float = Field(description="シーン終了秒")
    narration: str = Field(description="ナレーション/セリフ。無音なら空文字")
    on_screen_text: str = Field(description="画面テロップ。なければ空文字")
    visual_direction: str = Field(description="映像の具体的な指示")
    product_visibility: Literal["none", "subtle", "featured"] = Field(
        description="このシーンでの商品の映り方"
    )


class _ScriptOutput(BaseModel):
    title: str = Field(description="投稿タイトル案")
    hook: str = Field(description="採用した冒頭フックの説明")
    scenes: list[_SceneOutput] = Field(description="シーンのリスト")
    caption: str = Field(description="投稿キャプション案")
    hashtags: list[str] = Field(description="ハッシュタグ (#なし)")
    trend_basis: str = Field(description="どのトレンド要素をどう組み込んだか")
    pattern_tag: str = Field(
        description="この台本のフック+構成の型を表す短い英数字ラベル (snake_case)"
    )
    pinned_comment: str = Field(
        description="投稿直後に固定するコメント文。商品リンク位置に {LINK} を1回だけ含める"
    )


class ScriptGenerator:
    def __init__(self, api_key: str = "", model: str = "claude-opus-4-8"):
        self.client = anthropic.Anthropic(api_key=api_key) if api_key else anthropic.Anthropic()
        self.model = model

    def generate(
        self,
        product: Product,
        style: StylePreset,
        insights: TrendInsights,
        count: int = 1,
        pattern_stats: list[PatternStat] | None = None,
        brief: str = "",
        must_texts: list[str] | None = None,
    ) -> list[VideoScript]:
        """指定スタイルの台本を count 本生成する.

        実績データ (pattern_stats) がある場合、約8割は過去に最も反応が良かった
        「勝ちパターン」を踏襲 (exploit) し、約2割はあえて違う構成を試す
        (explore)。実績がまだなければ全て探索的に生成する。

        Args:
            brief: 人間が指定する動画の雰囲気・方向性 (任意)。
            must_texts: 動画に必ず入れるテキスト (任意・複数可)。
                テロップまたはナレーションとして全台本に組み込まれる。
        """
        top = top_pattern_for_style(pattern_stats or [], style.name)
        variants = self._split_variants(count)
        scripts: list[VideoScript] = []
        used_angles: list[str] = []
        for variant in variants:
            script = self._generate_one(
                product, style, insights, used_angles, variant, top,
                brief=brief, must_texts=must_texts or [],
            )
            scripts.append(script)
            used_angles.append(f"{script.hook} / {script.title}")
        return scripts

    @staticmethod
    def _split_variants(count: int) -> list[str]:
        """8割exploit / 2割explore の比率でバリアントを割り当てる."""
        if count <= 1:
            return ["exploit"] * count
        exploit_n = max(1, min(round(count * 0.8), count))
        return ["exploit"] * exploit_n + ["explore"] * (count - exploit_n)

    def _generate_one(
        self,
        product: Product,
        style: StylePreset,
        insights: TrendInsights,
        used_angles: list[str],
        variant: str,
        top: PatternStat | None,
        brief: str = "",
        must_texts: list[str] | None = None,
    ) -> VideoScript:
        user_prompt = self._build_prompt(
            product, style, insights, used_angles, variant, top,
            brief=brief, must_texts=must_texts or [],
        )
        response = self.client.messages.parse(
            model=self.model,
            max_tokens=16000,
            thinking={"type": "adaptive"},
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}],
            output_format=_ScriptOutput,
        )
        out: _ScriptOutput = response.parsed_output
        scenes = [
            Scene(index=n, **s.model_dump()) for n, s in enumerate(out.scenes)
        ]
        total = max((s.end_seconds for s in scenes), default=style.duration_seconds)
        script_id = f"{style.name}_{datetime.now().strftime('%Y%m%d')}_{uuid.uuid4().hex[:8]}"
        return VideoScript(
            script_id=script_id,
            style=style.name,
            language=style.language,
            title=out.title,
            hook=out.hook,
            total_seconds=total,
            scenes=scenes,
            caption=out.caption,
            hashtags=out.hashtags,
            trend_basis=out.trend_basis,
            variant=variant,
            pattern_tag=out.pattern_tag,
            short_code=make_short_code(script_id),
            pinned_comment=out.pinned_comment,
        )

    @staticmethod
    def _build_prompt(
        product: Product,
        style: StylePreset,
        insights: TrendInsights,
        used_angles: list[str],
        variant: str,
        top: PatternStat | None,
        brief: str = "",
        must_texts: list[str] | None = None,
    ) -> str:
        parts = [
            "## トレンド分析 (現在伸びているショート動画の要点)",
            insights.model_dump_json(indent=1, exclude={"analyzed_at", "source_count"}),
            "",
            "## 商品情報",
            product.model_dump_json(indent=1),
            "",
            "## スタイル指定",
            style.model_dump_json(indent=1, exclude={"tts_voice"}),
            "",
            f"尺は {style.duration_seconds} 秒以内。言語は {style.language}。",
            "この条件で台本を1本書いてください。",
        ]

        if brief:
            parts += [
                "",
                "## 制作者の意図 (最優先で反映すること)",
                brief,
                "この意図はトレンド分析やスタイル指定と矛盾する場合でも優先してください。",
            ]

        if must_texts:
            parts += [
                "",
                "## 動画に必ず入れるテキスト (一字一句変えないこと)",
                *[f"- {t}" for t in must_texts],
                "上記の各テキストを、テロップ (on_screen_text) または"
                "ナレーション (narration) のいずれかに、原文のまま必ず含めてください。",
            ]

        if top is not None:
            if variant == "exploit":
                parts += [
                    "",
                    "## 過去の実績 (このスタイルで最も反応が良かったパターン)",
                    f"パターンタグ: {top.pattern_tag}",
                    f"good評価での平均エンゲージメント率: {top.avg_engagement_rate:.1%} "
                    f"(good実績 {top.good_count}件 / bad実績 {top.bad_count}件)",
                    "このパターンのフック・構成の型を踏襲してください。"
                    f"pattern_tag には '{top.pattern_tag}' をそのまま使ってください。",
                ]
            else:
                parts += [
                    "",
                    "## 探索指示 (このパターンとは違う構成を試す)",
                    f"最も実績の良いパターン '{top.pattern_tag}' とはあえて異なる、"
                    "新しいフック・構成のアイデアを試してください。"
                    "新しい構成には新しいpattern_tagを付けてください。",
                ]

        if used_angles:
            parts += [
                "",
                "## すでに生成済みの切り口 (重複を避けること)",
                *[f"- {a}" for a in used_angles],
                "上記とはフック・構成の異なる新しい切り口にしてください。",
            ]
        return "\n".join(parts)


def save_scripts(scripts: list[VideoScript], out_dir: Path) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for s in scripts:
        path = out_dir / f"{s.script_id}.json"
        path.write_text(s.model_dump_json(indent=2), encoding="utf-8")
        paths.append(path)
    return paths


def load_script(path: Path) -> VideoScript:
    return VideoScript(**json.loads(path.read_text(encoding="utf-8")))
