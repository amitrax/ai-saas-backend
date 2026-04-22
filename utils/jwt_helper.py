"""
JWT Helper Module
Handles JWT token generation and verification.
"""

import os
from datetime import datetime, timedelta, timezone
import jwt
from dotenv import load_dotenv

load_dotenv()

JWT_SECRET = os.getenv("JWT_SECRET", "fallback_secret_key")
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_HOURS = 24


def generate_token(user_id: str, email: str) -> str:
    """
    Generate a JWT token for an authenticated user.

    Args:
        user_id: The user's MongoDB ObjectId as a string.
        email: The user's email address.

    Returns:
        Encoded JWT token string.
    """
    payload = {
        "user_id": user_id,
        "email": email,
        "iat": datetime.now(timezone.utc),
        "exp": datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRATION_HOURS),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def verify_token(token: str) -> dict | None:
    """
    Verify and decode a JWT token.

    Args:
        token: The JWT token string to verify.

    Returns:
        Decoded payload dictionary, or None if invalid/expired.
    """
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.InvalidTokenError:
        return None
