"""
calendar_client.py — Google Calendar API 연동
- 오늘 일정 가져오기
- 일정 제목 기반 TPO 자동 추론
"""

from __future__ import annotations
import httpx
from datetime import datetime, timezone
from typing import Optional


def get_today_events(access_token: str) -> list[dict[str, str]]:
    """
    Google Calendar API로 오늘 일정 가져오기
    access_token: Google OAuth 로그인 후 세션에 저장된 토큰
    """
    try:
        now = datetime.now(timezone.utc)
        # 한국 시간 기준 오늘 (UTC+9)
        from datetime import timedelta
        kst_offset = timedelta(hours=9)
        kst_now = now + kst_offset
        day_start = kst_now.replace(hour=0, minute=0, second=0, microsecond=0) - kst_offset
        day_end   = kst_now.replace(hour=23, minute=59, second=59, microsecond=0) - kst_offset

        url = "https://www.googleapis.com/calendar/v3/calendars/primary/events"
        headers = {"Authorization": f"Bearer {access_token}"}
        params = {
            "timeMin":      day_start.isoformat() + "Z",
            "timeMax":      day_end.isoformat() + "Z",
            "singleEvents": True,
            "orderBy":      "startTime",
            "maxResults":   10,
        }

        resp = httpx.get(url, headers=headers, params=params, timeout=8)
        resp.raise_for_status()

        events = []
        for item in resp.json().get("items", []):
            title      = item.get("summary", "")
            start_raw  = item.get("start", {})
            start_time = start_raw.get("dateTime", start_raw.get("date", ""))
            location   = item.get("location", "")
            events.append({
                "title":    title,
                "start":    start_time,
                "location": location,
            })
        return events

    except Exception as e:
        print(f"[calendar] API 오류: {e}")
        return []


# ── 일정 제목 → TPO 자동 추론 ──────────────────────────────────────
_TPO_KEYWORDS = {
    "비즈니스": ["회의", "미팅", "발표", "프레젠테이션", "면접", "출장", "컨퍼런스", "세미나", "meeting", "interview"],
    "데이트":   ["데이트", "소개팅", "약속", "dinner", "date"],
    "스포츠":   ["운동", "헬스", "요가", "등산", "러닝", "수영", "축구", "야구", "gym"],
    "파티":     ["파티", "party", "행사", "축제", "결혼식", "졸업식", "동창회"],
    "캐주얼":   ["쇼핑", "카페", "영화", "친구"],
}


def tpo_from_events(events: list[dict[str, str]]) -> Optional[str]:
    """
    일정 제목 분석 → TPO 자동 추론
    추론 실패 시 None 반환 (사용자 설정 TPO 유지)
    """
    for event in events:
        title = event.get("title", "").lower()
        for tpo, keywords in _TPO_KEYWORDS.items():
            if any(kw in title for kw in keywords):
                return tpo
    return None


def format_events_for_prompt(events: list[dict[str, str]]) -> str:
    """Claude 프롬프트에 삽입할 일정 텍스트 생성"""
    if not events:
        return ""
    lines = []
    for ev in events:
        time_str = ev.get("start", "")
        if "T" in time_str:
            # dateTime 형식 → 시간만 추출
            try:
                dt = datetime.fromisoformat(time_str.replace("Z", "+00:00"))
                from datetime import timedelta
                kst = dt + timedelta(hours=9)
                time_str = kst.strftime("%H:%M")
            except Exception:
                pass
        loc = f" ({ev['location']})" if ev.get("location") else ""
        lines.append(f"  - {time_str} {ev['title']}{loc}")
    return "\n".join(lines)
