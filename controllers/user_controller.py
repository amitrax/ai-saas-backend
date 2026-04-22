"""
User Controller Module
Handles user profile, activity feed, and password change.
"""

import bcrypt
from datetime import datetime, timezone, timedelta
from flask import jsonify, request
from bson.objectid import ObjectId

from config.db import db
from models.user_model import find_user_by_id, users_collection

activity_collection = db["activities"]


def get_profile(current_user: dict):
    """GET /api/user/profile — Returns user profile + usage stats."""
    try:
        user = find_user_by_id(current_user["user_id"])
        if not user:
            return jsonify({"success": False, "message": "User not found."}), 404

        return jsonify({
            "success": True,
            "data": {
                "user_id": str(user["_id"]),
                "name": user["name"],
                "email": user["email"],
                "plan": user.get("plan", "free"),
                "is_verified": user.get("is_verified", False),
                "avatar_url": user.get("avatar_url", ""),
                "usage": user.get("usage", {
                    "chat_count": 0,
                    "image_count": 0,
                    "resume_count": 0,
                    "score_count": 0,
                }),
                "created_at": user["created_at"].isoformat() if user.get("created_at") else None,
            },
        }), 200

    except Exception as e:
        print(f"[Profile Error] {e}")
        return jsonify({"success": False, "message": "An internal server error occurred."}), 500


def get_activity(current_user: dict):
    """
    GET /api/user/activity — Returns the last 10 activity log entries
    plus a 7-day daily breakdown for the chart.
    """
    try:
        uid = current_user["user_id"]

        # Recent 10 activities for the feed
        recent_cursor = activity_collection.find(
            {"user_id": uid},
            {"type": 1, "input": 1, "created_at": 1, "_id": 0},
        ).sort("created_at", -1).limit(10)

        feed = []
        for doc in recent_cursor:
            feed.append({
                "type": doc["type"],
                "label": _activity_label(doc["type"], doc.get("input", "")),
                "time": _time_ago(doc["created_at"]),
            })

        # 7-day chart data
        today = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        chart_data = []
        for i in range(6, -1, -1):
            day_start = today - timedelta(days=i)
            day_end = day_start + timedelta(days=1)
            count = activity_collection.count_documents({
                "user_id": uid,
                "created_at": {"$gte": day_start, "$lt": day_end},
            })
            chart_data.append({
                "day": day_start.strftime("%a"),
                "requests": count,
            })

        return jsonify({
            "success": True,
            "data": {
                "feed": feed,
                "chart": chart_data,
            },
        }), 200

    except Exception as e:
        print(f"[Activity Error] {e}")
        return jsonify({"success": False, "message": "An internal server error occurred."}), 500


def get_chat_history(current_user: dict):
    """
    GET /api/user/chat-history — Returns all past chat interactions for the user.
    """
    try:
        uid = current_user["user_id"]
        # Fetch chat activities
        chats_cursor = activity_collection.find(
            {"user_id": uid, "type": "chat"},
            {"input": 1, "output": 1, "created_at": 1, "_id": 0}
        ).sort("created_at", -1).limit(50)  # load last 50 queries

        history = []
        for doc in chats_cursor:
            history.append({
                "query": doc.get("input", ""),
                "response": doc.get("output", ""),
                "time": _time_ago(doc["created_at"]),
                "created_at": doc["created_at"].isoformat() if doc.get("created_at") else None
            })

        return jsonify({
            "success": True,
            "data": history
        }), 200

    except Exception as e:
        print(f"[Chat History Error] {e}")
        return jsonify({"success": False, "message": "An internal server error occurred."}), 500

def clear_chat_history(current_user: dict):
    """
    DELETE /api/user/chat-history — Deletes all chat history for the user.
    """
    try:
        uid = current_user["user_id"]
        result = activity_collection.delete_many({"user_id": uid, "type": "chat"})
        return jsonify({"success": True, "message": f"Cleared {result.deleted_count} chats."}), 200
    except Exception as e:
        print(f"[Clear Chat Error] {e}")
        return jsonify({"success": False, "message": "Failed to clear chat history."}), 500

def change_password(current_user: dict):
    """
    POST /api/user/change-password
    Body: { current_password, new_password }
    """
    try:
        data = request.get_json()
        current_pw = data.get("current_password", "")
        new_pw = data.get("new_password", "")

        if not current_pw or not new_pw:
            return jsonify({"success": False, "message": "Both current and new password are required."}), 400
        if len(new_pw) < 6:
            return jsonify({"success": False, "message": "New password must be at least 6 characters."}), 400

        user = users_collection.find_one({"_id": ObjectId(current_user["user_id"])})
        if not user:
            return jsonify({"success": False, "message": "User not found."}), 404

        if not bcrypt.checkpw(current_pw.encode("utf-8"), user["password"].encode("utf-8")):
            return jsonify({"success": False, "message": "Current password is incorrect."}), 401

        hashed = bcrypt.hashpw(new_pw.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("utf-8")
        users_collection.update_one(
            {"_id": user["_id"]},
            {"$set": {"password": hashed, "updated_at": datetime.now(timezone.utc)}},
        )

        return jsonify({"success": True, "message": "Password changed successfully."}), 200

    except Exception as e:
        print(f"[Change Password Error] {e}")
        return jsonify({"success": False, "message": "An internal server error occurred."}), 500


def update_name(current_user: dict):
    """
    POST /api/user/update-name
    Body: { name }
    """
    try:
        data = request.get_json()
        name = data.get("name", "").strip()

        if not name or len(name) < 2:
            return jsonify({"success": False, "message": "Name must be at least 2 characters."}), 400

        users_collection.update_one(
            {"_id": ObjectId(current_user["user_id"])},
            {"$set": {"name": name, "updated_at": datetime.now(timezone.utc)}},
        )

        return jsonify({"success": True, "message": "Name updated successfully.", "data": {"name": name}}), 200

    except Exception as e:
        print(f"[Update Name Error] {e}")
        return jsonify({"success": False, "message": "An internal server error occurred."}), 500

def update_avatar(current_user: dict):
    """
    POST /api/user/update-avatar
    Body: { avatar_url }
    """
    try:
        data = request.get_json()
        avatar_url = data.get("avatar_url", "").strip()

        if not avatar_url:
            return jsonify({"success": False, "message": "Avatar URL is required."}), 400

        users_collection.update_one(
            {"_id": ObjectId(current_user["user_id"])},
            {"$set": {"avatar_url": avatar_url, "updated_at": datetime.now(timezone.utc)}},
        )

        return jsonify({"success": True, "message": "Profile picture updated successfully.", "data": {"avatar_url": avatar_url}}), 200

    except Exception as e:
        print(f"[Update Avatar Error] {e}")
        return jsonify({"success": False, "message": "An internal server error occurred."}), 500


# ── Helpers ───────────────────────────────────────────────────────────────────

def _activity_label(activity_type: str, input_text: str) -> str:
    labels = {
        "chat": "💬 Asked AI a question",
        "image": "🎨 Generated an image",
        "resume": "📄 Created a resume",
        "score": "📊 Checked resume score",
    }
    return labels.get(activity_type, "⚡ Used NeuralForge AI")


def _time_ago(dt: datetime) -> str:
    if not dt:
        return "just now"
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    diff = datetime.now(timezone.utc) - dt
    s = int(diff.total_seconds())
    if s < 60:
        return "just now"
    if s < 3600:
        return f"{s // 60}m ago"
    if s < 86400:
        return f"{s // 3600}h ago"
    return f"{s // 86400}d ago"
