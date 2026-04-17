"""
model.py — 이미지 분석 핵심 모듈
- 배경 제거 (rembg)
- 전처리 (resize, normalize)
- Marqo-FashionSigLIP 분석 (feature extractor로 고정)
- 카테고리 기반 두께/질감 추론

[2026-04-17 확장] 누적 학습 파이프라인 연동
- get_image_embedding() : pgvector에 저장할 임베딩 벡터 반환
- analyze_outfit()      : custom classifier(training/)가 있으면 우선 사용,
                          없으면 기존 Marqo 59-label softmax로 fallback
- 모델 전체는 건드리지 않음 — feature extractor로만 활용
"""

import os

try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False
    print("PIL 없음 → AI 분석 비활성화 (pip install pillow)")

try:
    import numpy as np
    NUMPY_AVAILABLE = True
except ImportError:
    NUMPY_AVAILABLE = False
    print("numpy 없음 (pip install numpy)")

try:
    import torch
    import open_clip
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False
    print("torch/open_clip 없음 → AI 분석 비활성화 (pip install torch open_clip_torch)")

# rembg 설치 필요: pip install rembg
try:
    from rembg import remove
    REMBG_AVAILABLE = True
except ImportError:
    REMBG_AVAILABLE = False
    print("rembg 없음 → 배경제거 스킵 (pip install rembg)")

# ── 모델 지연 로드 (첫 분석 요청 시에만 로드) ────────────────────
# import 시점에 로드하면 컨테이너 시작마다 ~600MB 모델을 기다려야 함
_model     = None
_preprocess = None
_tokenizer  = None

def _ensure_model():
    global _model, _preprocess, _tokenizer
    if _model is not None:
        return
    if not TORCH_AVAILABLE:
        raise RuntimeError("AI 분석 모듈(torch/open_clip)이 설치되지 않았습니다.")
    print("[model.py] FashionSigLIP 모델 로딩 중... (최초 1회만)")
    _model, _, _preprocess = open_clip.create_model_and_transforms(
        'hf-hub:Marqo/marqo-fashionSigLIP'
    )
    _tokenizer = open_clip.get_tokenizer('hf-hub:Marqo/marqo-fashionSigLIP')
    _model.eval()
    print("[model.py] 모델 로드 완료")

# ── 텍스트 임베딩 사전 캐시 (라벨은 고정이므로 한 번만 계산) ──
_text_features_cache = {}

# ── Custom Classifier (training/ 파이프라인이 만든 경량 모델) ────
# retrain_classifier.py 실행 후 training/checkpoints/<tag>/model.joblib 생성됨
# 추론 시 최신 active 버전을 로드해서 Marqo softmax 대신 사용
# 파일이 없으면 None → 기존 Marqo 59-label 방식으로 fallback
_custom_classifier = None
_custom_classifier_meta: dict = {}

def _try_load_custom_classifier() -> bool:
    """
    training/classifier.py의 CustomClassifier 로더를 사용해서
    현재 active 모델을 메모리에 올린다. DB에 active 버전이 없거나
    파일이 없으면 False 반환 → 기존 softmax fallback.
    """
    global _custom_classifier, _custom_classifier_meta
    if _custom_classifier is not None:
        return True
    try:
        from training.classifier import CustomClassifier  # type: ignore[import]
        clf = CustomClassifier.load_active()
        if clf is None:
            return False
        _custom_classifier = clf
        _custom_classifier_meta = clf.meta
        print(f"[model.py] Custom classifier 로드 완료: {clf.meta}")
        return True
    except Exception as e:
        # training 모듈 자체가 없거나 DB 연결 불가 → 조용히 fallback
        print(f"[model.py] custom classifier 로드 스킵 ({e}) → Marqo softmax fallback")
        return False


def invalidate_custom_classifier():
    """재학습 후 서버에 새 모델을 반영하고 싶을 때 호출 (app.py의 admin 엔드포인트에서 사용 가능)."""
    global _custom_classifier, _custom_classifier_meta
    _custom_classifier = None
    _custom_classifier_meta = {}

