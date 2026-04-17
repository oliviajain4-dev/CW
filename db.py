"""
db.py — DB 연결 모듈
- 환경변수 DATABASE_URL이 있으면 PostgreSQL 사용 (Docker 환경)
- 없으면 SQLite 폴백 (로컬 개발 시 Docker 없이도 실행 가능)
"""

import os
import json
from contextlib import contextmanager
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL")  # Docker에서 주입
_USE_POSTGRES = bool(DATABASE_URL)


# ── PostgreSQL 연결 풀 ─────────────────────────────────────────
if _USE_POSTGRES:
    import psycopg2
    from psycopg2.extras import RealDictCursor
    from psycopg2 import pool as pg_pool

    _pool = pg_pool.ThreadedConnectionPool(
        minconn=1, maxconn=10,
        dsn=DATABASE_URL
    )

    @contextmanager
    def get_db():
        conn = _pool.getconn()
        try:
            conn.autocommit = False
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            _pool.putconn(conn)

    def fetchall(conn, sql, params=()):
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(sql, params)
            return [dict(r) for r in cur.fetchall()]

    def fetchone(conn, sql, params=()):
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(sql, params)
            row = cur.fetchone()
            return dict(row) if row else None

    def execute(conn, sql, params=()):
        with conn.cursor() as cur:
            cur.execute(sql, params)

    def executereturning(conn, sql, params=()):
        """INSERT ... RETURNING id"""
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchone()[0]

# ── SQLite 폴백 ────────────────────────────────────────────────
else:
    import sqlite3

    _DB_PATH = "wardrobe.db"

    @contextmanager
    def get_db():
        conn = sqlite3.connect(_DB_PATH)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def fetchall(conn, sql, params=()):
        # SQLite: ? 플레이스홀더, PostgreSQL: %s
        cur = conn.execute(sql, params)
        return [dict(r) for r in cur.fetchall()]

    def fetchone(conn, sql, params=()):
        cur = conn.execute(sql, params)
        row = cur.fetchone()
        return dict(row) if row else None

    def execute(conn, sql, params=()):
        conn.execute(sql, params)

    def executereturning(conn, sql, params=()):
        cur = conn.execute(sql, params)
        return cur.lastrowid


def is_postgres() -> bool:
    return _USE_POSTGRES


def db_engine() -> str:
    return "PostgreSQL" if _USE_POSTGRES else "SQLite"


