"""
training/build_dataset.py

DB에서 학습용 데이터셋을 빌드한다.

입력:
  wardrobe_items 테이블
    - label_source가 'user_corrected' 또는 'verified'인 레코드만 사용
      (= 사람이 눈으로 확인한 정답 레이블 = 골드 라벨)
    - embedding 컬럼이 채워진 행만 사용
      (= 새 컬럼 추가 이전 레코드는 학습 데이터에서 제외)

출력:
  training/datasets/<run_tag>.parquet
    컬럼: id, user_id, category, item_type, embedding (list[float])

  training_runs 테이블에 스냅샷 메타 기록.

사용 예:
  from training.build_dataset import build
  path, stats = build(run_tag="v1_20260417")
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Optional

# 현 파일 기준 상위(CW/)를 import path에 추가 — 스크립트 직접 실행 대응
import sys
_HERE = os.path.dirname(os.path.abspath(__file__))
_CW   = os.path.dirname(_HERE)
if _CW not in sys.path:
    sys.path.insert(0, _CW)

from db import get_db, is_postgres, fetchall, executereturning  # type: ignore[import]

DATASETS_DIR = os.path.join(_HERE, "datasets")
os.makedirs(DATASETS_DIR, exist_ok=True)

# 학습 데이터로 인정할 label_source 값
ACCEPTED_SOURCES = ("user_corrected", "verified")


def _final_labels_from_row(row: dict) -> tuple[str, str]:
    """
    정정값이 있으면 그것을, 없으면 category/item_type을 최종 라벨로 사용.
    (verified 상태는 원본이 곧 정답)
    """
    cat  = row.get("corrected_category")  or row.get("category")
    item = row.get("corrected_item_type") or row.get("item_type")
    return str(cat), str(item)


def build(run_tag: Optional[str] = None,
          min_samples_per_label: int = 3) -> tuple[str, dict]:
    """
    학습 데이터셋을 파일로 저장하고 (경로, 통계 dict) 반환.

    min_samples_per_label: 한 라벨에 샘플이 이보다 적으면 학습에서 제외
                           (클래스 불균형으로 모델이 망가지는 걸 방지)
    """
    if not is_postgres():
        raise RuntimeError(
            "학습 데이터 빌드는 PostgreSQL(+pgvector) 환경에서만 지원됩니다. "
            "docker-compose up 으로 DB를 띄우고 실행해주세요."
        )

    if run_tag is None:
        run_tag = "run_" + datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    # ── 1. 후보 레코드 로드 ─────────────────────────────────────────
    # embedding::text 로 캐스팅해서 받으면 "[0.12, -0.3, ...]" 문자열로 옴 →
    # json.loads 로 간단히 역직렬화 가능 (pgvector 패키지 없이도 동작)
    placeholders = ",".join(["%s"] * len(ACCEPTED_SOURCES))
    sql = f"""
        SELECT
            id,
            user_id,
            category,
            item_type,
            corrected_category,
            corrected_item_type,
            label_source,
            embedding::text AS embedding_txt
        FROM wardrobe_items
        WHERE label_source IN ({placeholders})
          AND embedding IS NOT NULL
    """

    with get_db() as conn:
        rows = fetchall(conn, sql, tuple(ACCEPTED_SOURCES))

    if not rows:
        raise RuntimeError(
            "학습 데이터가 없습니다. 사용자 정정(label_source='user_corrected') "
            "또는 확인(label_source='verified') 레코드가 하나도 없습니다."
        )

    # ── 2. 최종 라벨 + 임베딩 파싱 ───────────────────────────────
    records: list[dict] = []
    for r in rows:
        cat, item = _final_labels_from_row(r)
        try:
            emb = json.loads(r["embedding_txt"])
        except Exception:
            continue
        if not isinstance(emb, list) or len(emb) < 64:
            continue
        records.append({
            "id":        r["id"],
            "user_id":   str(r["user_id"]) if r.get("user_id") else None,
            "category":  cat,
            "item_type": item,
            "embedding": emb,
        })

    # ── 3. 라벨 분포 + 최소 샘플 필터 ───────────────────────────────
    from collections import Counter
    cat_counts  = Counter(r["category"]  for r in records)
    item_counts = Counter(r["item_type"] for r in records)

    valid_items = {k for k, c in item_counts.items() if c >= min_samples_per_label}
    filtered = [r for r in records if r["item_type"] in valid_items]

    if len(filtered) < 10:
        raise RuntimeError(
            f"유효 샘플이 너무 적습니다 ({len(filtered)}개). "
            f"min_samples_per_label={min_samples_per_label}을 낮추거나 "
            f"정정 데이터를 더 쌓은 뒤 다시 실행해주세요."
        )

    # ── 4. parquet로 저장 (pandas가 있으면 parquet, 없으면 json 폴백) ──
    snapshot_path = os.path.join(DATASETS_DIR, f"{run_tag}.parquet")
    try:
        import pandas as pd  # type: ignore[import]
        df = pd.DataFrame(filtered)
        df.to_parquet(snapshot_path, index=False)
    except Exception as e:
        # pandas/pyarrow 없으면 json으로 폴백 (느리지만 동작 보장)
        snapshot_path = os.path.join(DATASETS_DIR, f"{run_tag}.json")
        with open(snapshot_path, "w", encoding="utf-8") as f:
            json.dump(filtered, f, ensure_ascii=False)
        print(f"[build_dataset] parquet 저장 실패({e}) → JSON으로 폴백: {snapshot_path}")

    # ── 5. training_runs에 메타 기록 ─────────────────────────────
    label_dist = {
        "category":  dict(cat_counts),
        "item_type": dict(item_counts),
        "dropped_items_under_min": [k for k, c in item_counts.items() if c < min_samples_per_label],
    }
    try:
        with get_db() as conn:
            executereturning(conn, """
                INSERT INTO training_runs
                    (run_tag, snapshot_path, label_source_filter, n_samples, label_distribution)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id
            """, (run_tag, snapshot_path, ",".join(ACCEPTED_SOURCES),
                  len(filtered), json.dumps(label_dist, ensure_ascii=False)))
    except Exception as e:
        print(f"[build_dataset] training_runs 기록 실패 (무시하고 계속): {e}")

    stats = {
        "run_tag":     run_tag,
        "n_samples":   len(filtered),
        "n_dropped":   len(records) - len(filtered),
        "n_classes":   len(valid_items),
        "categories":  dict(cat_counts),
        "snapshot":    snapshot_path,
    }
    print(f"[build_dataset] 완료: {stats}")
    return snapshot_path, stats


if __name__ == "__main__":
    # 수동 실행용: python -m training.build_dataset
    path, st = build()
    print(json.dumps(st, ensure_ascii=False, indent=2))
