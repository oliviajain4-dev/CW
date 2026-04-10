# -*- coding: utf-8 -*-
"""
내 옷장의 코디 — 기술 스택 흐름도 (2D)
diagrams + Graphviz 기반 전문 아이콘 다이어그램
"""
import os, sys, io
os.environ["PATH"] += r";C:\Program Files\Graphviz\bin"

import requests as _req

# 출력 폴더: 이 파일(make_flowchart.py)은 CW 루트에 위치하지만
# 생성되는 모든 산출물은 flowchart/ 폴더 안에 저장
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "flowchart")
os.makedirs(OUTPUT_DIR, exist_ok=True)

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch, Circle, FancyArrowPatch
from matplotlib.offsetbox import AnnotationBbox, OffsetImage
import matplotlib.patheffects as pe
import numpy as np
from PIL import Image, ImageDraw, ImageFont

plt.rcParams['font.family'] = 'Malgun Gothic'
plt.rcParams['axes.unicode_minus'] = False

_LOGO_CACHE = {}

def get_logo(url, size=140, bg='#ffffff', shape='circle'):
    """
    Icons8 등 CDN에서 PNG 로고를 다운로드해 원형/라운드 배경 위에 합성.
    실패 시 None 반환.
    """
    if url in _LOGO_CACHE:
        raw = _LOGO_CACHE[url]
    else:
        try:
            r = _req.get(url, timeout=6, headers={'User-Agent': 'Mozilla/5.0'})
            r.raise_for_status()
            raw = r.content
            _LOGO_CACHE[url] = raw
        except Exception:
            return None

    try:
        logo = Image.open(io.BytesIO(raw)).convert('RGBA')
    except Exception:
        return None

    # 캔버스 생성
    canvas = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(canvas)

    # 배경 도형
    rv, gv, bv = int(bg[1:3],16), int(bg[3:5],16), int(bg[5:7],16)
    shadow = (max(0,rv-35), max(0,gv-35), max(0,bv-35), 200)
    fill   = (rv, gv, bv, 240)
    if shape == 'circle':
        d.ellipse([4, 4, size-4, size-4], fill=shadow)
        d.ellipse([2, 2, size-6, size-6], fill=fill)
    else:
        d.rounded_rectangle([4, 4, size-4, size-4], radius=24, fill=shadow)
        d.rounded_rectangle([2, 2, size-6, size-6], radius=22, fill=fill)

    # 로고 크기 조정 후 중앙 붙여넣기
    pad = int(size * 0.18)
    logo_size = size - pad * 2
    logo = logo.resize((logo_size, logo_size), Image.LANCZOS)
    canvas.paste(logo, (pad, pad), logo)

    return np.array(canvas)


def make_icon(label, color, size=120, text_color='white', shape='circle', sub=''):
    """PIL로 아이콘 PNG 생성 → numpy array 반환"""
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)

    r, g, b = int(color[1:3], 16), int(color[3:5], 16), int(color[5:7], 16)
    shadow = (max(0, r-40), max(0, g-40), max(0, b-40), 220)
    fill   = (r, g, b, 230)

    if shape == 'circle':
        d.ellipse([4, 4, size-4, size-4], fill=shadow)
        d.ellipse([2, 2, size-6, size-6], fill=fill)
    else:
        d.rounded_rectangle([4, 4, size-4, size-4], radius=22, fill=shadow)
        d.rounded_rectangle([2, 2, size-6, size-6], radius=20, fill=fill)

    # 텍스트
    try:
        font_big = ImageFont.truetype(r"C:\Windows\Fonts\malgunbd.ttf", 24)
        font_sm  = ImageFont.truetype(r"C:\Windows\Fonts\malgun.ttf", 13)
    except:
        font_big = ImageFont.load_default()
        font_sm  = font_big

    cx, cy = size//2, size//2 - (8 if sub else 0)
    # 흰 그림자 효과
    for dx, dy in [(-1,-1),(1,-1),(-1,1),(1,1)]:
        d.text((cx+dx, cy+dy), label, fill=(0,0,0,120),
               font=font_big, anchor='mm')
    d.text((cx, cy), label, fill=text_color, font=font_big, anchor='mm')

    if sub:
        d.text((cx, cy+22), sub, fill=(255,255,255,200),
               font=font_sm, anchor='mm')

    return np.array(img)


def draw_node(ax, cx, cy, icon_arr, title, sub='', icon_size=0.55):
    """노드 배치: 아이콘 + 아래 텍스트"""
    img = OffsetImage(icon_arr, zoom=icon_size)
    ab  = AnnotationBbox(img, (cx, cy), frameon=False, zorder=4)
    ax.add_artist(ab)
    ax.text(cx, cy - 0.72, title,
            ha='center', va='top', fontsize=9.5, fontweight='bold',
            color='#1a1a2e', zorder=5)
    if sub:
        ax.text(cx, cy - 1.05, sub,
                ha='center', va='top', fontsize=7.5,
                color='#636e72', zorder=5)


