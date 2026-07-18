"""モデル・設定・スタイルプリセットの基本テスト (APIキー不要)."""

from pathlib import Path

import pytest

from svf.config import StylePreset, list_styles, load_style
from svf.media.assemble import _wrap_text
from svf.media.visuals import VisualPicker
from svf.models import Scene, TrendItem, VideoScript
from svf.trends.base import extract_hashtags


def test_all_style_presets_load():
    styles = list_styles()
    assert set(styles) >= {
        "kawaii_presenter",
        "english_presenter",
        "hands_only",
        "daily_scene",
    }
    for name in styles:
        style = load_style(name)
        assert isinstance(style, StylePreset)
        assert style.duration_seconds > 0
        assert style.product_placement in ("featured", "subtle", "background")


def test_daily_scene_is_background_placement():
    style = load_style("daily_scene")
    assert style.product_placement == "background"
    assert style.presenter == ""


def test_english_presenter_language():
    style = load_style("english_presenter")
    assert style.language == "en"


def test_load_unknown_style_raises():
    with pytest.raises(FileNotFoundError):
        load_style("no_such_style")


def test_extract_hashtags():
    tags = extract_hashtags("朝のルーティン #コーヒー #morning routine #vlog、おすすめ")
    assert "コーヒー" in tags
    assert "morning" in tags
    assert "vlog" in tags


def test_trend_item_defaults():
    item = TrendItem(platform="youtube", video_id="abc", url="https://youtu.be/abc")
    assert item.view_count == 0
    assert item.hashtags == []


def test_video_script_roundtrip():
    script = VideoScript(
        script_id="test_001",
        style="hands_only",
        scenes=[
            Scene(
                index=0,
                start_seconds=0,
                end_seconds=3,
                narration="朝のはじまり",
                product_visibility="subtle",
            )
        ],
    )
    restored = VideoScript.model_validate_json(script.model_dump_json())
    assert restored.scenes[0].narration == "朝のはじまり"


def test_wrap_text_limits_lines():
    wrapped = _wrap_text("これはとても長いテロップのテストです。画面に収まるように改行されます。", max_chars=10)
    lines = wrapped.split("\n")
    assert len(lines) <= 4
    assert all(len(line) <= 11 for line in lines)


def test_visual_picker_gradient_fallback(tmp_path: Path):
    picker = VisualPicker(tmp_path / "broll", tmp_path / "images")
    visual = picker.pick("手元のアップ")
    assert visual.kind == "gradient"
    assert visual.colors is not None


def test_visual_picker_keyword_match(tmp_path: Path):
    broll = tmp_path / "broll"
    broll.mkdir()
    (broll / "coffee_pour.mp4").touch()
    (broll / "random_clip.mp4").touch()
    picker = VisualPicker(broll, tmp_path / "images")
    visual = picker.pick("coffee をカップに注ぐ手元のアップ")
    assert visual.path is not None
    assert visual.path.name == "coffee_pour.mp4"
