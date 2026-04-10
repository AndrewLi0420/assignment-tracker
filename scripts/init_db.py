"""Run this once to create the database schema."""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from app.db import init_db

if __name__ == "__main__":
    init_db()
    print("Database initialized.")

#Deploy it
