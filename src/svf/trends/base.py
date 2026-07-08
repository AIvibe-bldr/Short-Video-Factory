"""トレンド収集の共通インターフェース."""

from __future__ import annotations

import json
import re
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path

from svf.models import TrendItem


def extract_hashtags(text: str) -> list[str]:
    """テキストからハッシュタグを抽出する."""
    return re.findall(r"#([^\s#,、。]+)", text or "")


class TrendCollector(ABC):
    """各プラットフォームのトレンド収集の基底クラス."""

    platform: str = ""

    @abstractmethod
    def collect(self, query: str = "", limit: int = 20) -> list[TrendItem]:
        """再生数の高いショート動画のメタデータを収集する.

        Args:
            query: 検索キーワード (商品ジャンルなど)。空なら全体トレンド。
            limit: 取得件数の上限。
        """


def save_trends(items: list[TrendItem], out_dir: Path) -> Path:
    """収集結果をJSONで保存する."""
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    path = out_dir / f"trends_{stamp}.json"
    path.write_text(
        json.dumps([i.model_dump() for i in items], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path


def latest_trends_path(trends_dir: Path) -> Path:
    """最新の収集結果ファイルのパスを返す (curate で上書きするため)."""
    files = sorted(trends_dir.glob("trends_*.json"))
    if not files:
        raise FileNotFoundError(
            f"{trends_dir} に収集結果がありません。先に `svf research` を実行してください。"
        )
    return files[-1]


def load_latest_trends(trends_dir: Path) -> list[TrendItem]:
    """最新の収集結果を読み込む."""
    path = latest_trends_path(trends_dir)
    data = json.loads(path.read_text(encoding="utf-8"))
    return [TrendItem(**d) for d in data]


def overwrite_trends(items: list[TrendItem], path: Path) -> None:
    """既存の収集結果ファイルを人間の評価 (good/bad) 付きで上書きする."""
    path.write_text(
        json.dumps([i.model_dump() for i in items], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
