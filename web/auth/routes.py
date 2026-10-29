from flask import Blueprint, request, jsonify, session, current_app
from werkzeug.security import generate_password_hash, check_password_hash
from email.message import EmailMessage
import hashlib
import hmac
import os
import re
import secrets
import smtplib
import ssl
import time

from web.auth.database import current_user_id, get_connection


auth = Blueprint("auth", __name__, url_prefix="/api/auth")
RESET_RESPONSE = {
    "success": True,
    "message": "If an account matches and email delivery is available, a one-time code will be sent.",
}


def _secret():
    return os.environ.get("PRICE_LENS_OTP_SECRET") or current_app.config["SECRET_KEY"]


def _digest(label, value):
    return hmac.new(_secret().encode(), f"{label}:{value}".encode(), hashlib.sha256).hexdigest()


def send_otp_email(email, code):
    """Send a recovery code via configured SMTP without logging message contents."""
    host = os.environ.get("PRICE_LENS_SMTP_HOST")
    sender = os.environ.get("PRICE_LENS_SMTP_FROM") or os.environ.get("PRICE_LENS_SMTP_USER")
    if not host or not sender:
        raise RuntimeError("SMTP is not configured")
    port = int(os.environ.get("PRICE_LENS_SMTP_PORT", "587"))
    user = os.environ.get("PRICE_LENS_SMTP_USER")
    password = os.environ.get("PRICE_LENS_SMTP_PASSWORD")
    use_ssl = os.environ.get("PRICE_LENS_SMTP_SSL", "false").lower() == "true"
    use_starttls = os.environ.get("PRICE_LENS_SMTP_STARTTLS", "true").lower() == "true"
    message = EmailMessage()
    message["Subject"] = "Your PriceLens password reset code"
    message["From"] = sender
    message["To"] = email
    message.set_content(
        f"Your PriceLens verification code is {code}. It expires in 10 minutes. "
        "If you did not request this, you can ignore this email."
    )
    context = ssl.create_default_context()
    client = smtplib.SMTP_SSL(host, port, timeout=10, context=context) if use_ssl else smtplib.SMTP(host, port, timeout=10)
    with client:
        if use_starttls and not use_ssl:
            client.starttls(context=context)

        if user and password:
            client.login(user, password)

        client.send_message(message)


def smtp_configuration_error():
    """Return a safe configuration diagnostic without exposing credential values."""
    host = os.environ.get("PRICE_LENS_SMTP_HOST", "").strip()
    sender = (os.environ.get("PRICE_LENS_SMTP_FROM") or os.environ.get("PRICE_LENS_SMTP_USER", "")).strip()
    user = os.environ.get("PRICE_LENS_SMTP_USER", "").strip()
    password = os.environ.get("PRICE_LENS_SMTP_PASSWORD", "")
    if not host or not sender:
        return "Password recovery email is not configured. Set the PriceLens SMTP environment variables."
    if "gmail.com" in host.lower() and (not user or not password):
        return "Gmail recovery email requires PRICE_LENS_SMTP_USER and a Gmail App Password in PRICE_LENS_SMTP_PASSWORD."
    if os.environ.get("PRICE_LENS_SMTP_SSL", "false").lower() != "true" and os.environ.get("PRICE_LENS_SMTP_STARTTLS", "true").lower() != "true":
        return "Password recovery SMTP must use STARTTLS or SSL."
    try:
        port = int(os.environ.get("PRICE_LENS_SMTP_PORT", "587"))
    except ValueError:
        return "PRICE_LENS_SMTP_PORT must be a valid port number."
    if not 1 <= port <= 65535:
        return "PRICE_LENS_SMTP_PORT must be between 1 and 65535."
    return None


def _reset_email(data):
    email = data.get("email", "") if isinstance(data, dict) else ""
    if not isinstance(email, str):
        return None
    normalized = email.strip().lower()
    if len(normalized) > 254 or not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", normalized):
        return None
    return normalized


