import os
import re
import secrets
import smtplib
import ssl
from datetime import datetime
from email.message import EmailMessage

from dotenv import load_dotenv

load_dotenv()

from authlib.integrations.flask_client import OAuth
from flask import Flask, flash, jsonify, redirect, render_template, request, url_for
from flask_login import (
    LoginManager,
    current_user,
    login_required,
    login_user,
    logout_user,
)
from groq import Groq
from itsdangerous import BadSignature, URLSafeTimedSerializer
from werkzeug.middleware.proxy_fix import ProxyFix

from engine import CareerRecommender
from models import ProgressStep, User, db

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-secret-change-me")

db_url = os.getenv("DATABASE_URL", "sqlite:///careerpath.db")
if db_url.startswith("postgres://"):
    db_url = db_url.replace("postgres://", "postgresql://", 1)
app.config["SQLALCHEMY_DATABASE_URI"] = db_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {"pool_pre_ping": True, "pool_recycle": 300}

GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-20b")
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
RESET_MAX_AGE = 3600

db.init_app(app)

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"
login_manager.login_message = "Please log in to continue."

oauth = OAuth(app)
oauth.register(
    name="google",
    client_id=os.getenv("GOOGLE_CLIENT_ID"),
    client_secret=os.getenv("GOOGLE_CLIENT_SECRET"),
    server_metadata_url="https://accounts.google.com/.well-known/openid-configuration",
    client_kwargs={"scope": "openid email profile"},
)


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


@login_manager.unauthorized_handler
def unauthorized():
    if request.path.startswith("/api/"):
        return jsonify(error="Please log in first."), 401
    flash("Please log in to continue.", "info")
    return redirect(url_for("login"))


with app.app_context():
    try:
        db.create_all()
    except Exception as error:
        print("Database setup error:", error)

engine = CareerRecommender()


# ---------- Helpers ----------
def get_ai_advice(name, recommendations, skills, interests):
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        return None
    try:
        client = Groq(api_key=api_key)
        top = "\n".join(
            f"- {r['role']} ({r['match_score']}% match)" for r in recommendations
        )
        prompt = (
            f"You are a friendly career mentor for interns.\n"
            f"Intern name: {name}\n"
            f"Skills: {skills}\n"
            f"Interests: {interests}\n"
            f"Top matched careers:\n{top}\n\n"
            "Write short, warm, personalized advice in under 120 words. "
            "Mention why the top career fits and one concrete next step. "
            "Plain text only, no markdown, no bullet symbols."
        )
        response = client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            max_tokens=1000,
        )
        content = response.choices[0].message.content
        return content.strip() if content else None
    except Exception as error:
        print("Groq error:", error)
        return None


def build_progress(user):
    steps = (
        ProgressStep.query.filter_by(user_id=user.id)
        .order_by(ProgressStep.role, ProgressStep.step_order)
        .all()
    )
    grouped = {}
    for step in steps:
        grouped.setdefault(step.role, []).append(step)

    result = []
    for role, items in grouped.items():
        done = sum(1 for item in items if item.completed)
        result.append(
            {
                "role": role,
                "total": len(items),
                "done": done,
                "percent": round(done / len(items) * 100),
                "steps": [
                    {"id": i.id, "text": i.step_text, "completed": i.completed}
                    for i in items
                ],
            }
        )
    return result


def _serializer():
    return URLSafeTimedSerializer(app.config["SECRET_KEY"])


def make_reset_token(user):
    return _serializer().dumps(
        {"id": user.id, "h": user.password_hash[-12:]}, salt="password-reset"
    )


def verify_reset_token(token):
    try:
        data = _serializer().loads(token, salt="password-reset", max_age=RESET_MAX_AGE)
    except BadSignature:
        return None
    user = db.session.get(User, data.get("id"))
    if not user or user.password_hash[-12:] != data.get("h"):
        return None
    return user


