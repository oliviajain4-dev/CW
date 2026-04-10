"""
model.py — 이미지 분석 핵심 모듈
- 배경 제거 (rembg)
- 전처리 (resize, normalize)
- Marqo-FashionSigLIP 분석
- 카테고리 기반 두께/질감 추론
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

# ── Marqo 분석 ──────────────────────────────────
def analyze_outfit(image_path, remove_bg=True):
    """
    이미지 분석 후 카테고리 + 두께 + 질감 반환

    반환 형식:
    {
        "상의":   {"item": "knit sweater", "thickness": "두꺼움", "warmth": 3, "texture": "knit"},
        "하의":   {"item": "jeans",        "thickness": "보통",   "warmth": 2, "texture": "denim"},
        "아우터": {"item": "coat",         "thickness": "두꺼움", "warmth": 4, "texture": "wool"},
        "총_보온도": 9   ← warmth 합산 (날씨 연동할 때 활용)
    }
    """
    if not TORCH_AVAILABLE or not PIL_AVAILABLE:
        raise RuntimeError("AI 분석 모듈(torch/PIL)이 설치되지 않았습니다.")

    _ensure_model()  # 첫 호출 시에만 모델 다운로드/로드

    image = preprocess_image(image_path, remove_bg=remove_bg)
    tensor = _preprocess(image).unsqueeze(0)  # type: ignore[operator]
    result: dict = {}
    total_warmth = 0

    with torch.no_grad():  # type: ignore[attr-defined]
        image_features = _model.encode_image(tensor)  # type: ignore[operator]
        image_features = image_features / image_features.norm(dim=-1, keepdim=True)

        # ── 각 그룹별 최고 확률 예측 (텍스트 임베딩 캐시) ──
        def get_score(part, labels):
            if part not in _text_features_cache:
                text  = _tokenizer(labels)  # type: ignore[operator]
                feats = _model.encode_text(text)  # type: ignore[operator]
                feats = feats / feats.norm(dim=-1, keepdim=True)
                _text_features_cache[part] = feats
            feats = _text_features_cache[part]
            probs = (image_features @ feats.T).softmax(dim=-1)
            return labels[probs.argmax()], probs.max().item()

        outer_pred, outer_prob   = get_score("아우터", outer_labels)
        dress_pred, dress_prob   = get_score("원피스", dress_labels)
        top_pred,   top_prob     = get_score("상의",   top_labels)
        bottom_pred, bottom_prob = get_score("하의",   bottom_labels)

        # ── 카테고리 결정 우선순위 ──────────────────
        # 1순위: 아우터 (확률 > 0.5 이고 no outer 아님)
        # 2순위: 원피스 (dress 계열 확률 > 0.6 이고 no dress 아님)
        # 3순위: 상의/하의 중 확률 높은 것
        has_outer = (outer_pred != "no outer" and outer_prob > 0.5)
        has_dress = (dress_pred != "no dress" and dress_prob > 0.6)

        if has_outer:
            final_category = "아우터"
            final_item     = outer_pred
        elif has_dress:
            final_category = "원피스"
            final_item     = dress_pred
        elif top_prob >= bottom_prob:
            final_category = "상의"
            final_item     = top_pred
        else:
            final_category = "하의"
            final_item     = bottom_pred

        info = THICKNESS_MAP.get(final_item, {"thickness": "보통", "warmth": 1, "texture": "mixed"})
        result[final_category] = {
            "item":      final_item,
            "thickness": info["thickness"],
            "warmth":    info["warmth"],
            "texture":   info["texture"],
        }
        total_warmth = info["warmth"]

    result["총_보온도"] = total_warmth
    return result

# ── 배치 분석 (여러 장 한 번에) ─────────────────────────────────────
def analyze_outfit_batch(image_paths: list) -> list:
    """
    여러 이미지를 배치로 한 번에 분석.
    encode_image를 N번 → 1번으로 줄여 CPU 추론 시간 대폭 단축.

    반환: analyze_outfit()과 동일한 dict의 리스트
    """
    if not TORCH_AVAILABLE or not PIL_AVAILABLE:
        raise RuntimeError("AI 분석 모듈(torch/PIL)이 설치되지 않았습니다.")

    _ensure_model()

    # 전처리 → 배치 텐서 (N, 3, 224, 224)
    tensors = [_preprocess(preprocess_image(p)) for p in image_paths]
    batch   = torch.stack(tensors)  # type: ignore[attr-defined]

    results = []
    with torch.no_grad():  # type: ignore[attr-defined]
        # 핵심: N장을 한 번의 forward pass로 처리
        image_features = _model.encode_image(batch)  # type: ignore[operator]
        image_features = image_features / image_features.norm(dim=-1, keepdim=True)

        # 텍스트 임베딩 (캐시 — 최초 1회만 계산)
        def get_feats(part, labels):
            if part not in _text_features_cache:
                text  = _tokenizer(labels)  # type: ignore[operator]
                feats = _model.encode_text(text)  # type: ignore[operator]
                feats = feats / feats.norm(dim=-1, keepdim=True)
                _text_features_cache[part] = feats
            return _text_features_cache[part]

        outer_feats  = get_feats("아우터", outer_labels)
        dress_feats  = get_feats("원피스", dress_labels)
        top_feats    = get_feats("상의",   top_labels)
        bottom_feats = get_feats("하의",   bottom_labels)

        for i in range(len(image_paths)):
            feat = image_features[i:i+1]  # (1, D)

            outer_probs  = (feat @ outer_feats.T).softmax(dim=-1)
            dress_probs  = (feat @ dress_feats.T).softmax(dim=-1)
            top_probs    = (feat @ top_feats.T).softmax(dim=-1)
            bottom_probs = (feat @ bottom_feats.T).softmax(dim=-1)

            outer_pred  = outer_labels[outer_probs.argmax()]
            dress_pred  = dress_labels[dress_probs.argmax()]
            top_pred    = top_labels[top_probs.argmax()]
            bottom_pred = bottom_labels[bottom_probs.argmax()]

            has_outer = (outer_pred != "no outer" and outer_probs.max().item() > 0.5)
            has_dress = (dress_pred != "no dress" and dress_probs.max().item() > 0.6)

            if has_outer:
                final_category, final_item = "아우터", outer_pred
            elif has_dress:
                final_category, final_item = "원피스", dress_pred
            elif top_probs.max().item() >= bottom_probs.max().item():
                final_category, final_item = "상의", top_pred
            else:
                final_category, final_item = "하의", bottom_pred

            info = THICKNESS_MAP.get(final_item, {"thickness": "보통", "warmth": 1, "texture": "mixed"})
            results.append({
                final_category: {
                    "item":      final_item,
                    "thickness": info["thickness"],
                    "warmth":    info["warmth"],
                    "texture":   info["texture"],
                },
                "총_보온도": info["warmth"],
            })

    return results


# ── 보온도 기반 계절 추론 ────────────────────────
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