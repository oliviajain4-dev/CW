"""
weather.py — 기상청 API 허브 연동
- 단기예보 기온/날씨 파싱
- 온도 구간별 카테고리 분류
- 체감온도 계산
"""

import requests
import os
from datetime import datetime, timedelta
from dotenv import load_dotenv

load_dotenv("weather_api_key.env")
API_KEY = os.getenv("WEATHER_API_KEY")

# ── 서울 기본 격자 좌표 ─────────────────────────
DEFAULT_NX = 60
DEFAULT_NY = 127

# ── 온도 구간 분류 ──────────────────────────────
def classify_temp(temperature):
    """
    기온 → 날씨 카테고리 분류
    recommend.py에서 이 카테고리로 옷 추천
    """
    if temperature <= 4:
        return "한파"       # 패딩, 두꺼운 코트
    elif temperature <= 8:
        return "매우추움"   # 코트, 두꺼운 니트
    elif temperature <= 11:
        return "추움"       # 자켓, 니트
    elif temperature <= 16:
        return "쌀쌀"       # 가디건, 청자켓
    elif temperature <= 19:
        return "선선"       # 얇은 자켓, 긴팔
    elif temperature <= 22:
        return "포근"       # 긴팔, 얇은 가디건
    elif temperature <= 27:
        return "더움"       # 반팔
    else:
        return "매우더움"   # 민소매, 반바지

# ── 체감온도 계산 ───────────────────────────────
def feels_like(temp, wind_speed):
    """
    체감온도 = 기온 + 풍속 보정
    """
    if wind_speed < 1:
        return temp
    fl = 13.12 + 0.6215 * temp - 11.37 * (wind_speed ** 0.16) + 0.3965 * (wind_speed ** 0.16) * temp
    return round(fl, 1)

# ── base_time 계산 ──────────────────────────────
def get_base_time():
    """
    기상청은 정시 발표 아니라 특정 시간대 발표
    가장 최근 발표 시간 반환
    """
    now = datetime.now()
    base_times = ["0200", "0500", "0800", "1100", "1400", "1700", "2000", "2300"]
    base_hours = [2, 5, 8, 11, 14, 17, 20, 23]

    current_hour = now.hour
    selected = "2300"
    selected_date = now

    for i, h in enumerate(base_hours):
        if current_hour >= h + 1:
            selected = base_times[i]
        elif current_hour < 3:
            selected = "2300"
            selected_date = now - timedelta(days=1)

    return selected_date.strftime("%Y%m%d"), selected

# ── 기상청 API 호출 ─────────────────────────────
def get_weather(nx=DEFAULT_NX, ny=DEFAULT_NY):
    """
    기상청 API 허브 단기예보 호출
    반환:
    {
        "temperature": 8.0,       기온
        "feels_like": 5.2,        체감온도
        "category": "추움",       온도 구간
        "is_raining": False,      강수 여부
        "is_snowing": False,      강설 여부
        "wind_speed": 2.3,        풍속
        "humidity": 60,           습도
        "weather_desc": "맑음"    날씨 설명
    }
    """
    base_date, base_time = get_base_time()

    url = "http://apis.data.go.kr/1360000/VilageFcstInfoService_2.0/getVilageFcst"
    params = {
        "serviceKey":    API_KEY,
        "pageNo":     1,
        "numOfRows":  200,
        "dataType":   "JSON",
        "base_date":  base_date,
        "base_time":  base_time,
        "nx":         nx,
        "ny":         ny,
    }

    try:
        response = requests.get(url, params=params, timeout=10)
        print(f"API 상태코드: {response.status_code}")

        if response.status_code != 200:
            print(f"API 오류: {response.text[:200]}")
            return None

        data = response.json()
        items = data["response"]["body"]["items"]["item"]

    except Exception as e:
        print(f"API 호출 실패: {e}")
        return None

    # 가장 가까운 예보 시간 데이터 파싱
    weather_info = {
        "temperature": None,
        "wind_speed":  0,
        "humidity":    0,
        "precipitation": 0,
    }

    now_str = datetime.now().strftime("%H%M")
    target_time = None

    for item in items:
        fcst_time = item.get("fcstTime", "")
        if fcst_time >= now_str and target_time is None:
            target_time = fcst_time

    for item in items:
        if item.get("fcstTime") != target_time:
            continue
        cat = item.get("category")
        val = item.get("fcstValue")

        if cat == "TMP":   weather_info["temperature"]   = float(val)
        elif cat == "WSD": weather_info["wind_speed"]    = float(val)
        elif cat == "REH": weather_info["humidity"]      = int(val)
        elif cat == "PTY": weather_info["precipitation"] = int(val)

    if weather_info["temperature"] is None:
        print("기온 데이터 없음")
        return None

    temp = weather_info["temperature"]
    wind = weather_info["wind_speed"]
    pty  = weather_info["precipitation"]

    # 강수 형태 해석
    # 0:없음 1:비 2:비/눈 3:눈 4:소나기
    is_raining = pty in [1, 2, 4]
    is_snowing = pty in [2, 3]

    weather_desc = {
        0: "맑음", 1: "비", 2: "비/눈", 3: "눈", 4: "소나기"
    }.get(pty, "맑음")

    result = {
        "temperature":  temp,
        "feels_like":   feels_like(temp, wind),
        "category":     classify_temp(feels_like(temp, wind)),
        "is_raining":   is_raining,
        "is_snowing":   is_snowing,
        "wind_speed":   wind,
        "humidity":     weather_info["humidity"],
        "weather_desc": weather_desc,
    }

    return result

# ── 메인 실행 ───────────────────────────────────
if __name__ == "__main__":
    print("날씨 정보 가져오는 중...")
    weather = get_weather()

    if weather:
        print(f"\n── 현재 날씨 ──")
        print(f"기온      : {weather['temperature']}도")
        print(f"체감온도  : {weather['feels_like']}도")
        print(f"날씨      : {weather['weather_desc']}")
        print(f"풍속      : {weather['wind_speed']}m/s")
        print(f"습도      : {weather['humidity']}%")
        print(f"비        : {weather['is_raining']}")
        print(f"눈        : {weather['is_snowing']}")
        print(f"\n── 온도 카테고리 ──")
        print(f"지금은 '{weather['category']}' → 이에 맞는 옷 추천 예정")
    else:
        print("날씨 정보를 가져오지 못했어요.")
        print("API 키와 네트워크를 확인해주세요.")