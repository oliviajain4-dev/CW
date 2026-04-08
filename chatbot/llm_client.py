import anthropic
from dotenv import load_dotenv
import os

load_dotenv()
CLAUDE_API_KEY = os.getenv("CLAUDE_API_KEY")


def get_outfit_comment(weather_data: dict, style_rec: dict,
                       layering: dict, tpo: str = "일상") -> str:
    client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)

    system_prompt = """당신은 친근한 스타일 어시스턴트예요.
사용자의 날씨 데이터와 오늘의 코디 추천을 받아서,
자연스럽고 실용적인 코디 코멘트를 2~3문장으로 말해주세요.

규칙:
- 반말로 친근하게 말해요
- 날씨 상황을 먼저 한 문장으로 요약해요
- 핵심 아이템을 구체적으로 언급해요
- 쾌적함 포인트를 자연스럽게 녹여요
- 너무 길지 않게, 핵심만요"""

    layering_info = ""
    if layering["layering_needed"]:
        layering_info = f"""
레이어링 필요: 예 (일교차 {layering['temp_diff']:.0f}도)
아침 체감온도: {layering['morning_tmp']}°C
낮 체감온도: {layering['afternoon_tmp']}°C
레이어링 팁: {layering['layering_tip']}"""

    user_prompt = f"""오늘 날씨와 코디 정보예요.

날씨 요약: {style_rec['condition_label']}
아침 체감온도: {weather_data['morning']['feels_like']}°C
낮 체감온도: {weather_data['afternoon']['feels_like']}°C
강수 여부: {style_rec['precip']}
쾌적 포인트: {style_rec['comfort_point']}
{layering_info}
추천 아이템: {', '.join(style_rec['recommended_items'])}
피할 아이템: {', '.join(style_rec['avoid_items'])}
오늘 용도: {tpo}
습도 메모: {style_rec['humidity_note'] if style_rec['humidity_note'] else '없음'}

위 정보를 바탕으로 오늘 코디 코멘트를 해줘."""

    message = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=300,
        messages=[{"role": "user", "content": user_prompt}],
        system=system_prompt
    )

    return message.content[0].text