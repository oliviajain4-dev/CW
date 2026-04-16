# My Mini Co-di 👗

> **AI 기반 개인 스타일리스트 웹 서비스**
> 내 옷장 사진을 등록하면, 오늘 날씨·일정·체형에 딱 맞는 코디를 AI 수석 디자이너가 직접 말로 알려줍니다.

---

## 목차

- [서비스 소개](#서비스-소개)
- [주요 기능](#주요-기능)
- [기술 스택](#기술-스택)
- [아키텍처](#아키텍처)
- [DB 스키마](#db-스키마)
- [폴더 구조](#폴더-구조)
- [환경 변수](#환경-변수)
- [실행 방법](#실행-방법)
- [v1.0 구현 현황](#v10-구현-현황)
- [팀원](#팀원)

---

## 서비스 소개

My Mini Co-di는 패션에 관심 있지만 매일 아침 "오늘 뭐 입지?"를 고민하는 사람들을 위한 AI 스타일링 어시스턴트입니다.

- 내 옷장 사진을 올리면 AI가 자동으로 종류·보온도·소재를 분석해 등록
- 매일 아침 기상청 날씨 데이터를 기반으로 오늘의 코디를 추천
- 30년 경력의 AI 수석 디자이너가 음성으로 직접 스타일링 조언을 전달
- 구글 캘린더 일정을 읽어 TPO(장소·상황·목적)에 맞는 코디 자동 선택
- 옷장에 없는 아이템은 무신사 링크로 바로 쇼핑 연결

---

## 주요 기능

### 1. AI 옷장 관리
- 옷 사진 업로드 → OpenCLIP + YOLO 기반 자동 분류 (상의/하의/아우터)
- 아이템 종류, 보온도(0~5), 소재 자동 분석
- Cloudinary에 사용자별 폴더로 이미지 저장
- 옷 삭제 시 Cloudinary 고아 폴더 자동 정리

### 2. 날씨 기반 코디 추천
- 기상청 단기예보 API (격자 좌표 기반) 아침/낮/저녁 체감온도 수집
- 온도·강수·습도·일교차를 종합한 스타일 매핑 엔진
- 내 옷장 아이템과 날씨 조건 매칭 (보온도 필터링 포함)
- 레이어링 필요 여부 자동 판단 + 시간대별 착탈 팁 제공

### 3. AI 수석 디자이너 코멘트
- Claude API (`claude-sonnet-4-6`) 기반 개인화 스타일링 코멘트 생성
- 실제 옷장 아이템 이름을 직접 언급하는 맞춤 코디 제안
- 없는 아이템은 무신사 검색 링크로 자동 연결
- 말풍선(bubble) 형태로 상의/하의/아우터 핵심 포인트 요약

### 4. AI 수석 디자이너 음성 인터랙션 (티키타카)
- 마이크 ON 버튼 → Web Speech API로 음성 인식(STT)
- WebSocket(`/voice/ws`) 통해 실시간 Claude 응답 스트리밍
- Google Cloud TTS로 자연스러운 한국어 음성 출력
- 코멘트 낭독 중 말 끊기(Barge-in) → 위치 저장 후 대화 → 자동 재개
- TTS 정제 엔진: 알파벳·이모지·기호 한국어 치환 (`chatbot/tts.py`, `static/js/voice.js`)

### 5. 구글 캘린더 연동
- Google OAuth 로그인 후 오늘 일정 자동 조회
- 일정 키워드 분석 → TPO 자동 감지 (예: "발표" → 포멀, "운동" → 스포티)
- 일정 기반 코디 추천에 반영

### 6. 쇼핑 연동
- 날씨/스타일 조건에 맞는 아이템 부족 시 무신사 자동 검색 링크 생성
- 아이템 카테고리별 쇼핑 카드 UI (카테고리 이모지 + 색상 구분)
- 대화창 내 링크도 클릭 가능한 카드로 자동 변환

### 7. 사용자 프로필
- 키/몸무게/체형/성별/선호 스타일/온도 민감도/TPO/위치 설정
- Google OAuth 또는 이메일/비밀번호 로그인
- 프로필 기반 AI 코멘트 개인화 (체형·스타일 선호도 반영)

---

## 기술 스택

| 영역 | 기술 |
|---|---|
| **웹 프레임워크** | FastAPI + Uvicorn |
| **템플릿** | Jinja2 |
| **DB** | PostgreSQL 15 (Docker), SQLite (로컬 개발) |
| **인증** | Flask-Login + Authlib (Google OAuth 2.0) |
| **이미지 저장** | Cloudinary |
| **AI 분류** | OpenCLIP + YOLO (Ultralytics) |
| **AI 스타일링** | Claude API (claude-sonnet-4-6) |
| **날씨** | 기상청 단기예보 API (KMA) |
| **음성 STT** | Web Speech API (브라우저 내장, 한국어) |
| **음성 TTS** | Google Cloud Text-to-Speech REST API |
| **실시간 통신** | WebSocket (FastAPI + Starlette) |
| **3D 캐릭터** | Three.js (GLB 모델) |
| **마크다운 렌더** | marked.js v9 |
| **컨테이너** | Docker + docker-compose |

---

## 아키텍처

```
브라우저
│
├── [대시보드 로드]
│     ├── GET /api/recommend?quick=true  → 날씨/스타일 즉시 표시
│     └── GET /api/recommend             → AI 코멘트 (Claude, ~4s)
│
├── [마이크 ON]
│     ├── Web Speech API (STT) ──────────────┐
│     └── WebSocket /voice/ws               │
│           ├── start_conversation           │
│           ├── user_text (STT 결과) ←───────┘
│           │     └── Claude 스트리밍 응답
│           │           ├── sentence_text (문장별 텍스트)
│           │           ├── audio_chunk (Google TTS PCM)
│           │           └── response_text (전체 완성 텍스트)
│           ├── barge_in (말 끊기)
│           └── resume_outfit (중단 위치에서 낭독 재개)
│
└── [옷 등록]
      ├── POST /wardrobe/upload
      │     ├── OpenCLIP/YOLO 분류
      │     └── Cloudinary 저장
      └── GET /wardrobe

서버 (FastAPI)
├── app.py              ← 라우터 통합, 인증, 세션
├── db.py               ← PostgreSQL / SQLite 연결
├── model.py            ← 이미지 AI 분석
├── chatbot/
│   ├── weather_client.py      ← 기상청 API
│   ├── weather_style_mapper.py← 날씨→스타일 매핑
│   ├── llm_client.py          ← Claude API (코멘트 + 챗봇)
│   ├── recommend.py           ← 옷장 매칭 로직
│   ├── shopping.py            ← 무신사 쿼리 생성
│   ├── tts.py                 ← Google TTS + 정제 함수
│   └── calendar_client.py     ← Google Calendar API
└── voice/
    └── router.py              ← WebSocket 음성 파이프라인
```

---

## DB 스키마

```
users               — 사용자 계정 + 프로필 + 위치 설정
wardrobe_items      — 옷장 아이템 (카테고리/보온도/소재/이미지)
weather_logs        — 날씨 데이터 누적 (기상청 원본 포함)
style_logs          — AI 코디 추천 이력 + 사용자 피드백
recommendation_items— style_logs ↔ wardrobe_items 연결
top_outfits_by_weather (VIEW) — 날씨별 인기 코디 집계
```

> `style_logs` 저장 및 피드백(좋아요/싫어요) 기능은 v1.0에서 DB 스키마만 완료, 저장 코드는 v2에서 구현 예정

---

## 폴더 구조

```
CW/
├── app.py                   ← FastAPI 메인 서버
├── db.py                    ← DB 연결 (PostgreSQL/SQLite 자동 전환)
├── model.py                 ← 이미지 AI 분류
├── make_flowchart.py        ← 흐름도 생성 스크립트
├── make_cloudinary_cleanup.py
├── chatbot/                 ← AI 추천·날씨·TTS 모듈
├── voice/                   ← WebSocket 음성 파이프라인
├── templates/               ← Jinja2 HTML 템플릿
│   ├── base.html
│   ├── dashboard.html       ← 메인 대시보드
│   ├── wardrobe.html
│   └── profile.html
├── static/
│   ├── css/style.css
│   ├── js/main.js
│   ├── js/voice.js          ← Web Speech API + TTS 정제
│   └── images/
├── docker/
│   └── init.sql             ← PostgreSQL 초기 스키마
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
└── .env                     ← (gitignore) API 키 보관
```

---

## 환경 변수

`.env` 파일에 아래 키를 설정하세요. (`.env`는 절대 Git 커밋 금지)

```env
KMA_API_KEY=...            # 기상청 단기예보 API
CLAUDE_API_KEY=...         # Anthropic Claude API
GOOGLE_TTS_API_KEY=...     # Google Cloud Text-to-Speech
GOOGLE_CLIENT_ID=...       # Google OAuth 2.0
GOOGLE_CLIENT_SECRET=...   # Google OAuth 2.0
CLOUDINARY_URL=...         # cloudinary://api_key:secret@cloud_name
DATABASE_URL=...           # PostgreSQL 연결 문자열 (없으면 SQLite)
SECRET_KEY=...             # FastAPI 세션 서명 키
```

---

## 실행 방법

### Docker (권장)

```bash
# 최초 실행 (PostgreSQL + 앱 동시 빌드)
docker-compose up --build

# 이후 실행
docker-compose up
```

접속: http://localhost:5000

### 로컬 직접 실행

```bash
# 패키지 설치
pip install -r requirements.txt

# 서버 실행 (SQLite 자동 사용)
uvicorn app:app --host 0.0.0.0 --port 5000 --reload
```

---

## v1.0 구현 현황

### 완료
- [x] Google OAuth / 이메일 로그인·회원가입
- [x] 옷 사진 업로드 → AI 자동 분류 (OpenCLIP + YOLO)
- [x] Cloudinary 이미지 저장 (사용자별 폴더 격리)
- [x] 기상청 API 날씨 수집 (아침/낮/저녁 체감온도)
- [x] 날씨 → 스타일 매핑 엔진 (보온도·레이어링·강수 처리)
- [x] Claude AI 수석 디자이너 코멘트 (옷장 아이템 직접 언급)
- [x] 음성 어시스턴트 (STT: Web Speech API → Claude → TTS: Google)
- [x] 티키타카: 코멘트 낭독 중 말 끊기 → 대화 → 중단 위치 재개
- [x] TTS 정제 엔진 (알파벳·기호 한국어 치환, 양쪽 동기화)
- [x] 구글 캘린더 연동 → TPO 자동 감지
- [x] 무신사 쇼핑 카드 (없는 아이템 자동 링크)
- [x] 사용자 프로필 (체형·민감도·위치·선호 스타일)
- [x] 3D 캐릭터 (Three.js GLB)
- [x] Docker + PostgreSQL 배포 환경

### v2 예정
- [ ] 코디 추천 로그 저장 (`style_logs` 활용)
- [ ] 좋아요/싫어요 피드백 → 추천 모델 개선
- [ ] 날씨별 인기 코디 통계 (`top_outfits_by_weather` VIEW 활용)
- [ ] 브라이언(3D 캐릭터) GLB 파일 연결

---

## 팀원

| 이름 | 역할 | 브랜치 |
|---|---|---|
| HJ | 인증·DB·음성 파이프라인·UI 통합 | feat/hj |
| NY | AI 분류·수석 디자이너 UI·챗봇 | feat/ny2 |
| CS | 구글 캘린더·3D 캐릭터·패널 UX | feat/cs |
| JH | Flask→FastAPI 전환·날씨 엔진·Cloudinary | feat/jh |

---

*README 마지막 업데이트: v1.0 (2026-04-16)*
