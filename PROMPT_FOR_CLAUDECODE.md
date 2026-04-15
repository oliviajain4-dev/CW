# 내 옷장의 코디 — Claude Code 전체 작업 지시서 (최종)

> VS Code Claude Code에 이 파일 전체를 붙여넣어 실행하세요.
> **반드시 아래 파일들을 전부 직접 읽은 뒤 수정하세요. 읽지 않고 수정하면 기존 로직 파괴됨.**

---

## 📂 작업 전 필수 확인 — 전부 읽어라

- `voice/router.py`
- `templates/dashboard.html`
- `chatbot/llm_client.py`
- `static/js/voice.js`  ← 수정 금지, 구조 파악용
- `static/js/main.js`
- `static/css/style.css`
- `app.py`
- `CLAUDE.md`

---

## 🚫 절대 수정 금지

| 파일 | 보호 대상 |
|---|---|
| `static/js/voice.js` | `_EN_KO_JS` 테이블 전체, `cleanText()` 함수 |
| `chatbot/tts.py` | `_EN_KO` 테이블 전체, `clean_for_tts()` 함수 |
| `voice/router.py` | `_VOICE_SYSTEM` 안의 한국어 강제 규칙 (추가는 OK, 삭제 금지) |
| `app.py` | 기존 엔드포인트 삭제 금지 |

---

## ✅ Task 1: `chatbot/llm_client.py` — 파일 잘림 복구

**현상:** 파일이 197번째 줄에서 절단됨. `get_chatbot_response()` 함수 본문이 시스템 프롬프트 중간에서 잘려 있음.

파일 읽고 잘린 지점 확인 후, `get_chatbot_response()` 함수 전체를 아래로 교체:

```python
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
- 날씨 얘기는 맥락상 필요할 때만. 매 대화마다 날씨부터 꺼내지 마."""

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

    messages = list(history) if history else []
    messages.append({"role": "user", "content": user_message})

    message = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=800,
        system=system_prompt,
        messages=messages,
    )
    return message.content[0].text.strip()
```

---

## ✅ Task 2: `voice/router.py` — 티키타카 전면 개편

파일 전체 읽고 아래 변경 전부 적용.

### 2-1. SECTIONS 단순화

```python
SECTIONS = ["GREETING", "FOLLOWUP"]
```

### 2-2. section_prompts 교체

`process_section()` 안의 `section_prompts` dict를 아래로 교체:

```python
section_prompts = {
    "GREETING": (
        f"{'안녕, ' + session['user_name'] + '! ' if session['user_name'] else '안녕! '}"
        "다음 순서대로 자연스럽게 말해. "
        "① 이름을 불러주면서 짧고 친근하게 인사. "
        "② 오늘 날씨 — 아침/낮/저녁 체감온도를 자연스럽게 섞어서 한두 마디. '선선'은 절대 금지, 대신 '서늘', '쾌청', '포근', '살짝 쌀쌀' 등 다양하게. "
        "③ 오늘 추천 코디 — 옷장 아이템 이름 직접 언급하면서 구체적으로 제안. "
        "④ 선택지 제시: '이 코디로 할래? 아니면 오늘 다른 무드 원해?' "
        "문장은 2~3개씩 끊어서 말해. 질문은 마지막에 하나만."
    ),
    "FOLLOWUP": (
        "사용자 말에 자연스럽게 먼저 반응하고, 필요하면 코디 수정이나 추가 팁을 줘. "
        "날씨 얘기는 이미 했으니 반복하지 마. "
        "사용자가 코디 수락하면 짧게 마무리하고 팁 하나 더 줘. "
        "사용자가 다른 스타일 원하면 옷장 기반으로 다시 제안. "
        "같은 말 반복 절대 금지."
    ),
}
```

### 2-3. FOLLOWUP 날씨 prepend 제거

현재:
```python
if section in ["WEATHER", "PROPOSAL", "FOLLOWUP"] and weather_label:
    task_prompt = f"현재 날씨 정보: {weather_label}. \n" + task_prompt
```

변경 — GREETING에만 날씨 prepend:
```python
if section == "GREETING" and weather_label:
    task_prompt = f"현재 날씨 정보: {weather_label}. \n" + task_prompt
```

### 2-4. assistant 응답 messages[]에 저장

