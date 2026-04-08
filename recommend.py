"""
recommend.py — 날씨 + 옷장 추천 로직
- 날씨 조건 분류
- 내 옷장에서 날씨에 맞는 옷 필터링
- 최종 코디 세트 추천
나중에 chatbot.py에서 이 함수 import해서 씀
"""

import sqlite3
from weather import get_weather, classify_temp
from model import analyze_outfit
import os

# ── 날씨 카테고리별 추천 보온도 범위 ────────────
# weather.py의 classify_temp() 결과와 연동
WEATHER_WARMTH = {
    "한파":     {"min": 7, "outer": True,  "desc": "패딩·두꺼운 코트 필수"},
    "매우추움": {"min": 5, "outer": True,  "desc": "코트·두꺼운 니트 필요"},
    "추움":     {"min": 4, "outer": True,  "desc": "자켓·니트 추천"},
    "쌀쌀":     {"min": 2, "outer": True,  "desc": "가디건·청자켓 추천"},
    "선선":     {"min": 1, "outer": False, "desc": "긴팔·얇은 겉옷 추천"},
    "포근":     {"min": 0, "outer": False, "desc": "긴팔 정도면 충분"},
    "더움":     {"min": 0, "outer": False, "desc": "반팔 추천"},
    "매우더움": {"min": 0, "outer": False, "desc": "민소매·반바지 추천"},
}

# ── DB에서 옷장 불러오기 ────────────────────────
def load_wardrobe():
    """
    wardrobe.db에서 전체 옷장 불러오기
    없으면 images 폴더 분석해서 생성
    """
    if not os.path.exists("wardrobe.db"):
        print("wardrobe.db 없음 → images 폴더 분석 시작...")
        build_wardrobe()

    conn = sqlite3.connect("wardrobe.db")
    rows = conn.execute(
        "SELECT category, item_type, temp_min, temp_max, image_path FROM wardrobe"
    ).fetchall()
    conn.close()

    wardrobe = []
    for row in rows:
        wardrobe.append({
            "category":   row[0],
            "item_type":  row[1],
            "temp_min":   row[2],
            "temp_max":   row[3],
            "image_path": row[4],
        })
    return wardrobe

# ── 옷장 생성 (images 폴더 분석) ───────────────
def build_wardrobe():
    """
    images 폴더 사진 분석해서 wardrobe.db 생성
    """
    import sqlite3
    from datetime import datetime

    conn = sqlite3.connect("wardrobe.db")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS wardrobe (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            image_path  TEXT,
            category    TEXT,
            item_type   TEXT,
            temp_min    INTEGER,
            temp_max    INTEGER,
            created_at  TEXT
        )
    """)
    conn.commit()

    image_folder = "images"
    image_files  = [f for f in os.listdir(image_folder)
                    if f.endswith((".jpg", ".jpeg", ".png"))]

    for img_file in image_files:
        img_path = os.path.join(image_folder, img_file)
        result   = analyze_outfit(img_path)

        for category in ["상의", "하의", "아우터"]:
            info = result[category]
            if info["item"] == "없음":
                continue
            conn.execute("""
                INSERT INTO wardrobe
                (image_path, category, item_type, temp_min, temp_max, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                img_path, category, info["item"],
                0, 35,
                datetime.now().isoformat()
            ))

    conn.commit()
    conn.close()
    print("wardrobe.db 생성 완료!")

# ── 날씨에 맞는 옷 필터링 ───────────────────────
def filter_by_weather(wardrobe, weather):
    """
    날씨 카테고리에 맞는 옷만 필터링
    보온도 기준으로 정렬
    """
    category    = weather["category"]
    feels_temp  = weather["feels_like"]
    need_outer  = WEATHER_WARMTH[category]["outer"]
    min_warmth  = WEATHER_WARMTH[category]["min"]

    filtered = {"상의": [], "하의": [], "아우터": []}

    for item in wardrobe:
        cat  = item["category"]
        t_min = item["temp_min"]
        t_max = item["temp_max"]

        # 체감온도 범위 안에 있는 옷만
        if t_min <= feels_temp <= t_max:
            filtered[cat].append(item)

    return filtered, need_outer

# ── 최종 추천 조합 ──────────────────────────────
def recommend(weather=None):
    """
    날씨 정보 받아서 최종 코디 추천
    나중에 chatbot.py에서 이 함수 호출
    반환:
    {
        "weather": {...},
        "recommendation": {
            "상의": {...},
            "하의": {...},
            "아우터": {...},
        },
        "message": "오늘 8도로 추워요. 니트에 코트 추천드려요!"
    }
    """
    # 날씨 정보 가져오기
    if weather is None:
        print("날씨 정보 가져오는 중...")
        weather = get_weather()
        if not weather:
            return None

    # 옷장 불러오기
    wardrobe = load_wardrobe()
    if not wardrobe:
        print("옷장이 비어있어요! images 폴더에 사진을 넣어주세요.")
        return None

    # 날씨에 맞는 옷 필터링
    filtered, need_outer = filter_by_weather(wardrobe, weather)

    # 추천 결과 구성
    recommendation = {}

    # 상의 추천 (첫 번째 매칭)
    if filtered["상의"]:
        recommendation["상의"] = filtered["상의"][0]
    else:
        recommendation["상의"] = {"item_type": "해당 옷 없음"}

    # 하의 추천
    if filtered["하의"]:
        recommendation["하의"] = filtered["하의"][0]
    else:
        recommendation["하의"] = {"item_type": "해당 옷 없음"}

    # 아우터 추천 (필요한 경우만)
    if need_outer and filtered["아우터"]:
        recommendation["아우터"] = filtered["아우터"][0]
    elif need_outer:
        recommendation["아우터"] = {"item_type": "아우터 없음 (추가 필요)"}
    else:
        recommendation["아우터"] = {"item_type": "아우터 불필요"}

    # 추천 메시지 생성
    category = weather["category"]
    desc     = WEATHER_WARMTH[category]["desc"]
    top      = recommendation["상의"].get("item_type", "")
    bottom   = recommendation["하의"].get("item_type", "")
    outer    = recommendation["아우터"].get("item_type", "")

    message = (
        f"오늘 체감온도 {weather['feels_like']}도로 {category}해요. "
        f"{desc}. "
        f"{top}에 {bottom}"
        f"{' + ' + outer if outer not in ['아우터 불필요', '아우터 없음 (추가 필요)'] else ''} 추천드려요!"
    )

    # 비/눈 추가 메시지
    if weather["is_raining"]:
        message += " 비가 오니까 우산 챙기세요!"
    if weather["is_snowing"]:
        message += " 눈이 오니까 미끄럼 주의하세요!"

    return {
        "weather":        weather,
        "recommendation": recommendation,
        "message":        message,
    }

# ── 메인 실행 ───────────────────────────────────
if __name__ == "__main__":
    result = recommend()

    if result:
        w = result["weather"]
        r = result["recommendation"]

        print(f"\n── 오늘의 날씨 ──")
        print(f"기온     : {w['temperature']}도")
        print(f"체감온도 : {w['feels_like']}도")
        print(f"날씨     : {w['weather_desc']}")
        print(f"카테고리 : {w['category']}")

        print(f"\n── 오늘의 추천 코디 ──")
        print(f"상의  : {r['상의'].get('item_type', '')}")
        print(f"하의  : {r['하의'].get('item_type', '')}")
        print(f"아우터: {r['아우터'].get('item_type', '')}")

        print(f"\n── 추천 메시지 ──")
        print(result["message"])