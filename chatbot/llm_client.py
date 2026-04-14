import anthropic
import json
import re
from dotenv import load_dotenv
import os

load_dotenv()
CLAUDE_API_KEY = os.getenv("CLAUDE_API_KEY")


def get_outfit_comment(weather_data: dict, style_rec: dict,
                       layering: dict, tpo: str = "일상",
                       user_profile: dict = None,
                       wardrobe_items: list = None,
                       trend_news: list = None) -> str:
    """
    수석 디자이너 코멘트 — 실제 옷장 아이템 기반 맞춤 스타일링

    wardrobe_items: [
        {"category": "상의", "item_type": "crop top", "warmth": 0, "texture": "mixed"},
        {"category": "아우터", "item_type": "denim jacket", "warmth": 2, "texture": "denim"},
        ...
    ]
    """
    client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)

    system_prompt = """당신은 사용자의 실제 옷장을 완벽하게 파악하고 있는 개인 전담 스타일리스트입니다.
파리·밀라노·서울 무대의 30년 경력, 날씨·체형·TPO를 꿰뚫는 현실적 스타일링이 특기입니다.

【핵심 원칙 — 반드시 지킬 것】
- 추천은 반드시 "실제 보유 옷장" 아이템을 이름으로 직접 언급할 것
  예) "네 denim jacket 꺼내" / "crop top에 jeans 조합이면 딱이야"
- 옷장에 없는 아이템이 오늘 날씨에 필요하면 솔직하게 말할 것
  예) "아우터가 denim jacket밖에 없는데, 오늘 저녁 6도까지 떨어지니까 그거라도 꼭 챙겨"
- 보온도 수치를 활용해서 레이어링 판단 근거를 자연스럽게 녹일 것
  예) "denim jacket(보온도 2점)으론 아침은 버티는데 저녁엔 좀 추울 수 있어"
- 옷장이 비어있는 카테고리는 현실적 대안이나 구매 제안으로 마무리할 것

【말투】 반말, 친근하고 전문가다운 어조, 자연스러운 감탄사 허용

【코멘트 구성】
1. 오늘 날씨 한 줄 요약 (체감온도 + 특이사항)
2. 실제 옷장 기반 오늘 코디 세트 추천 (상의→하의→아우터 순, 아이템 이름 직접 언급)
3. 레이어링 — layering_needed=True일 때만 작성. 시간대별(아침/낮/저녁)로 구체적으로.
   layering_needed=False면 이 항목 완전히 생략. 여름·겨울처럼 하루 종일 같은 두께면 언급 불필요.
4. 헤어·신발·악세서리 포인트 (날씨·코디·체형 맞춤)
5. 오늘 전체 무드 한 줄 마무리

【금지】 막연한 조언("편한 옷 입어요") / 옷장에 없는 것만 추천 / 체형 부정적 언급
- 코멘트 내부에서 불릿, 번호목록 사용 최소화. 자연스러운 문장 위주로 작성.

【응답 형식 — 반드시 JSON만 반환. 다른 텍스트 절대 금지】
{
  "comment": "전체 코디 코멘트 (마크다운, 반말)",
  "bubbles": {
    "상의": "캐릭터 옷에 붙는 말풍선. 핵심 한 마디, 15자 이내, 반말 (옷장에 없으면 null)",
    "하의": "위와 동일 (없으면 null)",
    "아우터": "위와 동일 (없으면 null)",
    "원피스": "위와 동일 (없으면 null)"
  }
}"""

    # ── 실제 옷장 섹션 구성 ────────────────────────────────────────
    wardrobe_section = ""
    if wardrobe_items:
        from collections import defaultdict
        by_cat = defaultdict(list)
        for item in wardrobe_items:
            by_cat[item.get("category", "기타")].append(item)

        lines = []
        for cat in ["상의", "하의", "아우터", "원피스"]:
            items = by_cat.get(cat, [])
            if items:
                for it in items:
                    lines.append(
                        f"  {cat}: {it['item_type']} "
                        f"(보온도 {it.get('warmth', 0)}점, 소재: {it.get('texture', '미상')})"
                    )
            else:
                lines.append(f"  {cat}: 없음")
        wardrobe_section = "\n【실제 보유 옷장 — 이것만 활용해서 추천할 것】\n" + "\n".join(lines)
    else:
        wardrobe_section = "\n【실제 보유 옷장】\n  (등록된 옷이 없음 — 일반 추천으로 대체)"

    # ── 레이어링 정보 ──────────────────────────────────────────────
    layering_needed = layering.get("layering_needed", False)
    if layering_needed:
        layering_info = f"""
layering_needed=True
일교차: {layering['temp_diff']:.0f}도
아침 체감: {layering['morning_tmp']}°C → 낮 체감: {layering['afternoon_tmp']}°C
팁: {layering['layering_tip']}"""
    else:
        layering_info = "layering_needed=False (레이어링 항목 생략)"

    # ── 사용자 프로필 ──────────────────────────────────────────────
    profile_info = ""
    if user_profile:
        profile_info = f"""
【착용자 정보】
이름: {user_profile.get('name', '사용자')}
키: {user_profile.get('height', '?')}cm / 몸무게: {user_profile.get('weight', '?')}kg
체형: {user_profile.get('body_type', '보통')} / 성별: {user_profile.get('gender', '미입력')}
선호 스타일: {user_profile.get('style_pref', '캐주얼')}"""

    # ── 트렌드 뉴스 ───────────────────────────────────────────────
    news_section = ""
    if trend_news:
        news_section = "\n【최신 패션 트렌드 뉴스 (자연스럽게 반영)】\n" + "\n".join(trend_news)

    user_prompt = f"""오늘 스타일링 해줘. 반드시 실제 옷장 아이템 이름을 직접 언급하면서 코디를 구성해.

【오늘 날씨】
상태: {style_rec['condition_label']}
아침 체감: {weather_data['morning']['feels_like']}°C / 낮: {weather_data['afternoon']['feels_like']}°C / 저녁: {weather_data['evening']['feels_like']}°C
강수: {style_rec['precip']} / 습도: {style_rec['humidity_level']}
쾌적 포인트: {style_rec['comfort_point']}
{f"습도 노트: {style_rec['humidity_note']}" if style_rec.get('humidity_note') else ''}
레이어링: {layering_info}
{wardrobe_section}

【날씨 기준 이상적 아이템 (참고용)】
권장: {', '.join(style_rec['recommended_items'])}
비권장: {', '.join(style_rec['avoid_items'])}

【오늘 용도】 {tpo}
{profile_info}
{news_section}"""

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1300,
        messages=[{"role": "user", "content": user_prompt}],
        system=system_prompt
    )

    raw = message.content[0].text.strip()
    try:
        match = re.search(r'\{.*\}', raw, re.DOTALL)
        if match:
            data = json.loads(match.group())
            return {
                "comment": data.get("comment", raw),
                "bubbles": data.get("bubbles", {}),
            }
    except Exception:
        pass
    return {"comment": raw, "bubbles": {}}


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
- 칭찬과 개선점을 균형 있게
- 응답에 **, *, --, —, _, 번호목록, 불릿 등 특수기호 절대 사용 금지. 순수 한글 문장으로만 작성."""

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
        model="claude-sonnet-4-6",
        max_tokens=500,
        messages=messages,
        system=system_prompt
    )

    return message.content[0].text