@auth.route("/signup", methods=["POST"])
def signup():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "A JSON object is required."}), 400

    name = data.get("name", "")
    email = data.get("email", "")
    password = data.get("password", "")

    if not isinstance(name, str) or not isinstance(email, str) or not isinstance(password, str):
        return jsonify({"error": "Name, email and password must be text."}), 400

    name = name.strip()
    email = email.strip().lower()

    if not name or not email or not password:
        return jsonify({
            "error": "Name, email and password are required."
        }), 400

    if len(password) < 8:
        return jsonify({
            "error": "Password must contain at least 8 characters."
        }), 400

    if len(name) > 100 or len(email) > 254 or len(password) > 1024:
        return jsonify({"error": "One or more fields exceed the allowed length."}), 400

    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
        return jsonify({"error": "Enter a valid email address."}), 400

    connection = get_connection()

    try:
        existing_user = connection.execute(
            "SELECT id FROM users WHERE email = ?",
            (email,)
        ).fetchone()

        if existing_user:
            return jsonify({
                "error": "An account with this email already exists."
            }), 409

        password_hash = generate_password_hash(password)

        cursor = connection.execute(
            """
            INSERT INTO users (name, email, password_hash)
            VALUES (?, ?, ?)
            """,
            (name, email, password_hash)
        )

        connection.commit()

        return jsonify({
            "success": True,
            "message": "Account created successfully.",
            "user_id": cursor.lastrowid
        }), 201

    finally:
        connection.close()