# ── 라벨 정의 ───────────────────────────────────
top_labels = [
    "t-shirt", "blouse", "shirt", "hoodie", "knit sweater",
    "crop top", "tank top", "turtleneck", "long sleeve shirt", "sweatshirt"
]
bottom_labels = [
    "jeans", "slacks", "long skirt", "mini skirt", "pleated skirt",
    "wide pants", "shorts", "midi skirt", "leggings"
]
dress_labels = [
    "dress", "one-piece dress", "maxi dress", "midi dress",
    "mini dress", "sundress", "shirt dress", "no dress"
]
outer_labels = [
    "padding jacket", "coat", "jacket", "cardigan", "blazer",
    "trench coat", "leather jacket", "denim jacket", "bomber jacket", "no outer"
]
shoe_labels = [
    "sneakers", "boots", "ankle boots", "high heels", "loafers",
    "sandals", "oxford shoes", "running shoes", "slip-on shoes", "platform shoes"
]
accessory_labels = [
    "handbag", "backpack", "crossbody bag", "sunglasses", "hat",
    "baseball cap", "beanie", "scarf", "watch", "necklace",
    "socks", "knee-high socks", "ankle socks", "stockings",
]

# ── 통합 분류 테이블 ─────────────────────────────
# Marqo-FashionSigLIP은 패션 특화 CLIP 모델 — 신발·악세서리도 학습 데이터에 포함됨
# 모든 라벨을 하나의 softmax로 비교 → argmax = 전체에서 가장 유사한 라벨
_outer_clf  = [l for l in outer_labels if l != "no outer"]  # 9개
_dress_clf  = [l for l in dress_labels if l != "no dress"]  # 7개
_ALL_CLF_LABELS: list[str] = (
    _outer_clf + _dress_clf + top_labels + bottom_labels
    + shoe_labels + accessory_labels
)  # 총 59개 (아우터9 + 원피스7 + 상의10 + 하의9 + 신발10 + 악세서리14[양말포함])

_LABEL_TO_CAT: dict[str, str] = {}
for _l in _outer_clf:        _LABEL_TO_CAT[_l] = "아우터"
for _l in _dress_clf:        _LABEL_TO_CAT[_l] = "원피스"
for _l in top_labels:        _LABEL_TO_CAT[_l] = "상의"
for _l in bottom_labels:     _LABEL_TO_CAT[_l] = "하의"
for _l in shoe_labels:       _LABEL_TO_CAT[_l] = "신발"
for _l in accessory_labels:  _LABEL_TO_CAT[_l] = "악세서리"

