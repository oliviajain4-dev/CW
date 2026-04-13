"""
voice/router.py — 음성 파이프라인 FastAPI APIRouter
app.py에 include_router()로 통합됨 (별도 포트 불필요)

엔드포인트:
  POST /voice/stt  → 오디오 파일 업로드 → 텍스트
  WS   /voice/ws   → 전체 파이프라인 (오디오 → STT → Claude → TTS → 재생)
  GET  /voice      → 음성 채팅 전용 UI (voice/static/index.html)
"""
import asyncio
import base64
import json
from typing import Optional

from fastapi import APIRouter, File, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse

from voice.stt_service import transcribe
from voice.pipeline import stream_voice_response

router = APIRouter(prefix="/voice", tags=["voice"])


@router.get("", response_class=HTMLResponse, name="voice_chat")
async def voice_chat_page():
    """음성 채팅 전용 페이지 (기존 voice/static/index.html)"""
    with open("voice/static/index.html", encoding="utf-8") as f:
        return f.read()


@router.post("/stt", name="voice_stt")
async def stt_endpoint(audio: UploadFile = File(...)):
    """오디오 파일 → 텍스트 (Whisper small) — 단독 테스트용"""
    audio_bytes = await audio.read()
    loop = asyncio.get_event_loop()
    try:
        text = await loop.run_in_executor(None, transcribe, audio_bytes)
        return {"text": text}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@router.websocket("/ws")
async def voice_ws(websocket: WebSocket):
    """
    WebSocket 음성 파이프라인
    Client → { "type": "audio",     "data": "<base64 webm>", "context": {...} }
    Client → { "type": "interrupt"                                              }
    Server → { "type": "transcript",  "text": "..."          }
    Server → { "type": "audio_chunk", "data": "<base64 mp3>" }
    Server → { "type": "done"                                }
    Server → { "type": "interrupted"                         }
    Server → { "type": "error",       "message": "..."       }
    """
    await websocket.accept()

    tts_task: Optional[asyncio.Task] = None
    state = {"interrupted": False}

    try:
        while True:
            raw = await websocket.receive_text()
            msg = json.loads(raw)

            # ── 인터럽트 ─────────────────────────────────────────────
            if msg["type"] == "interrupt":
                state["interrupted"] = True
                if tts_task and not tts_task.done():
                    tts_task.cancel()
                continue

            # ── 오디오 수신 → 파이프라인 ─────────────────────────────
            if msg["type"] == "audio":
                state["interrupted"] = False

                if tts_task and not tts_task.done():
                    tts_task.cancel()
                    await asyncio.sleep(0)

                audio_bytes = base64.b64decode(msg["data"])
                context     = msg.get("context", {})
                speaker     = msg.get("speaker", "ko-KR-Wavenet-A")

                # 1. STT (Whisper — 동기 블로킹 → executor)
                loop = asyncio.get_event_loop()
                try:
                    text = await loop.run_in_executor(None, transcribe, audio_bytes)
                except Exception as e:
                    await websocket.send_text(
                        json.dumps({"type": "error", "message": f"STT 오류: {e}"})
                    )
                    continue

                await websocket.send_text(
                    json.dumps({"type": "transcript", "text": text})
                )

                # 2. Claude 스트리밍 → TTS → 청크 전송 (별도 태스크)
                async def _stream(t: str, ctx: dict, sp: str):
                    try:
                        async for mp3 in stream_voice_response(t, context=ctx, speaker=sp):
                            if state["interrupted"]:
                                await websocket.send_text(
                                    json.dumps({"type": "interrupted"})
                                )
                                return
                            b64 = base64.b64encode(mp3).decode()
                            await websocket.send_text(
                                json.dumps({"type": "audio_chunk", "data": b64})
                            )
                        await websocket.send_text(json.dumps({"type": "done"}))
                    except asyncio.CancelledError:
                        await websocket.send_text(json.dumps({"type": "interrupted"}))
                    except Exception as e:
                        await websocket.send_text(
                            json.dumps({"type": "error", "message": f"TTS 오류: {e}"})
                        )

                tts_task = asyncio.create_task(_stream(text, context, speaker))

    except WebSocketDisconnect:
        if tts_task and not tts_task.done():
            tts_task.cancel()
