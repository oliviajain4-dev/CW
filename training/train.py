"""
training/train.py — 경량 분류기 학습

Marqo-FashionSigLIP은 고정 feature extractor로 두고,
그 위에 작은 지도학습 모델(logistic regression / lightgbm / MLP)을 얹는다.

왜 이 방식인가:
  - 데이터가 수십~수천 개 수준이어도 동작
  - CPU에서 10~60초면 학습 완료
  - Marqo 모델 가중치는 그대로라 안정성 유지
  - joblib 파일 하나만 교체하면 배포 완료

target:
  - "item_type" : 세부 아이템 (jeans / knit sweater ...) — 주 타겟
  - "category"  : 상의/하의/아우터 ... — 보조(간단, 높은 정확도 기대)
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime
from typing import Optional

_HERE = os.path.dirname(os.path.abspath(__file__))
_CW   = os.path.dirname(_HERE)
if _CW not in sys.path:
    sys.path.insert(0, _CW)

from db import get_db, is_postgres, execute, executereturning  # type: ignore[import]

CHECKPOINTS_DIR = os.path.join(_HERE, "checkpoints")
os.makedirs(CHECKPOINTS_DIR, exist_ok=True)


def _load_snapshot(snapshot_path: str):
    """build_dataset가 저장한 parquet(또는 json) → (X, y_cat, y_item) 배열."""
    import numpy as np
    if snapshot_path.endswith(".parquet"):
        import pandas as pd  # type: ignore[import]
        df = pd.read_parquet(snapshot_path)
        X = np.asarray(df["embedding"].tolist(), dtype="float32")
        y_cat  = df["category"].astype(str).to_numpy()
        y_item = df["item_type"].astype(str).to_numpy()
    else:
        with open(snapshot_path, "r", encoding="utf-8") as f:
            rows = json.load(f)
        X = np.asarray([r["embedding"] for r in rows], dtype="float32")
        y_cat  = np.asarray([r["category"]  for r in rows])
        y_item = np.asarray([r["item_type"] for r in rows])
    return X, y_cat, y_item


def _load_previous_best(target: str) -> Optional[float]:
    """같은 target의 기존 active 모델의 accuracy (없으면 None).
    새 모델이 더 나빠졌는지 비교하기 위해 사용 (Canary 판단)."""
    if not is_postgres():
        return None
    try:
        from db import fetchone
        with get_db() as conn:
            row = fetchone(conn, """
                SELECT accuracy FROM classifier_versions
                WHERE target=%s AND is_active=TRUE
                ORDER BY created_at DESC LIMIT 1
            """, (target,))
            return float(row["accuracy"]) if row and row.get("accuracy") is not None else None
    except Exception:
        return None


def train_classifier(snapshot_path: str,
                     target: str = "item_type",
                     model_type: str = "logreg",
                     run_tag: Optional[str] = None,
                     activate: bool = True,
                     min_improvement: float = -0.03) -> dict:
    """
    target:   'item_type' (주) / 'category' (보조)
    model_type: 'logreg' / 'lightgbm' / 'mlp'
    activate:  True면 classifier_versions.is_active=TRUE 로 설정 (서빙에 즉시 반영)
    min_improvement: 기존 active 모델 대비 accuracy가 이만큼 떨어지면 activate=False
                     (예: -0.03 → 3%p까지 하락은 허용, 그 이상이면 롤백 안 함)
    """
    import numpy as np
    from sklearn.model_selection import train_test_split
    from sklearn.preprocessing import LabelEncoder

    if target not in ("item_type", "category"):
        raise ValueError("target must be 'item_type' or 'category'")

    run_tag = run_tag or (target + "_" + datetime.now().strftime("%Y%m%d_%H%M%S"))

    # ── 1. 데이터 로드 ──
    X, y_cat, y_item = _load_snapshot(snapshot_path)
    y = y_item if target == "item_type" else y_cat

    le = LabelEncoder()
    y_enc = le.fit_transform(y)
    n_classes = len(le.classes_)
    if n_classes < 2:
        raise RuntimeError(f"클래스가 1개뿐입니다 ({le.classes_}). 학습 불가.")

    # ── 2. train/val split ──
    # 클래스별 샘플이 너무 적으면 stratify 불가 → 자동 비활성화
    min_per_class = int(np.bincount(y_enc).min())
    stratify = y_enc if min_per_class >= 2 else None
    X_tr, X_val, y_tr, y_val = train_test_split(
        X, y_enc, test_size=0.2, random_state=42, stratify=stratify
    )

    # ── 3. 모델 학습 ──
    if model_type == "logreg":
        from sklearn.linear_model import LogisticRegression
        clf = LogisticRegression(max_iter=2000, n_jobs=1, C=1.0)
        clf.fit(X_tr, y_tr)
    elif model_type == "mlp":
        from sklearn.neural_network import MLPClassifier
        clf = MLPClassifier(hidden_layer_sizes=(256,), max_iter=200, random_state=42)
        clf.fit(X_tr, y_tr)
    elif model_type == "lightgbm":
        try:
            import lightgbm as lgb  # type: ignore[import]
        except ImportError as e:
            raise RuntimeError("lightgbm 미설치. requirements.txt에 추가하고 pip install하세요.") from e
        clf = lgb.LGBMClassifier(n_estimators=300, learning_rate=0.05, num_leaves=31)
        clf.fit(X_tr, y_tr)
    else:
        raise ValueError(f"unknown model_type: {model_type}")

    # ── 4. 평가 (평가의 상세는 evaluate.py에서도 다시 돌림, 여기선 요약) ──
    from sklearn.metrics import accuracy_score
    val_pred  = clf.predict(X_val)
    acc       = float(accuracy_score(y_val, val_pred))

    top3_acc: Optional[float] = None
    if hasattr(clf, "predict_proba"):
        import numpy as np
        probs = clf.predict_proba(X_val)
        top3  = np.argsort(-probs, axis=1)[:, :min(3, n_classes)]
        top3_acc = float(np.mean([y in top3[i] for i, y in enumerate(y_val)]))

    print(f"[train] {run_tag} — {model_type} on {target} | "
          f"n={len(X)} classes={n_classes} acc={acc:.3f} top3={top3_acc}")

    # ── 5. 저장 ──
    import joblib
    version_tag   = run_tag
    ckpt_dir      = os.path.join(CHECKPOINTS_DIR, version_tag)
    os.makedirs(ckpt_dir, exist_ok=True)
    model_path    = os.path.join(ckpt_dir, "model.joblib")

    joblib.dump({
        "clf":         clf,
        "label_enc":   le,
        "target":      target,
        "model_type":  model_type,
        "version_tag": version_tag,
        "embedding_dim": int(X.shape[1]),
    }, model_path)

    metrics = {
        "version_tag":    version_tag,
        "target":         target,
        "model_type":     model_type,
        "accuracy":       acc,
        "top3_accuracy":  top3_acc,
        "n_train":        int(len(X_tr)),
        "n_val":          int(len(X_val)),
        "classes":        list(le.classes_),
        "snapshot_path":  snapshot_path,
    }
    with open(os.path.join(ckpt_dir, "metrics.json"), "w", encoding="utf-8") as f:
        json.dump(metrics, f, ensure_ascii=False, indent=2)

    # ── 6. classifier_versions에 등록 + active 전환 (canary 체크) ──
    prev_acc = _load_previous_best(target)
    would_activate = activate
    if activate and prev_acc is not None and (acc - prev_acc) < min_improvement:
        would_activate = False
        print(f"[train] canary guard: 이전 acc={prev_acc:.3f} → 새 acc={acc:.3f} "
              f"(Δ={acc-prev_acc:+.3f}) / min_improvement={min_improvement} → 활성화 보류")

    if is_postgres():
        try:
            with get_db() as conn:
                if would_activate:
                    # 같은 target의 이전 active를 모두 내림
                    execute(conn,
                        "UPDATE classifier_versions SET is_active=FALSE WHERE target=%s",
                        (target,))
                executereturning(conn, """
                    INSERT INTO classifier_versions
                        (version_tag, model_type, target, checkpoint_path,
                         n_train, n_val, accuracy, top3_accuracy, notes, is_active)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                """, (version_tag, model_type, target, model_path,
                      metrics["n_train"], metrics["n_val"], acc, top3_acc,
                      f"snapshot={os.path.basename(snapshot_path)}",
                      would_activate))
        except Exception as e:
            print(f"[train] classifier_versions 기록 실패(계속 진행): {e}")

    metrics["activated"] = would_activate
    metrics["prev_active_accuracy"] = prev_acc
    return metrics


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("snapshot", help="training/datasets/*.parquet 경로")
    ap.add_argument("--target", default="item_type", choices=["item_type", "category"])
    ap.add_argument("--model",  default="logreg",    choices=["logreg", "lightgbm", "mlp"])
    args = ap.parse_args()
    m = train_classifier(args.snapshot, target=args.target, model_type=args.model)
    print(json.dumps(m, ensure_ascii=False, indent=2, default=str))
