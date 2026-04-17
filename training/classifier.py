"""
training/classifier.py — 추론 시 로드되는 경량 분류기 래퍼

model.py가 analyze_outfit() 안에서 이 클래스를 호출해 Marqo softmax를 대체한다.

역할:
  1. classifier_versions 테이블에서 target별 is_active=TRUE 모델을 찾는다
     (item_type / category 각각 독립적으로 active 가능)
  2. joblib 파일을 로드해서 메모리에 보관
  3. predict_one() / predict_batch() 제공

현재 규칙:
  - item_type active 모델이 있으면 그걸로 세부 라벨 예측 → category는 매핑 테이블에서 유도
  - item_type active 모델이 없고 category active 모델만 있으면 "카테고리만" 예측
    (이 경우 model.py가 카테고리 내 대표 아이템을 고르거나 fallback)
  - 둘 다 없으면 load_active()가 None 반환 → model.py에서 Marqo softmax로 fallback
"""
from __future__ import annotations

import os
import sys
from typing import Optional

_HERE = os.path.dirname(os.path.abspath(__file__))
_CW   = os.path.dirname(_HERE)
if _CW not in sys.path:
    sys.path.insert(0, _CW)


def _item_to_category_map() -> dict:
    """model.py가 정의한 _LABEL_TO_CAT 재사용."""
    try:
        from model import _LABEL_TO_CAT  # type: ignore[import]
        return dict(_LABEL_TO_CAT)
    except Exception:
        # model.py import 실패 시 빈 맵 → 미지 라벨은 "기타"
        return {}


class CustomClassifier:
    """
    단일 target(item_type 또는 category)용 래퍼.
    load_active()는 두 타겟을 모두 고려해 최적의 조합을 반환.
    """

    def __init__(self, bundle: dict, meta: dict):
        self.clf         = bundle["clf"]
        self.label_enc   = bundle["label_enc"]
        self.target      = bundle["target"]
        self.version_tag = bundle.get("version_tag", "?")
        self.meta        = meta
        self._label_to_cat = _item_to_category_map()

    # ── 내부 유틸 ────────────────────────────────────────────────
    def _decode(self, idx: int) -> str:
        return str(self.label_enc.classes_[idx])

    def _cat_from_item(self, item: str) -> str:
        return self._label_to_cat.get(item, "기타")

    # ── 단일 예측 ────────────────────────────────────────────────
    def predict_one(self, embedding) -> dict:
        """
        embedding: numpy 1D (D,) 또는 list.
        반환: {"item_type": ..., "category": ..., "confidence": ...}
        """
        import numpy as np
        x = np.asarray(embedding, dtype="float32").reshape(1, -1)

        if hasattr(self.clf, "predict_proba"):
            probs = self.clf.predict_proba(x)[0]
            idx   = int(probs.argmax())
            conf  = float(probs[idx])
        else:
            idx   = int(self.clf.predict(x)[0])
            conf  = 1.0

        label = self._decode(idx)
        if self.target == "item_type":
            return {"item_type": label,
                    "category":  self._cat_from_item(label),
                    "confidence": conf}
        else:  # category 전용 모델
            return {"item_type": label,   # category 이름이 item_type에 들어가지만
                    "category":  label,   # 호출부에서 동일하게 처리
                    "confidence": conf}

    # ── 배치 예측 ────────────────────────────────────────────────
    def predict_batch(self, embeddings) -> list:
        import numpy as np
        X = np.asarray(embeddings, dtype="float32")
        if X.ndim == 1:
            X = X.reshape(1, -1)

        results = []
        if hasattr(self.clf, "predict_proba"):
            probs = self.clf.predict_proba(X)
            idxs  = probs.argmax(axis=1)
            for i, idx in enumerate(idxs):
                label = self._decode(int(idx))
                conf  = float(probs[i, idx])
                if self.target == "item_type":
                    results.append({"item_type": label,
                                    "category":  self._cat_from_item(label),
                                    "confidence": conf})
                else:
                    results.append({"item_type": label,
                                    "category":  label,
                                    "confidence": conf})
        else:
            preds = self.clf.predict(X)
            for p in preds:
                label = self._decode(int(p))
                if self.target == "item_type":
                    results.append({"item_type": label,
                                    "category":  self._cat_from_item(label),
                                    "confidence": 1.0})
                else:
                    results.append({"item_type": label,
                                    "category":  label,
                                    "confidence": 1.0})
        return results

    # ── 로더 ─────────────────────────────────────────────────────
    @classmethod
    def load_active(cls) -> Optional["CustomClassifier"]:
        """
        현재 active 분류기 중 최우선(item_type)을 찾아 로드.
        반환 None → model.py가 Marqo softmax로 fallback.
        """
        try:
            from db import get_db, is_postgres, fetchone  # type: ignore[import]
        except Exception:
            return None
        if not is_postgres():
            return None

        try:
            with get_db() as conn:
                # item_type 모델 우선
                row = fetchone(conn, """
                    SELECT version_tag, model_type, target, checkpoint_path,
                           accuracy, top3_accuracy, created_at
                    FROM classifier_versions
                    WHERE is_active=TRUE AND target='item_type'
                    ORDER BY created_at DESC LIMIT 1
                """)
                if row is None:
                    row = fetchone(conn, """
                        SELECT version_tag, model_type, target, checkpoint_path,
                               accuracy, top3_accuracy, created_at
                        FROM classifier_versions
                        WHERE is_active=TRUE AND target='category'
                        ORDER BY created_at DESC LIMIT 1
                    """)
        except Exception as e:
            print(f"[CustomClassifier.load_active] DB 조회 실패: {e}")
            return None

        if row is None:
            return None

        ckpt = row["checkpoint_path"]
        if not os.path.exists(ckpt):
            print(f"[CustomClassifier] 체크포인트 파일 없음: {ckpt}")
            return None

        import joblib
        bundle = joblib.load(ckpt)
        meta = {
            "version_tag":  row["version_tag"],
            "model_type":   row["model_type"],
            "target":       row["target"],
            "accuracy":     float(row.get("accuracy") or 0.0),
            "top3_accuracy": row.get("top3_accuracy"),
        }
        return cls(bundle, meta)
