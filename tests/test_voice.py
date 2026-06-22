"""
tests/test_voice.py — 음성 파이프라인 3종 독립 검증 스크립트
서버 실행 없이 바로 돌릴 수 있음.

실행:
  cd CW
  python tests/test_voice.py

항목:
  [1] Google TTS  — ko-KR-Neural2-B 음성, PCM 정상 반환 여부
  [2] clean_for_tts — 기호·영어 제거·변환 정확도

참고: Gemini Live 검증은 제거됨 (REDESIGN.md — Claude 단일화로 음성 LLM 대체).
"""

import asyncio
import base64
import io
import os
import sys
import wave

import httpx
from dotenv import load_dotenv

# .env 로드 (CW 루트 기준)
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), "..", ".env"))

# voice/ 패키지 경로 등록
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ════════════════════════════════════════════════════════════════════
# 공통 유틸
# ════════════════════════════════════════════════════════════════════
def ok(msg): print(f"  ✅ {msg}")
def fail(msg): print(f"  ❌ {msg}")
def section(title): print(f"\n{'─'*55}\n  {title}\n{'─'*55}")


# ════════════════════════════════════════════════════════════════════
# [1] Google TTS 테스트
# ════════════════════════════════════════════════════════════════════
async def test_tts():
    section("[1] Google TTS — ko-KR-Neural2-B")

    api_key = os.getenv("GOOGLE_TTS_API_KEY")
    if not api_key:
        fail("GOOGLE_TTS_API_KEY 없음 → .env 확인")
        return False

    url = "https://texttospeech.googleapis.com/v1/text:synthesize"
    payload = {
        "input": {"text": "안녕, 오늘 코디 도와줄게. 날씨가 쌀쌀하니까 코트 어때?"},
        "voice": {"languageCode": "ko-KR", "name": "ko-KR-Neural2-B"},
        "audioConfig": {
            "audioEncoding": "LINEAR16",
            "sampleRateHertz": 24000,
        },
    }

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.post(url, params={"key": api_key}, json=payload)

        if r.status_code != 200:
            fail(f"HTTP {r.status_code} — {r.text[:200]}")
            return False

        data = r.json()
        if "audioContent" not in data:
            fail(f"audioContent 키 없음 — 응답: {data}")
            return False

        wav_bytes = base64.b64decode(data["audioContent"])
        ok(f"WAV 수신 — {len(wav_bytes):,} bytes")

        # WAV 헤더 파싱 → PCM 추출
        with wave.open(io.BytesIO(wav_bytes)) as wf:
            channels    = wf.getnchannels()
            sample_rate = wf.getframerate()
            sample_width = wf.getsampwidth()
            n_frames    = wf.getnframes()
            pcm         = wf.readframes(n_frames)

        duration = n_frames / sample_rate
        ok(f"PCM 파싱 — {sample_rate}Hz / {sample_width*8}bit / {channels}ch / {duration:.2f}초")

        # 검증
        assert sample_rate == 24000,  f"sampleRate={sample_rate} (기대: 24000)"
        assert sample_width == 2,     f"sampleWidth={sample_width} (기대: 2=16bit)"
        assert channels == 1,         f"channels={channels} (기대: 1=mono)"
        assert len(pcm) > 0,          "PCM 데이터 비어 있음"

        ok(f"PCM raw — {len(pcm):,} bytes — 모든 조건 통과")
        return True

    except AssertionError as e:
        fail(f"조건 불일치 — {e}")
        return False
    except Exception as e:
        fail(f"예외 — {e}")
        return False


# ════════════════════════════════════════════════════════════════════
# [2] clean_for_tts 정확도 테스트
# ════════════════════════════════════════════════════════════════════
def test_clean_for_tts():
    section("[2] clean_for_tts — 기호·영어 정제 검증")

    try:
        from voice.pipeline import clean_for_tts
    except ImportError as e:
        fail(f"voice.pipeline import 실패 — {e}")
        return False

    cases = [
        # (입력, 기대 포함 키워드, 기대 제거 키워드)
        ("**오늘** t-shirt 어때?",           ["티셔츠"],          ["**", "t-shirt"]),
        ("코디: — jeans + jacket 조합✨",     ["청바지", "재킷"],  ["—", "✨", "jeans", "jacket"]),
        ("1. coat\n2. sneakers\n3. beanie",  ["코트", "스니커즈", "비니"], ["1.", "2.", "3."]),
        ("wide pants에 hoodie 어울려?",       ["와이드팬츠", "후드티"], ["wide", "hoodie"]),
        ("*추천*: turtle-neck + trench coat",["터틀넥", "트렌치코트"], ["*", "turtle-neck"]),
    ]

    all_pass = True
    for text, must_have, must_not in cases:
        result = clean_for_tts(text)
        has_all   = all(k in result for k in must_have)
        has_none  = all(k not in result for k in must_not)
        passed    = has_all and has_none

        status = "✅" if passed else "❌"
        print(f"  {status} 입력: {text[:45]!r}")
        print(f"     결과: {result!r}")
        if not has_all:
            missing = [k for k in must_have if k not in result]
            print(f"     누락: {missing}")
        if not has_none:
            remaining = [k for k in must_not if k in result]
            print(f"     미제거: {remaining}")
        print()

        if not passed:
            all_pass = False

    if all_pass:
        ok("clean_for_tts 전체 케이스 통과")
    else:
        fail("일부 케이스 실패 — voice/pipeline.py clean_for_tts 수정 필요")

    return all_pass


# ════════════════════════════════════════════════════════════════════
# 메인
# ════════════════════════════════════════════════════════════════════
async def main():
    print("\n" + "═"*55)
    print("  음성 파이프라인 검증 — test_voice.py")
    print("═"*55)

    results = {}

    # [1] TTS
    results["Google TTS"] = await test_tts()

    # [2] clean_for_tts (동기)
    results["clean_for_tts"] = test_clean_for_tts()

    # 최종 요약
    section("최종 결과")
    all_ok = True
    for name, passed in results.items():
        icon = "✅" if passed else "❌"
        print(f"  {icon}  {name}")
        if not passed:
            all_ok = False

    print()
    if all_ok:
        print("  🎉 전체 통과 — 서버 켜고 실제 음성 테스트 진행 가능")
    else:
        print("  ⚠️  실패 항목 수정 후 재실행하세요")
    print()


if __name__ == "__main__":
    asyncio.run(main())
