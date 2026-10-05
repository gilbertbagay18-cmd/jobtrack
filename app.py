import hashlib
import os
import secrets
from dotenv import load_dotenv
load_dotenv()
from datetime import date, datetime, timedelta, timezone
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_wtf.csrf import CSRFProtect, CSRFError
from werkzeug.security import generate_password_hash, check_password_hash
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from db import get_db, init_db
from mailer import send_email

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY")
if not app.secret_key:
    raise RuntimeError("SECRET_KEY missing. Add it to your .env file.")
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SECURE"] = os.environ.get("FLASK_ENV") == "production"
csrf = CSRFProtect(app)
limiter = Limiter(get_remote_address, app=app, storage_uri="memory://")
RESET_TTL = int(os.environ.get("RESET_TOKEN_EXPIRATION", "1800"))
init_db()

STATUSES = ["Applied", "Interview", "Offer", "Rejected"]
SORTS = {
    "new": "id DESC",
    "soon": "interview_at IS NULL OR interview_at = '', interview_at ASC",
    "az": "company COLLATE NOCASE ASC",
}

def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "uid" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return wrapper

def when(iso):
    if not iso:
        return None
    try:
        dt = datetime.fromisoformat(iso)
    except ValueError:
        return None
    days = (dt.date() - date.today()).days
    if days < 0:
        tag, cls = "Past", "past"
    elif days == 0:
        tag, cls = "Today", "soon"
    elif days == 1:
        tag, cls = "Tomorrow", "soon"
    else:
        tag, cls = "In " + str(days) + " days", "later"
    fmt = "%Y%m%dT%H%M%S"
    return {"nice": dt.strftime("%a, %b %d · %I:%M %p"), "tag": tag,
            "cls": cls, "days": days, "start": dt.strftime(fmt),
            "end": (dt + timedelta(hours=1)).strftime(fmt)}

def password_error(pw):
    if len(pw) < 8:
        return "Use at least 8 characters."
    if pw.isalpha() or pw.isdigit():
        return "Mix letters and numbers in your password."
    return None

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form["name"].strip()
        email = request.form["email"].strip().lower()
        pw = request.form["password"]
        if pw != request.form.get("confirm", ""):
            flash("Passwords do not match.")
            return render_template("auth.html", mode="register")
        if not name or "@" not in email:
            flash("Please enter your name and a valid email.")
            return render_template("auth.html", mode="register")
        err = password_error(pw)
        if err:
            flash(err)
            return render_template("auth.html", mode="register")
        conn = get_db()
        if conn.execute("SELECT 1 FROM users WHERE email = ?", (email,)).fetchone():
            conn.close()
            flash("That email is already registered. Try logging in.")
            return render_template("auth.html", mode="register")
        first = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0
        cur = conn.execute("INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
                           (name, email, generate_password_hash(pw)))
        uid = cur.lastrowid
        if first:
            conn.execute("UPDATE applications SET user_id = ? WHERE user_id IS NULL", (uid,))
        conn.commit()
        conn.close()
        session["uid"] = uid
        session["name"] = name
        flash("Welcome, " + name + "! 🎉")
        return redirect(url_for("index"))
    return render_template("auth.html", mode="register")

@app.route("/login", methods=["GET", "POST"])
@limiter.limit("10 per minute", methods=["POST"])
def login():
    if request.method == "POST":
        email = request.form["email"].strip().lower()
        conn = get_db()
        user = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
        conn.close()
        if user and check_password_hash(user["password_hash"], request.form["password"]):
            session["uid"] = user["id"]
            session["name"] = user["name"]
            return redirect(url_for("index"))
        flash("Wrong email or password.")
    return render_template("auth.html", mode="login")

def utcnow():
    return datetime.now(timezone.utc).replace(tzinfo=None)

def hash_token(token):
    return hashlib.sha256(token.encode()).hexdigest()

