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

# torch CPU 전용 먼저 설치 (PyPI 버전은 CUDA 의존이라 별도 인덱스 사용)
RUN pip install torch torchvision \
    --index-url https://download.pytorch.org/whl/cpu

# 나머지 패키지 설치
RUN pip install -r requirements.txt

# ── 앱 소스 복사 ───────────────────────────────────
COPY . .

# ── 업로드 디렉토리 생성 ───────────────────────────
RUN mkdir -p static/uploads

# ── 포트 노출 ─────────────────────────────────────
EXPOSE 5000

# ── 실행 명령 ─────────────────────────────────────
CMD ["python", "app.py"]
