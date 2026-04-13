"""
voice/pipeline.py — Claude 스트리밍 → 문장 단위 TTS 파이프라인
흐름: 사용자 텍스트 → Claude API (streaming) → 문장 감지 → Google TTS → MP3 bytes yield

핵심 설계:
- Claude 응답 전체를 기다리지 않고 문장 단위로 잘라서 TTS에 흘림
- 첫 응답 목표: 2초 이내 (짧은 첫 문장 → 즉시 TTS 전송)
- AsyncGenerator로 구현 → FastAPI WebSocket과 자연스럽게 연결
- TTS 전송 전 텍스트 정제: 언더바, 이모지, 마크다운 기호 제거
"""
import asyncio
import os
import re
from typing import AsyncGenerator, Optional

import anthropic

from voice.tts_service import synthesize

# ── 이모지 제거 정규식 ─────────────────────────────────────────────
_EMOJI_RE = re.compile(
    "["
    "\U0001F600-\U0001F64F"   # 표정 이모지
    "\U0001F300-\U0001F5FF"   # 기호/지도
    "\U0001F680-\U0001F6FF"   # 교통/지도
    "\U0001F700-\U0001F77F"   # 연금술 기호
    "\U0001F780-\U0001F7FF"
    "\U0001F800-\U0001F8FF"
    "\U0001F900-\U0001F9FF"   # 보충 기호
    "\U0001FA00-\U0001FA6F"
    "\U0001FA70-\U0001FAFF"
    "\U00002702-\U000027B0"   # Dingbats
    "\U000024C2-\U0001F251"
    "\U0000200B-\U0000200F"   # 제로폭 공백 등
    "]+",
    flags=re.UNICODE,
)

# ── 문장 종결 패턴 ─────────────────────────────────────────────────
_SENTENCE_END = re.compile(
    r'(?<=[.!?])\s+'
    r'|(?<=[다요죠네군]\.)\s*'
    r'|(?<=[다요죠네군！？])\s+'
)

STYLIST_SYSTEM = """당신은 사용자의 실제 옷장을 완벽하게 파악하고 있는 개인 전담 스타일리스트입니다.
파리·밀라노·서울 무대의 30년 경력, 날씨·체형·TPO를 꿰뚫는 현실적 스타일링이 특기입니다.

【음성 대화 규칙 — 반드시 지킬 것】
- 반말로, 친근하지만 전문가다운 어조
- 짧고 자연스럽게 말하듯 — 한 번에 2~3문장 이내
- 마크다운 기호(*, #, -, **, __, ~, `) 절대 사용 금지 — 순수 텍스트만
- 이모지 사용 금지 — TTS가 그대로 읽어버림
- 언더바(_), 별표(*), 대시(-) 로 강조하지 말 것
- 번호 목록(1. 2. 3.) 사용 금지 — 자연스러운 문장으로 말할 것
- 구체적이고 실용적인 조언"""


def _clean_for_tts(text: str) -> str:
    """
    TTS로 보내기 전 텍스트 정제.
    읽으면 어색한 기호·이모지·마크다운을 제거해서 자연스러운 발화로 만든다.
    """
    # 이모지 제거
    text = _EMOJI_RE.sub("", text)
    # 마크다운 강조 기호 제거 (**굵게**, *기울임*, __언더바__, ~~취소선~~, `코드`)
    text = re.sub(r"\*{1,3}|_{1,3}|~~|`", "", text)
    # 마크다운 헤더 제거 (# 제목)
    text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)
    # 리스트 마커 제거 (- 항목, * 항목, 1. 항목)
    text = re.sub(r"^\s*[-*•]\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"^\s*\d+\.\s+", "", text, flags=re.MULTILINE)
    # 괄호로 감싼 URL 제거
    text = re.sub(r"\[([^\]]+)\]\([^\)]+\)", r"\1", text)
    # 남은 꺾쇠/대괄호 제거
    text = re.sub(r"[<>\[\]]", "", text)
    # 여러 공백 → 하나
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _build_context_str(context: Optional[dict]) -> str:
    if not context:
        return ""
    lines = []
    wardrobe = context.get("wardrobe", [])
    if wardrobe:
        items = [f"  - {i.get('category','')}: {i.get('item_type','')}" for i in wardrobe]
        lines.append("【내 옷장】\n" + "\n".join(items))
    weather = context.get("weather_label", "")
    if weather:
        lines.append(f"【오늘 날씨】 {weather}")
    return "\n".join(lines) + "\n" if lines else ""


def _split_on_sentence_boundary(buffer: str) -> tuple[list[str], str]:
    parts = _SENTENCE_END.split(buffer)
    if len(parts) <= 1:
        return [], buffer
    completed = [p.strip() for p in parts[:-1] if p.strip()]
    return completed, parts[-1]


async def stream_voice_response(
    user_message: str,
    context: Optional[dict] = None,
    speaker: str = "ko-KR-Wavenet-A",
) -> AsyncGenerator[bytes, None]:
    """
    Claude 스트리밍 응답 → 문장 단위 Google TTS → MP3 bytes를 순서대로 yield.

    동작 흐름:
      1. Claude API를 스트리밍 모드로 호출
      2. 텍스트 청크가 쌓이면서 문장 종결 패턴(. ! ? 다. 요. 등)을 감지
      3. 문장이 완성될 때마다 _clean_for_tts() → Google TTS → MP3
      4. MP3 바이트를 WebSocket으로 즉시 yield → 브라우저에서 순차 재생
    """
    client = anthropic.AsyncAnthropic(api_key=os.getenv("CLAUDE_API_KEY"))
    loop = asyncio.get_event_loop()

    context_str = _build_context_str(context)
    full_prompt = f"{context_str}{user_message}"

    buffer = ""

    async with client.messages.stream(
        model="claude-sonnet-4-6",
        max_tokens=300,
        system=STYLIST_SYSTEM,
        messages=[{"role": "user", "content": full_prompt}],
    ) as stream:
        async for chunk in stream.text_stream:
            buffer += chunk

            sentences, buffer = _split_on_sentence_boundary(buffer)
            for sentence in sentences:
                clean = _clean_for_tts(sentence)
                if clean:
                    mp3 = await loop.run_in_executor(
                        None, synthesize, clean, speaker
                    )
                    yield mp3

    # 스트림 끝 — 버퍼 나머지 처리
    remainder = _clean_for_tts(buffer)
    if remainder:
        mp3 = await loop.run_in_executor(None, synthesize, remainder, speaker)
        yield mp3
