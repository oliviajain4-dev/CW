from weather.weather_client import get_weather
from weather.weather_style_mapper import get_style_recommendation, get_layering_recommendation
from weather.llm_client import get_outfit_comment


def run(nx: int = 62, ny: int = 123, sensitivity: int = 3, tpo: str = "학원"):
    """
    nx, ny : 기상청 격자 좌표 (성남 기준 62, 123)
    sensitivity : 1=추위많이탐 / 3=보통 / 5=더위많이탐
    tpo : 오늘 용도
    """
    print("날씨 불러오는 중...")
    weather = get_weather(nx, ny)

    print(f"아침 체감 {weather['morning']['feels_like']}°C / "
          f"낮 체감 {weather['afternoon']['feels_like']}°C / "
          f"저녁 체감 {weather['evening']['feels_like']}°C")
    print(f"일교차 {weather['temp_range_diff']:.1f}도")

    style_rec = get_style_recommendation(
        weather["morning"]["feels_like"],
        weather["morning"]["reh"],
        weather["morning"]["sky"],
        weather["morning"]["pty"],
        sensitivity
    )

    layering = get_layering_recommendation(weather, sensitivity)

    print(f"\n날씨: {style_rec['condition_label']}")
    print(f"추천 아이템: {', '.join(style_rec['recommended_items'])}")
    if style_rec["humidity_note"]:
        print(f"습도: {style_rec['humidity_note']}")
    if layering["layering_needed"]:
        print(f"\n⚠️  {layering['layering_tip']}")

    print("\nAI 코멘트 생성 중...")
    comment = get_outfit_comment(weather, style_rec, layering, tpo)
    print(f"\n💬 오늘의 코디:\n{comment}")


if __name__ == "__main__":
    run()