# ── 두께 / 질감 매핑 ────────────────────────────
# 카테고리로 두께·질감 추론
# 나중에 날씨 API 연동할 때 체감온도 계산에 활용
THICKNESS_MAP = {
    # 아우터
    "padding jacket":  {"thickness": "매우두꺼움", "warmth": 5, "texture": "synthetic"},
    "coat":            {"thickness": "두꺼움",     "warmth": 4, "texture": "wool"},
    "trench coat":     {"thickness": "보통",       "warmth": 3, "texture": "cotton"},
    "leather jacket":  {"thickness": "보통",       "warmth": 3, "texture": "leather"},
    "denim jacket":    {"thickness": "보통",       "warmth": 2, "texture": "denim"},
    "jacket":          {"thickness": "보통",       "warmth": 3, "texture": "mixed"},
    "blazer":          {"thickness": "얇음",       "warmth": 2, "texture": "wool"},
    "cardigan":        {"thickness": "얇음",       "warmth": 2, "texture": "knit"},
    "bomber jacket":   {"thickness": "보통",       "warmth": 3, "texture": "synthetic"},
    # 상의
    "knit sweater":    {"thickness": "두꺼움",     "warmth": 3, "texture": "knit"},
    "turtleneck":      {"thickness": "보통",       "warmth": 3, "texture": "knit"},
    "sweatshirt":      {"thickness": "보통",       "warmth": 2, "texture": "cotton"},
    "hoodie":          {"thickness": "보통",       "warmth": 2, "texture": "cotton"},
    "long sleeve shirt":{"thickness": "얇음",      "warmth": 1, "texture": "cotton"},
    "shirt":           {"thickness": "얇음",       "warmth": 1, "texture": "cotton"},
    "blouse":          {"thickness": "매우얇음",   "warmth": 0, "texture": "chiffon"},
    "t-shirt":         {"thickness": "매우얇음",   "warmth": 0, "texture": "cotton"},
    "crop top":        {"thickness": "매우얇음",   "warmth": 0, "texture": "mixed"},
    "tank top":        {"thickness": "매우얇음",   "warmth": 0, "texture": "cotton"},
    # 하의
    "jeans":           {"thickness": "보통",       "warmth": 2, "texture": "denim"},
    "slacks":          {"thickness": "얇음",       "warmth": 1, "texture": "wool"},
    "wide pants":      {"thickness": "얇음",       "warmth": 1, "texture": "mixed"},
    "leggings":        {"thickness": "얇음",       "warmth": 1, "texture": "spandex"},
    "midi skirt":      {"thickness": "얇음",       "warmth": 0, "texture": "mixed"},
    "long skirt":      {"thickness": "얇음",       "warmth": 0, "texture": "mixed"},
    "pleated skirt":   {"thickness": "매우얇음",   "warmth": 0, "texture": "chiffon"},
    "mini skirt":      {"thickness": "매우얇음",   "warmth": 0, "texture": "mixed"},
    "shorts":          {"thickness": "매우얇음",   "warmth": 0, "texture": "cotton"},
    "dress":           {"thickness": "매우얇음",   "warmth": 0, "texture": "mixed"},
    "one-piece dress": {"thickness": "매우얇음",   "warmth": 0, "texture": "mixed"},
    "maxi dress":      {"thickness": "얇음",       "warmth": 0, "texture": "mixed"},
    "midi dress":      {"thickness": "얇음",       "warmth": 0, "texture": "mixed"},
    "mini dress":      {"thickness": "매우얇음",   "warmth": 0, "texture": "mixed"},
    "sundress":        {"thickness": "매우얇음",   "warmth": 0, "texture": "cotton"},
    "shirt dress":     {"thickness": "얇음",       "warmth": 0, "texture": "cotton"},
    # 신발 — 보온도: 부츠=3, 앵클부츠=2, 운동화/로퍼/옥스포드/러닝=1, 샌들/힐/플랫=0
    "boots":           {"thickness": "두꺼움",     "warmth": 3, "texture": "leather"},
    "ankle boots":     {"thickness": "보통",       "warmth": 2, "texture": "leather"},
    "sneakers":        {"thickness": "얇음",       "warmth": 1, "texture": "canvas"},
    "loafers":         {"thickness": "얇음",       "warmth": 1, "texture": "leather"},
    "oxford shoes":    {"thickness": "얇음",       "warmth": 1, "texture": "leather"},
    "running shoes":   {"thickness": "얇음",       "warmth": 1, "texture": "synthetic"},
    "slip-on shoes":   {"thickness": "얇음",       "warmth": 1, "texture": "canvas"},
    "platform shoes":  {"thickness": "얇음",       "warmth": 1, "texture": "synthetic"},
    "sandals":         {"thickness": "매우얇음",   "warmth": 0, "texture": "leather"},
    "high heels":      {"thickness": "매우얇음",   "warmth": 0, "texture": "leather"},
    # 악세서리 — 스카프=2, 비니/모자=1, 나머지=0
    "scarf":           {"thickness": "보통",       "warmth": 2, "texture": "wool"},
    "beanie":          {"thickness": "얇음",       "warmth": 1, "texture": "knit"},
    "hat":             {"thickness": "얇음",       "warmth": 1, "texture": "wool"},
    "baseball cap":    {"thickness": "없음",       "warmth": 0, "texture": "cotton"},
    "handbag":         {"thickness": "없음",       "warmth": 0, "texture": "leather"},
    "backpack":        {"thickness": "없음",       "warmth": 0, "texture": "synthetic"},
    "crossbody bag":   {"thickness": "없음",       "warmth": 0, "texture": "leather"},
    "sunglasses":      {"thickness": "없음",       "warmth": 0, "texture": "none"},
    "watch":           {"thickness": "없음",       "warmth": 0, "texture": "none"},
    "necklace":        {"thickness": "없음",       "warmth": 0, "texture": "none"},
    # 양말 (악세서리로 분류)
    "knee-high socks": {"thickness": "보통",       "warmth": 2, "texture": "cotton"},
    "socks":           {"thickness": "얇음",       "warmth": 1, "texture": "cotton"},
    "stockings":       {"thickness": "매우얇음",   "warmth": 1, "texture": "nylon"},
    "ankle socks":     {"thickness": "얇음",       "warmth": 0, "texture": "cotton"},
    # 기본값
    "없음":            {"thickness": "없음",       "warmth": 0, "texture": "none"},
}

