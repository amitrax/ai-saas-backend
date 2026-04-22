"""
Authentication Controller
=========================
Handles signup, OTP verification, login, forgot/reset password.

OTP flow:
  1. POST /api/auth/signup  → creates user (unverified) + sends OTP email
  2. POST /api/auth/verify-otp → marks user verified
  3. POST /api/auth/login  → blocked if not verified

OTP storage: dedicated 'otps' MongoDB collection (TTL index optional).
Rate limiting: max 3 OTP requests per email per 10 minutes.
"""

import bcrypt
import random
import string
import uuid
from datetime import datetime, timedelta, timezone
from flask import request, jsonify
from pymongo.errors import DuplicateKeyError

from models.user_model import create_user, find_user_by_email, users_collection
from utils.jwt_helper import generate_token
from utils.email import send_otp_email, send_email
from config.db import db


# ── OTP collection ──────────────────────────────────────────────────────────
otps_collection = db["otps"]
OTP_EXPIRY_MIN = 10       # minutes before OTP expires
OTP_RATE_LIMIT = 3        # max sends per email per rate window
OTP_RATE_WINDOW_MIN = 10  # rate window in minutes


# ── Helpers ──────────────────────────────────────────────────────────────────

def _generate_otp() -> str:
    return "".join(random.choices(string.digits, k=6))


def _is_rate_limited(email: str) -> bool:
    """Returns True if the email has hit the OTP send rate limit."""
    window_start = datetime.now(timezone.utc) - timedelta(minutes=OTP_RATE_WINDOW_MIN)
    count = otps_collection.count_documents({
        "email": email,
        "created_at": {"$gte": window_start},
    })
    return count >= OTP_RATE_LIMIT


def _create_and_send_otp(email: str) -> bool:
    """Generates OTP, stores it, sends email. Returns True on success."""
    otp = _generate_otp()
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(minutes=OTP_EXPIRY_MIN)

    otps_collection.insert_one({
        "email": email,
        "otp": otp,
        "expires_at": expires_at,
        "created_at": now,
    })

    return send_otp_email(email, otp)


# ── Endpoints ─────────────────────────────────────────────────────────────────

def signup():
    """
    POST /api/auth/signup
    Body: { name, email, password }
    Creates unverified user and immediately sends OTP to email.
    """
    try:
        data = request.get_json()

        if not data:
            return jsonify({"success": False, "message": "Request body is required."}), 400

        name = data.get("name", "").strip()
        email = data.get("email", "").strip().lower()
        password = data.get("password", "")

        if not name:
            return jsonify({"success": False, "message": "Name is required."}), 400
        if not email:
            return jsonify({"success": False, "message": "Email is required."}), 400
        if not password or len(password) < 6:
            return jsonify({
                "success": False,
                "message": "Password must be at least 6 characters.",
            }), 400

        # Duplicate check
        existing = find_user_by_email(email)
        if existing:
            if not existing.get("is_verified"):
                # Allow re-sending OTP for unverified accounts
                if _is_rate_limited(email):
                    return jsonify({
                        "success": False,
                        "message": "Too many OTP requests. Please wait 10 minutes.",
                    }), 429
                
                # Update the password just in case they typed a new one during this retry
                # This prevents "Invalid password" upon login after verifying.
                new_hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")
                users_collection.update_one(
                    {"_id": existing["_id"]},
                    {"$set": {"password": new_hashed}}
                )

                _create_and_send_otp(email)
                return jsonify({
                    "success": True,
                    "message": "Account exists but is unverified. A new OTP has been sent.",
                    "data": {"email": email},
                }), 200
            return jsonify({
                "success": False,
                "message": "An account with this email already exists.",
            }), 409

        # Hash password
        hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")

        # Create user (unverified)
        user = create_user(name, email, hashed)

        # Send OTP
        _create_and_send_otp(email)

        return jsonify({
            "success": True,
            "message": "Account created! Check your email for the verification code.",
            "data": {
                "user_id": str(user["_id"]),
                "email": email,
            },
        }), 201

    except DuplicateKeyError:
        return jsonify({"success": False, "message": "An account with this email already exists."}), 409
    except Exception as exc:
        print(f"[Signup Error] {exc}")
        return jsonify({"success": False, "message": "An internal server error occurred."}), 500


