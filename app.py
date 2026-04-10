"""
app.py — 내 옷장의 코디 Flask 웹 대시보드
라우트:
  GET  /                    → 대시보드 (날씨 + 오늘 코디 + 챗봇)
  GET  /profile             → 개인정보 입력 페이지
  POST /profile             → 개인정보 저장
  GET  /wardrobe            → 옷장 목록
  POST /wardrobe/add        → 옷 이미지 업로드 & 분석
  POST /wardrobe/delete/<id>→ 옷 삭제
  POST /feedback/<log_id>   → 코디 피드백 저장 (모델 개선용)
  POST /chat                → 챗봇 API (JSON)
  GET  /api/weather         → 현재 날씨 JSON
  GET  /api/recommend       → 코디 추천 JSON
"""

from flask import Flask, render_template, request, redirect, url_for, jsonify, session, flash
import os
import json
import time
from datetime import datetime
from dotenv import load_dotenv
from werkzeug.utils import secure_filename

# db.py: PostgreSQL(Docker) 또는 SQLite(로컬) 자동 선택
from db import get_db, fetchall, fetchone, execute, executereturning, \
               save_style_log, save_feedback, is_postgres, db_engine

load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", os.urandom(24))

UPLOAD_FOLDER = "static/uploads"
ALLOWED_EXT   = {"jpg", "jpeg", "png"}
PROFILE_PATH  = "user_profile.json"    # SQLite 환경용 폴백

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

# ── 날씨/AI 추천 캐시 (30분) ──────────────────────
_dashboard_cache = {"data": None, "ts": 0}
CACHE_TTL = 30 * 60  # 30분


# ── 유틸 ──────────────────────────────────────────────────────────
def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXT


def init_db():
    """SQLite 환경에서만 테이블 생성 (PostgreSQL은 init.sql로 처리)"""
    if is_postgres():
        print(f"[DB] {db_engine()} 연결됨")
        return
    with get_db() as conn:
        execute(conn, """
            CREATE TABLE IF NOT EXISTS wardrobe_items (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     TEXT,
                image_path  TEXT,
                category    TEXT,
                item_type   TEXT,
                warmth      INTEGER DEFAULT 1,
                texture     TEXT,
                created_at  TEXT
            )
        """)
        execute(conn, """
            CREATE TABLE IF NOT EXISTS users (
                id          TEXT PRIMARY KEY,
                name        TEXT, gender TEXT, height INTEGER, weight INTEGER,
                body_type   TEXT, style_pref TEXT, sensitivity INTEGER DEFAULT 3,
                tpo TEXT DEFAULT '일상', location_nx INTEGER DEFAULT 62,
                location_ny INTEGER DEFAULT 123, created_at TEXT, updated_at TEXT
            )
        """)
    print(f"[DB] {db_engine()} 초기화 완료")


# ── 사용자 프로필 로드/저장 ────────────────────────────────────────
def load_profile(user_id=None) -> dict:
    if is_postgres():
        if not user_id:
            # 임시: 첫 번째 사용자 로드 (나중에 로그인 기능으로 대체)
            with get_db() as conn:
                row = fetchone(conn, "SELECT * FROM users LIMIT 1")
                return dict(row) if row else {}
        with get_db() as conn:
            row = fetchone(conn, "SELECT * FROM users WHERE id=%s", (user_id,))
            return dict(row) if row else {}
    else:
        if os.path.exists(PROFILE_PATH):
            with open(PROFILE_PATH, "r", encoding="utf-8") as f:
                return json.load(f)
        return {}


