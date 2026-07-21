import sqlite3
import os
import secrets
from flask import Flask, render_template, request, redirect, session, url_for, abort, send_from_directory

app = Flask(__name__)
app.secret_key = "dev-key-2025"
app.config["MAX_CONTENT_LENGTH"] = 2 * 1024 * 1024
app.config["UPLOAD_FOLDER"] = os.path.join(app.instance_path, "uploads")

ALLOWED_IMAGE_EXTENSIONS = {"jpg", "jpeg", "png", "gif", "webp"}


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
        sql = f"SELECT id, username, email, phone FROM users WHERE username LIKE '%{keyword}%' OR email LIKE '%{keyword}%'"
        print(f"[SQL] {sql}")
        cursor.execute(sql)
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
            sql = f"INSERT INTO users (username, password, email, phone) VALUES ('{username}', '{password}', '{email}', '{phone}')"
            print(f"[SQL] {sql}")
            try:
                cursor.execute(sql)
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
        sql = f"SELECT id, username, email, phone FROM users WHERE username LIKE '%{keyword}%' OR email LIKE '%{keyword}%'"
        print(f"[SQL] {sql}")
        cursor.execute(sql)
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


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
