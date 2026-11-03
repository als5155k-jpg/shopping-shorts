"""
ElevenLabs 나레이션 생성 (쇼핑쇼츠용 기본값 고정)

.env 파일(이 스크립트와 같은 폴더)에서 ELEVENLABS_API_KEY를 읽는다.
환경변수 ELEVENLABS_API_KEY가 있으면 그것을 먼저 쓴다. .env는 git에 올리지 않는다.
"""

import os
import subprocess

import requests

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

DEFAULT_VOICE_ID = "5I7B1di44aCL15NkP0jn"  # Kanna - Calm & Friendly (한국어 여성)
DEFAULT_MODEL_ID = "eleven_multilingual_v2"
DEFAULT_VOICE_SETTINGS = {
    "stability": 0.52,
    "similarity_boost": 0.57,
    "style": 0.10,
    "speed": 1.19,
    "use_speaker_boost": True,
}


def _load_api_key() -> str:
    if os.environ.get("ELEVENLABS_API_KEY"):
        return os.environ["ELEVENLABS_API_KEY"].strip()
    env_path = os.path.join(SCRIPT_DIR, ".env")
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8-sig") as f:
            for line in f:
                line = line.strip()
                if line.startswith("ELEVENLABS_API_KEY="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
    raise RuntimeError("ELEVENLABS_API_KEY를 찾지 못함 (환경변수 또는 .env 확인)")


def generate_narration(
    script_text: str,
    out_path: str,
    voice_id: str = DEFAULT_VOICE_ID,
    voice_settings: dict = None,
    trim_silence: bool = True,
) -> str:
    """대본을 나레이션 mp3로 만든다. trim_silence=True면 문장 사이 긴 무음 구간을
    ffmpeg로 압축해서 시청 이탈로 이어질 만한 공백을 줄인다."""
    key = _load_api_key()
    settings = dict(DEFAULT_VOICE_SETTINGS)
    if voice_settings:
        settings.update(voice_settings)

    r = requests.post(
        f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
        headers={"xi-api-key": key, "Content-Type": "application/json"},
        json={"text": script_text, "model_id": DEFAULT_MODEL_ID, "voice_settings": settings},
        timeout=120,
    )
    r.raise_for_status()

    if not trim_silence:
        with open(out_path, "wb") as f:
            f.write(r.content)
        return out_path

    raw_path = out_path + ".raw.mp3"
    with open(raw_path, "wb") as f:
        f.write(r.content)
    subprocess.run(
        ["ffmpeg", "-y", "-i", raw_path,
         "-af", "silenceremove=stop_periods=-1:stop_duration=0.08:stop_threshold=-35dB:stop_silence=0.02",
         out_path, "-loglevel", "error"],
        check=True,
    )
    os.remove(raw_path)
    return out_path
