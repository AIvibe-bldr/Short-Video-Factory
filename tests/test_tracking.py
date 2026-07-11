"""動画ごとの流入計測 (short_code / 計測リンク / 固定コメント) のテスト."""

from svf.models import PerformanceRecord, VideoScript
from svf.feedback.tracker import recompute_pattern_stats, top_pattern_for_style
from svf.tracking import (
    build_tracking_url,
    coupon_code,
    make_short_code,
    render_pinned_comment,
)


# ---- short_code ----


def test_short_code_is_deterministic():
    assert make_short_code("abc") == make_short_code("abc")


def test_short_code_differs_per_script():
    assert make_short_code("script_a") != make_short_code("script_b")


def test_short_code_length_and_charset():
    code = make_short_code("kawaii_20260711_deadbeef")
    assert len(code) == 6
    assert code.isalnum() and code == code.lower()


# ---- 計測リンク ----


def test_tracking_url_contains_utm_params():
    url = build_tracking_url("https://example.com/item", "youtube", "abc123")
    assert "utm_source=youtube" in url
    assert "utm_medium=short_video" in url
    assert "utm_campaign=svf_abc123" in url


def test_tracking_url_preserves_existing_query():
    url = build_tracking_url("https://example.com/item?ref=lp", "tiktok", "abc123")
    assert "ref=lp" in url
    assert "utm_campaign=svf_abc123" in url


def test_tracking_url_empty_base():
    assert build_tracking_url("", "youtube", "abc123") == ""


# ---- 固定コメント ----


def test_render_pinned_comment_injects_link_and_code():
    template = "動画で使ってたのはこれ→ {LINK} クーポン: {CODE}"
    text = render_pinned_comment(
        template, "https://example.com/item", "instagram", "abc123"
    )
    assert "utm_source=instagram" in text
    assert "utm_campaign=svf_abc123" in text
    assert coupon_code("abc123") == "SVF-ABC123"
    assert "SVF-ABC123" in text
    assert "{LINK}" not in text and "{CODE}" not in text


def test_render_pinned_comment_without_product_url():
    text = render_pinned_comment("こちら→ {LINK}", "", "youtube", "abc123")
    assert "(商品URL未設定)" in text


# ---- 購入データが勝ちパターン選定に優先される ----


def _script(tag: str) -> VideoScript:
    return VideoScript(script_id=f"s_{tag}", style="hands_only", pattern_tag=tag)


def _rec(script_id: str, **kw) -> PerformanceRecord:
    defaults = dict(
        id=f"p_{script_id}", script_id=script_id, platform="youtube",
        quality_rating="good", views=1000,
    )
    defaults.update(kw)
    return PerformanceRecord(**defaults)


def test_pattern_with_purchases_beats_higher_engagement():
    scripts = {"s_viral": _script("viral"), "s_seller": _script("seller")}
    history = [
        # バズったが売れていないパターン
        _rec("s_viral", likes=500),  # エンゲージ率 50%
        # エンゲージは低いが購入が出ているパターン
        _rec("s_seller", likes=10, clicks=100, purchases=5),  # 購入率 5%
    ]
    stats = recompute_pattern_stats(history, scripts)
    top = top_pattern_for_style(stats, "hands_only")
    assert top.pattern_tag == "seller"
    assert top.total_purchases == 5
    assert top.avg_conversion_rate > 0


def test_bad_rating_purchases_are_excluded():
    scripts = {"s_burnout": _script("burnout")}
    history = [
        _rec("s_burnout", clicks=1000, purchases=100, quality_rating="bad"),
    ]
    stats = recompute_pattern_stats(history, scripts)
    assert stats[0].total_purchases == 0  # bad評価の購入は集計されない
    assert stats[0].avg_conversion_rate == 0.0


def test_conversion_rate_prefers_clicks_denominator():
    rec = _rec("s_x", views=10000, clicks=200, purchases=10)
    assert rec.conversion_rate() == 10 / 200