def send_reset_email(user):
    link = url_for("reset_password", token=make_reset_token(user), _external=True)
    username = os.getenv("MAIL_USERNAME")
    app_password = os.getenv("MAIL_APP_PASSWORD")

    if not username or not app_password:
        print(f"\n[DEV] Email is not set up. Password reset link for {user.email}:\n{link}\n")
        return

    first_name = user.name.split()[0]
    plain = (
        f"Hi {first_name},\n\n"
        f"We received a request to reset your CareerPath AI password.\n"
        f"Open this link within 1 hour to choose a new password:\n{link}\n\n"
        f"If you didn't ask for this, you can safely ignore this email."
    )
    html = f"""
    <div style="font-family:Arial,sans-serif;max-width:480px;margin:auto;padding:24px;">
      <h2 style="color:#4f46e5;">CareerPath AI</h2>
      <p>Hi {first_name},</p>
      <p>We received a request to reset your password. Click the button below within 1 hour to choose a new one.</p>
      <p style="margin:28px 0;">
        <a href="{link}" style="background:#4f46e5;color:#ffffff;padding:12px 24px;border-radius:10px;text-decoration:none;font-weight:bold;">Reset my password</a>
      </p>
      <p style="color:#667085;font-size:13px;">If you didn't ask for this, you can safely ignore this email.</p>
    </div>
    """

    try:
        msg = EmailMessage()
        msg["Subject"] = "Reset your CareerPath AI password"
        msg["From"] = f"CareerPath AI <{username}>"
        msg["To"] = user.email
        msg.set_content(plain)
        msg.add_alternative(html, subtype="html")
        with smtplib.SMTP_SSL(
            "smtp.gmail.com", 465, context=ssl.create_default_context(), timeout=15
        ) as server:
            server.login(username, app_password.replace(" ", ""))
            server.send_message(msg)
    except Exception as error:
        print("Email error:", error)
        print(f"[DEV] Reset link for {user.email}:\n{link}\n")


# ---------- Pages ----------
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/signup", methods=["GET", "POST"])
def signup():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm", "")

        error = None
        if len(name) < 2:
            error = "Please enter your name."
        elif not EMAIL_PATTERN.match(email):
            error = "Please enter a valid email address."
        elif len(password) < 8:
            error = "Password must be at least 8 characters."
        elif password != confirm:
            error = "Passwords do not match."
        elif User.query.filter_by(email=email).first():
            error = "An account with this email already exists."

        if error:
            flash(error, "error")
            return render_template("signup.html", name=name, email=email)

        user = User(name=name, email=email)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        login_user(user)
        flash(f"Welcome, {user.name}! Your account is ready.", "success")
        return redirect(url_for("dashboard"))

    return render_template("signup.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = User.query.filter_by(email=email).first()

        if user and user.check_password(password):
            login_user(user, remember=True)
            return redirect(url_for("dashboard"))

        flash("Incorrect email or password.", "error")
        return render_template("login.html", email=email)

    return render_template("login.html")


@app.route("/logout")
@login_required
def logout():
    logout_user()
    flash("You have been logged out.", "info")
    return redirect(url_for("index"))


@app.route("/auth/google")
def google_login():
    if not os.getenv("GOOGLE_CLIENT_ID") or not os.getenv("GOOGLE_CLIENT_SECRET"):
        flash("Google sign-in is not set up yet.", "error")
        return redirect(url_for("login"))
    redirect_uri = url_for("google_callback", _external=True)
    return oauth.google.authorize_redirect(redirect_uri)


@app.route("/auth/google/callback")
def google_callback():
    try:
        token = oauth.google.authorize_access_token()
        info = token.get("userinfo") or oauth.google.userinfo()
    except Exception as error:
        print("Google sign-in error:", error)
        flash("Google sign-in failed. Please try again.", "error")
        return redirect(url_for("login"))

    email = (info.get("email") or "").strip().lower()
    if not email or not info.get("email_verified", False):
        flash("Your Google email could not be verified.", "error")
        return redirect(url_for("login"))

    user = User.query.filter_by(email=email).first()
    if not user:
        name = info.get("name") or email.split("@")[0]
        user = User(name=name, email=email)
        user.set_password(secrets.token_urlsafe(32))
        db.session.add(user)
        db.session.commit()
        flash(f"Welcome, {user.name}! Your account is ready.", "success")

    login_user(user, remember=True)
    return redirect(url_for("dashboard"))


@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    if current_user.is_authenticated:
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        if not EMAIL_PATTERN.match(email):
            flash("Please enter a valid email address.", "error")
            return render_template("forgot_password.html", email=email)

        user = User.query.filter_by(email=email).first()
        if user:
            send_reset_email(user)

        flash("If an account exists for that email, we've sent a reset link.", "success")
        return redirect(url_for("login"))

    return render_template("forgot_password.html")


@app.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token):
    user = verify_reset_token(token)
    if not user:
        flash("That reset link is invalid or has expired. Please request a new one.", "error")
        return redirect(url_for("forgot_password"))

    if request.method == "POST":
        password = request.form.get("password", "")
        confirm = request.form.get("confirm", "")

        if len(password) < 8:
            flash("Password must be at least 8 characters.", "error")
        elif password != confirm:
            flash("Passwords do not match.", "error")
        else:
            user.set_password(password)
            db.session.commit()
            flash("Password updated! You can log in now.", "success")
            return redirect(url_for("login"))

    return render_template("reset_password.html")


