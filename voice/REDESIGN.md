# 음성 기능 재설계 설계서

> 작성일: 2026-04-14  
> 이 파일을 Claude Code/Cowork에 보여주면서 "REDESIGN.md 읽고 거기서부터 시작해줘"라고 하면 전체 맥락을 즉시 파악함

---

## 왜 재설계했나 — 3가지 근본 문제

1. **Gemini Live API 모델 deprecated**
   - `voice/pipeline.py`가 `gemini-2.0-flash-exp` 사용
   - 2026년 기준 v1alpha Live API에서 완전히 지원 중단 → 음성 기능 전체 불작동

2. **LLM이 두 개로 분리**
   - 타이핑 챗봇 → Claude (claude-sonnet-4-6)
   - 마이크 음성 → Gemini
   - 같은 질문에 다른 AI가 다른 답변 → 사용자 경험 파괴

3. **텍스트/음성 완전 분리**
   - 텍스트 챗봇: 화면에만 보임, 소리 없음
   - 음성 챗봇: 소리만 나옴, 화면에 안 보임
   - `clean_for_tts()`가 voice/pipeline.py에만 있어 챗봇 응답에 미적용
   - 마이크 버튼이 별도 `/voice` 페이지로 이동하는 구조 (dashboard에서 벗어남)

---

## 새로운 아키텍처

### 사용 모델/API

| 역할 | 기존 | 변경 후 | 이유 |
|---|---|---|---|
| STT (음성→텍스트) | Gemini Live API | **Web Speech API** (브라우저 내장) | Deepgram 한국어 미지원, Gemini deprecated, Web Speech 무료+한국어 완벽 지원, 크롬 기준 |
| LLM (대화) | Gemini (voice) + Claude (chatbot) | **Claude 단일화** (claude-sonnet-4-6) | 일관된 답변, 맥락 공유 가능 |
| TTS (텍스트→음성) | Google TTS (voice에서만) | **Google TTS** → chatbot/tts.py 공용 모듈 | 기존 키 재활용, chatbot도 동일하게 사용 |

### 전체 흐름

```
마이크 버튼 ON (초록색) → WebSocket /voice/ws 열림
        ↓
Web Speech API (브라우저 로컬 처리, 한국어, 무료)
음성 → 텍스트 변환
        ↓  onspeechstart 이벤트에서 barge-in 처리
        ↓  onresult에서 텍스트 완성
WebSocket으로 { type: "user_text", text: "..." } 전송
        ↓
voice/router.py 수신
        ↓
chatbot/llm_client.py → Claude API (claude-sonnet-4-6) 스트리밍 호출
        ↓ 첫 문장 완성 즉시
  ┌─────┴──────────────────────────┐
  ↓                                ↓
{ type: "response_text" }    chatbot/tts.py
화면 말풍선에 텍스트 표시     clean_for_tts() → Google TTS
                             → { type: "audio_chunk" } 스트리밍
                             브라우저에서 오디오 재생
        ↓
사용자가 말 시작 (onspeechstart)
→ barge_in 전송 → 서버 asyncio Task 취소 → 오디오 즉시 중단
→ 새 입력 처리 (티키타카)

마이크 버튼 OFF (빨간색) → { type: "end_conversation" } → WebSocket 세션 종료
```

### 성능 특성

- STT: 브라우저 로컬 처리 → 네트워크 없음, 즉시
- Claude 응답: 스트리밍 모드 → 첫 문장 TTS까지 약 1~1.5초
- Barge-in: onspeechstart 이벤트 기반 → 말 시작하는 순간 오디오 중단

---

## 수정 대상 파일 상세

### 1. `chatbot/tts.py` — 신규 생성

```python
# 역할: clean_for_tts() + Google TTS 공용 모듈
# voice/pipeline.py에서 이동
# 어디서든: from chatbot.tts import clean_for_tts, synthesize_speech

def clean_for_tts(text: str) -> str:
    # 특수기호, 마크다운, 이모지, 영어→한국어 패션 용어 변환
    # voice/pipeline.py의 기존 함수 그대로 이동 + 강화

async def synthesize_speech(text: str) -> bytes:
    # Google TTS REST API 호출 → raw PCM bytes 반환
    # GOOGLE_TTS_API_KEY 환경변수 사용
```

### 2. `voice/pipeline.py` — 대폭 축소

- GeminiLiveSession 클래스 전체 삭제
- google.genai import 전체 삭제
- clean_for_tts(), _synthesize_tts() → chatbot/tts.py로 이동
- 파일 자체가 거의 비워지거나 삭제 가능

### 3. `voice/router.py` — WebSocket 프로토콜 변경