# ── 전처리 파이프라인 ────────────────────────────
def preprocess_image(image_path, remove_bg=False, target_size=(224, 224)):
    """
    1. 이미지 로드
    2. 배경 제거 (rembg) -> 이거 학원pc에서 막힘
    3. 리사이즈 ->test_preprocess로 3개 비교해봤는데 정사각형 크롭 후 리사이즈가 젤 정확도 높음
    4. Marqo 전처리
    """
    image = Image.open(image_path).convert("RGB")

    # 정사각형 크롭
    w, h = image.size
    s    = min(w, h)
    left = (w - s) // 2
    top  = (h - s) // 2
    image = image.crop((left, top, left+s, top+s))

    # 리사이즈
    image = image.resize(target_size, Image.LANCZOS)

    return image

# ── 이미지 임베딩만 뽑기 (pgvector/retrieval용) ──────────────────
def get_image_embedding(image_path) -> list:
    """
    이미지 한 장의 정규화된 임베딩 벡터를 Python list로 반환.
    DB(pgvector) 저장용 — wardrobe_items.embedding 컬럼에 바로 넣을 수 있는 형태.

    SigLIP-B/16 기준 768 차원. 모델을 바꾸면 차원이 달라지므로
    docker/init.sql의 vector(768) 선언도 함께 업데이트해야 함.
    """
    if not TORCH_AVAILABLE or not PIL_AVAILABLE:
        raise RuntimeError("AI 분석 모듈(torch/PIL)이 설치되지 않았습니다.")
    _ensure_model()
    image = preprocess_image(image_path)
    tensor = _preprocess(image).unsqueeze(0)  # type: ignore[operator]
    with torch.no_grad():  # type: ignore[attr-defined]
        feats = _model.encode_image(tensor)  # type: ignore[operator]
        feats = feats / feats.norm(dim=-1, keepdim=True)
        return feats[0].cpu().numpy().astype("float32").tolist()


