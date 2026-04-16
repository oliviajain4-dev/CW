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
    { "type": "start_conversation", "context": { "wardrobe": [...], "weather_label": "...", "user_profile": {...} } }
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

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse

from chatbot.llm_client import stream_chatbot_response
from chatbot.tts import _SENTENCE_END, clean_for_tts, synthesize_speech

router = APIRouter(prefix="/voice", tags=["voice"])

_PING_SEC    = 30
_FALLBACK    = "잠깐, 다시 말씀해주세요."
_MAX_TOKENS  = 500

SECTIONS = ["GREETING", "FOLLOWUP"]

_SENSITIVITY_MAP = {
    1: "추위를 많이 타는 편",
    2: "약간 추위 타는 편",
    3: "보통",
    4: "약간 더위 타는 편",
    5: "더위를 많이 타는 편",
}

# ── 음성 전용 스타일리스트 시스템 프롬프트 ────────────────────────────────
_VOICE_SYSTEM = """너는 사용자의 전담 스타일리스트야.
사용자의 옷장을 완벽하게 파악하고 있어.
파리, 밀라노, 서울 무대 30년 경력으로 날씨, 체형, 티피오에 맞는 현실적 스타일링이 특기야.

출력 규칙. 반드시 지켜라.
모든 답변은 순수한 한국어 문장으로만 작성해라. 알파벳 단 한 글자도 절대 금지.
영어 의류·색상·소재·스타일 단어는 전부 한국어로 바꿔라.
  예: t-shirt→티셔츠, jeans→청바지, cardigan→가디건, coat→코트, jacket→재킷,
      denim jacket→청자켓, hoodie→후드티, sweatshirt→맨투맨, sneakers→스니커즈,
      black→블랙, white→화이트, beige→베이지, navy→네이비, casual→캐주얼, basic→베이직
자연스럽고 친근한 문장으로 말해라. 너무 짧지 않게, 필요한 정보를 충분히 담아라.
반말로 친근하지만 전문가처럼 말해라.
목록 형식으로 나열하지 마라. 자연스럽게 이어서 말해라.
특수기호 절대 금지: 별표(*), 대시(-/—), 밑줄(_), 번호목록, 불릿, 괄호(()), 슬래시(/) 전부 금지.
숫자 뒤 단위도 한국어로: °C→도, %→퍼센트.
사용자가 말을 끊으면 이전 맥락 버리고 새로 들어온 말에만 집중해서 답해라.

올바른 예시: 오늘 쌀쌀하니까 베이지 코트에 청바지 어때. 깔끔하고 따뜻하게 입을 수 있어.
잘못된 예시: coat 추천: jeans 매치

다양한 날씨 표현을 써라. '선선'은 절대 금지. 대신 '서늘', '쾌청', '포근', '살짝 쌀쌀', '제법 따뜻' 등 번갈아 사용.
같은 표현을 두 번 이상 연속으로 쓰지 마라.
문장은 2~3개 단위로 끊어서 말해라. 질문은 한 번에 하나만.
코디를 제안한 뒤 반드시 선택지를 줘라: '이 코디로 할래? 아니면 다른 스타일 원해?'
날씨 언급은 대화 시작에서 1번만. 이후 대화에서 날씨 반복 금지.
사용자가 제안을 수락하면 짧게 마무리하고 추가 팁 하나 줘."""


