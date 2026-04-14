"""
voice/router.py — Web Speech API(STT) + Claude 스트리밍 + Google TTS WebSocket 라우터
app.py에 include_router()로 통합됨

아키텍처:
  STT: 브라우저 Web Speech API → 텍스트 변환 후 서버에 전송
  LLM: Claude API (claude-sonnet-4-6) 스트리밍
  TTS: Google Cloud TTS (chatbot/tts.py)

엔드포인트:
  GET /voice     → 음성 채팅 전용 UI (레거시)
  WS  /voice/ws  → WebSocket 메인 채널

WebSocket 프로토콜:
  클라이언트 → 서버:
    { "type": "start_conversation", "context": { "wardrobe": [...], "weather_label": "..." } }
    { "type": "user_text",          "text": "사용자가 말한 텍스트" }
    { "type": "barge_in" }
    { "type": "end_conversation" }

  서버 → 클라이언트:
    { "type": "state",         "value": "listening|processing|speaking" }
    { "type": "response_text", "text": "Claude 전체 응답 텍스트" }   ← 화면 표시용
    { "type": "audio_chunk",   "data": "<base64 24kHz PCM>" }
    { "type": "done" }
    { "type": "error",         "message": "..." }
    { "type": "ping" }
"""
import asyncio
import base64
import json
import os
from typing import Optional

import anthropic
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse

from chatbot.tts import _SENTENCE_END, clean_for_tts, synthesize_speech

router = APIRouter(prefix="/voice", tags=["voice"])

_PING_SEC    = 30
_FALLBACK    = "잠깐, 다시 말씀해주세요."
_MAX_TOKENS  = 500

# ── 음성 전용 스타일리스트 시스템 프롬프트 ────────────────────────────────
_VOICE_SYSTEM = """너는 사용자의 전담 스타일리스트야.
사용자의 옷장을 완벽하게 파악하고 있어.
파리, 밀라노, 서울 무대 30년 경력으로 날씨, 체형, TPO에 맞는 현실적 스타일링이 특기야.

출력 규칙. 반드시 지켜라.
모든 답변은 순수한 한글 문장으로만 말해라.
영어 단어가 나오면 반드시 한국어 발음으로 바꿔서 말해라.
두 문장 이내로 짧게 말해라. 세 문장 이상 절대 금지.
반말로 친근하지만 전문가처럼 말해라.
목록 형식으로 나열하지 마라. 자연스럽게 이어서 말해라.
특수기호 절대 사용 금지. 별표, 대시, 밑줄, 번호목록, 불릿 전부 금지.
사용자가 말을 끊으면 이전 맥락 버리고 새로 들어온 말에만 집중해서 답해라.

올바른 예시: 오늘 쌀쌀하니까 베이지 코트에 청바지 어때. 깔끔하고 따뜻하게 입을 수 있어.
잘못된 예시: 코트 추천: 청바지 매치"""


# ── 컨텍스트 빌더 ─────────────────────────────────────────────────────────
def _build_context_str(context: Optional[dict]) -> str:
    if not context:
        return ""
    lines = []
    wardrobe = context.get("wardrobe", [])
    if wardrobe:
        items = [f"  {i.get('category','')}: {i.get('item_type','')}" for i in wardrobe]
        lines.append("내 옷장\n" + "\n".join(items))
    weather = context.get("weather_label", "")
    if weather:
        lines.append(f"오늘 날씨: {weather}")
    return "\n".join(lines) + "\n" if lines else ""


# ══════════════════════════════════════════════════════════════════════════
# HTTP 엔드포인트
# ══════════════════════════════════════════════════════════════════════════

@router.get("", response_class=HTMLResponse, name="voice_chat")
async def voice_chat_page():
    """음성 채팅 전용 페이지 (레거시 — 현재 dashboard에 통합됨)"""
    with open("voice/static/index.html", encoding="utf-8") as f:
        return f.read()


# ══════════════════════════════════════════════════════════════════════════
# WebSocket — Claude 스트리밍 + Google TTS
# ══════════════════════════════════════════════════════════════════════════

