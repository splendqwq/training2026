import sqlite3
import os
import secrets
from decimal import Decimal, InvalidOperation
from flask import Flask, render_template, request, redirect, session, url_for, abort, send_from_directory

app = Flask(__name__)
app.secret_key = "dev-key-2025"
app.config["MAX_CONTENT_LENGTH"] = 2 * 1024 * 1024
app.config["UPLOAD_FOLDER"] = os.path.join(app.instance_path, "uploads")

ALLOWED_IMAGE_EXTENSIONS = {"jpg", "jpeg", "png", "gif", "webp"}
MAX_RECHARGE_AMOUNT = Decimal("100000.00")
PAGE_FILES = {
    "help": "help.html",
}


def image_type_from_signature(uploaded_file):
    """根据文件签名判断图片类型，不信任客户端提供的 MIME 类型。"""
    header = uploaded_file.stream.read(16)
    uploaded_file.stream.seek(0)
    if header.startswith(b"\xff\xd8\xff"):
        return "jpg"
    if header.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if header.startswith((b"GIF87a", b"GIF89a")):
        return "gif"
    if header.startswith(b"RIFF") and header[8:12] == b"WEBP":
        return "webp"
    return None


def is_allowed_image(uploaded_file):
    if "." not in uploaded_file.filename:
        return False, None
    extension = uploaded_file.filename.rsplit(".", 1)[1].lower()
    detected_type = image_type_from_signature(uploaded_file)
    extension_matches_type = (
        extension == detected_type
        or (extension == "jpeg" and detected_type == "jpg")
    )
    return extension in ALLOWED_IMAGE_EXTENSIONS and extension_matches_type, detected_type

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
            phone TEXT,
            balance REAL DEFAULT 0
        )
    """)
    # 兼容旧表：如果 balance 列不存在则添加
    try:
        cursor.execute("ALTER TABLE users ADD COLUMN balance REAL DEFAULT 0")
    except sqlite3.OperationalError:
        pass  # 列已存在
    cursor.execute("INSERT OR IGNORE INTO users (username, password, email, phone, balance) VALUES (?, ?, ?, ?, ?)",
                   ("admin", "admin123", "admin@example.com", "13800138000", 99999))
    cursor.execute("INSERT OR IGNORE INTO users (username, password, email, phone, balance) VALUES (?, ?, ?, ?, ?)",
                   ("alice", "alice2025", "alice@example.com", "13900139001", 100))
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


@app.route("/upload", methods=["GET", "POST"])
def upload():
    if "username" not in session:
        return redirect("/login")
    username = session["username"]
    file_url = None
    error = None
    if request.method == "POST":
        if "file" not in request.files:
            error = "没有选择文件"
        else:
            f = request.files["file"]
            if f.filename == "":
                error = "没有选择文件"
            else:
                allowed, image_type = is_allowed_image(f)
                if not allowed:
                    error = "只允许上传内容与扩展名一致的 JPG、PNG、GIF 或 WEBP 图片"
                else:
                    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
                    filename = f"{secrets.token_hex(16)}.{image_type}"
                    save_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
                    f.save(save_path)
                    file_url = url_for("uploaded_file", filename=filename)
    return render_template("upload.html", username=username, file_url=file_url, error=error)


@app.route("/uploads/<filename>")
def uploaded_file(filename):
    if "username" not in session:
        abort(403)
    return send_from_directory(app.config["UPLOAD_FOLDER"], filename)


@app.errorhandler(413)
def file_too_large(error):
    if request.path == "/upload":
        return render_template(
            "upload.html",
            username=session.get("username"),
            file_url=None,
            error="文件不能超过 2 MB",
        ), 413
    return "请求体过大", 413


@app.route("/profile")
def profile():
    return render_current_profile()


def render_current_profile(error=None):
    """只返回当前会话所属用户的资料，绝不信任客户端提交的用户 ID。"""
    username = session.get("username")
    if not username:
        return redirect("/login")

    conn = sqlite3.connect("data/users.db")
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, username, email, phone, balance FROM users WHERE username = ?",
        (username,),
    )
    row = cursor.fetchone()
    conn.close()

    if not row:
        session.clear()
        return redirect("/login")

    user_data = {
        "id": row[0],
        "username": row[1],
        "email": row[2],
        "phone": row[3],
        "balance": row[4],
    }
    return render_template("profile.html", user=user_data, error=error)


@app.route("/recharge", methods=["POST"])
def recharge():
    if "username" not in session:
        return redirect("/login")

    amount_text = request.form.get("amount", "").strip()
    try:
        amount = Decimal(amount_text)
    except (InvalidOperation, ValueError):
        return render_current_profile("充值金额格式无效")

    if not amount.is_finite() or amount <= 0 or amount > MAX_RECHARGE_AMOUNT:
        return render_current_profile("充值金额必须大于 0，且不能超过 100000 元")

    conn = sqlite3.connect("data/users.db")
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE users SET balance = balance + ? WHERE username = ?",
        (str(amount), session["username"]),
    )
    conn.commit()
    conn.close()
    return redirect("/profile")


@app.route("/page")
def page():
    page_name = request.args.get("name", "")
    page_content = None
    error = None
    filename = PAGE_FILES.get(page_name)
    if not filename:
        error = "页面不存在"
    else:
        # 仅使用服务端固定映射的文件名，用户输入无法参与文件系统路径拼接。
        file_path = os.path.join(app.root_path, "pages", filename)
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                page_content = f.read()
        except OSError:
            error = "页面暂不可用"

    username = session.get("username")
    user_info = None
    if username and username in USERS:
        user_info = USERS[username]
        user_info["username"] = username

    return render_template("index.html", username=username, user=user_info,
                           page_content=page_content, page_error=error)


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
