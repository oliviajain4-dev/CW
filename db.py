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
