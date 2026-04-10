"""
shopping.py — 쇼핑 추천 모듈
1. AI가 옷장 분석 → 우선순위별 필요 아이템 JSON 추출
2. 네이버 쇼핑 API로 실제 상품 이미지 + 링크 조회
3. 네이버 API 키 없으면 무신사 검색 URL로 fallback
"""

import os
import re
import json
import urllib.parse
import requests
import anthropic
from dotenv import load_dotenv
from collections import defaultdict

load_dotenv()
CLAUDE_API_KEY       = os.getenv("CLAUDE_API_KEY")
NAVER_CLIENT_ID      = os.getenv("NAVER_CLIENT_ID")
NAVER_CLIENT_SECRET  = os.getenv("NAVER_CLIENT_SECRET")

_TYPE_LABEL = {"missing": "없는 아이템", "upgrade": "업그레이드", "trend": "트렌드"}


# ── 네이버 뉴스 API — 최신 패션 트렌드 ───────────────────────────
def get_fashion_news(style_pref: str = "캐주얼") -> list:
    """
    반환: ["- 제목: 설명 요약...", ...]
    API 키 없거나 실패 시 빈 리스트
    """
    if not NAVER_CLIENT_ID or not NAVER_CLIENT_SECRET:
        return []
    try:
        res = requests.get(
            "https://openapi.naver.com/v1/search/news.json",
            headers={
                "X-Naver-Client-Id":     NAVER_CLIENT_ID,
                "X-Naver-Client-Secret": NAVER_CLIENT_SECRET,
            },
            params={"query": f"패션 트렌드 {style_pref}", "display": 3, "sort": "date"},
            timeout=5,
        )
        items = res.json().get("items", [])
        news = []
        for item in items:
            title = re.sub(r"<[^>]+>", "", item.get("title", ""))
            desc  = re.sub(r"<[^>]+>", "", item.get("description", ""))
            if title:
                news.append(f"- {title}" + (f": {desc[:80]}" if desc else ""))
        return news
    except Exception:
        return []


# ── AI: 옷장 분석 → 쇼핑 필요 목록 ───────────────────────────────
def get_shopping_needs(wardrobe_items: list, style_rec: dict,
                       user_profile: dict = None,
                       trend_news: list = None) -> list:
    """
    반환 예시:
    [
      {"priority": 1, "reason": "아우터가 denim jacket밖에 없어 영하 대비 불가",
       "search_query": "여성 캐주얼 롱코트", "category": "아우터", "type": "missing"},
      ...
    ]
    """
    client = anthropic.Anthropic(api_key=CLAUDE_API_KEY)

    # 옷장 정리
    by_cat = defaultdict(list)
    for item in (wardrobe_items or []):
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
    wardrobe_str = "\n".join(lines)

    style_pref = (user_profile or {}).get("style_pref", "캐주얼")
    gender     = (user_profile or {}).get("gender", "여성")
    temp_range = style_rec.get("temp_range", "mild")
    condition  = style_rec.get("condition_label", "")

    # f-string 안에서 백슬래시 불가 → 변수로 먼저 조합
    news_str = ""
    if trend_news:
        news_str = "【최신 트렌드 뉴스 참고】\n" + "\n".join(trend_news)

    prompt = f"""이 사람의 옷장을 분석해서 지금 당장 사야 할 옷을 우선순위 1~3위로 알려줘.

【현재 옷장】
{wardrobe_str}

【사용자 정보】
성별: {gender} / 선호 스타일: {style_pref}

【날씨 맥락】
현재 날씨: {temp_range} ({condition})

판단 기준 (우선순위 순):
1. 없는 카테고리로 인한 치명적 공백 (예: 아우터 없음)
2. 현재 날씨 대비 보온도 부족
3. 스타일 업그레이드 또는 요즘 유행 반영 제안
{news_str}

응답은 반드시 아래 JSON만. 설명 없이:
{{
  "shopping_needs": [
    {{
      "priority": 1,
      "reason": "이유 (반말, 한 문장, 구체적으로 — 예: 아우터가 denim jacket밖에 없어서 추운 날 버티기 힘들어)",
      "search_query": "네이버 쇼핑 검색어 (한국어, 성별+스타일+아이템명 포함 — 예: 여성 캐주얼 롱코트)",
      "category": "상의|하의|아우터|원피스|신발|악세서리",
      "type": "missing|upgrade|trend"
    }}
  ]
}}"""

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=500,
        messages=[{"role": "user", "content": prompt}]
    )

    raw = message.content[0].text.strip()

    # JSON 블록 추출 (마크다운 코드블록 대응)
    match = re.search(r"\{.*\}", raw, re.DOTALL)
    if not match:
        return []
    data = json.loads(match.group())
    return data.get("shopping_needs", [])


# ── 네이버 쇼핑 API ──────────────────────────────────────────────
def search_naver_shopping(query: str, display: int = 3) -> list:
    """
    반환: [{"title", "image", "link", "price", "mall"}]
    API 키 없거나 실패 시 빈 리스트 반환 → fallback으로 처리
    """
    if not NAVER_CLIENT_ID or not NAVER_CLIENT_SECRET:
        return []

    try:
        res = requests.get(
            "https://openapi.naver.com/v1/search/shop.json",
            headers={
                "X-Naver-Client-Id":     NAVER_CLIENT_ID,
                "X-Naver-Client-Secret": NAVER_CLIENT_SECRET,
            },
            params={"query": query, "display": display, "sort": "sim"},
            timeout=5,
        )
        items = res.json().get("items", [])
        result = []
        for item in items:
            title = re.sub(r"<[^>]+>", "", item.get("title", ""))
            price = item.get("lprice", "0")
            result.append({
                "title": title,
                "image": item.get("image", ""),
                "link":  item.get("link", ""),
                "price": f"{int(price):,}원" if price else "",
                "mall":  item.get("mallName", ""),
            })
        return result
    except Exception:
        return []


# ── 쇼핑 카드 조합 ────────────────────────────────────────────────
def get_shopping_cards(wardrobe_items: list, style_rec: dict,
                       user_profile: dict = None,
                       trend_news: list = None) -> list:
    """
    최종 카드 리스트 반환.
    네이버 API 있으면 실제 상품 이미지+링크,
    없으면 무신사 검색 URL 카드로 fallback.

    반환:
    [
      {
        "priority": 1,
        "reason": "...",
        "category": "아우터",
        "type": "missing",
        "type_label": "없는 아이템",
        "products": [...],        # 네이버 상품 (없으면 [])
        "search_url": "...",      # 무신사 검색 URL (항상 포함)
        "search_query": "...",
      }
    ]
    """
    needs = get_shopping_needs(wardrobe_items, style_rec, user_profile, trend_news)

    cards = []
    for need in needs[:3]:
        query    = need.get("search_query", "")
        products = search_naver_shopping(query, display=3)
        musinsa_url = (
            "https://www.musinsa.com/search/goods?keyword="
            + urllib.parse.quote(query)
        )
        cards.append({
            "priority":    need.get("priority", len(cards) + 1),
            "reason":      need.get("reason", ""),
            "category":    need.get("category", ""),
            "type":        need.get("type", "missing"),
            "type_label":  _TYPE_LABEL.get(need.get("type", "missing"), ""),
            "products":    products,
            "search_url":  musinsa_url,
            "search_query": query,
        })

    return cards
