import hashlib
import os
import secrets
from dotenv import load_dotenv
load_dotenv()
from datetime import date, datetime, timedelta, timezone
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, flash, session, abort
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

STATUSES = ["Applied", "Interview", "Offer", "Rejected", "Withdrawn"]
SORTS = {
    "new": "id DESC",
    "old": "id ASC",
    "az": "company COLLATE NOCASE ASC",
    "za": "company COLLATE NOCASE DESC",
    "soon": "interview_at IS NULL OR interview_at = '', interview_at < date('now'), interview_at ASC",
}

def start_session(uid):
    """Keep only what the pages need in the signed session cookie."""
    conn = get_db()
    u = conn.execute("SELECT * FROM users WHERE id = ?", (uid,)).fetchone()
    conn.close()
    session["uid"] = u["id"]
    session["name"] = u["name"]
    session["sv"] = u["session_version"] or 0
    session["theme"] = u["theme"] or "system"
    session["default_status"] = u["default_status"] or "Applied"
    session["default_sort"] = u["default_sort"] or "new"

def current_user():
    conn = get_db()
    u = conn.execute("SELECT * FROM users WHERE id = ?", (session["uid"],)).fetchone()
    conn.close()
    return u

def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "uid" not in session:
            return redirect(url_for("login"))
        u = current_user()
        if u is None or (u["session_version"] or 0) != session.get("sv"):
            session.clear()
            flash("Please log in again.")
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
        start_session(uid)
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
            session.clear()
            start_session(user["id"])
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
            conn.execute("UPDATE users SET password_hash = ?, session_version = session_version + 1 WHERE id = ?", (generate_password_hash(pw), row["user_id"]))
            conn.execute("UPDATE password_resets SET used_at = ? WHERE user_id = ? AND used_at IS NULL", (now, row["user_id"]))
            conn.commit()
            conn.close()
            flash("Password changed! Please log in. ✅")
            return redirect(url_for("login"))
    conn.close()
    return render_template("auth.html", mode="reset")

SORT_LABELS = {"new": "Newest", "old": "Oldest", "az": "Company A-Z", "za": "Company Z-A", "soon": "Upcoming interview"}

@app.route("/logout", methods=["POST"])
def logout():
    uid = session.get("uid")
    if uid:
        conn = get_db()
        conn.execute("UPDATE users SET session_version = session_version + 1 WHERE id = ?", (uid,))
        conn.commit()
        conn.close()
    session.clear()
    flash("You are logged out. See you soon! 👋")
    return redirect(url_for("login"))

@app.route("/profile")
@login_required
def profile():
    u = current_user()
    conn = get_db()
    counts = {s: 0 for s in STATUSES}
    for r in conn.execute("SELECT status, COUNT(*) AS c FROM applications WHERE user_id = ? GROUP BY status", (u["id"],)):
        counts[r["status"]] = r["c"]
    conn.close()
    total = sum(counts.values())
    rate = round(100 * (counts["Interview"] + counts["Offer"]) / total, 1) if total else 0
    return render_template("profile.html", u=u, counts=counts, total=total, rate=rate,
                           since=(u["created_at"] or "")[:10])

@app.route("/settings")
@login_required
def settings():
    return render_template("settings.html", u=current_user(), statuses=STATUSES, sorts=SORT_LABELS)

@app.route("/settings/account", methods=["POST"])
@login_required
def settings_account():
    u = current_user()
    back = url_for("settings") + "#account"
    name = request.form.get("name", "").strip()[:80]
    email = request.form.get("email", "").strip().lower()[:200]
    if not name or "@" not in email:
        flash("Enter your name and a valid email.")
        return redirect(back)
    if email != u["email"]:
        if not check_password_hash(u["password_hash"], request.form.get("current", "")):
            flash("Enter your current password to change your email.")
            return redirect(back)
        conn = get_db()
        taken = conn.execute("SELECT 1 FROM users WHERE email = ? AND id != ?", (email, u["id"])).fetchone()
        conn.close()
        if taken:
            flash("That email is already in use.")
            return redirect(back)
    conn = get_db()
    conn.execute("UPDATE users SET name = ?, email = ? WHERE id = ?", (name, email, u["id"]))
    conn.commit()
    conn.close()
    session["name"] = name
    flash("Profile updated ✅")
    return redirect(url_for("settings"))

@app.route("/settings/password", methods=["POST"])
@limiter.limit("10 per hour", methods=["POST"])
@login_required
def settings_password():
    u = current_user()
    back = url_for("settings") + "#password"
    f = request.form
    new = f.get("password", "")
    if not check_password_hash(u["password_hash"], f.get("current", "")):
        flash("Your current password is incorrect.")
        return redirect(back)
    if new != f.get("confirm", ""):
        flash("New passwords do not match.")
        return redirect(back)
    err = password_error(new)
    if err:
        flash(err)
        return redirect(back)
    conn = get_db()
    conn.execute("UPDATE users SET password_hash = ?, session_version = session_version + 1 WHERE id = ?", (generate_password_hash(new), u["id"]))
    conn.commit()
    conn.close()
    start_session(u["id"])
    flash("Password changed ✅ Other devices were logged out.")
    return redirect(url_for("settings"))