def draw_arrow(ax, x1, y1, x2, y2, label='', color='#2d3436', style='->',
               rad=0.0, lw=1.8):
    ax.annotate('', xy=(x2, y2), xytext=(x1, y1),
                arrowprops=dict(
                    arrowstyle=style, color=color, lw=lw,
                    connectionstyle=f'arc3,rad={rad}',
                    shrinkA=28, shrinkB=28),
                zorder=3)
    if label:
        mx = (x1+x2)/2
        my = (y1+y2)/2
        off_x = 0.15 if rad == 0 else 0.3 * rad / abs(rad)
        off_y = 0.18 if x1 != x2 else 0
        ax.text(mx + off_x, my + off_y, label,
                ha='center', va='center', fontsize=7.5,
                color=color, fontweight='bold',
                bbox=dict(boxstyle='round,pad=0.15', fc='white',
                          ec=color, alpha=0.85, lw=0.8),
                zorder=6)


def draw_cluster_bg(ax, x, y, w, h, color, title):
    """배경 클러스터 박스"""
    rect = FancyBboxPatch((x, y), w, h,
                          boxstyle='round,pad=0.1,rounding_size=0.3',
                          facecolor=color, edgecolor=color,
                          linewidth=2, alpha=0.10, zorder=0)
    ax.add_patch(rect)
    # 테두리만
    rect2 = FancyBboxPatch((x, y), w, h,
                           boxstyle='round,pad=0.1,rounding_size=0.3',
                           facecolor='none', edgecolor=color,
                           linewidth=1.5, alpha=0.35, zorder=1,
                           linestyle='--')
    ax.add_patch(rect2)
    ax.text(x + 0.22, y + h - 0.18, title,
            fontsize=8, color=color, alpha=0.9,
            fontweight='bold', zorder=2)


