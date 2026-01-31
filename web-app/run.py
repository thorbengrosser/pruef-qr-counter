"""Run the Flask app. No cookies, no session."""
import os
import sys

# Run from web-app directory so static/templates resolve
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app

app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
