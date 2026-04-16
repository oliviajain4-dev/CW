/* ── 패널 리사이즈 (8방향) ───────────────────── */
function initResizable(panel) {
  if (panel._resizable) return;
  panel._resizable = true;

  const handles = panel.querySelectorAll('.resize-handle');
  let resizing = false, dir = '', startX, startY, startW, startH, startL, startT;

  handles.forEach(handle => {
    handle.addEventListener('mousedown', e => {
      resizing = true;
      dir = handle.dataset.dir;
      startX = e.clientX; startY = e.clientY;
      startW = panel.offsetWidth; startH = panel.offsetHeight;
      const rect = panel.getBoundingClientRect();
      startL = rect.left; startT = rect.top;
      // left/top 고정 (right/bottom 기반이면 계산 꼬임)
      panel.style.left   = startL + 'px';
      panel.style.top    = startT  + 'px';
      panel.style.right  = 'auto';
      panel.style.bottom = 'auto';
      panel.style.transition = 'none';
      e.preventDefault();
      e.stopPropagation();
    });
  });

  document.addEventListener('mousemove', e => {
    if (!resizing) return;
    const dx = e.clientX - startX;
    const dy = e.clientY - startY;
    let w = startW, h = startH, l = startL, t = startT;

    const minW = parseInt(panel.style.minWidth  || panel.dataset.minW || 200);
    const minH = parseInt(panel.style.minHeight || panel.dataset.minH || 120);
    if (dir.includes('e')) w = Math.max(minW, startW + dx);
    if (dir.includes('s')) h = Math.max(minH, startH + dy);
    if (dir.includes('w')) { w = Math.max(minW, startW - dx); l = startL + startW - w; }
    if (dir.includes('n')) { h = Math.max(minH, startH - dy); t = startT + startH - h; }

    panel.style.width  = w + 'px';
    panel.style.height = h + 'px';
    panel.style.left   = l + 'px';
    panel.style.top    = t + 'px';
  });

  document.addEventListener('mouseup', () => {
    if (!resizing) return;
    resizing = false;
    panel.style.transition = '';
  });
}

/* ── 패널 드래그 ────────────────────────────── */
function initDraggable(panel) {
  const header = panel.querySelector('.panel-header');
  if (!header) return;
  let dragging = false, ox = 0, oy = 0;

  header.addEventListener('mousedown', e => {
    if (e.target.classList.contains('panel-close')) return;
    dragging = true;
    bringToFront(panel);
    const rect = panel.getBoundingClientRect();
    // 현재 위치를 left/top으로 고정 (right/bottom 해제)
    panel.style.left   = rect.left + 'px';
    panel.style.top    = rect.top  + 'px';
    panel.style.right  = 'auto';
    panel.style.bottom = 'auto';
    ox = e.clientX - rect.left;
    oy = e.clientY - rect.top;
    panel.style.transition = 'none';
    e.preventDefault();
  });

  document.addEventListener('mousemove', e => {
    if (!dragging) return;
    panel.style.left = (e.clientX - ox) + 'px';
    panel.style.top  = (e.clientY - oy) + 'px';
  });

  document.addEventListener('mouseup', () => {
    if (!dragging) return;
    dragging = false;
    panel.style.transition = '';
  });

  // 터치 지원
  header.addEventListener('touchstart', e => {
    if (e.target.classList.contains('panel-close')) return;
    dragging = true;
    const rect = panel.getBoundingClientRect();
    panel.style.left = rect.left + 'px'; panel.style.top = rect.top + 'px';
    panel.style.right = 'auto'; panel.style.bottom = 'auto';
    const t = e.touches[0];
    ox = t.clientX - rect.left; oy = t.clientY - rect.top;
    e.preventDefault();
  }, { passive: false });

  document.addEventListener('touchmove', e => {
    if (!dragging) return;
    const t = e.touches[0];
    panel.style.left = (t.clientX - ox) + 'px';
    panel.style.top  = (t.clientY - oy) + 'px';
  }, { passive: true });

  document.addEventListener('touchend', () => { dragging = false; });
}

/* ── 캐릭터 옷 입히기 ───────────────────────── */
const wornItems = { 상의: null, 하의: null, 아우터: null, 원피스: null };


