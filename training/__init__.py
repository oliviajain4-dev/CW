"""
training/ — 누적 학습 파이프라인

설계 원칙 (CLAUDE.md 폴더 구조 규칙 준수):
- 메인 실행 스크립트는 CW/retrain_classifier.py (루트)
- 이 폴더에는 모듈(서브루틴)만 위치
- 산출물(데이터셋 스냅샷/모델 체크포인트)은 datasets/·checkpoints/ 안에 저장

흐름:
  retrain_classifier.py
    → build_dataset.build()   (정정 데이터 + 임베딩 → parquet 스냅샷)
    → train.train_classifier()(sklearn 경량 모델 학습 → joblib 저장)
    → evaluate.evaluate()     (metrics.json 저장, DB classifier_versions 갱신)

추론 시:
  model.py의 _try_load_custom_classifier()가
  training.classifier.CustomClassifier.load_active() 로 불러옴.
"""
