import os
import secrets
import time
from flask import Flask, render_template, request, redirect, session, abort
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)

# 生产环境由环境变量提供；缺失时生成临时密钥，服务重启后旧会话会失效。
app.secret_key = os.environ.get("FLASK_SECRET_KEY", secrets.token_urlsafe(32))
app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
)

# 不在源代码保存明文密码。启动前需要设置这两个环境变量。
admin_password = os.environ.get("ADMIN_PASSWORD")
alice_password = os.environ.get("ALICE_PASSWORD")
if not admin_password or not alice_password:
    raise RuntimeError("请先设置 ADMIN_PASSWORD 和 ALICE_PASSWORD 环境变量")

USERS = {
    "admin": {
        "password_hash": generate_password_hash(admin_password),
        "role": "admin",
        "email": "admin@example.com",
        "phone": "13800138000",
        "balance": 99999,
    },
    "alice": {
        "password_hash": generate_password_hash(alice_password),
        "role": "user",
        "email": "alice@example.com",
        "phone": "13900139001",
        "balance": 100,
    },
}

# 简单的内存登录失败限制：连续失败 5 次，锁定 10 分钟。
MAX_LOGIN_FAILURES = 5
LOCKOUT_SECONDS = 600
login_attempts = {}


def public_user_info(username):
    user = USERS[username]
    return {
        "username": username,
        "role": user["role"],
        "email": user["email"],
        "phone": user["phone"],
        "balance": user["balance"],
    }


@app.route("/")
def index():
    username = session.get("username")
    user_info = public_user_info(username) if username in USERS else None
    return render_template("index.html", username=username, user=user_info)


@app.route("/login", methods=["GET", "POST"])
def login():
    error = None

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        client_ip = request.remote_addr or "unknown"
        key = f"{client_ip}:{username}"
        attempt = login_attempts.get(key, {"count": 0, "locked_until": 0})

        if attempt["locked_until"] > time.time():
            error = "登录尝试次数过多，请稍后再试。"
        else:
            user = USERS.get(username)
            if user and check_password_hash(user["password_hash"], password):
                login_attempts.pop(key, None)
                session.clear()
                session["username"] = username
                return redirect("/")

            attempt["count"] += 1
            if attempt["count"] >= MAX_LOGIN_FAILURES:
                attempt = {"count": 0, "locked_until": time.time() + LOCKOUT_SECONDS}
            login_attempts[key] = attempt
            error = "用户名或密码错误"

    return render_template("login.html", error=error)


@app.route("/logout", methods=["POST","GET"])
def logout():
    session.clear()
    return redirect("/")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