# ── Marqo 분석 ──────────────────────────────────
def analyze_outfit(image_path, remove_bg=True, return_embedding: bool = False):
    """
    이미지 분석 후 카테고리 + 두께 + 질감 반환

    동작 순서:
      1. Marqo 모델로 이미지 임베딩 추출 (항상 수행)
      2. training/에서 학습한 custom classifier가 있으면 그걸로 예측
      3. 없으면 기존 Marqo 59-label softmax로 fallback
      4. return_embedding=True 이면 임베딩도 반환 (DB 저장 시 활용)

    반환 형식:
    {
        "상의":   {"item": "knit sweater", "thickness": "두꺼움", "warmth": 3, "texture": "knit"},
        "총_보온도": 3,
        "_confidence": 0.87,       ← argmax softmax 확률 (추가됨)
        "_source":    "marqo"      ← 'marqo' 또는 'custom_v1_...'
        "_embedding": [...]        ← return_embedding=True인 경우만
    }
    """
    if not TORCH_AVAILABLE or not PIL_AVAILABLE:
        raise RuntimeError("AI 분석 모듈(torch/PIL)이 설치되지 않았습니다.")

    _ensure_model()  # 첫 호출 시에만 모델 다운로드/로드

    image = preprocess_image(image_path, remove_bg=remove_bg)
    tensor = _preprocess(image).unsqueeze(0)  # type: ignore[operator]
    result: dict = {}

    with torch.no_grad():  # type: ignore[attr-defined]
        image_features = _model.encode_image(tensor)  # type: ignore[operator]
        image_features = image_features / image_features.norm(dim=-1, keepdim=True)

        # numpy로 한 번 변환해두면 custom classifier든 DB저장이든 재활용 가능
        emb_np = image_features[0].cpu().numpy().astype("float32")

        use_custom = _try_load_custom_classifier()
        final_item: str
        final_category: str
        confidence: float
        source: str

        if use_custom and _custom_classifier is not None:
            # ── 경량 분류기 경로 (누적 학습 결과) ─────────────────────
            pred = _custom_classifier.predict_one(emb_np)
            final_item     = pred["item_type"]
            final_category = pred["category"]
            confidence     = float(pred.get("confidence", 0.0))
            source         = f"custom:{_custom_classifier_meta.get('version_tag', '?')}"
        else:
            # ── Fallback: 기존 59-label softmax ─────────────────────
            if "all_clf" not in _text_features_cache:
                tokens = _tokenizer(_ALL_CLF_LABELS)  # type: ignore[operator]
                feats  = _model.encode_text(tokens)   # type: ignore[operator]
                feats  = feats / feats.norm(dim=-1, keepdim=True)
                _text_features_cache["all_clf"] = feats

            all_feats = _text_features_cache["all_clf"]
            all_probs = (image_features @ all_feats.T).softmax(dim=-1)[0]  # (59,)
            best_idx  = int(all_probs.argmax())
            final_item     = _ALL_CLF_LABELS[best_idx]
            final_category = _LABEL_TO_CAT[final_item]
            confidence     = float(all_probs[best_idx].item())
            source         = "marqo"

        info = THICKNESS_MAP.get(final_item, {"thickness": "보통", "warmth": 1, "texture": "mixed"})
        result[final_category] = {
            "item":      final_item,
            "thickness": info["thickness"],
            "warmth":    info["warmth"],
            "texture":   info["texture"],
        }
        result["총_보온도"]   = info["warmth"]
        result["_confidence"] = round(confidence, 4)
        result["_source"]     = source
        if return_embedding:
            result["_embedding"] = emb_np.tolist()

    return result

