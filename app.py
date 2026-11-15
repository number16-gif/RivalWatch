"""Локальный Flask-интерфейс RivalWatch."""
import hmac
import logging
import re
import secrets
import sqlite3
from contextlib import closing

from flask import (Flask, abort, flash, g, redirect, render_template,
                   request, session, url_for)
from werkzeug.security import check_password_hash, generate_password_hash

from database import connect, init_db, now_iso
from engine import check_page, validate_public_url
from settings import DEMO_PATH, get_secret_key

logging.basicConfig(filename="rivalwatch.log", level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s")


def create_app(testing=False):
    app = Flask(__name__)
    app.config.update(
        SECRET_KEY=get_secret_key(),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        MAX_CONTENT_LENGTH=16384,
        TESTING=testing,
    )
    init_db()

    @app.context_processor
    def inject_csrf():
        def csrf_token():
            if "csrf_token" not in session:
                session["csrf_token"] = secrets.token_hex(24)
            return session["csrf_token"]
        return {"csrf_token": csrf_token}

    @app.before_request
    def before_request():
        if request.method == "POST":
            expected = session.get("csrf_token", "")
            supplied = request.form.get("csrf_token", "")
            if not expected or not hmac.compare_digest(expected, supplied):
                abort(400, "Неверный CSRF-токен. Обнови страницу.")
        g.user = None
        uid = session.get("user_id")
        if uid:
            with closing(connect()) as db:
                g.user = db.execute(
                    "SELECT id,username,telegram_chat_id FROM users WHERE id=?", (uid,)
                ).fetchone()

    @app.after_request
    def set_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; object-src 'none'; frame-ancestors 'none';"
            " base-uri 'self'; form-action 'self'"
        )
        response.headers["Cache-Control"] = "no-store"
        return response

    def require_user():
        return redirect(url_for("login")) if g.user is None else None

    def owned_page(db, page_id):
        page = db.execute(
            "SELECT * FROM pages WHERE id=? AND user_id=?",
            (page_id, g.user["id"]),
        ).fetchone()
        if page is None:
            abort(404)
        return page

    @app.route("/")
    def index():
        if response := require_user():
            return response
        with closing(connect()) as db:
            pages = db.execute(
                "SELECT * FROM pages WHERE user_id=? ORDER BY id DESC",
                (g.user["id"],),
            ).fetchall()
            changes = db.execute(
                """SELECT COUNT(*) AS count FROM events e
                   JOIN pages p ON p.id=e.page_id WHERE p.user_id=?""",
                (g.user["id"],),
            ).fetchone()["count"]
            runs = db.execute(
                """SELECT r.*,p.url FROM runs r JOIN pages p ON p.id=r.page_id
                   WHERE p.user_id=? ORDER BY r.id DESC LIMIT 8""",
                (g.user["id"],),
            ).fetchall()
        return render_template("dashboard.html", pages=pages, changes=changes, runs=runs)

    @app.route("/register", methods=["GET", "POST"])
    def register():
        if g.user:
            return redirect(url_for("index"))
        if request.method == "POST":
            username = request.form.get("username", "").strip().lower()
            password = request.form.get("password", "")
            if not re.fullmatch(r"[a-z0-9_]{3,30}", username):
                flash("Логин: 3–30 латинских букв, цифр или _", "error")
            elif not 10 <= len(password) <= 128:
                flash("Пароль должен содержать 10–128 символов", "error")
            else:
                with closing(connect()) as db:
                    try:
                        cursor = db.execute(
                            "INSERT INTO users(username,password_hash,created_at) VALUES(?,?,?)",
                            (username, generate_password_hash(password), now_iso()),
                        )
                        uid = cursor.lastrowid
                        if db.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 1:
                            db.execute(
                                "UPDATE pages SET user_id=?,next_check_at=? WHERE user_id IS NULL",
                                (uid, now_iso()),
                            )
                        db.commit()
                    except sqlite3.IntegrityError:
                        flash("Такой логин уже занят", "error")
                    else:
                        session.clear()
                        session["user_id"] = uid
                        return redirect(url_for("index"))
        return render_template("auth.html", register=True)

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if g.user:
            return redirect(url_for("index"))
        if request.method == "POST":
            username = request.form.get("username", "").strip().lower()
            password = request.form.get("password", "")
            with closing(connect()) as db:
                user = db.execute(
                    "SELECT * FROM users WHERE username=?", (username,)
                ).fetchone()
            if user and check_password_hash(user["password_hash"], password):
                session.clear()
                session["user_id"] = user["id"]
                return redirect(url_for("index"))
            flash("Неправильный логин или пароль", "error")
        return render_template("auth.html", register=False)

    @app.post("/logout")
    def logout():
        session.clear()
        return redirect(url_for("login"))

    @app.post("/pages/add")
    def add_page():
        if response := require_user():
            return response
        url = request.form.get("url", "").strip()
        title = request.form.get("title", "").strip()[:80]
        try:
            interval = int(request.form.get("interval_hours", "6"))
            if interval not in (6, 12, 24, 48):
                raise ValueError("Выбери допустимый интервал")
            if url == "demo://example":
                raise ValueError("Для демо есть отдельная кнопка")
            if len(url) > 1500:
                raise ValueError("Слишком длинный URL")
            validate_public_url(url)
            with closing(connect()) as db:
                if db.execute(
                    "SELECT COUNT(*) AS n FROM pages WHERE user_id=?", (g.user["id"],)
                ).fetchone()["n"] >= 20:
                    raise ValueError("В учебной версии максимум 20 страниц")
                db.execute(
                    """INSERT INTO pages(user_id,url,title,interval_hours,next_check_at,created_at)
                       VALUES(?,?,?,?,?,?)""",
                    (g.user["id"], url, title, interval, now_iso(), now_iso()),
                )
                db.commit()
            flash("Страница добавлена", "success")
        except (ValueError, sqlite3.IntegrityError) as exc:
            flash(f"Не удалось добавить: {exc}", "error")
        return redirect(url_for("index"))

    @app.post("/demo/add")
    def demo_add():
        if response := require_user():
            return response
        if not DEMO_PATH.exists():
            DEMO_PATH.write_text(
                "<!doctype html><html><body><main><h1>Демо</h1>"
                "<p>Цена: 1000 рублей</p></main></body></html>",
                encoding="utf-8",
            )
        with closing(connect()) as db:
            if not db.execute(
                "SELECT 1 FROM pages WHERE user_id=? AND url=?",
                (g.user["id"], "demo://example"),
            ).fetchone():
                db.execute(
                    """INSERT INTO pages(user_id,url,title,interval_hours,next_check_at,created_at)
                       VALUES(?,?,?,6,?,?)""",
                    (g.user["id"], "demo://example", "Демостраница", now_iso(), now_iso()),
                )
                db.commit()
        flash("Демо добавлено", "success")
        return redirect(url_for("index"))

    @app.get("/pages/<int:page_id>")
    def page_detail(page_id):
        if response := require_user():
            return response
        with closing(connect()) as db:
            page = owned_page(db, page_id)
            events = db.execute(
                "SELECT * FROM events WHERE page_id=? ORDER BY id DESC LIMIT 20",
                (page_id,),
            ).fetchall()
            runs = db.execute(
                "SELECT * FROM runs WHERE page_id=? ORDER BY id DESC LIMIT 20",
                (page_id,),
            ).fetchall()
        return render_template("page.html", page=page, events=events, runs=runs)

    @app.post("/pages/<int:page_id>/check")
    def check_now(page_id):
        if response := require_user():
            return response
        with closing(connect()) as db:
            owned_page(db, page_id)
        flash(check_page(page_id, force=True), "success")
        return redirect(url_for("page_detail", page_id=page_id))

    @app.post("/pages/<int:page_id>/update")
    def update_page(page_id):
        if response := require_user():
            return response
        with closing(connect()) as db:
            owned_page(db, page_id)
            try:
                interval = int(request.form.get("interval_hours", "6"))
            except ValueError:
                interval = 0
            if interval not in (6, 12, 24, 48):
                flash("Недопустимый интервал", "error")
            else:
                title = request.form.get("title", "").strip()[:80]
                db.execute(
                    "UPDATE pages SET title=?,interval_hours=? WHERE id=?",
                    (title, interval, page_id),
                )
                db.commit()
                flash("Изменения сохранены", "success")
        return redirect(url_for("page_detail", page_id=page_id))

    @app.post("/pages/<int:page_id>/toggle")
    def toggle_page(page_id):
        if response := require_user():
            return response
        with closing(connect()) as db:
            page = owned_page(db, page_id)
            db.execute(
                "UPDATE pages SET enabled=?,next_check_at=? WHERE id=?",
                (0 if page["enabled"] else 1, now_iso(), page_id),
            )
            db.commit()
        return redirect(url_for("page_detail", page_id=page_id))

    @app.post("/pages/<int:page_id>/delete")
    def delete_page(page_id):
        if response := require_user():
            return response
        with closing(connect()) as db:
            owned_page(db, page_id)
            db.execute(
                "DELETE FROM pages WHERE id=? AND user_id=?",
                (page_id, g.user["id"]),
            )
            db.commit()
        flash("Страница удалена", "success")
        return redirect(url_for("index"))

    @app.route("/settings", methods=["GET", "POST"])
    def settings():
        if response := require_user():
            return response
        if request.method == "POST":
            chat_id = request.form.get("telegram_chat_id", "").strip()
            if chat_id and not re.fullmatch(r"-?\d{5,20}", chat_id):
                flash("Chat ID должен состоять из цифр", "error")
            else:
                with closing(connect()) as db:
                    db.execute(
                        "UPDATE users SET telegram_chat_id=? WHERE id=?",
                        (chat_id or None, g.user["id"]),
                    )
                    db.commit()
                flash("Настройки сохранены", "success")
                return redirect(url_for("settings"))
        return render_template("settings.html")

    return app


if __name__ == "__main__":
    create_app().run(host="127.0.0.1", port=5000, debug=False)
