"""
app.py — 내 옷장의 코디 FastAPI 통합 서버 (포트 5000)
Flask → FastAPI 마이그레이션 + 음성 파이프라인(voice/router.py) 통합

라우트:
  GET  /                     → 대시보드
  GET  /login                → 로그인 페이지
  POST /login                → 로그인 처리
  POST /signup               → 회원가입
  GET  /auth/google          → Google OAuth 시작
  GET  /auth/google/callback → Google OAuth 콜백
  GET  /logout               → 로그아웃
  GET  /profile              → 프로필 페이지
  POST /profile              → 프로필 저장
  GET  /wardrobe             → 옷장 목록
  POST /wardrobe/add         → 옷 업로드 & AI 분석
  POST /wardrobe/delete/{id} → 옷 삭제
  POST /wardrobe/move/{id}   → 카테고리 변경
  POST /feedback/{log_id}    → 코디 피드백
  POST /chat                 → 챗봇 API
  GET  /api/weather          → 날씨 JSON
  GET  /api/recommend        → 코디 추천 JSON
  GET  /api/shopping         → 쇼핑 추천 JSON
  GET  /fashion-show         → 패션쇼 페이지
  + voice/* (voice/router.py)
"""

from __future__ import annotations

import json
import os
import time
import uuid
import urllib.parse
from datetime import datetime
from typing import Optional

from dotenv import load_dotenv

load_dotenv()

import cloudinary
import cloudinary.uploader
from fastapi import FastAPI, File, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.middleware.sessions import SessionMiddleware
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

from db import (
    db_engine, execute, executereturning, fetchall, fetchone,
    get_db, is_postgres, save_feedback, save_style_log,
)
from voice.router import router as voice_router

# ══════════════════════════════════════════════════════════════════
# 앱 초기화
# ══════════════════════════════════════════════════════════════════

app = FastAPI(title="내 옷장의 코디")

app.add_middleware(
    SessionMiddleware,
    secret_key=os.getenv("FLASK_SECRET_KEY", "change-me-please"),
    session_cookie=os.getenv("SESSION_COOKIE_NAME", "session_local"),
)

app.mount("/static", StaticFiles(directory="static"), name="static_files")
templates = Jinja2Templates(directory="templates")


def img_url_filter(image_path) -> str:
    """Cloudinary public_id → CDN URL, 로컬 경로 → /static/..."""
    if not image_path:
        return ""
    image_path = str(image_path).strip()
    if not image_path:
        return ""
    if image_path.startswith("http"):
        return image_path
    # static/ 으로 시작하면 로컬 파일
    if image_path.startswith("static/") or image_path.startswith("/static/"):
        clean = image_path.replace("\\", "/").lstrip("/").replace("static/", "")
        return f"/static/{clean}"
    # 그 외(users/... 등)는 Cloudinary public_id
    cloud_name = os.getenv("CLOUDINARY_CLOUD_NAME")
    if cloud_name:
        return f"https://res.cloudinary.com/{cloud_name}/image/upload/{image_path}"
    # Cloudinary 미설정이면 로컬 폴백
    clean = image_path.replace("\\", "/")
    return f"/static/{clean}"


templates.env.filters["img_url"] = img_url_filter


def make_musinsa_search_url(query: str) -> str:
    if not query:
        return "https://www.musinsa.com/search/goods"
    return "https://www.musinsa.com/search/goods?keyword=" + urllib.parse.quote(query)


def make_shopping_query(category: str, style_pref: str = "캐주얼", gender: str = "여성") -> str:
    if not category:
        return f"{gender} {style_pref}".strip()
    label_map = {
        "상의": "상의",
        "하의": "하의",
        "아우터": "아우터",
        "원피스": "원피스",
        "신발": "신발",
        "악세서리": "악세서리",
    }
    label = label_map.get(category, category)
    return f"{gender} {style_pref} {label}".strip()

# 음성 파이프라인 라우터 통합
app.include_router(voice_router)

# ── Cloudinary ────────────────────────────────────────────────────
_CLOUDINARY_ENABLED = bool(os.getenv("CLOUDINARY_CLOUD_NAME"))
if _CLOUDINARY_ENABLED:
    cloudinary.config(
        cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME"),
        api_key=os.getenv("CLOUDINARY_API_KEY"),
        api_secret=os.getenv("CLOUDINARY_API_SECRET"),
        secure=True,
    )

# ── Google OAuth ──────────────────────────────────────────────────
_GOOGLE_ENABLED = bool(os.getenv("GOOGLE_CLIENT_ID"))
_oauth = None
if _GOOGLE_ENABLED:
    from authlib.integrations.starlette_client import OAuth
    _oauth = OAuth()
    _oauth.register(
        name="google",
        client_id=os.getenv("GOOGLE_CLIENT_ID"),
        client_secret=os.getenv("GOOGLE_CLIENT_SECRET"),
        server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
        client_kwargs={
            "scope": "openid email profile https://www.googleapis.com/auth/calendar.readonly",
            "access_type": "online",
            "prompt": "consent",
        },
    )

# ── 상수 ─────────────────────────────────────────────────────────
UPLOAD_FOLDER = "static/uploads"
ALLOWED_EXT   = {"jpg", "jpeg", "png"}
PROFILE_PATH  = "user_profile.json"

_recommend_cache: dict = {}
_CACHE_TTL = 1800

