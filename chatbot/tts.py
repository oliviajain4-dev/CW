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
# 한국어 종결어미(다/어/야/네/요/죠/군/걸) 뒤 공백 또는 문장부호도 감지
_SENTENCE_END = re.compile(
    r'[.?!。！？]+\s*|'                          # 문장부호 (기존)
    r'(?<=[다어야네요죠군걸])\s+(?=[^다어야네요죠군걸\s])|'  # 종결어미 뒤 공백 + 다음 글자
    r'(?<=[다어야네요죠군걸])\s*\n'               # 종결어미 뒤 줄바꿈
)

# ══════════════════════════════════════════════════════════════════════════
# ⚠️  TTS 절대규칙 — 이 테이블은 수정·삭제 금지 (CLAUDE.md 참고)
#     voice.js의 _EN_KO_JS 와 항상 동일한 내용을 유지해야 합니다.
# ══════════════════════════════════════════════════════════════════════════
# ── 영어 → 한국어 변환 테이블 (복합어를 반드시 단어보다 먼저 배치) ─────────
_EN_KO: list[tuple[str, str]] = [

    # ── 상의 복합어 ──────────────────────────────────────────────────────
    (r'\bt[\s-]?shirt\b',            '티셔츠'),
    (r'\bcrop[\s-]?top\b',           '크롭탑'),
    (r'\btank[\s-]?top\b',           '탱크탑'),
    (r'\btube[\s-]?top\b',           '튜브탑'),
    (r'\bpolo[\s-]?shirt\b',         '폴로셔츠'),
    (r'\bround[\s-]?neck\b',         '라운드넥'),
    (r'\bv[\s-]?neck\b',             '브이넥'),
    (r'\bturtle[\s-]?neck\b',        '터틀넥'),
    (r'\bover[\s-]?fit\b',           '오버핏'),
    (r'\bslim[\s-]?fit\b',           '슬림핏'),
    (r'\bloose[\s-]?fit\b',          '루즈핏'),

    # ── 하의 복합어 ──────────────────────────────────────────────────────
    (r'\bwide[\s-]?pants?\b',        '와이드팬츠'),
    (r'\bjogger[\s-]?pants?\b',      '조거팬츠'),
    (r'\bcargo[\s-]?pants?\b',       '카고팬츠'),
    (r'\blinen[\s-]?pants?\b',       '린넨팬츠'),
    (r'\bflare[\s-]?skirt\b',        '플레어스커트'),
    (r'\bmini[\s-]?skirt\b',         '미니스커트'),
    (r'\bmidi[\s-]?skirt\b',         '미디스커트'),
    (r'\bmaxi[\s-]?skirt\b',         '맥시스커트'),
    (r'\bwrap[\s-]?skirt\b',         '랩스커트'),

    # ── 아우터 복합어 ─────────────────────────────────────────────────────
    (r'\bdenim[\s-]?jacket\b',       '청자켓'),
    (r'\bset[\s-]?up\b',             '세트업'),
    (r'\bone[\s-]?piece\b',          '원피스'),
    (r'\bjump[\s-]?suit\b',          '점프수트'),
    (r'\btrench[\s-]?coat\b',        '트렌치코트'),
    (r'\bwind[\s-]?breaker\b',       '바람막이'),
    (r'\bdown[\s-]?jacket\b',        '다운재킷'),

    # ── 가방 복합어 ──────────────────────────────────────────────────────
    (r'\btote[\s-]?bag\b',           '토트백'),
    (r'\bback[\s-]?pack\b',          '백팩'),
    (r'\bcross[\s-]?bag\b',          '크로스백'),
    (r'\bshoulder[\s-]?bag\b',       '숄더백'),
    (r'\bfanny[\s-]?pack\b',         '힙색'),

    # ── 상의 단어 ─────────────────────────────────────────────────────────
    (r'\bblouse\b',                  '블라우스'),
    (r'\bshirt\b',                   '셔츠'),
    (r'\bknit(?:wear)?\b',           '니트'),
    (r'\bhoodie\b',                  '후드티'),
    (r'\bsweatshirt\b',              '맨투맨'),
    (r'\bcardigan\b',                '가디건'),
    (r'\bvest\b',                    '조끼'),
    (r'\bsleeveless\b',              '민소매'),
    (r'\bpolo\b',                    '폴로'),

    # ── 하의 단어 ─────────────────────────────────────────────────────────
    (r'\bjeans?\b',                  '청바지'),
    (r'\bdenim\b',                   '데님'),
    (r'\bskirt\b',                   '스커트'),
    (r'\bshorts?\b',                 '반바지'),
    (r'\bleggings?\b',               '레깅스'),
    (r'\bslacks?\b',                 '슬랙스'),
    (r'\bpants?\b',                  '팬츠'),
    (r'\btrousers?\b',               '바지'),

    # ── 원피스·아우터 단어 ────────────────────────────────────────────────
    (r'\bdress\b',                   '원피스'),
    (r'\bjumpsuit\b',                '점프수트'),
    (r'\bcoat\b',                    '코트'),
    (r'\bblazer\b',                  '블레이저'),
    (r'\bjacket\b',                  '재킷'),
    (r'\btrench\b',                  '트렌치코트'),
    (r'\bpadding\b',                 '패딩'),
    (r'\bparka\b',                   '파카'),
    (r'\bouter(?:wear)?\b',          '아우터'),

    # ── 신발 ──────────────────────────────────────────────────────────────
    (r'\bsneakers?\b',               '스니커즈'),
    (r'\bboots?\b',                  '부츠'),
    (r'\bloafers?\b',                '로퍼'),
    (r'\bheels?\b',                  '힐'),
    (r'\bsandals?\b',                '샌들'),
    (r'\bmules?\b',                  '뮬'),
    (r'\bflats?\b',                  '플랫슈즈'),
    (r'\bslipper\b',                 '슬리퍼'),

    # ── 가방·악세서리 단어 ────────────────────────────────────────────────
    (r'\bbackpack\b',                '백팩'),
    (r'\btote\b',                    '토트백'),
    (r'\bclutch\b',                  '클러치'),
    (r'\bbag\b',                     '가방'),
    (r'\bbelt\b',                    '벨트'),
    (r'\bscarf\b',                   '스카프'),
    (r'\bbeanie\b',                  '비니'),
    (r'\bcap\b',                     '모자'),
    (r'\bhat\b',                     '모자'),
    (r'\bnecklace\b',                '목걸이'),
    (r'\bearrings?\b',               '귀걸이'),
    (r'\bbracelet\b',                '팔찌'),
    (r'\bwatch\b',                   '시계'),
    (r'\bsunglasses?\b',             '선글라스'),
    (r'\bgloves?\b',                 '장갑'),

    # ── 소재 ──────────────────────────────────────────────────────────────
    (r'\bcotton\b',                  '면'),
    (r'\blinen\b',                   '린넨'),
    (r'\bwool\b',                    '울'),
    (r'\bleather\b',                 '가죽'),
    (r'\bsuede\b',                   '스웨이드'),
    (r'\bsatin\b',                   '새틴'),
    (r'\bsilk\b',                    '실크'),
    (r'\bchiffon\b',                 '시폰'),
    (r'\bfleece\b',                  '플리스'),
    (r'\bvelvet\b',                  '벨벳'),
    (r'\bcorduroy\b',                '코듀로이'),
    (r'\btweed\b',                   '트위드'),
    (r'\bcashmere\b',                '캐시미어'),
    (r'\bpolyester\b',               '폴리에스터'),
    (r'\bspandex\b',                 '스판'),

    # ── 컬러 ──────────────────────────────────────────────────────────────
    (r'\bblack\b',                   '블랙'),
    (r'\bwhite\b',                   '화이트'),
    (r'\bbeige\b',                   '베이지'),
    (r'\bgr[ae]y\b',                 '그레이'),
    (r'\bnavy\b',                    '네이비'),
    (r'\bbrown\b',                   '브라운'),
    (r'\bivory\b',                   '아이보리'),
    (r'\bcamel\b',                   '카멜'),
    (r'\bmustard\b',                 '머스타드'),
    (r'\bkhaki\b',                   '카키'),
    (r'\bolive\b',                   '올리브'),
    (r'\bburgundy\b',                '버건디'),
    (r'\bwine\b',                    '와인'),
    (r'\bcream\b',                   '크림'),
    (r'\bpink\b',                    '핑크'),
    (r'\bred\b',                     '레드'),
    (r'\bblue\b',                    '블루'),
    (r'\bgreen\b',                   '그린'),
    (r'\byellow\b',                  '옐로'),
    (r'\bpurple\b',                  '퍼플'),
    (r'\borange\b',                  '오렌지'),
    (r'\bgold\b',                    '골드'),
    (r'\bsilver\b',                  '실버'),

    # ── 스타일·무드 ───────────────────────────────────────────────────────
    (r'\bcasual\b',                  '캐주얼'),
    (r'\bformal\b',                  '포멀'),
    (r'\bbasic\b',                   '베이직'),
    (r'\bvintage\b',                 '빈티지'),
    (r'\bminimal(?:ist)?\b',         '미니멀'),
    (r'\bstreetwear\b',              '스트릿'),
    (r'\bsporty\b',                  '스포티'),
    (r'\belegant\b',                 '엘레강스'),
    (r'\bclassy\b',                  '클래식'),
    (r'\bchic\b',                    '시크'),
    (r'\bcute\b',                    '큐트'),
    (r'\bcool\b',                    '쿨'),
    (r'\bstyling\b',                 '스타일링'),
    (r'\bcoordination\b',            '코디'),
    (r'\boutfit\b',                  '코디'),
    (r'\blook\b',                    '룩'),
    (r'\bTPO\b',                     '티피오'),
    (r'\bSNS\b',                     '에스엔에스'),
    (r'\bmixed\b',                   '혼방'),
    (r'\btexture\b',                 '소재'),
    (r'\bwarmth\b',                  '보온'),
    (r'\blayering\b',                '레이어링'),
]

