# 음성 파이프라인 (Voice Pipeline) 설명서

> 조원 전원이 이해할 수 있도록 작성한 기술 문서입니다.

---

## 1. 왜 만들었나? (배경)

기존 서비스는 **텍스트 채팅**만 가능했습니다.
사용자가 타이핑으로 "오늘 뭐 입을까?"를 물으면 AI가 텍스트로 답했죠.

우리가 목표로 한 건 **음성으로 자연스럽게 대화**하는 것입니다.
- 말로 물어보면 → AI가 말로 대답
- AI가 말하는 중에 사용자가 끊어도 → 즉시 반응 (barge-in)
- 대화가 끝나면 → 자동으로 다시 듣기 시작 (티카타카)

**현재 구조: Gemini Live 단일 API**
```
사용자 목소리(PCM) → [Gemini Live] → AI 목소리(PCM)
                     STT + LLM + TTS 통합
```

---

## 2. 기술 스택

| 역할 | 기술 | 이유 |
|------|------|------|
| STT + LLM + TTS 통합 | Google Gemini Live API | 단일 API로 STT·LLM·TTS를 모두 처리, 초저지연 |
| 실시간 통신 | WebSocket | 양방향 실시간 통신 필수 |
| 백엔드 | FastAPI | asyncio 기반 비동기 → 스트리밍 처리에 최적 |

---

## 3. 파일 구조

```
voice/
├── pipeline.py         GeminiLiveSession 클래스 — Gemini Live 세션 관리
├── router.py           FastAPI WebSocket/HTTP 엔드포인트
└── static/
    └── index.html      브라우저 음성 채팅 UI (PCM 오디오 처리 포함)
```

---

## 4. 각 파일이 하는 일

### pipeline.py — Gemini Live 세션 래퍼

`GeminiLiveSession` 클래스 하나로 전체 파이프라인을 관리합니다.

```
start_session(context)   → Gemini Live WebSocket 연결, 옷장·날씨 컨텍스트 주입
send_audio(pcm_bytes)    → 16kHz 16-bit PCM 오디오 전송
receive_audio()          → 응답 PCM 오디오 스트리밍 수신 (AsyncGenerator)
interrupt()              → barge-in 시 수신 루프 즉시 종료
end_session()            → 연결 종료 및 리소스 정리
```

### router.py — WebSocket 엔드포인트

```
GET  /voice      → 음성 채팅 UI 페이지 서빙
POST /voice/stt  → 410 반환 (Gemini Live로 교체됨)
WS   /voice/ws   → Gemini Live 실시간 대화 (메인)
```

---

## 5. WebSocket 통신 프로토콜

### 브라우저 → 서버

| 메시지 타입 | 내용 |
|-------------|------|
| `start_conversation` | `{ context: { wardrobe: [...], weather_label: "..." } }` |
| `audio_chunk` | `{ data: "<base64 16kHz PCM>" }` — 발화 완료 후 전송 |
| `end_conversation` | 대화 종료 |

### 서버 → 브라우저

| 메시지 타입 | 내용 |
|-------------|------|
| `state` | `"listening"` 또는 `"speaking"` |
| `audio_chunk` | `{ data: "<base64 24kHz PCM>" }` — Gemini 응답 오디오 |
| `done` | 응답 완료 |
| `error` | `{ message: "..." }` |

---

## 6. 티카타카 동작 흐름

```
[대화 시작 버튼 클릭]
        ↓ (옷장·날씨 컨텍스트 API 로드 → start_conversation 전송)
   서버: GeminiLiveSession 시작 → state: listening
        ↓
   브라우저: 마이크 VAD 시작 ← ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─┐
        ↓                                                  │
   말하는 동안 PCM 누적                                     │
   500ms 침묵 → audio_chunk 전송                           │
        ↓                                                  │
   서버: Gemini Live 전송 → 응답 스트리밍 시작              │
   state: speaking                                         │
        ↓                                                  │
   브라우저: PCM 청크 순서대로 Web Audio API 재생            │
        ↓                                                  │
   서버: turn_complete → state: listening ─ ─ ─ ─ ─ ─ ─ ─ ┘

   ※ AI 말하는 중 사용자가 말하면? (barge-in)
      barge VAD 감지(250ms) → 재생 즉시 중단
      → bargePcmBuffer(사용자 음성) → audio_chunk 전송
      → 서버: interrupt() + 새 Gemini 응답 시작
```

---

## 7. 오디오 포맷

| 방향 | 샘플레이트 | 비트 | 채널 | MIME |
|------|-----------|------|------|------|
| 브라우저 → 서버 | 16000 Hz | 16-bit 부호 있는 정수 | mono | `audio/pcm;rate=16000` |
| 서버 → 브라우저 | 24000 Hz | 16-bit 부호 있는 정수 | mono | raw PCM |

---

## 8. 실행 방법

```bash
# 로컬 실행
python app.py

# 접속
http://localhost:5000/voice    ← 음성 채팅 전용 UI
http://localhost:5000          ← 기존 웹 UI

# Docker
docker-compose up --build
```

### .env에 필요한 키

```
GEMINI_API_KEY=...    # Google Gemini Live API
CLAUDE_API_KEY=...    # Claude AI (텍스트 챗봇용, 음성과는 별개)
```

---

## 9. 알려진 제약

| 항목 | 내용 |
|------|------|
| HTTPS 필요 | 실제 배포 시 브라우저 마이크 권한은 HTTPS에서만 허용 (localhost는 예외) |
| ScriptProcessorNode | 마이크 PCM 캡처에 deprecated API 사용 중 — 향후 AudioWorklet으로 교체 권장 |
| Gemini Live 음성 | 현재 `Kore` 음성 고정 — pipeline.py의 `_VOICE` 변수로 변경 가능 |
| barge-in 민감도 | 주변 소음 환경에서 오작동 가능 → index.html의 `BARGE_DB_THRESH` 조정 |
