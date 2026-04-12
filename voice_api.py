"""
voice_api.py — FastAPI 음성 파이프라인 서버 (포트 8000)

엔드포인트:
  GET  /           → 음성 채팅 UI (voice/static/index.html)
  POST /voice/stt  → 오디오 파일 업로드 → 텍스트 반환
  WS   /voice/ws   → 전체 파이프라인 (오디오 → STT → Claude → TTS → 재생)

WebSocket 프로토콜:
  Client → Server:
    { "type": "audio",     "data": "<base64 webm>", "context": {...} }
    { "type": "interrupt"                                              }

  Server → Client:
    { "type": "transcript",   "text": "인식된 텍스트"   }
    { "type": "audio_chunk",  "data": "<base64 mp3>"   }
    { "type": "done"                                   }
    { "type": "interrupted"                            }
    { "type": "error",        "message": "오류 메시지" }
"""
import asyncio
import base64
import json
import os

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI, File, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from voice.stt_service import transcribe
from voice.pipeline import stream_voice_response

app = FastAPI(title="내 옷장의 코디 — Voice API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="voice/static"), name="voice_static")


# ── UI ────────────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def index():
    with open("voice/static/index.html", encoding="utf-8") as f:
        return f.read()


# ── REST: STT 단독 엔드포인트 (테스트용) ──────────────────────────────────────

@app.post("/voice/stt")
async def stt_endpoint(audio: UploadFile = File(...)):
    """오디오 파일 → 텍스트 변환 (Whisper small)"""
    audio_bytes = await audio.read()
    loop = asyncio.get_event_loop()
    try:
        text = await loop.run_in_executor(None, transcribe, audio_bytes)
        return {"text": text}
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


# ── WebSocket: 전체 파이프라인 ────────────────────────────────────────────────

@app.websocket("/voice/ws")
async def voice_ws(websocket: WebSocket):
    await websocket.accept()

    # 현재 TTS 스트리밍 태스크
    tts_task: asyncio.Task | None = None
    # 인터럽트 플래그 (dict로 closure 공유)
    state = {"interrupted": False}

    try:
        while True:
            raw = await websocket.receive_text()
            msg = json.loads(raw)

            # ── 인터럽트: TTS 재생 중 사용자가 말 시작 ─────────────────────
            if msg["type"] == "interrupt":
                state["interrupted"] = True
                if tts_task and not tts_task.done():
                    tts_task.cancel()
                continue

            # ── 오디오 수신: 파이프라인 실행 ──────────────────────────────
            if msg["type"] == "audio":
                state["interrupted"] = False

                # 이전 태스크가 아직 실행 중이면 취소
                if tts_task and not tts_task.done():
                    tts_task.cancel()
                    await asyncio.sleep(0)  # 취소 처리 yield

                audio_bytes = base64.b64decode(msg["data"])
                context = msg.get("context", {})
                speaker = msg.get("speaker", "nara")

                # 1. STT (Whisper — 블로킹 → run_in_executor)
                loop = asyncio.get_event_loop()
                try:
                    text = await loop.run_in_executor(None, transcribe, audio_bytes)
                except Exception as e:
                    await websocket.send_text(
                        json.dumps({"type": "error", "message": f"STT 오류: {e}"})
                    )
                    continue

                # 인식 결과를 먼저 클라이언트에 전송 (UI 자막용)
                await websocket.send_text(
                    json.dumps({"type": "transcript", "text": text})
                )

                # 2. Claude → TTS 스트리밍 (별도 태스크로 비동기 실행)
                async def _stream_and_send(
                    _text: str, _context: dict, _speaker: str
                ):
                    try:
                        async for mp3_chunk in stream_voice_response(
                            _text, context=_context, speaker=_speaker
                        ):
                            if state["interrupted"]:
                                await websocket.send_text(
                                    json.dumps({"type": "interrupted"})
                                )
                                return
                            b64 = base64.b64encode(mp3_chunk).decode()
                            await websocket.send_text(
                                json.dumps({"type": "audio_chunk", "data": b64})
                            )
                        await websocket.send_text(json.dumps({"type": "done"}))

                    except asyncio.CancelledError:
                        await websocket.send_text(
                            json.dumps({"type": "interrupted"})
                        )
                    except Exception as e:
                        await websocket.send_text(
                            json.dumps({"type": "error", "message": f"TTS 오류: {e}"})
                        )

                tts_task = asyncio.create_task(
                    _stream_and_send(text, context, speaker)
                )

    except WebSocketDisconnect:
        if tts_task and not tts_task.done():
            tts_task.cancel()


# ── 실행 ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=False)
