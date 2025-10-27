# backend/app/__init__.py
"""
Package init: load environment variables from a .env file if present.
This runs before app modules import os.getenv for configuration.
"""

from dotenv import load_dotenv

load_dotenv()