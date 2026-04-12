"""
voice/pipeline.py — Claude 스트리밍 → 문장 단위 TTS 파이프라인
흐름: 사용자 텍스트 → Claude API (streaming) → 문장 감지 → CLOVA TTS → MP3 bytes yield

핵심 설계:
- Claude 응답 전체를 기다리지 않고 문장 단위로 잘라서 TTS에 흘림
- 첫 응답 목표: 2초 이내 (짧은 첫 문장 → 즉시 TTS 전송)
- AsyncGenerator로 구현 → FastAPI WebSocket과 자연스럽게 연결
"""
import asyncio
import os
import re
from typing import AsyncGenerator, Optional

import anthropic

from voice.tts_service import synthesize

# ── 문장 종결 패턴 ─────────────────────────────────────────────────────────
# 한국어: 다/요/죠/네/군/구나 + 문장부호, 영어: .!?
_SENTENCE_END = re.compile(
    r'(?<=[.!?])\s+'                    # 영문 문장 부호 뒤 공백
    r'|(?<=[다요죠네군]\.)\s*'           # 한국어 종결 + 마침표
    r'|(?<=[다요죠네군！？])\s+'         # 한국어 종결 + 느낌표/물음표
)

STYLIST_SYSTEM = """당신은 사용자의 실제 옷장을 완벽하게 파악하고 있는 개인 전담 스타일리스트입니다.
파리·밀라노·서울 무대의 30년 경력, 날씨·체형·TPO를 꿰뚫는 현실적 스타일링이 특기입니다.

【음성 대화 규칙】
- 반말로, 친근하지만 전문가다운 어조
- 짧고 자연스럽게 — 한 번에 2~3문장 이내
- 마크다운 기호(*, #, -, **) 절대 사용 금지 — 순수 텍스트만
- 이모지 사용 금지 (TTS가 읽어버림)
- 구체적이고 실용적인 조언"""


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
    """
    버퍼에서 완성된 문장들을 추출하고 나머지(미완성)를 반환.
    반환: (완성된 문장 리스트, 남은 버퍼)
    """
    parts = _SENTENCE_END.split(buffer)
    if len(parts) <= 1:
        return [], buffer
    completed = [p.strip() for p in parts[:-1] if p.strip()]
    return completed, parts[-1]


async def stream_voice_response(
    user_message: str,
    context: Optional[dict] = None,
    speaker: str = "nara",
) -> AsyncGenerator[bytes, None]:
    """
    Claude 스트리밍 응답 → 문장 단위 CLOVA TTS → MP3 bytes를 순서대로 yield.

    사용법 (FastAPI WebSocket):
        async for mp3_chunk in stream_voice_response(text, context):
            await websocket.send_bytes(mp3_chunk)
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
                if sentence:
                    # CLOVA TTS는 동기 HTTP — run_in_executor로 스레드 풀에서 실행
                    mp3 = await loop.run_in_executor(
                        None, synthesize, sentence, speaker
                    )
                    yield mp3

    # 스트림 끝 — 버퍼에 남은 텍스트 처리
    remainder = buffer.strip()
    if remainder:
        mp3 = await loop.run_in_executor(None, synthesize, remainder, speaker)
        yield mp3
