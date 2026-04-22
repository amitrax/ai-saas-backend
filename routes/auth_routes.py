"""
Authentication Routes Module
Defines routes for user signup and login.
"""

from flask import Blueprint
from controllers.auth_controller import signup, login, send_otp, verify_otp, forgot_password, reset_password, test_email

auth_bp = Blueprint("auth", __name__, url_prefix="/api/auth")

# POST /api/auth/signup - Register a new user
auth_bp.route("/signup", methods=["POST"])(signup)

# POST /api/auth/login - Authenticate and get JWT token
auth_bp.route("/login", methods=["POST"])(login)

# POST /api/auth/send-otp - Send an OTP to user email
auth_bp.route("/send-otp", methods=["POST"])(send_otp)

# POST /api/auth/verify-otp - Verify user OTP
auth_bp.route("/verify-otp", methods=["POST"])(verify_otp)

# POST /api/auth/forgot-password - Send password reset email
auth_bp.route("/forgot-password", methods=["POST"])(forgot_password)

# POST /api/auth/reset-password - Reset password using token
auth_bp.route("/reset-password", methods=["POST"])(reset_password)

# GET /api/auth/test-email - Test email sending functionality
auth_bp.route("/test-email", methods=["GET"])(test_email)