def build():
    # ── 아이콘 생성 ────────────────────────────────────
    icons = {
        'user':    make_icon('USER',    '#00b894', sub='Browser'),
        'flask':   make_icon('Flask',   '#1a1a2e', sub='app.py',   shape='round'),
        'kma':     make_icon('KMA',     '#0984e3', sub='날씨API'),
        'mapper':  make_icon('MAP',     '#f39c12', sub='매핑'),
        'claude':  make_icon('Claude',  '#d35400', sub='AI'),
        'chatbot': make_icon('CHAT',    '#e84393', sub='챗봇'),
        'siglip':  make_icon('CLIP',    '#6c5ce7', sub='Marqo'),
        'upload':  make_icon('IMG',     '#a29bfe', sub='Upload'),
        'db':      make_icon('db.py',   '#00cec9', sub='전환', shape='round'),
        'pg':      make_icon('PG',      '#336791', sub='PostgreSQL'),
        'docker':  make_icon('Docker',  '#2496ed', sub='Compose', shape='round'),
        'env':     make_icon('.env',    '#636e72', sub='API Key',  shape='round'),
        'git':     make_icon('Git',     '#f05032', sub='GitHub',   shape='round'),
    }

    # ── 레이아웃 ────────────────────────────────────────
    fig, ax = plt.subplots(figsize=(22, 14))
    fig.patch.set_facecolor('#f8f9fa')
    ax.set_facecolor('#f8f9fa')
    ax.set_xlim(0, 22)
    ax.set_ylim(0, 14)
    ax.axis('off')

    # 클러스터 배경
    draw_cluster_bg(ax, 0.4, 10.4, 21.2, 3.3,  '#00b894', '사용자 / 웹 레이어')
    draw_cluster_bg(ax, 0.4,  6.8, 10.4, 3.3,  '#0984e3', '날씨 처리')
    draw_cluster_bg(ax, 11.2, 6.8, 10.4, 3.3,  '#e84393', 'AI 추천 엔진')
    draw_cluster_bg(ax, 0.4,  3.2, 10.4, 3.3,  '#6c5ce7', '옷장 AI 분석')
    draw_cluster_bg(ax, 11.2, 3.2, 10.4, 3.3,  '#00cec9', '데이터 레이어')
    draw_cluster_bg(ax, 0.4,  0.2, 21.2, 2.7,  '#2496ed', '인프라 (Docker 환경)')

    # ── 노드 배치 (cx, cy) ──────────────────────────────
    #  [사용자 레이어]
    draw_node(ax,  2.5, 12.1, icons['user'],    '사용자',        'localhost:5000')
    draw_node(ax,  8.5, 12.1, icons['flask'],   'Flask',         'app.py 라우터')
    draw_node(ax, 15.0, 12.1, icons['flask'],   'Flask',         'API / 세션 처리',  icon_size=0.45)
    draw_node(ax, 20.5, 12.1, icons['git'],     'GitHub',        '소스 관리')

    # [날씨 처리]
    draw_node(ax,  3.0,  8.4, icons['kma'],    '기상청 API',    'apis.data.go.kr')
    draw_node(ax,  8.5,  8.4, icons['mapper'], '날씨-코디 매핑','weather_style_mapper')

    # [AI 추천]
    draw_node(ax, 13.5,  8.4, icons['claude'], 'Claude AI',     'claude-opus-4-6')
    draw_node(ax, 19.5,  8.4, icons['chatbot'],'챗봇',          '수석 디자이너')

    # [옷장 분석]
    draw_node(ax,  3.0,  4.8, icons['upload'], '이미지 업로드', '/wardrobe/add')
    draw_node(ax,  8.5,  4.8, icons['siglip'], 'FashionSigLIP', 'Marqo 분류 모델')

    # [데이터 레이어]
    draw_node(ax, 13.5,  4.8, icons['db'],     'db.py',         'PG/SQLite 자동전환')
    draw_node(ax, 19.5,  4.8, icons['pg'],     'PostgreSQL 15', 'style/weather_logs')

    # [인프라]
    draw_node(ax,  3.5,  1.5, icons['docker'], 'Docker Compose','Flask + PG 컨테이너')
    draw_node(ax,  9.5,  1.5, icons['pg'],     'PostgreSQL',    'init.sql 자동실행',  icon_size=0.45)
    draw_node(ax, 15.5,  1.5, icons['env'],    '.env',          'KMA / Claude API Key')
    draw_node(ax, 20.5,  1.5, icons['git'],    '.gitignore',    'venv / .env 제외',   icon_size=0.42)

    # ── 화살표 ──────────────────────────────────────────
    AK = '#2d3436'
    AW = '#0984e3'
    AAI= '#e84393'
    ADB= '#00cec9'
    ADK= '#2496ed'

    # 사용자 흐름
    draw_arrow(ax,  2.5, 11.55, 8.5,  11.55, 'HTTP 요청',     AK)
    draw_arrow(ax,  8.5, 10.65, 8.5,  11.55, '',              AK)  # Flask 위

    # Flask → 날씨 조회
    draw_arrow(ax,  7.2, 12.1,  3.0,  9.0,   '날씨 조회',     AW,  rad=-0.25)
    # KMA → 매핑
    draw_arrow(ax,  4.5,  8.4,  7.0,  8.4,   '온도/강수',     AW)
    # 매핑 → Claude
    draw_arrow(ax,  10.0, 8.4,  12.0, 8.4,   '코디 조건',     AK)
    # Claude → 챗봇
    draw_arrow(ax,  15.0, 8.4,  18.0, 8.4,   '컨텍스트',      AAI)

    # Flask → 이미지 업로드
    draw_arrow(ax,  7.2, 12.1,  3.0,  5.4,   '이미지 분석',   '#6c5ce7', rad=0.3)
    # 업로드 → SigLIP
    draw_arrow(ax,  4.5,  4.8,  7.0,  4.8,   '이미지',        '#6c5ce7')
    # SigLIP → DB
    draw_arrow(ax,  10.0, 4.8,  12.0, 4.8,   '분석 결과',     ADB)
    # DB → PostgreSQL
    draw_arrow(ax,  15.0, 4.8,  18.0, 4.8,   '저장/조회',     ADB)

    # 챗봇 → Flask (결과 반환)
    draw_arrow(ax,  19.5, 9.0,  15.0, 11.55, '코디 추천',     AAI, rad=-0.3)

    # Flask → 사용자 (응답)
    draw_arrow(ax,  8.5, 12.1,  2.5,  12.1,  '대시보드',      AK,  style='<-')

    # 인프라 → DB 연결
    draw_arrow(ax,  9.5,  2.1,  13.5, 4.2,   '',              ADK, rad=-0.2)

    # ── 제목 + 범례 ──────────────────────────────────────
    ax.text(11, 13.65,
            '내 옷장의 코디 — 기술 스택 흐름도',
            ha='center', va='center', fontsize=20, fontweight='bold',
            color='#1a1a2e',
            path_effects=[pe.withStroke(linewidth=5, foreground='#f8f9fa')])
    ax.text(11, 13.2,
            'Flask  ·  Claude AI (claude-opus-4-6)  ·  Marqo FashionSigLIP  ·  KMA API  ·  PostgreSQL  ·  Docker',
            ha='center', va='center', fontsize=9, color='#636e72')

    legend_items = [
        ('#00b894', '사용자/웹'),
        ('#0984e3', '날씨 처리'),
        ('#e84393', 'AI 추천'),
        ('#6c5ce7', '이미지 분석'),
        ('#00cec9', 'DB/저장'),
        ('#2496ed', '인프라'),
    ]
    patches = [mpatches.Patch(color=c, label=l, alpha=0.7)
               for c, l in legend_items]
    ax.legend(handles=patches, loc='lower right',
              facecolor='white', edgecolor='#ddd',
              labelcolor='#2d3436', fontsize=8.5,
              framealpha=0.95, ncol=2)

    plt.tight_layout(pad=0.3)
    plt.savefig(os.path.join(OUTPUT_DIR, 'flowchart_2D.png'),
                dpi=200, bbox_inches='tight', facecolor='#f8f9fa')
    plt.close()
    print("2D 저장 완료")


