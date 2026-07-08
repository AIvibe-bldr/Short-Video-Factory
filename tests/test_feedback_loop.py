"""フィードバックループ (キュレーション・8:2探索/活用・実績集計) のテスト.

Claude APIを呼ばない純粋ロジックのみを対象にする。
"""

from pathlib import Path

import pytest

from svf.analysis.analyzer import select_curated
from svf.feedback.tracker import (
    latest_decision,
    load_pattern_stats,
    load_performance_history,
    record_performance,
    record_publish_decision,
    recompute_pattern_stats,
    save_pattern_stats,
    top_pattern_for_style,
)
from svf.models import PatternStat, PerformanceRecord, TrendItem, VideoScript
from svf.script.generator import ScriptGenerator


# ---- キュレーション (good/bad 判定) ----


def _item(rating=None) -> TrendItem:
    return TrendItem(
        platform="youtube", video_id="v1", url="https://x", human_rating=rating
    )


def test_select_curated_requires_review():
    with pytest.raises(RuntimeError, match="評価されていません"):
        select_curated([_item(), _item()])


def test_select_curated_requires_at_least_one_good():
    with pytest.raises(RuntimeError, match="good判定"):
        select_curated([_item("bad"), _item("bad")])


def test_select_curated_filters_out_bad_and_unreviewed():
    items = [_item("good"), _item("bad"), _item(None)]
    usable = select_curated(items)
    assert len(usable) == 1
    assert usable[0].human_rating == "good"


# ---- 8割exploit / 2割explore の分割 ----


@pytest.mark.parametrize(
    "count,expected_exploit,expected_explore",
    [(0, 0, 0), (1, 1, 0), (3, 2, 1), (5, 4, 1), (10, 8, 2)],
)
def test_split_variants_ratio(count, expected_exploit, expected_explore):
    variants = ScriptGenerator._split_variants(count)
    assert variants.count("exploit") == expected_exploit
    assert variants.count("explore") == expected_explore
    assert len(variants) == count


# ---- 実績記録 → パターン統計 (bad評価は平均計算から除外) ----


def _script(style="hands_only", tag="before_after") -> VideoScript:
    return VideoScript(script_id=f"s_{tag}", style=style, pattern_tag=tag)


def test_recompute_pattern_stats_excludes_bad_from_average():
    script = _script()
    good_rec = PerformanceRecord(
        id="p1", script_id=script.script_id, platform="youtube",
        views=1000, likes=100, quality_rating="good",
    )
    bad_rec = PerformanceRecord(
        id="p2", script_id=script.script_id, platform="youtube",
        views=1000000, likes=900000, quality_rating="bad",  # 数値は圧倒的だがbad
    )
    stats = recompute_pattern_stats([good_rec, bad_rec], {script.script_id: script})
    assert len(stats) == 1
    s = stats[0]
    assert s.good_count == 1
    assert s.bad_count == 1
    # bad評価の巨大な数値が平均に混ざっていないこと
    assert s.avg_engagement_rate == pytest.approx(good_rec.engagement_rate())


def test_top_pattern_for_style_ignores_zero_good_count():
    stats = [
        PatternStat(pattern_tag="only_bad", style="hands_only", good_count=0, bad_count=5),
        PatternStat(pattern_tag="has_good", style="hands_only", good_count=2, avg_engagement_rate=0.1),
    ]
    top = top_pattern_for_style(stats, "hands_only")
    assert top.pattern_tag == "has_good"


def test_engagement_rate_uses_views_over_impressions():
    rec = PerformanceRecord(
        id="p1", script_id="s1", platform="tiktok",
        impressions=10000, views=1000, likes=100, quality_rating="good",
    )
    assert rec.engagement_rate() == pytest.approx(0.1)


# ---- 公開判断 → 実績記録の順序制約 ----


def test_publish_and_performance_roundtrip(tmp_path: Path):
    record_publish_decision(tmp_path, "s1", "published", "テスト投稿")
    decision = latest_decision(tmp_path, "s1")
    assert decision is not None
    assert decision.decision == "published"

    rec = record_performance(tmp_path, "s1", "youtube", "good", views=500, likes=50)
    history = load_performance_history(tmp_path)
    assert len(history) == 1
    assert history[0].id == rec.id

    stats = recompute_pattern_stats(history, {"s1": _script(tag="s1_pattern")})
    save_pattern_stats(stats, tmp_path)
    reloaded = load_pattern_stats(tmp_path)
    assert reloaded == stats