`process_section()` 스트리밍 완료 후 full_text 저장 추가:
```python
# 스트리밍 루프 끝, done 전송 전
if full_text.strip():
    messages.append({"role": "assistant", "content": full_text.strip()})
```

### 2-5. user_text 수신 → 항상 FOLLOWUP 처리

```python
elif msg_type == "user_text":
    text = data.get("text", "").strip()
    if not text:
        continue
    await _cancel_current()
    current_task = asyncio.create_task(
        process_section("FOLLOWUP", user_input=text)
    )
```

### 2-6. _build_context_str() — 날씨 상세 추가

기존 함수 전체를 아래로 교체:

```python
def _build_context_str(context: Optional[dict]) -> str:
    if not context:
        return ""
    lines = []

    wardrobe = context.get("wardrobe", [])
    if wardrobe:
        items = [f"  {i.get('category','')}: {i.get('item_type','')}" for i in wardrobe]
        lines.append("내 옷장\n" + "\n".join(items))

    weather       = context.get("weather", {})
    weather_label = context.get("weather_label", "")
    if weather_label or weather:
        w_lines = []
        if weather_label:
            w_lines.append(f"  날씨 요약: {weather_label}")
        if weather:
            mo = weather.get("morning",   {})
            af = weather.get("afternoon", {})
            ev = weather.get("evening",   {})
            if mo.get("feels_like") is not None:
                w_lines.append(
                    f"  체감: 아침 {mo['feels_like']}°C / "
                    f"낮 {af.get('feels_like','?')}°C / "
                    f"저녁 {ev.get('feels_like','?')}°C"
                )
            if mo.get("reh") is not None:
                w_lines.append(f"  습도: {mo['reh']}%")
        lines.append("오늘 날씨\n" + "\n".join(w_lines))

    profile = context.get("user_profile", {})
    if profile:
        pl = []
        if profile.get("name"):       pl.append(f"이름: {profile['name']}")
        if profile.get("height"):     pl.append(f"키: {profile['height']}cm")
        if profile.get("body_type"):  pl.append(f"체형: {profile['body_type']}")
        if profile.get("style_pref"): pl.append(f"선호 스타일: {profile['style_pref']}")
        if profile.get("gender"):     pl.append(f"성별: {profile['gender']}")
        sens = profile.get("sensitivity")
        if sens:
            sm = {1:"추위를 많이 타는 편",2:"약간 추위 타는 편",3:"보통",
                  4:"약간 더위 타는 편",5:"더위를 많이 타는 편"}
            pl.append(f"추위 민감도: {sm.get(int(sens),'보통')}")
        if pl:
            lines.append("사용자 정보\n  " + "\n  ".join(pl))

    return "\n".join(lines) + "\n" if lines else ""
```

### 2-7. _VOICE_SYSTEM 끝에 다양성 지시 추가

`_VOICE_SYSTEM` 문자열 마지막 `"""` 바로 앞에 아래 추가
(한국어 강제 규칙 절대 삭제 금지):

```
다양한 날씨 표현을 써라. '선선'은 절대 금지. '서늘', '쾌청', '포근', '살짝 쌀쌀', '제법 따뜻' 등 번갈아 사용.
같은 표현 두 번 이상 연속 금지.
문장은 2~3개씩 끊어서 말해라. 질문은 한 번에 하나만.
코디 제안 후 반드시 선택지 줘라: '이 코디로 할래? 아니면 다른 스타일 원해?'
날씨 언급은 GREETING에서 1번만. 이후 대화에서 날씨 반복 금지.
```

### 2-8. start_conversation — prev_messages 수신 + pending_sections 단순화

```python
if msg_type == "start_conversation":
    context = data.get("context", {})
    prev = data.get("prev_messages", [])
    if prev and isinstance(prev, list):
        messages.extend(prev[-20:])
    profile = context.get("user_profile", {})
    session["user_name"]         = profile.get("name", "")
    sens_raw                     = profile.get("sensitivity", 3)
    session["sensitivity_label"] = _SENSITIVITY_MAP.get(int(sens_raw), "보통")
    pending_sections             = ["GREETING"]
    ping_task    = asyncio.create_task(_ping_loop())
    current_task = asyncio.create_task(process_section("GREETING"))
```