# ── 배치 분석 (여러 장 한 번에) ─────────────────────────────────────
def analyze_outfit_batch(image_paths: list, return_embedding: bool = False) -> list:
    """
    여러 이미지를 배치로 한 번에 분석.
    encode_image를 N번 → 1번으로 줄여 CPU 추론 시간 대폭 단축.

    - custom classifier가 로드되어 있으면 우선 사용, 없으면 59-label softmax
    - return_embedding=True면 각 결과에 _embedding 포함 → wardrobe_items.embedding 저장용

    반환: analyze_outfit()과 동일한 dict의 리스트
    """
    if not TORCH_AVAILABLE or not PIL_AVAILABLE:
        raise RuntimeError("AI 분석 모듈(torch/PIL)이 설치되지 않았습니다.")

    _ensure_model()

    # 전처리 → 배치 텐서 (N, 3, 224, 224)
    tensors = [_preprocess(preprocess_image(p)) for p in image_paths]
    batch   = torch.stack(tensors)  # type: ignore[attr-defined]

    results = []
    use_custom = _try_load_custom_classifier()

    with torch.no_grad():  # type: ignore[attr-defined]
        # N장을 한 번의 forward pass로 처리
        image_features = _model.encode_image(batch)  # type: ignore[operator]
        image_features = image_features / image_features.norm(dim=-1, keepdim=True)
        emb_np_all = image_features.cpu().numpy().astype("float32")  # (N, D)

        if use_custom and _custom_classifier is not None:
            # ── 경량 분류기로 일괄 예측 ───────────────────────────────
            preds = _custom_classifier.predict_batch(emb_np_all)
            for i, pred in enumerate(preds):
                final_item     = pred["item_type"]
                final_category = pred["category"]
                confidence     = float(pred.get("confidence", 0.0))
                source         = f"custom:{_custom_classifier_meta.get('version_tag', '?')}"
                info = THICKNESS_MAP.get(final_item, {"thickness": "보통", "warmth": 1, "texture": "mixed"})
                res_dict: dict = {
                    final_category: {
                        "item":      final_item,
                        "thickness": info["thickness"],
                        "warmth":    info["warmth"],
                        "texture":   info["texture"],
                    },
                    "총_보온도":   info["warmth"],
                    "_confidence": round(confidence, 4),
                    "_source":     source,
                }
                if return_embedding:
                    res_dict["_embedding"] = emb_np_all[i].tolist()
                results.append(res_dict)
            return results

        # ── Fallback: 기존 59-label softmax 경로 ───────────────────
        if "all_clf" not in _text_features_cache:
            tokens = _tokenizer(_ALL_CLF_LABELS)  # type: ignore[operator]
            feats  = _model.encode_text(tokens)   # type: ignore[operator]
            feats  = feats / feats.norm(dim=-1, keepdim=True)
            _text_features_cache["all_clf"] = feats

        all_feats = _text_features_cache["all_clf"]  # (59, D)
        all_probs = (image_features @ all_feats.T).softmax(dim=-1)  # (N, 59)

        for i in range(len(image_paths)):
            best_idx       = int(all_probs[i].argmax())
            final_item     = _ALL_CLF_LABELS[best_idx]
            final_category = _LABEL_TO_CAT[final_item]
            confidence     = float(all_probs[i, best_idx].item())

            info = THICKNESS_MAP.get(final_item, {"thickness": "보통", "warmth": 1, "texture": "mixed"})
            res_dict = {
                final_category: {
                    "item":      final_item,
                    "thickness": info["thickness"],
                    "warmth":    info["warmth"],
                    "texture":   info["texture"],
                },
                "총_보온도":   info["warmth"],
                "_confidence": round(confidence, 4),
                "_source":     "marqo",
            }
            if return_embedding:
                res_dict["_embedding"] = emb_np_all[i].tolist()
            results.append(res_dict)

    return results


# ── 보온도 기반 계절 추론 ────────────────────────────────────────
def infer_season(warmth_score):
    """
    총 보온도로 계절 추론
    날씨 API 연동할 때 교차 검증용
    """
    if warmth_score >= 8:
        return "겨울"
    elif warmth_score >= 5:
        return "가을/봄"
    elif warmth_score >= 2:
        return "봄/여름"
    else:
        return "여름"

# ── 메인 실행 ───────────────────────────────────
if __name__ == "__main__":
    image_folder = "images"

    if not os.path.exists(image_folder):
        os.makedirs(image_folder)
        print("images 폴더를 만들었어요! 옷 사진을 넣고 다시 실행해주세요.")
    else:
        image_files = [f for f in os.listdir(image_folder)
                       if f.endswith((".jpg", ".jpeg", ".png"))]

        if not image_files:
            print("images 폴더에 사진을 넣어주세요!")
        else:
            for img_file in image_files:
                img_path = os.path.join(image_folder, img_file)
                print(f"\n── {img_file} ──")

                result = analyze_outfit(img_path)

                for part in ["상의", "하의", "아우터"]:
                    info = result[part]
                    print(f"{part:5}: {info['item']:20} "
                          f"두께:{info['thickness']:6} "
                          f"보온:{info['warmth']}점 "
                          f"질감:{info['texture']}")

                warmth = result["총_보온도"]
                season = infer_season(warmth)
                print(f"총 보온도: {warmth}점 → 추정 계절: {season}")