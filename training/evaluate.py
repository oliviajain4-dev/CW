"""
training/evaluate.py — 학습된 분류기의 상세 성능 리포트

train.py는 학습+기본 accuracy만 계산. 여기선:
  - 혼동 행렬 (어떤 라벨이 서로 헷갈리는지)
  - per-class precision/recall/F1
  - top-k accuracy (k=1,3,5)
를 계산해서 JSON으로 저장.

사용:
  python -m training.evaluate training/checkpoints/<tag>/model.joblib training/datasets/<tag>.parquet
"""
from __future__ import annotations

import json
import os
import sys
from typing import Optional

_HERE = os.path.dirname(os.path.abspath(__file__))
_CW   = os.path.dirname(_HERE)
if _CW not in sys.path:
    sys.path.insert(0, _CW)


def _load_snapshot(snapshot_path: str):
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


def evaluate(model_path: str,
             snapshot_path: str,
             output_path: Optional[str] = None) -> dict:
    import joblib
    import numpy as np
    from sklearn.metrics import (
        accuracy_score, classification_report, confusion_matrix,
    )

    bundle = joblib.load(model_path)
    clf    = bundle["clf"]
    le     = bundle["label_enc"]
    target = bundle["target"]

    X, y_cat, y_item = _load_snapshot(snapshot_path)
    y_true_raw = y_item if target == "item_type" else y_cat
    # 미지의 라벨(새로 정정된 라벨)은 평가에서 제외
    mask = np.isin(y_true_raw, le.classes_)
    X = X[mask]
    y_true_raw = y_true_raw[mask]
    y_true = le.transform(y_true_raw)

    if len(y_true) == 0:
        return {"error": "평가 가능한 샘플 없음 (모델 라벨과 겹치는 데이터가 없습니다)."}

    # 예측 + 확률
    y_pred = clf.predict(X)
    top1 = float(accuracy_score(y_true, y_pred))

    topk_scores: dict = {"top1": top1}
    if hasattr(clf, "predict_proba"):
        probs = clf.predict_proba(X)
        for k in (3, 5):
            k_eff = min(k, probs.shape[1])
            topk = np.argsort(-probs, axis=1)[:, :k_eff]
            topk_scores[f"top{k}"] = float(np.mean([y in topk[i] for i, y in enumerate(y_true)]))

    # per-class 리포트
    report = classification_report(
        y_true, y_pred,
        labels=list(range(len(le.classes_))),
        target_names=list(le.classes_),
        output_dict=True,
        zero_division=0,
    )

    # 혼동 행렬 (전체 저장은 용량 이슈 없음 — 클래스 보통 <100)
    cm = confusion_matrix(y_true, y_pred, labels=list(range(len(le.classes_))))

    metrics = {
        "model_path":    model_path,
        "snapshot_path": snapshot_path,
        "target":        target,
        "n_eval":        int(len(y_true)),
        "accuracy":      top1,
        "topk":          topk_scores,
        "per_class":     report,
        "confusion_matrix": cm.tolist(),
        "labels":        list(le.classes_),
    }

    out = output_path or os.path.join(os.path.dirname(model_path), "evaluation.json")
    with open(out, "w", encoding="utf-8") as f:
        json.dump(metrics, f, ensure_ascii=False, indent=2)
    print(f"[evaluate] 저장 → {out}  |  accuracy={top1:.3f}  topk={topk_scores}")
    return metrics


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("model",    help="training/checkpoints/<tag>/model.joblib")
    ap.add_argument("snapshot", help="training/datasets/<tag>.parquet")
    ap.add_argument("--out",    default=None)
    args = ap.parse_args()
    evaluate(args.model, args.snapshot, args.out)