@auth.route("/login", methods=["POST"])
def login():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "A JSON object is required."}), 400

    email = data.get("email", "")
    password = data.get("password", "")

    if not isinstance(email, str) or not isinstance(password, str):
        return jsonify({"error": "Email and password must be text."}), 400

    email = email.strip().lower()

    if not email or not password:
        return jsonify({
            "error": "Email and password are required."
        }), 400

    connection = get_connection()

    try:
        user = connection.execute(
            """
            SELECT id, name, email, password_hash, session_version
            FROM users
            WHERE email = ?
            """,
            (email,)
        ).fetchone()

        if not user or not check_password_hash(
            user["password_hash"],
            password
        ):
            return jsonify({
                "error": "Invalid email or password."
            }), 401

        connection.execute(
            """
            UPDATE users
            SET last_login = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (user["id"],)
        )

        connection.commit()

        session.clear()
        session["user_id"] = user["id"]
        session["session_version"] = user["session_version"]

        return jsonify({
            "success": True,
            "message": "Login successful.",
            "user": {
                "id": user["id"],
                "name": user["name"],
                "email": user["email"]
            }
        })

    finally:
        connection.close()


@auth.route("/logout", methods=["POST"])
def logout():
    session.clear()

    return jsonify({
        "success": True,
        "message": "Logged out successfully."
    })


@auth.route("/profile", methods=["GET"])
def profile():
    user_id = current_user_id()

    if not user_id:
        return jsonify({
            "error": "Authentication required."
        }), 401

    connection = get_connection()

    try:
        user = connection.execute(
            """
            SELECT id, name, email, created_at, last_login
            FROM users
            WHERE id = ?
            """,
            (user_id,)
        ).fetchone()

        if not user:
            session.clear()

            return jsonify({
                "error": "User account not found."
            }), 404

        return jsonify({
            "success": True,
            "user": dict(user)
        })

    finally:
        connection.close()


@auth.route("/forgot-password", methods=["POST"])
def forgot_password():
    email = _reset_email(request.get_json(silent=True))
    if email is None:
        return jsonify({"error": "Enter a valid email address."}), 400

    configuration_error = smtp_configuration_error()
    if configuration_error:
        current_app.logger.error("Password recovery email unavailable: %s", configuration_error)
        return jsonify({"error": configuration_error}), 503

    now = int(time.time())
    email_key = _digest("email", email)
    ip_key = _digest("ip", request.remote_addr or "unknown")
    code = f"{secrets.randbelow(1_000_000):06d}"
    connection = get_connection()
    should_send = False
    try:
        ip_limit = connection.execute(
            "SELECT window_started, request_count FROM password_reset_ip_limits WHERE ip_key = ?",
            (ip_key,),
        ).fetchone()
        if ip_limit and now - ip_limit["window_started"] < 3600 and ip_limit["request_count"] >= 5:
            return jsonify(RESET_RESPONSE), 202
        if not ip_limit or now - ip_limit["window_started"] >= 3600:
            connection.execute(
                "INSERT INTO password_reset_ip_limits(ip_key, window_started, request_count) VALUES (?, ?, 1) "
                "ON CONFLICT(ip_key) DO UPDATE SET window_started=excluded.window_started, request_count=1",
                (ip_key, now),
            )
        else:
            connection.execute(
                "UPDATE password_reset_ip_limits SET request_count=request_count+1 WHERE ip_key=?",
                (ip_key,),
            )

        existing = connection.execute(
            "SELECT requested_at FROM password_reset_requests WHERE email_key=?",
            (email_key,),
        ).fetchone()
        if existing and now - existing["requested_at"] < 60:
            connection.commit()
            return jsonify(RESET_RESPONSE), 202

        user = connection.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone()
        should_send = user is not None
        connection.execute(
            "INSERT INTO password_reset_requests(email_key, ip_key, user_id, otp_hash, expires_at, attempts, requested_at, verified_at, reset_token_hash, token_expires_at) "
            "VALUES (?, ?, ?, ?, ?, 0, ?, NULL, NULL, NULL) "
            "ON CONFLICT(email_key) DO UPDATE SET ip_key=excluded.ip_key, user_id=excluded.user_id, otp_hash=excluded.otp_hash, expires_at=excluded.expires_at, attempts=0, requested_at=excluded.requested_at, verified_at=NULL, reset_token_hash=NULL, token_expires_at=NULL",
            (email_key, ip_key, user["id"] if user else None, _digest(f"otp:{email}", code) if user else None, now + 600, now),
        )
        connection.commit()
    finally:
        connection.close()

    if should_send:
        try:
            send_otp_email(email, code)
        except Exception as exc:
            current_app.logger.error("Password recovery email delivery failed (%s)", type(exc).__name__)
            connection = get_connection()
            try:
                connection.execute(
                    "UPDATE password_reset_requests SET otp_hash=NULL, expires_at=? WHERE email_key=?",
                    (now, email_key),
                )
                connection.commit()
            finally:
                connection.close()
    return jsonify(RESET_RESPONSE), 202


@auth.route("/verify-otp", methods=["POST"])
def verify_otp():
    data = request.get_json(silent=True)
    email = _reset_email(data)
    code = data.get("otp", "") if isinstance(data, dict) else ""
    if email is None or not isinstance(code, str) or not re.fullmatch(r"\d{6}", code):
        return jsonify({"error": "The code is invalid or expired."}), 400

    email_key = _digest("email", email)
    now = int(time.time())
    connection = get_connection()
    try:
        row = connection.execute(
            "SELECT * FROM password_reset_requests WHERE email_key=?", (email_key,)
        ).fetchone()
        if not row or not row["user_id"] or not row["otp_hash"] or now > row["expires_at"] or row["attempts"] >= 5:
            return jsonify({"error": "The code is invalid or expired."}), 400
        if not hmac.compare_digest(row["otp_hash"], _digest(f"otp:{email}", code)):
            connection.execute(
                "UPDATE password_reset_requests SET attempts=attempts+1 WHERE email_key=?", (email_key,)
            )
            connection.commit()
            return jsonify({"error": "The code is invalid or expired."}), 400
        reset_token = secrets.token_urlsafe(32)
        connection.execute(
            "UPDATE password_reset_requests SET otp_hash=NULL, verified_at=?, reset_token_hash=?, token_expires_at=? WHERE email_key=?",
            (now, _digest("reset-token", reset_token), now + 900, email_key),
        )
        connection.commit()
        return jsonify({"success": True, "reset_token": reset_token})
    finally:
        connection.close()


@auth.route("/reset-password", methods=["POST"])
def reset_password():
    data = request.get_json(silent=True)
    token = data.get("reset_token", "") if isinstance(data, dict) else ""
    password = data.get("new_password", "") if isinstance(data, dict) else ""
    confirmation = data.get("confirm_password", "") if isinstance(data, dict) else ""
    if not isinstance(token, str) or not token or not isinstance(password, str) or not isinstance(confirmation, str):
        return jsonify({"error": "The password reset session is invalid or expired."}), 400
    if password != confirmation:
        return jsonify({"error": "Passwords do not match."}), 400
    if len(password) < 8 or len(password) > 1024:
        return jsonify({"error": "Use a password between 8 and 1024 characters."}), 400

    now = int(time.time())
    token_hash = _digest("reset-token", token)
    connection = get_connection()
    try:
        row = connection.execute(
            "SELECT email_key, user_id FROM password_reset_requests WHERE reset_token_hash=? AND token_expires_at>=?",
            (token_hash, now),
        ).fetchone()
        if not row or not row["user_id"]:
            return jsonify({"error": "The password reset session is invalid or expired."}), 400
        connection.execute(
            "UPDATE users SET password_hash=?, session_version=session_version+1 WHERE id=?",
            (generate_password_hash(password), row["user_id"]),
        )
        connection.execute(
            "UPDATE password_reset_requests SET reset_token_hash=NULL, token_expires_at=NULL, otp_hash=NULL WHERE email_key=?",
            (row["email_key"],),
        )
        connection.commit()
        session.clear()
        return jsonify({"success": True, "message": "Password updated successfully."})
    finally:
        connection.close()
