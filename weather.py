import requests
from dotenv import load_dotenv
import os
from datetime import datetime

load_dotenv()
API_KEY = os.getenv("WEATHER_API_KEY")

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

    response = requests.get(url, params=params)
    data = response.json()

    items = data["response"]["body"]["items"]["item"]

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

    # 체감온도 계산
    if "temperature" in weather_info and "wind_speed" in weather_info:
        t = weather_info["temperature"]
        v = weather_info["wind_speed"]
        feels_like = 13.12 + 0.6215*t - 11.37*(v**0.16) + 0.3965*(v**0.16)*t
        weather_info["feels_like"] = round(feels_like, 1)

    # 강수 여부
    pty = weather_info.get("precipitation", 0)
    weather_info["is_raining"] = pty in [1, 2, 4]
    weather_info["is_snowing"] = pty == 3

    return weather_info

if __name__ == "__main__":
    print("API KEY:", API_KEY)  # 키 확인
    weather = get_weather()
    print(weather)

