"""
voice/pipeline.py — 하위 호환성 유지용 stub
Gemini Live 파이프라인이 제거되고 chatbot/tts.py 로 이전됨.
직접 사용 시: from chatbot.tts import clean_for_tts, synthesize_speech
"""
from chatbot.tts import (  # noqa: F401
    _SENTENCE_END,
    clean_for_tts,
    synthesize_speech,
)