```
클라이언트 → 서버:
  { "type": "start_conversation", "context": { "wardrobe": [...], "weather_label": "..." } }
  { "type": "user_text", "text": "사용자가 말한 텍스트" }
  { "type": "barge_in" }
  { "type": "end_conversation" }

서버 → 클라이언트:
  { "type": "state", "value": "listening|processing|speaking" }
  { "type": "response_text", "text": "Claude 응답 텍스트" }
  { "type": "audio_chunk", "data": "<base64 24kHz PCM>" }
  { "type": "done" }
  { "type": "error", "message": "..." }
```

- user_text 수신 → chatbot/llm_client.get_chatbot_response() 호출 (Claude)
- 응답을 response_text로 먼저 전송 (화면 표시)
- chatbot/tts.synthesize_speech()로 TTS → audio_chunk 스트리밍
- Claude 스트리밍(stream=True): 문장 종결 감지 즉시 TTS 호출 (지연 최소화)
- 세션: start_conversation 후 end_conversation 전까지 WebSocket 절대 끊기지 않음
- barge_in: 진행 중인 asyncio Task 취소

### 4. `chatbot/llm_client.py` — 소폭 수정

- get_chatbot_response(): voice/router.py에서도 import해서 사용
- 두 system_prompt 모두 마크다운 금지 지시 추가:
  ```
  "응답에 **, *, -, --, —, _, 번호목록, 불릿 등 특수기호 절대 사용 금지.
   순수 한글 문장으로만 작성."
  ```

### 5. `templates/dashboard.html` — UI 변경

- voiceMicBtn: ON/OFF 토글 버튼
  - OFF (기본): 빨간색 배경 + "OFF" 텍스트
  - ON: 초록색 배경 + "ON" 텍스트 + pulse 애니메이션
- voiceStatus 텍스트:
  - OFF → "마이크가 꺼져 있어요"
  - listening → "듣는 중..."
  - processing → "생각하는 중..."
  - speaking → "말하는 중..."
- Web Speech API JS:
  - lang: 'ko-KR', continuous: false
  - onspeechstart → barge_in WebSocket 전송 + 오디오 중단
  - onresult → user_text WebSocket 전송
  - 버튼 OFF → end_conversation 전송
- response_text 수신 → 말풍선에 텍스트 표시
- 기존 텍스트 챗봇(/chat POST) 기능 건드리지 말 것
- Web Speech API 미지원 환경: "Chrome 브라우저에서만 지원됩니다" 표시

### 6. `requirements.txt` — 패키지 정리

- `google-generativeai` 제거 (Gemini 완전 제거)
- `httpx` 유지 (Google TTS REST 호출에 필요)
- 나머지 유지

---

## 절대 건드리면 안 되는 것

- `app.py`: voice_router include 부분 외 건드리지 말 것
- `chatbot/recommend.py`, `weather.py`, `weather_client.py`, `weather_style_mapper.py`, `shopping.py`
- `model.py`, `db.py`
- `templates/wardrobe.html`, `login.html`, `profile.html`, `base.html`
- `.env` 파일

---

## Claude Code에 넣을 전체 프롬프트

아래를 그대로 복사해서 Claude Code에 붙여넣기:

