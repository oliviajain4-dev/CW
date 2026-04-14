"""
chatbot/tts.py — Google Cloud TTS 공용 모듈
텍스트 정제(clean_for_tts) + TTS 합성(synthesize_speech) 을 한 곳에서 관리.

사용법:
    from chatbot.tts import clean_for_tts, synthesize_speech, _SENTENCE_END
    pcm_bytes = await synthesize_speech("안녕하세요")
"""
import base64
import io
import os
import re
import wave

import httpx

# ── Google TTS 설정 ───────────────────────────────────────────────────
_TTS_URL   = "https://texttospeech.googleapis.com/v1/text:synthesize"
_TTS_VOICE = {"languageCode": "ko-KR", "name": "ko-KR-Neural2-B"}
_TTS_RATE  = 24000   # 출력 샘플레이트 (브라우저 재생 기준)

# 문장 종결 패턴 — 스트리밍 TTS에서 문장 단위 분리용
_SENTENCE_END = re.compile(r'[.?!。]+')

# ── 영어 → 한국어 패션 용어 변환 테이블 (긴 표현 먼저) ─────────────────
_EN_KO: list[tuple[str, str]] = [
    # 복합어 (먼저 처리)
    (r'\bwide[\s-]?pants?\b',      '와이드팬츠'),
    (r'\bjogger[\s-]?pants?\b',    '조거팬츠'),
    (r'\bset[\s-]?up\b',           '세트업'),
    (r'\bone[\s-]?piece\b',        '원피스'),
    (r'\bjump[\s-]?suit\b',        '점프수트'),
    (r'\bt[\s-]?shirt\b',          '티셔츠'),
    (r'\bround[\s-]?neck\b',       '라운드넥'),
    (r'\bv[\s-]?neck\b',           '브이넥'),
    (r'\bturtle[\s-]?neck\b',      '터틀넥'),
    (r'\bover[\s-]?fit\b',         '오버핏'),
    (r'\bslim[\s-]?fit\b',         '슬림핏'),
    (r'\bloose[\s-]?fit\b',        '루즈핏'),
    (r'\btube[\s-]?top\b',         '튜브탑'),
    (r'\btrench[\s-]?coat\b',      '트렌치코트'),
    (r'\bwind[\s-]?breaker\b',     '바람막이'),
    (r'\btote[\s-]?bag\b',         '토트백'),
    (r'\bback[\s-]?pack\b',        '백팩'),
    # 단어
    (r'\bblouse\b',                '블라우스'),
    (r'\bshirt\b',                 '셔츠'),
    (r'\bknit(?:wear)?\b',         '니트'),
    (r'\bhoodie\b',                '후드티'),
    (r'\bsweatshirt\b',            '맨투맨'),
    (r'\bcardigan\b',              '가디건'),
    (r'\bvest\b',                  '조끼'),
    (r'\bjeans?\b',                '청바지'),
    (r'\bdenim\b',                 '청바지'),
    (r'\bskirt\b',                 '스커트'),
    (r'\bshorts?\b',               '반바지'),
    (r'\bleggings?\b',             '레깅스'),
    (r'\bslacks?\b',               '슬랙스'),
    (r'\bpants?\b',                '팬츠'),
    (r'\bdress\b',                 '원피스'),
    (r'\bjumpsuit\b',              '점프수트'),
    (r'\bcoat\b',                  '코트'),
    (r'\bblazer\b',                '블레이저'),
    (r'\bjacket\b',                '재킷'),
    (r'\btrench\b',                '트렌치코트'),
    (r'\bpadding\b',               '패딩'),
    (r'\bparka\b',                 '파카'),
    (r'\bouter\b',                 '아우터'),
    (r'\bsneakers?\b',             '스니커즈'),
    (r'\bboots?\b',                '부츠'),
    (r'\bloafers?\b',              '로퍼'),
    (r'\bheels?\b',                '힐'),
    (r'\bsandals?\b',              '샌들'),
    (r'\bmules?\b',                '뮬'),
    (r'\bbackpack\b',              '백팩'),
    (r'\btote\b',                  '토트백'),
    (r'\bclutch\b',                '클러치'),
    (r'\bbag\b',                   '가방'),
    (r'\bbelt\b',                  '벨트'),
    (r'\bscarf\b',                 '스카프'),
    (r'\bbeanie\b',                '비니'),
    (r'\bcap\b',                   '모자'),
    (r'\bhat\b',                   '모자'),
    (r'\bcasual\b',                '캐주얼'),
    (r'\bformal\b',                '포멀'),
    (r'\bbasic\b',                 '베이직'),
    (r'\bvintage\b',               '빈티지'),
    (r'\bminimal\b',               '미니멀'),
]

