"""動画の実績 (インプレッション数など) を記録し、次の台本生成に反映する仕組み.

重要な安全装置:
- 実績を記録できるのは `svf publish` で人間が「実際に投稿した」と
  記録した動画のみ。ツールが自動で投稿することはない。
- 実績には必ず人間の `quality_rating` (good/bad) を付ける。
  bad (例: 炎上・釣りタイトルで伸びただけ) の実績は、数値がどれだけ
  良くても「勝ちパターン」の強化 (avg_engagement_rate の計算) からは除外する。
  これにより、インプレッション数だけを最適化して炎上系動画が
  量産される事態を防ぐ。
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from svf.models import PatternStat, PerformanceRecord, Platform, PublishDecision, VideoScript

PERFORMANCE_LOG = "performance.jsonl"
DECISIONS_LOG = "decisions.jsonl"
PATTERN_STATS_FILE = "pattern_stats.json"


def _append_jsonl(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(obj, ensure_ascii=False) + "\n")


def _read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


# ---- 公開判断 (人間による最終決定) ----


def record_publish_decision(
    feedback_dir: Path, script_id: str, decision: str, note: str = ""
) -> PublishDecision:
    record = PublishDecision(script_id=script_id, decision=decision, note=note)
    _append_jsonl(feedback_dir / DECISIONS_LOG, record.model_dump())
    return record


def latest_decision(feedback_dir: Path, script_id: str) -> Optional[PublishDecision]:
    rows = [
        d for d in _read_jsonl(feedback_dir / DECISIONS_LOG) if d["script_id"] == script_id
    ]
    if not rows:
        return None
    return PublishDecision(**rows[-1])


# ---- 実績記録 ----


def record_performance(
    feedback_dir: Path,
    script_id: str,
    platform: Platform,
    quality_rating: str,
    impressions: int = 0,
    views: int = 0,
    likes: int = 0,
    comments: int = 0,
    saves: int = 0,
    shares: int = 0,
    posted_url: str = "",
    quality_notes: str = "",
) -> PerformanceRecord:
    record = PerformanceRecord(
        id=f"perf_{datetime.now().strftime('%Y%m%d%H%M%S%f')}",
        script_id=script_id,
        platform=platform,
        posted_url=posted_url,
        impressions=impressions,
        views=views,
        likes=likes,
        comments=comments,
        saves=saves,
        shares=shares,
        quality_rating=quality_rating,
        quality_notes=quality_notes,
    )
    _append_jsonl(feedback_dir / PERFORMANCE_LOG, record.model_dump())
    return record


def load_performance_history(feedback_dir: Path) -> list[PerformanceRecord]:
    return [PerformanceRecord(**d) for d in _read_jsonl(feedback_dir / PERFORMANCE_LOG)]


# ---- パターン統計 (次の台本生成が参照する「勝ちパターン」) ----


def recompute_pattern_stats(
    history: list[PerformanceRecord], scripts: dict[str, VideoScript]
) -> list[PatternStat]:
    """style×pattern_tag ごとに集計する.

    bad評価の実績はサンプル数 (bad_count) には反映するが、
    avg_engagement_rate の計算には使わない。
    """
    groups: dict[tuple[str, str], dict] = {}
    for rec in history:
        script = scripts.get(rec.script_id)
        if script is None or not script.pattern_tag:
            continue
        key = (script.style, script.pattern_tag)
        g = groups.setdefault(
            key, {"good": 0, "bad": 0, "rates": [], "last_used": rec.recorded_at}
        )
        if rec.quality_rating == "bad":
            g["bad"] += 1
        else:
            g["good"] += 1
            g["rates"].append(rec.engagement_rate())
        g["last_used"] = max(g["last_used"], rec.recorded_at)

    stats = []
    for (style, tag), g in groups.items():
        avg = sum(g["rates"]) / len(g["rates"]) if g["rates"] else 0.0
        stats.append(
            PatternStat(
                pattern_tag=tag,
                style=style,
                sample_size=g["good"] + g["bad"],
                good_count=g["good"],
                bad_count=g["bad"],
                avg_engagement_rate=avg,
                last_used=g["last_used"],
            )
        )
    stats.sort(key=lambda s: s.avg_engagement_rate, reverse=True)
    return stats


def save_pattern_stats(stats: list[PatternStat], feedback_dir: Path) -> Path:
    path = feedback_dir / PATTERN_STATS_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps([s.model_dump() for s in stats], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path


def load_pattern_stats(feedback_dir: Path) -> list[PatternStat]:
    path = feedback_dir / PATTERN_STATS_FILE
    if not path.exists():
        return []
    return [PatternStat(**d) for d in json.loads(path.read_text(encoding="utf-8"))]


def top_pattern_for_style(stats: list[PatternStat], style: str) -> Optional[PatternStat]:
    """そのスタイルで最も実績の良いパターン (good実績が1件以上あるもの) を返す."""
    candidates = [s for s in stats if s.style == style and s.good_count > 0]
    return candidates[0] if candidates else None
