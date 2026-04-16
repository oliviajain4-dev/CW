# 내 옷장의 코디 — 프로젝트 규칙 (CLAUDE.md)

> **이 파일은 Claude Code가 작업 시작 시 자동으로 읽습니다.**
> 팀원 누구든, Claude를 통해 작업할 때 반드시 아래 규칙을 따르세요.

---

## 🚨 TTS 절대규칙 — 브랜치 병합 후에도 절대 수정 금지

> **이 섹션은 프로젝트 전체에서 가장 높은 우선순위를 가집니다.**
> 어떤 브랜치 병합, 리팩토링, 코드 정리 작업을 하더라도 아래 내용은 변경하지 마세요.

### 수정 금지 파일 및 함수

| 파일 | 함수/변수 | 이유 |
|---|---|---|
| `chatbot/tts.py` | `_EN_KO` 테이블, `clean_for_tts()` | 서버 TTS 정제 핵심 로직 |
| `static/js/voice.js` | `_EN_KO_JS` 테이블, `cleanText()` | 브라우저 TTS 정제 핵심 로직 |
| `voice/router.py` | `_VOICE_SYSTEM` 프롬프트 | AI 음성 응답 한국어 강제 |
| `chatbot/llm_client.py` | 각 함수의 TTS 절대규칙 섹션 | AI 디자이너 코멘트 한국어 강제 |

### TTS 3대 원칙

1. **순수 한국어만 읽힌다** — 알파벳은 한 글자도 음성으로 나와서는 안 됨
2. **이모지·기호는 묵음** — 이모지, 대시(-/—), 별표(*), 밑줄(_), 괄호 등은 제거
3. **두 테이블은 항상 동일** — `tts.py`의 `_EN_KO`와 `voice.js`의 `_EN_KO_JS`는 동일한 내용을 유지

### TTS 경로 구조 (참고)

```
[자동 읽기] fillDesignerPanel(comment)
  → VoiceEngine.autoSpeak(comment)
  → voice.js cleanText()          ← 브라우저 Web Speech API
  → SpeechSynthesisUtterance

[마이크 대화] 마이크 ON → Web Speech API STT
  → WebSocket /voice/ws
  → voice/router.py process_user_text()
  → chatbot/tts.py clean_for_tts() ← Google Cloud TTS
  → synthesize_speech()
```

### 영어→한국어 변환 테이블 추가 방법

새로운 영어 단어가 TTS에서 이상하게 읽힌다면:
1. `chatbot/tts.py`의 `_EN_KO` 테이블에 추가
2. **동시에** `static/js/voice.js`의 `_EN_KO_JS` 테이블에도 동일하게 추가
3. 두 파일을 한 번에 수정하지 않으면 어느 한쪽 경로에서 영어가 그대로 읽힘

---

## 폴더 구조 규칙

### 핵심 원칙
- **새로운 기능 = 새로운 폴더**
- 메인 실행 `.py` 파일 → `CW/` 루트에 위치
- 그 기능에서 생성되는 **모든 산출물** (이미지, 데이터, 설정, 서브모듈) → 해당 기능 폴더 안에 위치

### 현재 폴더 구조

```
CW/                          ← 메인 .py 파일만 여기에
│
├── app.py                   ← FastAPI 웹 서버 (메인)
├── db.py                    ← DB 연결 모듈 (메인)
├── model.py                 ← 이미지 AI 분석 (메인)
├── make_flowchart.py        ← 흐름도 생성 메인 스크립트
├── ui_mockup.html           ← UI 목업 (feat/ny2에서 추가)
│
├── chatbot/                 ← 챗봇/추천 기능 모듈 전체
│   ├── weather.py
│   ├── weather_client.py
│   ├── weather_style_mapper.py
│   ├── llm_client.py
│   ├── recommend.py
│   ├── tts.py               ← Google TTS 공용 모듈 (clean_for_tts 포함)
│   └── weather_main.py
│
├── voice/                   ← 음성 어시스턴트 모듈
│   ├── router.py            ← WebSocket /voice/ws 엔드포인트
│   └── static/
│
├── flowchart/               ← 흐름도 기능의 모든 산출물
│   ├── flowchart_2D.png
│   ├── flowchart_3D.png
│   └── flowchart_3d_service_flow.png
│
├── promo/                   ← 홍보용 이미지/자료
├── templates/               ← FastAPI HTML 템플릿
├── static/                  ← CSS, JS, 업로드 이미지
│   ├── images/
│   │   └── room_bg.png      ← 대시보드 배경 이미지
│   ├── js/
│   │   ├── main.js
│   │   └── voice.js
│   └── css/
│       ├── style.css        ← 배경: url('/static/images/room_bg.png')
│       └── voice.css
├── docker/                  ← Docker 관련 파일 (init.sql)
└── .devcontainer/           ← VS Code Dev Container 설정
```

---

## 새 기능 추가 시 규칙

