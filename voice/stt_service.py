"""
voice/stt_service.py — Whisper 로컬 STT
- small 모델 지연 로드 (최초 호출 시 다운로드, 이후 캐시)
- 오디오 bytes → 텍스트 반환
"""
import os
import tempfile
import whisper

_model = None


def _ensure_model():
    global _model
    if _model is None:
        _model = whisper.load_model("small")
    return _model


def transcribe(audio_bytes: bytes, lang: str = "ko") -> str:
    """
    오디오 bytes → 텍스트 (한국어 기본)

    audio_bytes: 브라우저 MediaRecorder가 보낸 webm/opus bytes
    lang: Whisper 언어 코드 (None이면 자동 감지)
    """
    model = _ensure_model()

    suffix = ".webm"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
        f.write(audio_bytes)
        tmp_path = f.name

    try:
        result = model.transcribe(tmp_path, language=lang)
        return result["text"].strip()
    finally:
        os.unlink(tmp_path)
