"""
Upload Controller Module
========================
Handles file upload logic including validation, saving to disk,
and storing metadata in MongoDB.
"""

import os
import uuid
from datetime import datetime, timezone
from flask import request, jsonify
from werkzeug.utils import secure_filename
from config.db import db
from bson.objectid import ObjectId

# Allowed extensions
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "pdf", "docx"}
MAX_CONTENT_LENGTH = 20 * 1024 * 1024  # 20MB

# MongoDB Collection
files_collection = db["files"]

# Upload directory (created at startup in app.py)
UPLOAD_FOLDER = os.path.join(os.getcwd(), "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

def upload_file(current_user: dict):
    """
    POST /api/upload
    Expects multipart/form-data with a "file" field.
    """
    try:
        if "file" not in request.files:
            return jsonify({"success": False, "message": "No file part in the request."}), 400
        
        file = request.files["file"]
        if file.filename == "":
            return jsonify({"success": False, "message": "No selected file."}), 400

        # Check file extension
        if not allowed_file(file.filename):
            return jsonify({
                "success": False,
                "message": f"Unsupported file type. Allowed: {', '.join(ALLOWED_EXTENSIONS)}"
            }), 400
        
        # Check size limit (by reading a chunk and evaluating content length or reading entirely)
        # However, Flask normally processes content length. We'll do it safely:
        file.seek(0, os.SEEK_END)
        file_size = file.tell()
        if file_size > MAX_CONTENT_LENGTH:
            return jsonify({"success": False, "message": "File exceeds the 20MB size limit."}), 413
        file.seek(0) # Reset pointer

        # Generate safe and unique filename
        ext = file.filename.rsplit(".", 1)[1].lower()
        original_name = secure_filename(file.filename)
        unique_id = str(uuid.uuid4())
        new_filename = f"{unique_id}.{ext}"
        
        file_path = os.path.join(UPLOAD_FOLDER, new_filename)
        file.save(file_path)

        file_url = f"/uploads/{new_filename}"
        
        # Determine strict type
        if ext in {"pdf", "docx"}:
            file_category = "document"
        else:
            file_category = "image"
            
        file_type = file.content_type  # e.g. "image/png" or "application/pdf"

        # Save metadata to DB
        doc = {
            "user_id": ObjectId(current_user["user_id"]),
            "original_name": original_name,
            "file_name": new_filename,
            "file_url": file_url,
            "category": file_category,
            "type": file_type,
            "size": file_size,
            "created_at": datetime.now(timezone.utc)
        }
        
        result = files_collection.insert_one(doc)

        return jsonify({
            "success": True,
            "message": "File uploaded successfully.",
            "data": {
                "file_id": str(result.inserted_id),
                "file_url": file_url,
                "file_type": file_type,
                "category": file_category,
                "original_name": original_name
            }
        }), 201

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"success": False, "message": "An internal server error occurred during upload."}), 500