def build_pipeline():
    """
    참조 이미지 스타일 — 수평 파이프라인 다이어그램
    Main row: GitHub → Docker → Flask → Claude AI → PostgreSQL
    Top node: 사용자 (요청/응답 curved arrows)
    Side inputs: KMA API, FashionSigLIP → Flask
    """

    # ── 아이콘 ────────────────────────────────────────────
    icons = {
        'github': make_icon('GH',     '#24292e', sub='GitHub',       shape='round'),
        'docker': make_icon('Docker', '#2496ed', sub='Compose',      shape='round'),
        'flask':  make_icon('Flask',  '#1a1a2e', sub='app.py',       shape='round'),
        'claude': make_icon('Claude', '#e67e22', sub='Anthropic',    shape='circle'),
        'pg':     make_icon('PG',     '#336791', sub='PostgreSQL',   shape='circle'),
        'user':   make_icon('USER',   '#00b894', sub='Browser',      shape='circle'),
        'kma':    make_icon('KMA',    '#0984e3', sub='날씨 API',     shape='circle'),
        'siglip': make_icon('CLIP',   '#6c5ce7', sub='Marqo',        shape='circle'),
    }

    fig, ax = plt.subplots(figsize=(22, 10))
    fig.patch.set_facecolor('white')
    ax.set_facecolor('white')
    ax.set_xlim(0, 22)
    ax.set_ylim(0, 10)
    ax.axis('off')

    # ── 메인 파이프라인 노드 (y=5) ─────────────────────────
    MAIN_Y = 5.0
    main_nodes = [
        ( 2.5, MAIN_Y, 'github', 'GitHub',      '(소스 관리)'),
        ( 6.5, MAIN_Y, 'docker', 'Docker',       '(빌드·컨테이너)'),
        (10.5, MAIN_Y, 'flask',  'Flask',         '(웹서버·라우터)'),
        (14.5, MAIN_Y, 'claude', 'Claude AI',     '(AI 추천엔진)'),
        (18.5, MAIN_Y, 'pg',     'PostgreSQL',    '(데이터 저장)'),
    ]
    for cx, cy, key, name, role in main_nodes:
        draw_node(ax, cx, cy, icons[key], name, role)

    # ── 상단 노드: 사용자 ────────────────────────────────────
    USER_X, USER_Y = 10.5, 8.2
    draw_node(ax, USER_X, USER_Y, icons['user'], '사용자', '(웹 브라우저)')

    # ── 하단 노드: KMA API / SigLIP ─────────────────────────
    draw_node(ax, 7.5, 1.8, icons['kma'],    '기상청 API',     '(날씨 데이터)')
    draw_node(ax, 13.5, 1.8, icons['siglip'], 'FashionSigLIP', '(이미지 분석)')

    # ── 메인 수평 화살표 ─────────────────────────────────────
    MK = '#555555'
    for i in range(len(main_nodes) - 1):
        x1, y1 = main_nodes[i][0],   main_nodes[i][1]
        x2, y2 = main_nodes[i+1][0], main_nodes[i+1][1]
        draw_arrow(ax, x1, y1, x2, y2, color=MK, lw=2.2)

    # ── 사용자 → Flask (HTTP 요청) ───────────────────────────
    draw_arrow(ax, USER_X - 0.5, USER_Y - 0.55,
               10.5, MAIN_Y + 0.55,
               'HTTP 요청', '#00b894', rad=-0.25, lw=1.8)

    # ── PostgreSQL → 사용자 (결과 반환) ────────────────────────
    draw_arrow(ax, 18.5, MAIN_Y + 0.55,
               USER_X + 0.5, USER_Y - 0.55,
               '결과 반환', '#336791', rad=-0.3, lw=1.8)

    # ── KMA API → Flask ─────────────────────────────────────
    draw_arrow(ax, 7.5, 2.5,
               10.0, MAIN_Y - 0.55,
               '날씨 조건', '#0984e3', rad=0.2, lw=1.6)

    # ── SigLIP → Flask ──────────────────────────────────────
    draw_arrow(ax, 13.5, 2.5,
               11.0, MAIN_Y - 0.55,
               '분류 결과', '#6c5ce7', rad=-0.2, lw=1.6)

    # ── 제목 ─────────────────────────────────────────────────
    ax.text(11, 9.5,
            '내 옷장의 코디 — 기술 스택 파이프라인',
            ha='center', va='center', fontsize=19, fontweight='bold',
            color='#1a1a2e')
    ax.text(11, 9.0,
            'GitHub  ·  Docker  ·  Flask  ·  Claude AI  ·  PostgreSQL  ·  기상청 API  ·  Marqo FashionSigLIP',
            ha='center', va='center', fontsize=9, color='#888888')

    # ── 구분선 ────────────────────────────────────────────────
    ax.plot([1, 21], [MAIN_Y, MAIN_Y], color='#eeeeee', lw=40,
            solid_capstyle='round', zorder=0, alpha=0.5)

    plt.tight_layout(pad=0.3)
    plt.savefig(os.path.join(OUTPUT_DIR, 'pipeline.png'),
                dpi=200, bbox_inches='tight', facecolor='white')
    plt.close()
    print("Pipeline saved")