def save_profile_data(data: dict) -> str:
    if is_postgres():
        with get_db() as conn:
            existing = fetchone(conn, "SELECT id FROM users LIMIT 1")
            if existing:
                user_id = existing["id"]
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
                    user_id
                ))
            else:
                user_id = executereturning(conn, """
                    INSERT INTO users
                        (name, gender, height, weight, body_type, style_pref,
                         sensitivity, tpo, location_nx, location_ny)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    RETURNING id
                """, (
                    data["name"], data["gender"],
                    int(data["height"]) if data["height"] else None,
                    int(data["weight"]) if data["weight"] else None,
                    data["body_type"], data["style_pref"],
                    int(data["sensitivity"]), data["tpo"],
                    int(data["nx"]), int(data["ny"])
                ))
        return str(user_id)
    else:
        with open(PROFILE_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return "local"


# ── 라우트 ────────────────────────────────────────────────────────
@app.route("/")
def dashboard():
    global _dashboard_cache
    profile = load_profile()

    # ── 캐시 확인 (30분) ──────────────────────────
    now_ts = time.time()
    cached = _dashboard_cache["data"]
    if cached and (now_ts - _dashboard_cache["ts"]) < CACHE_TTL:
        weather_chatbot = cached["weather"]
        style_rec       = cached["style_rec"]
        layering        = cached["layering"]
        ai_comment      = cached["ai_comment"]
        style_log_id    = cached["style_log_id"]
    else:
        weather_chatbot = None
        style_rec       = None
        layering        = None
        ai_comment      = None
        style_log_id    = None

        try:
            from chatbot.weather_client import get_weather as get_weather_chatbot
            from chatbot.weather_style_mapper import get_style_recommendation, get_layering_recommendation
            from chatbot.llm_client import get_outfit_comment

            sensitivity = int(profile.get("sensitivity", 3))
            tpo         = profile.get("tpo", "일상")
            nx          = int(profile.get("location_nx") or profile.get("nx") or 62)
            ny          = int(profile.get("location_ny") or profile.get("ny") or 123)

            weather_chatbot = get_weather_chatbot(nx=nx, ny=ny)
            style_rec = get_style_recommendation(
                weather_chatbot["morning"]["feels_like"],
                weather_chatbot["morning"]["reh"],
                weather_chatbot["morning"]["sky"],
                weather_chatbot["morning"]["pty"],
                sensitivity
            )
            layering   = get_layering_recommendation(weather_chatbot, sensitivity)
            ai_comment = get_outfit_comment(
                weather_chatbot, style_rec, layering, tpo,
                profile if profile else None
            )

            # 추천 결과 DB 저장 (누적)
            user_id = profile.get("id")
            style_log_id = save_style_log(
                user_id, weather_chatbot, style_rec, layering, ai_comment, tpo
            )

            # 캐시 저장
            _dashboard_cache["data"] = {
                "weather": weather_chatbot, "style_rec": style_rec,
                "layering": layering, "ai_comment": ai_comment,
                "style_log_id": style_log_id
            }
            _dashboard_cache["ts"] = now_ts

        except Exception as e:
            ai_comment = f"(날씨/AI 연결 오류: {e})"

    # 옷장 아이템
    with get_db() as conn:
        wardrobe_items = fetchall(
            conn,
            "SELECT * FROM wardrobe_items ORDER BY created_at DESC"
        )

    return render_template("dashboard.html",
        profile=profile,
        weather=weather_chatbot,
        style_rec=style_rec,
        layering=layering,
        ai_comment=ai_comment,
        wardrobe_items=wardrobe_items,
        style_log_id=style_log_id,
        db_engine=db_engine(),
        now=datetime.now()
    )


@app.route("/profile", methods=["GET", "POST"])
def profile():
    if request.method == "POST":
        data = {
            "name":        request.form.get("name", "").strip(),
            "gender":      request.form.get("gender", "미입력"),
            "height":      request.form.get("height", ""),
            "weight":      request.form.get("weight", ""),
            "body_type":   request.form.get("body_type", "보통"),
            "style_pref":  request.form.get("style_pref", "캐주얼"),
            "sensitivity": request.form.get("sensitivity", "3"),
            "tpo":         request.form.get("tpo", "일상"),
            "nx":          request.form.get("nx", "62"),
            "ny":          request.form.get("ny", "123"),
        }
        save_profile_data(data)
        return redirect(url_for("dashboard"))

    profile_data = load_profile()
    return render_template("profile.html", profile=profile_data)


@app.route("/wardrobe")
def wardrobe():
    with get_db() as conn:
        items = fetchall(
            conn,
            "SELECT * FROM wardrobe_items ORDER BY category, created_at DESC"
        )
    categories = {"상의": [], "하의": [], "원피스": [], "아우터": []}
    for item in items:
        cat = item["category"]
        if cat in categories:
            categories[cat].append(item)
    return render_template("wardrobe.html", categories=categories)


@app.route("/wardrobe/add", methods=["POST"])
def wardrobe_add():
    if "image" not in request.files:
        return redirect(url_for("wardrobe"))

    files = [f for f in request.files.getlist("image")
             if f.filename != "" and allowed_file(f.filename)]
    if not files:
        return redirect(url_for("wardrobe"))

    profile = load_profile()
    user_id = profile.get("id")
    errors  = []

    for file in files:
        filename  = secure_filename(file.filename)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_")
        filename  = timestamp + filename
        save_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
        file.save(save_path)

        try:
            from model import analyze_outfit
            result = analyze_outfit(save_path)

            with get_db() as conn:
                for category in ["상의", "하의", "아우터"]:
                    info = result[category]
                    if info["item"] == "없음":
                        continue
                    # dress는 하의가 아닌 원피스로 저장
                    save_category = "원피스" if info["item"] == "dress" else category
                    if is_postgres():
                        execute(conn, """
                            INSERT INTO wardrobe_items
                                (user_id, image_path, category, item_type, warmth, texture, created_at)
                            VALUES (%s, %s, %s, %s, %s, %s, NOW())
                        """, (user_id, save_path, save_category, info["item"],
                              info["warmth"], info["texture"]))
                    else:
                        execute(conn, """
                            INSERT INTO wardrobe_items
                                (user_id, image_path, category, item_type, warmth, texture, created_at)
                            VALUES (?, ?, ?, ?, ?, ?, ?)
                        """, (user_id, save_path, save_category, info["item"],
                              info["warmth"], info["texture"], datetime.now().isoformat()))
        except Exception as e:
            import traceback
            traceback.print_exc()
            errors.append(f"{file.filename}: {e}")

    if errors:
        flash("일부 이미지 분석 오류: " + " / ".join(errors), "error")

    return redirect(url_for("wardrobe"))


@app.route("/wardrobe/move/<int:item_id>", methods=["POST"])
def wardrobe_move(item_id):
    """옷 카테고리 변경 (드래그&드롭)"""
    data = request.get_json()
    new_category = data.get("category")
    if new_category not in ["상의", "하의", "원피스", "아우터"]:
        return jsonify({"error": "invalid category"}), 400
    ph = "%s" if is_postgres() else "?"
    with get_db() as conn:
        execute(conn, f"UPDATE wardrobe_items SET category={ph} WHERE id={ph}", (new_category, item_id))
    return jsonify({"ok": True})


@app.route("/wardrobe/delete/<int:item_id>", methods=["POST"])
def wardrobe_delete(item_id):
    ph = "%s" if is_postgres() else "?"
    with get_db() as conn:
        row = fetchone(conn, f"SELECT image_path FROM wardrobe_items WHERE id={ph}", (item_id,))
        if row:
            img_path = row.get("image_path", "")
            # 같은 image_path로 등록된 모든 행 한 번에 삭제
            if img_path:
                execute(conn, f"DELETE FROM wardrobe_items WHERE image_path={ph}", (img_path,))
                if os.path.exists(img_path) and "uploads" in img_path:
                    os.remove(img_path)
            else:
                execute(conn, f"DELETE FROM wardrobe_items WHERE id={ph}", (item_id,))
    return redirect(url_for("wardrobe"))


@app.route("/feedback/<int:log_id>", methods=["POST"])
def feedback(log_id):
    """
    코디 피드백 저장 — 누적 데이터로 모델 개선
    """
    data     = request.get_json()
    score    = data.get("score")
    text     = data.get("text", "")
    was_worn = data.get("was_worn")

    save_feedback(log_id, score, text, was_worn)
    return jsonify({"status": "ok", "log_id": log_id})


@app.route("/chat", methods=["POST"])
def chat():
    data    = request.get_json()
    message = data.get("message", "")
    context = data.get("context", {})

    if not message:
        return jsonify({"error": "메시지가 없어요"}), 400

    try:
        from chatbot.llm_client import get_chatbot_response
        reply = get_chatbot_response(message, context)
        return jsonify({"reply": reply})
    except Exception as e:
        return jsonify({"reply": f"(오류: {e})"}), 500


@app.route("/api/weather")
def api_weather():
    profile = load_profile()
    try:
        from chatbot.weather_client import get_weather
        nx = int(profile.get("location_nx") or profile.get("nx") or 62)
        ny = int(profile.get("location_ny") or profile.get("ny") or 123)
        weather = get_weather(nx=nx, ny=ny)
        return jsonify(weather)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/recommend")
def api_recommend():
    profile = load_profile()
    try:
        from chatbot.weather_client import get_weather
        from chatbot.weather_style_mapper import get_style_recommendation, get_layering_recommendation
        from chatbot.llm_client import get_outfit_comment

        sensitivity = int(profile.get("sensitivity", 3))
        tpo         = profile.get("tpo", "일상")
        nx = int(profile.get("location_nx") or profile.get("nx") or 62)
        ny = int(profile.get("location_ny") or profile.get("ny") or 123)

        weather   = get_weather(nx=nx, ny=ny)
        style_rec = get_style_recommendation(
            weather["morning"]["feels_like"], weather["morning"]["reh"],
            weather["morning"]["sky"], weather["morning"]["pty"], sensitivity
        )
        layering  = get_layering_recommendation(weather, sensitivity)
        comment   = get_outfit_comment(weather, style_rec, layering, tpo, profile or None)

        return jsonify({
            "weather":   weather,
            "style_rec": style_rec,
            "layering":  layering,
            "comment":   comment,
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    init_db()
    # Docker 환경에서 reloader=False: reloader가 두 번째 프로세스 spawn하여 주소창 두 개 뜨는 문제 방지
    app.run(debug=True, host="0.0.0.0", port=5000, use_reloader=False)