_TOP_WARMTH_MIN = {
    "freezing": 2, "very_cold": 1, "cold": 1, "cool": 0,
    "mild": 0, "warm": 0, "hot": 0, "very_hot": 0,
}
_NEEDS_OUTER = {"freezing", "very_cold", "cold", "cool"}


# ══════════════════════════════════════════════════════════════════
# Auth 유틸
# ══════════════════════════════════════════════════════════════════

class _AnonymousUser:
    is_authenticated = False
    id = None
    name = ""
    email = ""
    avatar_url = ""


class User:
    is_authenticated = True

    def __init__(self, row: dict):
        self.id         = str(row["id"])
        self.name       = row.get("name") or ""
        self.email      = row.get("email") or ""
        self.avatar_url = row.get("avatar_url") or ""

    @staticmethod
    def get(user_id: str) -> Optional["User"]:
        try:
            ph  = "%s" if is_postgres() else "?"
            with get_db() as conn:
                row = fetchone(conn, f"SELECT * FROM users WHERE id={ph}", (user_id,))
                return User(row) if row else None
        except Exception:
            return None


class _LoginRequired(Exception):
    pass


@app.exception_handler(_LoginRequired)
async def _login_required_handler(request: Request, exc: _LoginRequired):
    return RedirectResponse("/login", status_code=302)


def _get_user(request: Request) -> User | _AnonymousUser:
    user_id = request.session.get("user_id")
    if not user_id:
        return _AnonymousUser()
    return User.get(user_id) or _AnonymousUser()


def _require_user(request: Request) -> User:
    """로그인 필수. 미로그인이면 _LoginRequired 발생 → /login 리다이렉트."""
    user = _get_user(request)
    if not user.is_authenticated:
        raise _LoginRequired()
    return user


# ── Flash 메시지 ───────────────────────────────────────────────────
def flash(request: Request, message: str, category: str = "info"):
    if "_flash" not in request.session:
        request.session["_flash"] = []
    request.session["_flash"].append([category, message])


# ── 템플릿 렌더 헬퍼 ───────────────────────────────────────────────
def render(request: Request, name: str, ctx: dict = {}) -> HTMLResponse:
    """
    FastAPI Jinja2 템플릿을 Flask와 호환되게 렌더.
    - url_for('route_name') 및 url_for('static', filename='...')
    - get_flashed_messages(with_categories=True/False)
    - current_user (User | _AnonymousUser)
    - endpoint (현재 라우트 함수명, base.html 네비 active 표시용)
    """
    user       = _get_user(request)
    flash_msgs = request.session.pop("_flash", [])

    def _url_for(endpoint: str, **kwargs) -> str:
        if endpoint == "static":
            return f"/static/{kwargs.get('filename', '')}"
        try:
            return request.url_for(endpoint, **kwargs).path
        except Exception:
            return f"/{endpoint}"

    def _get_flashed(with_categories: bool = False):
        return flash_msgs if with_categories else [m for _, m in flash_msgs]

    ep_func = request.scope.get("endpoint")
    ep = ep_func.__name__ if callable(ep_func) else ""

    return templates.TemplateResponse(request, name, {
        "current_user":         user,
        "url_for":              _url_for,
        "get_flashed_messages": _get_flashed,
        "endpoint":             ep,
        **ctx,
    })


# ── 유틸 ──────────────────────────────────────────────────────────

def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXT


# 카테고리 한→영 변환 (Cloudinary public_id는 영문만 권장)
_CAT_EN = {"상의": "top", "하의": "bottom", "아우터": "outer", "원피스": "dress"}


def upload_image(
    file_path: str,
    user_id=None,
    subfolder: str = "wardrobe",   # 하위 호환용 (무시됨)
    category: str = None,
    item_name: str = None,
) -> str:
    """
    Cloudinary 업로드 + 회원별 폴더/파일명 규칙 적용.

    폴더  : users/{user_id}/closet
    파일명: user{uid}__{cat}__{item}__{timestamp}
            예) user42__top__shirt__20260413_104818

    Cloudinary 미설정 → 로컬 경로 그대로 반환.
    업로드 실패 → RuntimeError 발생 (호출부에서 DB 저장을 막음).
    """
    if not _CLOUDINARY_ENABLED:
        return file_path

    # 폴더: wardrobe → users/{id}/closet, 그 외(profile 등) → users/{id}/{subfolder}
    if subfolder == "wardrobe":
        folder = f"users/{user_id}/closet" if user_id else "shared/closet"
    else:
        folder = f"users/{user_id}/{subfolder}" if user_id else f"shared/{subfolder}"

    ts        = datetime.now().strftime("%Y%m%d_%H%M%S")
    cat_en    = _CAT_EN.get(category or "", subfolder)
    item_slug = (item_name or "item").replace(" ", "_").replace("/", "_")
    uid_str   = str(user_id)[:12] if user_id else "anon"
    public_id = f"user{uid_str}__{cat_en}__{item_slug}__{ts}"

    try:
        result = cloudinary.uploader.upload(
            file_path,
            folder=folder,
            public_id=public_id,
            resource_type="image",
            overwrite=False,
        )
        url = result["secure_url"]
        print(f"[Cloudinary] 업로드 완료: {folder}/{public_id} → {url[:60]}...")
        return url
    except Exception as e:
        raise RuntimeError(f"Cloudinary 업로드 실패: {e}") from e


