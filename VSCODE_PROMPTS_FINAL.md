# VS Code Claude Code 최종 프롬프트 (3개)
> 순서대로 하나씩 실행. 각 프롬프트 완료 후 다음 것 실행.

---

## PROMPT 1 — voice/router.py 완성 (잘린 파일 복원)

```
voice/router.py 파일을 읽어봐. 238번 줄에서 파일이 잘려 있어.
FOLLOWUP section_prompt 중간에서 끊겼고, process_section() 함수 본문과
voice_ws() WebSocket 핸들러가 통째로 없어.

아래 스펙대로 238번 줄 이후를 완성해줘.

────────────────────────────────────────────────────────
1. FOLLOWUP section_prompt 완성 (잘린 문자열 이어붙이기)
────────────────────────────────────────────────────────
"사용자 말에 자연스럽게 먼저 반응하고, 필요하면 코디 수정이나 추가 팁을 줘. "
"날씨 얘기는 이미 했으니 반복하지 마. "
"제안 수락하면 짧게 마무리 후 추가 팁 하나. 질문은 한 번에 하나만. "
"2~3문장으로 끊어서 말해. 알파벳 금지."

────────────────────────────────────────────────────────
2. process_section(section, user_input="", forced=False) 함수 본문
────────────────────────────────────────────────────────
- nonlocal interrupted; interrupted = False
- context_str = _build_context_str(context)
- system_with_ctx = _VOICE_SYSTEM + "\n\n【현재 상황】\n" + context_str (context_str 있을 때)
- GREETING이면 section_prompts["GREETING"]를 system_with_ctx 끝에 추가 지시로 붙임
- call_messages 구성:
    * messages 복사본에서 시작
    * user_input 있으면 {"role":"user","content":user_input} 추가
    * call_messages가 비어있으면 {"role":"user","content":"시작해줘"} 추가
- await _set_state("processing")
- client = anthropic.Anthropic(api_key=os.getenv("CLAUDE_API_KEY"))
- client.messages.stream() 호출: model="claude-sonnet-4-6", max_tokens=_MAX_TOKENS
- await _set_state("speaking") — 스트림 시작 직후
- 스트림 청크마다:
    * interrupted 체크 → True면 즉시 return
    * buffer에 누적 → _SENTENCE_END로 문장 감지
    * 완성된 문장: clean_for_tts() → synthesize_speech() (executor에서 동기 실행)
    * pcm → base64 인코딩 → ws.send({"type":"audio_chunk","data":encoded})
- 스트림 종료 후 buffer 잔여 텍스트 처리 (동일 방식)
- interrupted=False 이면:
    * messages.append({"role":"assistant","content":full_text})
    * _send({"type":"response_text","text":full_text})
    * _send({"type":"done"})
    * _set_state("listening")
- asyncio.CancelledError 무시, 일반 Exception은 error 메시지 전송

────────────────────────────────────────────────────────
3. voice_ws() WebSocket 핸들러 본문 (@router.websocket("/ws") 아래)
────────────────────────────────────────────────────────
- await websocket.accept()
- 세션 상태 변수들 (context, state, current_task, ping_task, interrupted, messages, session) 선언
- 내부 헬퍼: _send(), _set_state(), _cancel_task(), _cancel_current(), _ping_loop()
  (파일 상단에 이미 선언된 함수들과 동일 패턴)
- ping_task = asyncio.create_task(_ping_loop()) 시작
- 메시지 루프 (try/finally):
    while True:
        raw = await websocket.receive_text()
        msg = json.loads(raw)
        msg_type = msg.get("type")

        if msg_type == "start_conversation":
            context = msg.get("context", {})
            profile = context.get("user_profile", {})
            session["user_name"] = profile.get("name", "")
            sens = profile.get("sensitivity", 3)
            session["sensitivity_label"] = _SENSITIVITY_MAP.get(int(sens), "보통")
            prev = msg.get("prev_messages", [])
            messages = list(prev) if prev else []
            await _cancel_current()
            current_task = asyncio.create_task(process_section("GREETING"))

        elif msg_type == "user_text":
            text = msg.get("text", "").strip()
            if not text:
                continue
            messages.append({"role": "user", "content": text})
            await _cancel_current()
            current_task = asyncio.create_task(
                process_section("FOLLOWUP", user_input=text)
            )

        elif msg_type == "barge_in":
            await _cancel_current()           ← 핵심: TTS 즉시 중단
            await _set_state("listening")

        elif msg_type == "end_conversation":
            break

- except WebSocketDisconnect: pass
- finally: _cancel_task(current_task), _cancel_task(ping_task)

────────────────────────────────────────────────────────
주의:
- chatbot/tts.py import: from chatbot.tts import _SENTENCE_END, clean_for_tts, synthesize_speech
- CLAUDE.md TTS 절대규칙 파일 (tts.py, voice.js) 절대 수정 금지
- app.py 절대 수정 금지
```

