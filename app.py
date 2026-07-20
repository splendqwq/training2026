import sqlite3
import os
from flask import Flask, render_template, request, redirect, session

app = Flask(__name__)
app.secret_key = "dev-key-2025"

# 用户数据库 - 明文密码
USERS = {
    "admin": {
        "password": "admin123",
        "role": "admin",
        "email": "admin@example.com",
        "phone": "13800138000",
        "balance": 99999
    },
    "alice": {
        "password": "alice2025",
        "role": "user",
        "email": "alice@example.com",
        "phone": "13900139001",
        "balance": 100
    }
}


def init_db():
    """初始化 SQLite 数据库，建表并插入默认用户"""
    os.makedirs("data", exist_ok=True)
    conn = sqlite3.connect("data/users.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            email TEXT,
            phone TEXT
        )
    """)
    # 插入默认用户（INSERT OR IGNORE 防止重复）
    cursor.execute("INSERT OR IGNORE INTO users (username, password, email, phone) VALUES (?, ?, ?, ?)",
                   ("admin", "admin123", "admin@example.com", "13800138000"))
    cursor.execute("INSERT OR IGNORE INTO users (username, password, email, phone) VALUES (?, ?, ?, ?)",
                   ("alice", "alice2025", "alice@example.com", "13900139001"))
    conn.commit()
    conn.close()


init_db()


@app.route("/")
def index():
    username = session.get("username")
    user_info = None
    if username and username in USERS:
        user_info = USERS[username]
        # 将用户名也放进字典，方便模板展示
        user_info["username"] = username

    # 处理搜索参数
    keyword = request.args.get("keyword", "")
    search_results = None
    if keyword:
        conn = sqlite3.connect("data/users.db")
        cursor = conn.cursor()
        pattern = f"%{keyword}%"
        cursor.execute(
            "SELECT id, username, email, phone FROM users "
            "WHERE username LIKE ? OR email LIKE ?",
            (pattern, pattern),
        )
        search_results = cursor.fetchall()
        conn.close()

    return render_template("index.html", username=username, user=user_info,
                           keyword=keyword, search_results=search_results)


@app.route("/login", methods=["GET", "POST"])
def login():
    error = None
    msg = request.args.get("msg", "")
    if request.method == "POST":
        username = request.form.get("username", "")
        password = request.form.get("password", "")
        if username in USERS and USERS[username]["password"] == password:
            session["username"] = username
            user_info = USERS[username]
            user_info["username"] = username
            keyword = request.args.get("keyword", "")
            return render_template("index.html", username=username, user=user_info,
                                   keyword=keyword, search_results=None)
        else:
            error = "用户名或密码错误"
    return render_template("login.html", error=error, msg=msg)


@app.route("/logout")
def logout():
    session.pop("username", None)
    return redirect("/")


@app.route("/register", methods=["GET", "POST"])
def register():
    error = None
    if request.method == "POST":
        username = request.form.get("username", "")
        password = request.form.get("password", "")
        email = request.form.get("email", "")
        phone = request.form.get("phone", "")
        if not username or not password:
            error = "用户名和密码不能为空"
        else:
            conn = sqlite3.connect("data/users.db")
            cursor = conn.cursor()
            try:
                cursor.execute(
                    "INSERT INTO users (username, password, email, phone) VALUES (?, ?, ?, ?)",
                    (username, password, email, phone),
                )
                conn.commit()
                conn.close()
                return redirect("/login?msg=注册成功，请登录")
            except sqlite3.IntegrityError:
                error = "用户名已存在"
                conn.close()
    return render_template("register.html", error=error)


@app.route("/search")
def search():
    keyword = request.args.get("keyword", "")
    results = []
    if keyword:
        conn = sqlite3.connect("data/users.db")
        cursor = conn.cursor()
        pattern = f"%{keyword}%"
        cursor.execute(
            "SELECT id, username, email, phone FROM users "
            "WHERE username LIKE ? OR email LIKE ?",
            (pattern, pattern),
        )
        results = cursor.fetchall()
        conn.close()
    return render_template("index.html", username=session.get("username"),
                           user=None, keyword=keyword, search_results=results)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
