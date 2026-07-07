"""ナレーション音声の合成.

プロバイダー:
- edge   : Microsoft Edge TTS (無料・キー不要・多言語) ← デフォルト
- voicevox: VOICEVOX (無料・日本語。ローカルエンジン必須)
- elevenlabs: ElevenLabs (高品質・要APIキー)
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import httpx

DEFAULT_VOICES = {
    "ja": "ja-JP-NanamiNeural",
    "en": "en-US-AriaNeural",
}


def synthesize_speech(
    text: str,
    out_path: Path,
    language: str = "ja",
    voice: str = "",
    provider: str = "edge",
    voicevox_url: str = "http://localhost:50021",
    elevenlabs_api_key: str = "",
) -> Path:
    """テキストを音声ファイル (mp3/wav) にする."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if provider == "voicevox":
        return _voicevox(text, out_path, voice or "1", voicevox_url)
    if provider == "elevenlabs":
        return _elevenlabs(text, out_path, voice, elevenlabs_api_key)
    return _edge(text, out_path, voice or DEFAULT_VOICES.get(language, DEFAULT_VOICES["ja"]))


def _edge(text: str, out_path: Path, voice: str) -> Path:
    import edge_tts

    async def run() -> None:
        communicate = edge_tts.Communicate(text, voice)
        await communicate.save(str(out_path))

    asyncio.run(run())
    return out_path


def _voicevox(text: str, out_path: Path, speaker: str, base_url: str) -> Path:
    with httpx.Client(base_url=base_url, timeout=60) as client:
        q = client.post("/audio_query", params={"text": text, "speaker": speaker})
        q.raise_for_status()
        audio = client.post(
            "/synthesis", params={"speaker": speaker}, json=q.json()
        )
        audio.raise_for_status()
    wav_path = out_path.with_suffix(".wav")
    wav_path.write_bytes(audio.content)
    return wav_path


def _elevenlabs(text: str, out_path: Path, voice_id: str, api_key: str) -> Path:
    if not api_key:
        raise ValueError("ELEVENLABS_API_KEY が設定されていません。")
    voice_id = voice_id or "21m00Tcm4TlvDq8ikWAM"
    r = httpx.post(
        f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
        headers={"xi-api-key": api_key},
        json={"text": text, "model_id": "eleven_multilingual_v2"},
        timeout=120,
    )
    r.raise_for_status()
    out_path.write_bytes(r.content)
    return out_path
