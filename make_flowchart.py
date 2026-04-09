# -*- coding: utf-8 -*-
"""
내 옷장의 코디 — 기술 스택 흐름도 (2D)
diagrams + Graphviz 기반 전문 아이콘 다이어그램
"""
import os, sys
os.environ["PATH"] += r";C:\Program Files\Graphviz\bin"

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
import io

plt.rcParams['font.family'] = 'Malgun Gothic'
plt.rcParams['axes.unicode_minus'] = False


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


if __name__ == '__main__':
    build()
