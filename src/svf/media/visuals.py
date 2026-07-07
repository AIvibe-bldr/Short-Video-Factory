"""シーンごとの背景素材の選択.

優先順位:
1. assets/broll/ にあるユーザーの動画素材 (商品の実写・生活シーンなど)
2. assets/images/ にある静止画素材 (Ken Burns 風に使用)
3. どちらもなければグラデーション背景 (テロップ中心の動画になる)

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


class VisualPicker:
    def __init__(self, broll_dir: Path, images_dir: Path, seed: Optional[int] = None):
        self.videos = sorted(
            p for p in broll_dir.glob("*") if p.suffix.lower() in VIDEO_EXTS
        ) if broll_dir.exists() else []
        self.images = sorted(
            p for p in images_dir.glob("*") if p.suffix.lower() in IMAGE_EXTS
        ) if images_dir.exists() else []
        self._rng = random.Random(seed)
        self._used: set[Path] = set()

    def pick(self, visual_direction: str) -> SceneVisual:
        """シーンの映像指示に合う素材を選ぶ."""
        candidates = self.videos + self.images
        if candidates:
            best = self._match_by_keyword(candidates, visual_direction)
            if best is None:
                unused = [c for c in candidates if c not in self._used] or candidates
                best = self._rng.choice(unused)
            self._used.add(best)
            kind = "video" if best.suffix.lower() in VIDEO_EXTS else "image"
            return SceneVisual(kind=kind, path=best)
        return SceneVisual(kind="gradient", colors=self._rng.choice(GRADIENTS))

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