def build_full_stack_OLD():
    """
    전체 기술 스택 — 5개 레이어 수직 다이어그램
    Layer A: 개발환경    (VS Code, Python, Git, pip)
    Layer B: 소스·인프라 (GitHub, Docker Compose)
    Layer C: 웹 레이어   (Flask, Jinja2, HTML/CSS/JS, python-dotenv)
    Layer D: AI·외부API  (KMA API, Claude AI, Marqo/SigLIP, Pillow+OpenCV)
    Layer E: 데이터베이스 (SQLite, PostgreSQL 15)
    """

    # ── 레이어 Y좌표 ─────────────────────────────────────────
    YA = 18.0   # 개발환경
    YB = 13.8   # 소스·인프라
    YC =  9.6   # 웹 레이어
    YD =  5.4   # AI·외부API
    YE =  1.6   # 데이터베이스

    # ── 아이콘 ────────────────────────────────────────────────
    IC = {
        # A
        'vscode':  make_icon('VSC',    '#007acc', sub='VS Code',       shape='round'),
        'python':  make_icon('PY',     '#3776ab', sub='Python 3.11',   shape='circle'),
        'git':     make_icon('Git',    '#f05032', sub='GitHub',        shape='round'),
        'pip':     make_icon('pip',    '#3775a9', sub='requirements',  shape='round'),
        # B
        'github':  make_icon('GH',     '#24292e', sub='소스 관리',     shape='round'),
        'docker':  make_icon('Docker', '#2496ed', sub='Compose',       shape='round'),
        # C
        'flask':   make_icon('Flask',  '#1a1a2e', sub='app.py',        shape='round'),
        'jinja':   make_icon('Jinja',  '#b41717', sub='템플릿엔진',    shape='round'),
        'html':    make_icon('HTML',   '#e34c26', sub='CSS · JS',      shape='round'),
        'dotenv':  make_icon('.env',   '#636e72', sub='API Key',       shape='round'),
        # D
        'kma':     make_icon('KMA',    '#0984e3', sub='날씨API',       shape='circle'),
        'claude':  make_icon('Claude', '#e67e22', sub='Anthropic',     shape='circle'),
        'siglip':  make_icon('CLIP',   '#6c5ce7', sub='Marqo',         shape='circle'),
        'cv':      make_icon('CV',     '#00897b', sub='Pillow·OpenCV', shape='circle'),
        # E
        'sqlite':  make_icon('SQLite', '#003b57', sub='로컬 DB',       shape='circle'),
        'pg':      make_icon('PG',     '#336791', sub='PostgreSQL 15', shape='circle'),
    }

    fig, ax = plt.subplots(figsize=(28, 26))
    fig.patch.set_facecolor('#ffffff')
    ax.set_facecolor('#ffffff')
    ax.set_xlim(0, 28)
    ax.set_ylim(0, 23)
    ax.axis('off')

    # ── 레이어 배경 밴드 ──────────────────────────────────────
    bands = [
        (YA, '#007acc', '개발 환경  (Development)'),
        (YB, '#24292e', '소스 관리 · 인프라  (Infra)'),
        (YC, '#1a1a2e', '웹 레이어  (Web Server)'),
        (YD, '#e67e22', 'AI · 외부 API  (Services)'),
        (YE, '#336791', '데이터베이스  (Database)'),
    ]
    for cy, color, title in bands:
        rect = FancyBboxPatch((0.4, cy - 2.5), 27.2, 3.2,
                              boxstyle='round,pad=0.15,rounding_size=0.4',
                              facecolor=color, alpha=0.10,
                              edgecolor=color, linewidth=2.0,
                              linestyle='--', zorder=0)
        ax.add_patch(rect)
        ax.text(1.0, cy + 0.5, title,
                fontsize=9.5, color=color, fontweight='bold',
                alpha=0.95, zorder=1)

    # ── 노드 배치 ─────────────────────────────────────────────
    # Layer A: 개발환경 (4개)
    nodes_A = [(4.5,  YA, 'vscode', 'VS Code',       '개발 IDE'),
               (10.5, YA, 'python', 'Python 3.11',   '언어·런타임'),
               (16.5, YA, 'git',    'Git',            '버전 관리'),
               (22.5, YA, 'pip',    'pip',            'requirements.txt')]

    # Layer B: 소스·인프라 (2개)
    nodes_B = [(9.5,  YB, 'github', 'GitHub',         '코드 원격 저장소'),
               (19.5, YB, 'docker', 'Docker Compose', 'Flask + PG 컨테이너')]

    # Layer C: 웹 레이어 (4개)
    nodes_C = [(4.5,  YC, 'flask',  'Flask',          '웹 서버·라우터'),
               (10.5, YC, 'jinja',  'Jinja2',         'HTML 템플릿 엔진'),
               (16.5, YC, 'html',   'HTML/CSS/JS',    '프론트엔드 UI'),
               (22.5, YC, 'dotenv', 'python-dotenv',  'API키 환경변수')]

    # Layer D: AI·외부API (4개)
    nodes_D = [(4.5,  YD, 'kma',    '기상청 API',     '날씨·강수 데이터'),
               (10.5, YD, 'claude', 'Claude AI',      '코디 추천·챗봇'),
               (16.5, YD, 'siglip', 'FashionSigLIP',  'Marqo 의류 분류'),
               (22.5, YD, 'cv',     'Pillow·OpenCV',  '이미지 전처리')]

    # Layer E: DB (2개)
    nodes_E = [(9.5,  YE, 'sqlite', 'SQLite',         '로컬 개발용 DB'),
               (19.5, YE, 'pg',     'PostgreSQL 15',  '고객·옷장 데이터 저장')]

    all_nodes = nodes_A + nodes_B + nodes_C + nodes_D + nodes_E
    for cx, cy, key, name, role in all_nodes:
        draw_node(ax, cx, cy, IC[key], name, role, icon_size=0.75)

    # ── 레이어 간 대표 화살표 ─────────────────────────────────
    AK = '#555555'
    lw = 2.0

    # A → B
    draw_arrow(ax, 10.5, YA - 0.65,  9.5, YB + 0.65, 'git push',   AK, lw=lw)
    draw_arrow(ax, 22.5, YA - 0.65, 19.5, YB + 0.65, '패키지 관리', AK, rad=0.15, lw=lw)

    # B → C
    draw_arrow(ax,  9.5, YB - 0.65,  4.5, YC + 0.65, '코드 배포',   AK, rad=0.25, lw=lw)
    draw_arrow(ax, 19.5, YB - 0.65, 16.5, YC + 0.65, 'up --build', '#2496ed', rad=0.15, lw=lw)

    # C → D
    draw_arrow(ax,  4.5, YC - 0.65,  4.5, YD + 0.65, '날씨 요청',   '#0984e3', lw=lw)
    draw_arrow(ax, 10.5, YC - 0.65, 10.5, YD + 0.65, 'AI 코디 요청','#e67e22', lw=lw)
    draw_arrow(ax, 16.5, YC - 0.65, 16.5, YD + 0.65, '이미지 분석', '#6c5ce7', lw=lw)

    # D → E
    draw_arrow(ax,  4.5, YD - 0.65,  9.5, YE + 0.65, '날씨 로그 저장',  AK, rad=0.25, lw=lw)
    draw_arrow(ax, 10.5, YD - 0.65,  9.5, YE + 0.65, '추천 이력 저장',  AK, rad=0.1,  lw=lw)
    draw_arrow(ax, 16.5, YD - 0.65, 19.5, YE + 0.65, '옷장 정보 저장',  AK, rad=-0.1, lw=lw)

    # Docker → PG (Docker가 PG 컨테이너 포함)
    draw_arrow(ax, 19.5, YB - 0.65, 19.5, YE + 0.65,
               'init.sql 자동실행', '#2496ed', rad=0.45, lw=1.5)

    # ── 제목 ─────────────────────────────────────────────────
    ax.text(14, 22.3,
            '내 옷장의 코디 — 전체 기술 스택',
            ha='center', va='center', fontsize=22, fontweight='bold',
            color='#1a1a2e',
            path_effects=[pe.withStroke(linewidth=6, foreground='white')])
    ax.text(14, 21.7,
            'VS Code · Python · Git · GitHub · Docker · Flask · Jinja2 · Claude AI · '
            'KMA API · Marqo FashionSigLIP · Pillow · OpenCV · SQLite · PostgreSQL 15',
            ha='center', va='center', fontsize=9, color='#888888')

    plt.tight_layout(pad=0.3)
    plt.savefig(os.path.join(OUTPUT_DIR, 'full_stack.png'),
                dpi=200, bbox_inches='tight', facecolor='white')
    plt.close()
    print("Full stack saved")


