# ── 베이스 이미지 ──────────────────────────────────
FROM python:3.10-slim

WORKDIR /app

# ── 시스템 패키지 (최소화: X11 display 라이브러리 제거) ──
# libsm6 / libxext6 / libxrender-dev 는 GUI/X11용 → 서버 환경 불필요
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    libglib2.0-0 \
    libgl1 \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# ── Python 의존성 설치 ─────────────────────────────
# requirements.txt 먼저 복사 → 소스 변경 시 pip 레이어 캐시 재사용
COPY requirements.txt .

# 나머지 패키지 설치 (torch 제외 — requirements.txt에 포함됨)
RUN grep -vE "^torch(audio|vision)?[>=!]" requirements.txt | pip install -r /dev/stdin --extra-index-url https://download.pytorch.org/whl/cpu

# ── 앱 소스 복사 ───────────────────────────────────
COPY . .

# ── 업로드 디렉토리 생성 ───────────────────────────
RUN mkdir -p static/uploads

# ── 포트 노출 ─────────────────────────────────────
EXPOSE 5000

# ── 실행 명령 ─────────────────────────────────────
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "5000"]
