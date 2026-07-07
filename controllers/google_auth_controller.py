"""
Google OAuth 2.0 Controller
============================
Implements the server-side Authorization Code flow with Google.

Flow:
  1. GET  /api/auth/google/login     → redirect to Google's OAuth consent screen
  2. GET  /api/auth/google/callback  → receive code, exchange for tokens,
                                       verify ID token, find/create user,
                                       issue app JWT, redirect to frontend

Google handles 100% of authentication — including 2FA, passkeys, and
security prompts. We never see or store the user's Google password.
"""

import os
import urllib.parse
import secrets
import requests as http_requests
from flask import request, jsonify, redirect, session

from models.user_model import find_or_create_google_user
from utils.jwt_helper import generate_token

# ── Config ────────────────────────────────────────────────────────────────────

GOOGLE_CLIENT_ID     = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
GOOGLE_REDIRECT_URI  = os.getenv(
    "GOOGLE_REDIRECT_URI",
    "http://localhost:5000/api/auth/google/callback",
)
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")

GOOGLE_AUTH_URL  = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"
GOOGLE_TOKEN_INFO_URL = "https://oauth2.googleapis.com/tokeninfo"

# ── In-memory state store (use Redis/DB in production) ────────────────────────
# Maps CSRF state → True (we only care that the state was issued by us)
_valid_states: set = set()


# ── Endpoints ─────────────────────────────────────────────────────────────────

def google_login():
    """
    GET /api/auth/google/login

    Generates a Google OAuth 2.0 authorization URL with a CSRF state token
    and redirects the browser to Google's login/consent page.

    Google then handles all authentication:
      - account selection
      - password prompt
      - 2-Step Verification (Prompt, OTP, Passkey, Authenticator)
    """
    if not GOOGLE_CLIENT_ID or not GOOGLE_CLIENT_SECRET:
        return jsonify({
            "success": False,
            "message": (
                "Google OAuth is not configured. "
                "Please set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET in your .env file."
            ),
        }), 503

    # Generate a cryptographically random CSRF state token
    state = secrets.token_urlsafe(32)
    _valid_states.add(state)

    # Build the OAuth URL — Google will show its own login / 2FA / consent screens
    params = {
        "client_id":     GOOGLE_CLIENT_ID,
        "redirect_uri":  GOOGLE_REDIRECT_URI,
        "response_type": "code",
        "scope":         "openid email profile",
        "state":         state,
        "access_type":   "online",
        # Force account selection so users can switch accounts
        "prompt":        "select_account",
    }

    auth_url = f"{GOOGLE_AUTH_URL}?{urllib.parse.urlencode(params)}"
    return redirect(auth_url)


