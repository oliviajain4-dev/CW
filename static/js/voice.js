/* ============================================================
   voice.js — 음성 어시스턴트 (My Mini Co-di)
   Web Speech API(TTS + STT) + /chat 엔드포인트 연결
   ============================================================ */
(function () {
  'use strict';

  const synth = window.speechSynthesis;
  let recognition  = null;
  let isListening  = false;
  let isSpeaking   = false;
  let ttsEnabled   = true;
  let lastComment  = '';

  // ══════════════════════════════════════════════════════════════════════
  // ⚠️  TTS 절대규칙 — 이 테이블과 cleanText()는 수정·삭제 금지 (CLAUDE.md 참고)
  //     Python chatbot/tts.py의 _EN_KO 와 항상 동일한 내용을 유지해야 합니다.
  // ══════════════════════════════════════════════════════════════════════
  const _EN_KO_JS = [
    // ── 상의 복합어
    [/\bt[\s-]?shirt\b/gi,            '티셔츠'],
    [/\bcrop[\s-]?top\b/gi,           '크롭탑'],
    [/\btank[\s-]?top\b/gi,           '탱크탑'],
    [/\btube[\s-]?top\b/gi,           '튜브탑'],
    [/\bpolo[\s-]?shirt\b/gi,         '폴로셔츠'],
    [/\bround[\s-]?neck\b/gi,         '라운드넥'],
    [/\bv[\s-]?neck\b/gi,             '브이넥'],
    [/\bturtle[\s-]?neck\b/gi,        '터틀넥'],
    [/\bover[\s-]?fit\b/gi,           '오버핏'],
    [/\bslim[\s-]?fit\b/gi,           '슬림핏'],
    [/\bloose[\s-]?fit\b/gi,          '루즈핏'],
    // ── 하의 복합어
    [/\bwide[\s-]?pants?\b/gi,        '와이드팬츠'],
    [/\bjogger[\s-]?pants?\b/gi,      '조거팬츠'],
    [/\bcargo[\s-]?pants?\b/gi,       '카고팬츠'],
    [/\blinen[\s-]?pants?\b/gi,       '린넨팬츠'],
    [/\bflare[\s-]?skirt\b/gi,        '플레어스커트'],
    [/\bmini[\s-]?skirt\b/gi,         '미니스커트'],
    [/\bmidi[\s-]?skirt\b/gi,         '미디스커트'],
    [/\bmaxi[\s-]?skirt\b/gi,         '맥시스커트'],
    [/\bwrap[\s-]?skirt\b/gi,         '랩스커트'],
    // ── 아우터 복합어
    [/\bdenim[\s-]?jacket\b/gi,       '청자켓'],
    [/\bset[\s-]?up\b/gi,             '세트업'],
    [/\bone[\s-]?piece\b/gi,          '원피스'],
    [/\bjump[\s-]?suit\b/gi,          '점프수트'],
    [/\btrench[\s-]?coat\b/gi,        '트렌치코트'],
    [/\bwind[\s-]?breaker\b/gi,       '바람막이'],
    [/\bdown[\s-]?jacket\b/gi,        '다운재킷'],
    // ── 가방 복합어
    [/\btote[\s-]?bag\b/gi,           '토트백'],
    [/\bback[\s-]?pack\b/gi,          '백팩'],
    [/\bcross[\s-]?bag\b/gi,          '크로스백'],
    [/\bshoulder[\s-]?bag\b/gi,       '숄더백'],
    [/\bfanny[\s-]?pack\b/gi,         '힙색'],
    // ── 상의 단어
    [/\bblouse\b/gi,                  '블라우스'],
    [/\bshirt\b/gi,                   '셔츠'],
    [/\bknit(?:wear)?\b/gi,           '니트'],
    [/\bhoodie\b/gi,                  '후드티'],
    [/\bsweatshirt\b/gi,              '맨투맨'],
    [/\bcardigan\b/gi,                '가디건'],
    [/\bvest\b/gi,                    '조끼'],
    [/\bsleeveless\b/gi,              '민소매'],
    [/\bpolo\b/gi,                    '폴로'],
    // ── 하의 단어
    [/\bjeans?\b/gi,                  '청바지'],
    [/\bdenim\b/gi,                   '데님'],
    [/\bskirt\b/gi,                   '스커트'],
    [/\bshorts?\b/gi,                 '반바지'],
    [/\bleggings?\b/gi,               '레깅스'],
    [/\bslacks?\b/gi,                 '슬랙스'],
    [/\bpants?\b/gi,                  '팬츠'],
    [/\btrousers?\b/gi,               '바지'],
    // ── 원피스·아우터 단어
    [/\bdress\b/gi,                   '원피스'],
    [/\bjumpsuit\b/gi,                '점프수트'],
    [/\bcoat\b/gi,                    '코트'],
    [/\bblazer\b/gi,                  '블레이저'],
    [/\bjacket\b/gi,                  '재킷'],
    [/\btrench\b/gi,                  '트렌치코트'],
    [/\bpadding\b/gi,                 '패딩'],
    [/\bparka\b/gi,                   '파카'],
    [/\bouter(?:wear)?\b/gi,          '아우터'],
    // ── 신발
    [/\bsneakers?\b/gi,               '스니커즈'],
    [/\bboots?\b/gi,                  '부츠'],
    [/\bloafers?\b/gi,                '로퍼'],
    [/\bheels?\b/gi,                  '힐'],
    [/\bsandals?\b/gi,                '샌들'],
    [/\bmules?\b/gi,                  '뮬'],
    [/\bflats?\b/gi,                  '플랫슈즈'],
    [/\bslipper\b/gi,                 '슬리퍼'],
    // ── 가방·악세서리 단어
    [/\bbackpack\b/gi,                '백팩'],
    [/\btote\b/gi,                    '토트백'],
    [/\bclutch\b/gi,                  '클러치'],
    [/\bbag\b/gi,                     '가방'],
    [/\bbelt\b/gi,                    '벨트'],
    [/\bscarf\b/gi,                   '스카프'],
    [/\bbeanie\b/gi,                  '비니'],
    [/\bcap\b/gi,                     '모자'],
    [/\bhat\b/gi,                     '모자'],
    [/\bnecklace\b/gi,                '목걸이'],
    [/\bearrings?\b/gi,               '귀걸이'],
    [/\bbracelet\b/gi,                '팔찌'],
    [/\bwatch\b/gi,                   '시계'],
    [/\bsunglasses?\b/gi,             '선글라스'],
    [/\bgloves?\b/gi,                 '장갑'],
    // ── 소재
    [/\bcotton\b/gi,                  '면'],
    [/\blinen\b/gi,                   '린넨'],
    [/\bwool\b/gi,                    '울'],
    [/\bleather\b/gi,                 '가죽'],
    [/\bsuede\b/gi,                   '스웨이드'],
    [/\bsatin\b/gi,                   '새틴'],
    [/\bsilk\b/gi,                    '실크'],
    [/\bchiffon\b/gi,                 '시폰'],
    [/\bfleece\b/gi,                  '플리스'],
    [/\bvelvet\b/gi,                  '벨벳'],
    [/\bcorduroy\b/gi,                '코듀로이'],
    [/\btweed\b/gi,                   '트위드'],
    [/\bcashmere\b/gi,                '캐시미어'],
    [/\bpolyester\b/gi,               '폴리에스터'],
    [/\bspandex\b/gi,                 '스판'],
    // ── 컬러
    [/\bblack\b/gi,                   '블랙'],
    [/\bwhite\b/gi,                   '화이트'],
    [/\bbeige\b/gi,                   '베이지'],
    [/\bgr[ae]y\b/gi,                 '그레이'],
    [/\bnavy\b/gi,                    '네이비'],
    [/\bbrown\b/gi,                   '브라운'],
    [/\bivory\b/gi,                   '아이보리'],
    [/\bcamel\b/gi,                   '카멜'],
    [/\bmustard\b/gi,                 '머스타드'],
    [/\bkhaki\b/gi,                   '카키'],
    [/\bolive\b/gi,                   '올리브'],
    [/\bburgundy\b/gi,                '버건디'],
    [/\bwine\b/gi,                    '와인'],
    [/\bcream\b/gi,                   '크림'],
    [/\bpink\b/gi,                    '핑크'],
    [/\bred\b/gi,                     '레드'],
    [/\bblue\b/gi,                    '블루'],
    [/\bgreen\b/gi,                   '그린'],
    [/\byellow\b/gi,                  '옐로'],
    [/\bpurple\b/gi,                  '퍼플'],
    [/\borange\b/gi,                  '오렌지'],
    [/\bgold\b/gi,                    '골드'],
    [/\bsilver\b/gi,                  '실버'],
    // ── 스타일·무드
    [/\bcasual\b/gi,                  '캐주얼'],
    [/\bformal\b/gi,                  '포멀'],
    [/\bbasic\b/gi,                   '베이직'],
    [/\bvintage\b/gi,                 '빈티지'],
    [/\bminimal(?:ist)?\b/gi,         '미니멀'],
    [/\bstreetwear\b/gi,              '스트릿'],
    [/\bsporty\b/gi,                  '스포티'],
    [/\belegant\b/gi,                 '엘레강스'],
    [/\bclassy\b/gi,                  '클래식'],
    [/\bchic\b/gi,                    '시크'],
    [/\bcute\b/gi,                    '큐트'],
    [/\bcool\b/gi,                    '쿨'],
    [/\bstyling\b/gi,                 '스타일링'],
    [/\bcoordination\b/gi,            '코디'],
    [/\boutfit\b/gi,                  '코디'],
    [/\blook\b/gi,                    '룩'],
    [/\bTPO\b/g,                      '티피오'],
    [/\bSNS\b/g,                      '에스엔에스'],
    [/\bmixed\b/gi,                   '혼방'],
    [/\btexture\b/gi,                 '소재'],
    [/\bwarmth\b/gi,                  '보온'],
    [/\blayering\b/gi,                '레이어링'],
  ];

  /* ── 마크다운 → TTS 읽기용 순수 한국어 변환 ─── */
  function cleanText(md) {
    let t = md || '';
    // 이모지 제거
    t = t.replace(/[\u{1F600}-\u{1F64F}\u{1F300}-\u{1F5FF}\u{1F680}-\u{1F6FF}\u{1F1E0}-\u{1F1FF}\u{2600}-\u{27BF}\u{1F900}-\u{1F9FF}\u{1FA00}-\u{1FA6F}\u{1FA70}-\u{1FAFF}\u{2702}-\u{27B0}\u{FE00}-\u{FE0F}]/gu, '');
    // 마크다운 강조 기호 제거
    t = t.replace(/\*{1,3}|_{1,3}|~{2}|`{1,3}/g, '');
    // 헤더(#) 제거
    t = t.replace(/^#{1,6}\s*/gm, '');
    // 번호 목록 제거
    t = t.replace(/^\s*\d+\.\s+/gm, '');
    // 글머리 기호 제거
    t = t.replace(/^\s*[-+*•◦▪▸➤]\s+/gm, '');
    // 인용 블록 제거
    t = t.replace(/^\s*>\s*/gm, '');
    // 마크다운 링크 → 텍스트만
    t = t.replace(/\[([^\]]+)\]\([^)]+\)/g, '$1');
    // 이중/삼중 대시 → 공백
    t = t.replace(/-{2,}/g, ' ');
    // 각종 대시/구분자 → 공백 (TTS "대시" 방지)
    t = t.replace(/[-\u2013\u2014\u00B7\u30FB\uFF65·・•]/g, ' ');
    // 괄호·특수기호 제거
    t = t.replace(/[_|\\()\[\]{}<>@^%$&※°℃]/g, ' ');
    // 영어 → 한국어 변환
    for (const [pat, rep] of _EN_KO_JS) {
      t = t.replace(pat, rep);
    }
    // 변환 후 남은 영문자 전부 제거 (순수 한국어만 TTS로)
    t = t.replace(/[A-Za-z]+/g, '');
    // 줄바꿈 → 공백
    t = t.replace(/\n/g, ' ');
    // 연속 공백 정리
    t = t.replace(/\s{2,}/g, ' ');
    return t.trim();
  }

  /* ── TTS ─────────────────────────────────────── */
  function speak(text, onEnd) {
    if (!synth || !ttsEnabled || !text) { if (onEnd) onEnd(); return; }
    synth.cancel();
    const utter = new SpeechSynthesisUtterance(cleanText(text));
    utter.lang  = 'ko-KR';
    utter.rate  = 1.05;
    utter.pitch = 1.1;

    // 한국어 음성 우선 선택
    const voices = synth.getVoices();
    const kr = voices.find(v => v.lang === 'ko-KR') || voices.find(v => v.lang.startsWith('ko'));
    if (kr) utter.voice = kr;

    utter.onstart = () => { isSpeaking = true;  setUI('speaking'); };
    utter.onend   = () => { isSpeaking = false; setUI('idle');     if (onEnd) onEnd(); };
    utter.onerror = () => { isSpeaking = false; setUI('idle'); };
    synth.speak(utter);
  }

  function stopSpeaking() {
    synth && synth.cancel();
    isSpeaking = false;
    setUI('idle');
  }

  /* ── STT ─────────────────────────────────────── */
  function initRecog() {
    const R = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!R) return null;
    const r = new R();
    r.lang            = 'ko-KR';
    r.continuous      = false;
    r.interimResults  = false;

    r.onstart  = () => { isListening = true;  setUI('listening'); };
    r.onend    = () => { isListening = false; if (!isSpeaking) setUI('idle'); };
    r.onerror  = () => { isListening = false; setUI('idle'); };
    r.onresult = e => {
      const text = e.results[0][0].transcript;
      addLog(text, 'user');
      sendVoiceChat(text);
    };
    return r;
  }

  function toggleListen() {
    if (!recognition) recognition = initRecog();
    if (!recognition) {
      alert('음성 인식이 지원되지 않아요.\nChrome 또는 Edge 브라우저를 이용해 주세요.');
      setUI('idle');
      return;
    }
    if (isListening) {
      recognition.stop();
      setUI('idle');
    } else {
      if (isSpeaking) stopSpeaking();
      try {
        recognition.start();
        setUI('listening');
      } catch (e) {
        setUI('idle');
      }
    }
  }

  /* ── 음성 채팅 (/chat API 연결) ──────────────── */
  function sendVoiceChat(text) {
    setUI('thinking');
    const ctx = typeof chatContext !== 'undefined' ? chatContext : {};
    fetch('/chat', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ message: text, context: ctx })
    })
    .then(r => r.json())
    .then(d => {
      const reply = d.reply || '응답을 받지 못했어요.';
      addLog(reply, 'assistant');
      speak(reply);
    })
    .catch(() => {
      const err = '오류가 발생했어요. 다시 시도해 주세요.';
      addLog(err, 'assistant');
      speak(err);
    });
  }

  /* ── 팁 말풍선 (캐릭터 옆) ───────────────────── */
  function updateTips(comment) {
    const clean = cleanText(comment);
    // 문장 분리 후 적당한 길이만 추출
    const sentences = clean
      .split(/(?<=[.!?。])\s+/)
      .map(s => s.trim())
      .filter(s => s.length >= 14 && s.length <= 65);

    [0, 1, 2].forEach(i => {
      const el = document.getElementById('voiceTip' + i);
      if (!el) return;
      if (sentences[i]) {
        el.textContent = sentences[i];
        el.style.display = 'block';
        setTimeout(() => el.classList.add('visible'), i * 700 + 600);
      } else {
        el.style.display = 'none';
        el.classList.remove('visible');
      }
    });
  }

  /* ── 전문 텍스트 패널 ────────────────────────── */
  function setTextContent(html) {
    const el = document.getElementById('voiceTextBody');
    if (el) el.innerHTML = html;
  }

  function toggleTextPanel() {
    const panel = document.getElementById('voiceTextPanel');
    const btn   = document.getElementById('voiceTextBtn');
    if (!panel) return;
    const open = panel.classList.toggle('open');
    if (btn) btn.classList.toggle('active', open);
  }

  /* ── UI 상태 관리 ────────────────────────────── */
  function setUI(state) {
    const mic             = document.getElementById('voiceMicBtn');
    const status          = document.getElementById('voiceStatus');
    const designerNotice  = document.getElementById('designerVoiceProgress');
    const wave            = document.getElementById('voiceSpeakWave');
    const log             = document.getElementById('voiceChatLog');
    if (!mic) return;

    mic.classList.remove('listening', 'thinking', 'speaking');

    const labels = {
      listening: '대화 듣는 중...',
      thinking:  '대화 중...',
      speaking:  '말하는 중...',
      idle:      '대화 준비 완료',
    };
    if (state !== 'idle') mic.classList.add(state);
    if (designerNotice) designerNotice.textContent = labels[state] || labels.idle;
    if (status) status.textContent = labels[state] || labels.idle;
    if (wave)   wave.style.display = state === 'speaking' ? 'flex' : 'none';

    // 대화가 시작되면 로그 영역 표시
    if (log && (state === 'listening' || state === 'thinking')) {
      log.style.display = 'block';
    }
  }

  function addLog(text, role) {
    const log = document.getElementById('voiceChatLog');
    if (!log) return;
    log.style.display = 'block';
    const div = document.createElement('div');
    div.className = 'voice-log-' + role;
    if (role === 'assistant' && typeof marked !== 'undefined') {
      div.innerHTML = marked.parse(text);
    } else {
      div.textContent = text;
    }
    log.appendChild(div);
    log.scrollTop = log.scrollHeight;
  }

  /* ── 초기화 ──────────────────────────────────── */
  window.addEventListener('DOMContentLoaded', () => {
    recognition = initRecog();

    document.getElementById('voiceMicBtn')
      ?.addEventListener('click', toggleListen);

    document.getElementById('voiceStopBtn')
      ?.addEventListener('click', stopSpeaking);

    document.getElementById('voiceTextBtn')
      ?.addEventListener('click', toggleTextPanel);

    // voice.css가 없는 페이지에서는 아무것도 안 함
  });

  // 음성 목록 비동기 로딩 대응
  if (synth && typeof synth.onvoiceschanged !== 'undefined') {
    synth.onvoiceschanged = () => {};
  }

  /* ── Public API ──────────────────────────────── */
  window.VoiceEngine = {
    autoSpeak(comment) {
      lastComment = comment;
      updateTips(comment);
      setTimeout(() => speak(comment), 800);
    },
    setTextContent,
    toggleTextPanel,
    speak,
    stopSpeaking,
  };
})();
