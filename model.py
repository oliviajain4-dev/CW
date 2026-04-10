"""
model.py — 이미지 분석 핵심 모듈
- 배경 제거 (rembg)
- 전처리 (resize, normalize)
- Marqo-FashionSigLIP 분석
- 카테고리 기반 두께/질감 추론
"""

import torch
import open_clip
import os
import numpy as np
from PIL import Image

# rembg 설치 필요: pip install rembg
try:
    from rembg import remove
    REMBG_AVAILABLE = True
except ImportError:
    REMBG_AVAILABLE = False
    print("rembg 없음 → 배경제거 스킵 (pip install rembg)")

# ── 모델 로드 ───────────────────────────────────
model, _, preprocess = open_clip.create_model_and_transforms(
    'hf-hub:Marqo/marqo-fashionSigLIP'
)
tokenizer = open_clip.get_tokenizer('hf-hub:Marqo/marqo-fashionSigLIP')
model.eval()

# ── 텍스트 임베딩 사전 캐시 (라벨은 고정이므로 한 번만 계산) ──
_text_features_cache = {}

# ── 라벨 정의 ───────────────────────────────────
top_labels = [
    "t-shirt", "blouse", "shirt", "hoodie", "knit sweater",
    "crop top", "tank top", "turtleneck", "long sleeve shirt", "sweatshirt"
]
bottom_labels = [
    "jeans", "slacks", "long skirt", "mini skirt", "pleated skirt",
    "dress", "wide pants", "shorts", "midi skirt", "leggings"
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
    image = preprocess_image(image_path, remove_bg=remove_bg)
    tensor = preprocess(image).unsqueeze(0)
    result = {}
    total_warmth = 0

    with torch.no_grad():
        image_features = model.encode_image(tensor)
        image_features = image_features / image_features.norm(dim=-1, keepdim=True)

        # 각 카테고리별 최고 확률과 예측 수집 (텍스트 임베딩 캐시 활용)
        category_scores = {}
        for part, labels in [("상의", top_labels),
                              ("하의", bottom_labels),
                              ("아우터", outer_labels)]:
            cache_key = part
            if cache_key not in _text_features_cache:
                text  = tokenizer(labels)
                feats = model.encode_text(text)
                feats = feats / feats.norm(dim=-1, keepdim=True)
                _text_features_cache[cache_key] = feats
            feats = _text_features_cache[cache_key]
            probs = (image_features @ feats.T).softmax(dim=-1)
            pred  = labels[probs.argmax()]
            prob  = probs.max().item()
            category_scores[part] = (pred, prob)

        # ── 카테고리 결정 로직 ──────────────────────
        outer_pred, outer_prob = category_scores["아우터"]
        top_pred,   top_prob   = category_scores["상의"]
        bottom_pred, bottom_prob = category_scores["하의"]

        has_outer = (outer_pred != "no outer" and outer_prob > 0.5)

        # 아우터가 감지됐으면 → 아우터 사진이므로 상의/하의는 저장 안 함
        # 아우터가 없으면 → 상의/하의 중 확률 높은 것 하나만 저장
        if has_outer:
            best_main = None  # 아우터 사진 → 상의/하의 모두 없음
        else:
            best_main = "상의" if top_prob >= bottom_prob else "하의"

        for part, labels in [("상의", top_labels), ("하의", bottom_labels), ("아우터", outer_labels)]:
            pred, prob = category_scores[part]

            if part == "아우터":
                item = pred if has_outer else "없음"
            elif best_main is None:
                item = "없음"   # 아우터 사진 → 상의/하의 없음
            elif part == best_main:
                item = pred
            else:
                item = "없음"

            info = THICKNESS_MAP.get(item, {"thickness": "보통", "warmth": 1, "texture": "mixed"})
            result[part] = {
                "item":      item,
                "thickness": info["thickness"],
                "warmth":    info["warmth"],
                "texture":   info["texture"],
            }
            total_warmth += info["warmth"]

    result["총_보온도"] = total_warmth  # 낮을수록 여름옷, 높을수록 겨울옷
    return result

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