def google_callback():
    """
    GET /api/auth/google/callback

    Handles Google's redirect after the user authenticates.

    Steps:
      1. Validate CSRF state
      2. Handle user-denied errors from Google
      3. Exchange authorization code for access + ID tokens
      4. Verify the ID token with Google's tokeninfo endpoint
      5. Find or create the user in MongoDB
      6. Generate an app-level JWT
      7. Redirect to the frontend with the token
    """
    # ── 1. Extract query params ───────────────────────────────────────────────
    code  = request.args.get("code")
    state = request.args.get("state")
    error = request.args.get("error")

    frontend_callback = f"{FRONTEND_URL}/auth/google/callback"

    # ── 2. Handle OAuth errors (user denied, etc.) ────────────────────────────
    if error:
        error_msg = {
            "access_denied": "You cancelled the Google sign-in. Please try again.",
        }.get(error, f"Google authentication failed: {error}")

        return redirect(
            f"{frontend_callback}?error={urllib.parse.quote(error_msg)}"
        )

    # ── 3. Validate CSRF state ────────────────────────────────────────────────
    if not state or state not in _valid_states:
        return redirect(
            f"{frontend_callback}?error="
            + urllib.parse.quote("Invalid state parameter. Please try signing in again.")
        )
    _valid_states.discard(state)  # one-time use

    if not code:
        return redirect(
            f"{frontend_callback}?error="
            + urllib.parse.quote("No authorization code received from Google.")
        )

    # ── 4. Exchange code for tokens ───────────────────────────────────────────
    try:
        token_resp = http_requests.post(
            GOOGLE_TOKEN_URL,
            data={
                "code":          code,
                "client_id":     GOOGLE_CLIENT_ID,
                "client_secret": GOOGLE_CLIENT_SECRET,
                "redirect_uri":  GOOGLE_REDIRECT_URI,
                "grant_type":    "authorization_code",
            },
            timeout=10,
        )
        token_data = token_resp.json()
    except Exception as exc:
        print(f"[Google OAuth] Token exchange error: {exc}")
        return redirect(
            f"{frontend_callback}?error="
            + urllib.parse.quote("Failed to communicate with Google. Please try again.")
        )

    if "error" in token_data:
        print(f"[Google OAuth] Token exchange failed: {token_data}")
        return redirect(
            f"{frontend_callback}?error="
            + urllib.parse.quote("Google authentication failed. Please try again.")
        )

    id_token    = token_data.get("id_token")
    access_token = token_data.get("access_token")

    if not id_token or not access_token:
        return redirect(
            f"{frontend_callback}?error="
            + urllib.parse.quote("Incomplete response from Google. Please try again.")
        )

    # ── 5. Verify the ID token with Google ────────────────────────────────────
    # We verify by calling Google's tokeninfo endpoint — this is the secure,
    # official method that validates the token's signature, expiry, and audience.
    try:
        info_resp = http_requests.get(
            GOOGLE_TOKEN_INFO_URL,
            params={"id_token": id_token},
            timeout=10,
        )
        info = info_resp.json()
    except Exception as exc:
        print(f"[Google OAuth] Token verification error: {exc}")
        return redirect(
            f"{frontend_callback}?error="
            + urllib.parse.quote("Failed to verify identity with Google. Please try again.")
        )

    # Verify the token was issued for OUR app
    if info.get("aud") != GOOGLE_CLIENT_ID:
        print(f"[Google OAuth] Token audience mismatch: {info.get('aud')}")
        return redirect(
            f"{frontend_callback}?error="
            + urllib.parse.quote("Token verification failed. Please try again.")
        )

    if info.get("error_description"):
        print(f"[Google OAuth] Token info error: {info}")
        return redirect(
            f"{frontend_callback}?error="
            + urllib.parse.quote("Invalid or expired token from Google.")
        )

    # ── 6. Extract verified profile ───────────────────────────────────────────
    google_id = info.get("sub")   # Google's stable unique user ID
    email     = info.get("email")
    name      = info.get("name", email.split("@")[0] if email else "User")
    picture   = info.get("picture", "")

    if not google_id or not email:
        return redirect(
            f"{frontend_callback}?error="
            + urllib.parse.quote("Could not retrieve your profile from Google.")
        )

    # ── 7. Find or create user in MongoDB ────────────────────────────────────
    try:
        user = find_or_create_google_user(
            google_id=google_id,
            email=email,
            name=name,
            picture=picture,
        )
    except Exception as exc:
        print(f"[Google OAuth] DB error: {exc}")
        return redirect(
            f"{frontend_callback}?error="
            + urllib.parse.quote("Account creation failed. Please try again.")
        )

    # ── 8. Issue app JWT ──────────────────────────────────────────────────────
    app_token = generate_token(str(user["_id"]), user["email"])

    # ── 9. Redirect to frontend with token + user ─────────────────────────────
    user_payload = urllib.parse.quote_plus({
        "user_id":    str(user["_id"]),
        "name":       user.get("name", ""),
        "email":      user.get("email", ""),
        "avatar_url": user.get("avatar_url", ""),
        "plan":       user.get("plan", "free"),
    }.__str__())  # simple approach — we pass as query param

    # Pass as individual query params for easy parsing on frontend
    params = urllib.parse.urlencode({
        "token":      app_token,
        "user_id":    str(user["_id"]),
        "name":       user.get("name", ""),
        "email":      user.get("email", ""),
        "avatar_url": user.get("avatar_url", ""),
        "plan":       user.get("plan", "free"),
    })

    print(f"[Google OAuth] Authenticated user: {email}")
    return redirect(f"{frontend_callback}?{params}")