### 규칙 1 — 폴더 먼저 만들고 작업
```
새 기능 "보고서 자동화" 추가 시:
  ✅ CW/make_report.py          ← 메인 실행 파일만 루트에
  ✅ CW/report/output.pdf       ← 산출물은 폴더 안에
  ✅ CW/report/template.html    ← 관련 파일도 폴더 안에
  ✅ CW/report/data.json        ← 관련 파일도 폴더 안에

  ❌ CW/output.pdf              ← 루트에 산출물 직접 생성 금지
  ❌ CW/template.html           ← 루트에 관련 파일 생성 금지
```

### 규칙 2 — 루트에 생성 가능한 파일 목록
루트(`CW/`)에는 아래만 허용:

| 파일 | 설명 |
|---|---|
| `app.py` | FastAPI 메인 서버 |
| `db.py` | DB 연결 모듈 |
| `model.py` | 이미지 분석 모듈 |
| `make_*.py` | 각 기능의 메인 실행 스크립트 |
| `Dockerfile` | Docker 빌드 설정 |
| `docker-compose.yml` | 컨테이너 실행 설정 |
| `requirements.txt` | Python 패키지 목록 |
| `.env` / `.env.example` | 환경변수 |
| `.gitignore` / `.dockerignore` | Git/Docker 제외 설정 |
| `CLAUDE.md` | 이 파일 |
| `README.md` | 프로젝트 설명 |

### 규칙 3 — 절대 루트에 생성하면 안 되는 것
- 이미지 파일 (`.png`, `.jpg`, `.svg`)
- 문서 파일 (`.pdf`, `.docx`)
- 데이터 파일 (`.json`, `.csv`, `.xlsx`) — `db.py`/DB로 관리
- 임시 스크립트 (`test_*.py`, `temp_*.py`)
- 폰트 파일 (`.ttf`, `.otf`)

---

## 기능별 폴더 네이밍 규칙

| 기능 | 폴더명 |
|---|---|
| 흐름도/다이어그램 | `flowchart/` |
| PDF/문서 생성 | `docs/` |
| 데이터 분석/리포트 | `report/` |
| 테스트/실험 | `tests/` |
| 크롤링/스크래핑 | `crawler/` |
| 알림/자동화 | `automation/` |

---

## requirements.txt 관리 규칙

### 핵심 원칙
> **새 패키지를 설치하면 반드시 requirements.txt에 기록해야 합니다.**
> 기록하지 않으면 팀원 컴퓨터 / Docker 빌드에서 import 에러가 발생합니다.

### 규칙 1 — 패키지 설치 후 즉시 등록

새 라이브러리를 `pip install`한 경우, **작업 완료 전에 반드시** requirements.txt 하단에 추가:

```bash
# 방법 A: 직접 추가 (버전 고정 권장)
echo "패키지명==버전" >> requirements.txt

# 방법 B: pip freeze로 정확한 버전 확인 후 추가
pip show 패키지명   # 버전 확인
# → requirements.txt 하단에 수동 추가
```

### 규칙 2 — Claude에게 작업 요청 시

Claude에게 새 기능 구현을 요청하면 Claude가 자동으로:
1. 새로 필요한 패키지 파악
2. requirements.txt에 이미 있는지 확인
3. 없으면 하단에 추가

**Claude 지시 포함 문구 예시:**
> "~~ 기능 만들어줘. 새 패키지 설치했으면 requirements.txt에도 추가해줘."

### 규칙 3 — requirements.txt 수정 시 주의사항

- **전체 삭제 후 재작성 금지** — 기존 패키지가 사라지면 Docker 빌드 실패
- 추가만 허용: 파일 하단에 append
- 삭제는 실제로 해당 패키지를 코드에서 완전히 제거했을 때만

### 현재 등록된 주요 패키지 (기능별)

| 기능 | 패키지 |
|---|---|
| 웹 서버 | `fastapi`, `uvicorn`, `flask`, `werkzeug` |
| AI 추천 | `anthropic`, `openai` |
| 날씨 API | `requests` |
| 환경변수 | `python-dotenv` |
| 이미지 분석 (AI) | `open_clip_torch`, `transformers`, `timm`, `pillow`, `numpy`, `scipy`, `opencv-python` |
| 객체 탐지 | `ultralytics` (YOLO, feat/ny2에서 추가) |
| 흐름도 생성 | `matplotlib` |
| 데이터 처리 | `pandas`, `polars` (feat/ny2에서 추가), `pydantic`, `PyYAML` |
| 인증 | `authlib==1.6.10`, `Flask-Login==0.6.3` |
| 이미지 저장 | `cloudinary==1.44.1` |
| HTTP 클라이언트 | `httpx` |
| 음성 STT | `openai-whisper` |
| DB | `psycopg2-binary` (PostgreSQL 15) |

---

## API 키 규칙

- `.env` 파일에만 저장, **절대 코드에 하드코딩 금지**
- `.env`는 **절대 Git 커밋 금지** (`.gitignore`에 포함됨)
- 팀원에게 API 키 전달 시 카카오톡/슬랙 등 별도 채널 사용

