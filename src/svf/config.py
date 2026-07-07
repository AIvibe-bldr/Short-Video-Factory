"""設定・商品情報・スタイルプリセットの読み込み."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Optional

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = PROJECT_ROOT / "config"
STYLES_DIR = CONFIG_DIR / "styles"
DATA_DIR = PROJECT_ROOT / "data"
OUTPUT_DIR = PROJECT_ROOT / "output"
ASSETS_DIR = PROJECT_ROOT / "assets"


class Product(BaseModel):
    """紹介する商品の情報."""

    name: str
    category: str = ""
    price: str = ""
    url: str = ""
    target_audience: str = ""
    selling_points: list[str] = Field(default_factory=list)
    usage_scenes: list[str] = Field(default_factory=list)  # 商品が使われる生活シーン
    brand_tone: str = ""  # ブランドの雰囲気・トーン
    ng_expressions: list[str] = Field(default_factory=list)  # 使ってはいけない表現


class StylePreset(BaseModel):
    """動画スタイルのプリセット (「可愛い女の子が紹介」「手元だけ」など)."""

    name: str
    display_name: str = ""
    description: str = ""
    language: str = "ja"
    presenter: str = ""  # 出演者の設定 (いなければ空)
    tone: str = ""  # 話し方・テンションの指定
    visual_style: str = ""  # 映像全体の雰囲気
    product_placement: str = "featured"  # featured / subtle / background
    camera_direction: str = ""  # 撮影・構図の指針
    duration_seconds: float = 30.0
    tts_voice: str = ""  # 音声合成のボイス指定 (空ならデフォルト)
    extra_instructions: str = ""  # 台本生成への追加指示


class Settings(BaseModel):
    """全体設定."""

    anthropic_api_key: str = ""
    youtube_api_key: str = ""
    instagram_access_token: str = ""
    instagram_business_account_id: str = ""
    elevenlabs_api_key: str = ""
    voicevox_url: str = "http://localhost:50021"
    heygen_api_key: str = ""
    claude_model: str = "claude-opus-4-8"
    region_code: str = "JP"  # トレンド収集の対象地域
    video_width: int = 1080
    video_height: int = 1920
    fps: int = 30

    @classmethod
    def load(cls) -> "Settings":
        overrides: dict[str, Any] = {}
        settings_file = CONFIG_DIR / "settings.yaml"
        if settings_file.exists():
            overrides = yaml.safe_load(settings_file.read_text(encoding="utf-8")) or {}
        return cls(
            anthropic_api_key=os.getenv("ANTHROPIC_API_KEY", ""),
            youtube_api_key=os.getenv("YOUTUBE_API_KEY", ""),
            instagram_access_token=os.getenv("INSTAGRAM_ACCESS_TOKEN", ""),
            instagram_business_account_id=os.getenv("INSTAGRAM_BUSINESS_ACCOUNT_ID", ""),
            elevenlabs_api_key=os.getenv("ELEVENLABS_API_KEY", ""),
            voicevox_url=os.getenv("VOICEVOX_URL", "http://localhost:50021"),
            heygen_api_key=os.getenv("HEYGEN_API_KEY", ""),
            **overrides,
        )


def load_product(path: Optional[Path] = None) -> Product:
    """商品情報を読み込む。指定がなければ config/product.yaml を使う."""
    if path is None:
        path = CONFIG_DIR / "product.yaml"
        if not path.exists():
            example = CONFIG_DIR / "product.example.yaml"
            raise FileNotFoundError(
                f"{path} がありません。{example} をコピーして商品情報を記入してください。"
            )
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return Product(**data)


def load_style(name: str) -> StylePreset:
    """スタイルプリセットを名前で読み込む."""
    path = STYLES_DIR / f"{name}.yaml"
    if not path.exists():
        available = ", ".join(sorted(p.stem for p in STYLES_DIR.glob("*.yaml")))
        raise FileNotFoundError(f"スタイル '{name}' が見つかりません。利用可能: {available}")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    data.setdefault("name", name)
    return StylePreset(**data)


def list_styles() -> list[str]:
    return sorted(p.stem for p in STYLES_DIR.glob("*.yaml"))
