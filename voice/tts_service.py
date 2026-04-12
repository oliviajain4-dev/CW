"""
voice/tts_service.py — Google Cloud Text-to-Speech
- 텍스트 → MP3 bytes 반환
- GOOGLE_TTS_API_KEY 환경변수 필요 (.env에 등록)
- 한국어 WaveNet 음성 사용 (고품질)
"""
import base64
import os
import requests

GOOGLE_TTS_URL = "https://texttospeech.googleapis.com/v1/text:synthesize"

# 사용 가능한 한국어 화자
# ko-KR-Wavenet-A : 여성 (기본)
# ko-KR-Wavenet-B : 여성 2
# ko-KR-Wavenet-C : 남성
# ko-KR-Wavenet-D : 남성 2
# ko-KR-Standard-A: 여성 (저비용)
DEFAULT_SPEAKER = "ko-KR-Wavenet-A"


def synthesize(text: str, speaker: str = DEFAULT_SPEAKER, speed: float = 1.0) -> bytes:
    """
    텍스트 → MP3 bytes (Google Cloud TTS)

    text:    변환할 텍스트
    speaker: 화자 코드 (ko-KR-Wavenet-A/B/C/D 또는 ko-KR-Standard-A)
    speed:   발화 속도 0.25~4.0, 1.0=기본
    반환:    MP3 bytes — 브라우저 Audio API로 바로 재생 가능
    """
    api_key = os.getenv("GOOGLE_TTS_API_KEY")
    if not api_key:
        raise RuntimeError(
            "GOOGLE_TTS_API_KEY 환경변수가 없습니다. .env 파일을 확인하세요."
        )

    payload = {
        "input": {"text": text},
        "voice": {
            "languageCode": "ko-KR",
            "name": speaker,
        },
        "audioConfig": {
            "audioEncoding": "MP3",
            "speakingRate": speed,
        },
    }

    resp = requests.post(
        f"{GOOGLE_TTS_URL}?key={api_key}",
        json=payload,
        timeout=10,
    )
    resp.raise_for_status()
    audio_b64 = resp.json()["audioContent"]
    return base64.b64decode(audio_b64)
