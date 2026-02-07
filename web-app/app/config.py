"""Configuration from environment."""
import os

# Required
SERVER_SECRET = os.environ.get("SERVER_SECRET", "").encode("utf-8") or b"dev-secret-change-in-production"
DATABASE_PATH = os.environ.get("DATABASE_PATH", "/data/pruef.db")

# Admin: X-Admin-Key header only (query param avoided to prevent logging in access logs)
ADMIN_KEY = os.environ.get("ADMIN_KEY", "")

# Dashboard Basic Auth (Flask-level)
DASHBOARD_USER = os.environ.get("DASHBOARD_USER", "admin")
DASHBOARD_PASSWORD = os.environ.get("DASHBOARD_PASSWORD", "change-me")

# Optional: if set, POST /api/check with header X-Load-Test-Key: <value> skips rate limiting (for load testing)
LOAD_TEST_BYPASS_KEY = os.environ.get("LOAD_TEST_BYPASS_KEY", "")

# Rate limit: 10 checks per 10 minutes per user_id
RATE_LIMIT_COUNT = 10
RATE_LIMIT_WINDOW_SECONDS = 600
BLOCK_DURATION_SECONDS = 600

# Retention: purge events older than 90 days (lazy on write)
RETENTION_DAYS = 90

# Timezone for dashboard display
DISPLAY_TIMEZONE = "Europe/Berlin"
