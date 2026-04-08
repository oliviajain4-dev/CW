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
# requirements를 먼저 복사 → 코드 변경 시 캐시 재사용
COPY requirements.txt .

# open_clip / torch 는 용량이 매우 크므로 CPU-only 버전 설치
# (GPU 필요시 docker-compose.yml에서 nvidia runtime 설정)
RUN pip install --no-cache-dir \
    flask \
    psycopg2-binary \
    python-dotenv \
    requests \
    anthropic \
    pillow \
    werkzeug

# open_clip (Marqo FashionSigLIP 모델용)
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