_EN_KO_COMPILED = [(re.compile(p, re.IGNORECASE), r) for p, r in _EN_KO]


def clean_for_tts(text: str) -> str:
    """
    TTS 전달 전 텍스트 정제.
    마크다운·이모지·특수기호·영어 패션 용어를 모두 제거/변환한다.
    """
    # 1. 이모지 전체 제거
    text = re.sub(
        r'['
        r'\U0001F600-\U0001F64F'
        r'\U0001F300-\U0001F5FF'
        r'\U0001F680-\U0001F6FF'
        r'\U0001F1E0-\U0001F1FF'
        r'\U00002600-\U000027BF'
        r'\U0001F900-\U0001F9FF'
        r'\U0001FA00-\U0001FA6F'
        r'\U0001FA70-\U0001FAFF'
        r'\u2702-\u27B0'
        r'\uFE00-\uFE0F'
        r']', '', text
    )
    # 2. 마크다운 강조 기호 (**bold**, *italic*, __ul__, ~~strike~~, `code`)
    text = re.sub(r'\*{1,3}|_{1,3}|~{2}|`{1,3}', '', text)
    # 3. 헤더 (#, ##, ###)
    text = re.sub(r'^#{1,6}\s*', '', text, flags=re.MULTILINE)
    # 4. 번호 목록 (1. 2. 3.)
    text = re.sub(r'^\s*\d+\.\s+', '', text, flags=re.MULTILINE)
    # 5. 글머리 기호 (- + * • ◦ ▪ ▸ ➤)
    text = re.sub(r'^\s*[-+*•◦▪▸➤]\s+', '', text, flags=re.MULTILINE)
    # 6. 인용 블록 (>)
    text = re.sub(r'^\s*>\s*', '', text, flags=re.MULTILINE)
    # 7a. 이중/삼중 대시 (--  ---)
    text = re.sub(r'-{2,}', '', text)
    # 7b. 특수 단일 문자: 밑줄, 엠대시, 가운데점, 기타
    text = re.sub(r'[_—·|\\()\[\]{}<>@^%$&]', '', text)
    # 8. 영어 → 한국어 패션 용어 변환
    for pattern, replacement in _EN_KO_COMPILED:
        text = pattern.sub(replacement, text)
    # 9. 연속 줄바꿈 → 공백
    text = re.sub(r'\n{2,}', ' ', text)
    # 10. 연속 공백 정리
    text = re.sub(r'\s{2,}', ' ', text)
    return text.strip()


async def synthesize_speech(text: str) -> bytes:
    """
    Google Cloud TTS REST API → raw PCM bytes (WAV 헤더 제거).
    출력: 24kHz 16-bit mono PCM
    GOOGLE_TTS_API_KEY 환경변수 필요.
    """
    api_key = os.getenv("GOOGLE_TTS_API_KEY")
    payload = {
        "input": {"text": text},
        "voice": _TTS_VOICE,
        "audioConfig": {
            "audioEncoding": "LINEAR16",
            "sampleRateHertz": _TTS_RATE,
        },
    }
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(_TTS_URL, params={"key": api_key}, json=payload)
        resp.raise_for_status()

    wav_bytes = base64.b64decode(resp.json()["audioContent"])
    with wave.open(io.BytesIO(wav_bytes)) as wf:
        return wf.readframes(wf.getnframes())
