# ── 베이스 이미지 ──────────────────────────────────
# slim: 불필요한 패키지 제거된 경량 Python
FROM python:3.10-slim

# ── 작업 디렉토리 ──────────────────────────────────
WORKDIR /app

# ── 시스템 패키지 (OpenCV, rembg, psycopg2 빌드에 필요) ──
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender-dev \
    libgl1 \
    && rm -rf /var/lib/apt/lists/*

# ── Python 의존성 설치 ─────────────────────────────
# requirements.txt 먼저 복사 → 소스 변경 시 pip 캐시 재사용
COPY requirements.txt .

# open_clip / torch 는 CPU-only 버전 사용
# requirements.txt에 torch==...+cpu 로 명시되어 있으나 extra-index 가 필요
RUN pip install --no-cache-dir \
    flask psycopg2-binary python-dotenv requests anthropic \
    pillow werkzeug transformers cloudinary flask-login authlib

# torch CPU-only (용량 크므로 별도 레이어 — 캐시 최대 활용)
RUN pip install --no-cache-dir open_clip_torch

# ── 앱 소스 복사 ───────────────────────────────────
COPY . .

# ── 업로드 디렉토리 생성 ───────────────────────────
RUN mkdir -p static/uploads

# ── 포트 노출 ─────────────────────────────────────
EXPOSE 5000

# ── 실행 명령 ─────────────────────────────────────
# 개발: debug=True / 운영: gunicorn으로 교체
CMD ["python", "app.py"]
