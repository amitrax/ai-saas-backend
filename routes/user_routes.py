"""
User Routes Module
"""

from flask import Blueprint
from controllers.user_controller import get_profile, get_activity, change_password, update_name, update_avatar, get_chat_history, clear_chat_history
from utils.auth_middleware import token_required

user_bp = Blueprint("user", __name__, url_prefix="/api/user")


@user_bp.route("/profile", methods=["GET"])
@token_required
def profile(**kwargs):
    return get_profile(kwargs["current_user"])


@user_bp.route("/activity", methods=["GET"])
@token_required
def activity(**kwargs):
    return get_activity(kwargs["current_user"])


@user_bp.route("/chat-history", methods=["GET"])
@token_required
def chat_history(**kwargs):
    return get_chat_history(kwargs["current_user"])


@user_bp.route("/chat-history", methods=["DELETE"])
@token_required
def delete_chat_history(**kwargs):
    return clear_chat_history(kwargs["current_user"])


@user_bp.route("/change-password", methods=["POST"])
@token_required
def change_pw(**kwargs):
    return change_password(kwargs["current_user"])


@user_bp.route("/update-name", methods=["POST"])
@token_required
def update_n(**kwargs):
    return update_name(kwargs["current_user"])


@user_bp.route("/update-avatar", methods=["POST"])
@token_required
def update_a(**kwargs):
    return update_avatar(kwargs["current_user"])