@router.websocket("/ws")
async def voice_ws(websocket: WebSocket):
    await websocket.accept()

    # ── 세션 상태 ──────────────────────────────────────────────────────
    context: dict      = {}
    state              = "idle"
    current_task: Optional[asyncio.Task] = None
    ping_task:    Optional[asyncio.Task] = None
    interrupted        = False

    # ── 유틸 ───────────────────────────────────────────────────────────
    async def _send(obj: dict):
        await websocket.send_text(json.dumps(obj, ensure_ascii=False))

    async def _set_state(s: str):
        nonlocal state
        state = s
        await _send({"type": "state", "value": s})

    async def _cancel_task(task: Optional[asyncio.Task]) -> None:
        if task and not task.done():
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):
                pass

    async def _cancel_current() -> None:
        nonlocal current_task, interrupted
        interrupted = True
        await _cancel_task(current_task)
        current_task = None

    # ── keepalive 핑 ───────────────────────────────────────────────────
    async def _ping_loop():
        try:
            while True:
                await asyncio.sleep(_PING_SEC)
                await websocket.send_text(json.dumps({"type": "ping"}))
        except (asyncio.CancelledError, Exception):
            pass

    # ── Claude 스트리밍 + TTS ──────────────────────────────────────────
    async def process_user_text(user_text: str) -> None:
        """
        Claude 스트리밍 → 문장 종결 즉시 TTS → audio_chunk 전송.
        전체 텍스트 완성 후 response_text 전송 (화면 표시용).
        """
        nonlocal interrupted
        interrupted = False

        try:
            await _set_state("processing")

            claude_client  = anthropic.AsyncAnthropic(api_key=os.getenv("CLAUDE_API_KEY"))
            context_str    = _build_context_str(context)
            system_prompt  = _VOICE_SYSTEM + ("\n\n" + context_str if context_str else "")

            text_buf        = ""
            full_text       = ""
            speaking_started = False

            async with claude_client.messages.stream(
                model="claude-sonnet-4-6",
                max_tokens=_MAX_TOKENS,
                system=system_prompt,
                messages=[{"role": "user", "content": user_text}],
            ) as stream:
                async for chunk in stream.text_stream:
                    if interrupted:
                        break

                    text_buf  += chunk
                    full_text += chunk

                    # 문장 종결 감지 → 즉시 TTS
                    while True:
                        m = _SENTENCE_END.search(text_buf)
                        if not m:
                            break
                        sentence = text_buf[: m.end()].strip()
                        text_buf = text_buf[m.end() :].strip()
                        if not sentence:
                            continue
                        cleaned = clean_for_tts(sentence)
                        if not cleaned:
                            continue
                        try:
                            if not speaking_started:
                                await _set_state("speaking")
                                speaking_started = True
                            pcm = await synthesize_speech(cleaned)
                            if pcm:
                                b64 = base64.b64encode(pcm).decode()
                                await _send({"type": "audio_chunk", "data": b64})
                        except Exception:
                            pass  # TTS 실패 시 해당 문장 스킵

            if interrupted:
                return

            # 남은 버퍼 (마침표 없이 끝나는 문장)
            if text_buf.strip():
                cleaned = clean_for_tts(text_buf.strip())
                if cleaned:
                    try:
                        if not speaking_started:
                            await _set_state("speaking")
                            speaking_started = True
                        pcm = await synthesize_speech(cleaned)
                        if pcm:
                            b64 = base64.b64encode(pcm).decode()
                            await _send({"type": "audio_chunk", "data": b64})
                    except Exception:
                        pass

            # 전체 텍스트 전송 (화면 표시용)
            if full_text:
                await _send({"type": "response_text", "text": full_text})

            await _send({"type": "done"})
            await _set_state("listening")

        except asyncio.CancelledError:
            raise

        except Exception as e:
            await _send({"type": "error", "message": f"오류: {e}. {_FALLBACK}"})
            await _set_state("listening")

    # ── 메시지 루프 ────────────────────────────────────────────────────
    try:
        ping_task = asyncio.create_task(_ping_loop())

        while True:
            raw      = await websocket.receive_text()
            msg      = json.loads(raw)
            msg_type = msg.get("type")

            # 1. 대화 시작
            if msg_type == "start_conversation":
                await _cancel_current()
                context = msg.get("context", {})
                await _set_state("listening")

            # 2. 사용자 음성 텍스트 수신 (Web Speech API 변환 결과)
            elif msg_type == "user_text":
                await _cancel_current()
                user_text = msg.get("text", "").strip()
                if not user_text:
                    continue
                current_task = asyncio.create_task(process_user_text(user_text))

            # 3. barge-in 신호
            elif msg_type == "barge_in":
                await _cancel_current()
                await _set_state("listening")

            # 4. 대화 종료
            elif msg_type == "end_conversation":
                await _cancel_current()
                context = {}
                state   = "idle"

    except WebSocketDisconnect:
        pass

    finally:
        await _cancel_task(ping_task)
        await _cancel_current()
