"""ffmpeg によるショート動画の組み立て (9:16縦型).

シーンごとに「背景素材 + テロップ + ナレーション音声」のセグメントを作り、
最後に連結して1本のmp4にする。
"""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path
from typing import Optional

from svf.media.tts import synthesize_speech
from svf.media.visuals import SceneVisual, VisualPicker
from svf.models import ProduceResult, VideoScript

# 日本語対応フォントの探索候補
FONT_CANDIDATES = [
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Bold.ttc",
    "/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc",
    "/System/Library/Fonts/Helvetica.ttc",
    "C:/Windows/Fonts/meiryob.ttc",
    "C:/Windows/Fonts/msgothic.ttc",
]


def find_font(custom: str = "") -> Optional[str]:
    if custom and Path(custom).exists():
        return custom
    for candidate in FONT_CANDIDATES:
        if Path(candidate).exists():
            return candidate
    return None


def _wrap_text(text: str, max_chars: int = 13) -> str:
    """drawtext は自動改行しないため、テロップを行に分割する."""
    lines, current = [], ""
    for ch in text:
        current += ch
        if ch in "。！？!?\n" or len(current) >= max_chars:
            lines.append(current.strip())
            current = ""
    if current.strip():
        lines.append(current.strip())
    return "\n".join(lines[:4])  # 画面に収まる行数に制限


class VideoAssembler:
    def __init__(
        self,
        width: int = 1080,
        height: int = 1920,
        fps: int = 30,
        font_path: str = "",
        tts_provider: str = "edge",
        tts_settings: Optional[dict] = None,
    ):
        self.width = width
        self.height = height
        self.fps = fps
        self.font_path = find_font(font_path)
        if self.font_path is None:
            print(
                "警告: 日本語対応フォントが見つからないため、テロップなしで生成します。"
                "fonts-noto-cjk 等をインストールするか、font_path を指定してください。"
            )
        self.tts_provider = tts_provider
        self.tts_settings = tts_settings or {}
        self._check_ffmpeg()

    @staticmethod
    def _check_ffmpeg() -> None:
        try:
            subprocess.run(
                ["ffmpeg", "-version"], capture_output=True, check=True
            )
        except (FileNotFoundError, subprocess.CalledProcessError) as e:
            raise RuntimeError(
                "ffmpeg が見つかりません。インストールしてください "
                "(macOS: brew install ffmpeg / Ubuntu: apt install ffmpeg)"
            ) from e

    def produce(
        self,
        script: VideoScript,
        picker: VisualPicker,
        audio_dir: Path,
        output_dir: Path,
        tts_voice: str = "",
    ) -> ProduceResult:
        """台本1本をmp4に組み立てる."""
        if not script.scenes:
            raise ValueError(
                f"台本 {script.script_id} にシーンがありません。動画を生成できません。"
            )
        output_dir.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="svf_") as tmp:
            tmp_dir = Path(tmp)
            segments = []
            for scene in script.scenes:
                duration = max(scene.end_seconds - scene.start_seconds, 0.5)
                narration_path = None
                if scene.narration.strip():
                    narration_path = synthesize_speech(
                        scene.narration,
                        audio_dir / f"{script.script_id}_s{scene.index}.mp3",
                        language=script.language,
                        voice=tts_voice,
                        provider=self.tts_provider,
                        **self.tts_settings,
                    )
                visual = picker.pick(scene.visual_direction, scene.product_visibility)
                seg = tmp_dir / f"seg_{scene.index:03d}.mp4"
                self._render_segment(
                    visual, scene.on_screen_text, duration, narration_path, seg, tmp_dir
                )
                segments.append(seg)

            video_path = output_dir / f"{script.script_id}.mp4"
            self._concat(segments, tmp_dir, video_path)

        return ProduceResult(
            script_id=script.script_id,
            video_path=str(video_path),
            duration_seconds=script.total_seconds,
        )

    def _render_segment(
        self,
        visual: SceneVisual,
        on_screen_text: str,
        duration: float,
        narration: Optional[Path],
        out_path: Path,
        tmp_dir: Path,
    ) -> None:
        """1シーン分のセグメントを作る."""
        w, h, fps = self.width, self.height, self.fps
        cmd: list[str] = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error"]

        # --- 映像入力 ---
        if visual.kind == "video":
            cmd += ["-stream_loop", "-1", "-t", f"{duration}", "-i", str(visual.path)]
            vf = (
                f"scale={w}:{h}:force_original_aspect_ratio=increase,"
                f"crop={w}:{h},fps={fps}"
            )
        elif visual.kind == "image":
            cmd += ["-loop", "1", "-t", f"{duration}", "-i", str(visual.path)]
            # ゆっくりズームして静止画でも動きを出す (Ken Burns)
            frames = int(duration * fps)
            vf = (
                f"scale={w * 2}:{h * 2}:force_original_aspect_ratio=increase,"
                f"crop={w * 2}:{h * 2},"
                f"zoompan=z='min(zoom+0.0008,1.15)':d={frames}:s={w}x{h}:fps={fps}"
            )
        else:  # gradient
            c1, c2 = visual.colors or ("0x1a1a2e", "0x16213e")
            cmd += [
                "-f", "lavfi", "-t", f"{duration}",
                "-i",
                f"gradients=size={w}x{h}:c0={c1}:c1={c2}:speed=0.02:rate={fps}",
            ]
            vf = "null"

        # --- 音声入力 (ナレーション or 無音) ---
        if narration is not None:
            cmd += ["-i", str(narration)]
        else:
            cmd += ["-f", "lavfi", "-t", f"{duration}", "-i", "anullsrc=r=44100:cl=stereo"]

        # --- テロップ ---
        # テキストは textfile= で渡す。inline の text= はクォート・カンマ・
        # バックスラッシュを含むテロップで filter 文字列が壊れるため使わない
        # (Claudeが生成する文には任意の記号が入りうる)。
        if on_screen_text.strip() and self.font_path:
            text_file = tmp_dir / f"{out_path.stem}_text.txt"
            text_file.write_text(_wrap_text(on_screen_text), encoding="utf-8")
            vf += (
                f",drawtext=fontfile='{self.font_path}':textfile='{text_file.as_posix()}':"
                f"fontsize=64:fontcolor=white:borderw=6:bordercolor=black:"
                f"x=(w-text_w)/2:y=h*0.72:line_spacing=16"
            )

        cmd += [
            "-filter_complex", f"[0:v]{vf}[v]",
            "-map", "[v]", "-map", "1:a",
            "-t", f"{duration}",
            "-c:v", "libx264", "-preset", "fast", "-pix_fmt", "yuv420p",
            "-r", f"{fps}",
            "-c:a", "aac", "-ar", "44100", "-ac", "2",
            "-af", "apad",  # ナレーションが尺より短い場合は無音で埋める
            "-shortest",
            str(out_path),
        ]
        self._run(cmd)

    def _concat(self, segments: list[Path], tmp_dir: Path, out_path: Path) -> None:
        list_file = tmp_dir / "concat.txt"
        list_file.write_text(
            "".join(f"file '{s.as_posix()}'\n" for s in segments), encoding="utf-8"
        )
        self._run(
            [
                "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                "-f", "concat", "-safe", "0", "-i", str(list_file),
                "-c", "copy", str(out_path),
            ]
        )

    @staticmethod
    def _run(cmd: list[str]) -> None:
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"ffmpeg エラー:\n{result.stderr[-2000:]}")
