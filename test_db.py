import os
from config.db import db

def test_database_operations():
    try:
        users = db["users"]
        print("Inserting a test user...")
        test_user = {"name": "Test User", "email": "test@example.com", "role": "test"}
        result = users.insert_one(test_user)
        print(f"User inserted with ID: {result.inserted_id}")

        print("Fetching test user...")
        fetched_user = users.find_one({"_id": result.inserted_id})
        print(f"Successfully fetched test user: {fetched_user['name']}")

        # Clean up
        users.delete_one({"_id": result.inserted_id})
        print("Test complete and data cleaned up successfully!")
    except Exception as e:
        print(f"Error during database operations: {e}")

if __name__ == "__main__":
    test_database_operations()
