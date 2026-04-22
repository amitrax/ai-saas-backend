"""
AI SaaS Backend Application
============================
Flask backend with MongoDB, JWT authentication, Groq AI chat,
and HuggingFace image generation.

Run: python app.py
"""

import os
from dotenv import load_dotenv
from flask import Flask, jsonify
from flask_cors import CORS

# Load environment variables before any other imports
load_dotenv()

from routes.auth_routes import auth_bp
from routes.user_routes import user_bp
from routes.ai_routes import ai_bp
from routes.upload_routes import upload_bp


app = Flask(__name__, static_url_path='/uploads', static_folder='uploads')

# Enable CORS for all routes (configure origins in production)
CORS(app, resources={
    r"/api/*": {
        "origins": "*",
        "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        "allow_headers": ["Content-Type", "Authorization"],
    }
})

# Register route blueprints
app.register_blueprint(auth_bp)
app.register_blueprint(user_bp)
app.register_blueprint(ai_bp)
app.register_blueprint(upload_bp)

# --- Health Check Endpoints ---
@app.route("/api/health", methods=["GET"])
def health_check():
    return jsonify({
        "success": True,
        "message": "AI SaaS Backend is running.",
        "version": "1.0.0",
    }), 200

@app.route("/health", methods=["GET"])
@app.route("/", methods=["GET"])
def root_health():
    return "Backend running", 200

@app.route("/db-health", methods=["GET"])
def db_health_route():
    from config.db import db
    try:
        db.command("ping")
        return jsonify({"status": "healthy", "database": "connected"}), 200
    except Exception as e:
        return jsonify({"status": "unhealthy", "database": "disconnected", "error": str(e)}), 500

# --- Global Error Handlers ---
@app.errorhandler(404)
def not_found(error):
    return jsonify({
        "success": False,
        "message": "The requested resource was not found.",
    }), 404

@app.errorhandler(405)
def method_not_allowed(error):
    return jsonify({
        "success": False,
        "message": "HTTP method not allowed for this endpoint.",
    }), 405

@app.errorhandler(500)
def internal_error(error):
    return jsonify({
        "success": False,
        "message": "An internal server error occurred.",
    }), 500


if __name__ == "__main__":
    port = int(os.getenv("PORT", os.getenv("FLASK_PORT", 5000)))
    debug = os.getenv("FLASK_DEBUG", "True").lower() == "true"

    print(f"\n{'='*50}")
    print(f"  AI SaaS Backend v1.0.0")
    print(f"  Running on http://127.0.0.1:{port}")
    print(f"  Debug mode: {debug}")
    print(f"{'='*50}\n")

    app.run(host="0.0.0.0", port=port)