# re.ASCII: 한국어를 \W(비단어)로 취급 → 영어단어 바로 뒤에 한글이 붙어도 \b 정상 동작
_EN_KO_COMPILED = [(re.compile(p, re.IGNORECASE | re.ASCII), r) for p, r in _EN_KO]


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
    # 7a. 이중/삼중 대시 → 공백
    text = re.sub(r'-{2,}', ' ', text)
    # 7b. 각종 대시·구분자 → 공백으로 변환 (TTS가 "대시"로 읽는 문자 모두 포함)
    text = re.sub(r'[-\u2013\u2014\u00B7\u30FB\uFF65·]', ' ', text)  # - – — · ・ ･
    # 7c. 기타 특수기호 → 제거 (괄호·기호는 공백 삽입 후 제거)
    text = re.sub(r'[_|\\()\[\]{}<>@^%$&※°℃]', ' ', text)
    # 8. 영어 → 한국어 패션 용어 변환
    for pattern, replacement in _EN_KO_COMPILED:
        text = pattern.sub(replacement, text)
    # 9. 변환 후 남은 영문자 전부 제거 (순수 한국어만 TTS로 전달)
    text = re.sub(r'[A-Za-z]+', '', text)
    # 10. 연속 줄바꿈 → 공백
    text = re.sub(r'\n{2,}', ' ', text)
    # 11. 단일 줄바꿈 → 공백
    text = re.sub(r'\n', ' ', text)
    # 12. 연속 공백 정리
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