현재 필요한 키:
```
KMA_API_KEY=...            # 기상청 API (발급 완료)
CLAUDE_API_KEY=...         # Anthropic Claude API (발급 완료)
GOOGLE_TTS_API_KEY=...     # Google Cloud TTS (chatbot/tts.py)
GOOGLE_CLIENT_ID=...       # Google OAuth 로그인
GOOGLE_CLIENT_SECRET=...   # Google OAuth 로그인
CLOUDINARY_URL=...         # 이미지 클라우드 저장
```

---

## Git 규칙

- 브랜치: 기능별로 `feat/기능명` 형식
- 커밋: 한 기능 완성 후 커밋 (잦은 소규모 커밋 지양)
- PR: `feat/*` → `main` 으로 병합
- **force push는 팀장 확인 후 진행**

---

## 음성 기능 재설계 결정사항 (2026-04-14)

> 자세한 내용은 `voice/REDESIGN.md` 참고

### 핵심 변경
- **Gemini Live API 완전 제거** (gemini-2.0-flash-exp deprecated로 작동 불가)
- **STT**: Web Speech API (브라우저 내장, 무료, 한국어 완벽 지원)
- **LLM**: Claude 단일화 — `claude-sonnet-4-6` (텍스트 챗봇과 동일 엔진)
- **TTS**: Google TTS 유지 → `chatbot/tts.py` 공용 모듈로 이동
- **마이크 버튼**: `templates/dashboard.html` 안에 있음 (ON=초록/OFF=빨강 토글)

### 수정 대상 파일
| 파일 | 변경 내용 |
|---|---|
| `voice/pipeline.py` | Gemini 제거, 대폭 축소 |
| `voice/router.py` | WebSocket 프로토콜 변경 (텍스트 수신→Claude→텍스트+오디오 전송) |
| `chatbot/llm_client.py` | 마크다운 금지 프롬프트 강화, voice에서도 import 가능하게 |
| `chatbot/tts.py` | **신규** — clean_for_tts() + Google TTS 공용 모듈 |
| `templates/dashboard.html` | 마이크 버튼 ON/OFF 토글, Web Speech API JS 추가 |
| `requirements.txt` | google-generativeai 제거 |

### Claude에게 작업 지시 시 필수 포함 문구
```
관련 파일 전부 스스로 확인하고, app.py만 건드리지 말고
위 수정 대상 파일 전부 수정해줘. 뭘 어디서 바꿨는지 파일별로 정리해줘.
```

### API 키 현황 (voice 관련)
- `GOOGLE_TTS_API_KEY` → `chatbot/tts.py`에서 사용
- `CLAUDE_API_KEY` → `chatbot/llm_client.py`에서 사용 (기존과 동일)
- `GEMINI_API_KEY` → 더 이상 사용 안 함 (코드에서 참조 제거됨)
- `DEEPGRAM_API_KEY` → 한국어 미지원으로 사용 안 함 (키만 보관)

---

## 실행 방법 (빠른 참조)

```powershell
# Docker 실행
docker-compose up --build

# 로컬 직접 실행 (DB 없이 테스트)
uvicorn app:app --host 0.0.0.0 --port 5000 --reload

# 접속
http://localhost:5000

# 흐름도 재생성
python make_flowchart.py   # → flowchart/ 폴더에 저장됨
```

---

## 브랜치 머지 이력 (feat/hj 기준)

| 날짜 | 머지 브랜치 | 주요 변경 | 충돌 해결 |
|---|---|---|---|
| 2026-04-15 | `origin/feat/cs` | 구글 캘린더 연동, 브라이언 캐릭터 추가, 캘린더/패널 UX 개선 | requirements.txt — authlib 버전 충돌 → `1.6.10` 유지 |
| 2026-04-15 | `origin/feat/ny2` | 수석디자이너 UI + 챗봇 최종 수정, ultralytics/polars 추가 | requirements.txt — pip freeze 덤프 vs 카테고리 형식 → 카테고리 형식 유지, 신규 패키지만 반영 |

---

## 주요 버그 수정 이력

| 날짜 | 파일 | 문제 | 수정 내용 |
|---|---|---|---|
| 2026-04-15 | `static/css/style.css` | 대시보드 배경 이미지 안 나옴 | `feat/ny2` 머지 시 `room_bg.png` → `room_bf.png`로 파일명 변경됐으나 CSS는 미반영 → CSS 경로 수정 |

---

## 현재 확인된 미구현 기능 (DB 스키마는 있음)

`docker/init.sql`에 테이블은 설계되어 있지만 Python 코드가 없는 기능:

| 테이블 | 기능 | 상태 |
|---|---|---|
| `style_logs` | 코디 추천 로그 자동 저장 | DB 설계만 완료, 저장 코드 없음 |
| `recommendation_items` | 추천 아이템 연결 | DB 설계만 완료 |
| `top_outfits_by_weather` (VIEW) | 날씨별 인기 코디 집계 | DB 설계만 완료 |

→ 좋아요/싫어요 피드백 기능 추가 시 위 테이블에 연동하면 됨