def _cloudinary_public_id(url: str) -> str:
    try:
        after_upload = url.split("/upload/", 1)[1]
        if after_upload.startswith("v") and "/" in after_upload:
            _, after_upload = after_upload.split("/", 1)
        return after_upload.rsplit(".", 1)[0]
    except Exception:
        parts = url.split("/")
        return "/".join(parts[-2:]).rsplit(".", 1)[0]


def delete_image(image_path: str) -> None:
    if not image_path:
        return
    if image_path.startswith("http"):
        try:
            cloudinary.uploader.destroy(_cloudinary_public_id(image_path))
        except Exception as e:
            print(f"Cloudinary 삭제 실패: {e}")
    else:
        if os.path.exists(image_path) and "uploads" in image_path:
            os.remove(image_path)


def load_profile(user_id: str = None) -> dict:
    if not user_id:
        return {}
    if is_postgres():
        with get_db() as conn:
            row = fetchone(conn, "SELECT * FROM users WHERE id=%s", (user_id,))
            return dict(row) if row else {}
    else:
        if os.path.exists(PROFILE_PATH):
            with open(PROFILE_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}


def save_profile_data(data: dict, user_id: str) -> str:
    if is_postgres() and user_id:
        with get_db() as conn:
            execute(conn, """
                UPDATE users SET
                    name=%s, gender=%s, height=%s, weight=%s,
                    body_type=%s, style_pref=%s, sensitivity=%s,
                    tpo=%s, location_nx=%s, location_ny=%s
                WHERE id=%s
            """, (
                data["name"], data["gender"],
                int(data["height"]) if data["height"] else None,
                int(data["weight"]) if data["weight"] else None,
                data["body_type"], data["style_pref"],
                int(data["sensitivity"]), data["tpo"],
                int(data["nx"]), int(data["ny"]),
                user_id,
            ))
        return user_id
    else:
        with open(PROFILE_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return "local"


def _save_avatar(user_id: str, avatar_url: str) -> None:
    if not user_id or user_id == "local":
        return
    ph = "%s" if is_postgres() else "?"
    with get_db() as conn:
        execute(conn, f"UPDATE users SET avatar_url={ph} WHERE id={ph}", (avatar_url, user_id))


def init_db():
    if is_postgres():
        with get_db() as conn:
            for col, definition in [
                ("email",         "VARCHAR(200)"),
                ("password_hash", "TEXT"),
                ("google_id",     "TEXT"),
                ("avatar_url",    "TEXT"),
            ]:
                execute(conn, f"ALTER TABLE users ADD COLUMN IF NOT EXISTS {col} {definition}")
            execute(conn, "CREATE UNIQUE INDEX IF NOT EXISTS users_email_uidx    ON users(email)     WHERE email IS NOT NULL")
            execute(conn, "CREATE UNIQUE INDEX IF NOT EXISTS users_google_id_uidx ON users(google_id) WHERE google_id IS NOT NULL")
        print(f"[DB] {db_engine()} 연결됨")
        return

    with get_db() as conn:
        execute(conn, """
            CREATE TABLE IF NOT EXISTS wardrobe_items (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     TEXT,
                image_path  TEXT,
                category    TEXT NOT NULL,
                item_type   TEXT NOT NULL,
                warmth      INTEGER DEFAULT 1,
                texture     TEXT,
                color_tone  TEXT,
                created_at  TEXT
            )
        """)
        execute(conn, """
            CREATE TABLE IF NOT EXISTS users (
                id            TEXT PRIMARY KEY,
                email         TEXT UNIQUE,
                password_hash TEXT,
                google_id     TEXT UNIQUE,
                avatar_url    TEXT,
                name          TEXT, gender TEXT, height INTEGER, weight INTEGER,
                body_type     TEXT, style_pref TEXT, sensitivity INTEGER DEFAULT 3,
                tpo TEXT DEFAULT '일상', location_nx INTEGER DEFAULT 62,
                location_ny   INTEGER DEFAULT 123,
                created_at TEXT, updated_at TEXT
            )
        """)
        for col, definition in [
            ("email", "TEXT"), ("password_hash", "TEXT"),
            ("google_id", "TEXT"), ("avatar_url", "TEXT"),
        ]:
            try:
                execute(conn, f"ALTER TABLE users ADD COLUMN {col} {definition}")
            except Exception:
                pass
    print(f"[DB] {db_engine()} 초기화 완료")


# ══════════════════════════════════════════════════════════════════
# 시작 이벤트
# ══════════════════════════════════════════════════════════════════

@app.on_event("startup")
def startup():
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    init_db()


# ══════════════════════════════════════════════════════════════════
# 인증 라우트
# ══════════════════════════════════════════════════════════════════

@app.get("/login", name="login_page")
def login_page(request: Request):
    user = _get_user(request)
    if user.is_authenticated:
        return RedirectResponse("/", status_code=302)
    return render(request, "login.html", {"active_tab": "login"})


@app.post("/login", name="login")
async def login(request: Request):
    form     = await request.form()
    email    = str(form.get("email", "")).strip().lower()
    password = str(form.get("password", ""))

    if not email or not password:
        flash(request, "이메일과 비밀번호를 입력해주세요.", "error")
        return render(request, "login.html", {"active_tab": "login"})

    ph = "%s" if is_postgres() else "?"
    with get_db() as conn:
        row = fetchone(conn, f"SELECT * FROM users WHERE email={ph}", (email,))

    if not row or not row.get("password_hash"):
        flash(request, "이메일 또는 비밀번호가 올바르지 않습니다.", "error")
        return render(request, "login.html", {"active_tab": "login"})

    if not check_password_hash(row["password_hash"], password):
        flash(request, "이메일 또는 비밀번호가 올바르지 않습니다.", "error")
        return render(request, "login.html", {"active_tab": "login"})

    request.session["user_id"] = str(row["id"])
    return RedirectResponse("/", status_code=302)


@app.post("/signup", name="signup")
async def signup(request: Request):
    form      = await request.form()
    name      = str(form.get("name", "")).strip()
    email     = str(form.get("email", "")).strip().lower()
    password  = str(form.get("password", ""))
    password2 = str(form.get("password2", ""))

    if not name or not email or not password:
        flash(request, "모든 항목을 입력해주세요.", "error")
        return render(request, "login.html", {"active_tab": "signup"})
    if len(password) < 8:
        flash(request, "비밀번호는 8자 이상이어야 합니다.", "error")
        return render(request, "login.html", {"active_tab": "signup"})
    if password != password2:
        flash(request, "비밀번호가 일치하지 않습니다.", "error")
        return render(request, "login.html", {"active_tab": "signup"})

    ph = "%s" if is_postgres() else "?"
    with get_db() as conn:
        if fetchone(conn, f"SELECT id FROM users WHERE email={ph}", (email,)):
            flash(request, "이미 가입된 이메일입니다.", "error")
            return render(request, "login.html", {"active_tab": "signup"})

        hashed = generate_password_hash(password)
        if is_postgres():
            user_id = executereturning(conn, """
                INSERT INTO users (name, email, password_hash)
                VALUES (%s, %s, %s) RETURNING id
            """, (name, email, hashed))
        else:
            user_id = str(uuid.uuid4())
            execute(conn, """
                INSERT INTO users (id, name, email, password_hash)
                VALUES (?, ?, ?, ?)
            """, (user_id, name, email, hashed))

        row = fetchone(conn, f"SELECT * FROM users WHERE id={ph}", (str(user_id),))

    request.session["user_id"] = str(row["id"])
    flash(request, f"환영합니다, {name}님! 프로필을 완성해주세요.", "success")
    return RedirectResponse("/profile", status_code=302)


@app.get("/auth/google", name="auth_google")
async def auth_google(request: Request):
    if not _GOOGLE_ENABLED or not _oauth:
        flash(request, "Google 로그인이 설정되지 않았습니다.", "error")
        return RedirectResponse("/login", status_code=302)
    redirect_uri = str(request.url_for("auth_google_callback"))
    return await _oauth.google.authorize_redirect(request, redirect_uri)


@app.get("/auth/google/callback", name="auth_google_callback")
async def auth_google_callback(request: Request):
    if not _GOOGLE_ENABLED or not _oauth:
        return RedirectResponse("/login", status_code=302)
    try:
        token     = await _oauth.google.authorize_access_token(request)
        user_info = token.get("userinfo") or {}
        google_id = user_info.get("sub")
        email     = (user_info.get("email") or "").lower()
        name      = user_info.get("name") or email.split("@")[0]
        picture   = user_info.get("picture")
    except Exception as e:
        flash(request, f"Google 로그인 오류: {e}", "error")
        return RedirectResponse("/login", status_code=302)

    with get_db() as conn:
        row = fetchone(conn, "SELECT * FROM users WHERE google_id=%s", (google_id,))
        if not row and email:
            row = fetchone(conn, "SELECT * FROM users WHERE email=%s", (email,))
            if row:
                execute(conn, "UPDATE users SET google_id=%s, avatar_url=COALESCE(avatar_url,%s) WHERE id=%s",
                        (google_id, picture, row["id"]))
                row = fetchone(conn, "SELECT * FROM users WHERE id=%s", (row["id"],))
        if not row:
            user_id = executereturning(conn, """
                INSERT INTO users (name, email, google_id, avatar_url)
                VALUES (%s, %s, %s, %s) RETURNING id
            """, (name, email, google_id, picture))
            row = fetchone(conn, "SELECT * FROM users WHERE id=%s", (str(user_id),))

    request.session["user_id"] = str(row["id"])
    # 캘린더 접근용 access_token 세션 저장
    try:
        access_token: str | None = token["access_token"]  # type: ignore[index]
    except Exception:
        access_token = None
    if access_token:
        request.session["google_access_token"] = access_token
    if not row.get("gender"):
        flash(request, f"환영합니다, {name}님! 프로필을 완성해주세요.", "success")
        return RedirectResponse("/profile", status_code=302)
    return RedirectResponse("/", status_code=302)


@app.get("/api/calendar", name="api_calendar")
async def api_calendar(request: Request):
    """이번 주 구글 캘린더 일정 반환. 구글 로그인 필요."""
    _require_user(request)
    access_token = request.session.get("google_access_token")
    if not access_token:
        return JSONResponse({"days": [], "error": "구글 로그인 필요"}, status_code=200)
    from chatbot.calendar_client import get_week_events, get_today_events, tpo_from_events
    days = get_week_events(access_token)
    # TPO는 오늘 일정 기준으로 추론
    today_events = get_today_events(access_token)
    auto_tpo = tpo_from_events(today_events)
    return JSONResponse({"days": days, "auto_tpo": auto_tpo})


@app.get("/logout", name="logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/login", status_code=302)


# ══════════════════════════════════════════════════════════════════
# 메인 라우트
# ══════════════════════════════════════════════════════════════════

@app.get("/", include_in_schema=False)
def root(request: Request):
    user = _get_user(request)
    if user.is_authenticated:
        return RedirectResponse("/dashboard", status_code=302)
    return RedirectResponse("/login", status_code=302)


@app.get("/dashboard", name="dashboard")
def dashboard(request: Request):
    user = _require_user(request)
    profile = load_profile(user.id)
    ph = "%s" if is_postgres() else "?"
    with get_db() as conn:
        wardrobe_items = fetchall(
            conn,
            f"SELECT * FROM wardrobe_items WHERE (user_id={ph} OR user_id IS NULL) ORDER BY created_at DESC",
            (user.id,)
        )
    return render(request, "dashboard.html", {
        "profile":        profile,
        "wardrobe_items": wardrobe_items,
        "db_engine":      db_engine(),
        "now":            datetime.now(),
    })


@app.get("/profile", name="profile")
def profile_get(request: Request):
    user = _require_user(request)
    return render(request, "profile.html", {"profile": load_profile(user.id)})


@app.post("/profile", name="profile_save")
async def profile_post(request: Request):
    user = _require_user(request)
    form = await request.form()

    data = {
        "name":        str(form.get("name", "")).strip(),
        "gender":      str(form.get("gender", "미입력")),
        "height":      str(form.get("height", "")),
        "weight":      str(form.get("weight", "")),
        "body_type":   str(form.get("body_type", "보통")),
        "style_pref":  str(form.get("style_pref", "캐주얼")),
        "sensitivity": str(form.get("sensitivity", "3")),
        "tpo":         str(form.get("tpo", "일상")),
        "nx":          str(form.get("nx", "62")),
        "ny":          str(form.get("ny", "123")),
    }
    uid = save_profile_data(data, user.id)

    avatar_file = form.get("avatar")
    if avatar_file and hasattr(avatar_file, "filename") and avatar_file.filename and allowed_file(avatar_file.filename):
        filename   = secure_filename(avatar_file.filename)
        timestamp  = datetime.now().strftime("%Y%m%d_%H%M%S_")
        local_path = os.path.join(UPLOAD_FOLDER, f"avatar_{timestamp}{filename}").replace("\\", "/")
        contents   = await avatar_file.read()
        with open(local_path, "wb") as f:
            f.write(contents)
        avatar_url = upload_image(local_path, user_id=uid, subfolder="profile")
        try:
            _save_avatar(uid, avatar_url)
        except Exception as e:
            try:
                delete_image(avatar_url)
            except Exception as cleanup_error:
                print(f"[Cloudinary cleanup 실패] {cleanup_error}")
            flash(request, f"프로필 사진 저장 중 오류가 발생했습니다. 다시 시도해주세요.", "error")
            return RedirectResponse("/profile", status_code=302)

    return RedirectResponse("/", status_code=302)


@app.get("/wardrobe", name="wardrobe")
def wardrobe(request: Request):
    user = _require_user(request)
    ph = "%s" if is_postgres() else "?"
    with get_db() as conn:
        items = fetchall(
            conn,
            f"SELECT * FROM wardrobe_items WHERE (user_id={ph} OR user_id IS NULL) ORDER BY category, created_at DESC",
            (user.id,)
        )
    categories = {"상의": [], "하의": [], "원피스": [], "아우터": []}
    for item in items:
        cat = item["category"]
        if cat in categories:
            categories[cat].append(item)
    return render(request, "wardrobe.html", {"categories": categories})


@app.post("/wardrobe/add", name="wardrobe_add")
async def wardrobe_add(request: Request):
    import asyncio
    user  = _require_user(request)
    form  = await request.form()
    files = form.getlist("image")

    valid_files = [
        f for f in files
        if hasattr(f, "filename") and f.filename and allowed_file(f.filename)
    ]
    if not valid_files:
        return RedirectResponse("/wardrobe", status_code=302)

    from model import analyze_outfit_batch
    errors = []

    # ── 1. 모든 파일 먼저 저장 ────────────────────────────────────────
    saved = []   # (local_path, orig_filename)
    for file in valid_files:
        filename   = secure_filename(file.filename)
        timestamp  = datetime.now().strftime("%Y%m%d_%H%M%S_")
        filename   = timestamp + filename
        local_path = os.path.join(UPLOAD_FOLDER, filename).replace("\\", "/")
        contents = await file.read()
        with open(local_path, "wb") as f:
            f.write(contents)
        saved.append((local_path, file.filename))

    # ── 2. 배치 분석 (한 번의 forward pass로 전체 처리 → 속도 개선) ──
    try:
        local_paths = [lp for lp, _ in saved]
        print(f"[wardrobe_add] 분석 시작: {len(local_paths)}장")
        results = await asyncio.to_thread(analyze_outfit_batch, local_paths)
        for fname, res in zip([os.path.basename(p) for p in local_paths], results):
            cat  = next((k for k in ["아우터","원피스","상의","하의"] if k in res), "?")
            item = res.get(cat, {}).get("item", "?") if cat != "?" else "?"
            print(f"[wardrobe_add] {fname[:30]} → 카테고리={cat}, 아이템={item}")
    except Exception as e:
        import traceback; traceback.print_exc()
        for lp, _ in saved:
            if os.path.exists(lp):
                os.remove(lp)
        flash(request, f"AI 분석 실패: {e}", "error")
        return RedirectResponse("/wardrobe", status_code=302)

    # ── 3. Cloudinary 업로드 → DB 저장 (순서 중요: 업로드 실패 시 DB 저장 안 함) ──
    for (local_path, orig_filename), result in zip(saved, results):
        try:
            category = next((k for k in ["아우터", "원피스", "상의", "하의"] if k in result), None)
            if category is None:
                raise ValueError("분류 결과에 카테고리가 없습니다.")

            item_info    = result[category]
            item_name    = str(item_info["item"])
            item_warmth  = int(item_info["warmth"])
            item_texture = str(item_info["texture"])

            # Cloudinary 업로드 (실패 시 RuntimeError → DB 저장 건너뜀)
            save_path = upload_image(
                local_path,
                user_id=user.id,
                subfolder="wardrobe",
                category=category,
                item_name=item_name,
            )

            # Cloudinary 성공 후에만 DB에 기록 (트랜잭션 보장)
            try:
                with get_db() as conn:
                    if is_postgres():
                        execute(conn, """
                            INSERT INTO wardrobe_items
                                (user_id, image_path, category, item_type, warmth, texture, created_at)
                            VALUES (%s, %s, %s, %s, %s, %s, NOW())
                        """, (user.id, save_path, category, item_name, item_warmth, item_texture))
                    else:
                        execute(conn, """
                            INSERT INTO wardrobe_items
                                (user_id, image_path, category, item_type, warmth, texture, created_at)
                            VALUES (?, ?, ?, ?, ?, ?, ?)
                        """, (user.id, save_path, category, item_name, item_warmth, item_texture,
                              datetime.now().isoformat()))
            except Exception as e:
                try:
                    delete_image(save_path)
                except Exception as cleanup_error:
                    print(f"[Cloudinary cleanup 실패] {cleanup_error}")
                if os.path.exists(local_path):
                    os.remove(local_path)
                errors.append(f"{orig_filename}: DB 저장 실패 — {e}")
                continue

        except RuntimeError as e:
            # Cloudinary 업로드 실패 → DB 저장 안 함
            if os.path.exists(local_path):
                os.remove(local_path)
            errors.append(f"{orig_filename}: 업로드 실패 — {e}")
        except Exception as e:
            import traceback; traceback.print_exc()
            if os.path.exists(local_path):
                os.remove(local_path)
            errors.append(f"{orig_filename}: 처리 실패 — {e}")

    if errors:
        flash(request, "일부 이미지 분석 오류: " + " / ".join(errors), "error")

    return RedirectResponse("/wardrobe", status_code=302)


@app.post("/wardrobe/move/{item_id}", name="wardrobe_move")
async def wardrobe_move(item_id: int, request: Request):
    _require_user(request)
    data         = await request.json()
    new_category = data.get("category")
    if new_category not in ["상의", "하의", "원피스", "아우터"]:
        return JSONResponse({"error": "invalid category"}, status_code=400)
    ph = "%s" if is_postgres() else "?"
    with get_db() as conn:
        execute(conn, f"UPDATE wardrobe_items SET category={ph} WHERE id={ph}", (new_category, item_id))
    return JSONResponse({"ok": True})


@app.post("/wardrobe/delete/{item_id}", name="wardrobe_delete")
def wardrobe_delete(item_id: int, request: Request):
    _require_user(request)
    ph = "%s" if is_postgres() else "?"
    with get_db() as conn:
        row = fetchone(conn, f"SELECT image_path FROM wardrobe_items WHERE id={ph}", (item_id,))
        if row:
            img_path = str(row["image_path"] or "")
            execute(conn, f"DELETE FROM wardrobe_items WHERE id={ph}", (item_id,))
            if img_path:
                remaining = fetchone(conn, f"SELECT id FROM wardrobe_items WHERE image_path={ph}", (img_path,))
                if remaining is None:
                    delete_image(img_path)
    return RedirectResponse("/wardrobe", status_code=302)


@app.get("/fashion-show", name="fashion_show")
def fashion_show(request: Request):
    _require_user(request)
    return render(request, "fashion_show.html")


# ══════════════════════════════════════════════════════════════════
# API 라우트
# ══════════════════════════════════════════════════════════════════

@app.post("/feedback/{log_id}", name="feedback")
async def feedback(log_id: int, request: Request):
    _require_user(request)
    data     = await request.json()
    score    = data.get("score")
    text     = data.get("text", "")
    was_worn = data.get("was_worn")
    save_feedback(log_id, score, text, was_worn)
    return JSONResponse({"status": "ok", "log_id": log_id})


@app.post("/chat", name="chat")
async def chat(request: Request):
    _require_user(request)
    data    = await request.json()
    message = data.get("message", "")
    context = data.get("context", {})
    history = data.get("history", [])
    if not message:
        return JSONResponse({"error": "메시지가 없어요"}, status_code=400)
    try:
        from chatbot.llm_client import get_chatbot_response
        reply = get_chatbot_response(message, context, history)
        return JSONResponse({"reply": reply})
    except Exception as e:
        return JSONResponse({"reply": f"(오류: {e})"}, status_code=500)


@app.post("/api/tts", name="api_tts")
async def api_tts(request: Request):
    _require_user(request)
    data = await request.json()
    text = data.get("text", "").strip()
    if not text:
        return JSONResponse({"error": "text is required"}, status_code=400)
    try:
        import base64
        from chatbot.tts import clean_for_tts, synthesize_speech
        cleaned = clean_for_tts(text)
        pcm = await synthesize_speech(cleaned)
        if not pcm:
            return JSONResponse({"error": "TTS 실패"}, status_code=500)
        return JSONResponse({"audio": base64.b64encode(pcm).decode()})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/weather", name="api_weather")
def api_weather(request: Request):
    user    = _require_user(request)
    profile = load_profile(user.id)
    try:
        from chatbot.weather_client import get_weather
        nx = int(profile.get("location_nx") or profile.get("nx") or 62)
        ny = int(profile.get("location_ny") or profile.get("ny") or 123)
        return JSONResponse(get_weather(nx=nx, ny=ny))
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/recommend", name="api_recommend")
async def api_recommend(request: Request, quick: bool = False):
    """
    quick=true  → 날씨·스타일·옷장 매칭만 반환 (AI 코멘트 생략, ~1s)
    quick=false → 전체 반환 (AI 코멘트 포함, ~4s)
    프론트에서 quick=true 먼저 호출 → 날씨/스타일 즉시 표시,
    그다음 full 호출 → 디자이너 코멘트 표시
    """
    import asyncio
    user    = _require_user(request)
    profile = load_profile(user.id)
    try:
        from chatbot.weather_client import get_weather
        from chatbot.weather_style_mapper import get_style_recommendation, get_layering_recommendation
        from chatbot.llm_client import get_outfit_comment

        sensitivity = int(profile.get("sensitivity", 3))
        tpo         = profile.get("tpo", "일상")
        style_pref  = (profile or {}).get("style_pref", "캐주얼")
        nx = int(profile.get("location_nx") or profile.get("nx") or 62)
        ny = int(profile.get("location_ny") or profile.get("ny") or 123)

        ph = "%s" if is_postgres() else "?"
        with get_db() as conn:
            user_items = fetchall(
                conn,
                f"SELECT id, category, item_type, warmth, texture, image_path "
                f"FROM wardrobe_items WHERE user_id={ph} ORDER BY created_at DESC",
                (user.id,)
            )

        cache_key      = f"{user.id},{nx},{ny},{tpo},{sensitivity},{len(user_items)}"
        cache_key_full = cache_key + ",full"
        cached_full    = _recommend_cache.get(cache_key_full)
        if cached_full and time.time() - cached_full["ts"] < _CACHE_TTL:
            return JSONResponse(cached_full["data"])

        # ── 날씨는 항상 필요 ─────────────────────────────────────────
        cached_quick = _recommend_cache.get(cache_key)
        if cached_quick and time.time() - cached_quick["ts"] < _CACHE_TTL:
            weather = cached_quick["data"]["weather"]
        else:
            weather = await asyncio.to_thread(get_weather, nx=nx, ny=ny)

        style_rec = get_style_recommendation(
            weather["morning"]["feels_like"], weather["morning"]["reh"],
            weather["morning"]["sky"], weather["morning"]["pty"], sensitivity
        )
        layering = get_layering_recommendation(weather, sensitivity)

        temp_range  = style_rec.get("temp_range", "mild")
        top_min     = _TOP_WARMTH_MIN.get(temp_range, 0)
        needs_outer = temp_range in _NEEDS_OUTER

        wardrobe_matches = {"상의": [], "하의": [], "아우터": []}
        for item in user_items:
            cat      = item.get("category")
            img_path = item.get("image_path", "")
            if cat not in wardrobe_matches or not img_path:
                continue
            img_url = img_url_filter(img_path)
            entry   = {"id": item["id"], "item_type": item["item_type"],
                       "warmth": item.get("warmth", 0), "image_url": img_url}
            warmth  = item.get("warmth", 0)
            if cat == "아우터" and needs_outer:
                wardrobe_matches["아우터"].append(entry)
            elif cat == "상의" and warmth >= top_min:
                wardrobe_matches["상의"].append(entry)
            elif cat == "하의":
                wardrobe_matches["하의"].append(entry)

        for cat in wardrobe_matches:
            wardrobe_matches[cat] = wardrobe_matches[cat][:3]

        categories_needed = ["상의", "하의"]
        if needs_outer:
            categories_needed.append("아우터")
        shopping_fallback = []
        for cat in categories_needed:
            if not wardrobe_matches.get(cat):
                query = make_shopping_query(cat, style_pref, profile.get("gender", "여성"))
                shopping_fallback.append({
                    "category": cat,
                    "search_query": query,
                    "search_url": make_musinsa_search_url(query),
                })

        quick_result = {
            "weather": weather, "style_rec": style_rec, "layering": layering,
            "wardrobe_matches": wardrobe_matches,
            "shopping_fallback": shopping_fallback,
        }
        _recommend_cache[cache_key] = {"data": quick_result, "ts": time.time()}

        # quick=true 이면 AI 코멘트 없이 즉시 반환
        if quick:
            return JSONResponse(quick_result)

        # ── AI 코멘트 로드 ───────────────────────────────────────────
        wardrobe_for_ai = [
            {"category": it["category"], "item_type": it["item_type"],
             "warmth": it.get("warmth", 0), "texture": it.get("texture", "미상")}
            for it in user_items
        ]

        # 캘린더 일정 가져오기 (구글 로그인 시에만)
        calendar_events: "list[dict]" = []
        g_token = request.session.get("google_access_token")
        if g_token:
            from chatbot.calendar_client import get_today_events, tpo_from_events  # type: ignore[import]
            _evs: "list[dict]" = await asyncio.to_thread(get_today_events, g_token)  # type: ignore[arg-type]
            calendar_events = _evs
            _detected: "str | None" = tpo_from_events(_evs)  # type: ignore[arg-type]
            if _detected:
                tpo = _detected

        trend_news: list = []
        outfit_result = await asyncio.to_thread(
            get_outfit_comment, weather, style_rec, layering, str(tpo),  # type: ignore[arg-type]
            profile or None, wardrobe_for_ai, trend_news, calendar_events
        )
        comment = outfit_result.get("comment", "") if isinstance(outfit_result, dict) else outfit_result
        bubbles = outfit_result.get("bubbles", {}) if isinstance(outfit_result, dict) else {}

        save_style_log(user.id, weather, style_rec, layering, comment, tpo)

        user_profile_data = {
            "name":        profile.get("name", ""),
            "sensitivity": int(profile.get("sensitivity", 3)),
            "height":      profile.get("height", ""),
            "weight":      profile.get("weight", ""),
            "body_type":   profile.get("body_type", "보통"),
            "style_pref":  profile.get("style_pref", "캐주얼"),
            "gender":      profile.get("gender", ""),
            "tpo":         profile.get("tpo", "일상"),
        }
        full_result = {**quick_result, "comment": comment, "bubbles": bubbles,
                       "user_profile": user_profile_data}
        _recommend_cache[cache_key_full] = {"data": full_result, "ts": time.time()}
        return JSONResponse(full_result)
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/wardrobe", name="api_wardrobe")
def api_wardrobe(request: Request):
    """
    챗봇·개인화 엔진용 옷장 데이터 API.
    로그인한 유저 본인 옷만 반환.
    카테고리별로 그룹화하여 반환.
    """
    user = _require_user(request)
    ph = "%s" if is_postgres() else "?"
    with get_db() as conn:
        items = fetchall(
            conn,
            f"SELECT id, category, item_type, warmth, texture, image_path, created_at "
            f"FROM wardrobe_items WHERE (user_id={ph} OR user_id IS NULL) ORDER BY category, created_at DESC",
            (user.id,)
        )
    grouped: dict = {"상의": [], "하의": [], "원피스": [], "아우터": []}
    for item in items:
        cat = item.get("category", "")
        if cat in grouped:
            grouped[cat].append({
                "id":        item["id"],
                "item_type": item["item_type"],
                "warmth":    item.get("warmth", 0),
                "texture":   item.get("texture", ""),
                "image_url": img_url_filter(str(item.get("image_path") or "")),
            })
    return JSONResponse({
        "user_id":    user.id,
        "total":      len(items),
        "categories": grouped,
    })


@app.get("/api/shopping", name="api_shopping")
async def api_shopping(request: Request):
    import asyncio
    user    = _require_user(request)
    profile = load_profile(user.id)
    try:
        from chatbot.shopping import get_shopping_cards
        from chatbot.weather_client import get_weather
        from chatbot.weather_style_mapper import get_style_recommendation

        sensitivity = int(profile.get("sensitivity", 3))
        style_pref  = (profile or {}).get("style_pref", "캐주얼")
        nx = int(profile.get("location_nx") or profile.get("nx") or 62)
        ny = int(profile.get("location_ny") or profile.get("ny") or 123)

        ph = "%s" if is_postgres() else "?"
        with get_db() as conn:
            wardrobe_items = fetchall(
                conn,
                f"SELECT category, item_type, warmth, texture FROM wardrobe_items "
                f"WHERE user_id={ph} ORDER BY created_at DESC",
                (user.id,)
            )
            if not wardrobe_items:
                wardrobe_items = fetchall(
                    conn,
                    "SELECT category, item_type, warmth, texture FROM wardrobe_items "
                    "WHERE user_id IS NULL ORDER BY created_at DESC"
                )

        # 날씨 캐시 활용 (recommend API가 먼저 호출된 경우 재사용)
        cache_key    = f"{user.id},{nx},{ny}"
        cached_quick = next(
            (v for k, v in _recommend_cache.items() if k.startswith(cache_key)),
            None
        )
        if cached_quick and time.time() - cached_quick["ts"] < _CACHE_TTL:
            weather = cached_quick["data"]["weather"]
        else:
            weather = await asyncio.to_thread(get_weather, nx=nx, ny=ny)

        style_rec = get_style_recommendation(
            weather["morning"]["feels_like"], weather["morning"]["reh"],
            weather["morning"]["sky"], weather["morning"]["pty"], sensitivity
        )

        # 쇼핑카드 생성
        cards = await asyncio.to_thread(
            get_shopping_cards, all_items, style_rec, profile or None, []
        )
        return JSONResponse({"cards": cards})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)


# ══════════════════════════════════════════════════════════════════
# 이미지 프록시 (same-origin canvas 색상 추출용)
# ══════════════════════════════════════════════════════════════════

@app.get("/proxy/image", name="proxy_image")
async def proxy_image(url: str):
    """Cloudinary 이미지를 same-origin으로 프록시 → canvas getImageData 허용"""
    import httpx
    from fastapi.responses import Response as RawResponse
    if not url.startswith("https://res.cloudinary.com/"):
        return JSONResponse({"error": "허용되지 않는 URL"}, status_code=400)
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(url)
        return RawResponse(
            content=r.content,
            media_type=r.headers.get("content-type", "image/jpeg"),
            headers={"Cache-Control": "public, max-age=3600"},
        )
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=502)


# ══════════════════════════════════════════════════════════════════
# 실행
# ══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import uvicorn
    print("서버 실행 중: http://127.0.0.1:5000")
    uvicorn.run("app:app", host="0.0.0.0", port=5000, reload=True)