def send_otp():
    """
    POST /api/auth/send-otp
    Body: { email }
    Resends OTP (rate-limited to 3 per 10 min).
    """
    try:
        data = request.get_json()
        email = data.get("email", "").strip().lower()

        if not email:
            return jsonify({"success": False, "message": "Email is required."}), 400

        user = find_user_by_email(email)
        if not user:
            return jsonify({"success": False, "message": "No account found with that email."}), 404

        if user.get("is_verified"):
            return jsonify({"success": False, "message": "Account is already verified."}), 400

        if _is_rate_limited(email):
            return jsonify({
                "success": False,
                "message": "Too many OTP requests. Please wait 10 minutes before trying again.",
            }), 429

        _create_and_send_otp(email)

        return jsonify({"success": True, "message": "Verification code sent to your email."}), 200

    except Exception as exc:
        print(f"[Send OTP Error] {exc}")
        return jsonify({"success": False, "message": "An internal server error occurred."}), 500


def verify_otp():
    """
    POST /api/auth/verify-otp
    Body: { email, otp }
    Validates the OTP and marks the user as verified.
    """
    try:
        data = request.get_json()
        email = data.get("email", "").strip().lower()
        otp = data.get("otp", "").strip()

        if not email or not otp:
            return jsonify({"success": False, "message": "Email and OTP are required."}), 400

        if len(otp) != 6 or not otp.isdigit():
            return jsonify({"success": False, "message": "OTP must be exactly 6 digits."}), 400

        user = find_user_by_email(email)
        if not user:
            return jsonify({"success": False, "message": "No account found with that email."}), 404

        if user.get("is_verified"):
            return jsonify({"success": True, "message": "Account is already verified. Please log in."}), 200

        now = datetime.now(timezone.utc)

        # Find the most recent valid OTP for this email
        otp_record = otps_collection.find_one(
            {
                "email": email,
                "otp": otp,
                "expires_at": {"$gt": now},
            },
            sort=[("created_at", -1)],
        )

        if not otp_record:
            # Check if OTP exists but expired
            expired = otps_collection.find_one({"email": email, "otp": otp})
            if expired:
                return jsonify({"success": False, "message": "OTP has expired. Please request a new one."}), 400
            return jsonify({"success": False, "message": "Invalid OTP. Please check and try again."}), 400

        # Mark user as verified
        users_collection.update_one(
            {"_id": user["_id"]},
            {"$set": {"is_verified": True, "verified_at": now}},
        )

        # Clean up all OTPs for this email
        otps_collection.delete_many({"email": email})

        return jsonify({"success": True, "message": "Email verified! You can now log in."}), 200

    except Exception as exc:
        print(f"[Verify OTP Error] {exc}")
        return jsonify({"success": False, "message": "An internal server error occurred."}), 500


def login():
    """
    POST /api/auth/login
    Body: { email, password }
    Blocked if user is not verified.
    """
    try:
        data = request.get_json()

        if not data:
            return jsonify({"success": False, "message": "Request body is required."}), 400

        email = data.get("email", "").strip().lower()
        password = data.get("password", "")

        if not email:
            return jsonify({"success": False, "message": "Email is required."}), 400
        if not password:
            return jsonify({"success": False, "message": "Password is required."}), 400

        user = find_user_by_email(email)
        if not user:
            return jsonify({"success": False, "message": "Invalid email or password."}), 401

        # Block unverified users
        if not user.get("is_verified"):
            return jsonify({
                "success": False,
                "message": "Please verify your email before logging in. Check your inbox for the OTP.",
            }), 403

        # Verify password
        is_valid = bcrypt.checkpw(password.encode("utf-8"), user["password"].encode("utf-8"))
        if not is_valid:
            return jsonify({"success": False, "message": "Invalid email or password."}), 401

        # Generate JWT
        token = generate_token(str(user["_id"]), user["email"])

        return jsonify({
            "success": True,
            "message": "Login successful.",
            "data": {
                "token": token,
                "user": {
                    "user_id": str(user["_id"]),
                    "name": user["name"],
                    "email": user["email"],
                    "plan": user.get("plan", "free"),
                    "avatar_url": user.get("avatar_url", ""),
                },
            },
        }), 200

    except Exception as exc:
        print(f"[Login Error] {exc}")
        return jsonify({"success": False, "message": "An internal server error occurred."}), 500