---

## ✅ Task 3: `templates/dashboard.html` — UI 전면 개편

파일 전체 읽고 아래 변경 전부 적용.

### 3-1. voiceStartBtn / voiceStopBtn 완전 삭제

디자이너 패널 헤더에서 아래 두 버튼 HTML 완전히 제거:
```html
<button id="voiceStartBtn" ...>...</button>
<button id="voiceStopBtn"  ...>...</button>
```

패널 헤더는 타이틀 + ✕ 닫기버튼만 남겨라:
```html
<div class="panel-header" id="designerPanelHeader">
  <span class="designer-panel-title">
    <span class="designer-emoji">👨‍🎨</span> 수석 디자이너
  </span>
  <button class="panel-close" onclick="closePanel('designerPanel')">✕</button>
</div>
```

### 3-2. voice-bar 마이크 버튼 → "대화시작" / "대화종료" 텍스트로

`#voiceMicBtn` 버튼의 초기 텍스트를 "💬 대화시작"으로 변경:
```html
<button id="voiceMicBtn" class="voice-mic-btn" title="대화 시작/종료">💬 대화시작</button>
```

`updateUI()` 함수 안에서 micBtn 텍스트를 상태에 따라 변경:
```javascript
micBtn.textContent = inVoice ? '⏹ 대화종료' : '💬 대화시작';
micBtn.classList.toggle('voice-on',  inVoice);
micBtn.classList.toggle('voice-off', !inVoice);
```

### 3-3. designerVoiceStatus — off 상태 텍스트 제거 + 스타일 크게

`updateUI()` 안의 labels 'off' 값을 빈 문자열로:
```javascript
const labels = {
    off:        '',
    listening:  '🎙 듣는 중...',
    processing: '💭 생각하는 중...',
    speaking:   '🔊 말하는 중...',
};
```

`#designerVoiceStatus` 인라인 스타일 교체:
```html
<div id="designerVoiceStatus" style="
  font-size:16px;font-weight:700;color:#7755aa;text-align:center;
  padding:6px 12px;min-height:0;flex-shrink:0;
  background:rgba(119,85,170,0.07);border-radius:10px;
  margin:4px 0;letter-spacing:0.02em;
  transition:all 0.2s;
"></div>
```

### 3-4. 더블링 방지 — fillDesignerPanel에서 마이크 ON 시 자동 TTS 건너뛰기

`fillDesignerPanel()` 함수 안의 `/api/tts` fetch 블록을 아래로 교체:
```javascript
// 마이크 OFF 상태일 때만 자동 읽기 (마이크 ON이면 voice chat이 읽어줌)
if (!inVoice) {
    fetch('/api/tts', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text: comment })
    })
    .then(r => r.json())
    .then(data => { if (data.audio) enqueuePCM(data.audio); })
    .catch(() => {
        if (typeof VoiceEngine !== 'undefined') VoiceEngine.autoSpeak(comment);
    });
}
```

### 3-5. 마이크 ON 시 기존 오디오 중단 (더블링 방지 2)

micBtn 클릭 이벤트에서 `inVoice = true` 직전에 `stopAudio()` 호출:
```javascript
// 마이크 ON 분기 안에서, fetch 시작 전
stopAudio();  // 디자이너 패널 자동 읽기 중단
```

### 3-6. voiceStartBtn/StopBtn 관련 JS 이벤트 리스너 삭제

HTML에서 버튼을 삭제했으니, JS 안에 남아있는 아래 코드도 삭제:
```javascript
// 아래 블록 전부 찾아서 삭제
const startBtn = document.getElementById('voiceStartBtn');
const stopBtn  = document.getElementById('voiceStopBtn');
if (startBtn) { startBtn.addEventListener('click', ...) }
if (stopBtn)  { stopBtn.addEventListener('click', ...) }
```

대신 stopVoiceSession 호출은 micBtn 토글(OFF 분기)에서만 처리:
```javascript
// micBtn.click() OFF 분기 — 그대로 유지하되 _savedMessages 초기화 추가
} else {
    _savedMessages = [];
    inVoice     = false;
    serverState = 'idle';
    updateUI('off');
    if (recognition) { try { recognition.stop(); } catch (_) {} recognition = null; }
    stopAudio();
    if (ws?.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ type: 'end_conversation' }));
        ws.close();
    }
    ws = null;
    if (reconnTimer) { clearTimeout(reconnTimer); reconnTimer = null; }
}
```

