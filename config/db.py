"""
Database Configuration Module
Handles MongoDB connection using pymongo.
"""

import os
import sys
from pymongo import MongoClient
import certifi
from dotenv import load_dotenv

import urllib.parse
import re

load_dotenv()

raw_uri = os.getenv("MONGO_URI", "mongodb://localhost:27017/ai_saas_db")

# Helper to automatically escape special characters in the password if they exist
match = re.match(r'(mongodb(?:\+srv)?://[^:]+:)(.*)(@[^@/]+/[^?]+)', raw_uri)
if match:
    prefix, password, rest = match.groups()
    MONGO_URI = f"{prefix}{urllib.parse.quote_plus(password)}{rest}"
else:
    MONGO_URI = raw_uri


def get_database():
    """
    Create and return a MongoDB database connection.
    Returns the database instance for the AI SaaS application.
    """
    client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000, tlsCAFile=certifi.where())
    db_name = MONGO_URI.rsplit("/", 1)[-1].split("?")[0] if "/" in MONGO_URI else "ai_saas_db"
    db = client[db_name]

    try:
        # Verify connection
        client.admin.command("ping")
        print("[OK] MongoDB connected successfully")
    except Exception as e:
        print(f"[FAIL] MongoDB connection failed at startup: {e}")
        print("[INFO] The server will still start, but database operations will fail.")
        print("[INFO] Fix the credentials in your .env and the connection will restore.")

    return db


# Initialize database instance
db = get_database()
