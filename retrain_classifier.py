"""
retrain_classifier.py — 누적 학습 파이프라인 메인 실행 스크립트

CLAUDE.md 규칙:
  - 메인 실행 .py는 루트(CW/)에 위치 ✓
  - 산출물(데이터셋/체크포인트)은 기능 폴더(training/) 안에 ✓

실행:
  # 1회 수동 실행 (기본)
  python retrain_classifier.py

  # 태그 지정
  python retrain_classifier.py --tag v2_20260420

  # 활성화 없이 학습만 (canary 검증용)
  python retrain_classifier.py --no-activate

  # 스케줄 예시 (크론):
  #   0 3 * * *  cd /app && python retrain_classifier.py >> logs/retrain.log 2>&1

파이프라인 흐름:
  1. training.build_dataset.build()   → parquet 스냅샷 생성 + training_runs 기록
  2. training.train.train_classifier()→ item_type 분류기 학습 + classifier_versions 기록
  3. training.train.train_classifier()→ category 분류기 학습(보조)
  4. training.evaluate.evaluate()     → 상세 평가 리포트 저장

성공 시 자동으로 classifier_versions.is_active=TRUE → 서버 재시작 시 반영
(즉시 반영하려면 app.py의 /admin/reload-classifier 같은 엔드포인트에서
 model.invalidate_custom_classifier() 호출)
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime


def main() -> int:
    ap = argparse.ArgumentParser(description="옷장 분류기 누적 재학습 파이프라인")
    ap.add_argument("--tag", default=None,
                    help="실행 태그 (기본: 타임스탬프)")
    ap.add_argument("--target", default="both",
                    choices=["both", "item_type", "category"],
                    help="학습할 타겟")
    ap.add_argument("--model", default="logreg",
                    choices=["logreg", "lightgbm", "mlp"])
    ap.add_argument("--no-activate", action="store_true",
                    help="학습만 하고 서빙에 반영하지 않음 (canary/수동 검증용)")
    ap.add_argument("--min-samples-per-label", type=int, default=3,
                    help="클래스당 최소 샘플 수 (미달 라벨은 학습 제외)")
    args = ap.parse_args()

    run_tag = args.tag or "run_" + datetime.now().strftime("%Y%m%d_%H%M%S")
    activate = not args.no_activate

    print("=" * 60)
    print(f"[retrain_classifier] 시작 : tag={run_tag} target={args.target} "
          f"model={args.model} activate={activate}")
    print("=" * 60)

    # ── 1. 데이터셋 빌드 ─────────────────────────────────────────
    from training.build_dataset import build
    snapshot_path, ds_stats = build(
        run_tag=run_tag,
        min_samples_per_label=args.min_samples_per_label,
    )
    print(f"[retrain] 데이터셋 생성: {ds_stats}")

    # ── 2. 모델 학습 ─────────────────────────────────────────────
    from training.train import train_classifier
    from training.evaluate import evaluate

    results: dict = {"run_tag": run_tag, "dataset": ds_stats, "models": []}
    targets = (["item_type", "category"] if args.target == "both" else [args.target])

    for tgt in targets:
        metrics = train_classifier(
            snapshot_path,
            target=tgt,
            model_type=args.model,
            run_tag=f"{tgt}_{run_tag}",
            activate=activate,
        )
        # 상세 평가 (metrics.json 옆에 evaluation.json 저장)
        model_path = metrics_to_ckpt_path(metrics)
        try:
            eval_metrics = evaluate(model_path, snapshot_path)
            metrics["evaluation_summary"] = {
                k: v for k, v in eval_metrics.items()
                if k in ("n_eval", "accuracy", "topk", "labels")
            }
        except Exception as e:
            print(f"[retrain] evaluate 실패(무시): {e}")
        results["models"].append(metrics)

    # ── 3. 요약 출력 + 서버 캐시 무효화 (옵션) ────────────────────
    print("=" * 60)
    print("[retrain_classifier] 완료")
    print(json.dumps({
        "run_tag": run_tag,
        "dataset": {k: ds_stats[k] for k in ("n_samples", "n_classes", "n_dropped")
                    if k in ds_stats},
        "models":  [
            {"target":     m["target"],
             "accuracy":   m["accuracy"],
             "activated":  m.get("activated"),
             "n_train":    m["n_train"],
             "n_val":      m["n_val"]}
            for m in results["models"]
        ],
    }, ensure_ascii=False, indent=2))

    try:
        from model import invalidate_custom_classifier
        invalidate_custom_classifier()
        print("[retrain] 서버 내 custom classifier 캐시 무효화 완료 "
              "(다음 추론 시 새 모델 로드)")
    except Exception as e:
        print(f"[retrain] (주의) 캐시 무효화 실패: {e}"
              " — 서버 재시작 후 새 모델이 반영됨")

    return 0


def metrics_to_ckpt_path(metrics: dict) -> str:
    """train_classifier가 저장한 model.joblib 경로를 재구성."""
    import os
    _HERE = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(_HERE, "training", "checkpoints",
                        metrics["version_tag"], "model.joblib")


if __name__ == "__main__":
    sys.exit(main())