### 3-7. _savedMessages — 재연결 시 대화 기억 유지

IIFE 밖 window 레벨에 선언 (스크립트 최상단, `(function() {` 전):
```javascript
let _savedMessages = [];
```

`connectWS()` 안 `ws.onopen`:
```javascript
ws.onopen = () => {
    if (inVoice) {
        ws.send(JSON.stringify({
            type: 'start_conversation',
            context: buildCtx(),
            prev_messages: _savedMessages,
        }));
    }
};
```

`addLog()` 안에서 designerChatWindow에 추가 전:
```javascript
_savedMessages.push({ role: (role === 'assistant' ? 'assistant' : 'user'), content: text });
if (_savedMessages.length > 20) _savedMessages = _savedMessages.slice(-20);
```

### 3-8. buildCtx() — weather 상세 추가

```javascript
function buildCtx() {
    const c = (typeof chatContext !== 'undefined') ? chatContext : {};
    return {
        wardrobe:      c.wardrobe      || [],
        weather_label: c.weather_label || '',
        weather:       c.weather       || {},
        tpo:           c.tpo           || '일상',
        user_profile:  c.user_profile  || {},
    };
}
```

### 3-9. recognition 중복 시작 방지

IIFE 상단 변수 선언부에 추가:
```javascript
let _recognizing = false;
```

`setupRecognition()` 안:
```javascript
recognition.onstart = () => { _recognizing = true; };
recognition.onend   = () => {
    _recognizing = false;
    if (inVoice && serverState === 'listening') startRecognition();
};
recognition.onerror = (e) => {
    _recognizing = false;
    if (e.error === 'no-speech' && inVoice && serverState === 'listening')
        startRecognition();
};
```

`startRecognition()`:
```javascript
function startRecognition() {
    if (!recognition || !inVoice || _recognizing) return;
    try { recognition.start(); } catch (_) {}
}
```

`ws.onmessage`에서 state listening 처리:
```javascript
if (msg.value === 'listening') {
    updateUI('listening');
    if (!_recognizing) startRecognition();
}
```

---

## ✅ Task 4: `templates/dashboard.html` — Musinsa 링크 → 이모지 카드

`addLog()` 함수 바로 위에 `buildShopCards()` 함수 추가:

```javascript
function buildShopCards(text) {
    const linkRe = /\[([^\]]+)\]\((https?:\/\/[^)]*musinsa[^)]*)\)/g;
    const cards  = [];
    let m;
    while ((m = linkRe.exec(text)) !== null) cards.push({ name: m[1], url: m[2] });
    if (!cards.length) return null;

    const CAT_MAP = {
        상의:   { emoji: '👕', color: '#f472b6' },
        하의:   { emoji: '👖', color: '#60a5fa' },
        아우터: { emoji: '🧥', color: '#fb923c' },
        신발:   { emoji: '👟', color: '#4ade80' },
        가방:   { emoji: '👜', color: '#a78bfa' },
    };
    function guessCategory(name) {
        if (/티셔츠|맨투맨|후드|셔츠|니트|블라우스|가디건|크롭/.test(name)) return '상의';
        if (/청바지|슬랙스|팬츠|스커트|반바지|바지|데님/.test(name))        return '하의';
        if (/코트|재킷|자켓|점퍼|패딩|바람막이|트렌치|아우터/.test(name))   return '아우터';
        if (/스니커즈|신발|부츠|로퍼|샌들|슬리퍼|힐|운동화/.test(name))     return '신발';
        if (/가방|백팩|숄더|크로스|토트|클러치/.test(name))                  return '가방';
        return null;
    }

    const wrap = document.createElement('div');
    wrap.style.cssText = 'display:flex;gap:8px;margin-top:8px;overflow-x:auto;padding-bottom:4px;';

    cards.forEach(({ name, url }) => {
        const cat = guessCategory(name);
        const { emoji, color } = CAT_MAP[cat] || { emoji: '🛍', color: '#a78bfa' };
        const card = document.createElement('a');
        card.href   = url; card.target = '_blank'; card.rel = 'noopener';
        card.style.cssText = [
            'display:flex','flex-direction:column','align-items:center',
            'width:72px','flex-shrink:0','text-decoration:none',
            'background:rgba(255,255,255,0.04)',
            'border:1px solid rgba(255,255,255,0.1)',
            'border-radius:12px','padding:8px 4px 6px','gap:4px',
            'transition:background 0.15s','cursor:pointer',
        ].join(';');
        card.addEventListener('mouseover', () => { card.style.background = color + '22'; });
        card.addEventListener('mouseout',  () => { card.style.background = 'rgba(255,255,255,0.04)'; });

        const emojiEl = document.createElement('div');
        emojiEl.style.cssText = `font-size:22px;width:42px;height:42px;border-radius:10px;background:${color}33;display:flex;align-items:center;justify-content:center;`;
        emojiEl.textContent = emoji;

        const nameEl = document.createElement('div');
        nameEl.style.cssText = 'font-size:9px;color:#ccc;text-align:center;line-height:1.3;max-width:64px;overflow:hidden;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;';
        nameEl.textContent = name;

        const badge = document.createElement('div');
        badge.style.cssText = `font-size:8px;color:${color};font-weight:700;`;
        badge.textContent = '무신사 →';

        card.append(emojiEl, nameEl, badge);
        wrap.appendChild(card);
    });
    return wrap;
}
```

