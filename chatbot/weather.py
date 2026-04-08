import requests
from dotenv import load_dotenv
import os
from datetime import datetime

load_dotenv()
API_KEY = os.getenv("KMA_API_KEY")


def classify_temp(feels_like: float) -> tuple[str, str]:
    """
    체감온도 → (카테고리, 날씨 설명) 반환
    recommend.py의 WEATHER_WARMTH 키와 일치해야 함
    """
    if feels_like <= -5:
        return "한파",     "한파 수준으로 매우 춥습니다"
    elif feels_like <= 2:
        return "매우추움", "매우 추운 날씨입니다"
    elif feels_like <= 8:
        return "추움",     "추운 날씨입니다"
    elif feels_like <= 13:
        return "쌀쌀",     "쌀쌀한 날씨입니다"
    elif feels_like <= 18:
        return "선선",     "선선한 날씨입니다"
    elif feels_like <= 23:
        return "포근",     "포근한 날씨입니다"
    elif feels_like <= 28:
        return "더움",     "더운 날씨입니다"
    else:
        return "매우더움", "매우 더운 날씨입니다"


def get_weather(nx=60, ny=127):
    """
    nx, ny : 기상청 격자 좌표
    서울 기본값 nx=60, ny=127
    """
    now = datetime.now()
    base_date = now.strftime("%Y%m%d")
    base_time = "0500"  # 오전 5시 예보

    url = "https://apihub.kma.go.kr/api/typ02/openApi/VilageFcstInfoService_2.0/getVilageFcst"
    params = {
        "serviceKey": API_KEY,
        "pageNo": 1,
        "numOfRows": 100,
        "dataType": "JSON",
        "base_date": base_date,
        "base_time": base_time,
        "nx": nx,
        "ny": ny
    }

    try:
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        items = data["response"]["body"]["items"]["item"]
    except Exception as e:
        print(f"날씨 API 오류: {e}")
        return None

    weather_info = {}
    for item in items:
        category = item["category"]
        value = item["fcstValue"]

        if category == "TMP":    # 기온
            weather_info["temperature"] = float(value)
        elif category == "PTY":  # 강수형태
            weather_info["precipitation"] = int(value)
        elif category == "WSD":  # 풍속
            weather_info["wind_speed"] = float(value)

    # 체감온도 계산 (공식 체감온도 공식)
    t = weather_info.get("temperature", 15)
    v = weather_info.get("wind_speed", 0)
    if v > 0:
        feels_like = 13.12 + 0.6215 * t - 11.37 * (v ** 0.16) + 0.3965 * (v ** 0.16) * t
    else:
        feels_like = t
    weather_info["feels_like"] = round(feels_like, 1)

    # 강수 여부
    pty = weather_info.get("precipitation", 0)
    weather_info["is_raining"] = pty in [1, 2, 4]
    weather_info["is_snowing"] = pty == 3

    # 날씨 카테고리 + 설명 (recommend.py 연동용)
    category, weather_desc = classify_temp(weather_info["feels_like"])
    weather_info["category"] = category
    weather_info["weather_desc"] = weather_desc

    return weather_info


if __name__ == "__main__":
    print("API KEY:", API_KEY)
    weather = get_weather()
    print(weather)
