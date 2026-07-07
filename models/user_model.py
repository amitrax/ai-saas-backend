"""
User Model Module
Defines the user schema and database operations for the users collection.
"""

from datetime import datetime, timezone
from config.db import db

# MongoDB collection reference
users_collection = db["users"]

# Create unique indexes
users_collection.create_index("email", unique=True)


def create_user(name: str, email: str, hashed_password: str) -> dict:
    """
    Insert a new user document into the users collection.

    Args:
        name: User's full name.
        email: User's email address (must be unique).
        hashed_password: Bcrypt-hashed password string.

    Returns:
        The inserted user document (without password).
    """
    user_doc = {
        "name": name,
        "email": email,
        "password": hashed_password,
        "plan": "free",
        "usage": {
            "chat_count": 0,
            "image_count": 0,
            "resume_count": 0,
            "score_count": 0,
        },
        "is_verified": False,
        "otp": None,
        "otp_expiry": None,
        "reset_token": None,
        "reset_token_expiry": None,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    }

    result = users_collection.insert_one(user_doc)
    user_doc["_id"] = result.inserted_id

    # Return user without password
    safe_user = {k: v for k, v in user_doc.items() if k != "password"}
    return safe_user


def find_user_by_email(email: str) -> dict | None:
    """
    Find a user by their email address.

    Args:
        email: The email to search for.

    Returns:
        The user document or None if not found.
    """
    return users_collection.find_one({"email": email})


def find_user_by_id(user_id) -> dict | None:
    """
    Find a user by their MongoDB ObjectId.

    Args:
        user_id: The ObjectId to search for.

    Returns:
        The user document (without password) or None if not found.
    """
    from bson.objectid import ObjectId

    user = users_collection.find_one({"_id": ObjectId(user_id)})
    if user:
        user.pop("password", None)
    return user


def find_or_create_google_user(google_id: str, email: str, name: str, picture: str) -> dict:
    """
    Find an existing user by email (or google_id) and update their Google info,
    or create a brand-new OAuth user if none exists.

    Google users have no password field — Google owns their authentication.

    Args:
        google_id: The unique sub/ID from Google's ID token.
        email:     Verified email from the Google ID token.
        name:      Display name from the Google profile.
        picture:   Profile picture URL from Google.

    Returns:
        The user document (without password).
    """
    now = datetime.now(timezone.utc)

    # Try to find an existing user by email
    existing = users_collection.find_one({"email": email})

    if existing:
        # Update Google-specific fields in case they changed
        users_collection.update_one(
            {"_id": existing["_id"]},
            {
                "$set": {
                    "google_id": google_id,
                    "name": name,
                    "avatar_url": picture,
                    "is_verified": True,  # Google accounts are always verified
                    "updated_at": now,
                }
            },
        )
        existing.update({
            "google_id": google_id,
            "name": name,
            "avatar_url": picture,
            "is_verified": True,
        })
        existing.pop("password", None)
        return existing

    # Create a new OAuth user (no password)
    user_doc = {
        "google_id": google_id,
        "name": name,
        "email": email,
        "password": None,          # Google users never have a local password
        "avatar_url": picture,
        "auth_provider": "google",
        "plan": "free",
        "usage": {
            "chat_count": 0,
            "image_count": 0,
            "resume_count": 0,
            "score_count": 0,
        },
        "is_verified": True,        # Google handles verification
        "otp": None,
        "otp_expiry": None,
        "reset_token": None,
        "reset_token_expiry": None,
        "created_at": now,
        "updated_at": now,
    }

    result = users_collection.insert_one(user_doc)
    user_doc["_id"] = result.inserted_id
    user_doc.pop("password", None)
    return user_doc


def increment_usage(user_id, usage_type: str) -> bool:
    """
    Increment a user's usage counter for a specific activity type.

    Args:
        user_id: The user's ObjectId.
        usage_type: Either 'chat_count' or 'image_count'.

    Returns:
        True if the update was successful, False otherwise.
    """
    from bson.objectid import ObjectId

    result = users_collection.update_one(
        {"_id": ObjectId(user_id)},
        {
            "$inc": {f"usage.{usage_type}": 1},
            "$set": {"updated_at": datetime.now(timezone.utc)},
        },
    )
    return result.modified_count > 0
