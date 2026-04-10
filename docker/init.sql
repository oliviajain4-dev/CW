-- ================================================================
-- 내 옷장의 코디 — PostgreSQL 초기 스키마
-- docker-compose 최초 기동 시 자동 실행
-- ================================================================

-- ── 확장 ─────────────────────────────────────────────────────────
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";  -- UUID 생성
CREATE EXTENSION IF NOT EXISTS "pg_trgm";    -- 텍스트 유사도 검색

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
    item_type     VARCHAR(50)    -- DB에 없는 경우 텍스트로 저장
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