@app.route("/dashboard")
@login_required
def dashboard():
    return render_template("dashboard.html")


@app.route("/progress")
@login_required
def progress():
    return render_template("progress.html")


# ---------- API ----------
@app.route("/health")
def health():
    return jsonify(status="ok")


@app.post("/api/recommend")
@login_required
def api_recommend():
    data = request.get_json(silent=True) or {}
    skills = str(data.get("skills", "")).strip()
    interests = str(data.get("interests", "")).strip()

    result = engine.recommend(skills, interests, top_n=3)
    if "error" in result:
        return jsonify(result), 400

    current_user.skills = skills
    current_user.interests = interests
    db.session.commit()

    first_name = current_user.name.split()[0]
    result["advice"] = get_ai_advice(
        first_name, result["recommendations"], skills, interests
    )
    return jsonify(result)


@app.get("/api/profile")
@login_required
def api_profile():
    return jsonify(
        name=current_user.name,
        skills=current_user.skills or "",
        interests=current_user.interests or "",
    )


@app.post("/api/track")
@login_required
def api_track():
    data = request.get_json(silent=True) or {}
    role = data.get("role", "")
    record = next((r for r in engine.records if r["role"] == role), None)
    if not record:
        return jsonify(error="Career not found."), 404

    exists = ProgressStep.query.filter_by(user_id=current_user.id, role=role).first()
    if exists:
        return jsonify(ok=True, message="You are already tracking this career.")

    for order, text in enumerate(record["path_list"]):
        db.session.add(
            ProgressStep(
                user_id=current_user.id, role=role, step_order=order, step_text=text
            )
        )
    db.session.commit()
    return jsonify(ok=True, message=f"Now tracking {role}!")


@app.post("/api/untrack")
@login_required
def api_untrack():
    data = request.get_json(silent=True) or {}
    role = data.get("role", "")
    ProgressStep.query.filter_by(user_id=current_user.id, role=role).delete()
    db.session.commit()
    return jsonify(ok=True)


@app.get("/api/progress")
@login_required
def api_progress():
    return jsonify(roles=build_progress(current_user))


@app.post("/api/progress/<int:step_id>")
@login_required
def api_toggle_step(step_id):
    step = ProgressStep.query.filter_by(id=step_id, user_id=current_user.id).first()
    if not step:
        return jsonify(error="Step not found."), 404
    step.completed = not step.completed
    step.completed_at = datetime.utcnow() if step.completed else None
    db.session.commit()
    return jsonify(ok=True, completed=step.completed)


if __name__ == "__main__":
    app.run(debug=True, use_reloader=False)