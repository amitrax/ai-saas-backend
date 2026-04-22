"""
Authentication Middleware Module
Provides a decorator to protect routes that require JWT authentication.
"""

from functools import wraps
from flask import request, jsonify
from utils.jwt_helper import verify_token


def token_required(f):
    """
    Decorator that protects a route by requiring a valid JWT token
    in the Authorization header (Bearer <token>).

    On success, injects 'current_user' (decoded JWT payload) into
    the wrapped function's kwargs.
    """

    @wraps(f)
    def decorated(*args, **kwargs):
        token = None

        # Extract token from Authorization header
        auth_header = request.headers.get("Authorization")
        if auth_header and auth_header.startswith("Bearer "):
            token = auth_header.split(" ", 1)[1]

        if not token:
            return jsonify({
                "success": False,
                "message": "Authentication token is missing. Please provide a valid Bearer token.",
            }), 401

        # Verify the token
        payload = verify_token(token)
        if payload is None:
            return jsonify({
                "success": False,
                "message": "Token is invalid or has expired. Please log in again.",
            }), 401

        # Inject current user info into the route handler
        kwargs["current_user"] = payload
        return f(*args, **kwargs)

    return decorated
