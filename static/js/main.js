/* ── 이미지 미리보기 ──────────────────────────── */
const imageInput = document.getElementById("imageInput");
const previewImg = document.getElementById("previewImg");

if (imageInput) {
  imageInput.addEventListener("change", function () {
    const file = this.files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (e) => {
      previewImg.style.display = "block";
      previewImg.innerHTML = `<img src="${e.target.result}" alt="미리보기">`;
    };
    reader.readAsDataURL(file);
  });
}

/* ── 챗봇 ────────────────────────────────────── */
const chatWindow = document.getElementById("chatWindow");
const chatInput  = document.getElementById("chatInput");
const chatSend   = document.getElementById("chatSend");

function appendMsg(text, role) {
  if (!chatWindow) return;
  const div = document.createElement("div");
  div.className = `chat-msg ${role}`;
  div.innerHTML = text.replace(/\n/g, "<br>");
  chatWindow.appendChild(div);
  chatWindow.scrollTop = chatWindow.scrollHeight;
}

function sendChat() {
  if (!chatInput || !chatInput.value.trim()) return;
  const msg = chatInput.value.trim();
  chatInput.value = "";
  appendMsg(msg, "user");

  // 로딩 표시
  const loadingDiv = document.createElement("div");
  loadingDiv.className = "chat-msg assistant";
  loadingDiv.textContent = "...";
  loadingDiv.id = "loading";
  chatWindow.appendChild(loadingDiv);
  chatWindow.scrollTop = chatWindow.scrollHeight;

  fetch("/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      message: msg,
      context: typeof chatContext !== "undefined" ? chatContext : {}
    })
  })
    .then((r) => r.json())
    .then((data) => {
      document.getElementById("loading")?.remove();
      appendMsg(data.reply || "(응답 없음)", "assistant");
    })
    .catch((err) => {
      document.getElementById("loading")?.remove();
      appendMsg("오류가 발생했어요. 다시 시도해주세요.", "assistant");
    });
}

if (chatSend) chatSend.addEventListener("click", sendChat);
if (chatInput) {
  chatInput.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendChat();
    }
  });
}