```
아래 작업을 수행해줘. 반드시 관련 파일을 스스로 모두 확인하고,
app.py 하나만 건드리는 실수 없이 모든 관련 파일을 전부 수정해.
작업 완료 후 파일별로 무엇을 어떻게 바꿨는지 정리해서 보여줘.

먼저 voice/REDESIGN.md 파일을 읽고 전체 맥락을 파악한 뒤 작업 시작해.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[ 작업 목표 ]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

음성 대화 기능 전면 재설계.
현재 Gemini Live API(gemini-2.0-flash-exp)를 사용하는 음성 파이프라인이
모델 deprecated로 완전히 고장난 상태이며, 구조적으로도 잘못 설계되어 있음.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[ 새로운 아키텍처 ]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

STT: Web Speech API (브라우저 내장, 무료, 한국어 완벽 지원)
LLM: Claude API (claude-sonnet-4-6) 단일 사용
TTS: Google TTS (기존 GOOGLE_TTS_API_KEY 재활용)
     → chatbot/tts.py 공용 모듈로 분리

흐름:
마이크 버튼 ON
→ Web Speech API로 음성 인식 루프 시작 (브라우저)
→ 인식된 텍스트를 WebSocket /voice/ws 로 전송
→ voice/router.py가 받아서 chatbot/llm_client.py의 Claude 호출
→ Claude 텍스트 응답을 WebSocket으로 전송 (화면 표시용)
→ 동시에 chatbot/tts.py로 TTS 변환 → PCM 오디오 청크를 WebSocket으로 전송
→ 브라우저에서 텍스트 말풍선 표시 + 오디오 재생 동시 실행
→ 사용자가 말 시작하면 barge-in: 오디오 재생 즉시 중단 + 새 입력 처리
마이크 버튼 OFF → WebSocket 세션 종료

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[ 수정/생성할 파일 목록 — 전부 확인하고 수정할 것 ]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. chatbot/tts.py (신규 생성)
   - voice/pipeline.py에 있던 clean_for_tts() 함수 이동
   - voice/pipeline.py에 있던 _synthesize_tts() 이동 및 개선
     → 함수명: synthesize_speech(text: str) → bytes
   - clean_for_tts()는 더 강화할 것:
     특수기호(_, --, —, ·), 마크다운 강조(**/*/__ 등), 번호 목록, 불릿,
     영어 패션 용어 한국어 발음 변환 테이블 그대로 유지

2. voice/pipeline.py (대폭 수정)
   - GeminiLiveSession 클래스 전체 삭제
   - google.genai 관련 import 전체 삭제
   - clean_for_tts(), _synthesize_tts() → chatbot/tts.py로 이동 후 여기서 삭제

3. voice/router.py (수정)
   - WebSocket 프로토콜 변경 (상세 내용은 voice/REDESIGN.md 참고)
   - user_text 수신 시 chatbot/llm_client.get_chatbot_response() 호출
   - 응답: response_text(텍스트) + audio_chunk(오디오) 둘 다 전송
   - Claude 스트리밍(stream=True): 문장 종결 즉시 TTS 호출
   - 세션 유지: 침묵해도 끊기지 않게 keepalive ping 유지
   - barge_in: 진행 중 asyncio Task 취소

4. chatbot/llm_client.py (수정)
   - get_chatbot_response() voice/router.py에서 import 가능하게
   - 두 system_prompt 모두 마크다운/특수기호 금지 지시 추가

5. templates/dashboard.html (수정)
   - voiceMicBtn: ON/OFF 토글 (ON=초록+"ON", OFF=빨강+"OFF")
   - voiceStatus: 상태별 텍스트 자동 변경
   - Web Speech API JS 추가 (lang: ko-KR)
   - onspeechstart → barge_in 전송 + 오디오 즉시 중단
   - response_text 수신 → 말풍선 텍스트 표시
   - 기존 텍스트 챗봇(/chat POST) 기능 건드리지 말 것
   - Web Speech API 미지원 환경 → "Chrome에서만 지원" 안내

6. requirements.txt (수정)
   - google-generativeai 제거
   - 나머지 유지

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[ 추가 기술 요구사항 ]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

- Claude API는 반드시 스트리밍 모드(stream=True)로 호출할 것.
  문장 종결 감지 즉시 TTS 호출 → 첫 소리까지 지연 최소화.
  기존 voice/pipeline.py의 _SENTENCE_END 패턴 방식 그대로 chatbot/tts.py에 적용.

- barge-in은 Web Speech API의 onspeechstart 이벤트에서 발생시킬 것.
  onresult(텍스트 완성) 이전에 barge_in WebSocket 메시지 전송.
  브라우저: 오디오 재생 즉시 중단 (audio.pause() + audio queue 초기화)
  서버: 진행 중인 asyncio Task 취소

- 크롬 브라우저 기준으로 구현.
  Web Speech API 미지원 환경이면 voiceStatus에
  "이 기능은 Chrome 브라우저에서만 지원됩니다" 표시.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[ 절대 건드리면 안 되는 것 ]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

- app.py: voice_router include 부분 외에 다른 라우트 건드리지 말 것
- chatbot/recommend.py, weather.py, weather_client.py, weather_style_mapper.py, shopping.py
- model.py, db.py
- templates/wardrobe.html, login.html, profile.html, base.html
- CLAUDE.md 폴더 구조 규칙 준수
- .env 파일 절대 수정 금지

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[ 환경변수 ]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

- GOOGLE_TTS_API_KEY: chatbot/tts.py에서 사용
- CLAUDE_API_KEY: chatbot/llm_client.py에서 사용 (기존 동일)
- GEMINI_API_KEY: 더 이상 사용 안 함 (코드에서 참조 제거)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[ 작업 완료 후 제출 형식 ]
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

파일별로 무엇을 어떻게 바꿨는지 아래 형식으로 정리해줘:

[파일명] (신규생성/수정/삭제)
- 변경 내용 1
- 변경 내용 2

마지막에 테스트 방법도 간단히 알려줘.
```

---

## 나중에 이 파일 사용하는 방법

### 새 Cowork 세션에서 재개할 때
```
voice/REDESIGN.md 읽고 거기서부터 이어서 작업해줘.
```

### Claude Code에서 코드 작업 시작할 때
```
voice/REDESIGN.md 읽고 아래 프롬프트대로 작업해줘.
[위의 "Claude Code에 넣을 전체 프롬프트" 복사 붙여넣기]
```

### 에러가 났을 때
```
voice/REDESIGN.md 읽고 맥락 파악한 뒤, 아래 에러 해결해줘:
[에러 메시지 붙여넣기]
```
