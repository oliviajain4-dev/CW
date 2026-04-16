#pip install anthropic requests python-dotenv
import requests
from datetime import datetime, timedelta
from dotenv import load_dotenv
import os

load_dotenv()
KMA_API_KEY = os.getenv("KMA_API_KEY")

# ── 날씨 캐시 ────────────────────────────────────────────────────
# 기상청 예보는 3시간마다만 갱신 → base_date+base_time이 바뀌면 자동 무효화
# key: (nx, ny, base_date, base_time)
_weather_cache: dict = {}


def get_base_time(now: datetime) -> tuple[str, str]:
    base_times = [2, 5, 8, 11, 14, 17, 20, 23]
    hour = now.hour
    hour_adjusted = hour - 1 if now.minute < 10 else hour

    base_hour = max([t for t in base_times if t <= hour_adjusted], default=23)

    if hour_adjusted < 2:
        base_date = (now - timedelta(days=1)).strftime("%Y%m%d")
        base_hour = 23
    else:
        base_date = now.strftime("%Y%m%d")

    return base_date, f"{base_hour:02d}00"


def get_weather(nx: int, ny: int) -> dict:
    now = datetime.now()
    base_date, base_time = get_base_time(now)

    # 캐시 히트: 같은 예보 회차 데이터가 있으면 즉시 반환
    cache_key = (nx, ny, base_date, base_time)
    if cache_key in _weather_cache:
        return _weather_cache[cache_key]

    url = "http://apis.data.go.kr/1360000/VilageFcstInfoService_2.0/getVilageFcst"
    params = {
        "serviceKey": KMA_API_KEY,
        "numOfRows": 300,
        "pageNo": 1,
        "dataType": "JSON",
        "base_date": base_date,
        "base_time": base_time,
        "nx": nx,
        "ny": ny,
    }

    try:
        res = requests.get(url, params=params, timeout=8)
        res.raise_for_status()
        items = res.json()["response"]["body"]["items"]["item"]
    except Exception as e:
        # KMA API 장애 시 캐시된 직전 데이터를 우선 사용
        for key in reversed(list(_weather_cache)):
            if key[0] == nx and key[1] == ny:
                print(f"[weather] KMA API 오류 ({e}) → 직전 캐시 사용")
                return _weather_cache[key]
        # 캐시도 없으면 기본값 반환
        print(f"[weather] KMA API 오류 ({e}) → 기본값 사용")
        return _fallback_weather()

    forecast = {}
    for item in items:
        t = item["fcstTime"]
        if t not in forecast:
            forecast[t] = {}
        forecast[t][item["category"]] = item["fcstValue"]

    times = sorted(forecast.keys())

    def extract(time_str):
        data = forecast.get(time_str, {})
        return {
            "tmp":      float(data.get("TMP", 15)),
            "reh":      float(data.get("REH", 50)),
            "sky":      int(data.get("SKY", 1)),
            "pty":      int(data.get("PTY", 0)),
            "wsd":      float(data.get("WSD", 0)),
        }

    target_times = {"morning": "0800", "afternoon": "1400", "evening": "2000"}
    result = {}
    for label, t in target_times.items():
        if t in forecast:
            result[label] = extract(t)
        else:
            closest = min(times, key=lambda x: abs(int(x) - int(t)))
            result[label] = extract(closest)

    all_temps = [result[t]["tmp"] for t in result]
    result["temp_range_diff"] = max(all_temps) - min(all_temps)
    result["min_tmp"] = min(all_temps)
    result["max_tmp"] = max(all_temps)

    for t in ["morning", "afternoon", "evening"]:
        wsd = result[t]["wsd"]
        tmp = result[t]["tmp"]
        result[t]["feels_like"] = round(tmp - (wsd * 0.7), 1)

    # 캐시 저장 (같은 예보 회차 내 이후 요청은 네트워크 없이 즉시 반환)
    _weather_cache[cache_key] = result
    return result


def _fallback_weather() -> dict:
    """KMA API 완전 장애 시 사용할 기본값 (서비스 중단 방지)"""
    default_slot = {"tmp": 15.0, "reh": 60.0, "sky": 1, "pty": 0, "wsd": 1.0, "feels_like": 14.3}
    return {
        "morning":        default_slot.copy(),
        "afternoon":      {**default_slot, "tmp": 18.0, "feels_like": 17.3},
        "evening":        {**default_slot, "tmp": 13.0, "feels_like": 12.3},
        "temp_range_diff": 5.0,
        "min_tmp":        13.0,
        "max_tmp":        18.0,
    }