@app.route("/settings/preferences", methods=["POST"])
@login_required
def settings_preferences():
    f = request.form
    theme = f.get("theme", "system")
    status = f.get("default_status", "Applied")
    sort = f.get("default_sort", "new")
    if theme not in ("light", "dark", "system"):
        theme = "system"
    if status not in STATUSES:
        status = "Applied"
    if sort not in SORTS:
        sort = "new"
    conn = get_db()
    conn.execute("UPDATE users SET theme = ?, default_status = ?, default_sort = ? WHERE id = ?", (theme, status, sort, session["uid"]))
    conn.commit()
    conn.close()
    session["theme"], session["default_status"], session["default_sort"] = theme, status, sort
    flash("Preferences saved ✅")
    return redirect(url_for("settings"))

@app.route("/settings/delete", methods=["POST"])
@limiter.limit("5 per hour", methods=["POST"])
@login_required
def settings_delete():
    u = current_user()
    f = request.form
    if f.get("confirm", "").strip() != "DELETE" or not check_password_hash(u["password_hash"], f.get("password", "")):
        flash("Account NOT deleted. Type DELETE and enter your correct password.")
        return redirect(url_for("settings") + "#danger")
    conn = get_db()
    conn.execute("DELETE FROM applications WHERE user_id = ?", (u["id"],))
    conn.execute("DELETE FROM password_resets WHERE user_id = ?", (u["id"],))
    conn.execute("DELETE FROM users WHERE id = ?", (u["id"],))
    conn.commit()
    conn.close()
    session.clear()
    flash("Your account and all its data were deleted.")
    return redirect(url_for("login"))


EMPLOYMENT = ["Full-time", "Part-time", "Contract", "Internship"]
SETUPS = ["On-site", "Hybrid", "Remote"]
PERIODS = {"week": 7, "month": 30}
COLS = ("company", "position", "status", "date_applied", "interview_at", "location",
        "job_url", "salary", "employment_type", "work_setup", "notes")

def form_context(title):
    return {"statuses": STATUSES, "employment": EMPLOYMENT, "setups": SETUPS,
            "title": title, "hide_fab": True}

def form_values():
    """Read the job form, clean it, and return (values, errors)."""
    f = request.form
    keys = ("company", "position", "status", "date_applied", "interview_date",
            "interview_time", "location", "job_url", "salary", "employment_type",
            "work_setup", "notes")
    v = {k: f.get(k, "").strip()[:2000 if k == "notes" else 300] for k in keys}
    errors = []
    if not v["company"]:
        errors.append("Company is required.")
    if not v["position"]:
        errors.append("Position is required.")
    if v["status"] not in STATUSES:
        errors.append("Choose a valid status.")
    try:
        date.fromisoformat(v["date_applied"])
    except ValueError:
        errors.append("Enter a valid date applied.")
    v["interview_at"] = ""
    if v["interview_date"]:
        stamp = v["interview_date"] + "T" + (v["interview_time"] or "09:00")
        try:
            datetime.fromisoformat(stamp)
            v["interview_at"] = stamp
        except ValueError:
            errors.append("Enter a valid interview date and time.")
    if v["job_url"] and not v["job_url"].lower().startswith(("http://", "https://")):
        errors.append("Job link must start with http:// or https://")
    if v["employment_type"] not in EMPLOYMENT:
        v["employment_type"] = ""
    if v["work_setup"] not in SETUPS:
        v["work_setup"] = ""
    return v, errors

def split_interview(row):
    d = dict(row)
    d["interview_date"], _, d["interview_time"] = (d.get("interview_at") or "").partition("T")
    return d