# ── 스타일 로그 저장 (누적 데이터 핵심) ──────────────────────────
def save_style_log(user_id, weather_data: dict, style_rec: dict,
                   layering: dict, ai_comment: str, tpo: str) -> int:
    """
    추천 결과를 style_logs 테이블에 저장
    나중에 피드백을 받아 모델 개선에 활용
    """
    if not _USE_POSTGRES:
        return None  # SQLite 환경에서는 스킵

    import psycopg2.extras
    with get_db() as conn:
        # 날씨 로그 먼저 저장
        weather_id = executereturning(conn, """
            INSERT INTO weather_logs
              (location_nx, location_ny, morning_tmp, afternoon_tmp, evening_tmp,
               morning_reh, precip_type, temp_range, raw_data)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (
            62, 123,
            weather_data["morning"]["feels_like"],
            weather_data["afternoon"]["feels_like"],
            weather_data["evening"]["feels_like"],
            weather_data["morning"]["reh"],
            weather_data["morning"]["pty"],
            weather_data["temp_range_diff"],
            json.dumps(weather_data, ensure_ascii=False)
        ))

        # 스타일 로그 저장
        log_id = executereturning(conn, """
            INSERT INTO style_logs
              (user_id, weather_log_id, tpo, style_rec, layering_info, ai_comment)
            VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING id
        """, (
            user_id,
            weather_id,
            tpo,
            json.dumps(style_rec, ensure_ascii=False),
            json.dumps(layering, ensure_ascii=False),
            ai_comment
        ))

    return log_id


def save_feedback(log_id: int, score: int, text: str = None, was_worn: bool = None):
    """
    사용자 피드백 저장 — 모델 성능 개선의 핵심 데이터
    score: 1~5점
    """
    if not _USE_POSTGRES or not log_id:
        return

    with get_db() as conn:
        execute(conn, """
            UPDATE style_logs
            SET feedback_score = %s,
                feedback_text  = %s,
                was_worn       = %s
            WHERE id = %s
        """, (score, text, was_worn, log_id))


# ==================================================================
# 누적 학습 관련 헬퍼 (2026-04-17 추가)
# ==================================================================
#
# 설계 원칙:
#   - wardrobe_items INSERT 시 predicted_* 을 채우고 category/item_type 은 동일 값으로 초기화
#     (= UI에 표시되는 "현재 값" = 최초엔 모델 예측)
#   - 사용자 정정 시 corrected_*, label_source='user_corrected' 업데이트
#     + category/item_type 도 함께 업데이트 (UI 표시 유지)
#   - 원본 predicted_* 는 절대 덮지 않음 → "모델이 무엇을 틀렸는지" 영구 기록
# ==================================================================


def save_wardrobe_item_with_embedding(user_id, image_path, category, item_type,
                                      warmth, texture, embedding, confidence=None,
                                      source="marqo") -> int:
    """
    wardrobe_items INSERT — 예측값 + 임베딩을 함께 저장.
    SQLite 환경에서는 embedding을 JSON 문자열로 저장 (pgvector 없음).

    Args:
        embedding: list[float] (모델이 뽑아낸 정규화된 임베딩 벡터) 또는 None
        confidence: float 0~1 (argmax 확률)
        source: 'marqo' | 'custom:<version_tag>' — 어느 모델이 예측했는지
    """
    if _USE_POSTGRES:
        with get_db() as conn:
            with conn.cursor() as cur:
                # pgvector는 '[0.1, -0.2, ...]' 문자열을 vector 타입으로 자동 캐스팅
                emb_str = None
                if embedding is not None:
                    emb_str = "[" + ",".join(f"{float(v):.6f}" for v in embedding) + "]"

                cur.execute("""
                    INSERT INTO wardrobe_items
                        (user_id, image_path, category, item_type, warmth, texture,
                         predicted_category, predicted_item_type, predicted_confidence,
                         label_source, embedding, embedding_model, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s,
                            %s, %s, %s,
                            'auto', %s, %s, NOW())
                    RETURNING id
                """, (user_id, image_path, category, item_type, warmth, texture,
                      category, item_type, confidence,
                      emb_str,
                      "marqo-fashionSigLIP" if source.startswith("marqo") else source))
                return int(cur.fetchone()[0])
    else:
        # SQLite 환경 — embedding은 json으로 직렬화해 TEXT 컬럼에 저장
        # (기존 스키마에는 embedding 컬럼이 없을 수 있음 → 없으면 무시하고 기본 컬럼만)
        with get_db() as conn:
            cur = conn.execute("""
                INSERT INTO wardrobe_items
                    (user_id, image_path, category, item_type, warmth, texture, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (user_id, image_path, category, item_type, warmth, texture,
                  __import__("datetime").datetime.now().isoformat()))
            return int(cur.lastrowid)


def save_correction(item_id: int,
                    corrected_category: str = None,
                    corrected_item_type: str = None) -> None:
    """
    사용자가 분류 결과를 정정했을 때 호출.
      - corrected_* 컬럼을 채우고
      - 최종값(category/item_type)도 동기화
      - label_source = 'user_corrected'
      - corrected_at = NOW()

    predicted_* 컬럼은 절대 건드리지 않음 (원본 예측 영구 보존).

    둘 다 None이면 "확인(verify)"으로 처리 → label_source='verified'
    """
    ph = "%s" if _USE_POSTGRES else "?"
    with get_db() as conn:
        if corrected_category is None and corrected_item_type is None:
            # 확인만 — 기존 값이 맞다고 선언
            execute(conn, f"""
                UPDATE wardrobe_items
                SET label_source='verified',
                    corrected_at={'NOW()' if _USE_POSTGRES else "datetime('now')"}
                WHERE id={ph}
            """, (item_id,))
            return

        # 부분 수정 지원 (카테고리만 또는 타입만)
        sets = []
        params: list = []
        if corrected_category is not None:
            sets.append(f"category={ph}")
            sets.append(f"corrected_category={ph}")
            params.extend([corrected_category, corrected_category])
        if corrected_item_type is not None:
            sets.append(f"item_type={ph}")
            sets.append(f"corrected_item_type={ph}")
            params.extend([corrected_item_type, corrected_item_type])

        sets.append(f"label_source={ph}")
        params.append("user_corrected")
        if _USE_POSTGRES:
            sets.append("corrected_at=NOW()")
        else:
            sets.append("corrected_at=datetime('now')")

        params.append(item_id)
        sql = f"UPDATE wardrobe_items SET {', '.join(sets)} WHERE id={ph}"
        execute(conn, sql, tuple(params))


def save_recommendation_items(style_log_id: int, items: list) -> None:
    """
    style_logs INSERT 후 각 추천 아이템을 recommendation_items에 기록.
      items: [{"wardrobe_item_id": int|None, "category": "상의", "item_type": "knit sweater"}, ...]
    """
    if not _USE_POSTGRES or not style_log_id or not items:
        return
    with get_db() as conn:
        for it in items:
            execute(conn, """
                INSERT INTO recommendation_items
                    (style_log_id, wardrobe_item_id, category, item_type)
                VALUES (%s, %s, %s, %s)
            """, (style_log_id, it.get("wardrobe_item_id"),
                  it.get("category"), it.get("item_type")))


def save_item_feedback(rec_item_id: int, liked: bool = None,
                       was_worn: bool = None) -> None:
    """
    개별 추천 아이템에 대한 좋아요/싫어요/착용 피드백.
    re-ranker 학습 데이터의 핵심.
    """
    if not _USE_POSTGRES or not rec_item_id:
        return
    with get_db() as conn:
        execute(conn, """
            UPDATE recommendation_items
            SET user_liked = COALESCE(%s, user_liked),
                was_worn   = COALESCE(%s, was_worn)
            WHERE id = %s
        """, (liked, was_worn, rec_item_id))


def find_similar_items(embedding: list, user_id=None, limit: int = 20,
                       exclude_item_id: int = None) -> list:
    """
    pgvector 기반 최근접 이웃 검색 (라벨 없이도 즉시 추천 품질 개선).

    Args:
        embedding: 쿼리 임베딩 (list[float])
        user_id:   주어지면 해당 유저 옷장만 대상 (None이면 전체)
        limit:     반환 개수
        exclude_item_id: 이 id는 결과에서 제외 (자기 자신 제외용)

    반환: [{id, category, item_type, image_path, similarity}, ...]
    similarity = 1 - cosine_distance (1에 가까울수록 유사)
    """
    if not _USE_POSTGRES:
        return []  # SQLite 환경에서는 retrieval 비활성
    if embedding is None:
        return []

    emb_str = "[" + ",".join(f"{float(v):.6f}" for v in embedding) + "]"
    params: list = [emb_str]
    where = ["embedding IS NOT NULL"]
    if user_id is not None:
        where.append("user_id = %s")
        params.append(user_id)
    if exclude_item_id is not None:
        where.append("id <> %s")
        params.append(exclude_item_id)

    sql = f"""
        SELECT id, category, item_type, image_path,
               1 - (embedding <=> %s::vector) AS similarity
        FROM wardrobe_items
        WHERE {' AND '.join(where)}
        ORDER BY embedding <=> %s::vector
        LIMIT %s
    """
    # <=> 연산자를 두 번 사용 — 첫 번째는 SELECT용, 두 번째는 ORDER BY용
    params = [emb_str] + params[1:] + [emb_str, limit]

    with get_db() as conn:
        return fetchall(conn, sql, tuple(params))
