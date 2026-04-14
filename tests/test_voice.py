"""
tests/test_voice.py — 음성 파이프라인 3종 독립 검증 스크립트
서버 실행 없이 바로 돌릴 수 있음.

실행:
  cd CW
  python tests/test_voice.py

항목:
  [1] Google TTS  — ko-KR-Neural2-B 음성, PCM 정상 반환 여부
  [2] Gemini Live — TEXT 모드 텍스트 응답 정상 수신 여부
  [3] clean_for_tts — 기호·영어 제거·변환 정확도
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
# [2] Gemini Live TEXT 모드 테스트
# ════════════════════════════════════════════════════════════════════
async def test_gemini():
    section("[2] Gemini Live — TEXT 모드 응답")

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        fail("GEMINI_API_KEY 없음 → .env 확인")
        return False

    try:
        from google import genai
        from google.genai import types
    except ImportError:
        fail("google-genai 패키지 미설치 → pip install google-genai")
        return False

    client = genai.Client(api_key=api_key)
    config = types.LiveConnectConfig(
        response_modalities=["TEXT"],
        system_instruction=types.Content(
            parts=[types.Part(text=(
                "너는 코디 전문가야. 두 문장 이내로 한국어로만 짧게 답해. "
                "기호, 이모지, 영어 절대 사용 금지."
            ))]
        ),
    )

    received_text = ""
    chunk_count   = 0

    try:
        async with client.aio.live.connect(
            model="gemini-2.0-flash-live-001", config=config
        ) as session:

            ok("Gemini Live WebSocket 연결 성공")

            # 텍스트 입력으로 테스트 (오디오 없이도 응답 확인 가능)
            await session.send(
                input="오늘 청바지에 뭐 입으면 좋아? 날씨가 좀 쌀쌀해.",
                end_of_turn=True,
            )
            ok("텍스트 입력 전송 완료")

            async for response in session.receive():
                # 텍스트 청크 수집 (SDK 버전에 따라 두 경로 모두 체크)
                chunk = None
                if hasattr(response, "text") and response.text:
                    chunk = response.text
                elif (
                    response.server_content
                    and response.server_content.model_turn
                    and response.server_content.model_turn.parts
                ):
                    for part in response.server_content.model_turn.parts:
                        if hasattr(part, "text") and part.text:
                            chunk = (chunk or "") + part.text

                if chunk:
                    received_text += chunk
                    chunk_count   += 1

                # 오디오 청크가 오면 경고 (TEXT 모드인데 AUDIO가 오면 안 됨)
                if (
                    response.server_content
                    and response.server_content.model_turn
                ):
                    for part in response.server_content.model_turn.parts:
                        if hasattr(part, "inline_data") and part.inline_data:
                            fail("⚠️  오디오 청크 수신됨 — response_modalities가 TEXT가 아닐 수 있음")

                if response.server_content and response.server_content.turn_complete:
                    ok("turn_complete 신호 수신")
                    break

    except Exception as e:
        fail(f"Gemini Live 연결/수신 오류 — {e}")
        return False

    if not received_text:
        fail("텍스트 응답 없음 — response_modalities=['TEXT'] 설정 재확인 필요")
        return False

    ok(f"텍스트 청크 {chunk_count}개 수신")
    ok(f"응답 내용: {received_text.strip()[:120]}")

    # 검증 — 기호 포함 여부
    bad_chars = [c for c in ["*", "_", "#", "-", "—", "•"] if c in received_text]
    if bad_chars:
        print(f"  ⚠️  기호 포함됨 {bad_chars} → clean_for_tts()가 처리할 예정")
    else:
        ok("기호 없음 — clean_for_tts() 부담 최소")

    return True


# ════════════════════════════════════════════════════════════════════
# [3] clean_for_tts 정확도 테스트
# ════════════════════════════════════════════════════════════════════
def test_clean_for_tts():
    section("[3] clean_for_tts — 기호·영어 정제 검증")

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

    # [2] Gemini Live
    results["Gemini Live TEXT"] = await test_gemini()

    # [3] clean_for_tts (동기)
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