@app.route("/forgot", methods=["GET", "POST"])
@limiter.limit("5 per hour", methods=["POST"])
def forgot():
    if request.method == "POST":
        email = request.form["email"].strip().lower()
        conn = get_db()
        user = conn.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
        if user:
            now = utcnow()
            hour_ago = (now - timedelta(hours=1)).isoformat(timespec="seconds")
            recent = conn.execute("SELECT COUNT(*) FROM password_resets WHERE user_id = ? AND created_at > ?", (user["id"], hour_ago)).fetchone()[0]
            if recent < 3:
                token = secrets.token_urlsafe(32)
                expires = (now + timedelta(seconds=RESET_TTL)).isoformat(timespec="seconds")
                conn.execute("INSERT INTO password_resets (user_id, token_hash, expires_at, created_at) VALUES (?, ?, ?, ?)", (user["id"], hash_token(token), expires, now.isoformat(timespec="seconds")))
                conn.commit()
                base = os.environ.get("BASE_URL", request.url_root).rstrip("/")
                link = base + url_for("reset", token=token)
                text = "Hi! Use this link to choose a new password (valid for " + str(RESET_TTL // 60) + " minutes):\n\n" + link + "\n\nIf you did not ask for this, you can ignore this email."
                send_email(email, "Reset your JobTrack password", text)
        conn.close()
        flash("If that email is registered, a reset link is on its way.")
        return redirect(url_for("login"))
    return render_template("auth.html", mode="forgot")

@app.route("/reset/<token>", methods=["GET", "POST"])
def reset(token):
    now = utcnow().isoformat(timespec="seconds")
    conn = get_db()
    row = conn.execute("SELECT * FROM password_resets WHERE token_hash = ? AND used_at IS NULL AND expires_at > ?", (hash_token(token), now)).fetchone()
    if row is None:
        conn.close()
        flash("That reset link is invalid or has expired. Please request a new one.")
        return redirect(url_for("forgot"))
    if request.method == "POST":
        pw = request.form["password"]
        err = password_error(pw)
        if pw != request.form.get("confirm", ""):
            flash("Passwords do not match.")
        elif err:
            flash(err)
        else:
            conn.execute("UPDATE users SET password_hash = ? WHERE id = ?", (generate_password_hash(pw), row["user_id"]))
            conn.execute("UPDATE password_resets SET used_at = ? WHERE user_id = ? AND used_at IS NULL", (now, row["user_id"]))
            conn.commit()
            conn.close()
            flash("Password changed! Please log in. ✅")
            return redirect(url_for("login"))
    conn.close()
    return render_template("auth.html", mode="reset")

@app.route("/logout")
def logout():
    session.clear()
    flash("You are logged out. See you soon! 👋")
    return redirect(url_for("login"))

@app.route("/")
@login_required
def index():
    uid = session["uid"]
    q = request.args.get("q", "").strip()
    status = request.args.get("status", "")
    sort = request.args.get("sort", "new")
    sql = "SELECT * FROM applications WHERE user_id = ?"
    params = [uid]
    if q:
        sql += " AND (company LIKE ? OR position LIKE ? OR notes LIKE ? OR location LIKE ?)"
        params += ["%" + q + "%"] * 4
    if status:
        sql += " AND status = ?"
        params.append(status)
    sql += " ORDER BY " + SORTS.get(sort, SORTS["new"])
    conn = get_db()
    rows = conn.execute(sql, params).fetchall()
    jobs = [dict(r, when=when(r["interview_at"])) for r in rows]
    counts = {s: 0 for s in STATUSES}
    for r in conn.execute("SELECT status, COUNT(*) AS c FROM applications WHERE user_id = ? GROUP BY status", (uid,)):
        counts[r["status"]] = r["c"]
    now = datetime.now().strftime("%Y-%m-%dT%H:%M")
    up = conn.execute("SELECT * FROM applications WHERE user_id = ? AND interview_at >= ? ORDER BY interview_at LIMIT 3", (uid, now)).fetchall()
    upcoming = [dict(r, when=when(r["interview_at"])) for r in up]
    conn.close()
    return render_template("index.html", jobs=jobs, upcoming=upcoming,
        counts=counts, total=sum(counts.values()), q=q, status=status, sort=sort)

def form_data():
    f = request.form
    return (f["company"], f["position"], f["status"], f["date_applied"],
            f["interview_at"], f["location"], f["notes"])

@app.route("/add", methods=["GET", "POST"])
@login_required
def add():
    if request.method == "POST":
        conn = get_db()
        conn.execute("INSERT INTO applications (company, position, status, date_applied, interview_at, location, notes, user_id) VALUES (?,?,?,?,?,?,?,?)", form_data() + (session["uid"],))
        conn.commit()
        conn.close()
        flash("Application added ✅")
        return redirect(url_for("index"))
    return render_template("form.html", job=None, statuses=STATUSES,
        today=date.today().isoformat(), title="Add Application")

@app.route("/edit/<int:job_id>", methods=["GET", "POST"])
@login_required
def edit(job_id):
    uid = session["uid"]
    conn = get_db()
    job = conn.execute("SELECT * FROM applications WHERE id = ? AND user_id = ?", (job_id, uid)).fetchone()
    if job is None:
        conn.close()
        flash("Application not found.")
        return redirect(url_for("index"))
    if request.method == "POST":
        conn.execute("UPDATE applications SET company=?, position=?, status=?, date_applied=?, interview_at=?, location=?, notes=? WHERE id=? AND user_id=?", form_data() + (job_id, uid))
        conn.commit()
        conn.close()
        flash("Changes saved ✅")
        return redirect(url_for("index"))
    conn.close()
    return render_template("form.html", job=job, statuses=STATUSES,
        today="", title="Edit Application")

@app.route("/status/<int:job_id>", methods=["POST"])
@login_required
def set_status(job_id):
    new_status = request.form["status"]
    if new_status in STATUSES:
        conn = get_db()
        conn.execute("UPDATE applications SET status=? WHERE id=? AND user_id=?", (new_status, job_id, session["uid"]))
        conn.commit()
        conn.close()
        flash("Status updated to " + new_status + " ✅")
    return redirect(request.referrer or url_for("index"))

@app.route("/delete/<int:job_id>", methods=["POST"])
@login_required
def delete(job_id):
    conn = get_db()
    conn.execute("DELETE FROM applications WHERE id = ? AND user_id = ?", (job_id, session["uid"]))
    conn.commit()
    conn.close()
    flash("Application deleted 🗑️")
    return redirect(url_for("index"))

@app.route("/sw.js")
def sw():
    return app.send_static_file("sw.js"), 200, {"Content-Type": "application/javascript", "Service-Worker-Allowed": "/"}

@app.after_request
def security_headers(resp):
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["Referrer-Policy"] = "same-origin"
    return resp

@app.errorhandler(CSRFError)
def csrf_error(e):
    flash("Your session expired. Please try again.")
    return redirect(request.referrer or url_for("login"))

@app.errorhandler(429)
def too_many(e):
    flash("Too many attempts. Please wait a bit and try again.")
    return redirect(request.referrer or url_for("login"))

if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG") == "1")
