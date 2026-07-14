"""実績のCSV一括取り込み.

TikTok Shop Seller Center などの管理画面からエクスポート/転記した数値を
1ファイルでまとめて実績登録する。テンプレート:

    script_id,short_code,platform,quality,impressions,views,likes,comments,saves,shares,clicks,purchases,revenue,url,notes

- script_id か short_code のどちらかで動画を指定する (両方あれば script_id 優先)
- platform: youtube / tiktok / instagram
- quality: good / bad (人間の判定。炎上・釣りで伸びただけなら bad)
- 数値列は空欄可 (0扱い)

`svf publish` で published が記録されていない動画の行はエラーになる
(実際に投稿した動画のみ実績を記録するという原則を維持するため)。
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from pathlib import Path

from svf.feedback.tracker import (
    latest_decision,
    load_performance_history,
    record_performance,
    recompute_pattern_stats,
    save_pattern_stats,
)
from svf.models import PerformanceRecord, VideoScript

TEMPLATE_HEADER = (
    "script_id,short_code,platform,quality,impressions,views,likes,"
    "comments,saves,shares,clicks,purchases,revenue,url,notes"
)

TEMPLATE_CSV = TEMPLATE_HEADER + """
kawaii_presenter_20260708_xxxxxxxx,,youtube,good,50000,12000,800,40,60,20,150,6,8880,https://youtube.com/shorts/xxxx,
,gilqql,tiktok,good,,20000,1500,80,,,210,9,13320,,TikTok Shop経由
"""

_INT_FIELDS = (
    "impressions", "views", "likes", "comments", "saves", "shares",
    "clicks", "purchases",
)
_PLATFORMS = ("youtube", "tiktok", "instagram")


@dataclass
class ImportResult:
    imported: list[PerformanceRecord] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)  # "行N: 理由"


def build_short_code_index(scripts_dir: Path) -> dict[str, str]:
    """short_code → script_id の対応表を作る."""
    index: dict[str, str] = {}
    for path in scripts_dir.glob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        code = data.get("short_code")
        if code:
            index[code] = data["script_id"]
    return index


def _parse_int(value: str) -> int:
    value = (value or "").replace(",", "").strip()
    return int(value) if value else 0


def _parse_float(value: str) -> float:
    value = (value or "").replace(",", "").strip()
    return float(value) if value else 0.0


def import_performance_csv(
    csv_path: Path,
    scripts_dir: Path,
    feedback_dir: Path,
    scripts: dict[str, VideoScript],
) -> ImportResult:
    """CSVの各行を実績として記録し、最後にパターン統計を再計算する."""
    result = ImportResult()
    code_index = build_short_code_index(scripts_dir)

    # utf-8-sig: Excelで保存したCSVのBOMを許容する
    with csv_path.open(encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for line_no, row in enumerate(reader, start=2):  # 1行目はヘッダー
            error = _import_row(row, line_no, code_index, feedback_dir, result)
            if error:
                result.errors.append(error)

    if result.imported:
        stats = recompute_pattern_stats(load_performance_history(feedback_dir), scripts)
        save_pattern_stats(stats, feedback_dir)
    return result


def _import_row(
    row: dict,
    line_no: int,
    code_index: dict[str, str],
    feedback_dir: Path,
    result: ImportResult,
) -> str | None:
    """1行を取り込む。問題があればエラーメッセージを返す."""
    get = lambda key: (row.get(key) or "").strip()  # noqa: E731

    script_id = get("script_id")
    if not script_id:
        code = get("short_code")
        if not code:
            return f"行{line_no}: script_id か short_code が必要です"
        script_id = code_index.get(code)
        if not script_id:
            return f"行{line_no}: short_code '{code}' に対応する台本が見つかりません"

    platform = get("platform").lower()
    if platform not in _PLATFORMS:
        return f"行{line_no}: platform は {'/'.join(_PLATFORMS)} のいずれかにしてください"

    quality = get("quality").lower()
    if quality not in ("good", "bad"):
        return f"行{line_no}: quality は good か bad にしてください"

    decision = latest_decision(feedback_dir, script_id)
    if decision is None or decision.decision != "published":
        return (
            f"行{line_no}: {script_id} は `svf publish` で公開決定が未記録です。"
            "実際に投稿した動画のみ記録できます"
        )

    try:
        numbers = {name: _parse_int(get(name)) for name in _INT_FIELDS}
        revenue = _parse_float(get("revenue"))
    except ValueError as e:
        return f"行{line_no}: 数値の形式が不正です ({e})"

    record = record_performance(
        feedback_dir,
        script_id,
        platform,
        quality,
        revenue=revenue,
        posted_url=get("url"),
        quality_notes=get("notes"),
        **numbers,
    )
    result.imported.append(record)
    return None