@app.route("/")
@login_required
def index():
    uid = session["uid"]
    q = request.args.get("q", "").strip()
    status = request.args.get("status", "")
    period = request.args.get("period", "")
    sort = request.args.get("sort") or session.get("default_sort", "new")
    sql = "SELECT * FROM applications WHERE user_id = ?"
    params = [uid]
    if q:
        sql += " AND (company LIKE ? OR position LIKE ? OR notes LIKE ? OR location LIKE ?)"
        params += ["%" + q + "%"] * 4
    if status in STATUSES:
        sql += " AND status = ?"
        params.append(status)
    if period in PERIODS:
        sql += " AND date_applied >= ?"
        params.append((date.today() - timedelta(days=PERIODS[period])).isoformat())
    sql += " ORDER BY " + SORTS.get(sort, SORTS["new"])
    conn = get_db()
    rows = conn.execute(sql, params).fetchall()
    jobs = [dict(r, when=when(r["interview_at"])) for r in rows]
    counts = {s: 0 for s in STATUSES}
    for r in conn.execute("SELECT status, COUNT(*) AS c FROM applications WHERE user_id = ? GROUP BY status", (uid,)):
        counts[r["status"]] = r["c"]
    total = sum(counts.values())
    week_ago = (date.today() - timedelta(days=7)).isoformat()
    month_ago = (date.today() - timedelta(days=30)).isoformat()
    week = conn.execute("SELECT COUNT(*) FROM applications WHERE user_id = ? AND date_applied >= ?", (uid, week_ago)).fetchone()[0]
    month = conn.execute("SELECT COUNT(*) FROM applications WHERE user_id = ? AND date_applied >= ?", (uid, month_ago)).fetchone()[0]
    now = datetime.now().strftime("%Y-%m-%dT%H:%M")
    up = conn.execute("SELECT * FROM applications WHERE user_id = ? AND interview_at >= ? ORDER BY interview_at LIMIT 3", (uid, now)).fetchall()
    upcoming = [dict(r, when=when(r["interview_at"])) for r in up]
    conn.close()
    got = counts["Interview"] + counts["Offer"]
    rate = round(100 * got / total, 1) if total else 0
    return render_template("index.html", jobs=jobs, upcoming=upcoming, counts=counts,
        total=total, week=week, month=month, rate=rate, q=q, status=status,
        period=period, sort=sort, statuses=STATUSES)

@app.route("/job/<int:job_id>")
@login_required
def view(job_id):
    conn = get_db()
    row = conn.execute("SELECT * FROM applications WHERE id = ? AND user_id = ?", (job_id, session["uid"])).fetchone()
    conn.close()
    if row is None:
        abort(404)
    return render_template("job.html", job=dict(row, when=when(row["interview_at"])))

@app.route("/add", methods=["GET", "POST"])
@login_required
def add():
    if request.method == "POST":
        v, errors = form_values()
        if errors:
            for e in errors:
                flash(e)
            return render_template("form.html", job=v, **form_context("Add Application"))
        now = utcnow().isoformat(timespec="seconds")
        conn = get_db()
        conn.execute("INSERT INTO applications (" + ", ".join(COLS) + ", user_id, created_at, updated_at) VALUES (" + ", ".join("?" * (len(COLS) + 3)) + ")",
                     [v[c] for c in COLS] + [session["uid"], now, now])
        conn.commit()
        conn.close()
        flash("Application added ✅")
        return redirect(url_for("index"))
    job = {"status": session.get("default_status", "Applied"), "date_applied": date.today().isoformat()}
    return render_template("form.html", job=job, **form_context("Add Application"))

@app.route("/edit/<int:job_id>", methods=["GET", "POST"])
@login_required
def edit(job_id):
    uid = session["uid"]
    conn = get_db()
    row = conn.execute("SELECT * FROM applications WHERE id = ? AND user_id = ?", (job_id, uid)).fetchone()
    if row is None:
        conn.close()
        abort(404)
    if request.method == "POST":
        v, errors = form_values()
        if errors:
            conn.close()
            for e in errors:
                flash(e)
            return render_template("form.html", job=v, **form_context("Edit Application"))
        conn.execute("UPDATE applications SET " + ", ".join(c + " = ?" for c in COLS) + ", updated_at = ? WHERE id = ? AND user_id = ?",
                     [v[c] for c in COLS] + [utcnow().isoformat(timespec="seconds"), job_id, uid])
        conn.commit()
        conn.close()
        flash("Changes saved ✅")
        return redirect(url_for("index"))
    conn.close()
    return render_template("form.html", job=split_interview(row), **form_context("Edit Application"))

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
    if "uid" in session and request.endpoint != "static":
        resp.headers["Cache-Control"] = "no-store, private"
    return resp

@app.errorhandler(CSRFError)
def csrf_error(e):
    flash("Your session expired. Please try again.")
    return redirect(request.referrer or url_for("login"))

@app.errorhandler(429)
def too_many(e):
    flash("Too many attempts. Please wait a bit and try again.")
    return redirect(request.referrer or url_for("login"))

@app.context_processor
def inject_theme():
    return {"theme": session.get("theme", "system")}

def error_page(code, title, msg):
    return render_template("error.html", code=code, title=title, msg=msg), code

@app.errorhandler(404)
def not_found(e):
    return error_page(404, "Page not found", "We could not find that page. It may have moved, or it is not yours to view.")

@app.errorhandler(403)
def forbidden(e):
    return error_page(403, "Access denied", "You do not have permission to open this page.")

@app.errorhandler(405)
def not_allowed(e):
    return error_page(405, "Action not available", "That action cannot be done this way. Please use the buttons in the app.")

@app.errorhandler(500)
def server_error(e):
    app.logger.exception("Server error")
    return error_page(500, "Something went wrong", "Something broke on our side. Your data is safe. Please try again in a moment.")

if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG") == "1")
