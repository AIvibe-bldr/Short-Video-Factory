"""CSV一括取り込みと GA4 連携ロジックのテスト (ネットワーク不要な部分)."""

from pathlib import Path

from svf.feedback.importer import (
    TEMPLATE_CSV,
    build_short_code_index,
    import_performance_csv,
)
from svf.feedback.tracker import (
    load_performance_history,
    load_pattern_stats,
    record_publish_decision,
)
from svf.integrations.ga4 import _normalize_platform
from svf.models import VideoScript


def _setup_script(scripts_dir: Path, script_id: str, code: str) -> VideoScript:
    scripts_dir.mkdir(parents=True, exist_ok=True)
    s = VideoScript(
        script_id=script_id, style="hands_only",
        pattern_tag="before_after", short_code=code,
    )
    (scripts_dir / f"{script_id}.json").write_text(
        s.model_dump_json(indent=2), encoding="utf-8"
    )
    return s


# ---- CSV取り込み ----


def test_import_csv_by_script_id_and_short_code(tmp_path: Path):
    scripts_dir = tmp_path / "scripts"
    feedback_dir = tmp_path / "feedback"
    s1 = _setup_script(scripts_dir, "vid_a", "aaa111")
    s2 = _setup_script(scripts_dir, "vid_b", "bbb222")
    record_publish_decision(feedback_dir, "vid_a", "published")
    record_publish_decision(feedback_dir, "vid_b", "published")

    csv_file = tmp_path / "perf.csv"
    csv_file.write_text(
        "script_id,short_code,platform,quality,views,likes,clicks,purchases,revenue,notes\n"
        "vid_a,,youtube,good,1000,100,50,2,2960,\n"
        ",bbb222,tiktok,good,2000,,,,,TikTok Shop\n",
        encoding="utf-8",
    )
    result = import_performance_csv(
        csv_file, scripts_dir, feedback_dir,
        {"vid_a": s1, "vid_b": s2},
    )
    assert result.errors == []
    assert len(result.imported) == 2
    assert result.imported[0].purchases == 2
    assert result.imported[1].script_id == "vid_b"  # short_codeから解決された
    # パターン統計も再計算されている
    assert load_pattern_stats(feedback_dir)


def test_import_csv_rejects_unpublished_and_bad_rows(tmp_path: Path):
    scripts_dir = tmp_path / "scripts"
    feedback_dir = tmp_path / "feedback"
    s = _setup_script(scripts_dir, "vid_a", "aaa111")
    # publish未記録のまま

    csv_file = tmp_path / "perf.csv"
    csv_file.write_text(
        "script_id,short_code,platform,quality,views\n"
        "vid_a,,youtube,good,1000\n"       # publish未記録 → エラー
        "vid_a,,youtube,maybe,1000\n"      # 不正なquality → エラー
        ",zzz999,youtube,good,1000\n"      # 未知のshort_code → エラー
        "vid_a,,twitter,good,1000\n",      # 未対応platform → エラー
        encoding="utf-8",
    )
    result = import_performance_csv(csv_file, scripts_dir, feedback_dir, {"vid_a": s})
    assert result.imported == []
    assert len(result.errors) == 4
    assert load_performance_history(feedback_dir) == []


def test_import_csv_tolerates_bom_and_comma_numbers(tmp_path: Path):
    scripts_dir = tmp_path / "scripts"
    feedback_dir = tmp_path / "feedback"
    s = _setup_script(scripts_dir, "vid_a", "aaa111")
    record_publish_decision(feedback_dir, "vid_a", "published")

    csv_file = tmp_path / "perf.csv"
    # Excel保存を想定: BOM付き + カンマ区切りの数値
    csv_file.write_bytes(
        "﻿script_id,platform,quality,views,purchases\n"
        'vid_a,youtube,good,"12,000",3\n'.encode("utf-8")
    )
    result = import_performance_csv(csv_file, scripts_dir, feedback_dir, {"vid_a": s})
    assert result.errors == []
    assert result.imported[0].views == 12000
    assert result.imported[0].purchases == 3


def test_template_csv_is_parseable():
    import csv as csv_mod
    import io

    rows = list(csv_mod.DictReader(io.StringIO(TEMPLATE_CSV.strip())))
    assert len(rows) == 2
    assert "script_id" in rows[0] and "purchases" in rows[0]


def test_build_short_code_index_skips_broken_files(tmp_path: Path):
    scripts_dir = tmp_path / "scripts"
    _setup_script(scripts_dir, "vid_a", "aaa111")
    (scripts_dir / "broken.json").write_text("{not json", encoding="utf-8")
    index = build_short_code_index(scripts_dir)
    assert index == {"aaa111": "vid_a"}


# ---- GA4 連携 (純粋ロジック部分) ----


def test_normalize_platform():
    assert _normalize_platform("youtube.com") == "youtube"
    assert _normalize_platform("TikTok") == "tiktok"
    assert _normalize_platform("instagram_stories") == "instagram"
    assert _normalize_platform("ig") == "instagram"
    assert _normalize_platform("google") is None
    assert _normalize_platform("") is None
