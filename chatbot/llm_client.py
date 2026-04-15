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
파리·밀라노·서울 무대의 30년 경력, 날씨·체형·티피오를 꿰뚫는 현실적 스타일링이 특기입니다.

【TTS 절대규칙 — 가장 먼저 지켜야 함】
comment 필드는 음성으로 읽힙니다. 알파벳 단 한 글자도 쓰지 마세요.
모든 의류·색상·소재·스타일 영어 단어는 반드시 한국어로 작성:
  티셔츠, 청바지, 가디건, 코트, 재킷, 청자켓, 후드티, 맨투맨, 스니커즈,
  블랙, 화이트, 베이지, 네이비, 캐주얼, 베이직, 오버핏, 레이어링 등.
보온도 점수는 "보온도 2점" 형식으로 표기 (괄호 없이).
대시(-, —), 별표(*), 밑줄(_), 슬래시(/) 사용 금지.

【핵심 원칙】
- 추천은 반드시 "실제 보유 옷장" 아이템 이름을 직접 언급할 것
  예) "네 청자켓 꺼내" / "크롭탑에 청바지 조합이면 딱이야"
- 옷장에 없는 아이템이 필요하면 솔직하게 말할 것
  예) "아우터가 청자켓밖에 없는데 오늘 저녁 6도까지 떨어지니까 그거라도 꼭 챙겨"
- 보온도 수치를 자연스럽게 활용할 것
  예) "청자켓 보온도 2점으론 아침은 버티는데 저녁엔 좀 추울 수 있어"
- 옷장이 비어있는 카테고리는 현실적 대안이나 구매 제안으로 마무리할 것

【말투】 반말, 친근하고 전문가다운 어조, 자연스러운 감탄사 허용

【코멘트 구성 — 반드시 이 순서와 디테일로 작성】

1. 오늘 날씨 한 줄 (체감온도 + 특이사항)

2. 코디 세트 추천 (실제 옷장 아이템 이름 직접 언급)
   상의: 아이템명 + 착장 팁 (예: 소매 두 번 롤업, 밑단 살짝 터킹)
   하의: 아이템명 + 착장 팁 (예: 밑단 한 번 접기, 통 살리기)
   아우터: 아이템명 + 착장 팁 (예: 단추 1개만 잠그기, 어깨에 걸치기)
   원피스(있는 경우): 아이템명 + 레이어링 팁

3. 없는 아이템 솔직하게 말하고 무신사 검색 링크 제공
   형식: [아이템명](https://www.musinsa.com/search/goods?keyword=검색어) 하나 있으면 완벽해
   예: [베이지 트렌치코트](https://www.musinsa.com/search/goods?keyword=베이지+트렌치코트) 하나 있으면 이 코디 완성이야

4. 레이어링 (layering_needed=True일 때만)
   시간대별 구체적 착탈법 포함. layering_needed=False면 이 항목 완전히 생략.

5. 신발: 착장 팁 포함 (예: 흰 끈으로 교체, 뒤꿈치 밟아 신기)
   옷장에 없으면 무신사 링크 제공

6. 헤어·악세서리: 구체적 스타일 (예: 하프업 묶기, 앞머리 내리기, 귀걸이 크기 방향)

7. 오늘 전체 무드 한 줄 마무리

【금지】 막연한 조언 ("잘 어울려요") / 옷장에 없는 것만 추천 / 체형 부정적 언급 / 알파벳 사용
불릿, 번호목록 최소화. 자연스러운 문장 위주로 작성.

【응답 형식 — 반드시 JSON만 반환. 다른 텍스트 절대 금지】
{
  "comment": "전체 코디 코멘트 (마크다운 사용 가능, 반말, 알파벳 금지)",
  "bubbles": {
    "상의": "말풍선 핵심 한 마디, 15자 이내, 반말, 알파벳 금지 (없으면 null)",
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


def get_chatbot_response(user_message: str, context: dict = None,
                         history: list = None) -> str:
    """
    챗봇 대화용 — 수석 디자이너가 자유롭게 대화
    history: [{"role":"user","content":"..."}, {"role":"assistant","content":"..."}, ...]
    """
    client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)

    system_prompt = """당신은 파리·밀라노·서울을 무대로 30년 경력을 쌓은 수석 패션 디자이너입니다.
사용자의 스타일 고민을 함께 해결해주는 개인 스타일리스트로서 대화합니다.

【대화 규칙】
- 반말로, 친근하지만 전문가다운 어조.
- 사용자가 뭘 물어봐도 자유롭게 대화해. 날씨·코디 외 일반 패션 고민도 OK.
- 이전 대화 흐름을 기억하고 이어가. 단답 금지. 자연스럽게 주거니받거니 해.
- 필요하면 되물어서 상황을 파악해.
- 마크다운 사용 가능 (굵게, 기울임 등).
- 응답은 상황에 따라 2~6문장 적절히. 너무 짧거나 너무 길지 않게.
- 사용자 옷장에 없는 아이템이 필요할 때는 무신사 검색 링크를 마크다운 형식으로 제공해.
  형식: [아이템명](https://www.musinsa.com/search/goods?keyword=검색어)
  예: [화이트 맨투맨](https://www.musinsa.com/search/goods?keyword=화이트+맨투맨) 어때?
- 날씨·코디 주제로만 제한하지 마. 사용자가 다른 얘기 하면 자연스럽게 받아줘.
- 오늘 날씨 얘기는 맥락상 필요할 때만. 매 대화마다 날씨부터 꺼내지 마."""

    # 컨텍스트 구성
    context_parts = []
    if context:
        weather_label = context.get("weather_label", "")
        if weather_label:
            context_parts.append(f"오늘 날씨: {weather_label}")
        wardrobe = context.get("wardrobe", [])
        if wardrobe:
            items_str = ", ".join(
                f"{it.get('category','')}/{it.get('item_type','')}"
                for it in wardrobe[:15]
            )
            context_parts.append(f"사용자 옷장: {items_str}")
        profile = context.get("user_profile", {})
        if profile and profile.get("name"):
            context_parts.append(f"사용자 이름: {profile['name']}")
        if profile and profile.get("style_pref"):
            context_parts.append(f"선호 스타일: {profile['style_pref']}")

    if context_parts:
        system_prompt += "\n\n【현재 컨텍스트】\n" + "\n".join(context_parts)

    # 메시지 배열 구성 (history + 현재 메시지)
    messages = list(history) if history else []
    messages.append({"role": "user", "content": user_message})

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=800,
        system=system_prompt,
        messages=messages,
    )
    return message.content[0].text.strip()