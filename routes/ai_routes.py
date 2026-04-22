"""
AI Routes Module
"""

from flask import Blueprint
from controllers.ai_controller import chat, generate_image, generate_resume, generate_score
from utils.auth_middleware import token_required

ai_bp = Blueprint("ai", __name__, url_prefix="/api/ai")


@ai_bp.route("/chat", methods=["POST"])
@token_required
def ai_chat(**kwargs):
    return chat(kwargs["current_user"])


@ai_bp.route("/image", methods=["POST"])
@token_required
def ai_image(**kwargs):
    return generate_image(kwargs["current_user"])


@ai_bp.route("/resume", methods=["POST"])
@token_required
def ai_resume(**kwargs):
    return generate_resume(kwargs["current_user"])


# Both /score (legacy) and /ats-score (new file upload) point to same handler
@ai_bp.route("/score", methods=["POST"])
@ai_bp.route("/ats-score", methods=["POST"])
@token_required
def ai_score(**kwargs):
    return generate_score(kwargs["current_user"])