function wearItem(el) {
  const category = el.dataset.category;
  const src      = el.dataset.src;
  if (!src || !category) return;

  if (category === '원피스') {
    const dressImg = document.getElementById('charDressImg');
    if (!dressImg) return;

    // 같은 아이템 다시 누르면 탈착
    if (wornItems['원피스'] === el) {
      dressImg.style.display = 'none';
      dressImg.src = '';
      el.classList.remove('worn');
      wornItems['원피스'] = null;
      if (window.meganResetColor) window.meganResetColor('원피스');
      return;
    }
    // 이전 원피스 해제
    if (wornItems['원피스']) wornItems['원피스'].classList.remove('worn');
    // 상의/하의 오버레이 숨기기 (원피스가 덮으므로)
    ['charTopImg','charBottomImg'].forEach(id => {
      const img = document.getElementById(id);
      if (img) { img.style.display = 'none'; img.src = ''; }
    });
    if (wornItems['상의']) { wornItems['상의'].classList.remove('worn'); wornItems['상의'] = null; }
    if (wornItems['하의']) { wornItems['하의'].classList.remove('worn'); wornItems['하의'] = null; }

    dressImg.src = src;
    dressImg.style.display = 'block';
    el.classList.add('worn');
    wornItems['원피스'] = el;
    if (window.meganApplyTexture) window.meganApplyTexture('원피스', src, el.dataset.texture || 'cotton');
    return;
  }

  const imgMap = { 상의: 'charTopImg', 하의: 'charBottomImg', 아우터: 'charOuterImg' };
  const imgEl  = document.getElementById(imgMap[category]);
  if (!imgEl) return;

  // 상의/하의 선택 시 원피스 탈착
  if ((category === '상의' || category === '하의') && wornItems['원피스']) {
    const dressImg = document.getElementById('charDressImg');
    if (dressImg) { dressImg.style.display = 'none'; dressImg.src = ''; }
    wornItems['원피스'].classList.remove('worn');
    wornItems['원피스'] = null;
    if (window.meganResetColor) window.meganResetColor('원피스');
  }

  // 같은 아이템 다시 누르면 탈착
  if (wornItems[category] === el) {
    imgEl.style.display = 'none';
    imgEl.src = '';
    el.classList.remove('worn');
    wornItems[category] = null;
    if (window.meganResetColor) window.meganResetColor(category);
    return;
  }

  // 이전 착용 아이템 강조 해제
  if (wornItems[category]) wornItems[category].classList.remove('worn');

  imgEl.src = src;
  imgEl.style.display = 'block';
  el.classList.add('worn');
  wornItems[category] = el;
  if (window.meganApplyTexture) window.meganApplyTexture(category, src, el.dataset.texture || 'cotton');
}

/* ── 패널 z-index 관리 (클릭한 패널이 최상단) ── */
let _panelZ = 250;
function bringToFront(panel) {
  _panelZ++;
  panel.style.zIndex = _panelZ;
}

/* ── 패널 토글 ──────────────────────────────── */
function togglePanel(id) {
  const panel = document.getElementById(id);
  if (!panel) return;
  const isOpen = panel.classList.contains('open');

  // 왼쪽 패널끼리는 하나만 열기 (같은 위치 겹치므로)
  const leftPanels = ['weatherPanel','stylePanel','itemPanel','designerPanel','shoppingPanel','calendarPanel'];
  if (leftPanels.includes(id)) {
    leftPanels.forEach(p => { if (p !== id) closePanel(p); });
  }
  // chatPanel, profilePanel 은 위치가 달라서 동시에 열 수 있음

  if (isOpen) {
    closePanel(id);
  } else {
    panel.classList.add('open');
    bringToFront(panel);
    // 처음 열릴 때 한 번만 드래그 초기화
    if (!panel._draggable) { initDraggable(panel); panel._draggable = true; }
    initResizable(panel);
    // 사이드바 버튼 active 표시
    const btnMap = {
      weatherPanel: 'btn-weather', stylePanel: 'btn-style',
      itemPanel: 'btn-item', designerPanel: 'btn-designer',
      shoppingPanel: 'btn-shopping',
      profilePanel: 'btn-profile',
      calendarPanel: 'btn-calendar'
    };
    const btn = document.getElementById(btnMap[id]);
    if (btn) btn.classList.add('active');
  }
}

function closePanel(id) {
  const panel = document.getElementById(id);
  if (!panel) return;
  panel.classList.remove('open');
  const btnMap = {
    weatherPanel: 'btn-weather', stylePanel: 'btn-style',
    itemPanel: 'btn-item', designerPanel: 'btn-designer',
    shoppingPanel: 'btn-shopping',
    profilePanel: 'btn-profile'
  };
  const btn = document.getElementById(btnMap[id]);
  if (btn) btn.classList.remove('active');
}

/* ── 이미지 미리보기 (다중 파일 지원) ──────────── */
const imageInput = document.getElementById("imageInput");
const previewImg = document.getElementById("previewImg");

if (imageInput) {
  imageInput.addEventListener("change", function () {
    const files = Array.from(this.files);
    if (!files.length) return;
    previewImg.style.display = "flex";
    previewImg.style.flexWrap = "wrap";
    previewImg.style.gap = "6px";
    previewImg.style.marginTop = "10px";
    previewImg.innerHTML = "";

    files.forEach(file => {
      const reader = new FileReader();
      reader.onload = (e) => {
        const img = document.createElement("img");
        img.src = e.target.result;
        img.style.cssText = "height:90px;width:90px;object-fit:cover;border-radius:8px;border:1px solid #f0c0d8;";
        previewImg.appendChild(img);
      };
      reader.readAsDataURL(file);
    });
  });
}