def build_full_stack():
    """
    참조 이미지 스타일 — 실제 브랜드 로고 + 컨테이너 박스 전문 다이어그램
    Layout:
      [개발환경 바 — 최상단]
               ↓
    [사용자] ↔ [웹서버 컨테이너] ↔ [DB 컨테이너]
                    ↕
              [AI·외부API 컨테이너]
    """
    sz = 160
    BASE = 'https://img.icons8.com/color/{s}/{name}.png'
    FILL = 'https://img.icons8.com/ios-filled/{s}/{name}.png'

    def L(name, bg='#ffffff', shape='circle', filled=False, url=None):
        """Icons8 로고 다운로드, 실패 시 None"""
        if url is None:
            url = (f'https://img.icons8.com/ios-filled/{sz}/{name}.png' if filled
                   else f'https://img.icons8.com/color/{sz}/{name}.png')
        result = get_logo(url, size=sz, bg=bg, shape=shape)
        return result  # None 또는 np.array

    def icon(logo, fallback):
        """실제 로고가 있으면 사용, 없으면 fallback PIL 아이콘 사용"""
        return logo if logo is not None else fallback

    def M(label, color, shape='circle', sub=''):
        return make_icon(label, color, size=sz, shape=shape, sub=sub)

    # ── 아이콘 로드 (실제 로고 우선, fallback은 M()) ──────────
    IC = {
        # 개발환경
        'user':   icon(L('user-male-circle', bg='#e8f8f2'),
                       M('USER','#2ecc71')),
        'vscode': icon(L('visual-studio-code-2019', bg='#e8f4fc', shape='round'),
                       M('VSC','#007acc', shape='round')),
        'python': icon(L('python', bg='#f5f7ff'),
                       M('PY','#3776ab')),
        'git':    icon(L('git', bg='#fff4f0', shape='round'),
                       M('Git','#f05032', shape='round')),
        'github': icon(L('github', bg='#2d333b', shape='round', filled=True),
                       M('GH','#24292e', shape='round')),
        'docker': icon(L('docker', bg='#e8f4fc', shape='round'),
                       M('Docker','#2496ed', shape='round')),
        # 웹서버
        'flask':  icon(L('flask', bg='#f5f5f5', shape='round', filled=True),
                       M('Flask','#1a1a2e', shape='round')),
        'jinja':  M('Jinja','#b41717', shape='round'),
        'html':   icon(L('html-5--v1', bg='#fff2ee', shape='round'),
                       M('HTML','#e34c26', shape='round')),
        'dotenv': M('.env','#55606a', shape='round'),
        # AI·외부API
        'kma':    icon(L('partly-cloudy-day', bg='#e8f4ff'),
                       M('KMA','#0984e3')),
        'claude': icon(L('artificial-intelligence', bg='#fff4e8', filled=True),
                       M('Claude','#e67e22')),
        'siglip': icon(L('wardrobe', bg='#f0ecff'),
                       M('CLIP','#6c5ce7')),
        'cv':     icon(L('opencv', bg='#e8f8f5'),
                       M('CV','#00897b')),
        # DB
        'sqlite': icon(L('database', bg='#e8edf2', filled=True),
                       M('SQLite','#003b57')),
        'pg':     icon(L('postgreesql', bg='#ebf3ff'),
                       M('PG','#336791')),
    }

    FW, FH = 34, 24
    fig, ax = plt.subplots(figsize=(FW, FH))
    fig.patch.set_facecolor('#f0f2f5')
    ax.set_facecolor('#f0f2f5')
    ax.set_xlim(0, FW)
    ax.set_ylim(0, FH)
    ax.axis('off')

    # ── 컨테이너 그리기 함수 ────────────────────────────────
    def container(x, y, w, h, color, label):
        """흰 배경 + 컬러 테두리 + 컬러 헤더 바"""
        # 드롭 섀도
        ax.add_patch(FancyBboxPatch(
            (x + 0.18, y - 0.18), w, h,
            boxstyle='round,pad=0.1,rounding_size=0.55',
            facecolor='#00000028', edgecolor='none', zorder=1))
        # 흰 본체
        ax.add_patch(FancyBboxPatch(
            (x, y), w, h,
            boxstyle='round,pad=0.1,rounding_size=0.55',
            facecolor='white', edgecolor=color, linewidth=4.0, zorder=2))
        # 컬러 헤더 바
        ax.add_patch(FancyBboxPatch(
            (x + 0.08, y + h - 1.18), w - 0.16, 1.10,
            boxstyle='round,pad=0.05,rounding_size=0.45',
            facecolor=color, edgecolor='none', alpha=0.93, zorder=3))
        ax.text(x + w / 2, y + h - 0.60, label,
                ha='center', va='center', fontsize=10.5,
                fontweight='bold', color='white', zorder=4)

    # ── 제목 ────────────────────────────────────────────────
    ax.text(17, 23.3, '내 옷장의 코디 — 전체 기술 스택',
            ha='center', fontsize=22, fontweight='bold', color='#2d3436', va='center',
            path_effects=[pe.withStroke(linewidth=4, foreground='#f0f2f5')])
    ax.text(17, 22.75,
            'Flask · Claude AI · Marqo FashionSigLIP · 기상청 API · PostgreSQL · Docker Compose',
            ha='center', fontsize=9.5, color='#888888', va='center')

    # ════════════════════════════════════════════════════════
    # LAYER 1 — 개발 환경 바 (상단)
    container(0.5, 18.8, 33.0, 3.8, '#636e72',
              '개발 환경  ·  Development Environment')
    dev_items = [
        (3.5,  'vscode', 'VS Code',       '개발 IDE'),
        (9.0,  'python', 'Python 3.11',   '언어·런타임'),
        (14.5, 'git',    'Git',           '버전 관리'),
        (20.0, 'github', 'GitHub',        '원격 저장소'),
        (25.5, 'docker', 'Docker Compose','컨테이너 실행'),
        (31.0, 'dotenv', '.env',          'API Key 관리'),
    ]
    for x, key, name, sub in dev_items:
        draw_node(ax, x, 20.4, IC[key], name, sub, icon_size=0.68)

    # ════════════════════════════════════════════════════════
    # LAYER 2 — 웹서버 컨테이너 (중앙 좌)
    container(3.5, 12.5, 17.0, 5.8, '#e17055',
              '웹 서버 레이어  ·  Flask Application Server')
    draw_node(ax,  7.0, 15.1, IC['flask'], 'Flask',       'app.py · 라우터',   icon_size=0.90)
    draw_node(ax, 12.0, 15.1, IC['jinja'], 'Jinja2',      'HTML 템플릿 엔진',  icon_size=0.90)
    draw_node(ax, 17.5, 15.1, IC['html'],  'HTML/CSS/JS', '프론트엔드 UI',     icon_size=0.90)

    # LAYER 2 — DB 컨테이너 (중앙 우)
    container(22.0, 12.5, 11.5, 5.8, '#0984e3',
              '데이터베이스  ·  Database')
    draw_node(ax, 24.5, 15.1, IC['sqlite'], 'SQLite',       '로컬 개발용 DB',    icon_size=0.90)
    draw_node(ax, 30.0, 15.1, IC['pg'],     'PostgreSQL 15','고객·옷장 데이터',  icon_size=0.90)

    # ════════════════════════════════════════════════════════
    # LAYER 3 — AI · 외부 API 컨테이너 (하단)
    container(3.5, 2.5, 29.5, 9.5, '#6c5ce7',
              'AI 엔진  ·  외부 API  ·  External Services')
    draw_node(ax,  7.5, 9.5, IC['kma'],    '기상청 API',    '날씨·강수 데이터',  icon_size=0.90)
    draw_node(ax, 14.0, 9.5, IC['claude'], 'Claude AI',     '코디 추천·챗봇',    icon_size=0.90)
    draw_node(ax, 20.5, 9.5, IC['siglip'], 'FashionSigLIP', 'Marqo 의류 분류',   icon_size=0.90)
    draw_node(ax, 27.0, 9.5, IC['cv'],     'Pillow·OpenCV', '이미지 전처리',     icon_size=0.90)

    # AI 내부 서브 설명
    for x, txt in [
        ( 7.5, '날씨 조건 → 코디 스타일\nweather_style_mapper'),
        (14.0, '시스템 프롬프트\n수석 스타일리스트 역할'),
        (20.5, '의류 카테고리 + 보온도\nwarmth 점수 분류'),
        (27.0, '업로드 이미지\n전처리 · 리사이즈'),
    ]:
        ax.text(x, 6.2, txt, ha='center', va='center', fontsize=7.8,
                color='#6c5ce7', style='italic',
                bbox=dict(boxstyle='round,pad=0.35', fc='#ede7ff',
                          ec='#6c5ce7', alpha=0.65, lw=0.8))

    # ════════════════════════════════════════════════════════
    # 사용자 노드 (왼쪽 바깥)
    draw_node(ax, 1.5, 15.1, IC['user'], '사용자', 'localhost:5000', icon_size=1.0)

    # ── 화살표 ──────────────────────────────────────────────
    AW = 2.3

    # 개발환경 → 웹서버 (배포)
    ax.annotate('', xy=(12.0, 18.8), xytext=(12.0, 18.3),
                arrowprops=dict(arrowstyle='->', color='#636e72', lw=2.0), zorder=5)
    ax.text(13.7, 18.55, 'git pull / deploy', fontsize=8.5, color='#636e72', va='center')

    # 사용자 ↔ Flask
    draw_arrow(ax, 2.4, 15.7, 5.0, 15.7, 'HTTP 요청',       '#e17055', lw=AW)
    draw_arrow(ax, 5.0, 14.5, 2.4, 14.5, '응답 (대시보드)', '#e17055', lw=AW)

    # 웹서버 ↔ DB
    draw_arrow(ax, 20.5, 15.7, 23.5, 15.7, '저장 / 조회', '#0984e3', lw=AW)
    draw_arrow(ax, 23.5, 14.5, 20.5, 14.5, '결과 반환',   '#0984e3', lw=AW)

    # 웹서버 → AI/API
    draw_arrow(ax,  7.0, 12.5,  7.5, 11.5, '날씨 요청',    '#0984e3', lw=AW, rad= 0.15)
    draw_arrow(ax, 12.0, 12.5, 14.0, 11.5, 'AI 추천 요청', '#e67e22', lw=AW, rad= 0.10)
    draw_arrow(ax, 17.5, 12.5, 20.5, 11.5, '이미지 분석',  '#6c5ce7', lw=AW, rad=-0.10)

    # AI/API → 웹서버
    draw_arrow(ax,  7.5, 11.5,  7.0, 12.5, '날씨 데이터', '#0984e3', lw=1.8, rad=-0.30)
    draw_arrow(ax, 14.0, 11.5, 12.0, 12.5, '코디 추천',   '#e67e22', lw=1.8, rad=-0.25)
    draw_arrow(ax, 20.5, 11.5, 17.5, 12.5, '분류 결과',   '#6c5ce7', lw=1.8, rad= 0.25)

    plt.tight_layout(pad=0.3)
    plt.savefig(os.path.join(OUTPUT_DIR, 'full_stack.png'),
                dpi=180, bbox_inches='tight', facecolor='#f0f2f5')
    plt.close()
    print("Full stack saved")


if __name__ == '__main__':
    build()
    build_pipeline()
    build_full_stack()
