"""シーンごとの背景素材の選択.

優先順位:
1. assets/product/ にある商品写真 — 商品が映るシーン (featured/subtle) で優先使用
2. assets/broll/ にあるユーザーの動画素材 (商品の実写・生活シーンなど)
3. assets/images/ にある静止画素材 (Ken Burns 風に使用)
4. どれもなければグラデーション背景 (テロップ中心の動画になる)

素材ファイル名にキーワードを入れておくと、シーンの映像指示 (visual_direction) と
突き合わせて優先的に選ばれる。例: `desk_morning.mp4`, `product_closeup.jpg`
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Optional

VIDEO_EXTS = {".mp4", ".mov", ".webm", ".mkv"}
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}

# グラデーション背景の配色 (落ち着いたトーン)
GRADIENTS = [
    ("0x1a1a2e", "0x16213e"),
    ("0x2d132c", "0x801336"),
    ("0x1b262c", "0x0f4c75"),
    ("0x3a3845", "0x826f66"),
]


@dataclass
class SceneVisual:
    kind: Literal["video", "image", "gradient"]
    path: Optional[Path] = None
    colors: Optional[tuple[str, str]] = None


def _list_assets(directory: Path, exts: set[str]) -> list[Path]:
    if not directory.exists():
        return []
    return sorted(p for p in directory.glob("*") if p.suffix.lower() in exts)


class VisualPicker:
    def __init__(
        self,
        broll_dir: Path,
        images_dir: Path,
        product_dir: Optional[Path] = None,
        seed: Optional[int] = None,
    ):
        self.videos = _list_assets(broll_dir, VIDEO_EXTS)
        self.images = _list_assets(images_dir, IMAGE_EXTS)
        # 商品写真 (画像・動画どちらも可)
        self.product_assets = (
            _list_assets(product_dir, VIDEO_EXTS | IMAGE_EXTS) if product_dir else []
        )
        self._rng = random.Random(seed)
        self._used: set[Path] = set()
        self._product_cursor = 0

    def pick(self, visual_direction: str, product_visibility: str = "none") -> SceneVisual:
        """シーンの映像指示と商品の映り方に合う素材を選ぶ.

        - featured: 商品が主役のシーン。商品写真があれば必ずそれを使う。
        - subtle:   さりげなく映るシーン。映像指示に合う一般素材を優先し、
                    見つからなければ商品写真を使う。
        - none:     商品を映さないシーン。商品写真は使わない。
        """
        if product_visibility == "featured" and self.product_assets:
            return self._to_visual(self._next_product_asset())

        candidates = self.videos + self.images
        best = self._match_by_keyword(candidates, visual_direction) if candidates else None

        if best is None and product_visibility == "subtle" and self.product_assets:
            return self._to_visual(self._next_product_asset())

        if candidates:
            if best is None:
                unused = [c for c in candidates if c not in self._used] or candidates
                best = self._rng.choice(unused)
            self._used.add(best)
            return self._to_visual(best)

        # 一般素材ゼロ。商品が映ってよいシーンなら商品写真で埋める
        if product_visibility != "none" and self.product_assets:
            return self._to_visual(self._next_product_asset())
        return SceneVisual(kind="gradient", colors=self._rng.choice(GRADIENTS))

    def _next_product_asset(self) -> Path:
        """商品写真をローテーションで返す (同じ写真ばかりにならないように)."""
        asset = self.product_assets[self._product_cursor % len(self.product_assets)]
        self._product_cursor += 1
        return asset

    @staticmethod
    def _to_visual(path: Path) -> SceneVisual:
        kind = "video" if path.suffix.lower() in VIDEO_EXTS else "image"
        return SceneVisual(kind=kind, path=path)

    def _match_by_keyword(
        self, candidates: list[Path], direction: str
    ) -> Optional[Path]:
        """ファイル名のキーワードが映像指示に含まれる素材を探す."""
        direction_lower = (direction or "").lower()
        scored = []
        for c in candidates:
            words = c.stem.lower().replace("-", "_").split("_")
            hits = sum(1 for w in words if len(w) >= 3 and w in direction_lower)
            if hits:
                scored.append((hits, c in self._used, c))
        if not scored:
            return None
        # ヒット数が多く、未使用のものを優先
        scored.sort(key=lambda t: (-t[0], t[1]))
        return scored[0][2]