---

## PROMPT 2 — templates/dashboard.html barge-in 버그 수정

```
templates/dashboard.html 파일을 읽어봐.
Web Speech API 코드에서 말끊기(barge-in)가 안 되는 버그 3군데 고쳐줘.

────────────────────────────────────────────────────────
수정 1: recognition.onend — speaking 상태에서도 재시작 (핵심)
────────────────────────────────────────────────────────
현재:
  recognition.onend = () => {
    _recognizing = false;
    if (inVoice && serverState === 'listening') startRecognition();
  };

수정:
  recognition.onend = () => {
    _recognizing = false;
    if (inVoice && (serverState === 'listening' || serverState === 'speaking'))
      startRecognition();
  };

이유: TTS가 재생 중(speaking)일 때도 인식이 계속 돌아야 onspeechstart가 트리거돼서
     말끊기가 가능함. 현재는 speaking 상태에서 recognition이 꺼져 인사 멘트도 끊기지 않음.

────────────────────────────────────────────────────────
수정 2: recognition.onerror — 동일하게 speaking 포함
────────────────────────────────────────────────────────
현재:
  recognition.onerror = (e) => {
    _recognizing = false;
    if (e.error === 'no-speech' && inVoice && serverState === 'listening')
      startRecognition();
  };

수정:
  recognition.onerror = (e) => {
    _recognizing = false;
    if (e.error === 'no-speech' && inVoice &&
        (serverState === 'listening' || serverState === 'speaking'))
      startRecognition();
  };

────────────────────────────────────────────────────────
수정 3: recognition.onresult — confidence 낮은 노이즈 차단
────────────────────────────────────────────────────────
현재:
  recognition.onresult = (e) => {
    const text = e.results[0][0].transcript.trim();
    if (!text) return;
    ...
  };

수정 — text 검사 바로 아래 두 줄 추가:
  const conf = e.results[0][0].confidence ?? 1;
  if (conf < 0.4 || text.length < 2) return;

────────────────────────────────────────────────────────
주의: 딱 세 군데만 수정. 디자인/CSS/다른 JS 절대 건드리지 마.
```

---

## PROMPT 3 — chatbot/llm_client.py get_chatbot_response() 완성

```
chatbot/llm_client.py 파일을 읽어봐.
get_chatbot_response() 함수가 196번 줄에서 잘려 있어.
system_prompt 문자열 선언만 있고 실제 Claude API 호출 코드가 없어.

아래 스펙대로 완성해줘.

────────────────────────────────────────────────────────
get_chatbot_response() — system_prompt 이후 추가할 코드
────────────────────────────────────────────────────────

1. system_prompt 문자열 닫기
   현재 열려 있는 """ 제대로 닫기

2. context → system에 추가
   context_parts = []
   if context:
       if context.get("weather_label"):
           context_parts.append(f"오늘 날씨: {context['weather_label']}")
       if context.get("wardrobe"):
           items = [f"{i.get('category','')} {i.get('item_type','')}" for i in context["wardrobe"]]
           context_parts.append("옷장: " + ", ".join(items))
       if context.get("user_profile"):
           p = context["user_profile"]
           if p.get("name"): context_parts.append(f"이름: {p['name']}")
           if p.get("style_pref"): context_parts.append(f"선호 스타일: {p['style_pref']}")
   if context_parts:
       system_prompt += "\n\n【현재 상황】\n" + "\n".join(context_parts)

3. messages 구성
   msgs = list(history) if history else []
   msgs.append({"role": "user", "content": user_message})

4. Claude API 호출
   message = client.messages.create(
       model="claude-sonnet-4-6",
       max_tokens=800,
       system=system_prompt,
       messages=msgs,
   )

5. return message.content[0].text.strip()

────────────────────────────────────────────────────────
주의:
- get_outfit_comment() 함수는 건드리지 마
- CLAUDE.md TTS 절대규칙 섹션 (system_prompt 내 【TTS...】 주석) 수정 금지
- requirements.txt에 anthropic 이미 있는지 확인, 없으면 추가
```

---

## 실행 순서

1. **PROMPT 1** (router.py) → 서버 재시작 → 음성 연결 테스트
2. **PROMPT 2** (dashboard.html) → 브라우저 새로고침 → barge-in 테스트 (말하다가 끊기)
3. **PROMPT 3** (llm_client.py) → 텍스트 챗봇 테스트

## 테스트 체크리스트

- [ ] 마이크 ON → 인사 멘트 나오는 중 말하면 끊기는지
- [ ] 코디 추천 멘트 나오는 중 말하면 끊기는지
- [ ] 사용자 말 인식 후 AI가 tikitaka 대화 이어가는지
- [ ] 날씨가 인사 때 한 번만 나오는지 (FOLLOWUP에서 반복 안 하는지)
- [ ] 음성이 한국어로만 나오는지 (알파벳 없는지)