def forgot_password():
    """POST /api/auth/forgot-password — generates reset token and emails it."""
    try:
        data = request.get_json()
        email = data.get("email", "").strip().lower()

        if not email:
            return jsonify({"success": False, "message": "Email is required."}), 400

        user = find_user_by_email(email)
        if not user:
            # Don't reveal whether email exists
            return jsonify({"success": True, "message": "If that email exists, a reset link was sent."}), 200

        token = str(uuid.uuid4())
        expiry = datetime.now(timezone.utc) + timedelta(minutes=15)

        users_collection.update_one(
            {"_id": user["_id"]},
            {"$set": {"reset_token": token, "reset_token_expiry": expiry}},
        )

        import os
        from dotenv import load_dotenv
        load_dotenv(override=True)
        frontend_url = os.getenv("FRONTEND_URL", "http://localhost:3000").rstrip("/")

        reset_link = f"{frontend_url}/reset-password/{token}"
        html = f"""
        <div style="font-family:Arial,sans-serif;max-width:520px;margin:0 auto;">
          <h2 style="color:#4f46e5;">Password Reset</h2>
          <p>Click the link below to reset your NeuralForge password. It expires in 15 minutes.</p>
          <a href="{reset_link}"
             style="display:inline-block;padding:14px 28px;background:#4f46e5;
                    color:#fff;text-decoration:none;border-radius:10px;font-weight:600;">
            Reset Password
          </a>
          <p style="color:#94a3b8;font-size:12px;margin-top:24px;">
            If you didn't request this, ignore this email.
          </p>
        </div>
        """
        send_email(email, "Reset Your NeuralForge Password", html)

        return jsonify({"success": True, "message": "If that email exists, a reset link was sent."}), 200

    except Exception as exc:
        print(f"[Forgot Password Error] {exc}")
        return jsonify({"success": False, "message": "An internal server error occurred."}), 500


def reset_password():
    """POST /api/auth/reset-password — resets password using the token."""
    try:
        data = request.get_json()
        token = data.get("token", "").strip()
        new_password = data.get("new_password", "")

        if not token or not new_password or len(new_password) < 6:
            return jsonify({
                "success": False,
                "message": "Valid token and a new password (min 6 chars) are required.",
            }), 400

        user = users_collection.find_one({"reset_token": token})
        if not user:
            return jsonify({"success": False, "message": "Invalid or expired reset link."}), 400

        expiry = user.get("reset_token_expiry")
        if not expiry or datetime.now(timezone.utc) > expiry.replace(tzinfo=timezone.utc):
            return jsonify({"success": False, "message": "Reset link has expired."}), 400

        hashed = bcrypt.hashpw(new_password.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")

        users_collection.update_one(
            {"_id": user["_id"]},
            {
                "$set": {"password": hashed},
                "$unset": {"reset_token": "", "reset_token_expiry": ""},
            },
        )

        return jsonify({"success": True, "message": "Password reset successfully. You can now log in."}), 200

    except Exception as exc:
        print(f"[Reset Password Error] {exc}")
        return jsonify({"success": False, "message": "An internal server error occurred."}), 500


def test_email():
    """
    GET /api/auth/test-email
    Sends a test email to the configured GMAIL_USER.
    """
    try:
        import os
        to = os.getenv("GMAIL_USER", "sabwebsite7@gmail.com")
        success = send_email(to, "Test NeuralForge Backend", "<h1>Success</h1><p>Email delivery is working.</p>")
        if success:
            return jsonify({"success": True, "message": f"Test email sent successfully to {to}."}), 200
        else:
            return jsonify({"success": False, "message": "Failed to send test email. Check server logs."}), 500
    except Exception as exc:
        print(f"[Test Email Error] {exc}")
        return jsonify({"success": False, "message": "An internal server error occurred."}), 500

