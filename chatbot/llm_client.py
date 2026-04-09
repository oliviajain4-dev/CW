import anthropic
from dotenv import load_dotenv
import os

load_dotenv()
CLAUDE_API_KEY = os.getenv("CLAUDE_API_KEY")


def get_outfit_comment(weather_data: dict, style_rec: dict,
                       layering: dict, tpo: str = "일상",
                       user_profile: dict = None) -> str:
    """
    30년 경력 수석 디자이너가 머리부터 신발까지 전체 스타일링 코멘트 생성

    user_profile: {
        "name": str,
        "height": int,       # cm
        "weight": int,       # kg
        "body_type": str,    # 슬림/보통/근육형/통통
        "style_pref": str,   # 캐주얼/스트릿/포멀/미니멀/페미닌
        "gender": str,       # 여성/남성
    }
    """
    client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)

    system_prompt = """당신은 파리·밀라노·서울을 무대로 30년 경력을 쌓은 수석 패션 디자이너입니다.
수많은 셀럽과 일반인의 스타일링을 담당해왔으며, 날씨·체형·TPO를 고려한 섬세하고 현실적인 스타일링으로 유명합니다.

【말투 규칙】
- 반말로, 친근하지만 전문가다운 어조
- 감탄사(오, 딱이야, 완벽해)를 자연스럽게 섞기
- 너무 길지 않되, 디테일은 확실히 짚어줄 것

【코멘트 구성 — 반드시 이 순서로】
1. 오늘 날씨 한 줄 요약 (체감온도·날씨 상황 포함)
2. 헤어스타일 추천 (날씨·TPO·체형에 맞게 구체적으로)
3. 상의 스타일링 포인트 (색상 톤, 핏, 소재 팁)
4. 하의 스타일링 포인트 (상의와의 밸런스, 핏)
5. 아우터 착용법 (필요할 때만, 레이어링 팁 포함)
6. 신발 추천 (날씨·코디·체형에 최적화된 구체적 제안)
7. 악세서리·가방 1~2가지 포인트 제안
8. 오늘의 전체 무드 한 줄 마무리

【금지 사항】
- 뻔한 "날씨가 춥네요" 식의 평범한 멘트 금지
- 막연한 조언("편한 옷 입어요") 금지
- 체형이나 외모에 대한 부정적 언급 절대 금지"""

    # 레이어링 정보
    layering_info = ""
    if layering.get("layering_needed"):
        layering_info = f"""
일교차: {layering['temp_diff']:.0f}도 (레이어링 필수)
아침 체감: {layering['morning_tmp']}°C → 낮 체감: {layering['afternoon_tmp']}°C
레이어링 팁: {layering['layering_tip']}"""

    # 사용자 프로필 정보
    profile_info = ""
    if user_profile:
        profile_info = f"""
【착용자 정보】
이름: {user_profile.get('name', '사용자')}
키: {user_profile.get('height', '?')}cm / 몸무게: {user_profile.get('weight', '?')}kg
체형: {user_profile.get('body_type', '보통')}
선호 스타일: {user_profile.get('style_pref', '캐주얼')}
성별: {user_profile.get('gender', '미입력')}"""

    user_prompt = f"""오늘의 날씨와 코디 정보예요. 수석 디자이너로서 머리부터 신발까지 완전한 스타일링을 해줘.

【날씨 정보】
날씨 상태: {style_rec['condition_label']}
아침 체감온도: {weather_data['morning']['feels_like']}°C
낮 체감온도: {weather_data['afternoon']['feels_like']}°C
저녁 체감온도: {weather_data['evening']['feels_like']}°C
강수: {style_rec['precip']} / 습도: {style_rec['humidity_level']}
{layering_info}

【추천 아이템 (내 옷장 기반)】
추천 아이템: {', '.join(style_rec['recommended_items'])}
피할 아이템: {', '.join(style_rec['avoid_items'])}
쾌적 포인트: {style_rec['comfort_point']}
{f"습도 노트: {style_rec['humidity_note']}" if style_rec.get('humidity_note') else ''}

【오늘 용도 (TPO)】
{tpo}
{profile_info}

위 정보를 바탕으로 오늘 완전한 코디 스타일링을 해줘."""

    message = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=800,
        messages=[{"role": "user", "content": user_prompt}],
        system=system_prompt
    )

    return message.content[0].text


def get_chatbot_response(user_message: str, context: dict = None) -> str:
    """
    챗봇 대화용 — 사용자 질문에 수석 디자이너가 답변
    context: 현재 날씨/코디 추천 데이터
    """
    client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)

    system_prompt = """당신은 파리·밀라노·서울을 무대로 30년 경력을 쌓은 수석 패션 디자이너입니다.
사용자의 스타일 고민을 함께 해결해주는 개인 스타일리스트로서 대화합니다.

【대화 규칙】
- 반말로, 친근하지만 전문가다운 어조
- 구체적이고 실용적인 조언
- 필요하면 추가 질문으로 정보 파악
- 칭찬과 개선점을 균형 있게"""

    context_info = ""
    if context:
        wardrobe_info = ""
        wardrobe = context.get('wardrobe', [])
        if wardrobe:
            lines = []
            for item in wardrobe:
                lines.append(f"  - {item.get('category','')}: {item.get('item_type','')} (보온도 {item.get('warmth',0)}점, 소재 {item.get('texture','')})")
            wardrobe_info = "\n【내 옷장 보유 아이템】\n" + "\n".join(lines)

        context_info = f"""
【현재 날씨·코디 컨텍스트】
날씨: {context.get('weather_label', '')}
추천 아이템: {context.get('recommended_items', '')}
TPO: {context.get('tpo', '일상')}
{wardrobe_info}

위 옷장 아이템을 기반으로 실제 보유한 옷을 활용한 구체적인 코디를 추천해줘.
"""

    messages = [{"role": "user", "content": f"{context_info}\n{user_message}"}]

    message = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=500,
        messages=messages,
        system=system_prompt
    )

    return message.content[0].text
