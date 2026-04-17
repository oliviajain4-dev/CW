-- ================================================================
-- 내 옷장의 코디 — PostgreSQL 초기 스키마
-- docker-compose 최초 기동 시 자동 실행
-- ================================================================

-- ── 확장 ─────────────────────────────────────────────────────────
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";  -- UUID 생성
CREATE EXTENSION IF NOT EXISTS "pg_trgm";    -- 텍스트 유사도 검색
CREATE EXTENSION IF NOT EXISTS "vector";     -- pgvector: 이미지 임베딩 저장/검색 (retrieval)

-- ================================================================
-- 1. 사용자 (고객) 테이블
--    개인정보 + 스타일 선호도 저장
-- ================================================================
CREATE TABLE IF NOT EXISTS users (
    id            UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    -- 인증
    email         VARCHAR(200) UNIQUE,
    password_hash TEXT,
    google_id     TEXT UNIQUE,
    avatar_url    TEXT,
    -- 프로필
    name          VARCHAR(50),
    gender        VARCHAR(10),
    height        SMALLINT,           -- cm
    weight        SMALLINT,           -- kg
    body_type     VARCHAR(20),        -- 슬림/보통/근육형/통통
    style_pref    VARCHAR(30),        -- 캐주얼/스트릿/포멀/미니멀/페미닌
    sensitivity   SMALLINT DEFAULT 3, -- 1(추위) ~ 5(더위)
    tpo           VARCHAR(30) DEFAULT '일상',
    location_nx   SMALLINT DEFAULT 62,
    location_ny   SMALLINT DEFAULT 123,
    created_at    TIMESTAMPTZ DEFAULT NOW(),
    updated_at    TIMESTAMPTZ DEFAULT NOW()
);

