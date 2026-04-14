"""
make_eval.py — Marqo FashionSigLIP 정확도 평가 스크립트

사용법:
  1. tests/상의/   에 상의 사진 넣기
  2. tests/하의/   에 하의 사진 넣기
  3. tests/아우터/ 에 아우터 사진 넣기
  4. tests/원피스/ 에 원피스 사진 넣기
  5. python make_eval.py

결과: tests/eval_result.txt 로 저장됨
"""

import os
import sys
import json
from pathlib import Path

# Windows 터미널 UTF-8 출력
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# 프로젝트 루트를 경로에 추가
sys.path.insert(0, str(Path(__file__).parent))

from model import analyze_outfit

TESTS_DIR = Path(__file__).parent / "tests"
CATEGORIES = ["상의", "하의", "아우터", "원피스"]
IMG_EXTS   = {".jpg", ".jpeg", ".png", ".webp"}

def run_eval():
    total, correct = 0, 0
    per_cat: dict = {c: {"total": 0, "correct": 0, "wrong": []} for c in CATEGORIES}

    print("=" * 55)
    print("  Marqo FashionSigLIP 정확도 평가")
    print("=" * 55)

    for true_cat in CATEGORIES:
        cat_dir = TESTS_DIR / true_cat
        if not cat_dir.exists():
            print(f"\n[{true_cat}] 폴더 없음 — 건너뜀")
            continue

        images = [f for f in cat_dir.iterdir() if f.suffix.lower() in IMG_EXTS]
        if not images:
            print(f"\n[{true_cat}] 사진 없음 — 건너뜀")
            continue

        print(f"\n[{true_cat}] {len(images)}장 평가 중...")

        for img_path in sorted(images):
            try:
                result    = analyze_outfit(str(img_path))
                # analyze_outfit은 예측 카테고리를 key로 반환
                pred_cats = [k for k in result if k != "총_보온도"]
                pred_cat  = pred_cats[0] if pred_cats else "알수없음"
                pred_item = result.get(pred_cat, {}).get("item", "?")

                hit = (pred_cat == true_cat)
                mark = "O" if hit else "X"
                print(f"  {mark} {img_path.name:30s} → {pred_cat}({pred_item})")

                per_cat[true_cat]["total"] += 1
                total += 1
                if hit:
                    per_cat[true_cat]["correct"] += 1
                    correct += 1
                else:
                    per_cat[true_cat]["wrong"].append(
                        {"file": img_path.name, "predicted": pred_cat, "item": pred_item}
                    )
            except Exception as e:
                print(f"  ERR {img_path.name} 오류: {e}")

    # ── 결과 출력 ──────────────────────────────────────────────────
    print("\n" + "=" * 55)
    print("  카테고리별 정확도")
    print("=" * 55)
    for cat in CATEGORIES:
        s = per_cat[cat]
        if s["total"] == 0:
            print(f"  {cat:6}: 데이터 없음")
            continue
        acc = s["correct"] / s["total"] * 100
        bar = "█" * int(acc / 5) + "░" * (20 - int(acc / 5))
        print(f"  {cat:6}: [{bar}] {acc:5.1f}%  ({s['correct']}/{s['total']})")
        if s["wrong"]:
            for w in s["wrong"]:
                print(f"          ↳ {w['file']} → {w['predicted']}({w['item']})")

    if total > 0:
        overall = correct / total * 100
        print(f"\n  전체 정확도: {overall:.1f}%  ({correct}/{total})")
    else:
        print("\n  ⚠️  평가할 이미지가 없습니다.")
        print(f"     tests/상의/, tests/하의/ 등에 사진을 넣어주세요.")
        return

    # ── JSON 저장 ──────────────────────────────────────────────────
    out = {
        "overall_accuracy": round(overall, 1),
        "total": total,
        "correct": correct,
        "per_category": {
            c: {
                "accuracy": round(per_cat[c]["correct"] / per_cat[c]["total"] * 100, 1)
                            if per_cat[c]["total"] > 0 else None,
                "total":   per_cat[c]["total"],
                "correct": per_cat[c]["correct"],
                "wrong":   per_cat[c]["wrong"],
            }
            for c in CATEGORIES
        }
    }
    result_path = TESTS_DIR / "eval_result.json"
    result_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n  결과 저장: {result_path}")
    print("=" * 55)

if __name__ == "__main__":
    run_eval()
