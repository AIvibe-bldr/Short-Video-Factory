"""商品写真の優先使用と、brief/must_texts のプロンプト反映のテスト."""

from pathlib import Path

from svf.config import Product, StylePreset
from svf.media.visuals import VisualPicker
from svf.models import TrendInsights
from svf.script.generator import ScriptGenerator


def _picker_with_product(tmp_path: Path, with_general: bool = False) -> VisualPicker:
    product_dir = tmp_path / "product"
    product_dir.mkdir()
    (product_dir / "item_front.jpg").touch()
    (product_dir / "item_side.jpg").touch()
    broll = tmp_path / "broll"
    images = tmp_path / "images"
    if with_general:
        broll.mkdir()
        (broll / "coffee_pour.mp4").touch()
    return VisualPicker(broll, images, product_dir=product_dir)


# ---- 商品写真の優先使用 ----


def test_featured_scene_always_uses_product_photo(tmp_path: Path):
    picker = _picker_with_product(tmp_path, with_general=True)
    visual = picker.pick("coffee をカップに注ぐ", product_visibility="featured")
    assert visual.path is not None
    assert visual.path.parent.name == "product"


def test_product_photos_rotate(tmp_path: Path):
    picker = _picker_with_product(tmp_path)
    first = picker.pick("", product_visibility="featured")
    second = picker.pick("", product_visibility="featured")
    assert first.path != second.path  # ローテーションで別の写真になる


def test_none_scene_never_uses_product_photo(tmp_path: Path):
    picker = _picker_with_product(tmp_path)  # 一般素材なし
    visual = picker.pick("朝の風景", product_visibility="none")
    assert visual.kind == "gradient"  # 商品写真があってもnoneシーンでは使わない


def test_subtle_scene_prefers_keyword_match_then_product(tmp_path: Path):
    picker = _picker_with_product(tmp_path, with_general=True)
    # キーワードが合う一般素材があればそちら
    matched = picker.pick("coffee を注ぐ手元", product_visibility="subtle")
    assert matched.path.name == "coffee_pour.mp4"
    # 合わなければ商品写真
    sub = tmp_path / "b"
    sub.mkdir()
    fallback = _picker_with_product(sub).pick("無関係な指示", "subtle")
    assert fallback.path.parent.name == "product"


# ---- brief / must_texts のプロンプト反映 ----


def _prompt(brief="", must_texts=None) -> str:
    return ScriptGenerator._build_prompt(
        Product(name="テスト商品"),
        StylePreset(name="hands_only"),
        TrendInsights(),
        used_angles=[],
        variant="exploit",
        top=None,
        brief=brief,
        must_texts=must_texts or [],
    )


def test_brief_is_injected_as_top_priority():
    prompt = _prompt(brief="梅雨の時期に合う落ち着いた雰囲気で")
    assert "制作者の意図" in prompt
    assert "梅雨の時期に合う落ち着いた雰囲気で" in prompt
    assert "優先" in prompt


def test_must_texts_are_injected_verbatim():
    prompt = _prompt(must_texts=["今だけ送料無料", "詳細はプロフへ"])
    assert "必ず入れるテキスト" in prompt
    assert "- 今だけ送料無料" in prompt
    assert "- 詳細はプロフへ" in prompt


def test_no_brief_no_extra_sections():
    prompt = _prompt()
    assert "制作者の意図" not in prompt
    assert "必ず入れるテキスト" not in prompt
