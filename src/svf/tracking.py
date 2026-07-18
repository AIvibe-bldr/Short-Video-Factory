"""動画ごとの流入計測 (どの動画から購入ページに飛んできたかの特定).

仕組み:
- 台本ごとに固有の短いコード (short_code) を発行する
- 商品URLに UTM パラメータとしてコードを埋め込んだ「計測リンク」を作る
  → LP側のアクセス解析 (GA4など) で utm_campaign を見れば、
    どの動画から来たかが動画単位で分かる
- 固定コメント文は台本ごとに少しずつ違う文面で生成され、
  {LINK} の位置に計測リンクが差し込まれる
- クーポンコードとしても short_code を使えば、リンクを踏まずに
  検索して買った人も購入時に特定できる (ショップ側でコード登録が必要)
"""

from __future__ import annotations

import hashlib
from urllib.parse import urlencode, urlparse, urlunparse, parse_qsl

LINK_PLACEHOLDER = "{LINK}"
CODE_PLACEHOLDER = "{CODE}"

_BASE36 = "0123456789abcdefghijklmnopqrstuvwxyz"


def make_short_code(script_id: str, length: int = 6) -> str:
    """台本IDから固有の短いコードを決定論的に生成する (同じIDなら常に同じコード)."""
    digest = hashlib.sha256(script_id.encode("utf-8")).digest()
    n = int.from_bytes(digest[:8], "big")
    chars = []
    for _ in range(length):
        n, r = divmod(n, 36)
        chars.append(_BASE36[r])
    return "".join(chars)


def build_tracking_url(base_url: str, platform: str, short_code: str) -> str:
    """商品URLに動画識別用のUTMパラメータを付与する.

    utm_source   = 投稿先プラットフォーム (youtube / tiktok / instagram)
    utm_medium   = short_video
    utm_campaign = svf_<short_code>  ← 動画ごとに固有。これで流入元動画を特定する
    """
    if not base_url:
        return ""
    parsed = urlparse(base_url)
    query = dict(parse_qsl(parsed.query))
    query.update(
        {
            "utm_source": platform,
            "utm_medium": "short_video",
            "utm_campaign": f"svf_{short_code}",
        }
    )
    return urlunparse(parsed._replace(query=urlencode(query)))


def coupon_code(short_code: str) -> str:
    """クーポンコード表記 (ショップ側で登録して使う場合)."""
    return f"SVF-{short_code.upper()}"


def render_pinned_comment(
    template: str, base_url: str, platform: str, short_code: str
) -> str:
    """固定コメントのテンプレート ({LINK}/{CODE} 入り) を実際の文面にする.

    テンプレートに {LINK} が無い場合 (生成時の指示漏れ) でも、計測リンクが
    失われないよう末尾に追記する。
    """
    url = build_tracking_url(base_url, platform, short_code)
    if LINK_PLACEHOLDER in template:
        text = template.replace(LINK_PLACEHOLDER, url or "(商品URL未設定)")
    else:
        text = template.rstrip()
        if url:
            text += f"\n{url}"
    return text.replace(CODE_PLACEHOLDER, coupon_code(short_code))