-- ================================================================
-- 2. 옷장 아이템 테이블
--    이미지 분석 결과 누적 저장
-- ================================================================
CREATE TABLE IF NOT EXISTS wardrobe_items (
    id           SERIAL PRIMARY KEY,
    user_id      UUID REFERENCES users(id) ON DELETE CASCADE,
    image_path   TEXT,
    category     VARCHAR(10) NOT NULL,   -- 상의/하의/아우터
    item_type    VARCHAR(50) NOT NULL,   -- knit sweater, jeans 등
    warmth       SMALLINT DEFAULT 1,     -- 0~5 보온도
    texture      VARCHAR(30),            -- cotton, wool 등
    color_tone   VARCHAR(20),            -- 밝음/어두움/중간 (추후 분석)
    created_at   TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_wardrobe_user_id ON wardrobe_items(user_id);
CREATE INDEX IF NOT EXISTS idx_wardrobe_category ON wardrobe_items(category);

-- ── 2-1. 누적 학습용 추가 컬럼 (2026-04-17 추가) ────────────────
-- 목적: 모델이 예측한 라벨과 사용자가 정정한 라벨을 분리 저장
--       → 정정 데이터가 쌓이면 분류기 재학습 시 정답 레이블로 사용
-- 기존 category/item_type 컬럼은 "최종값(현재 UI에 표시)"으로 계속 활용
ALTER TABLE wardrobe_items ADD COLUMN IF NOT EXISTS predicted_category  VARCHAR(10);
ALTER TABLE wardrobe_items ADD COLUMN IF NOT EXISTS predicted_item_type VARCHAR(50);
ALTER TABLE wardrobe_items ADD COLUMN IF NOT EXISTS predicted_confidence REAL;        -- argmax softmax 확률
ALTER TABLE wardrobe_items ADD COLUMN IF NOT EXISTS corrected_category  VARCHAR(10);  -- 사용자가 정정한 경우만 채움
ALTER TABLE wardrobe_items ADD COLUMN IF NOT EXISTS corrected_item_type VARCHAR(50);  -- 사용자가 정정한 경우만 채움
ALTER TABLE wardrobe_items ADD COLUMN IF NOT EXISTS corrected_at        TIMESTAMPTZ;
ALTER TABLE wardrobe_items ADD COLUMN IF NOT EXISTS label_source        VARCHAR(20) DEFAULT 'auto';
    -- 'auto'           : 모델 예측 그대로
    -- 'user_corrected' : 사용자가 UI에서 정정 (학습 데이터 후보)
    -- 'verified'       : 사용자가 "맞다"고 명시적으로 확인 (골드 라벨)

-- 이미지 임베딩 저장 (pgvector) → retrieval 기반 추천에 즉시 활용
-- Marqo-FashionSigLIP 출력 차원 = 768 (ViT-B/16 SigLIP 기반)
-- 차원이 다른 모델로 교체 시 ALTER 필요
ALTER TABLE wardrobe_items ADD COLUMN IF NOT EXISTS embedding vector(768);
ALTER TABLE wardrobe_items ADD COLUMN IF NOT EXISTS embedding_model VARCHAR(60) DEFAULT 'marqo-fashionSigLIP';

-- 이미지 임베딩 유사도 검색용 인덱스 (코사인 거리, IVFFlat)
-- 레코드가 충분히 쌓이면 (>1000) 성능이 뚜렷하게 좋아짐
CREATE INDEX IF NOT EXISTS idx_wardrobe_embedding ON wardrobe_items
    USING ivfflat (embedding vector_cosine_ops) WITH (lists = 50);

CREATE INDEX IF NOT EXISTS idx_wardrobe_label_source ON wardrobe_items(label_source);

-- ================================================================
-- 3. 날씨 로그 테이블
--    매일 실제 날씨 데이터 누적 → 향후 예측 정확도 개선
-- ================================================================
CREATE TABLE IF NOT EXISTS weather_logs (
    id           SERIAL PRIMARY KEY,
    location_nx  SMALLINT,
    location_ny  SMALLINT,
    log_date     DATE DEFAULT CURRENT_DATE,
    morning_tmp  NUMERIC(4,1),    -- 아침 체감온도
    afternoon_tmp NUMERIC(4,1),   -- 낮 체감온도
    evening_tmp  NUMERIC(4,1),    -- 저녁 체감온도
    morning_reh  SMALLINT,        -- 아침 습도
    precip_type  SMALLINT,        -- 강수형태 (0:없음 1:비 2:진눈깨비 3:눈 4:소나기)
    temp_range   NUMERIC(4,1),    -- 일교차
    raw_data     JSONB,           -- 기상청 원본 데이터 전체
    created_at   TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_weather_date ON weather_logs(log_date);
CREATE INDEX IF NOT EXISTS idx_weather_location ON weather_logs(location_nx, location_ny);

-- ================================================================
-- 4. 스타일 추천 로그 테이블
--    AI가 추천한 코디 기록 → 피드백 수집 → 모델 개선
-- ================================================================
CREATE TABLE IF NOT EXISTS style_logs (
    id               SERIAL PRIMARY KEY,
    user_id          UUID REFERENCES users(id) ON DELETE SET NULL,
    weather_log_id   INTEGER REFERENCES weather_logs(id) ON DELETE SET NULL,
    log_date         DATE DEFAULT CURRENT_DATE,
    tpo              VARCHAR(30),
    -- 추천 결과 (JSON으로 전체 저장)
    style_rec        JSONB,   -- condition_label, recommended_items, avoid_items 등
    layering_info    JSONB,   -- layering_needed, layering_tip 등
    ai_comment       TEXT,    -- Claude가 생성한 코멘트 전문
    -- 사용자 피드백 (나중에 수집)
    feedback_score   SMALLINT CHECK (feedback_score BETWEEN 1 AND 5),  -- 1~5점
    feedback_text    TEXT,    -- 자유 피드백
    was_worn         BOOLEAN, -- 실제로 이 코디를 입었는지
    created_at       TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_style_logs_user ON style_logs(user_id);
CREATE INDEX IF NOT EXISTS idx_style_logs_date ON style_logs(log_date);

-- ================================================================
-- 5. 추천 아이템 매핑 테이블
--    style_logs ↔ wardrobe_items 연결
--    "그날 어떤 옷이 추천됐는지" 정확히 기록
-- ================================================================
CREATE TABLE IF NOT EXISTS recommendation_items (
    id            SERIAL PRIMARY KEY,
    style_log_id  INTEGER REFERENCES style_logs(id) ON DELETE CASCADE,
    wardrobe_item_id INTEGER REFERENCES wardrobe_items(id) ON DELETE SET NULL,
    category      VARCHAR(10),   -- 상의/하의/아우터
    item_type     VARCHAR(50),   -- DB에 없는 경우 텍스트로 저장
    -- 아이템 단위 피드백 (2026-04-17 추가) → re-ranker 학습 라벨
    user_liked    BOOLEAN,       -- NULL=무반응 / true=좋아요 / false=싫어요
    was_worn      BOOLEAN,       -- 실제 착용했는지 (강한 긍정 신호)
    created_at    TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_rec_items_log ON recommendation_items(style_log_id);
CREATE INDEX IF NOT EXISTS idx_rec_items_liked ON recommendation_items(user_liked);

-- ================================================================
-- 5-1. 모델 버전/학습 이력 (2026-04-17 추가)
--      training/ 파이프라인이 재학습할 때마다 이력을 남김
--      → 추론 시 최신 버전 로드, A/B 테스트 시 특정 버전 고정 가능
-- ================================================================
CREATE TABLE IF NOT EXISTS classifier_versions (
    id             SERIAL PRIMARY KEY,
    version_tag    VARCHAR(40) UNIQUE NOT NULL,   -- 예: 'v1_20260417', 'canary_...'
    model_type     VARCHAR(30) NOT NULL,          -- 'logreg' / 'lightgbm' / 'mlp'
    target         VARCHAR(30) NOT NULL,          -- 'category' / 'item_type'
    checkpoint_path TEXT NOT NULL,                -- training/checkpoints/v1_.../model.joblib
    n_train        INTEGER,
    n_val          INTEGER,
    accuracy       REAL,
    top3_accuracy  REAL,
    notes          TEXT,
    is_active      BOOLEAN DEFAULT FALSE,         -- 추론 시 현재 사용 중인 버전
    created_at     TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_classifier_active ON classifier_versions(is_active, target);

-- ================================================================
-- 5-2. 학습 데이터셋 스냅샷 (감사/재현용)
-- ================================================================
CREATE TABLE IF NOT EXISTS training_runs (
    id              SERIAL PRIMARY KEY,
    run_tag         VARCHAR(40) UNIQUE NOT NULL,
    snapshot_path   TEXT,                          -- training/datasets/run_tag.parquet
    label_source_filter VARCHAR(30),               -- 'user_corrected,verified' 등
    n_samples       INTEGER,
    label_distribution JSONB,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- ================================================================
-- 6. 모델 성능 개선용 뷰
--    피드백 점수가 높은 날씨-코디 조합 자동 집계
-- ================================================================
CREATE OR REPLACE VIEW top_outfits_by_weather AS
SELECT
    sl.tpo,
    wl.morning_tmp,
    wl.precip_type,
    sl.style_rec->>'condition_label' AS weather_label,
    sl.style_rec->>'recommended_items' AS recommended,
    ROUND(AVG(sl.feedback_score), 2) AS avg_score,
    COUNT(*) AS sample_count
FROM style_logs sl
JOIN weather_logs wl ON sl.weather_log_id = wl.id
WHERE sl.feedback_score IS NOT NULL
GROUP BY sl.tpo, wl.morning_tmp, wl.precip_type,
         sl.style_rec->>'condition_label', sl.style_rec->>'recommended_items'
HAVING COUNT(*) >= 3
ORDER BY avg_score DESC;

-- ================================================================
-- 7. updated_at 자동 갱신 트리거
-- ================================================================
CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE OR REPLACE TRIGGER users_updated_at
    BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION set_updated_at();

-- ================================================================
-- 8. 기본 테스트 데이터 (선택)
-- ================================================================
-- 초기 테스트 계정 (비밀번호: test1234 의 bcrypt hash — 실제 배포 전 삭제)
-- INSERT INTO users (name, email, password_hash, gender, height, weight, body_type, style_pref)
-- VALUES ('테스트유저', 'test@example.com', '...hash...', '여성', 165, 52, '보통', '캐주얼')
-- ON CONFLICT DO NOTHING;
