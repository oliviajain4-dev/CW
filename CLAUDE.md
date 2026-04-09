# 내 옷장의 코디 — 프로젝트 규칙 (CLAUDE.md)

> **이 파일은 Claude Code가 작업 시작 시 자동으로 읽습니다.**
> 팀원 누구든, Claude를 통해 작업할 때 반드시 아래 규칙을 따르세요.

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
├── app.py                   ← Flask 웹 서버 (메인)
├── db.py                    ← DB 연결 모듈 (메인)
├── model.py                 ← 이미지 AI 분석 (메인)
├── make_flowchart.py        ← 흐름도 생성 메인 스크립트
├── make_pdf.py              ← PDF 생성 메인 스크립트 (있을 경우)
│
├── chatbot/                 ← 챗봇/추천 기능 모듈 전체
│   ├── weather.py
│   ├── weather_client.py
│   ├── weather_style_mapper.py
│   ├── llm_client.py
│   ├── recommend.py
│   └── weather_main.py
│
├── flowchart/               ← 흐름도 기능의 모든 산출물
│   ├── flowchart_2D.png
│   └── flowchart_3D.png
│
├── templates/               ← Flask HTML 템플릿
├── static/                  ← CSS, JS, 업로드 이미지
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
| `app.py` | Flask 메인 서버 |
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
| 웹 서버 | `flask` |
| AI 추천 | `anthropic` |
| 날씨 API | `requests` |
| 환경변수 | `python-dotenv` |
| 이미지 분석 (AI) | `torch`, `torchvision`, `transformers`, `open_clip_torch` |
| 흐름도 생성 | `matplotlib`, `pillow`, `numpy` |
| PDF 생성 | `reportlab` (있을 경우) |
| DB | `psycopg2` 또는 `sqlite3` (내장) |

---

## API 키 규칙

- `.env` 파일에만 저장, **절대 코드에 하드코딩 금지**
- `.env`는 **절대 Git 커밋 금지** (`.gitignore`에 포함됨)
- 팀원에게 API 키 전달 시 카카오톡/슬랙 등 별도 채널 사용

현재 필요한 키:
```
KMA_API_KEY=...       # 기상청 API (발급 완료)
CLAUDE_API_KEY=...    # Anthropic Claude API (발급 완료)
```

---

## Git 규칙

- 브랜치: 기능별로 `feat/기능명` 형식
- 커밋: 한 기능 완성 후 커밋 (잦은 소규모 커밋 지양)
- PR: `feat/*` → `main` 으로 병합
- **force push는 팀장 확인 후 진행**

---

## 실행 방법 (빠른 참조)

```powershell
# Docker 실행
docker-compose up --build

# 접속
http://localhost:5000

# 흐름도 재생성
python make_flowchart.py   # → flowchart/ 폴더에 저장됨
```
