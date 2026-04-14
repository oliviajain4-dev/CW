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

# ── 통합 분류 테이블 ─────────────────────────────
# 기존 방식 버그: 그룹별 독립 softmax → 라벨 수가 적은 그룹이 항상 높은 확률
# (하의 9개 vs 상의 10개 → 하의 uniform max = 1/9 > 상의 1/10 → 하의 편향)
# 수정: 모든 라벨을 하나의 softmax로 비교 → argmax = 전체에서 가장 유사한 라벨
_outer_clf  = [l for l in outer_labels if l != "no outer"]  # 9개
_dress_clf  = [l for l in dress_labels if l != "no dress"]  # 7개
_ALL_CLF_LABELS: list[str] = _outer_clf + _dress_clf + top_labels + bottom_labels  # 총 35개

_LABEL_TO_CAT: dict[str, str] = {}
for _l in _outer_clf:    _LABEL_TO_CAT[_l] = "아우터"
for _l in _dress_clf:    _LABEL_TO_CAT[_l] = "원피스"
for _l in top_labels:    _LABEL_TO_CAT[_l] = "상의"
for _l in bottom_labels: _LABEL_TO_CAT[_l] = "하의"

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

        # ── 통합 softmax로 카테고리 결정 ───────────────────────────────
        # 35개 라벨 전체를 하나의 softmax → argmax = 가장 유사한 라벨
        if "all_clf" not in _text_features_cache:
            tokens = _tokenizer(_ALL_CLF_LABELS)  # type: ignore[operator]
            feats  = _model.encode_text(tokens)   # type: ignore[operator]
            feats  = feats / feats.norm(dim=-1, keepdim=True)
            _text_features_cache["all_clf"] = feats

        all_feats = _text_features_cache["all_clf"]
        all_probs = (image_features @ all_feats.T).softmax(dim=-1)[0]  # (35,)
        best_idx  = int(all_probs.argmax())

        final_item     = _ALL_CLF_LABELS[best_idx]
        final_category = _LABEL_TO_CAT[final_item]

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
        # N장을 한 번의 forward pass로 처리
        image_features = _model.encode_image(batch)  # type: ignore[operator]
        image_features = image_features / image_features.norm(dim=-1, keepdim=True)

        # 통합 텍스트 임베딩 캐시 (35개 라벨, 최초 1회만 계산)
        if "all_clf" not in _text_features_cache:
            tokens = _tokenizer(_ALL_CLF_LABELS)  # type: ignore[operator]
            feats  = _model.encode_text(tokens)   # type: ignore[operator]
            feats  = feats / feats.norm(dim=-1, keepdim=True)
            _text_features_cache["all_clf"] = feats

        all_feats = _text_features_cache["all_clf"]  # (35, D)

        # 한 번에 N×35 유사도 계산
        all_probs = (image_features @ all_feats.T).softmax(dim=-1)  # (N, 35)

        for i in range(len(image_paths)):
            best_idx       = int(all_probs[i].argmax())
            final_item     = _ALL_CLF_LABELS[best_idx]
            final_category = _LABEL_TO_CAT[final_item]

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