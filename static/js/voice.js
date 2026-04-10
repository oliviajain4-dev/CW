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

  /* ── 마크다운 → 읽기 텍스트 변환 ────────────── */
  function cleanText(md) {
    return (md || '')
      .replace(/#{1,6} /g, '')
      .replace(/\*\*|__|\*|_|`/g, '')
      .replace(/\[([^\]]+)\]\([^)]+\)/g, '$1')
      .replace(/\n{2,}/g, ' ')
      .trim();
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
      return;
    }
    if (isListening) {
      recognition.stop();
      setUI('idle');
    } else {
      if (isSpeaking) stopSpeaking();
      try { recognition.start(); } catch (e) { /* 이미 시작된 경우 무시 */ }
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
    const mic    = document.getElementById('voiceMicBtn');
    const status = document.getElementById('voiceStatus');
    const wave   = document.getElementById('voiceSpeakWave');
    const log    = document.getElementById('voiceChatLog');
    if (!mic) return;

    mic.classList.remove('listening', 'thinking', 'speaking');

    const labels = {
      listening: '듣고 있어요... (다시 누르면 중단)',
      thinking:  '생각 중...',
      speaking:  '말하는 중... (마이크 눌러 끊기)',
      idle:      '🎙 마이크를 눌러 말해보세요',
    };
    if (state !== 'idle') mic.classList.add(state);
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

    document.getElementById('voiceReplayBtn')
      ?.addEventListener('click', () => { if (lastComment) speak(lastComment); });

    document.getElementById('voiceTtsToggle')
      ?.addEventListener('click', function () {
        ttsEnabled = !ttsEnabled;
        this.textContent = ttsEnabled ? '🔊' : '🔇';
        if (!ttsEnabled) stopSpeaking();
      });

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