# ── 컨텍스트 빌더 ─────────────────────────────────────────────────────────
def _build_context_str(context: Optional[dict]) -> str:
    if not context:
        return ""
    lines = []
    wardrobe = context.get("wardrobe", [])
    if wardrobe:
        items = [f"  {i.get('category','')}: {i.get('item_type','')}" for i in wardrobe]
        lines.append("내 옷장\n" + "\n".join(items))

    weather = context.get("weather", {})
    weather_label = context.get("weather_label", "")
    if weather_label or weather:
        w_lines = []
        if weather_label:
            w_lines.append(f"  날씨 요약: {weather_label}")
        if weather:
            morning   = weather.get("morning", {})
            afternoon = weather.get("afternoon", {})
            evening   = weather.get("evening", {})
            if morning.get("feels_like") is not None:
                w_lines.append(
                    f"  체감온도: 아침 {morning['feels_like']}°C / "
                    f"낮 {afternoon.get('feels_like','?')}°C / "
                    f"저녁 {evening.get('feels_like','?')}°C"
                )
            reh = morning.get("reh")
            if reh is not None:
                w_lines.append(f"  습도: {reh}%")
        lines.append("오늘 날씨\n" + "\n".join(w_lines))

    profile = context.get("user_profile", {})
    if profile:
        profile_lines = []
        if profile.get("name"):
            profile_lines.append(f"이름: {profile['name']}")
        if profile.get("height"):
            profile_lines.append(f"키: {profile['height']}cm")
        if profile.get("body_type"):
            profile_lines.append(f"체형: {profile['body_type']}")
        if profile.get("style_pref"):
            profile_lines.append(f"선호 스타일: {profile['style_pref']}")
        if profile.get("gender"):
            profile_lines.append(f"성별: {profile['gender']}")
        sens = profile.get("sensitivity")
        if sens:
            sens_map = {1: "추위를 많이 타는 편", 2: "약간 추위 타는 편", 3: "보통",
                        4: "약간 더위 타는 편", 5: "더위를 많이 타는 편"}
            profile_lines.append(f"추위 민감도: {sens_map.get(int(sens), '보통')}")
        if profile_lines:
            lines.append("사용자 정보\n  " + "\n  ".join(profile_lines))

    outfit_comment = context.get("outfit_comment", "")
    if outfit_comment:
        # 앞 300자만 — TTS 길이 제한
        lines.append("화면에 표시된 오늘의 코디 코멘트 (이 내용을 참고해서 음성으로 요약)\n  "
                     + outfit_comment[:300].replace("\n", " "))

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

    messages:          list = []
    pending_sections:  list = []

    # 문자열 상태는 mutable container로 감싸서 중첩 함수에서 수정 가능하게 함
    session = {
        "user_name":         "",
        "sensitivity_label": "보통",
        "partial_text":      "",   # 스트리밍 중 실시간 누적 텍스트
        "interrupted_ctx":   "",   # barge-in 시 저장된 중단 내용
    }

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
        # 중단 시 스트리밍 중이던 내용 저장 (barge-in 이후 자연스러운 대화 재개용)
        if session["partial_text"]:
            session["interrupted_ctx"] = session["partial_text"]
            session["partial_text"] = ""
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

    # ── 섹션 기반 대화 진행 ────────────────────────────────────────────
    async def process_section(section: str, user_input: str = "", forced: bool = False, interrupted_ctx: str = "") -> None:
        nonlocal interrupted

        user_name         = session["user_name"]
        sensitivity_label = session["sensitivity_label"]

        outfit_comment = context.get("outfit_comment", "")
        section_prompts = {
            "GREETING": (
                f"{'안녕, ' + session['user_name'] + '! ' if session['user_name'] else '안녕! '}"
                "다음 순서대로 자연스럽게 말해. "
                "① 이름을 불러주면서 짧고 친근하게 인사. "
                "② 오늘 날씨 — 아침/낮/저녁 체감온도를 자연스럽게 섞어서 한두 마디. '선선'은 절대 금지, 대신 '서늘', '쾌청', '포근', '살짝 쌀쌀' 등 다양하게. "
                + (
                    "③ 화면에 표시된 코디 코멘트를 참고해서 핵심 코디를 친근하게 요약해줘. 옷장 아이템 이름 직접 언급. "
                    if outfit_comment else
                    "③ 오늘 추천 코디 — 옷장 아이템 이름 직접 언급하면서 구체적으로 제안. "
                )
                + "④ 선택지 제시: '이 코디로 할래? 아니면 오늘 다른 무드 원해?' "
                "문장은 2~3개씩 끊어서 말해. 질문은 마지막에 하나만."
            ),
            "FOLLOWUP": (
                "사용자 말에 자연스럽게 먼저 반응하고, 필요하면 코디 수정이나 추가 팁을 줘. "
                "날씨 얘기는 이미 했으니 반복하지 마. "
                "사용자가 코디 수락하면 짧게 마무리하고 팁 하나 더 줘. "
                "사용자가 다른 스타일 원하면 옷장 기반으로 다시 제안. "
                "같은 말 반복 절대 금지."
            ),
        }

        interrupted = False

        try:
            await _set_state("processing")
            context_str = _build_context_str(context)
            system      = _VOICE_SYSTEM + ("\n\n" + context_str if context_str else "")
            weather_label = context.get("weather_label", "")

            if user_input and not forced:
                # barge-in으로 중단된 내용이 있으면 메시지 이력에 추가 (Claude 컨텍스트용)
                if interrupted_ctx:
                    messages.append({"role": "assistant", "content": interrupted_ctx})
                    task_prompt = (
                        f"사용자가 '{user_input}'라고 말했어. "
                        "이 질문에 먼저 자연스럽게 답해줘. "
                        "답변이 끝나면 아까 하던 말을 자연스럽게 이어서 마무리해줘. "
                        "이미 한 말은 반복하지 말고 이어서 계속해."
                    )
                else:
                    task_prompt = (
                        f"사용자가 '{user_input}'라고 했어. 이 말에 먼저 자연스럽게 답하고, "
                        f"바로 이어서 {section_prompts[section]}"
                    )
                messages.append({"role": "user", "content": user_input})
            else:
                task_prompt = section_prompts[section]

            if section == "GREETING" and weather_label:
                task_prompt = f"현재 날씨 정보: {weather_label}. \n" + task_prompt

            call_messages = list(messages) + [{"role": "user", "content": task_prompt}]

            text_buf         = ""
            full_text        = ""
            speaking_started = False

            session["partial_text"] = ""  # 스트리밍 시작 전 초기화
            async for chunk in stream_chatbot_response(system, call_messages, max_tokens=_MAX_TOKENS):
                if interrupted:
                    break
                text_buf  += chunk
                full_text += chunk
                session["partial_text"] = full_text  # 실시간 업데이트 (barge-in 시 저장용)

                while True:
                    m = _SENTENCE_END.search(text_buf)
                    if not m:
                        break
                    sentence = text_buf[: m.end()].strip()
                    text_buf = text_buf[m.end():].strip()
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
                            await _send({"type": "audio_chunk", "data": base64.b64encode(pcm).decode()})
                    except Exception:
                        pass

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
                            await _send({"type": "audio_chunk", "data": base64.b64encode(pcm).decode()})
                    except Exception:
                        pass

            if full_text:
                await _send({"type": "response_text", "text": full_text})
                messages.append({"role": "assistant", "content": full_text})
            session["partial_text"] = ""  # 스트리밍 완료 후 초기화

            await _send({"type": "done"})

            if section in pending_sections:
                pending_sections.remove(section)

            if pending_sections and not interrupted and section in ["GREETING", "WEATHER"]:
                await _set_state("listening")
                asyncio.create_task(process_section(pending_sections[0], forced=True))
            else:
                await _set_state("listening")

        except asyncio.CancelledError:
            raise
        except Exception as e:
            session["partial_text"] = ""
            await _send({"type": "error", "message": f"오류: {e}. {_FALLBACK}"})
            await _set_state("listening")

    # ── 사용자 발화 처리 (barge-in → 현재 섹션 이어서) ─────────────────
    async def process_user_text(user_text: str) -> None:
        nonlocal interrupted
        interrupted = False
        # barge-in으로 저장된 중단 내용 꺼내기 (한 번 쓰고 지움)
        interrupted_ctx = session.get("interrupted_ctx", "")
        session["interrupted_ctx"] = ""
        current = pending_sections[0] if pending_sections else "FOLLOWUP"
        await process_section(current, user_input=user_text, forced=False, interrupted_ctx=interrupted_ctx)

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
                messages.clear()
                prev = msg.get("prev_messages", [])
                if prev and isinstance(prev, list):
                    messages.extend(prev[-20:])

                profile = context.get("user_profile", {})
                session["user_name"]         = profile.get("name", "")
                sens_raw = profile.get("sensitivity", 3)
                session["sensitivity_label"] = _SENSITIVITY_MAP.get(int(sens_raw), "보통")

                skip_greeting = msg.get("skip_greeting", False)
                if skip_greeting:
                    # 수석 디자이너 TTS가 이미 코디를 소개함 → GREETING 생략, 바로 듣기
                    pending_sections[:] = []
                    await _set_state("listening")
                else:
                    pending_sections[:] = ["GREETING"]
                    current_task = asyncio.create_task(process_section("GREETING"))

            # 2. 사용자 음성 텍스트 수신 (Web Speech API 변환 결과)
            elif msg_type == "user_text":
                text = msg.get("text", "").strip()
                if not text:
                    continue
                # _cancel_current: partial_text → interrupted_ctx 자동 저장
                await _cancel_current()
                current_task = asyncio.create_task(process_user_text(text))

            # 3. barge-in 신호
            elif msg_type == "barge_in":
                # _cancel_current 안에서 partial_text → interrupted_ctx 저장
                await _cancel_current()
                await _set_state("listening")

            # 4. 대화 종료
            elif msg_type == "end_conversation":
                await _cancel_current()
                context = {}
                messages.clear()
                pending_sections.clear()
                session["user_name"]         = ""
                session["sensitivity_label"] = "보통"
                session["interrupted_ctx"]   = ""
                session["partial_text"]      = ""
                state = "idle"

    except WebSocketDisconnect:
        pass

    finally:
        await _cancel_task(ping_task)
        await _cancel_current()