`addLog()` 안에서 `win.appendChild(div)` 다음에:
```javascript
const shopCards = buildShopCards(text);
if (shopCards) win.appendChild(shopCards);
win.scrollTop = win.scrollHeight;
```

---

## ✅ Task 5: `static/css/style.css` — 패널 초기 크기 + 마이크 버튼 스타일

`#designerPanel` 크기 확인, 없으면 추가:
```css
#designerPanel {
    width: 460px !important;
    min-width: 320px;
    height: 560px !important;
    min-height: 300px;
}
```

`#voiceMicBtn` — 텍스트 버튼으로 스타일 조정 (기존 이모지 크기 대신 텍스트 가독성):
```css
#voiceMicBtn {
    font-size: 13px !important;
    padding: 6px 14px !important;
    border-radius: 20px !important;
    min-width: 90px;
    letter-spacing: 0.02em;
}
```

---

## 📋 완료 후 검증 체크리스트

1. `llm_client.py` — 파일 끝에 `return message.content[0].text.strip()` 있는지
2. `router.py` — messages[]에 assistant 응답 저장하는 코드 있는지
3. `router.py` — FOLLOWUP 처리에 날씨 prepend 없는지
4. `dashboard.html` — `voiceStartBtn`, `voiceStopBtn` HTML + JS 이벤트 리스너 전부 삭제됐는지
5. `dashboard.html` — `micBtn.textContent` 가 inVoice 상태에 따라 변경되는지
6. `dashboard.html` — `fillDesignerPanel()` 안에 `if (!inVoice)` 가드 있는지
7. `dashboard.html` — micBtn ON 분기에 `stopAudio()` 호출 있는지
8. `dashboard.html` — `_savedMessages`가 IIFE 밖에 선언됐는지
9. `dashboard.html` — `_recognizing` flag + `startRecognition()` guard 있는지
10. `dashboard.html` — `buildShopCards()` 함수 있고 `addLog()`에서 호출하는지
11. `dashboard.html` — `updateUI()` labels에서 `off: ''` (빈 문자열)인지
12. `voice.js` — `_EN_KO_JS`, `cleanText()` 변경 안 됐는지
13. `chatbot/tts.py` — `_EN_KO`, `clean_for_tts()` 변경 안 됐는지
14. `requirements.txt` — 새 패키지 추가 없음 (변경 불필요)

---

## ⚠️ 주의사항

- `micBtn` 토글 ON/OFF 로직 자체는 기존 구조 유지. 텍스트와 `_savedMessages` 초기화만 추가.
- `_savedMessages` 반드시 IIFE 밖 선언. IIFE 안에 넣으면 reconnect 때 초기화됨.
- `process_section()` 에서 `full_text` 비어있으면 messages에 추가하지 마.
- 파일별로 수정 완료 후 "어느 줄을 어떻게 바꿨는지" 정리해서 알려줘.
