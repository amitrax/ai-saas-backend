"""
Upload Routes Module
====================
Provides endpoints for file uploading.
"""

from flask import Blueprint
from controllers.upload_controller import upload_file
from utils.auth_middleware import token_required

upload_bp = Blueprint("upload", __name__, url_prefix="/api/upload")

@upload_bp.route("", methods=["POST"])
@upload_bp.route("/", methods=["POST"])
@token_required
def handle_upload(**kwargs):
    return upload_file(kwargs["current_user"])
