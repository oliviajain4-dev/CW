#pip install anthropic requests python-dotenv
import requests
from datetime import datetime, timedelta
from dotenv import load_dotenv
import os

load_dotenv()
KMA_API_KEY = os.getenv("KMA_API_KEY")


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

    res = requests.get(url, params=params)
    items = res.json()["response"]["body"]["items"]["item"]

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

    return result